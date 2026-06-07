from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from opinions_agent.models import ReadwiseHighlight, ReadwiseSyncState, utcnow


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class ReadwiseClient:
    def __init__(self, token: str, *, base_url: str = "https://readwise.io/api/v2") -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")

    async def export(self, *, updated_after: str | None = None) -> list[dict[str, Any]]:
        if not self.token:
            raise ValueError("READWISE_TOKEN is required")
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params: dict[str, str] = {}
                if updated_after:
                    params["updatedAfter"] = updated_after
                if cursor:
                    params["pageCursor"] = cursor
                response = await client.get(
                    f"{self.base_url}/export/",
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


def _iter_highlights(export_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for document in export_results:
        for highlight in document.get("highlights", []):
            flattened.append({"document": document, "highlight": highlight})
    return flattened


def sync_export(session: Session, export_results: list[dict[str, Any]]) -> int:
    count = 0
    newest_updated_at: datetime | None = None
    for item in _iter_highlights(export_results):
        document = item["document"]
        highlight = item["highlight"]
        readwise_id = str(highlight["id"])
        existing = session.scalar(select(ReadwiseHighlight).where(ReadwiseHighlight.readwise_id == readwise_id))
        updated_at = parse_dt(highlight.get("updated"))
        highlighted_at = parse_dt(highlight.get("highlighted_at"))
        candidate = updated_at or highlighted_at
        if candidate is not None and (newest_updated_at is None or candidate > newest_updated_at):
            newest_updated_at = candidate
        values = {
            "document_id": str(document.get("user_book_id") or document.get("id") or ""),
            "document_title": document.get("title"),
            "document_author": document.get("author"),
            "text": highlight.get("text") or "",
            "highlighted_at": highlighted_at,
            "updated_at_external": updated_at,
            "raw": {"document": document, "highlight": highlight},
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            session.add(ReadwiseHighlight(readwise_id=readwise_id, **values))
            count += 1
    state = session.get(ReadwiseSyncState, 1) or ReadwiseSyncState(id=1)
    state.last_success_at = utcnow()
    if newest_updated_at is not None:
        state.updated_after = newest_updated_at.isoformat()
    state.page_cursor = None
    state.raw = {"documents": len(export_results)}
    session.merge(state)
    session.commit()
    return count


async def sync_readwise(session: Session, client: ReadwiseClient) -> int:
    state = session.get(ReadwiseSyncState, 1)
    results = await client.export(updated_after=state.updated_after if state else None)
    return sync_export(session, results)
