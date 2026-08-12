"""Narrow artifact recovery and git-phase reconciliation for opinion runs."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths
from opinions_agent.fsio import read_json, write_json_atomic, write_text_atomic
from opinions_agent.models import GitPhase, OpinionRun
from opinions_agent.tools.git_ops import assert_targets_clean, git_credential_env, run_git


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()


def capture_run_baseline(settings: Settings, run: OpinionRun, run_dir: Path) -> Path:
    """Record the exact writable files and repository base for one run."""
    target_files = [settings.opinions_target_file, settings.opinions_sources_file]
    assert_targets_clean(settings.opinions_repo_dir, target_files)
    run.git_base_sha = run_git(settings.opinions_repo_dir, "rev-parse", "HEAD")
    remote = run_git(settings.opinions_repo_dir, "rev-parse", f"origin/{settings.opinions_repo_branch}")
    if run.git_base_sha != remote:
        raise RuntimeError("opinions checkout does not match the fetched remote branch")
    run.git_phase = GitPhase.AGENT_EDITING.value
    recovery = run_dir / "recovery" / run.id
    baseline = recovery / "baseline"
    if baseline.exists():
        shutil.rmtree(baseline)
    baseline.mkdir(parents=True, exist_ok=True)
    corpus = CorpusPaths(settings.opinions_data_dir)
    sources = {
        "opinions.md": settings.opinions_target_path,
        "sources.jsonl": settings.opinions_sources_path,
        "decisions.jsonl": corpus.decisions_jsonl,
        "opinion-id-high-water.json": corpus.opinion_id_high_water,
    }
    files: dict[str, dict[str, str | bool]] = {}
    for name, source in sources.items():
        target = baseline / name
        _copy_if_present(source, target)
        files[name] = {"present": source.exists(), "sha256": file_hash(target) if target.exists() else ""}
    write_json_atomic(baseline / "manifest.json", {"run_id": run.id, "files": files})
    run.decision_log_hash = file_hash(corpus.decisions_jsonl)
    run.baseline_complete = True
    return recovery


def require_complete_baseline(run: OpinionRun, run_dir: Path) -> dict[str, dict[str, str | bool]]:
    """Return a verified baseline manifest or fail without changing writable files."""
    if not run.baseline_complete:
        raise RuntimeError("run baseline is incomplete")
    baseline = run_dir / "recovery" / run.id / "baseline"
    marker = read_json(baseline / "manifest.json")
    files = (marker or {}).get("files")
    if (marker or {}).get("run_id") != run.id or not isinstance(files, dict):
        raise RuntimeError("run baseline marker is incomplete")
    expected = {"opinions.md", "sources.jsonl", "decisions.jsonl", "opinion-id-high-water.json"}
    if set(files) != expected:
        raise RuntimeError("run baseline marker is incomplete")
    for name, record in files.items():
        path = baseline / name
        present = record.get("present") is True
        if present != path.is_file() or (present and record.get("sha256") != file_hash(path)):
            raise RuntimeError("run baseline files are incomplete")
    return files


def archive_and_restore_run(settings: Settings, run: OpinionRun, run_dir: Path) -> Path:
    """Archive failed edits and restore only the configured writable artifacts."""
    recovery = run_dir / "recovery" / run.id
    baseline_files = require_complete_baseline(run, run_dir)
    failed = recovery / "failed"
    failed.mkdir(parents=True, exist_ok=True)
    diff = run_git(
        settings.opinions_repo_dir,
        "diff",
        "HEAD",
        "--",
        settings.opinions_target_file,
        settings.opinions_sources_file,
    )
    write_text_atomic(failed / "changes.patch", diff + ("\n" if diff else ""))
    _copy_if_present(settings.opinions_target_path, failed / "opinions.md")
    _copy_if_present(settings.opinions_sources_path, failed / "sources.jsonl")
    corpus = CorpusPaths(settings.opinions_data_dir)
    _copy_if_present(corpus.decisions_jsonl, failed / "decisions.jsonl")
    run_git(
        settings.opinions_repo_dir,
        "reset",
        "--",
        settings.opinions_target_file,
        settings.opinions_sources_file,
    )
    _restore(recovery / "baseline" / "opinions.md", settings.opinions_target_path, baseline_files["opinions.md"])
    _restore(recovery / "baseline" / "sources.jsonl", settings.opinions_sources_path, baseline_files["sources.jsonl"])
    _restore(recovery / "baseline" / "decisions.jsonl", corpus.decisions_jsonl, baseline_files["decisions.jsonl"])
    _restore(
        recovery / "baseline" / "opinion-id-high-water.json",
        corpus.opinion_id_high_water,
        baseline_files["opinion-id-high-water.json"],
    )
    return failed


def remote_contains_result(settings: Settings, run: OpinionRun) -> bool:
    if not run.git_result_sha:
        return False
    run_git(
        settings.opinions_repo_dir,
        "fetch",
        "origin",
        settings.opinions_repo_branch,
        env=git_credential_env(settings.opinions_git_token),
    )
    import subprocess

    result = subprocess.run(
        [
            "git",
            "-C",
            str(settings.opinions_repo_dir),
            "merge-base",
            "--is-ancestor",
            run.git_result_sha,
            f"origin/{settings.opinions_repo_branch}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def reconcile_git_durability(settings: Settings, run: OpinionRun) -> bool:
    """Finish a known commit or push without running the agent again."""
    if run.git_phase == GitPhase.PUSHED.value and not run.git_result_sha:
        return True
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


def _restore(source: Path, target: Path, record: dict[str, str | bool]) -> None:
    if record["present"] is True:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    elif target.exists():
        target.unlink()
