from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opinions_agent.agent import AgentTurnOutput, OpinionAgent, TelegramMessageSpec, build_read_context
from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths, init_data_dirs, load_state, save_state
from opinions_agent.fsio import write_text_atomic
from opinions_agent.models import NON_TERMINAL_RUN_STATUSES, OpinionRun, RunStatus, TelegramInteraction, utcnow
from opinions_agent.reader import iso_utc, parse_iso
from opinions_agent.repo_checkout import ensure_opinions_repo, ensure_repo_file
from opinions_agent.selection import RunPaths, finalize_run_dir, select_run_highlights, write_run_bundle
from opinions_agent.tools.git_ops import assert_targets_clean, commit_and_push_opinions_files
from opinions_agent.validation import run_artifact_validation, update_opinion_id_high_water

DEFAULT_WINDOW = timedelta(days=7)


class TelegramSender(Protocol):
    async def send_message(self, chat_id: int, spec: TelegramMessageSpec) -> int: ...

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None: ...


class ActiveRunError(RuntimeError):
    pass


VALID_TRANSITIONS = {
    RunStatus.PENDING_AGENT.value: {RunStatus.RUNNING_AGENT.value, RunStatus.FAILED.value},
    RunStatus.RUNNING_AGENT.value: {
        RunStatus.AWAITING_USER.value,
        RunStatus.COMPLETED.value,
        RunStatus.BLOCKED.value,
        RunStatus.FAILED.value,
    },
    RunStatus.AWAITING_USER.value: {RunStatus.RUNNING_AGENT.value, RunStatus.FAILED.value, RunStatus.ABANDONED.value},
    RunStatus.COMPLETED.value: set(),
    RunStatus.BLOCKED.value: set(),
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
    run_id: str | None = None,
) -> OpinionRun | None:
    active = find_active_run(session)
    if active is not None:
        raise ActiveRunError(f"run {active.id} is still {active.status}; not starting another run")

    ensure_opinions_repo(settings)
    ensure_repo_file(settings, settings.opinions_target_file)
    ensure_repo_file(settings, settings.opinions_sources_file)
    assert_targets_clean(settings.opinions_repo_dir, [settings.opinions_target_file, settings.opinions_sources_file])

    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    start, end = _run_window(settings, window_start=window_start, window_end=window_end, now=now)
    highlights, documents = select_run_highlights(corpus, start, end)
    if not highlights:
        return None

    run_kwargs = {"id": run_id} if run_id is not None else {}
    run = OpinionRun(
        **run_kwargs,
        status=RunStatus.PENDING_AGENT.value,
        window_start=start,
        window_end=end,
        model=settings.harness_model,
        attempts=0,
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
        "review_summary_md": str(bundle.review_summary_md),
        "selected_highlights_jsonl": str(bundle.selected_highlights_jsonl),
        "selected_documents_jsonl": str(bundle.selected_documents_jsonl),
    }
    session.commit()

    try:
        await _run_agent_turn(
            session=session,
            settings=settings,
            agent=agent,
            telegram=telegram,
            run=run,
            prompt_fragment=None,
        )
        return run
    except Exception as exc:
        _fail_run(session, run, str(exc))
        raise


async def _run_agent_turn(
    *,
    session: Session,
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    run: OpinionRun,
    prompt_fragment: str | None,
) -> None:
    if run.status == RunStatus.PENDING_AGENT.value:
        transition(run, RunStatus.RUNNING_AGENT)
        session.commit()
    context = build_read_context(settings, _run_dir(run, settings))
    output, resume_state = await agent.run_turn(
        run_id=run.id,
        context=context,
        settings=settings,
        prompt_fragment=prompt_fragment,
        resume_state=run.resume_state,
    )
    run.agent_output = output.model_dump(mode="json")
    run.resume_state = resume_state
    run.turn_seq += 1
    run.attempts += 1
    if prompt_fragment is None and run.turn_seq == 1:
        _write_initial_telegram_review(_run_dir(run, settings), output)
    if output.status == "awaiting_user":
        transition(run, RunStatus.AWAITING_USER)
        session.commit()
        await send_agent_messages(session=session, settings=settings, telegram=telegram, run=run, output=output)
        return
    if output.status == "blocked":
        transition(run, RunStatus.BLOCKED)
        run.failure_reason = output.notes or "agent returned blocked"
        session.commit()
        await send_agent_messages(session=session, settings=settings, telegram=telegram, run=run, output=output)
        return
    if output.status == "done":
        session.commit()
        await _complete_done_run(session=session, settings=settings, telegram=telegram, run=run, output=output)
        return
    raise ValueError(f"unsupported agent status: {output.status}")


