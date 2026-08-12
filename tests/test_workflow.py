from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import seed_corpus
from sqlalchemy import select

from opinions_agent.agent import (
    AgentReadContext,
    AgentTurnOutput,
    DeterministicOpinionAgent,
    OpinionAgent,
    TelegramMessageSpec,
)
from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths, load_state
from opinions_agent.fsio import read_json, read_jsonl, write_jsonl_atomic
from opinions_agent.models import OpinionRun, RunStatus, TelegramInteraction
from opinions_agent.selection import RunPaths
from opinions_agent.telegram import FakeTelegramClient
from opinions_agent.tools.git_ops import run_git
from opinions_agent.workflow import (
    ActiveRunError,
    handle_telegram_update,
    send_agent_messages,
    start_opinion_run,
    transition,
)

WINDOW_START = datetime(2026, 6, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 6, 12, tzinfo=UTC)


async def start_run(session, settings, telegram, agent=None) -> OpinionRun | None:
    return await start_opinion_run(
        session=session,
        settings=settings,
        agent=agent or DeterministicOpinionAgent(),
        telegram=telegram,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
    )


async def handle(session, settings, telegram, update, agent=None) -> str:
    return await handle_telegram_update(
        session=session,
        settings=settings,
        agent=agent or DeterministicOpinionAgent(),
        telegram=telegram,
        update=update,
    )


def outbound_for_run(session, run: OpinionRun) -> TelegramInteraction:
    outbound = session.scalar(
        select(TelegramInteraction)
        .where(TelegramInteraction.direction == "outbound", TelegramInteraction.opinion_run_id == run.id)
        .order_by(TelegramInteraction.id)
    )
    assert outbound is not None
    assert outbound.message_id is not None
    return outbound


def callback_update(update_id: int, outbound: TelegramInteraction, data: str, chat_id: int = 12345) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb-{update_id}",
            "data": data,
            "message": {"message_id": outbound.message_id, "chat": {"id": chat_id}},
        },
    }


def reply_update(update_id: int, outbound: TelegramInteraction, text: str, chat_id: int = 12345) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 10000 + update_id,
            "chat": {"id": chat_id},
            "text": text,
            "reply_to_message": {"message_id": outbound.message_id},
        },
    }


