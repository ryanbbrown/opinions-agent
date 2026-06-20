from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from conftest import seed_corpus

from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths
from opinions_agent.fsio import read_jsonl
from opinions_agent.sample_run import prepare_sample_settings, sample_run_id, week_window_for_label
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