async def _complete_done_run(
    *,
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    run: OpinionRun,
    output: AgentTurnOutput,
) -> None:
    commit_boundary_finished = False
    try:
        validation = run_artifact_validation(settings=settings, run_dir=_run_dir(run, settings))
        commit = commit_and_push_opinions_files(
            repo_dir=settings.opinions_repo_dir,
            target_files=[settings.opinions_target_file, settings.opinions_sources_file],
            branch=settings.opinions_repo_branch,
            author_name=settings.opinions_git_author_name,
            author_email=settings.opinions_git_author_email,
            message=f"chore: complete opinion run {run.id}",
        )
        commit_boundary_finished = True
        update_opinion_id_high_water(settings, validation.high_water_mark)
        _advance_workflow_cursor(settings, run)
        _finalize_run_artifacts(
            settings,
            run,
            status=RunStatus.COMPLETED.value,
            commit_sha=commit.commit_sha,
            validation_summary=validation.summary,
        )
        transition(run, RunStatus.COMPLETED)
        session.commit()
        durability = f"commit {commit.commit_sha}" if commit.commit_sha else "no opinion file changes"
        final_output = AgentTurnOutput(
            status="done",
            telegram_messages=[
                message.model_copy(update={"text": f"{message.text}\n\nDurability: {durability}"})
                for message in output.telegram_messages
            ],
            notes=output.notes,
        )
        run.agent_output = final_output.model_dump(mode="json")
        session.commit()
        await send_agent_messages(session=session, settings=settings, telegram=telegram, run=run, output=final_output)
    except Exception as exc:
        _fail_run(session, run, str(exc))
        phase = "after commit/no-op handling" if commit_boundary_finished else "before commit"
        await send_agent_messages(
            session=session,
            settings=settings,
            telegram=telegram,
            run=run,
            output=AgentTurnOutput(
                status="blocked",
                telegram_messages=[TelegramMessageSpec(text=f"Opinion run failed {phase}: {exc}")],
            ),
        )
        raise


async def send_agent_messages(
    *,
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    run: OpinionRun,
    output: AgentTurnOutput | None = None,
) -> None:
    if output is None:
        output = AgentTurnOutput.model_validate(run.agent_output)
    for index, spec in enumerate(output.telegram_messages):
        await _send_idempotent(
            session=session,
            settings=settings,
            telegram=telegram,
            key=f"opinion-run:{run.id}:turn:{run.turn_seq}:message:{index}",
            run_id=run.id,
            spec=spec,
        )


def _write_initial_telegram_review(run_dir: Path, output: AgentTurnOutput) -> None:
    lines = ["# Initial Telegram Messages", ""]
    if not output.telegram_messages:
        lines.append("(No Telegram messages.)")
    for index, message in enumerate(output.telegram_messages, start=1):
        if index > 1:
            lines.extend(["", "---", ""])
        lines.extend([f"## Message {index}", "", message.text])
        if message.buttons:
            lines.extend(["", "Buttons: " + ", ".join(button.text for button in message.buttons)])
        if message.force_reply:
            lines.extend(["", "Force reply: yes"])
        if message.reply_to_message_id is not None:
            lines.extend(["", f"Reply to message: {message.reply_to_message_id}"])
    write_text_atomic(run_dir / "review" / "initial-telegram.md", "\n".join(lines).rstrip() + "\n")