async def test_active_run_blocks_new_run(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    session.add(OpinionRun(status=RunStatus.AWAITING_USER.value, window_start=WINDOW_START, window_end=WINDOW_END))
    session.commit()

    with pytest.raises(ActiveRunError):
        await start_run(session, settings, FakeTelegramClient())


async def test_start_run_writes_bundle_and_sends_agent_messages(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()

    run = await start_run(session, settings, telegram)

    assert run is not None
    assert run.status == RunStatus.AWAITING_USER.value
    assert run.turn_seq == 1
    run_dir = RunPaths(settings.runs_dir).active_run_dir(run.id)
    assert sorted(p.name for p in run_dir.iterdir()) == [
        "review",
        "selected-documents.jsonl",
        "selected-highlights.jsonl",
    ]
    assert sorted(p.name for p in (run_dir / "review").iterdir()) == ["initial-telegram.md", "summary.md"]
    initial_telegram = (run_dir / "review" / "initial-telegram.md").read_text(encoding="utf-8")
    assert "# Initial Telegram Messages" in initial_telegram
    assert "<b>Add Opinion #1</b>" in initial_telegram
    assert "<blockquote expandable>" in initial_telegram
    assert "Buttons: Approve, Reject" in initial_telegram
    assert len(telegram.sent) == 1
    assert [button.text for button in telegram.sent[0][1].buttons] == ["Approve", "Reject"]
    outbound = outbound_for_run(session, run)
    assert outbound.idempotency_key == f"opinion-run:{run.id}:turn:1:message:0"
    assert outbound.message_id == 1001


async def test_no_highlights_in_window_creates_no_run(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings, highlight_count=0)

    run = await start_run(session, settings, FakeTelegramClient())

    assert run is None
    assert session.scalar(select(OpinionRun)) is None


async def test_callback_resumes_agent_then_validates_commits_and_records_durability(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    outbound = outbound_for_run(session, run)
    (opinions_repo / "UNRELATED.md").write_text("dirty unrelated\n", encoding="utf-8")

    result = await handle(
        session,
        settings,
        telegram,
        callback_update(100, outbound, "approve:add-deterministic-opinion"),
    )

    assert result == "resumed"
    assert run.status == RunStatus.COMPLETED.value
    assert run.turn_seq == 2
    opinions_text = (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8")
    assert "opinion-000003" in opinions_text
    assert "Deterministic opinion." in opinions_text
    sources = read_jsonl(opinions_repo / "OPINIONS_SOURCES.jsonl")
    assert {"opinion-000003"} == {row["opinion_id"] for row in sources if row["evidence_id"] == "rw:h0"}
    assert read_json(CorpusPaths(settings.opinions_data_dir).opinion_id_high_water)["highest"] == 3
    state = load_state(CorpusPaths(settings.opinions_data_dir))
    assert "workflow" not in state.model_dump()
    committed_files = set(run_git(opinions_repo, "diff", "--name-only", "HEAD~1", "HEAD").splitlines())
    assert committed_files == {"OPINIONS.md", "OPINIONS_SOURCES.jsonl"}
    assert run_git(opinions_repo, "status", "--porcelain") == "M UNRELATED.md"
    assert len(telegram.edited_messages) == 1
    edited_chat_id, edited_message_id, edited_text = telegram.edited_messages[0]
    assert edited_chat_id == settings.telegram_allowed_chat_id
    assert edited_message_id == outbound.message_id
    assert edited_text.startswith("<b>✅ Approved - Add Opinion #1</b>")
    assert "Durable systems should preserve provenance" in edited_text
    assert "<blockquote expandable>" in edited_text
    assert "Durability: commit" in telegram.sent[-1][1].text
    assert not RunPaths(settings.runs_dir).active_run_dir(run.id).exists()
    assert (RunPaths(settings.runs_dir).completed_run_dir(run.id) / "final.json").exists()


class TwoMessageAgent(OpinionAgent):
    def __init__(self) -> None:
        self.prompts: list[str | None] = []

    async def run_turn(
        self,
        *,
        run_id: str,
        context: AgentReadContext,
        settings: Settings,
        prompt_fragment: str | None,
        resume_state: dict | None,
    ):
        self.prompts.append(prompt_fragment)
        if prompt_fragment is None:
            return AgentTurnOutput(
                status="awaiting_user",
                telegram_messages=[
                    TelegramMessageSpec(
                        text="First?",
                        buttons=[{"text": "Approve", "callback_data": "approve:first"}],
                    ),
                    TelegramMessageSpec(
                        text="Second?",
                        buttons=[{"text": "Approve", "callback_data": "approve:second"}],
                    ),
                ],
            ), {"fake": True}
        return AgentTurnOutput(status="done", telegram_messages=[TelegramMessageSpec(text="Done.")]), resume_state


async def test_records_partial_responses_without_resuming_until_all_required_messages_answered(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    agent = TwoMessageAgent()
    run = await start_run(session, settings, telegram, agent)
    outbounds = list(
        session.scalars(
            select(TelegramInteraction)
            .where(TelegramInteraction.direction == "outbound", TelegramInteraction.opinion_run_id == run.id)
            .order_by(TelegramInteraction.id)
        )
    )

    first = await handle(session, settings, telegram, callback_update(200, outbounds[0], "approve:first"), agent)
    second = await handle(session, settings, telegram, callback_update(201, outbounds[1], "approve:second"), agent)

    assert first == "recorded"
    assert second == "resumed"
    assert len(agent.prompts) == 2
    assert "Original Telegram message_id" in agent.prompts[-1]
    assert "Callback data:\napprove:first" in agent.prompts[-1]
    assert run.status == RunStatus.COMPLETED.value


async def test_reply_marks_original_message_addressed_without_resuming_until_all_required_messages_answered(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    agent = TwoMessageAgent()
    run = await start_run(session, settings, telegram, agent)
    outbounds = list(
        session.scalars(
            select(TelegramInteraction)
            .where(TelegramInteraction.direction == "outbound", TelegramInteraction.opinion_run_id == run.id)
            .order_by(TelegramInteraction.id)
        )
    )

    result = await handle(session, settings, telegram, reply_update(202, outbounds[0], "please revise"), agent)

    assert result == "recorded"
    assert run.status == RunStatus.AWAITING_USER.value
    assert len(agent.prompts) == 1
    assert len(telegram.edited_messages) == 1
    edited_chat_id, edited_message_id, edited_text = telegram.edited_messages[0]
    assert edited_chat_id == settings.telegram_allowed_chat_id
    assert edited_message_id == outbounds[0].message_id
    assert edited_text == "<b>💬 Reply received - First?</b>"


async def test_skip_resumes_without_app_side_decisions(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)

    result = await handle(
        session,
        settings,
        telegram,
        {
            "update_id": 300,
            "message": {"message_id": 301, "chat": {"id": settings.telegram_allowed_chat_id}, "text": "SKIP"},
        },
    )

    assert result == "skip"
    assert run.status == RunStatus.COMPLETED.value
    assert "opinion-000003" not in (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8")
    assert "Durability: no opinion file changes" in telegram.sent[-1][1].text


async def test_go_resumes_same_agent_conversation(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)

    result = await handle(
        session,
        settings,
        telegram,
        {
            "update_id": 301,
            "message": {"message_id": 302, "chat": {"id": settings.telegram_allowed_chat_id}, "text": "GO"},
        },
    )

    assert result == "go"
    assert run.status == RunStatus.COMPLETED.value
    assert "opinion-000003" in (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8")


async def test_free_text_without_reply_does_not_resume(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)

    result = await handle(
        session,
        settings,
        telegram,
        {
            "update_id": 302,
            "message": {"message_id": 303, "chat": {"id": settings.telegram_allowed_chat_id}, "text": "hello"},
        },
    )

    assert result == "no_pending_run"
    assert run.status == RunStatus.AWAITING_USER.value


async def test_duplicate_update_is_ignored(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    outbound = outbound_for_run(session, run)
    update = callback_update(400, outbound, "approve:add-deterministic-opinion")

    assert await handle(session, settings, telegram, update) == "resumed"
    assert await handle(session, settings, telegram, update) == "duplicate"


async def test_callback_data_must_match_stored_buttons(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    outbound = outbound_for_run(session, run)

    result = await handle(session, settings, telegram, callback_update(500, outbound, "approve:forged"))

    assert result == "ignored"
    assert run.status == RunStatus.AWAITING_USER.value


class BlockedAgent(OpinionAgent):
    async def run_turn(self, **kwargs):
        return AgentTurnOutput(
            status="blocked",
            telegram_messages=[TelegramMessageSpec(text="Manual intervention required.")],
            notes="blocked by test",
        ), None


async def test_blocked_agent_marks_terminal_blocked_without_commit(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    before = run_git(opinions_repo, "rev-parse", "HEAD")
    telegram = FakeTelegramClient()

    run = await start_run(session, settings, telegram, BlockedAgent())

    assert run.status == RunStatus.BLOCKED.value
    assert run.failure_reason == "blocked by test"
    assert telegram.sent[-1][1].text == "Manual intervention required."
    assert run_git(opinions_repo, "rev-parse", "HEAD") == before


class NoopDoneAgent(OpinionAgent):
    async def run_turn(self, **kwargs):
        return AgentTurnOutput(status="done", telegram_messages=[TelegramMessageSpec(text="Nothing to change.")]), None


class EmptyMessageAddOpinionAgent(OpinionAgent):
    async def run_turn(self, *, context: AgentReadContext, **kwargs):
        evidence = read_jsonl(context.selected_highlights_jsonl)[0]
        text = context.opinions_md.read_text(encoding="utf-8")
        context.opinions_md.write_text(
            text
            + "\n"
            + "- New fallback-summary opinion.\n"
            + "  <!-- opinion-id: opinion-000003 -->\n"
            + f"  <!-- sources: {evidence['highlight_id']} -->\n",
            encoding="utf-8",
        )
        rows = read_jsonl(context.sources_jsonl)
        rows.append(
            {
                "opinion_id": "opinion-000003",
                "evidence_id": evidence["highlight_id"],
                "document_id": evidence["document_id"],
                "document_title": evidence["document_title"],
                "source_url": evidence["source_url"],
                "evidence_text": evidence["text"],
                "added_at": evidence["highlighted_at"],
            }
        )
        write_jsonl_atomic(context.sources_jsonl, rows)
        return AgentTurnOutput(status="done", telegram_messages=[]), None


async def test_done_without_artifact_changes_completes_without_commit_sha(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    before = run_git(opinions_repo, "rev-parse", "HEAD")
    telegram = FakeTelegramClient()

    run = await start_run(session, settings, telegram, NoopDoneAgent())

    assert run.status == RunStatus.COMPLETED.value
    assert run_git(opinions_repo, "rev-parse", "HEAD") == before
    assert "Durability: no opinion file changes" in telegram.sent[-1][1].text
    final = read_json(RunPaths(settings.runs_dir).completed_run_dir(run.id) / "final.json")
    assert final["commit_sha"] is None


async def test_done_without_agent_message_sends_fallback_completion_summary(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()

    run = await start_run(session, settings, telegram, EmptyMessageAddOpinionAgent())

    assert run.status == RunStatus.COMPLETED.value
    assert "Done: 1 opinions added, 0 opinions updated, 0 opinions removed, and 1 evidence rows changed." in (
        telegram.sent[-1][1].text
    )
    assert "Durability: commit " in telegram.sent[-1][1].text


class RemoveHighestOpinionAgent(OpinionAgent):
    async def run_turn(self, *, context, **kwargs):
        text = context.opinions_md.read_text(encoding="utf-8")
        text = text.replace(
            "\n- This belief is old and weakly supported.\n"
            "  <!-- opinion-id: opinion-000002 -->\n"
            "  <!-- sources: rw:seed-old -->\n",
            "\n",
        )
        context.opinions_md.write_text(text, encoding="utf-8")
        rows = [row for row in read_jsonl(context.sources_jsonl) if row["opinion_id"] != "opinion-000002"]
        write_jsonl_atomic(context.sources_jsonl, rows)
        return (
            AgentTurnOutput(status="done", telegram_messages=[TelegramMessageSpec(text="Removed stale opinion.")]),
            None,
        )


async def test_high_water_does_not_regress_when_highest_opinion_is_removed(
    session,
    settings: Settings,
    opinions_repo: Path,
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()

    run = await start_run(session, settings, telegram, RemoveHighestOpinionAgent())

    assert run.status == RunStatus.COMPLETED.value
    assert "opinion-000002" not in (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8")
    assert read_json(CorpusPaths(settings.opinions_data_dir).opinion_id_high_water)["highest"] == 2


async def test_unrelated_staged_file_rejects_final_commit(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    outbound = outbound_for_run(session, run)
    (opinions_repo / "UNRELATED.md").write_text("staged unrelated\n", encoding="utf-8")
    run_git(opinions_repo, "add", "UNRELATED.md")

    with pytest.raises(Exception, match="refusing unrelated staged files"):
        await handle(session, settings, telegram, callback_update(501, outbound, "approve:add-deterministic-opinion"))

    assert run.status == RunStatus.FAILED.value
    assert "Opinion run failed before commit" in telegram.sent[-1][1].text


async def test_send_idempotent_retries_uncertain_message(session, settings: Settings, opinions_repo: Path) -> None:
    telegram = FakeTelegramClient()
    run = OpinionRun(
        status=RunStatus.AWAITING_USER.value,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        turn_seq=1,
        agent_output=AgentTurnOutput(
            status="awaiting_user",
            telegram_messages=[TelegramMessageSpec(text="Retry me.")],
        ).model_dump(mode="json"),
    )
    session.add(run)
    session.flush()
    key = f"opinion-run:{run.id}:turn:1:message:0"
    interaction = TelegramInteraction(
        direction="outbound",
        idempotency_key=key,
        opinion_run_id=run.id,
        chat_id=settings.telegram_allowed_chat_id,
        text="Retry me.",
        raw={"text": "Retry me.", "buttons": [], "force_reply": False},
        status="sending",
    )
    session.add(interaction)
    session.commit()

    await send_agent_messages(session=session, settings=settings, telegram=telegram, run=run)
    assert interaction.status == "uncertain"
    assert telegram.sent == []

    await send_agent_messages(session=session, settings=settings, telegram=telegram, run=run)
    assert interaction.status == "sent"
    assert interaction.message_id == 1001
    assert len(telegram.sent) == 1


class InvalidDoneAgent(DeterministicOpinionAgent):
    async def run_turn(self, *, context, settings, prompt_fragment, resume_state, **kwargs):
        if prompt_fragment is None:
            return await super().run_turn(
                context=context,
                settings=settings,
                prompt_fragment=prompt_fragment,
                resume_state=resume_state,
                **kwargs,
            )
        rows = read_jsonl(context.sources_jsonl)
        rows.append(
            {
                "opinion_id": "opinion-000001",
                "evidence_id": "rw:not-selected",
                "document_id": "reader:doc1",
                "document_title": "Example Article",
                "source_url": "https://example.com/article",
                "evidence_text": "Not selected.",
                "added_at": "2026-06-01T00:00:00+00:00",
            }
        )
        write_jsonl_atomic(context.sources_jsonl, rows)
        return AgentTurnOutput(status="done", telegram_messages=[TelegramMessageSpec(text="Done.")]), resume_state


async def test_final_validation_failure_marks_run_failed(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    agent = InvalidDoneAgent()
    run = await start_run(session, settings, telegram, agent)
    outbound = outbound_for_run(session, run)

    with pytest.raises(Exception, match="new source rows reference evidence outside current run|duplicate source row"):
        await handle(
            session,
            settings,
            telegram,
            callback_update(600, outbound, "approve:add-deterministic-opinion"),
            agent,
        )

    assert run.status == RunStatus.FAILED.value


def test_transition_rejects_invalid_edges() -> None:
    run = OpinionRun(status=RunStatus.COMPLETED.value, window_start=WINDOW_START, window_end=WINDOW_END)
    with pytest.raises(ValueError):
        transition(run, RunStatus.AWAITING_USER)
