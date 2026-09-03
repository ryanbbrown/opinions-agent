from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opinions_agent.corpus import (
    CorpusPaths,
    DocumentRow,
    HighlightRow,
    init_data_dirs,
    upsert_documents,
    upsert_highlights,
)
from opinions_agent.evals.availability import load_evidence_availability
from opinions_agent.fsio import read_jsonl
from opinions_agent.sample_run import prepare_sample_settings
from opinions_agent.selection import apply_highlighted_at_overrides, select_run_highlights


def _seed_corpus(path: Path) -> CorpusPaths:
    corpus = CorpusPaths(path)
    init_data_dirs(corpus)
    upsert_documents(
        corpus,
        [DocumentRow(document_id="reader:doc", reader_id="doc", title="Example")],
    )
    upsert_highlights(
        corpus,
        [
            HighlightRow(
                highlight_id="rw:moved",
                document_id="reader:doc",
                reader_id="doc",
                document_title="Example",
                text="This evidence became available after its source timestamp.",
                highlighted_at="2026-04-05T12:00:00+00:00",
                highlighted_date="2026-04-05",
                highlighted_week="2026-W14",
            )
        ],
    )
    return corpus


def test_load_evidence_availability_expands_grouped_rows(tmp_path: Path) -> None:
    path = tmp_path / "availability.jsonl"
    path.write_text(
        json.dumps(
            {
                "evidence_ids": ["rw:first", "rw:second"],
                "available_at": "2026-05-08T16:06:48+00:00",
                "reason": "Reviewed together later",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    overrides = load_evidence_availability(path)

    assert overrides == {
        "rw:first": datetime(2026, 5, 8, 16, 6, 48, tzinfo=UTC),
        "rw:second": datetime(2026, 5, 8, 16, 6, 48, tzinfo=UTC),
    }


def test_load_evidence_availability_rejects_duplicate_evidence_ids(tmp_path: Path) -> None:
    path = tmp_path / "availability.jsonl"
    rows = [
        {"evidence_ids": ["rw:same"], "available_at": "2026-05-01T00:00:00Z", "reason": "First"},
        {"evidence_ids": ["rw:same"], "available_at": "2026-05-08T00:00:00Z", "reason": "Second"},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate evidence availability override: rw:same"):
        load_evidence_availability(path)


def test_availability_override_moves_only_the_disposable_eval_copy(tmp_path: Path, settings) -> None:
    source = _seed_corpus(settings.opinions_data_dir)
    opinions_file = tmp_path / "OPINIONS.md"
    opinions_file.write_text(
        """# OPINIONS

## Example

- The moved evidence supports this seed opinion.
  <!-- opinion-id: opinion-000001 -->
  <!-- sources: rw:moved -->
""",
        encoding="utf-8",
    )
    overrides = {"rw:moved": datetime(2026, 5, 8, 16, 6, 48, tzinfo=UTC)}
    sample_settings = prepare_sample_settings(
        settings=settings,
        run_id="availability-test",
        opinions_file=opinions_file,
        highlighted_at_overrides=overrides,
    )
    copied = CorpusPaths(sample_settings.opinions_data_dir)
    april_start = datetime(2026, 3, 30, tzinfo=UTC)
    april_end = datetime(2026, 4, 6, tzinfo=UTC)
    may_start = datetime(2026, 5, 4, tzinfo=UTC)
    may_end = datetime(2026, 5, 11, tzinfo=UTC)

    source_april, _ = select_run_highlights(source, april_start, april_end)
    copied_april, _ = select_run_highlights(copied, april_start, april_end)
    copied_may, _ = select_run_highlights(copied, may_start, may_end)
    copied_sources = read_jsonl(sample_settings.opinions_repo_dir / "OPINIONS_SOURCES.jsonl")
    assert [row.highlight_id for row in source_april] == ["rw:moved"]
    assert copied_april == []
    assert [row.highlight_id for row in copied_may] == ["rw:moved"]
    assert copied_may[0].highlighted_at == "2026-05-08T16:06:48+00:00"
    assert copied_sources[0]["added_at"] == "2026-05-08T16:06:48+00:00"


def test_highlighted_at_overrides_reject_unknown_evidence() -> None:
    highlight = HighlightRow(
        highlight_id="rw:present",
        document_id="reader:doc",
        reader_id="doc",
        text="Present evidence.",
        highlighted_at="2026-04-05T12:00:00+00:00",
    )

    with pytest.raises(ValueError, match="highlight timestamp overrides not found in corpus: \\['rw:missing'\\]"):
        apply_highlighted_at_overrides(
            [highlight],
            {"rw:missing": datetime(2026, 5, 8, tzinfo=UTC)},
        )