async def _send_idempotent(
    *,
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    key: str,
    run_id: str,
    spec: TelegramMessageSpec,
) -> None:
    if settings.telegram_allowed_chat_id is None:
        raise ValueError("TELEGRAM_ALLOWED_CHAT_ID is required to send messages")
    existing = session.scalar(select(TelegramInteraction).where(TelegramInteraction.idempotency_key == key))
    if existing and existing.message_id is not None:
        return
    if existing and existing.status == "sending":
        existing.status = "uncertain"
        session.commit()
        return
    if existing and existing.status == "uncertain":
        result = session.execute(
            update(TelegramInteraction)
            .where(TelegramInteraction.id == existing.id, TelegramInteraction.status == "uncertain")
            .values(status="sending", updated_at=utcnow())
        )
        session.commit()
        if int(getattr(result, "rowcount", 0)) != 1:
            return
        session.refresh(existing)
    intent = existing or TelegramInteraction(
        direction="outbound",
        idempotency_key=key,
        opinion_run_id=run_id,
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
        result = await _handle_callback(session, settings, agent, telegram, update["callback_query"], inbound)
    elif "message" in update:
        result = await _handle_message(session, settings, agent, telegram, update["message"], inbound)
    else:
        result = "ignored"
    session.commit()
    return result


async def _handle_callback(
    session: Session,
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    callback: dict[str, Any],
    inbound: TelegramInteraction,
) -> str:
    callback_id = str(callback["id"])
    if session.scalar(select(TelegramInteraction).where(TelegramInteraction.callback_query_id == callback_id)):
        return "duplicate"
    message = callback.get("message") or {}
    chat_id = int((message.get("chat") or {}).get("id") or 0)
    message_id = message.get("message_id")
    data = str(callback.get("data") or "")
    inbound.callback_query_id = callback_id
    inbound.chat_id = chat_id
    inbound.message_id = message_id
    inbound.text = data
    if not _allowed_chat(settings, chat_id):
        await telegram.answer_callback_query(callback_id, "Not allowed")
        return "forbidden"
    outbound = _find_outbound_message(session, chat_id=chat_id, message_id=message_id)
    if outbound is None or outbound.opinion_run_id is None:
        await telegram.answer_callback_query(callback_id, "This message is no longer pending")
        return "stale"
    button_text = _button_text(outbound, data)
    if button_text is None:
        await telegram.answer_callback_query(callback_id, "Unsupported action")
        return "ignored"
    run = session.get(OpinionRun, outbound.opinion_run_id)
    if run is None or run.status != RunStatus.AWAITING_USER.value:
        await telegram.answer_callback_query(callback_id, "This run is no longer awaiting input")
        return "stale"
    _record_response(inbound, outbound, user_action=button_text, callback_data=data)
    await telegram.answer_callback_query(callback_id, button_text)
    if _current_turn_ready(session, run):
        return await _resume_from_telegram(
            session=session,
            settings=settings,
            agent=agent,
            telegram=telegram,
            run=run,
            prompt_fragment=_responses_prompt(session, run),
            result="resumed",
        )
    return "recorded"


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
    text = (message.get("text") or "").strip()
    if not text:
        return "ignored"
    active = find_active_run(session)
    if text in {"GO", "SKIP"} and active is not None and active.status == RunStatus.AWAITING_USER.value:
        return await _resume_from_telegram(
            session=session,
            settings=settings,
            agent=agent,
            telegram=telegram,
            run=active,
            prompt_fragment=f"Telegram command received.\n\nCommand:\n{text}",
            result=text.lower(),
        )

    reply_to = (message.get("reply_to_message") or {}).get("message_id")
    if reply_to is None:
        return "no_pending_run"
    outbound = _find_outbound_message(session, chat_id=chat_id, message_id=reply_to)
    if outbound is None or outbound.opinion_run_id is None:
        return "no_pending_run"
    run = session.get(OpinionRun, outbound.opinion_run_id)
    if run is None or run.status != RunStatus.AWAITING_USER.value:
        return "stale"
    _record_response(inbound, outbound, user_reply=text)
    if _current_turn_ready(session, run):
        return await _resume_from_telegram(
            session=session,
            settings=settings,
            agent=agent,
            telegram=telegram,
            run=run,
            prompt_fragment=_responses_prompt(session, run),
            result="resumed",
        )
    return "recorded"


async def _resume_from_telegram(
    *,
    session: Session,
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    run: OpinionRun,
    prompt_fragment: str,
    result: str,
) -> str:
    if not _claim_awaiting_run(session, run):
        return "already_resuming"
    try:
        await _run_agent_turn(
            session=session,
            settings=settings,
            agent=agent,
            telegram=telegram,
            run=run,
            prompt_fragment=prompt_fragment,
        )
        return result
    except Exception as exc:
        _fail_run(session, run, str(exc))
        raise


def _claim_awaiting_run(session: Session, run: OpinionRun) -> bool:
    result = session.execute(
        update(OpinionRun)
        .where(OpinionRun.id == run.id, OpinionRun.status == RunStatus.AWAITING_USER.value)
        .values(status=RunStatus.RUNNING_AGENT.value, updated_at=utcnow())
    )
    session.commit()
    if int(getattr(result, "rowcount", 0)) != 1:
        session.refresh(run)
        return False
    session.refresh(run)
    return True


def _find_outbound_message(session: Session, *, chat_id: int, message_id: int | None) -> TelegramInteraction | None:
    if message_id is None:
        return None
    return session.scalar(
        select(TelegramInteraction).where(
            TelegramInteraction.direction == "outbound",
            TelegramInteraction.chat_id == chat_id,
            TelegramInteraction.message_id == int(message_id),
            TelegramInteraction.status == "sent",
        )
    )


def _button_text(outbound: TelegramInteraction, callback_data: str) -> str | None:
    for button in outbound.raw.get("buttons", []):
        if button.get("callback_data") == callback_data:
            return str(button.get("text") or callback_data)
    return None


def _record_response(
    inbound: TelegramInteraction,
    outbound: TelegramInteraction,
    *,
    user_action: str | None = None,
    callback_data: str | None = None,
    user_reply: str | None = None,
) -> None:
    inbound.opinion_run_id = outbound.opinion_run_id
    inbound.status = "recorded"
    inbound.raw = {
        **(inbound.raw or {}),
        "in_response_to_message_id": outbound.message_id,
        "original_text": outbound.text,
        "buttons": outbound.raw.get("buttons", []),
        "user_action": user_action,
        "callback_data": callback_data,
        "user_reply": user_reply,
    }


def _current_turn_outbounds(session: Session, run: OpinionRun) -> list[TelegramInteraction]:
    prefix = f"opinion-run:{run.id}:turn:{run.turn_seq}:message:"
    return list(
        session.scalars(
            select(TelegramInteraction)
            .where(
                TelegramInteraction.direction == "outbound",
                TelegramInteraction.opinion_run_id == run.id,
                TelegramInteraction.idempotency_key.like(f"{prefix}%"),
            )
            .order_by(TelegramInteraction.id)
        )
    )


def _requires_response(outbound: TelegramInteraction) -> bool:
    return bool(outbound.raw.get("force_reply") or outbound.raw.get("buttons"))


def _responses_by_message(session: Session, run: OpinionRun) -> dict[int, TelegramInteraction]:
    responses = list(
        session.scalars(
            select(TelegramInteraction).where(
                TelegramInteraction.direction == "inbound",
                TelegramInteraction.opinion_run_id == run.id,
                TelegramInteraction.status == "recorded",
            )
        )
    )
    by_message: dict[int, TelegramInteraction] = {}
    for response in responses:
        original = (response.raw or {}).get("in_response_to_message_id")
        if original is not None:
            by_message.setdefault(int(original), response)
    return by_message


def _current_turn_ready(session: Session, run: OpinionRun) -> bool:
    expected = [outbound for outbound in _current_turn_outbounds(session, run) if _requires_response(outbound)]
    if not expected:
        return False
    responses = _responses_by_message(session, run)
    return all(outbound.message_id in responses for outbound in expected)


def _responses_prompt(session: Session, run: OpinionRun) -> str:
    responses = _responses_by_message(session, run)
    blocks = ["Telegram responses received."]
    for outbound in _current_turn_outbounds(session, run):
        if not _requires_response(outbound) or outbound.message_id not in responses:
            continue
        response = responses[outbound.message_id]
        blocks.extend(
            [
                "",
                f"Original Telegram message_id: {outbound.message_id}",
                "Original message text:",
                outbound.text or "",
                "",
            ]
        )
        if (response.raw or {}).get("user_action"):
            blocks.extend(["User action:", str(response.raw["user_action"])])
            blocks.extend(["Callback data:", str(response.raw.get("callback_data") or "")])
        if (response.raw or {}).get("buttons"):
            blocks.extend(["Buttons sent:", str(response.raw["buttons"])])
        if (response.raw or {}).get("user_reply"):
            blocks.extend(["User reply:", str(response.raw["user_reply"])])
    return "\n".join(blocks)


def _run_dir(run: OpinionRun, settings: Settings) -> Path:
    configured = (run.input_paths or {}).get("dir")
    return Path(configured) if configured else RunPaths(settings.runs_dir).active_run_dir(run.id)


def _ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _advance_workflow_cursor(settings: Settings, run: OpinionRun) -> None:
    corpus = CorpusPaths(settings.opinions_data_dir)
    state = load_state(corpus)
    state.workflow.last_completed_window_start = iso_utc(_ensure_utc(run.window_start))
    state.workflow.last_completed_window_end = iso_utc(_ensure_utc(run.window_end))
    save_state(corpus, state)


def _finalize_run_artifacts(
    settings: Settings,
    run: OpinionRun,
    *,
    status: str | None = None,
    commit_sha: str | None = None,
    validation_summary: str | None = None,
) -> None:
    finalize_run_dir(
        RunPaths(settings.runs_dir),
        run.id,
        {
            "run_id": run.id,
            "status": status or run.status,
            "window_start": iso_utc(_ensure_utc(run.window_start)),
            "window_end": iso_utc(_ensure_utc(run.window_end)),
            "turn_seq": run.turn_seq,
            "commit_sha": commit_sha,
            "validation": validation_summary,
        },
    )


def _fail_run(session: Session, run: OpinionRun, reason: str) -> None:
    if run.status in NON_TERMINAL_RUN_STATUSES:
        run.status = RunStatus.FAILED.value
    run.failure_reason = reason
    session.commit()


def abandon_run(session: Session, settings: Settings, run: OpinionRun) -> None:
    transition(run, RunStatus.ABANDONED)
    _finalize_run_artifacts(settings, run)
    session.commit()


def _allowed_chat(settings: Settings, chat_id: int) -> bool:
    return settings.telegram_allowed_chat_id is not None and settings.telegram_allowed_chat_id == chat_id


def next_update_offset(session: Session) -> int | None:
    max_seen = session.scalar(select(func.max(TelegramInteraction.update_id)))
    return int(max_seen) + 1 if max_seen is not None else None
