from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opinions_agent.agent import (
    OpinionAgent,
    OpinionProposalOutput,
    TelegramButton,
    TelegramMessageSpec,
    build_read_context,
    validate_proposals,
)
from opinions_agent.config import Settings
from opinions_agent.corpus import (
    CorpusPaths,
    OpinionDecision,
    append_decisions,
    init_data_dirs,
    load_state,
    read_decisions,
    read_highlights,
    save_state,
)
from opinions_agent.fsio import read_jsonl, write_jsonl_atomic, write_text_atomic
from opinions_agent.models import (
    NON_TERMINAL_RUN_STATUSES,
    OpinionProposal,
    OpinionRun,
    ProposalStatus,
    RunStatus,
    TelegramInteraction,
    utcnow,
)
from opinions_agent.opinions_doc import (
    add_opinion,
    load_opinions,
    next_opinion_id,
    read_sources,
    remove_opinion,
    update_opinion,
    validate_opinions_files,
)
from opinions_agent.reader import iso_utc, parse_iso
from opinions_agent.repo_checkout import ensure_opinions_repo, ensure_repo_file
from opinions_agent.selection import RunPaths, finalize_run_dir, select_run_highlights, write_run_bundle
from opinions_agent.tools.git_ops import GitToolError, assert_targets_clean, commit_and_push_opinions_files

DEFAULT_WINDOW = timedelta(days=7)


class TelegramSender(Protocol):
    async def send_message(self, chat_id: int, spec: TelegramMessageSpec) -> int: ...

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None: ...


class ActiveRunError(RuntimeError):
    pass


VALID_TRANSITIONS = {
    RunStatus.PENDING_AGENT.value: {RunStatus.AWAITING_USER.value, RunStatus.COMPLETED.value, RunStatus.FAILED.value},
    RunStatus.AWAITING_USER.value: {
        RunStatus.REVISING.value,
        RunStatus.COMPLETED.value,
        RunStatus.FAILED.value,
        RunStatus.ABANDONED.value,
    },
    RunStatus.REVISING.value: {RunStatus.AWAITING_USER.value, RunStatus.COMPLETED.value, RunStatus.FAILED.value},
    RunStatus.COMPLETED.value: set(),
    RunStatus.FAILED.value: set(),
    RunStatus.ABANDONED.value: set(),
}


def transition(run: OpinionRun, next_status: RunStatus) -> None:
    allowed = VALID_TRANSITIONS[run.status]
    if next_status.value not in allowed:
        raise ValueError(f"invalid opinion run transition: {run.status} -> {next_status.value}")
    run.status = next_status.value


def find_active_run(session: Session) -> OpinionRun | None:
    return session.scalar(select(OpinionRun).where(OpinionRun.status.in_(NON_TERMINAL_RUN_STATUSES)))


def _run_window(
    settings: Settings,
    *,
    window_start: datetime | None,
    window_end: datetime | None,
    now: datetime | None,
) -> tuple[datetime, datetime]:
    current = now or datetime.now(UTC)
    end = window_end or current
    if window_start is not None:
        return window_start, end
    state = load_state(CorpusPaths(settings.opinions_data_dir))
    cursor = parse_iso(state.workflow.last_completed_window_end)
    return cursor or (end - DEFAULT_WINDOW), end


