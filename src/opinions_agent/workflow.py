from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import Select, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opinions_agent.agent import AgentOutput, SummaryAgent, TelegramMessageSpec
from opinions_agent.config import Settings
from opinions_agent.highlight_export import export_run_bundle
from opinions_agent.models import (
    BLOCKING_SELECTION_STATUSES,
    ReadwiseHighlight,
    RunStatus,
    SummaryRun,
    SummaryRunHighlight,
    TelegramInteraction,
)
from opinions_agent.repo_checkout import ensure_opinions_repo, ensure_target_file, resolve_target_path
from opinions_agent.tools.git_ops import GitToolError, assert_target_clean, commit_and_push_opinions_file


class TelegramSender(Protocol):
    async def send_message(self, chat_id: int, spec: TelegramMessageSpec) -> int: ...

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None: ...


VALID_TRANSITIONS = {
    RunStatus.PENDING_AGENT.value: {RunStatus.AWAITING_USER.value, RunStatus.FAILED.value},
    RunStatus.AWAITING_USER.value: {
        RunStatus.REVISING.value,
        RunStatus.APPROVED.value,
        RunStatus.REJECTED.value,
        RunStatus.FAILED.value,
    },
    RunStatus.REVISING.value: {RunStatus.AWAITING_USER.value, RunStatus.FAILED.value},
    RunStatus.APPROVED.value: {RunStatus.COMMITTING.value, RunStatus.FAILED.value},
    RunStatus.COMMITTING.value: {RunStatus.COMMITTED.value, RunStatus.FAILED.value},
    RunStatus.COMMITTED.value: set(),
    RunStatus.REJECTED.value: set(),
    RunStatus.FAILED.value: set(),
}


def transition(run: SummaryRun, next_status: RunStatus) -> None:
    allowed = VALID_TRANSITIONS[run.status]
    if next_status.value not in allowed:
        raise ValueError(f"invalid summary run transition: {run.status} -> {next_status.value}")
    run.status = next_status.value


