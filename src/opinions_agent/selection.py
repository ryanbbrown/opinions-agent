"""Deterministic current-window highlight selection and active run bundle export."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from opinions_agent.corpus import (
    CorpusPaths,
    DocumentRow,
    HighlightRow,
    document_by_id,
    read_documents,
    read_highlights,
)
from opinions_agent.fsio import write_jsonl_atomic, write_text_atomic
from opinions_agent.reader import iso_utc, iso_week, parse_iso, reader_summary_key


@dataclass(frozen=True)
class RunPaths:
    runs_dir: Path

    @property
    def active_dir(self) -> Path:
        return self.runs_dir / "active"

    @property
    def completed_dir(self) -> Path:
        return self.runs_dir / "completed"

    def active_run_dir(self, run_id: str) -> Path:
        return self.active_dir / run_id

    def completed_run_dir(self, run_id: str) -> Path:
        return self.completed_dir / run_id


@dataclass(frozen=True)
class RunBundle:
    run_dir: Path
    review_summary_md: Path
    selected_highlights_jsonl: Path
    selected_documents_jsonl: Path
    highlights: list[HighlightRow]
    documents: list[DocumentRow]


def select_window(highlights: list[HighlightRow], window_start: datetime, window_end: datetime) -> list[HighlightRow]:
    """Select highlights with window_start <= highlighted_at < window_end, oldest first."""
    selected: list[tuple[datetime, HighlightRow]] = []
    for highlight in highlights:
        highlighted_at = parse_iso(highlight.highlighted_at)
        if highlighted_at is None:
            continue
        if window_start <= highlighted_at < window_end:
            selected.append((highlighted_at, highlight))
    selected.sort(key=lambda item: (item[0], item[1].highlight_id))
    return [highlight for _, highlight in selected]


def select_run_highlights(
    paths: CorpusPaths,
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[HighlightRow], list[DocumentRow]]:
    documents_by_id = document_by_id(paths)
    all_highlights = read_highlights(paths)
    highlights = [
        highlight
        for highlight in select_window(all_highlights, window_start, window_end)
        if not _is_backfill_document(documents_by_id.get(highlight.document_id))
    ]
    documents_with_evidence = {highlight.document_id for highlight in all_highlights}
    highlights.extend(
        _select_document_summary_evidence(
            paths=paths,
            window_start=window_start,
            window_end=window_end,
            documents_with_evidence=documents_with_evidence,
        )
    )
    highlights.sort(
        key=lambda highlight: (
            _evidence_datetime(highlight) or datetime.min.replace(tzinfo=UTC),
            highlight.highlight_id,
        )
    )
    seen: dict[str, DocumentRow] = {}
    for highlight in highlights:
        document = documents_by_id.get(highlight.document_id)
        if document is not None:
            seen.setdefault(document.document_id, document)
    return highlights, list(seen.values())


def _is_backfill_document(document: DocumentRow | None) -> bool:
    return document is not None and any(tag in {"backfill", ".backfill"} for tag in document.tags)


def _select_document_summary_evidence(
    *,
    paths: CorpusPaths,
    window_start: datetime,
    window_end: datetime,
    documents_with_evidence: set[str],
) -> list[HighlightRow]:
    selected: list[tuple[datetime, HighlightRow]] = []
    for document in read_documents(paths):
        if document.document_id in documents_with_evidence:
            continue
        if _is_backfill_document(document):
            continue
        if not document.tags:
            continue
        summary = (document.summary or "").strip()
        if not summary:
            continue
        saved_at = parse_iso(document.saved_at)
        if saved_at is None or not (window_start <= saved_at < window_end):
            continue
        selected.append((saved_at, _document_summary_evidence(document, summary, saved_at)))
    selected.sort(key=lambda item: (item[0], item[1].highlight_id))
    return [row for _, row in selected]


def _document_summary_evidence(document: DocumentRow, summary: str, saved_at: datetime) -> HighlightRow:
    return HighlightRow(
        highlight_id=reader_summary_key(document.reader_id),
        evidence_kind="document_summary",
        document_id=document.document_id,
        reader_id=document.reader_id,
        document_title=document.title,
        document_author=document.author,
        document_summary=document.summary,
        source_url=document.source_url,
        text=summary,
        highlighted_at=iso_utc(saved_at),
        highlighted_date=saved_at.astimezone(UTC).date().isoformat(),
        highlighted_week=iso_week(saved_at),
        updated_at=document.updated_at,
        content_path=document.content_path,
    )


def _evidence_datetime(evidence: HighlightRow) -> datetime | None:
    return parse_iso(evidence.highlighted_at)


def write_run_bundle(
    *,
    run_id: str,
    run_paths: RunPaths,
    window_start: datetime,
    window_end: datetime,
    highlights: list[HighlightRow],
    documents: list[DocumentRow],
) -> RunBundle:
    run_dir = run_paths.active_run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    highlights_path = run_dir / "selected-highlights.jsonl"
    documents_path = run_dir / "selected-documents.jsonl"
    summary_path = review_dir / "summary.md"

    write_jsonl_atomic(highlights_path, [row.model_dump(mode="json") for row in highlights])
    write_jsonl_atomic(documents_path, [row.model_dump(mode="json") for row in documents])

    titles = sorted({highlight.document_title or "Untitled" for highlight in highlights})
    summary_count = sum(1 for highlight in highlights if highlight.evidence_kind == "document_summary")
    brief = "\n".join(
        [
            f"# Opinion run {run_id}",
            "",
            f"Window: {iso_utc(window_start)} to {iso_utc(window_end)}",
            f"Selected evidence: {len(highlights)}",
            f"Selected document summaries: {summary_count}",
            f"Selected documents: {len(documents)}",
            "",
            "Documents:",
            *[f"- {title}" for title in titles],
        ]
    )
    write_text_atomic(summary_path, brief)
    return RunBundle(
        run_dir=run_dir,
        review_summary_md=summary_path,
        selected_highlights_jsonl=highlights_path,
        selected_documents_jsonl=documents_path,
        highlights=highlights,
        documents=documents,
    )


def finalize_run_dir(run_paths: RunPaths, run_id: str, final_payload: dict) -> Path:
    """Move a terminal run out of active/ and persist its final payload."""
    from opinions_agent.fsio import write_json_atomic

    completed_dir = run_paths.completed_run_dir(run_id)
    completed_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(completed_dir / "final.json", final_payload)
    active_dir = run_paths.active_run_dir(run_id)
    if active_dir.exists():
        shutil.rmtree(active_dir)
    return completed_dir


def cleanup_completed_runs(run_paths: RunPaths, *, retention_days: int, now: datetime | None = None) -> int:
    """Delete completed run directories older than the retention window. Returns directories removed."""
    if not run_paths.completed_dir.exists():
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    removed = 0
    for run_dir in run_paths.completed_dir.iterdir():
        if not run_dir.is_dir():
            continue
        modified = datetime.fromtimestamp(run_dir.stat().st_mtime, tz=UTC)
        if modified < cutoff:
            shutil.rmtree(run_dir)
            removed += 1
    return removed