async def start_opinion_run(
    *,
    session: Session,
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    now: datetime | None = None,
) -> OpinionRun | None:
    """Select the current window, run the proposal agent, and request per-proposal approval.

    Returns None when no highlights fall in the window. Raises ActiveRunError when a
    previous run is still non-terminal.
    """
    active = find_active_run(session)
    if active is not None:
        raise ActiveRunError(f"run {active.id} is still {active.status}; not starting another run")

    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    start, end = _run_window(settings, window_start=window_start, window_end=window_end, now=now)
    highlights, documents = select_run_highlights(corpus, start, end)
    if not highlights:
        return None

    run = OpinionRun(
        status=RunStatus.PENDING_AGENT.value,
        window_start=start,
        window_end=end,
        model=settings.harness_model,
        attempts=1,
    )
    session.add(run)
    session.flush()
    bundle = write_run_bundle(
        run_id=run.id,
        run_paths=RunPaths(settings.runs_dir),
        window_start=start,
        window_end=end,
        highlights=highlights,
        documents=documents,
    )
    run.input_paths = {
        "dir": str(bundle.run_dir),
        "brief_md": str(bundle.brief_md),
        "selected_highlights_jsonl": str(bundle.selected_highlights_jsonl),
        "selected_documents_jsonl": str(bundle.selected_documents_jsonl),
    }
    session.commit()

    try:
        context = build_read_context(settings, bundle.run_dir)
        output, resume_state = await agent.propose(run_id=run.id, context=context, settings=settings)
        run.agent_output = output.model_dump(mode="json")
        run.resume_state = resume_state
        _store_proposal_batch(session, settings, run, output)
        session.commit()
        if run.status == RunStatus.AWAITING_USER.value:
            await send_proposal_messages(session=session, settings=settings, telegram=telegram, run=run)
        return run
    except Exception as exc:
        if run.status in NON_TERMINAL_RUN_STATUSES:
            transition(run, RunStatus.FAILED)
        run.failure_reason = str(exc)
        session.commit()
        raise


def _store_proposal_batch(session: Session, settings: Settings, run: OpinionRun, output: OpinionProposalOutput) -> None:
    """Validate and persist a proposal batch, completing the run when the batch is empty."""
    if output.status == "needs_more_work":
        raise ValueError(f"agent returned needs_more_work: {output.notes or 'no notes'}")
    validate_proposals(output.proposals)
    # Current selected highlights are the only admissible evidence for proposals;
    # historical corpus highlights are context, not support.
    selected = _selected_highlight_ids(run, settings)
    for proposal in output.proposals:
        missing = [hid for hid in proposal.supporting_highlight_ids if hid not in selected]
        if missing:
            raise ValueError(f"{proposal.proposal_id}: supporting highlights not in current run selection: {missing}")
    if not output.proposals:
        transition(run, RunStatus.COMPLETED)
        _advance_workflow_cursor(settings, run)
        _finalize_run_artifacts(settings, run)
        return
    session.add_all(
        [
            OpinionProposal(
                opinion_run_id=run.id,
                batch=run.batch,
                proposal_id=proposal.proposal_id,
                kind=proposal.kind,
                opinion_id=proposal.opinion_id,
                title=proposal.title,
                current_text=proposal.current_text,
                proposed_text=proposal.proposed_text,
                rationale=proposal.rationale,
                supporting_highlight_ids=proposal.supporting_highlight_ids,
            )
            for proposal in output.proposals
        ]
    )
    transition(run, RunStatus.AWAITING_USER)


def _trim(text: str | None, limit: int = 900) -> str:
    cleaned = (text or "").strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3] + "..."


def proposal_message_spec(proposal: OpinionProposal) -> TelegramMessageSpec:
    lines = [f"[{proposal.kind}] Proposal {proposal.proposal_id}"]
    if proposal.opinion_id:
        lines.append(f"Opinion: {proposal.opinion_id}")
    if proposal.title:
        lines.append(f"Title: {proposal.title}")
    if proposal.current_text:
        lines.extend(["", "Current:", _trim(proposal.current_text)])
    if proposal.proposed_text:
        lines.extend(["", "Proposed:", _trim(proposal.proposed_text)])
    lines.extend(["", f"Why: {_trim(proposal.rationale)}"])
    if proposal.supporting_highlight_ids:
        lines.append(f"Sources: {', '.join(proposal.supporting_highlight_ids)}")
    return TelegramMessageSpec(
        text="\n".join(lines),
        buttons=[
            TelegramButton(text="Approve", callback_data=f"prop:{proposal.id}:approve"),
            TelegramButton(text="Reject", callback_data=f"prop:{proposal.id}:reject"),
            TelegramButton(text="Revise", callback_data=f"prop:{proposal.id}:revise"),
        ],
    )


