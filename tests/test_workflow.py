from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from opinions_agent.agent import AgentOutput, DeterministicSummaryAgent, TelegramMessageSpec
from opinions_agent.config import Settings
from opinions_agent.models import ReadwiseHighlight, RunStatus, SummaryRun, SummaryRunHighlight, TelegramInteraction
from opinions_agent.telegram import FakeTelegramClient
from opinions_agent.tools.git_ops import commit_and_push_opinions_file, run_git
from opinions_agent.workflow import handle_telegram_update, select_unsummarized_highlights, summarize_recent, transition


def add_highlight(session, *, readwise_id: str = "h1", text: str = "Highlight text") -> ReadwiseHighlight:
    highlight = ReadwiseHighlight(
        readwise_id=readwise_id,
        document_id="doc",
        document_title="A Book",
        document_author="Author",
        text=text,
    )
    session.add(highlight)
    session.commit()
    return highlight


class FailingRevisionAgent(DeterministicSummaryAgent):
    async def revise(self, **kwargs):
        raise RuntimeError("revision failed")


def test_selection_skips_blocking_statuses_but_not_failed(session) -> None:
    blocked = add_highlight(session, readwise_id="blocked")
    failed = add_highlight(session, readwise_id="failed")
    fresh = add_highlight(session, readwise_id="fresh")
    blocked_run = SummaryRun(status=RunStatus.AWAITING_USER.value)
    failed_run = SummaryRun(status=RunStatus.FAILED.value)
    session.add_all([blocked_run, failed_run])
    session.flush()
    session.add_all(
        [
            SummaryRunHighlight(summary_run_id=blocked_run.id, readwise_highlight_id=blocked.id),
            SummaryRunHighlight(summary_run_id=failed_run.id, readwise_highlight_id=failed.id),
        ]
    )
    session.commit()

    selected_ids = {h.readwise_id for h in select_unsummarized_highlights(session, 10)}

    assert selected_ids == {failed.readwise_id, fresh.readwise_id}


def test_invalid_status_transition_fails_loudly(session) -> None:
    run = SummaryRun(status=RunStatus.COMMITTED.value)
    with pytest.raises(ValueError):
        transition(run, RunStatus.AWAITING_USER)


@pytest.mark.asyncio
async def test_free_text_without_reply_requires_single_pending_run(
    session,
    settings: Settings,
    opinions_repo: Path,
) -> None:
    session.add_all(
        [
            SummaryRun(status=RunStatus.AWAITING_USER.value),
            SummaryRun(status=RunStatus.AWAITING_USER.value),
        ]
    )
    session.commit()

    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=FakeTelegramClient(),
        update={"update_id": 10, "message": {"message_id": 99, "chat": {"id": 12345}, "text": "please revise"}},
    )

    assert result == "no_pending_run"


@pytest.mark.asyncio
async def test_telegram_duplicate_update_is_ignored(session, settings: Settings, opinions_repo: Path) -> None:
    add_highlight(session)
    telegram = FakeTelegramClient()
    run = await summarize_recent(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=telegram,
        limit=1,
    )
    assert run is not None
    update = {
        "update_id": 42,
        "callback_query": {
            "id": "cb-dup",
            "data": f"run:{run.id}:reject",
            "message": {"message_id": 1, "chat": {"id": settings.telegram_allowed_chat_id}},
        },
    }

    assert await handle_telegram_update(
        session=session, settings=settings, agent=DeterministicSummaryAgent(), telegram=telegram, update=update
    ) == "rejected"
    assert await handle_telegram_update(
        session=session, settings=settings, agent=DeterministicSummaryAgent(), telegram=telegram, update=update
    ) == "duplicate"


@pytest.mark.asyncio
async def test_stale_callback_does_not_mutate_committed_run(session, settings: Settings, opinions_repo: Path) -> None:
    add_highlight(session)
    telegram = FakeTelegramClient()
    run = await summarize_recent(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=telegram,
        limit=1,
    )
    assert run is not None
    run.status = RunStatus.COMMITTED.value
    session.commit()

    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=telegram,
        update={
            "update_id": 50,
            "callback_query": {
                "id": "cb-stale",
                "data": f"run:{run.id}:approve",
                "message": {"message_id": 1, "chat": {"id": settings.telegram_allowed_chat_id}},
            },
        },
    )

    assert result == "stale"
    assert session.get(SummaryRun, run.id).status == RunStatus.COMMITTED.value


