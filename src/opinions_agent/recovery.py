"""Narrow artifact recovery and git-phase reconciliation for opinion runs."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths
from opinions_agent.fsio import write_text_atomic
from opinions_agent.models import GitPhase, OpinionRun
from opinions_agent.tools.git_ops import assert_targets_clean, git_credential_env, run_git


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()


def capture_run_baseline(settings: Settings, run: OpinionRun, run_dir: Path) -> Path:
    """Record the exact writable files and repository base for one run."""
    target_files = [settings.opinions_target_file, settings.opinions_sources_file]
    assert_targets_clean(settings.opinions_repo_dir, target_files)
    run.git_base_sha = run_git(settings.opinions_repo_dir, "rev-parse", "HEAD")
    run.git_phase = GitPhase.AGENT_EDITING.value
    recovery = run_dir / "recovery" / run.id
    baseline = recovery / "baseline"
    baseline.mkdir(parents=True, exist_ok=True)
    _copy_if_present(settings.opinions_target_path, baseline / "opinions.md")
    _copy_if_present(settings.opinions_sources_path, baseline / "sources.jsonl")
    corpus = CorpusPaths(settings.opinions_data_dir)
    _copy_if_present(corpus.decisions_jsonl, baseline / "decisions.jsonl")
    _copy_if_present(corpus.opinion_id_high_water, baseline / "opinion-id-high-water.json")
    run.decision_log_hash = file_hash(corpus.decisions_jsonl)
    return recovery


def archive_and_restore_run(settings: Settings, run: OpinionRun, run_dir: Path) -> Path:
    """Archive failed edits and restore only the configured writable artifacts."""
    recovery = run_dir / "recovery" / run.id
    failed = recovery / "failed"
    failed.mkdir(parents=True, exist_ok=True)
    diff = run_git(
        settings.opinions_repo_dir,
        "diff",
        "--",
        settings.opinions_target_file,
        settings.opinions_sources_file,
    )
    write_text_atomic(failed / "changes.patch", diff + ("\n" if diff else ""))
    _copy_if_present(settings.opinions_target_path, failed / "opinions.md")
    _copy_if_present(settings.opinions_sources_path, failed / "sources.jsonl")
    corpus = CorpusPaths(settings.opinions_data_dir)
    _copy_if_present(corpus.decisions_jsonl, failed / "decisions.jsonl")
    _restore(recovery / "baseline" / "opinions.md", settings.opinions_target_path)
    _restore(recovery / "baseline" / "sources.jsonl", settings.opinions_sources_path)
    _restore(recovery / "baseline" / "decisions.jsonl", corpus.decisions_jsonl)
    _restore(recovery / "baseline" / "opinion-id-high-water.json", corpus.opinion_id_high_water)
    return failed


def remote_contains_result(settings: Settings, run: OpinionRun) -> bool:
    if not run.git_result_sha:
        return False
    output = run_git(
        settings.opinions_repo_dir,
        "ls-remote",
        "origin",
        f"refs/heads/{settings.opinions_repo_branch}",
        env=git_credential_env(settings.opinions_git_token),
    )
    return bool(output and output.split()[0] == run.git_result_sha)


def reconcile_git_durability(settings: Settings, run: OpinionRun) -> bool:
    """Finish a known commit or push without running the agent again."""
    if run.git_phase == GitPhase.COMMIT_INTENT.value and not run.git_result_sha:
        latest = run_git(settings.opinions_repo_dir, "log", "-1", "--format=%H%x00%s")
        sha, _, message = latest.partition("\x00")
        if message == f"chore: complete opinion run {run.id}":
            run.git_result_sha = sha
            run.git_phase = GitPhase.COMMITTED.value
    if not run.git_result_sha:
        return False
    if remote_contains_result(settings, run):
        run.git_phase = GitPhase.PUSHED.value
        return True
    if run.git_phase != GitPhase.COMMITTED.value:
        return False
    head = run_git(settings.opinions_repo_dir, "rev-parse", "HEAD")
    if head != run.git_result_sha:
        return False
    run_git(
        settings.opinions_repo_dir,
        "push",
        "origin",
        f"{run.git_result_sha}:refs/heads/{settings.opinions_repo_branch}",
        env=git_credential_env(settings.opinions_git_token),
    )
    run.git_phase = GitPhase.PUSHED.value
    return remote_contains_result(settings, run)


def _copy_if_present(source: Path, target: Path) -> None:
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _restore(source: Path, target: Path) -> None:
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    elif target.exists():
        target.unlink()