async def send_proposal_messages(
    *,
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    run: OpinionRun,
) -> None:
    proposals = list(
        session.scalars(
            select(OpinionProposal)
            .where(
                OpinionProposal.opinion_run_id == run.id,
                OpinionProposal.batch == run.batch,
                OpinionProposal.status == ProposalStatus.PENDING.value,
            )
            .order_by(OpinionProposal.id)
        )
    )
    for proposal in proposals:
        await _send_idempotent(
            session=session,
            settings=settings,
            telegram=telegram,
            key=f"opinion-run:{run.id}:proposal:{proposal.id}",
            run_id=run.id,
            proposal_db_id=proposal.id,
            spec=proposal_message_spec(proposal),
        )


async def _send_idempotent(
    *,
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    key: str,
    run_id: str,
    spec: TelegramMessageSpec,
    proposal_db_id: int | None = None,
) -> None:
    if settings.telegram_allowed_chat_id is None:
        raise ValueError("TELEGRAM_ALLOWED_CHAT_ID is required to send approval messages")
    existing = session.scalar(select(TelegramInteraction).where(TelegramInteraction.idempotency_key == key))
    if existing and existing.message_id is not None:
        return
    if existing and existing.status == "sending":
        existing.status = "uncertain"
        session.commit()
        return
    intent = existing or TelegramInteraction(
        direction="outbound",
        idempotency_key=key,
        opinion_run_id=run_id,
        opinion_proposal_id=proposal_db_id,
        chat_id=settings.telegram_allowed_chat_id,
        text=spec.text,
        raw=spec.model_dump(mode="json"),
        status="sending",
    )
    session.add(intent)
    session.commit()
    message_id = await telegram.send_message(settings.telegram_allowed_chat_id, spec)
    intent.message_id = message_id
    intent.status = "sent"
    session.add(intent)
    session.commit()


async def handle_telegram_update(
    *,
    session: Session,
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    update: dict[str, Any],
) -> str:
    update_id = update.get("update_id")
    if update_id is None:
        return "ignored"
    inbound = TelegramInteraction(direction="inbound", update_id=int(update_id), raw=update, status="received")
    try:
        session.add(inbound)
        session.flush()
    except IntegrityError:
        session.rollback()
        return "duplicate"

    if "callback_query" in update:
        result = await _handle_callback(session, settings, telegram, update["callback_query"], inbound)
    elif "message" in update:
        result = await _handle_message(session, settings, agent, telegram, update["message"], inbound)
    else:
        result = "ignored"
    session.commit()
    return result


async def _handle_callback(
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    callback: dict[str, Any],
    inbound: TelegramInteraction,
) -> str:
    callback_id = str(callback["id"])
    if session.scalar(select(TelegramInteraction).where(TelegramInteraction.callback_query_id == callback_id)):
        return "duplicate"
    message = callback.get("message") or {}
    chat_id = int((message.get("chat") or {}).get("id") or 0)
    inbound.callback_query_id = callback_id
    inbound.chat_id = chat_id
    inbound.message_id = message.get("message_id")
    inbound.text = callback.get("data")
    if not _allowed_chat(settings, chat_id):
        await telegram.answer_callback_query(callback_id, "Not allowed")
        return "forbidden"
    try:
        prefix, proposal_db_id, action = str(callback.get("data", "")).split(":", 2)
        proposal_key = int(proposal_db_id)
    except ValueError:
        await telegram.answer_callback_query(callback_id, "Unsupported action")
        return "ignored"
    if prefix != "prop":
        await telegram.answer_callback_query(callback_id, "Unsupported action")
        return "ignored"
    proposal = session.get(OpinionProposal, proposal_key)
    run = session.get(OpinionRun, proposal.opinion_run_id) if proposal else None
    if (
        proposal is None
        or run is None
        or run.status != RunStatus.AWAITING_USER.value
        or proposal.status != ProposalStatus.PENDING.value
        or proposal.batch != run.batch
    ):
        await telegram.answer_callback_query(callback_id, "This proposal is no longer pending")
        return "stale"
    if action == "approve":
        await telegram.answer_callback_query(callback_id, "Approved")
        return await approve_proposal(session=session, settings=settings, telegram=telegram, run=run, proposal=proposal)
    if action == "reject":
        await telegram.answer_callback_query(callback_id, "Rejected")
        return await reject_proposal(session=session, settings=settings, telegram=telegram, run=run, proposal=proposal)
    if action == "revise":
        await telegram.answer_callback_query(callback_id, "Reply with revision notes")
        return "awaiting_revision"
    await telegram.answer_callback_query(callback_id, "Unsupported action")
    return "ignored"