@pytest.mark.asyncio
async def test_full_e2e_simulated_telegram_approval_commits_only_target(
    session, settings: Settings, opinions_repo: Path
) -> None:
    add_highlight(session, text="Good systems preserve provenance and make review cheap.")
    telegram = FakeTelegramClient()
    run = await summarize_recent(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=telegram,
        limit=1,
    )
    assert run is not None
    assert run.status == RunStatus.AWAITING_USER.value
    assert "Readwise Summary" not in (opinions_repo / "TEST_OPINIONS.md").read_text(encoding="utf-8")

    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=telegram,
        update={
            "update_id": 100,
            "callback_query": {
                "id": "cb-approve",
                "data": f"run:{run.id}:approve",
                "message": {"message_id": telegram.sent[0][1].reply_to_message_id or 1001, "chat": {"id": 12345}},
            },
        },
    )

    assert result == "committed"
    committed = session.get(SummaryRun, run.id)
    assert committed.status == RunStatus.COMMITTED.value
    assert committed.commit_sha
    assert len(telegram.sent) == 2
    assert telegram.sent[1][1].text.startswith(f"Committed summary for run {run.id}:")
    target_text = (opinions_repo / "TEST_OPINIONS.md").read_text(encoding="utf-8")
    assert "Good systems preserve provenance" in target_text
    assert run_git(opinions_repo, "diff", "--name-only", "HEAD~1", "HEAD") == "TEST_OPINIONS.md"
    assert run_git(opinions_repo, "status", "--porcelain") == ""


def test_outbound_send_crash_window_is_not_retried(session, settings: Settings) -> None:
    run = SummaryRun(status=RunStatus.AWAITING_USER.value)
    session.add(run)
    session.flush()
    session.add(
        TelegramInteraction(
            direction="outbound",
            idempotency_key=f"summary-run:{run.id}:message:0",
            summary_run_id=run.id,
            chat_id=settings.telegram_allowed_chat_id,
            status="sending",
        )
    )
    session.commit()

    from opinions_agent.workflow import send_agent_messages

    telegram = FakeTelegramClient()
    asyncio.run(
        send_agent_messages(
            session=session,
            settings=settings,
            telegram=telegram,
            run=run,
            output=AgentOutput(status="awaiting_user", telegram_messages=[TelegramMessageSpec(text="hello")]),
        )
    )

    interaction = session.scalar(select(TelegramInteraction).where(TelegramInteraction.summary_run_id == run.id))
    assert interaction.status == "uncertain"
    assert telegram.sent == []


@pytest.mark.asyncio
async def test_revision_sends_new_approval_message(session, settings: Settings, opinions_repo: Path) -> None:
    add_highlight(session, text="Original highlight text")
    telegram = FakeTelegramClient()
    run = await summarize_recent(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=telegram,
        limit=1,
    )
    outbound = session.scalar(
        select(TelegramInteraction).where(
            TelegramInteraction.direction == "outbound",
            TelegramInteraction.summary_run_id == run.id,
        )
    )

    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=telegram,
        update={
            "update_id": 2718,
            "message": {
                "message_id": 2719,
                "chat": {"id": settings.telegram_allowed_chat_id},
                "reply_to_message": {"message_id": outbound.message_id},
                "text": "mention review speed",
            },
        },
    )

    assert result == "revised"
    assert len(telegram.sent) == 2
    assert "Revision note: mention review speed" in telegram.sent[1][1].text
    interactions = list(
        session.scalars(
            select(TelegramInteraction)
            .where(TelegramInteraction.direction == "outbound", TelegramInteraction.summary_run_id == run.id)
            .order_by(TelegramInteraction.id)
        )
    )
    assert [interaction.idempotency_key for interaction in interactions] == [
        f"summary-run:{run.id}:proposal:0",
        f"summary-run:{run.id}:revision:2718:0",
    ]