def select_unsummarized_highlights(session: Session, limit: int) -> list[ReadwiseHighlight]:
    blocking = (
        select(SummaryRunHighlight.readwise_highlight_id)
        .join(SummaryRun, SummaryRun.id == SummaryRunHighlight.summary_run_id)
        .where(SummaryRun.status.in_(BLOCKING_SELECTION_STATUSES))
    )
    query: Select[tuple[ReadwiseHighlight]] = (
        select(ReadwiseHighlight)
        .where(ReadwiseHighlight.id.not_in(blocking))
        .order_by(ReadwiseHighlight.highlighted_at.desc().nullslast(), ReadwiseHighlight.id.desc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(session.scalars(query))


def acquire_summary_selection_lock(session: Session) -> None:
    if session.bind and session.bind.dialect.name == "postgresql":
        session.execute(text("select pg_advisory_xact_lock(730914184)"))


async def summarize_recent(
    *,
    session: Session,
    settings: Settings,
    agent: SummaryAgent,
    telegram: TelegramSender,
    limit: int,
) -> SummaryRun | None:
    acquire_summary_selection_lock(session)
    highlights = select_unsummarized_highlights(session, limit)
    if not highlights:
        return None

    run = SummaryRun(status=RunStatus.PENDING_AGENT.value, model=settings.harness_model, attempts=1)
    session.add(run)
    session.flush()
    session.add_all(
        [SummaryRunHighlight(summary_run_id=run.id, readwise_highlight_id=highlight.id) for highlight in highlights]
    )
    input_paths = export_run_bundle(run, highlights, settings.runs_dir)
    run.input_paths = input_paths
    session.commit()

    try:
        target_file = resolve_target_path(settings)
        output, resume_state = await agent.propose(
            run_id=run.id,
            input_paths=input_paths,
            target_file=target_file,
            settings=settings,
        )
        run.summary_text = output.revised_summary
        run.agent_output = output.model_dump(mode="json")
        run.resume_state = resume_state
        transition(run, RunStatus.AWAITING_USER)
        session.commit()
        await send_agent_messages(
            session=session,
            settings=settings,
            telegram=telegram,
            run=run,
            output=output,
            purpose="proposal",
        )
        session.commit()
        return run
    except Exception as exc:
        transition(run, RunStatus.FAILED)
        run.failure_reason = str(exc)
        session.commit()
        raise


async def send_agent_messages(
    *,
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    run: SummaryRun,
    output: AgentOutput,
    purpose: str = "message",
) -> None:
    if settings.telegram_allowed_chat_id is None:
        raise ValueError("TELEGRAM_ALLOWED_CHAT_ID is required to send approval messages")
    for index, spec in enumerate(output.telegram_messages):
        key = f"summary-run:{run.id}:{purpose}:{index}"
        existing = session.scalar(select(TelegramInteraction).where(TelegramInteraction.idempotency_key == key))
        if existing and existing.message_id is not None:
            continue
        if existing and existing.status == "sending":
            existing.status = "uncertain"
            continue
        intent = existing or TelegramInteraction(
            direction="outbound",
            idempotency_key=key,
            summary_run_id=run.id,
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
    agent: SummaryAgent,
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
        prefix, run_id, action = str(callback.get("data", "")).split(":", 2)
    except ValueError:
        await telegram.answer_callback_query(callback_id, "Unsupported action")
        return "ignored"
    if prefix != "run":
        await telegram.answer_callback_query(callback_id, "Unsupported action")
        return "ignored"
    run = session.get(SummaryRun, run_id)
    if not run or run.status not in {RunStatus.AWAITING_USER.value, RunStatus.REVISING.value}:
        await telegram.answer_callback_query(callback_id, "This run is no longer pending")
        return "stale"
    if action == "approve":
        await telegram.answer_callback_query(callback_id, "Approved")
        return await approve_run(session=session, settings=settings, telegram=telegram, run=run)
    if action == "reject":
        transition(run, RunStatus.REJECTED)
        await telegram.answer_callback_query(callback_id, "Rejected")
        return "rejected"
    if action == "revise":
        await telegram.answer_callback_query(callback_id, "Reply with revision notes")
        return "awaiting_revision"
    await telegram.answer_callback_query(callback_id, "Unsupported action")
    return "ignored"


async def _handle_message(
    session: Session,
    settings: Settings,
    agent: SummaryAgent,
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
    text = (message.get("text") or "").strip()
    if not text:
        return "ignored"
    run = _find_run_for_message(session, message)
    if not run:
        return "no_pending_run"
    try:
        transition(run, RunStatus.REVISING)
        session.commit()
        output, resume_state = await agent.revise(
            run_id=run.id,
            current_summary=run.summary_text or "",
            feedback=text,
            input_paths=run.input_paths,
            target_file=resolve_target_path(settings),
            settings=settings,
            resume_state=run.resume_state,
        )
        run.summary_text = output.revised_summary or run.summary_text
        run.agent_output = output.model_dump(mode="json")
        run.resume_state = resume_state
        run.attempts += 1
        transition(run, RunStatus.AWAITING_USER)
        session.commit()
        await send_agent_messages(
            session=session,
            settings=settings,
            telegram=telegram,
            run=run,
            output=output,
            purpose=f"revision:{inbound.update_id}",
        )
        return "revised"
    except Exception as exc:
        if run.status != RunStatus.FAILED.value:
            transition(run, RunStatus.FAILED)
        run.failure_reason = str(exc)
        session.commit()
        raise


async def approve_run(
    *,
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    run: SummaryRun,
) -> str:
    if run.status not in {RunStatus.AWAITING_USER.value, RunStatus.REVISING.value}:
        return "stale"
    try:
        ensure_opinions_repo(settings)
        if run.status == RunStatus.REVISING.value:
            transition(run, RunStatus.AWAITING_USER)
        transition(run, RunStatus.APPROVED)
        session.commit()
        transition(run, RunStatus.COMMITTING)
        session.commit()
        assert_target_clean(settings.opinions_repo_dir, settings.opinions_target_file)
        target = ensure_target_file(settings)
        _append_summary(target, run)
        result = commit_and_push_opinions_file(
            repo_dir=settings.opinions_repo_dir,
            target_file=settings.opinions_target_file,
            branch=settings.opinions_repo_branch,
            author_name=settings.opinions_git_author_name,
            author_email=settings.opinions_git_author_email,
        )
        run.commit_sha = result.commit_sha
        transition(run, RunStatus.COMMITTED)
        output = AgentOutput(
            status="committed",
            commit_sha=result.commit_sha,
            revised_summary=run.summary_text,
            telegram_messages=[
                TelegramMessageSpec(text=f"Committed summary for run {run.id}: {result.commit_sha or 'no changes'}")
            ],
        )
        run.agent_output = output.model_dump(mode="json")
        session.commit()
        try:
            await send_agent_messages(
                session=session,
                settings=settings,
                telegram=telegram,
                run=run,
                output=output,
                purpose="commit",
            )
        except Exception as exc:
            run.failure_reason = f"committed but failed to send confirmation: {exc}"
            session.commit()
        return "committed"
    except (GitToolError, OSError, ValueError) as exc:
        if run.status != RunStatus.FAILED.value:
            transition(run, RunStatus.FAILED)
        run.failure_reason = str(exc)
        session.commit()
        raise


def _append_summary(target: Path, run: SummaryRun) -> None:
    summary = (run.summary_text or "").strip()
    if not summary:
        raise ValueError("cannot approve an empty summary")
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    target.write_text(f"{existing}{prefix}\n## Readwise Summary {run.id}\n\n{summary}\n", encoding="utf-8")


def _find_run_for_message(session: Session, message: dict[str, Any]) -> SummaryRun | None:
    reply_to = (message.get("reply_to_message") or {}).get("message_id")
    if reply_to is not None:
        outbound = session.scalar(
            select(TelegramInteraction).where(
                TelegramInteraction.direction == "outbound",
                TelegramInteraction.message_id == int(reply_to),
            )
        )
        if outbound and outbound.summary_run_id:
            run = session.get(SummaryRun, outbound.summary_run_id)
            if run and run.status in {RunStatus.AWAITING_USER.value, RunStatus.REVISING.value}:
                return run
    pending = list(
        session.scalars(
            select(SummaryRun)
            .where(SummaryRun.status.in_([RunStatus.AWAITING_USER.value, RunStatus.REVISING.value]))
            .order_by(SummaryRun.created_at.desc())
            .limit(2)
        )
    )
    if len(pending) == 1:
        return pending[0]
    return None


def _allowed_chat(settings: Settings, chat_id: int) -> bool:
    return settings.telegram_allowed_chat_id is not None and settings.telegram_allowed_chat_id == chat_id


def next_update_offset(session: Session) -> int | None:
    max_seen = session.scalar(select(func.max(TelegramInteraction.update_id)))
    return int(max_seen) + 1 if max_seen is not None else None
