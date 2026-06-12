from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import seed_corpus
from sqlalchemy import select

from opinions_agent.agent import DeterministicOpinionAgent, OpinionChangeProposal, OpinionProposalOutput
from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths, load_state, read_decisions
from opinions_agent.fsio import read_json, read_jsonl
from opinions_agent.models import OpinionProposal, OpinionRun, ProposalStatus, RunStatus, TelegramInteraction
from opinions_agent.selection import RunPaths
from opinions_agent.telegram import FakeTelegramClient
from opinions_agent.tools.git_ops import GitToolError, run_git
from opinions_agent.workflow import (
    ActiveRunError,
    handle_telegram_update,
    send_proposal_messages,
    start_opinion_run,
    transition,
)

WINDOW_START = datetime(2026, 6, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 6, 12, tzinfo=UTC)


class EmptyBatchAgent(DeterministicOpinionAgent):
    async def propose(self, **kwargs):
        return OpinionProposalOutput(status="awaiting_user", proposals=[]), {"model": "empty"}


class InvalidProposalAgent(DeterministicOpinionAgent):
    async def propose(self, **kwargs):
        proposal = OpinionChangeProposal(
            proposal_id="prop_bad",
            kind="add_opinion",
            title="Bad",
            proposed_text="Bad",
            rationale="Unknown supporting highlight.",
            supporting_highlight_ids=["rw:does-not-exist"],
        )
        return OpinionProposalOutput(status="awaiting_user", proposals=[proposal]), None


class AddSourcesToMissingOpinionAgent(DeterministicOpinionAgent):
    async def propose(self, *, context, **kwargs):
        from opinions_agent.fsio import read_jsonl

        highlight = read_jsonl(context.run_dir / "selected-highlights.jsonl")[0]
        proposal = OpinionChangeProposal(
            proposal_id="prop_missing_opinion",
            kind="add_sources",
            opinion_id="opinion-999999",
            rationale="Targets an opinion that does not exist.",
            supporting_highlight_ids=[highlight["highlight_id"]],
        )
        return OpinionProposalOutput(status="awaiting_user", proposals=[proposal]), None


class FailingRevisionAgent(DeterministicOpinionAgent):
    async def revise(self, **kwargs):
        raise RuntimeError("revision failed")


async def start_run(session, settings, telegram, agent=None) -> OpinionRun | None:
    return await start_opinion_run(
        session=session,
        settings=settings,
        agent=agent or DeterministicOpinionAgent(),
        telegram=telegram,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
    )


def proposal_by_pid(session, run: OpinionRun, proposal_id: str, batch: int | None = None) -> OpinionProposal:
    proposal = session.scalar(
        select(OpinionProposal).where(
            OpinionProposal.opinion_run_id == run.id,
            OpinionProposal.proposal_id == proposal_id,
            OpinionProposal.batch == (batch or run.batch),
        )
    )
    assert proposal is not None
    return proposal


def callback_update(update_id: int, proposal_db_id: int, action: str, chat_id: int = 12345) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb-{update_id}",
            "data": f"prop:{proposal_db_id}:{action}",
            "message": {"message_id": 1, "chat": {"id": chat_id}},
        },
    }


async def handle(session, settings, telegram, update, agent=None) -> str:
    return await handle_telegram_update(
        session=session,
        settings=settings,
        agent=agent or DeterministicOpinionAgent(),
        telegram=telegram,
        update=update,
    )


