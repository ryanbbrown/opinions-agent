"""Readwise Reader v3 sync into the durable filesystem corpus.

V1 uses the Reader v3 list API as the single source of truth: parent documents carry
summaries and full content, `category=highlight` rows join to their document through
`parent_id`, and `category=note` rows attach note text to their highlight.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from opinions_agent.corpus import (
    CorpusPaths,
    DocumentRow,
    HighlightRow,
    document_by_id,
    init_data_dirs,
    load_state,
    read_highlights,
    save_state,
    upsert_documents,
    upsert_highlights,
    write_raw_payload,
)
from opinions_agent.fsio import write_text_atomic
from opinions_agent.html_to_markdown import html_to_markdown

HIGHLIGHT_CATEGORIES = {"highlight"}
NOTE_CATEGORIES = {"note"}


def document_key(reader_id: str) -> str:
    return f"reader:{reader_id}"


def highlight_key(reader_id: str) -> str:
    return f"rw:{reader_id}"


def reader_note_key(reader_id: str) -> str:
    return f"reader-note:{reader_id}"


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def iso_week(value: datetime) -> str:
    calendar = value.astimezone(UTC).isocalendar()
    return f"{calendar.year}-W{calendar.week:02d}"


class ReaderClient:
    def __init__(self, token: str, *, base_url: str = "https://readwise.io/api/v3") -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")

    async def list_documents(self, *, updated_after: str | None = None) -> list[dict[str, Any]]:
        if not self.token:
            raise ValueError("READWISE_TOKEN is required")
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                params: dict[str, str] = {"withHtmlContent": "true"}
                if updated_after:
                    params["updatedAfter"] = updated_after
                if cursor:
                    params["pageCursor"] = cursor
                response = await client.get(
                    f"{self.base_url}/list/",
                    headers={"Authorization": f"Token {self.token}"},
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                results.extend(data.get("results", []))
                cursor = data.get("nextPageCursor")
                if not cursor:
                    break
        return results


def _tags(row: dict[str, Any]) -> list[str]:
    tags = row.get("tags")
    if isinstance(tags, dict):
        return sorted(tags)
    if isinstance(tags, list):
        return sorted(str(tag) for tag in tags)
    return []


def _document_row(row: dict[str, Any], paths: CorpusPaths) -> DocumentRow:
    reader_id = str(row["id"])
    return DocumentRow(
        document_id=document_key(reader_id),
        reader_id=reader_id,
        title=row.get("title"),
        author=row.get("author"),
        source_url=row.get("source_url") or row.get("url"),
        summary=row.get("summary"),
        tags=_tags(row),
        saved_at=row.get("saved_at") or row.get("created_at"),
        updated_at=row.get("updated_at"),
        content_path=str(paths.document_md(reader_id).relative_to(paths.data_dir)),
        raw_path=str(paths.raw_json(reader_id).relative_to(paths.data_dir)),
    )


def _highlight_row(
    row: dict[str, Any],
    parent: DocumentRow | None,
    note: str | None,
) -> HighlightRow:
    reader_id = str(row["id"])
    parent_reader_id = str(row.get("parent_id") or "")
    highlighted_at = parse_iso(row.get("created_at") or row.get("saved_at"))
    return HighlightRow(
        highlight_id=highlight_key(reader_id),
        document_id=parent.document_id if parent else document_key(parent_reader_id),
        reader_id=parent_reader_id,
        document_title=parent.title if parent else None,
        document_author=parent.author if parent else None,
        document_summary=parent.summary if parent else None,
        source_url=parent.source_url if parent else None,
        text=row.get("content") or "",
        note=note,
        color=row.get("color"),
        highlighted_at=iso_utc(highlighted_at) if highlighted_at else None,
        highlighted_date=highlighted_at.astimezone(UTC).date().isoformat() if highlighted_at else None,
        highlighted_week=iso_week(highlighted_at) if highlighted_at else None,
        updated_at=row.get("updated_at"),
        content_path=parent.content_path if parent else None,
    )


def _document_note_row(row: dict[str, Any], parent: DocumentRow | None) -> HighlightRow:
    reader_id = str(row["id"])
    parent_reader_id = str(row.get("parent_id") or "")
    highlighted_at = parse_iso(row.get("created_at") or row.get("saved_at"))
    return HighlightRow(
        highlight_id=reader_note_key(reader_id),
        document_id=parent.document_id if parent else document_key(parent_reader_id),
        reader_id=reader_id,
        document_title=parent.title if parent else None,
        document_author=parent.author if parent else None,
        document_summary=parent.summary if parent else None,
        source_url=parent.source_url if parent else None,
        text=row.get("content") or "",
        highlighted_at=iso_utc(highlighted_at) if highlighted_at else None,
        highlighted_date=highlighted_at.astimezone(UTC).date().isoformat() if highlighted_at else None,
        highlighted_week=iso_week(highlighted_at) if highlighted_at else None,
        updated_at=row.get("updated_at"),
        content_path=parent.content_path if parent else None,
    )


@dataclass(frozen=True)
class NormalizedExport:
    documents: list[DocumentRow]
    highlights: list[HighlightRow]


def normalize_rows(rows: list[dict[str, Any]], paths: CorpusPaths) -> NormalizedExport:
    """Normalize a Reader v3 batch against the existing corpus.

    Highlights and notes can arrive without their parent in the same batch, so parent
    lookups fall back to documents.jsonl and existing highlight rows.
    """
    skip_categories = HIGHLIGHT_CATEGORIES | NOTE_CATEGORIES
    skipped_document_reader_ids = {
        str(row["id"])
        for row in rows
        if _category(row) not in skip_categories and any(tag in {"backfill", ".backfill"} for tag in _tags(row))
    }
    document_rows = [
        _document_row(row, paths)
        for row in rows
        if _category(row) not in skip_categories and str(row["id"]) not in skipped_document_reader_ids
    ]
    documents = {doc.document_id: doc for doc in document_rows}
    existing_documents = document_by_id(paths)
    existing_highlights = {row.highlight_id: row for row in read_highlights(paths)}
    highlight_reader_ids = {str(row["id"]) for row in rows if _category(row) in HIGHLIGHT_CATEGORIES}

    notes_by_highlight: dict[str, str] = {}
    document_note_rows: dict[str, HighlightRow] = {}
    for row in rows:
        if _category(row) not in NOTE_CATEGORIES or not row.get("parent_id"):
            continue
        if not (row.get("content") or "").strip():
            continue
        parent_reader_id = str(row["parent_id"])
        if parent_reader_id in skipped_document_reader_ids:
            continue
        parent_highlight_id = highlight_key(parent_reader_id)
        if parent_reader_id in highlight_reader_ids or parent_highlight_id in existing_highlights:
            notes_by_highlight[parent_highlight_id] = row.get("content") or ""
            continue
        parent_key = document_key(parent_reader_id)
        parent = documents.get(parent_key) or existing_documents.get(parent_key)
        if parent is not None and "backfill" not in parent.tags and ".backfill" not in parent.tags:
            document_note_rows[reader_note_key(str(row["id"]))] = _document_note_row(row, parent)

    highlight_rows: dict[str, HighlightRow] = {}
    for row in rows:
        if _category(row) not in HIGHLIGHT_CATEGORIES:
            continue
        if str(row.get("parent_id") or "") in skipped_document_reader_ids:
            continue
        parent_key = document_key(str(row.get("parent_id") or ""))
        parent = documents.get(parent_key) or existing_documents.get(parent_key)
        if parent is not None and ("backfill" in parent.tags or ".backfill" in parent.tags):
            continue
        note = notes_by_highlight.get(highlight_key(str(row["id"])))
        if note is None:
            previous = existing_highlights.get(highlight_key(str(row["id"])))
            note = previous.note if previous else None
        highlight_rows[highlight_key(str(row["id"]))] = _highlight_row(row, parent, note)

    # Attach notes whose highlight is not in this batch to the existing highlight row.
    for highlight_id, note in notes_by_highlight.items():
        if highlight_id not in highlight_rows and highlight_id in existing_highlights:
            highlight_rows[highlight_id] = existing_highlights[highlight_id].model_copy(update={"note": note})

    # Refresh denormalized document fields on existing highlights of re-synced documents.
    for existing in existing_highlights.values():
        if existing.highlight_id in highlight_rows:
            continue
        doc = documents.get(existing.document_id)
        if doc is not None:
            highlight_rows[existing.highlight_id] = existing.model_copy(
                update={
                    "document_title": doc.title,
                    "document_author": doc.author,
                    "document_summary": doc.summary,
                    "source_url": doc.source_url,
                    "content_path": doc.content_path,
                }
            )

    highlight_rows.update(document_note_rows)
    return NormalizedExport(documents=document_rows, highlights=list(highlight_rows.values()))


def _category(row: dict[str, Any]) -> str:
    return str(row.get("category") or "").lower()


def _document_markdown(row: dict[str, Any], doc: DocumentRow) -> str:
    html = row.get("html_content") or ""
    body = html_to_markdown(html) if html else (row.get("content") or "")
    header = [f"# {doc.title or 'Untitled'}", ""]
    if doc.author:
        header.append(f"Author: {doc.author}")
    if doc.source_url:
        header.append(f"Source: {doc.source_url}")
    if doc.summary:
        header.extend(["", f"Summary: {doc.summary}"])
    return "\n".join(header) + "\n\n" + (body or "(no content)\n")


@dataclass(frozen=True)
class SyncResult:
    fetched_rows: int
    new_documents: int
    new_highlights: int


async def sync_reader(client: ReaderClient, paths: CorpusPaths, *, now: datetime | None = None) -> SyncResult:
    """Run the sync workflow; state.json is advanced only after all corpus writes succeed."""
    init_data_dirs(paths)
    state = load_state(paths)
    rows = await client.list_documents(updated_after=state.sync.reader_updated_after)
    normalized = normalize_rows(rows, paths)

    new_documents = upsert_documents(paths, normalized.documents)
    new_highlights = upsert_highlights(paths, normalized.highlights)

    docs_by_id = {doc.document_id: doc for doc in normalized.documents}
    for row in rows:
        reader_id = str(row["id"])
        write_raw_payload(paths, reader_id, row)
        doc = docs_by_id.get(document_key(reader_id))
        if doc is not None:
            write_text_atomic(paths.document_md(reader_id), _document_markdown(row, doc))

    newest = max(
        (parsed for row in rows if (parsed := parse_iso(row.get("updated_at"))) is not None),
        default=None,
    )
    if newest is not None:
        state.sync.reader_updated_after = iso_utc(newest)
    state.sync.last_success_at = iso_utc(now or datetime.now(UTC))
    save_state(paths, state)
    return SyncResult(fetched_rows=len(rows), new_documents=new_documents, new_highlights=new_highlights)
