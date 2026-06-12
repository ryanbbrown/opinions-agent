"""Constrained tools exposed by the host app."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitCommitResult:
    changed: bool
    commit_sha: str | None


def run_git(repo_dir: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise GitToolError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def assert_relative_target(repo_dir: Path, target_file: str) -> Path:
    target = (repo_dir / target_file).resolve()
    repo = repo_dir.resolve()
    if target != repo and repo not in target.parents:
        raise GitToolError("target file escapes OPINIONS_REPO_DIR")
    return target


def assert_targets_clean(repo_dir: Path, target_files: list[str]) -> None:
    status = run_git(repo_dir, "status", "--porcelain", "--", *target_files)
    if status:
        raise GitToolError(f"target files are already dirty: {status}")


def commit_and_push_opinions_files(
    *,
    repo_dir: Path,
    target_files: list[str],
    branch: str,
    author_name: str,
    author_email: str,
    message: str,
    push: bool = True,
) -> GitCommitResult:
    if not author_name or not author_email:
        raise GitToolError("git author name/email are required")
    if not target_files:
        raise GitToolError("at least one target file is required")
    for target_file in target_files:
        assert_relative_target(repo_dir, target_file)
    if push:
        run_git(repo_dir, "fetch", "origin", branch)
    unstaged_status = run_git(repo_dir, "status", "--porcelain", "--", *target_files)
    if not unstaged_status:
        return GitCommitResult(changed=False, commit_sha=None)
    run_git(repo_dir, "add", "--", *target_files)
    staged_files = run_git(repo_dir, "diff", "--cached", "--name-only", "--", *target_files)
    staged = [line.strip() for line in staged_files.splitlines() if line.strip()]
    if not staged or any(staged_file not in target_files for staged_file in staged):
        run_git(repo_dir, "reset", "--", *target_files)
        raise GitToolError(f"refusing to commit files other than {target_files}: {staged}")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
    }
    run_git(repo_dir, "commit", "-m", message, "--", *target_files, env=env)
    sha = run_git(repo_dir, "rev-parse", "HEAD")
    if push:
        run_git(repo_dir, "push", "origin", branch)
    return GitCommitResult(changed=True, commit_sha=sha)
