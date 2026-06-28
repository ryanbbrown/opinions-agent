from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from conftest import seed_corpus

from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths, DocumentRow, upsert_documents
from opinions_agent.fsio import read_jsonl
from opinions_agent.sample_run import (
    prepare_sample_session_settings,
    prepare_sample_settings,
    sample_run_id,
    sample_session_dir,
    sample_session_settings,
    week_window_for_label,
)
from opinions_agent.tools.git_ops import run_git


def test_week_label_selects_chronological_corpus_week(settings: Settings) -> None:
    seed_corpus(settings)

    start, end = week_window_for_label(CorpusPaths(settings.opinions_data_dir), "W02")

    assert start == datetime(2026, 6, 8, tzinfo=UTC)
    assert end == datetime(2026, 6, 15, tzinfo=UTC)


def test_prepare_sample_settings_copies_artifacts_inside_run_dir(settings: Settings, tmp_path: Path) -> None:
    seed_corpus(settings)
    opinions_file = tmp_path / "OPINIONS.md"
    opinions_file.write_text(
        """# OPINIONS

## Agentic Software

- Existing opinion.
  <!-- opinion-id: opinion-000001 -->
  <!-- sources: rw:h0 -->
""",
        encoding="utf-8",
    )
    run_id = sample_run_id("W01", now=datetime(2026, 6, 19, 12, 0, tzinfo=UTC))

    sample = prepare_sample_settings(settings=settings, run_id=run_id, opinions_file=opinions_file)

    run_dir = settings.runs_dir / "active" / "20260619T120000Z-W01"
    assert sample.opinions_repo_dir == run_dir / "opinions-repo"
    assert sample.opinions_data_dir == run_dir / "data"
    assert sample.local_trace_dir == run_dir / ".traces"
    assert sample.use_fake_telegram is True
    assert sample.opinions_target_path.read_text(encoding="utf-8") == opinions_file.read_text(encoding="utf-8")
    assert read_jsonl(sample.opinions_sources_path) == [
        {
            "added_at": "2026-06-02T10:00:00+00:00",
            "document_id": "reader:doc1",
            "document_title": "Example Article",
            "evidence_id": "rw:h0",
            "evidence_text": "Durable systems should preserve provenance (highlight 0).",
            "opinion_id": "opinion-000001",
            "source_url": "https://example.com/article",
        }
    ]
    assert run_git(sample.opinions_repo_dir, "status", "--porcelain") == ""
    assert run_git(sample.opinions_repo_dir, "remote", "get-url", "origin") == str(run_dir / "remote.git")

    opinions_file.write_text("changed outside sample\n", encoding="utf-8")
    assert sample.opinions_target_path.read_text(encoding="utf-8") != "changed outside sample\n"


def test_sample_session_settings_reuses_copied_artifacts(settings: Settings, tmp_path: Path) -> None:
    seed_corpus(settings)
    opinions_file = tmp_path / "OPINIONS.md"
    opinions_file.write_text(
        """# OPINIONS

## Agentic Software

- Existing opinion.
  <!-- opinion-id: opinion-000001 -->
  <!-- sources: rw:h0 -->
""",
        encoding="utf-8",
    )

    created = prepare_sample_session_settings(settings=settings, name="review", opinions_file=opinions_file)
    loaded = sample_session_settings(settings=settings, name="review")
    session_dir = sample_session_dir(settings, "review")

    assert created == loaded
    assert loaded.database_url == f"sqlite+pysqlite:///{session_dir / 'sample-session.db'}"
    assert loaded.runs_dir == session_dir / "runs"
    assert loaded.opinions_data_dir == session_dir / "data"
    assert loaded.opinions_repo_dir == session_dir / "opinions-repo"
    assert loaded.opinions_target_path.read_text(encoding="utf-8") == opinions_file.read_text(encoding="utf-8")
    assert read_jsonl(loaded.opinions_sources_path)[0]["evidence_id"] == "rw:h0"

    opinions_file.write_text("changed outside session\n", encoding="utf-8")
    assert loaded.opinions_target_path.read_text(encoding="utf-8") != "changed outside session\n"


def test_prepare_sample_settings_derives_sources_from_document_summary_ids(
    settings: Settings,
    tmp_path: Path,
) -> None:
    seed_corpus(settings)
    paths = CorpusPaths(settings.opinions_data_dir)
    upsert_documents(
        paths,
        [
            DocumentRow(
                document_id="reader:summary-doc",
                reader_id="summary-doc",
                title="Summary Only",
                source_url="https://example.com/summary",
                summary="A tagged document summary can support an opinion.",
                tags=["ai direction"],
                saved_at="2026-06-02T00:00:00+00:00",
            )
        ],
    )
    opinions_file = tmp_path / "OPINIONS.md"
    opinions_file.write_text(
        """# OPINIONS

## AI Leverage

- Summary-backed opinions still derive source rows.
  <!-- opinion-id: opinion-000003 -->
  <!-- sources: reader-summary:summary-doc -->
""",
        encoding="utf-8",
    )

    sample = prepare_sample_settings(settings=settings, run_id="sample-summary", opinions_file=opinions_file)

    source_row = read_jsonl(sample.opinions_sources_path)[0]
    assert source_row["evidence_id"] == "reader-summary:summary-doc"
    assert source_row["document_id"] == "reader:summary-doc"
    assert source_row["evidence_text"] == "A tagged document summary can support an opinion."