async def _handle_message(
    session: Session,
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    message: dict[str, Any],
    inbound: TelegramInteraction,
) -> str:
    chat_id = int((message.get("chat") or {}).get("id") or 0)
    inbound.chat_id = chat_id
    inbound.message_id = message.get("message_id")
    inbound.text = message.get("text")
    if not _allowed_chat(settings, chat_id):
        return "forbidden"
    feedback = (message.get("text") or "").strip()
    if not feedback:
        return "ignored"
    run = _find_run_for_message(session, message)
    if not run:
        return "no_pending_run"
    try:
        transition(run, RunStatus.REVISING)
        _supersede_pending_proposals(session, run)
        session.commit()
        previous_output = OpinionProposalOutput.model_validate(run.agent_output)
        context = build_read_context(settings, _run_dir(run, settings))
        output, resume_state = await agent.revise(
            run_id=run.id,
            feedback=feedback,
            previous_output=previous_output,
            context=context,
            settings=settings,
            resume_state=run.resume_state,
        )
        run.agent_output = output.model_dump(mode="json")
        run.resume_state = resume_state
        run.attempts += 1
        run.batch += 1
        _store_proposal_batch(session, settings, run, output)
        session.commit()
        if run.status == RunStatus.AWAITING_USER.value:
            await send_proposal_messages(session=session, settings=settings, telegram=telegram, run=run)
        return "revised"
    except Exception as exc:
        if run.status in NON_TERMINAL_RUN_STATUSES:
            transition(run, RunStatus.FAILED)
        run.failure_reason = str(exc)
        session.commit()
        raise


def _run_dir(run: OpinionRun, settings: Settings) -> Path:
    configured = (run.input_paths or {}).get("dir")
    return Path(configured) if configured else RunPaths(settings.runs_dir).active_run_dir(run.id)


def _selected_highlight_ids(run: OpinionRun, settings: Settings) -> set[str]:
    return {str(row["highlight_id"]) for row in read_jsonl(_run_dir(run, settings) / "selected-highlights.jsonl")}


def _supersede_pending_proposals(session: Session, run: OpinionRun) -> None:
    pending = session.scalars(
        select(OpinionProposal).where(
            OpinionProposal.opinion_run_id == run.id,
            OpinionProposal.status == ProposalStatus.PENDING.value,
        )
    )
    for proposal in pending:
        proposal.status = ProposalStatus.SUPERSEDED.value
        proposal.decided_at = utcnow()


async def approve_proposal(
    *,
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    run: OpinionRun,
    proposal: OpinionProposal,
) -> str:
    try:
        applied_opinion_id, commit_sha = _apply_proposal_files(settings, proposal)
        proposal.status = ProposalStatus.APPROVED.value
        proposal.applied_opinion_id = applied_opinion_id
        proposal.commit_sha = commit_sha
        proposal.decided_at = utcnow()
        _append_decision(settings, run, proposal, "approved")
        _complete_run_if_terminal(session, settings, run)
        session.commit()
        await _send_idempotent(
            session=session,
            settings=settings,
            telegram=telegram,
            key=f"opinion-run:{run.id}:proposal:{proposal.id}:result",
            run_id=run.id,
            proposal_db_id=proposal.id,
            spec=TelegramMessageSpec(
                text=f"Applied {proposal.proposal_id} ({proposal.kind}): commit {commit_sha or 'no changes'}"
            ),
        )
        return "applied"
    except (GitToolError, OSError, ValueError) as exc:
        if run.status in NON_TERMINAL_RUN_STATUSES:
            transition(run, RunStatus.FAILED)
        run.failure_reason = (
            f"failed to apply proposal {proposal.proposal_id}: {exc}. "
            f"Inspect {settings.opinions_repo_dir} and push or reset manually before abandoning the run."
        )
        session.commit()
        raise


