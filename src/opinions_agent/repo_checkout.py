from __future__ import annotations

from pathlib import Path

from opinions_agent.config import Settings
from opinions_agent.tools.git_ops import assert_relative_target, run_git


def ensure_opinions_repo(settings: Settings) -> None:
    repo_dir = settings.opinions_repo_dir
    if (repo_dir / ".git").exists():
        run_git(repo_dir, "fetch", "origin", settings.opinions_repo_branch)
        run_git(repo_dir, "checkout", settings.opinions_repo_branch)
        run_git(repo_dir, "pull", "--ff-only", "origin", settings.opinions_repo_branch)
        return
    if not settings.opinions_repo_url:
        raise ValueError("OPINIONS_REPO_URL is required when OPINIONS_REPO_DIR is not already a git checkout")
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    import subprocess

    result = subprocess.run(
        ["git", "clone", "--branch", settings.opinions_repo_branch, settings.opinions_repo_url, str(repo_dir)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())


def resolve_target_path(settings: Settings) -> Path:
    return assert_relative_target(settings.opinions_repo_dir, settings.opinions_target_file)


def ensure_target_file(settings: Settings) -> Path:
    target = resolve_target_path(settings)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=True)
    return target
