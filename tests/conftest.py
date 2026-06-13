from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from opinions_agent.config import Settings
from opinions_agent.corpus import (
    CorpusPaths,
    DocumentRow,
    HighlightRow,
    init_data_dirs,
    upsert_documents,
    upsert_highlights,
)
from opinions_agent.db import init_db, make_engine, make_sessionmaker

SEED_OPINIONS_MD = """# OPINIONS

<!-- opinion-id: opinion-000001 -->
## 1. Small tools should make their state legible

A tool that hides its state makes users debug vibes instead of systems.

<!-- opinion-id: opinion-000002 -->
## 2. Stale opinion that may be removed

This belief is old and weakly supported.
"""


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
        opinions_target_file="OPINIONS.md",
        opinions_sources_file="OPINIONS_SOURCES.jsonl",
        opinions_git_author_name="opinions-agent",
        opinions_git_author_email="opinions-agent@example.com",
        opinions_data_dir=tmp_path / "data",
        runs_dir=tmp_path / ".runs",
        completed_run_retention_days=30,
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
    (repo / "OPINIONS.md").write_text(SEED_OPINIONS_MD, encoding="utf-8")
    seed_source = {
        "opinion_id": "opinion-000001",
        "highlight_id": "rw:seed",
        "document_id": "reader:seed",
        "document_title": "Seed Doc",
        "source_url": "https://example.com/seed",
        "highlight_text": "Seed highlight.",
        "added_at": "2026-05-01T00:00:00+00:00",
    }
    (repo / "OPINIONS_SOURCES.jsonl").write_text(json.dumps(seed_source) + "\n", encoding="utf-8")
    (repo / "UNRELATED.md").write_text("leave me alone\n", encoding="utf-8")
    git(repo, "add", "OPINIONS.md", "OPINIONS_SOURCES.jsonl", "UNRELATED.md")
    git(repo, "commit", "-m", "chore: initial")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-u", "origin", "main")
    return repo


def seed_corpus(settings: Settings, *, highlight_count: int = 2) -> CorpusPaths:
    """Seed the filesystem corpus with one document and dated highlights inside 2026-06-01..12."""
    paths = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(paths)
    upsert_documents(
        paths,
        [
            DocumentRow(
                document_id="reader:doc1",
                reader_id="doc1",
                title="Example Article",
                author="Jane Doe",
                source_url="https://example.com/article",
                summary="Reader generated summary.",
                content_path="documents/reader_doc1.md",
            )
        ],
    )
    upsert_highlights(
        paths,
        [
            HighlightRow(
                highlight_id=f"rw:h{index}",
                document_id="reader:doc1",
                reader_id="doc1",
                document_title="Example Article",
                document_author="Jane Doe",
                document_summary="Reader generated summary.",
                source_url="https://example.com/article",
                text=f"Durable systems should preserve provenance (highlight {index}).",
                highlighted_at=f"2026-06-{2 + index:02d}T10:00:00+00:00",
                highlighted_date=f"2026-06-{2 + index:02d}",
                highlighted_week="2026-W23",
                content_path="documents/reader_doc1.md",
            )
            for index in range(highlight_count)
        ],
    )
    return paths
