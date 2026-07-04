"""Deterministic end-to-end: sync fixture -> select -> converse -> agent edit -> validate -> commit."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from test_reader_sync import FakeReaderClient, doc_row, highlight_row, note_row

from opinions_agent.agent import DeterministicOpinionAgent
from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths, load_state
from opinions_agent.fsio import read_jsonl
from opinions_agent.models import RunStatus, TelegramInteraction
from opinions_agent.reader import sync_reader
from opinions_agent.selection import RunPaths
from opinions_agent.telegram import FakeTelegramClient
from opinions_agent.tools.git_ops import run_git
from opinions_agent.workflow import handle_telegram_update, start_opinion_run


async def test_full_deterministic_e2e(session, settings: Settings, opinions_repo: Path) -> None:
    paths = CorpusPaths(settings.opinions_data_dir)
    client = FakeReaderClient(
        [
            [
                doc_row(),
                highlight_row("hl1", created_at="2026-06-05T10:00:00Z"),
                highlight_row("hl2", created_at="2026-06-06T10:00:00Z", content="Second highlight."),
                note_row(parent_id="hl1"),
            ]
        ]
    )
    sync_result = await sync_reader(client, paths)
    assert sync_result.new_highlights == 2

    telegram = FakeTelegramClient()
    run = await start_opinion_run(
        session=session,
        settings=settings,
        agent=DeterministicOpinionAgent(),
        telegram=telegram,
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 12, tzinfo=UTC),
    )
    assert run is not None
    assert run.status == RunStatus.AWAITING_USER.value
    outbound = session.scalar(
        select(TelegramInteraction).where(
            TelegramInteraction.direction == "outbound",
            TelegramInteraction.opinion_run_id == run.id,
        )
    )
    assert outbound is not None

    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=DeterministicOpinionAgent(),
        telegram=telegram,
        update={
            "update_id": 1000,
            "callback_query": {
                "id": "cb-e2e",
                "data": "approve:add-deterministic-opinion",
                "message": {"message_id": outbound.message_id, "chat": {"id": settings.telegram_allowed_chat_id}},
            },
        },
    )
    assert result == "resumed"

    assert run.status == RunStatus.COMPLETED.value
    opinions_text = (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8")
    assert "<!-- opinion-id: opinion-000003 -->" in opinions_text
    assert "Deterministic opinion." in opinions_text

    sources = read_jsonl(opinions_repo / "OPINIONS_SOURCES.jsonl")
    assert "opinion-000003" in {row["opinion_id"] for row in sources}
    assert "rw:hl1" in {row["evidence_id"] for row in sources}

    decisions = read_jsonl(paths.decisions_jsonl)
    assert decisions[-1]["decision"] == "approved"

    state = load_state(paths)
    assert state.workflow.last_completed_window_end == "2026-06-12T00:00:00+00:00"

    files = set(run_git(opinions_repo, "diff", "--name-only", "HEAD~1", "HEAD").splitlines())
    assert files == {"OPINIONS.md", "OPINIONS_SOURCES.jsonl"}
    assert run_git(opinions_repo, "status", "--porcelain", "--", "OPINIONS.md", "OPINIONS_SOURCES.jsonl") == ""

    run_paths = RunPaths(settings.runs_dir)
    assert not run_paths.active_run_dir(run.id).exists()
    assert (run_paths.completed_run_dir(run.id) / "final.json").exists()