async def reject_proposal(
    *,
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    run: OpinionRun,
    proposal: OpinionProposal,
) -> str:
    proposal.status = ProposalStatus.REJECTED.value
    proposal.decided_at = utcnow()
    _append_decision(settings, run, proposal, "rejected")
    _complete_run_if_terminal(session, settings, run)
    session.commit()
    return "rejected"


def _append_decision(settings: Settings, run: OpinionRun, proposal: OpinionProposal, decision: str) -> None:
    corpus = CorpusPaths(settings.opinions_data_dir)
    append_decisions(
        corpus,
        [
            OpinionDecision(
                proposal_id=proposal.proposal_id,
                run_id=run.id,
                decision=decision,
                kind=proposal.kind,
                opinion_id=proposal.applied_opinion_id or proposal.opinion_id,
                proposed_title=proposal.title,
                supporting_highlight_ids=list(proposal.supporting_highlight_ids or []),
                decided_at=iso_utc(utcnow()),
            )
        ],
    )


def _apply_proposal_files(settings: Settings, proposal: OpinionProposal) -> tuple[str | None, str | None]:
    """Apply one approved proposal to the opinions repo and commit only the allowed files."""
    ensure_opinions_repo(settings)
    # Assert cleanliness before ensure_repo_file: a missing file touched into existence
    # would otherwise read as dirty and block the first apply.
    assert_targets_clean(settings.opinions_repo_dir, [settings.opinions_target_file, settings.opinions_sources_file])
    target = ensure_repo_file(settings, settings.opinions_target_file)
    sources_path = ensure_repo_file(settings, settings.opinions_sources_file)

    corpus = CorpusPaths(settings.opinions_data_dir)
    highlights_by_id = {row.highlight_id: row for row in read_highlights(corpus)}
    supporting = list(proposal.supporting_highlight_ids or [])
    missing = [hid for hid in supporting if hid not in highlights_by_id]
    if missing:
        raise ValueError(f"unknown supporting highlight ids: {missing}")

    doc = load_opinions(target)
    sources = read_sources(sources_path)
    applied_opinion_id = proposal.opinion_id
    added_at = iso_utc(utcnow())

    def source_rows(opinion_id: str) -> list[dict[str, Any]]:
        return [
            {
                "opinion_id": opinion_id,
                "highlight_id": hid,
                "document_id": highlights_by_id[hid].document_id,
                "document_title": highlights_by_id[hid].document_title,
                "source_url": highlights_by_id[hid].source_url,
                "highlight_text": highlights_by_id[hid].text,
                "added_at": added_at,
            }
            for hid in supporting
        ]

    if proposal.kind == "add_opinion":
        # Include decision-log IDs so removing the highest-numbered opinion (which purges
        # its source rows) can never cause a stable ID to be reissued.
        decision_ids = {d.opinion_id for d in read_decisions(corpus) if d.opinion_id}
        existing_ids = (
            {opinion.opinion_id for opinion in doc.opinions} | {row["opinion_id"] for row in sources} | decision_ids
        )
        applied_opinion_id = next_opinion_id(existing_ids)
        doc = add_opinion(
            doc, opinion_id=applied_opinion_id, title=proposal.title or "", body=proposal.proposed_text or ""
        )
        sources = _merge_sources(sources, source_rows(applied_opinion_id))
    elif proposal.kind == "update_opinion":
        assert proposal.opinion_id is not None
        doc = update_opinion(
            doc, opinion_id=proposal.opinion_id, title=proposal.title, body=proposal.proposed_text or ""
        )
        sources = _merge_sources(sources, source_rows(proposal.opinion_id))
    elif proposal.kind == "remove_opinion":
        assert proposal.opinion_id is not None
        doc = remove_opinion(doc, opinion_id=proposal.opinion_id)
        sources = [row for row in sources if row["opinion_id"] != proposal.opinion_id]
    elif proposal.kind == "add_sources":
        assert proposal.opinion_id is not None
        doc.get(proposal.opinion_id)
        sources = _merge_sources(sources, source_rows(proposal.opinion_id))
    else:
        raise ValueError(f"unsupported proposal kind: {proposal.kind}")

    validate_opinions_files(doc, sources)
    write_text_atomic(target, doc.render())
    write_jsonl_atomic(sources_path, sources)
    result = commit_and_push_opinions_files(
        repo_dir=settings.opinions_repo_dir,
        target_files=[settings.opinions_target_file, settings.opinions_sources_file],
        branch=settings.opinions_repo_branch,
        author_name=settings.opinions_git_author_name,
        author_email=settings.opinions_git_author_email,
        message=f"chore: apply opinion proposal {proposal.proposal_id} ({proposal.kind})",
    )
    return applied_opinion_id, result.commit_sha


