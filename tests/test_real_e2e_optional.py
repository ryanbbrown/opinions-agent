from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import seed_corpus
from sqlalchemy import select

from opinions_agent.agent import ThinHarnessOpinionAgent
from opinions_agent.config import Settings
from opinions_agent.models import OpinionProposal, RunStatus
from opinions_agent.telegram import FakeTelegramClient
from opinions_agent.workflow import handle_telegram_update, start_opinion_run


@pytest.mark.skipif(os.environ.get("OPINIONS_RUN_REAL_E2E") != "1", reason="set OPINIONS_RUN_REAL_E2E=1")
async def test_real_agent_can_complete_proposal_approval_flow(session, settings: Settings, opinions_repo: Path):
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required")
    seed_corpus(settings)
    telegram = FakeTelegramClient()

    run = await start_opinion_run(
        session=session,
        settings=settings,
        agent=ThinHarnessOpinionAgent(),
        telegram=telegram,
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 12, tzinfo=UTC),
    )
    assert run is not None
    assert run.status in {RunStatus.AWAITING_USER.value, RunStatus.COMPLETED.value}
    if run.status == RunStatus.COMPLETED.value:
        return  # model legitimately proposed an empty batch

    proposal = session.scalar(select(OpinionProposal).where(OpinionProposal.opinion_run_id == run.id))
    assert proposal is not None
    assert len(telegram.sent) >= 1

    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=ThinHarnessOpinionAgent(),
        telegram=telegram,
        update={
            "update_id": 9000,
            "callback_query": {
                "id": "real-agent-approve",
                "data": f"prop:{proposal.id}:approve",
                "message": {"message_id": 1001, "chat": {"id": settings.telegram_allowed_chat_id}},
            },
        },
    )

    assert result == "applied"
    assert proposal.commit_sha or proposal.kind == "add_sources"
