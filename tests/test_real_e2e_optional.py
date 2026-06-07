from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opinions_agent.agent import ThinHarnessSummaryAgent
from opinions_agent.config import Settings, get_settings
from opinions_agent.models import ReadwiseHighlight, RunStatus
from opinions_agent.repo_checkout import ensure_opinions_repo
from opinions_agent.telegram import FakeTelegramClient, TelegramClient
from opinions_agent.workflow import approve_run, handle_telegram_update, summarize_recent


@pytest.mark.asyncio
@pytest.mark.skipif(os.environ.get("OPINIONS_RUN_REAL_E2E") != "1", reason="set OPINIONS_RUN_REAL_E2E=1")
async def test_real_openai_agent_can_complete_telegram_approval_flow(session, settings: Settings, opinions_repo: Path):
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required")
    session.add(
        ReadwiseHighlight(
            readwise_id="real-agent-highlight",
            document_id="doc",
            document_title="Real Agent Fixture",
            document_author="Test",
            text="A small vertical slice should keep side effects outside the model loop.",
        )
    )
    session.commit()
    telegram = FakeTelegramClient()

    run = await summarize_recent(
        session=session,
        settings=settings,
        agent=ThinHarnessSummaryAgent(),
        telegram=telegram,
        limit=1,
    )
    assert run is not None
    assert run.status == RunStatus.AWAITING_USER.value
    assert run.summary_text

    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=ThinHarnessSummaryAgent(),
        telegram=telegram,
        update={
            "update_id": 200,
            "callback_query": {
                "id": "real-agent-approve",
                "data": f"run:{run.id}:approve",
                "message": {"message_id": 1001, "chat": {"id": settings.telegram_allowed_chat_id}},
            },
        },
    )

    assert result == "committed"
    assert "Readwise Summary" in settings.opinions_target_path.read_text(encoding="utf-8")


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("OPINIONS_RUN_LIVE_E2E") != "1",
    reason="set OPINIONS_RUN_LIVE_E2E=1",
)
async def test_live_openai_telegram_and_real_test_opinions_file(session, tmp_path: Path):
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required")
    live = get_settings()
    if not live.telegram_bot_token or live.telegram_allowed_chat_id is None:
        pytest.skip("real Telegram config is required")

    settings = replace(
        live,
        database_url="sqlite+pysqlite:///:memory:",
        runs_dir=tmp_path / ".runs-live",
        local_trace_dir=tmp_path / ".traces-live",
        local_tracing_enabled=False,
        opinions_target_file="TEST_OPINIONS.md",
        use_fake_telegram=False,
    )
    ensure_opinions_repo(settings)
    run_git(settings.opinions_repo_dir, "checkout", settings.opinions_repo_branch)
    run_git(settings.opinions_repo_dir, "pull", "--ff-only", "origin", settings.opinions_repo_branch)
    assert run_git(settings.opinions_repo_dir, "status", "--porcelain", "--", settings.opinions_target_file) == ""

    marker = f"live-e2e-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    session.add(
        ReadwiseHighlight(
            readwise_id=marker,
            document_id="live-e2e-doc",
            document_title="Live E2E Fixture",
            document_author="opinions-agent",
            text=(
                f"{marker}: A full vertical slice should use the real model, send real Telegram messages, "
                "and commit the approved summary to TEST_OPINIONS.md."
            ),
        )
    )
    session.commit()

    telegram = TelegramClient(settings.telegram_bot_token)
    run = await summarize_recent(
        session=session,
        settings=settings,
        agent=ThinHarnessSummaryAgent(),
        telegram=telegram,
        limit=1,
    )
    assert run is not None
    assert run.status == RunStatus.AWAITING_USER.value
    assert run.summary_text

    result = await approve_run(session=session, settings=settings, telegram=telegram, run=run)

    assert result == "committed"
    assert run.status == RunStatus.COMMITTED.value
    assert run.commit_sha
    target_text = settings.opinions_target_path.read_text(encoding="utf-8")
    assert f"## Readwise Summary {run.id}" in target_text
    assert run.summary_text.strip() in target_text
    assert run_git(settings.opinions_repo_dir, "diff", "--name-only", "HEAD~1", "HEAD") == settings.opinions_target_file
    assert run_git(settings.opinions_repo_dir, "status", "--porcelain", "--", settings.opinions_target_file) == ""