def _merge_sources(existing: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {(row["opinion_id"], row["highlight_id"]) for row in existing}
    merged = list(existing)
    for row in rows:
        if (row["opinion_id"], row["highlight_id"]) not in seen:
            merged.append(row)
            seen.add((row["opinion_id"], row["highlight_id"]))
    return merged


def _complete_run_if_terminal(session: Session, settings: Settings, run: OpinionRun) -> None:
    pending = session.scalar(
        select(func.count())
        .select_from(OpinionProposal)
        .where(
            OpinionProposal.opinion_run_id == run.id,
            OpinionProposal.status == ProposalStatus.PENDING.value,
        )
    )
    if pending:
        return
    transition(run, RunStatus.COMPLETED)
    _advance_workflow_cursor(settings, run)
    _finalize_run_artifacts(settings, run)


def _ensure_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; all stored timestamps are UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _advance_workflow_cursor(settings: Settings, run: OpinionRun) -> None:
    corpus = CorpusPaths(settings.opinions_data_dir)
    state = load_state(corpus)
    state.workflow.last_completed_window_start = iso_utc(_ensure_utc(run.window_start))
    state.workflow.last_completed_window_end = iso_utc(_ensure_utc(run.window_end))
    save_state(corpus, state)


def _finalize_run_artifacts(settings: Settings, run: OpinionRun) -> None:
    proposals = [
        {
            "proposal_id": proposal.proposal_id,
            "batch": proposal.batch,
            "kind": proposal.kind,
            "status": proposal.status,
            "opinion_id": proposal.applied_opinion_id or proposal.opinion_id,
            "commit_sha": proposal.commit_sha,
        }
        for proposal in sorted(run.proposals, key=lambda p: p.id)
    ]
    finalize_run_dir(
        RunPaths(settings.runs_dir),
        run.id,
        {
            "run_id": run.id,
            "status": run.status,
            "window_start": iso_utc(_ensure_utc(run.window_start)),
            "window_end": iso_utc(_ensure_utc(run.window_end)),
            "proposals": proposals,
        },
    )


def abandon_run(session: Session, settings: Settings, run: OpinionRun) -> None:
    """Explicitly abandon a pending run without advancing the workflow cursor."""
    transition(run, RunStatus.ABANDONED)
    _supersede_pending_proposals(session, run)
    _finalize_run_artifacts(settings, run)
    session.commit()


def _find_run_for_message(session: Session, message: dict[str, Any]) -> OpinionRun | None:
    """Revision feedback must be a reply to one of the pending run's proposal messages.

    Free text without a reply is ignored so a stray message cannot supersede a pending
    batch, and a reply to a completed run's message is never rerouted to the active run.
    """
    reply_to = (message.get("reply_to_message") or {}).get("message_id")
    if reply_to is None:
        return None
    outbound = session.scalar(
        select(TelegramInteraction).where(
            TelegramInteraction.direction == "outbound",
            TelegramInteraction.message_id == int(reply_to),
        )
    )
    if outbound and outbound.opinion_run_id:
        run = session.get(OpinionRun, outbound.opinion_run_id)
        if run and run.status == RunStatus.AWAITING_USER.value:
            return run
    return None


def _allowed_chat(settings: Settings, chat_id: int) -> bool:
    return settings.telegram_allowed_chat_id is not None and settings.telegram_allowed_chat_id == chat_id


def next_update_offset(session: Session) -> int | None:
    max_seen = session.scalar(select(func.max(TelegramInteraction.update_id)))
    return int(max_seen) + 1 if max_seen is not None else None
