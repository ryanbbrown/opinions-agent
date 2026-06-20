from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import seed_corpus

from opinions_agent.agent import ThinHarnessOpinionAgent, build_read_context
from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths
from opinions_agent.selection import RunPaths, select_run_highlights, write_run_bundle
from opinions_agent.validation import run_artifact_validation


@pytest.mark.skipif(os.environ.get("OPINIONS_RUN_REAL_E2E") != "1", reason="set OPINIONS_RUN_REAL_E2E=1")
async def test_real_thinharness_agent_only_e2e(settings: Settings, opinions_repo: Path):
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required")
    seed_corpus(settings)
    run_id = "real-agent-e2e"
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 12, tzinfo=UTC)
    highlights, documents = select_run_highlights(CorpusPaths(settings.opinions_data_dir), start, end)
    bundle = write_run_bundle(
        run_id=run_id,
        run_paths=RunPaths(settings.runs_dir),
        window_start=start,
        window_end=end,
        highlights=highlights,
        documents=documents,
    )
    context = build_read_context(settings, bundle.run_dir)
    agent = ThinHarnessOpinionAgent()

    first, resume_state = await agent.run_turn(
        run_id=run_id,
        context=context,
        settings=settings,
        prompt_fragment=None,
        resume_state=None,
    )

    assert first.status == "awaiting_user"
    assert first.telegram_messages
    assert resume_state

    prompt = """Telegram responses received.

Original Telegram message_id: 1001
Original message text:
Approve whichever single proposal is best supported by the selected evidence.

User action:
Approve
"""
    output, resume_state = await agent.run_turn(
        run_id=run_id,
        context=context,
        settings=settings,
        prompt_fragment=prompt,
        resume_state=resume_state,
    )

    for _ in range(5):
        if output.status != "awaiting_user":
            break
        assert output.telegram_messages
        output, resume_state = await agent.run_turn(
            run_id=run_id,
            context=context,
            settings=settings,
            prompt_fragment="Telegram command received.\n\nCommand:\nGO",
            resume_state=resume_state,
        )
    else:
        pytest.fail("real agent did not converge after 5 resume turns")

    assert output.status in {"done", "blocked"}
    assert output.telegram_messages
    if output.status == "done":
        run_artifact_validation(settings=settings, run_dir=context.run_dir)
        assert "commit" not in " ".join(message.text.lower() for message in output.telegram_messages)
