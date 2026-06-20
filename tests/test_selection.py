from __future__ import annotations

from datetime import UTC, datetime

import pytest

from opinions_agent.corpus import (
    CorpusPaths,
    DocumentRow,
    HighlightRow,
    init_data_dirs,
    upsert_documents,
    upsert_highlights,
)
from opinions_agent.fsio import read_json, read_jsonl
from opinions_agent.selection import (
    RunPaths,
    cleanup_completed_runs,
    finalize_run_dir,
    select_run_highlights,
    select_window,
    write_run_bundle,
)

WINDOW_START = datetime(2026, 6, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 6, 12, tzinfo=UTC)


def make_highlight(highlight_id: str, highlighted_at: str | None, document_id: str = "reader:doc1") -> HighlightRow:
    return HighlightRow(
        highlight_id=highlight_id,
        document_id=document_id,
        reader_id=document_id.removeprefix("reader:"),
        document_title="Example Article",
        document_summary="Summary.",
        text=f"Text for {highlight_id}",
        highlighted_at=highlighted_at,
        content_path="documents/reader_doc1.md",
    )


@pytest.fixture
def paths(tmp_path) -> CorpusPaths:
    corpus = CorpusPaths(tmp_path / "data")
    init_data_dirs(corpus)
    return corpus


def test_select_window_bounds_are_start_inclusive_end_exclusive() -> None:
    rows = [
        make_highlight("rw:before", "2026-05-31T23:59:59+00:00"),
        make_highlight("rw:start", "2026-06-01T00:00:00+00:00"),
        make_highlight("rw:mid", "2026-06-05T10:00:00+00:00"),
        make_highlight("rw:end", "2026-06-12T00:00:00+00:00"),
        make_highlight("rw:undated", None),
    ]

    selected = select_window(rows, WINDOW_START, WINDOW_END)

    assert [row.highlight_id for row in selected] == ["rw:start", "rw:mid"]


def test_select_run_highlights_joins_unique_documents(paths: CorpusPaths) -> None:
    upsert_documents(
        paths,
        [
            DocumentRow(document_id="reader:doc1", reader_id="doc1", title="Example Article", summary="Summary."),
            DocumentRow(document_id="reader:doc2", reader_id="doc2", title="Other Doc"),
        ],
    )
    upsert_highlights(
        paths,
        [
            make_highlight("rw:h1", "2026-06-02T00:00:00+00:00"),
            make_highlight("rw:h2", "2026-06-03T00:00:00+00:00"),
            make_highlight("rw:h3", "2026-06-04T00:00:00+00:00", document_id="reader:doc2"),
        ],
    )

    highlights, documents = select_run_highlights(paths, WINDOW_START, WINDOW_END)

    assert [h.highlight_id for h in highlights] == ["rw:h1", "rw:h2", "rw:h3"]
    assert sorted(d.document_id for d in documents) == ["reader:doc1", "reader:doc2"]


def test_run_bundle_contains_only_current_run_files(tmp_path) -> None:
    run_paths = RunPaths(tmp_path / "runs")
    old_dir = run_paths.active_run_dir("old-run")
    old_dir.mkdir(parents=True)
    (old_dir / "review" / "summary.md").parent.mkdir(parents=True)
    (old_dir / "review" / "summary.md").write_text("old", encoding="utf-8")
    highlights = [make_highlight("rw:h1", "2026-06-02T00:00:00+00:00")]
    documents = [DocumentRow(document_id="reader:doc1", reader_id="doc1", title="Example Article", summary="Summary.")]

    bundle = write_run_bundle(
        run_id="run-1",
        run_paths=run_paths,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        highlights=highlights,
        documents=documents,
    )

    assert sorted(p.name for p in bundle.run_dir.iterdir()) == [
        "review",
        "selected-documents.jsonl",
        "selected-highlights.jsonl",
    ]
    assert sorted(p.name for p in (bundle.run_dir / "review").iterdir()) == ["summary.md"]
    selected = read_jsonl(bundle.selected_highlights_jsonl)
    assert selected[0]["document_summary"] == "Summary."
    assert selected[0]["content_path"] == "documents/reader_doc1.md"
    summary = bundle.review_summary_md.read_text(encoding="utf-8")
    assert "Selected highlights: 1" in summary
    assert "opinion-worthy" not in summary
    assert "old-run" not in summary
    assert "old" not in str(read_jsonl(bundle.selected_documents_jsonl))


def test_finalize_run_dir_moves_run_out_of_active(tmp_path) -> None:
    run_paths = RunPaths(tmp_path / "runs")
    run_dir = run_paths.active_run_dir("run-1")
    (run_dir / "review").mkdir(parents=True)
    (run_dir / "review" / "summary.md").write_text("brief", encoding="utf-8")

    completed = finalize_run_dir(run_paths, "run-1", {"status": "completed"})

    assert not run_dir.exists()
    assert read_json(completed / "final.json") == {"status": "completed"}


def test_cleanup_completed_runs_respects_retention(tmp_path) -> None:
    import os

    run_paths = RunPaths(tmp_path / "runs")
    old = run_paths.completed_run_dir("old")
    fresh = run_paths.completed_run_dir("fresh")
    old.mkdir(parents=True)
    fresh.mkdir(parents=True)
    stale_time = datetime(2026, 5, 1, tzinfo=UTC).timestamp()
    os.utime(old, (stale_time, stale_time))

    removed = cleanup_completed_runs(run_paths, retention_days=30, now=datetime(2026, 6, 12, tzinfo=UTC))

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()