async def test_active_run_blocks_new_run(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    session.add(
        OpinionRun(status=RunStatus.AWAITING_USER.value, window_start=WINDOW_START, window_end=WINDOW_END)
    )
    session.commit()

    with pytest.raises(ActiveRunError):
        await start_run(session, settings, FakeTelegramClient())


async def test_start_run_writes_bundle_and_sends_per_proposal_messages(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()

    run = await start_run(session, settings, telegram)

    assert run is not None
    assert run.status == RunStatus.AWAITING_USER.value
    run_dir = RunPaths(settings.runs_dir).active_run_dir(run.id)
    assert sorted(p.name for p in run_dir.iterdir()) == [
        "brief.md",
        "selected-documents.jsonl",
        "selected-highlights.jsonl",
    ]
    proposals = list(session.scalars(select(OpinionProposal).where(OpinionProposal.opinion_run_id == run.id)))
    assert sorted(p.proposal_id for p in proposals) == ["prop_add", "prop_remove", "prop_sources", "prop_update"]
    assert len(telegram.sent) == 4
    for _, spec in telegram.sent:
        assert [button.text for button in spec.buttons] == ["Approve", "Reject", "Revise"]


async def test_no_highlights_in_window_creates_no_run(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings, highlight_count=0)

    run = await start_run(session, settings, FakeTelegramClient())

    assert run is None
    assert session.scalar(select(OpinionRun)) is None


async def test_approve_add_opinion_applies_commits_and_records_decision(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    (opinions_repo / "UNRELATED.md").write_text("dirty unrelated\n", encoding="utf-8")
    proposal = proposal_by_pid(session, run, "prop_add")

    result = await handle(session, settings, telegram, callback_update(100, proposal.id, "approve"))

    assert result == "applied"
    assert proposal.status == ProposalStatus.APPROVED.value
    assert proposal.commit_sha
    assert proposal.applied_opinion_id == "opinion-000003"
    opinions_text = (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8")
    assert "<!-- opinion-id: opinion-000003 -->" in opinions_text
    assert "## 3." in opinions_text
    sources = read_jsonl(opinions_repo / "OPINIONS_SOURCES.jsonl")
    assert {"opinion-000003"} == {row["opinion_id"] for row in sources if row["highlight_id"] == "rw:h0"}
    assert sources[-1]["highlight_text"].startswith("Durable systems")
    decisions = read_decisions(CorpusPaths(settings.opinions_data_dir))
    assert decisions[-1].decision == "approved"
    assert decisions[-1].opinion_id == "opinion-000003"
    committed_files = set(run_git(opinions_repo, "diff", "--name-only", "HEAD~1", "HEAD").splitlines())
    assert committed_files == {"OPINIONS.md", "OPINIONS_SOURCES.jsonl"}
    assert run_git(opinions_repo, "status", "--porcelain") == "M UNRELATED.md"
    assert run.status == RunStatus.AWAITING_USER.value
    assert telegram.sent[-1][1].text.startswith("Applied prop_add")


async def test_reject_records_decision_without_mutation(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    before = (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8")
    proposal = proposal_by_pid(session, run, "prop_remove")

    result = await handle(session, settings, telegram, callback_update(101, proposal.id, "reject"))

    assert result == "rejected"
    assert proposal.status == ProposalStatus.REJECTED.value
    assert (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8") == before
    decisions = read_decisions(CorpusPaths(settings.opinions_data_dir))
    assert decisions[-1].decision == "rejected"
    assert decisions[-1].kind == "remove_opinion"


async def test_run_completes_and_advances_cursor_after_all_proposals_terminal(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    proposals = list(session.scalars(select(OpinionProposal).where(OpinionProposal.opinion_run_id == run.id)))

    for index, proposal in enumerate(proposals):
        action = "approve" if proposal.kind != "remove_opinion" else "reject"
        await handle(session, settings, telegram, callback_update(200 + index, proposal.id, action))

    assert run.status == RunStatus.COMPLETED.value
    state = load_state(CorpusPaths(settings.opinions_data_dir))
    assert state.workflow.last_completed_window_start == "2026-06-01T00:00:00+00:00"
    assert state.workflow.last_completed_window_end == "2026-06-12T00:00:00+00:00"
    run_paths = RunPaths(settings.runs_dir)
    assert not run_paths.active_run_dir(run.id).exists()
    final = read_json(run_paths.completed_run_dir(run.id) / "final.json")
    assert final["status"] == "completed"
    assert len(final["proposals"]) == 4


async def test_duplicate_update_is_ignored(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    proposal = proposal_by_pid(session, run, "prop_sources")
    update = callback_update(300, proposal.id, "reject")

    assert await handle(session, settings, telegram, update) == "rejected"
    assert await handle(session, settings, telegram, update) == "duplicate"


async def test_stale_callback_does_not_mutate_terminal_proposal(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    proposal = proposal_by_pid(session, run, "prop_update")
    await handle(session, settings, telegram, callback_update(400, proposal.id, "reject"))

    result = await handle(session, settings, telegram, callback_update(401, proposal.id, "approve"))

    assert result == "stale"
    assert proposal.status == ProposalStatus.REJECTED.value


async def test_revision_supersedes_pending_batch_and_sends_new_messages(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    first_batch = proposal_by_pid(session, run, "prop_add")
    outbound = session.scalar(
        select(TelegramInteraction).where(
            TelegramInteraction.direction == "outbound",
            TelegramInteraction.opinion_proposal_id == first_batch.id,
        )
    )
    sent_before = len(telegram.sent)

    result = await handle(
        session,
        settings,
        telegram,
        {
            "update_id": 500,
            "message": {
                "message_id": 501,
                "chat": {"id": settings.telegram_allowed_chat_id},
                "reply_to_message": {"message_id": outbound.message_id},
                "text": "tighten the wording",
            },
        },
    )

    assert result == "revised"
    assert run.status == RunStatus.AWAITING_USER.value
    assert run.batch == 2
    assert first_batch.status == ProposalStatus.SUPERSEDED.value
    second_batch = proposal_by_pid(session, run, "prop_add", batch=2)
    assert "tighten the wording" in (second_batch.proposed_text or "")
    assert len(telegram.sent) == sent_before + 4

    stale = await handle(session, settings, telegram, callback_update(502, first_batch.id, "approve"))
    assert stale == "stale"

    approved = await handle(session, settings, telegram, callback_update(503, second_batch.id, "approve"))
    assert approved == "applied"


async def test_revision_failure_marks_run_failed_and_dedupes(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    outbound = session.scalar(
        select(TelegramInteraction).where(
            TelegramInteraction.direction == "outbound",
            TelegramInteraction.opinion_run_id == run.id,
        )
    )
    update = {
        "update_id": 600,
        "message": {
            "message_id": 601,
            "chat": {"id": settings.telegram_allowed_chat_id},
            "reply_to_message": {"message_id": outbound.message_id},
            "text": "make this sharper",
        },
    }

    with pytest.raises(RuntimeError, match="revision failed"):
        await handle(session, settings, telegram, update, agent=FailingRevisionAgent())

    assert run.status == RunStatus.FAILED.value
    assert run.failure_reason == "revision failed"
    assert await handle(session, settings, telegram, update, agent=FailingRevisionAgent()) == "duplicate"


async def test_empty_proposal_batch_completes_run_and_advances_cursor(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)

    run = await start_run(session, settings, FakeTelegramClient(), agent=EmptyBatchAgent())

    assert run is not None
    assert run.status == RunStatus.COMPLETED.value
    state = load_state(CorpusPaths(settings.opinions_data_dir))
    assert state.workflow.last_completed_window_end == "2026-06-12T00:00:00+00:00"


async def test_supporting_highlights_outside_run_selection_fail_run_loudly(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)

    with pytest.raises(ValueError, match="not in current run selection"):
        await start_run(session, settings, FakeTelegramClient(), agent=InvalidProposalAgent())

    run = session.scalar(select(OpinionRun))
    assert run.status == RunStatus.FAILED.value
    assert "rw:does-not-exist" in run.failure_reason


async def test_corpus_highlight_outside_window_is_not_valid_evidence(
    session, settings: Settings, opinions_repo: Path
) -> None:
    from opinions_agent.corpus import CorpusPaths as Paths
    from opinions_agent.corpus import HighlightRow, upsert_highlights

    seed_corpus(settings)
    upsert_highlights(
        Paths(settings.opinions_data_dir),
        [
            HighlightRow(
                highlight_id="rw:old",
                document_id="reader:doc1",
                reader_id="doc1",
                text="Historical highlight outside the window.",
                highlighted_at="2026-05-01T00:00:00+00:00",
            )
        ],
    )

    class OutOfWindowEvidenceAgent(DeterministicOpinionAgent):
        async def propose(self, **kwargs):
            proposal = OpinionChangeProposal(
                proposal_id="prop_old_evidence",
                kind="add_opinion",
                title="Old evidence",
                proposed_text="Built on stale evidence.",
                rationale="Uses a highlight outside the selected window.",
                supporting_highlight_ids=["rw:old"],
            )
            return OpinionProposalOutput(status="awaiting_user", proposals=[proposal]), None

    with pytest.raises(ValueError, match="not in current run selection"):
        await start_run(session, settings, FakeTelegramClient(), agent=OutOfWindowEvidenceAgent())


async def test_first_approval_creates_missing_sources_file(session, settings: Settings, opinions_repo: Path) -> None:
    run_git(opinions_repo, "rm", "OPINIONS_SOURCES.jsonl")
    run_git(opinions_repo, "commit", "-m", "chore: remove sources file")
    run_git(opinions_repo, "push", "origin", "main")
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    proposal = proposal_by_pid(session, run, "prop_add")

    result = await handle(session, settings, telegram, callback_update(900, proposal.id, "approve"))

    assert result == "applied"
    sources = read_jsonl(opinions_repo / "OPINIONS_SOURCES.jsonl")
    assert sources[0]["opinion_id"] == proposal.applied_opinion_id
    committed_files = set(run_git(opinions_repo, "diff", "--name-only", "HEAD~1", "HEAD").splitlines())
    assert committed_files == {"OPINIONS.md", "OPINIONS_SOURCES.jsonl"}


async def test_removed_highest_opinion_id_is_never_reissued(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    remove = proposal_by_pid(session, run, "prop_remove")  # removes opinion-000002, the highest ID
    add = proposal_by_pid(session, run, "prop_add")

    assert await handle(session, settings, telegram, callback_update(910, remove.id, "approve")) == "applied"
    assert await handle(session, settings, telegram, callback_update(911, add.id, "approve")) == "applied"

    assert add.applied_opinion_id == "opinion-000003"
    opinions_text = (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8")
    assert "opinion-000002" not in opinions_text


async def test_failed_push_marks_run_failed_with_recovery_instructions(
    session, settings: Settings, opinions_repo: Path, tmp_path: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    proposal = proposal_by_pid(session, run, "prop_add")
    shutil.rmtree(tmp_path / "remote.git")

    with pytest.raises(GitToolError):
        await handle(session, settings, telegram, callback_update(700, proposal.id, "approve"))

    assert run.status == RunStatus.FAILED.value
    assert "prop_add" in run.failure_reason
    assert "push or reset manually" in run.failure_reason


async def test_outbound_send_crash_window_is_not_retried(session, settings: Settings, opinions_repo: Path) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    proposal = proposal_by_pid(session, run, "prop_add")
    interaction = session.scalar(
        select(TelegramInteraction).where(TelegramInteraction.opinion_proposal_id == proposal.id)
    )
    interaction.message_id = None
    interaction.status = "sending"
    session.commit()
    telegram.sent.clear()

    await send_proposal_messages(session=session, settings=settings, telegram=telegram, run=run)

    assert interaction.status == "uncertain"
    assert telegram.sent == []


async def test_run_window_defaults_to_workflow_cursor(session, settings: Settings, opinions_repo: Path) -> None:
    from opinions_agent.corpus import save_state

    paths = seed_corpus(settings)
    state = load_state(paths)
    state.workflow.last_completed_window_end = "2026-06-01T00:00:00+00:00"
    save_state(paths, state)

    run = await start_opinion_run(
        session=session,
        settings=settings,
        agent=DeterministicOpinionAgent(),
        telegram=FakeTelegramClient(),
        now=WINDOW_END,
    )

    assert run is not None
    assert run.window_start == WINDOW_START
    assert run.window_end == WINDOW_END


def test_invalid_status_transition_fails_loudly() -> None:
    run = OpinionRun(status=RunStatus.COMPLETED.value, window_start=WINDOW_START, window_end=WINDOW_END)
    with pytest.raises(ValueError):
        transition(run, RunStatus.AWAITING_USER)


async def test_free_text_without_reply_never_triggers_revision(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)

    result = await handle(
        session,
        settings,
        telegram,
        {"update_id": 800, "message": {"message_id": 801, "chat": {"id": 12345}, "text": "thanks!"}},
    )

    assert result == "no_pending_run"
    assert run.status == RunStatus.AWAITING_USER.value
    assert run.batch == 1


async def test_reply_to_completed_run_message_is_not_rerouted_to_active_run(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    first_run = await start_run(session, settings, telegram)
    first_outbound = session.scalar(
        select(TelegramInteraction).where(
            TelegramInteraction.direction == "outbound",
            TelegramInteraction.opinion_run_id == first_run.id,
        )
    )
    proposals = list(
        session.scalars(select(OpinionProposal).where(OpinionProposal.opinion_run_id == first_run.id))
    )
    for index, proposal in enumerate(proposals):
        await handle(session, settings, telegram, callback_update(820 + index, proposal.id, "reject"))
    assert first_run.status == RunStatus.COMPLETED.value
    second_run = await start_run(session, settings, telegram)
    assert second_run is not None

    result = await handle(
        session,
        settings,
        telegram,
        {
            "update_id": 830,
            "message": {
                "message_id": 831,
                "chat": {"id": settings.telegram_allowed_chat_id},
                "reply_to_message": {"message_id": first_outbound.message_id},
                "text": "revise the old run",
            },
        },
    )

    assert result == "no_pending_run"
    assert second_run.batch == 1


async def test_partial_approve_then_revise_preserves_approved_proposal(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    approved = proposal_by_pid(session, run, "prop_add")
    await handle(session, settings, telegram, callback_update(840, approved.id, "approve"))
    pending = proposal_by_pid(session, run, "prop_update")
    outbound = session.scalar(
        select(TelegramInteraction).where(TelegramInteraction.opinion_proposal_id == pending.id)
    )

    result = await handle(
        session,
        settings,
        telegram,
        {
            "update_id": 841,
            "message": {
                "message_id": 842,
                "chat": {"id": settings.telegram_allowed_chat_id},
                "reply_to_message": {"message_id": outbound.message_id},
                "text": "narrow the scope",
            },
        },
    )

    assert result == "revised"
    assert approved.status == ProposalStatus.APPROVED.value
    assert pending.status == ProposalStatus.SUPERSEDED.value
    assert run.batch == 2
    assert run.status == RunStatus.AWAITING_USER.value


async def test_add_sources_to_missing_opinion_fails_run_loudly(
    session, settings: Settings, opinions_repo: Path
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram, agent=AddSourcesToMissingOpinionAgent())
    proposal = proposal_by_pid(session, run, "prop_missing_opinion")

    with pytest.raises(ValueError, match="opinion not found"):
        await handle(session, settings, telegram, callback_update(850, proposal.id, "approve"))

    assert run.status == RunStatus.FAILED.value
    assert "opinion-999999" in run.failure_reason


async def test_abandon_run_supersedes_pending_and_keeps_cursor(
    session, settings: Settings, opinions_repo: Path
) -> None:
    from opinions_agent.workflow import abandon_run

    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    cursor_before = load_state(CorpusPaths(settings.opinions_data_dir)).workflow.last_completed_window_end

    abandon_run(session, settings, run)

    assert run.status == RunStatus.ABANDONED.value
    proposals = list(session.scalars(select(OpinionProposal).where(OpinionProposal.opinion_run_id == run.id)))
    assert all(p.status == ProposalStatus.SUPERSEDED.value for p in proposals)
    state = load_state(CorpusPaths(settings.opinions_data_dir))
    assert state.workflow.last_completed_window_end == cursor_before
    run_paths = RunPaths(settings.runs_dir)
    assert not run_paths.active_run_dir(run.id).exists()
    assert (run_paths.completed_run_dir(run.id) / "final.json").exists()


async def test_finalize_failure_does_not_mask_original_error(
    session, settings: Settings, opinions_repo: Path, monkeypatch
) -> None:
    seed_corpus(settings)
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram)
    proposals = list(session.scalars(select(OpinionProposal).where(OpinionProposal.opinion_run_id == run.id)))
    for index, proposal in enumerate(proposals[:-1]):
        await handle(session, settings, telegram, callback_update(860 + index, proposal.id, "reject"))

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("opinions_agent.workflow.finalize_run_dir", boom)

    with pytest.raises(OSError, match="disk full"):
        await handle(session, settings, telegram, callback_update(870, proposals[-1].id, "approve"))

    assert run.status == RunStatus.COMPLETED.value
    assert "disk full" in run.failure_reason
