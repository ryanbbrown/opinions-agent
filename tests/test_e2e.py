"""Deterministic end-to-end: sync fixture -> select -> propose -> approve -> apply -> commit."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from test_reader_sync import FakeReaderClient, doc_row, highlight_row, note_row

from opinions_agent.agent import DeterministicOpinionAgent
from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths, load_state, read_decisions
from opinions_agent.fsio import read_jsonl
from opinions_agent.models import OpinionProposal, ProposalStatus, RunStatus
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
    proposals = list(session.scalars(select(OpinionProposal).where(OpinionProposal.opinion_run_id == run.id)))
    assert sorted(p.kind for p in proposals) == ["add_opinion", "add_sources", "remove_opinion", "update_opinion"]

    for index, proposal in enumerate(proposals):
        result = await handle_telegram_update(
            session=session,
            settings=settings,
            agent=DeterministicOpinionAgent(),
            telegram=telegram,
            update={
                "update_id": 1000 + index,
                "callback_query": {
                    "id": f"cb-e2e-{index}",
                    "data": f"prop:{proposal.id}:approve",
                    "message": {"message_id": 1, "chat": {"id": settings.telegram_allowed_chat_id}},
                },
            },
        )
        assert result == "applied"

    assert run.status == RunStatus.COMPLETED.value
    assert all(p.status == ProposalStatus.APPROVED.value for p in proposals)

    opinions_text = (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8")
    assert "<!-- opinion-id: opinion-000003 -->" in opinions_text  # added
    assert "Clarified by: Highlight text here." in opinions_text  # updated
    assert "opinion-000002" not in opinions_text  # removed

    sources = read_jsonl(opinions_repo / "OPINIONS_SOURCES.jsonl")
    source_opinions = {row["opinion_id"] for row in sources}
    assert "opinion-000003" in source_opinions
    assert "opinion-000002" not in source_opinions

    decisions = read_decisions(paths)
    assert len(decisions) == 4
    assert {d.decision for d in decisions} == {"approved"}

    state = load_state(paths)
    assert state.workflow.last_completed_window_end == "2026-06-12T00:00:00+00:00"

    for sha_range in ("HEAD~1 HEAD", "HEAD~2 HEAD~1", "HEAD~3 HEAD~2", "HEAD~4 HEAD~3"):
        files = set(run_git(opinions_repo, "diff", "--name-only", *sha_range.split()).splitlines())
        assert files <= {"OPINIONS.md", "OPINIONS_SOURCES.jsonl"}
    assert run_git(opinions_repo, "status", "--porcelain", "--", "OPINIONS.md", "OPINIONS_SOURCES.jsonl") == ""

    run_paths = RunPaths(settings.runs_dir)
    assert not run_paths.active_run_dir(run.id).exists()
    assert (run_paths.completed_run_dir(run.id) / "final.json").exists()
