from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from opinions_agent.config import Settings
from opinions_agent.db import init_db, make_engine, make_sessionmaker


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    SessionLocal = make_sessionmaker(engine)
    with SessionLocal() as session:
        yield session


@pytest.fixture
def settings(tmp_path) -> Settings:
    repo_dir = tmp_path / "opinions"
    return Settings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        telegram_bot_token="fake-token",
        telegram_allowed_chat_id=12345,
        telegram_webhook_secret="secret",
        readwise_token="fake-readwise",
        harness_model="openai:gpt-5.2",
        langfuse_public_key="",
        langfuse_secret_key="",
        langfuse_base_url="https://us.cloud.langfuse.com",
        opinions_repo_url="",
        opinions_repo_branch="main",
        opinions_repo_dir=repo_dir,
        opinions_target_file="TEST_OPINIONS.md",
        opinions_git_author_name="opinions-agent",
        opinions_git_author_email="opinions-agent@example.com",
        runs_dir=tmp_path / ".runs",
        local_trace_dir=tmp_path / ".traces",
        local_tracing_enabled=True,
        use_fake_telegram=True,
    )


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


@pytest.fixture
def opinions_repo(tmp_path, settings: Settings) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
    repo = settings.opinions_repo_dir
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, stdout=subprocess.PIPE)
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "TEST_OPINIONS.md").write_text("", encoding="utf-8")
    (repo / "UNRELATED.md").write_text("leave me alone\n", encoding="utf-8")
    git(repo, "add", "TEST_OPINIONS.md", "UNRELATED.md")
    git(repo, "commit", "-m", "chore: initial")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-u", "origin", "main")
    return repo
