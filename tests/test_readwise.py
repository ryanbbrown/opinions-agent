from __future__ import annotations

from sqlalchemy import select

from opinions_agent.models import ReadwiseHighlight, ReadwiseSyncState
from opinions_agent.readwise import sync_export


def export_payload(text: str = "A useful highlight") -> list[dict]:
    return [
        {
            "user_book_id": 10,
            "title": "Domain Notes",
            "author": "A. Reader",
            "highlights": [
                {
                    "id": 999,
                    "text": text,
                    "highlighted_at": "2026-06-01T00:00:00Z",
                    "updated": "2026-06-02T03:04:05Z",
                }
            ],
        }
    ]


def test_readwise_sync_is_idempotent(session) -> None:
    assert sync_export(session, export_payload()) == 1
    assert sync_export(session, export_payload("Updated text")) == 0

    rows = list(session.scalars(select(ReadwiseHighlight)))
    assert len(rows) == 1
    assert rows[0].text == "Updated text"
    state = session.get(ReadwiseSyncState, 1)
    assert state.updated_after == "2026-06-02T03:04:05+00:00"