@pytest.mark.asyncio
async def test_revision_failure_marks_run_failed_and_records_update(
    session, settings: Settings, opinions_repo: Path
) -> None:
    add_highlight(session)
    telegram = FakeTelegramClient()
    run = await summarize_recent(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=telegram,
        limit=1,
    )
    outbound = session.scalar(
        select(TelegramInteraction).where(
            TelegramInteraction.direction == "outbound",
            TelegramInteraction.summary_run_id == run.id,
        )
    )

    update = {
        "update_id": 314,
        "message": {
            "message_id": 315,
            "chat": {"id": settings.telegram_allowed_chat_id},
            "reply_to_message": {"message_id": outbound.message_id},
            "text": "make this sharper",
        },
    }
    with pytest.raises(RuntimeError, match="revision failed"):
        await handle_telegram_update(
            session=session,
            settings=settings,
            agent=FailingRevisionAgent(),
            telegram=telegram,
            update=update,
        )

    failed = session.get(SummaryRun, run.id)
    assert failed.status == RunStatus.FAILED.value
    assert failed.failure_reason == "revision failed"
    assert await handle_telegram_update(
        session=session,
        settings=settings,
        agent=FailingRevisionAgent(),
        telegram=telegram,
        update=update,
    ) == "duplicate"


def test_commit_tool_stages_only_target(session, settings: Settings, opinions_repo: Path) -> None:
    (opinions_repo / "TEST_OPINIONS.md").write_text("target changed\n", encoding="utf-8")
    (opinions_repo / "UNRELATED.md").write_text("dirty unrelated\n", encoding="utf-8")

    result = commit_and_push_opinions_file(
        repo_dir=opinions_repo,
        target_file="TEST_OPINIONS.md",
        branch="main",
        author_name=settings.opinions_git_author_name,
        author_email=settings.opinions_git_author_email,
    )

    assert result.changed
    assert run_git(opinions_repo, "diff", "--name-only", "HEAD~1", "HEAD") == "TEST_OPINIONS.md"
    assert run_git(opinions_repo, "status", "--porcelain") == "M UNRELATED.md"


def test_commit_tool_leaves_pre_staged_unrelated_file_staged(settings: Settings, opinions_repo: Path) -> None:
    (opinions_repo / "TEST_OPINIONS.md").write_text("target changed\n", encoding="utf-8")
    (opinions_repo / "UNRELATED.md").write_text("staged unrelated\n", encoding="utf-8")
    run_git(opinions_repo, "add", "UNRELATED.md")

    result = commit_and_push_opinions_file(
        repo_dir=opinions_repo,
        target_file="TEST_OPINIONS.md",
        branch="main",
        author_name=settings.opinions_git_author_name,
        author_email=settings.opinions_git_author_email,
    )

    assert result.changed
    assert run_git(opinions_repo, "diff", "--name-only", "HEAD~1", "HEAD") == "TEST_OPINIONS.md"
    assert run_git(opinions_repo, "status", "--porcelain") == "M  UNRELATED.md"


def test_commit_tool_noops_when_target_unchanged(settings: Settings, opinions_repo: Path) -> None:
    result = commit_and_push_opinions_file(
        repo_dir=opinions_repo,
        target_file="TEST_OPINIONS.md",
        branch="main",
        author_name=settings.opinions_git_author_name,
        author_email=settings.opinions_git_author_email,
    )

    assert result.changed is False
    assert result.commit_sha is None


@pytest.mark.asyncio
async def test_first_approval_can_create_missing_target_file(session, settings: Settings, opinions_repo: Path) -> None:
    run_git(opinions_repo, "rm", "TEST_OPINIONS.md")
    run_git(opinions_repo, "commit", "-m", "chore: remove test opinions")
    run_git(opinions_repo, "push", "origin", "main")
    add_highlight(session, text="The first approved summary should create the target file.")
    telegram = FakeTelegramClient()

    run = await summarize_recent(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=telegram,
        limit=1,
    )
    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=DeterministicSummaryAgent(),
        telegram=telegram,
        update={
            "update_id": 777,
            "callback_query": {
                "id": "cb-create-target",
                "data": f"run:{run.id}:approve",
                "message": {"message_id": 1001, "chat": {"id": settings.telegram_allowed_chat_id}},
            },
        },
    )

    assert result == "committed"
    assert (opinions_repo / "TEST_OPINIONS.md").exists()
    assert run_git(opinions_repo, "diff", "--name-only", "HEAD~1", "HEAD") == "TEST_OPINIONS.md"
