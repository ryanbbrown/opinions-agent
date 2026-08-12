from __future__ import annotations

from pathlib import Path

from opinions_agent.config import Settings
from opinions_agent.tools.git_ops import assert_relative_target, git_credential_env, redact_git_error, run_git


def ensure_opinions_repo(settings: Settings, *, refresh: bool = True) -> None:
    repo_dir = settings.opinions_repo_dir
    credential_env = git_credential_env(settings.opinions_git_token)
    if (repo_dir / ".git").exists():
        if not refresh:
            return
        run_git(repo_dir, "fetch", "origin", settings.opinions_repo_branch, env=credential_env)
        run_git(repo_dir, "checkout", settings.opinions_repo_branch)
        run_git(repo_dir, "pull", "--ff-only", "origin", settings.opinions_repo_branch, env=credential_env)
        local = run_git(repo_dir, "rev-parse", "HEAD")
        remote = run_git(repo_dir, "rev-parse", f"origin/{settings.opinions_repo_branch}")
        if local != remote:
            raise RuntimeError("opinions checkout does not match the fetched remote branch")
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
        env=credential_env,
    )
    if result.returncode != 0:
        raise RuntimeError(redact_git_error((result.stderr or result.stdout).strip(), settings.opinions_git_token))


def resolve_repo_file(settings: Settings, repo_file: str) -> Path:
    return assert_relative_target(settings.opinions_repo_dir, repo_file)


def ensure_repo_file(settings: Settings, repo_file: str) -> Path:
    target = resolve_repo_file(settings, repo_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=True)
    return target
