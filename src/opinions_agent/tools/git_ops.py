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


def assert_target_clean(repo_dir: Path, target_file: str) -> None:
    status = run_git(repo_dir, "status", "--porcelain", "--", target_file)
    if status:
        raise GitToolError(f"target file is already dirty: {target_file}")


def commit_and_push_opinions_file(
    *,
    repo_dir: Path,
    target_file: str,
    branch: str,
    author_name: str,
    author_email: str,
    message: str = "chore: append readwise summary",
    push: bool = True,
) -> GitCommitResult:
    if not author_name or not author_email:
        raise GitToolError("git author name/email are required")
    assert_relative_target(repo_dir, target_file)
    if push:
        run_git(repo_dir, "fetch", "origin", branch)
    unstaged_status = run_git(repo_dir, "status", "--porcelain", "--", target_file)
    if not unstaged_status:
        return GitCommitResult(changed=False, commit_sha=None)
    run_git(repo_dir, "add", "--", target_file)
    staged_files = run_git(repo_dir, "diff", "--cached", "--name-only", "--", target_file)
    staged = [line.strip() for line in staged_files.splitlines() if line.strip()]
    if staged != [target_file]:
        run_git(repo_dir, "reset", "--", target_file)
        raise GitToolError(f"refusing to commit files other than {target_file}: {staged}")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
    }
    run_git(repo_dir, "commit", "-m", message, "--", target_file, env=env)
    sha = run_git(repo_dir, "rev-parse", "HEAD")
    if push:
        run_git(repo_dir, "push", "origin", branch)
    return GitCommitResult(changed=True, commit_sha=sha)
