from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opinions_agent.agent import AgentTurnOutput, OpinionAgent, TelegramMessageSpec, build_read_context
from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths, init_data_dirs
from opinions_agent.diagnostics import log_operational_failure
from opinions_agent.fsio import write_text_atomic
from opinions_agent.models import (
    NON_TERMINAL_RUN_STATUSES,
    BatchStatus,
    CycleStatus,
    GitPhase,
    OpinionBatch,
    OpinionCycle,
    OpinionRun,
    RunStatus,
    TelegramInteraction,
    utcnow,
)
from opinions_agent.opinions_doc import load_opinions, parse_opinions, read_sources
from opinions_agent.reader import iso_utc
from opinions_agent.recovery import archive_and_restore_run, capture_run_baseline, file_hash
from opinions_agent.repo_checkout import ensure_opinions_repo, ensure_repo_file
from opinions_agent.selection import RunPaths, finalize_run_dir, select_run_highlights, write_run_bundle
from opinions_agent.tools.git_ops import (
    assert_targets_clean,
    commit_and_push_opinions_files,
    git_credential_env,
    run_git,
)
from opinions_agent.validation import run_artifact_validation, update_opinion_id_high_water

DEFAULT_WINDOW = timedelta(days=7)
LOGGER = logging.getLogger(__name__)


def _log_operational_failure(settings: Settings, run: OpinionRun, exc: Exception, phase: str) -> None:
    log_operational_failure(
        LOGGER,
        settings,
        exc,
        phase=phase,
        cycle_id=run.cycle_id or "none",
        batch=run.batch,
        run_id=run.id,
    )


class TelegramSender(Protocol):
    async def send_message(self, chat_id: int, spec: TelegramMessageSpec) -> int: ...

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None: ...

    async def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None: ...


class ActiveRunError(RuntimeError):
    pass


VALID_TRANSITIONS = {
    RunStatus.PENDING_AGENT.value: {RunStatus.RUNNING_AGENT.value, RunStatus.FAILED.value, RunStatus.ABANDONED.value},
    RunStatus.RUNNING_AGENT.value: {
        RunStatus.AWAITING_USER.value,
        RunStatus.COMPLETED.value,
        RunStatus.BLOCKED.value,
        RunStatus.FAILED.value,
        RunStatus.ABANDONED.value,
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
    return end - DEFAULT_WINDOW, end


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
        _log_operational_failure(settings, run, exc, "initial_turn")
        _fail_run(session, run, str(exc))
        await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=run)
        raise


async def start_materialized_opinion_run(
    *,
    session: Session,
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    batch: OpinionBatch,
) -> OpinionRun:
    """Start one queued cycle batch from its existing immutable bundle."""
    active = find_active_run(session)
    if active is not None:
        raise ActiveRunError(f"run {active.id} is still {active.status}; not starting another run")
    cycle = session.get(OpinionCycle, batch.cycle_id)
    if cycle is None:
        raise ValueError(f"cycle not found: {batch.cycle_id}")
    run = OpinionRun(
        status=RunStatus.PENDING_AGENT.value,
        window_start=cycle.window_start,
        window_end=cycle.window_end,
        model=settings.harness_model,
        attempts=0,
        cycle_id=cycle.id,
        batch=batch.batch_number,
        batch_count=cycle.batch_count,
        input_paths={
            "dir": batch.bundle_path,
            "review_summary_md": str(Path(batch.bundle_path) / "review" / "summary.md"),
            "selected_highlights_jsonl": str(Path(batch.bundle_path) / "selected-highlights.jsonl"),
            "selected_documents_jsonl": str(Path(batch.bundle_path) / "selected-documents.jsonl"),
        },
    )
    session.add(run)
    session.flush()
    batch.latest_run_id = run.id
    batch.status = BatchStatus.RUNNING.value
    session.commit()
    try:
        ensure_opinions_repo(settings)
        ensure_repo_file(settings, settings.opinions_target_file)
        ensure_repo_file(settings, settings.opinions_sources_file)
        capture_run_baseline(settings, run, Path(batch.bundle_path))
        session.commit()
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
        _log_operational_failure(settings, run, exc, "cycle_setup_or_turn")
        _fail_run(session, run, str(exc), settings=settings)
        await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=run)
        raise


async def run_pending_opinion_run(
    *,
    session: Session,
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    run: OpinionRun,
) -> None:
    if run.status != RunStatus.PENDING_AGENT.value:
        raise ValueError(f"run {run.id} is not pending")
    try:
        await _run_agent_turn(
            session=session,
            settings=settings,
            agent=agent,
            telegram=telegram,
            run=run,
            prompt_fragment=None,
        )
    except Exception as exc:
        _log_operational_failure(settings, run, exc, "pending_turn")
        _fail_run(session, run, str(exc), settings=settings)
        await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=run)
        raise


def complete_reconciled_run(session: Session, settings: Settings, run: OpinionRun) -> None:
    """Complete database and cycle state after recovery confirms the remote commit."""
    if run.git_phase != GitPhase.PUSHED.value:
        raise ValueError("run is not durably pushed")
    validation = run_artifact_validation(settings=settings, run_dir=_run_dir(run, settings))
    update_opinion_id_high_water(settings, validation.high_water_mark)
    run.decision_log_hash = file_hash(CorpusPaths(settings.opinions_data_dir).decisions_jsonl)
    if run.cycle_id:
        _complete_cycle_batch(session, settings, run, run.git_result_sha, validation.summary)
    else:
        _finalize_run_artifacts(
            settings,
            run,
            status=RunStatus.COMPLETED.value,
            commit_sha=run.git_result_sha,
            validation_summary=validation.summary,
        )
    run.status = RunStatus.COMPLETED.value
    run.git_phase = GitPhase.COMPLETED.value
    run.lease_owner = None
    run.lease_expires_at = None
    session.commit()


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
        run.lease_owner = uuid4().hex
        run.lease_expires_at = utcnow() + timedelta(minutes=15)
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
        run.lease_owner = None
        run.lease_expires_at = None
        _set_batch_status(session, run, BatchStatus.AWAITING_USER)
        session.commit()
        await send_agent_messages(session=session, settings=settings, telegram=telegram, run=run, output=output)
        return
    if output.status == "blocked":
        transition(run, RunStatus.BLOCKED)
        run.lease_owner = None
        run.lease_expires_at = None
        run.failure_reason = output.notes or "agent returned blocked"
        _stop_cycle(session, run, "agent_blocked", "The opinion agent needs manual intervention.")
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
        fallback_summary = _completion_summary(settings)
        run.git_phase = GitPhase.COMMIT_INTENT.value
        session.commit()
        commit = commit_and_push_opinions_files(
            repo_dir=settings.opinions_repo_dir,
            target_files=[settings.opinions_target_file, settings.opinions_sources_file],
            branch=settings.opinions_repo_branch,
            author_name=settings.opinions_git_author_name,
            author_email=settings.opinions_git_author_email,
            message=f"chore: complete opinion run {run.id}",
            push=False,
            git_token=settings.opinions_git_token,
        )
        run.git_result_sha = commit.commit_sha
        run.git_phase = GitPhase.COMMITTED.value
        session.commit()
        if commit.commit_sha:
            run_git(
                settings.opinions_repo_dir,
                "push",
                "origin",
                settings.opinions_repo_branch,
                env=git_credential_env(settings.opinions_git_token),
            )
        run.git_phase = GitPhase.PUSHED.value
        session.commit()
        commit_boundary_finished = True
        durability = f"commit {commit.commit_sha}" if commit.commit_sha else "no opinion file changes"
        final_messages = output.telegram_messages or [TelegramMessageSpec(text=fallback_summary)]
        final_output = AgentTurnOutput(
            status="done",
            telegram_messages=[
                message.model_copy(update={"text": f"{message.text}\n\nDurability: {durability}"})
                for message in final_messages
            ],
            notes=output.notes,
        )
        run.agent_output = final_output.model_dump(mode="json")
        update_opinion_id_high_water(settings, validation.high_water_mark)
        run.decision_log_hash = file_hash(CorpusPaths(settings.opinions_data_dir).decisions_jsonl)
        if run.cycle_id:
            _complete_cycle_batch(session, settings, run, commit.commit_sha, validation.summary)
        else:
            _finalize_run_artifacts(
                settings,
                run,
                status=RunStatus.COMPLETED.value,
                commit_sha=commit.commit_sha,
                validation_summary=validation.summary,
            )
        transition(run, RunStatus.COMPLETED)
        run.lease_owner = None
        run.lease_expires_at = None
        run.git_phase = GitPhase.COMPLETED.value
        session.commit()
    except Exception as exc:
        _log_operational_failure(settings, run, exc, "commit")
        _fail_run(session, run, str(exc), settings=settings)
        if run.cycle_id:
            await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=run)
        else:
            phase = "after commit handling" if commit_boundary_finished else "before commit"
            await send_agent_messages(
                session=session,
                settings=settings,
                telegram=telegram,
                run=run,
                output=AgentTurnOutput(
                    status="blocked",
                    telegram_messages=[TelegramMessageSpec(text=f"Opinion run failed {phase}.")],
                ),
            )
        raise
    try:
        await send_agent_messages(session=session, settings=settings, telegram=telegram, run=run, output=final_output)
    except Exception as exc:
        _log_operational_failure(settings, run, exc, "final_telegram")


def _completion_summary(settings: Settings) -> str:
    baseline_doc = parse_opinions(run_git(settings.opinions_repo_dir, "show", f"HEAD:{settings.opinions_target_file}"))
    current_doc = load_opinions(settings.opinions_target_path)
    baseline_by_id = {opinion.opinion_id: opinion for opinion in baseline_doc.opinions}
    current_by_id = {opinion.opinion_id: opinion for opinion in current_doc.opinions}

    added = len(set(current_by_id) - set(baseline_by_id))
    removed = len(set(baseline_by_id) - set(current_by_id))
    updated = sum(
        1
        for opinion_id in set(current_by_id) & set(baseline_by_id)
        if current_by_id[opinion_id] != baseline_by_id[opinion_id]
    )
    evidence_changed = _source_row_change_count(
        _source_rows_from_git(settings),
        read_sources(settings.opinions_sources_path),
    )
    return (
        f"Done: {added} opinions added, {updated} opinions updated, {removed} opinions removed, "
        f"and {evidence_changed} evidence rows changed."
    )


def _source_rows_from_git(settings: Settings) -> list[dict[str, Any]]:
    text = run_git(settings.opinions_repo_dir, "show", f"HEAD:{settings.opinions_sources_file}")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _source_row_change_count(baseline_rows: list[dict[str, Any]], current_rows: list[dict[str, Any]]) -> int:
    baseline_by_key = {_source_row_key(row): row for row in baseline_rows}
    current_by_key = {_source_row_key(row): row for row in current_rows}
    added = set(current_by_key) - set(baseline_by_key)
    removed = set(baseline_by_key) - set(current_by_key)
    updated = {
        key
        for key in set(current_by_key) & set(baseline_by_key)
        if _canonical_source_row(current_by_key[key]) != _canonical_source_row(baseline_by_key[key])
    }
    return len(added) + len(removed) + len(updated)


def _source_row_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("opinion_id")), str(row.get("evidence_id")))


def _canonical_source_row(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"))


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


async def send_cycle_failure_notice(
    *,
    session: Session,
    settings: Settings,
    telegram: TelegramSender,
    run: OpinionRun,
) -> None:
    if not run.cycle_id:
        return
    cycle = session.get(OpinionCycle, run.cycle_id)
    code = cycle.failure_code if cycle and cycle.failure_code else "run_failed"
    await _send_idempotent(
        session=session,
        settings=settings,
        telegram=telegram,
        key=f"opinion-cycle:{run.cycle_id}:batch:{run.batch}:stopped:{code}",
        run_id=run.id,
        spec=TelegramMessageSpec(
            text=(
                f"Opinion cycle {run.cycle_id} stopped at batch {run.batch}. "
                f"Failure code: {code}. Retry with: opinions-agent retry-cycle {run.cycle_id}"
            )
        ),
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
        await _answer_callback_query_best_effort(telegram, callback_id, "Not allowed")
        return "forbidden"
    if message_id is None:
        await _answer_callback_query_best_effort(telegram, callback_id, "This message is no longer pending")
        return "stale"
    outbound = _find_outbound_message(session, chat_id=chat_id, message_id=message_id)
    if outbound is None or outbound.opinion_run_id is None:
        await _answer_callback_query_best_effort(telegram, callback_id, "This message is no longer pending")
        return "stale"
    button_text = _button_text(outbound, data)
    if button_text is None:
        await _answer_callback_query_best_effort(telegram, callback_id, "Unsupported action")
        return "ignored"
    run = session.get(OpinionRun, outbound.opinion_run_id)
    if run is None or run.status != RunStatus.AWAITING_USER.value:
        await _answer_callback_query_best_effort(telegram, callback_id, "This run is no longer awaiting input")
        return "stale"
    _record_response(inbound, outbound, user_action=button_text, callback_data=data)
    await _answer_callback_query_best_effort(telegram, callback_id, button_text)
    await telegram.edit_message_text(
        chat_id,
        message_id,
        _addressed_message_text(outbound.text or "", button_text),
    )
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


async def _answer_callback_query_best_effort(
    telegram: TelegramSender, callback_query_id: str, text: str | None = None
) -> None:
    try:
        await telegram.answer_callback_query(callback_query_id, text)
    except Exception:
        pass


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
    await telegram.edit_message_text(
        chat_id,
        int(reply_to),
        _addressed_message_text(outbound.text or "", "Reply received"),
    )
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
        _log_operational_failure(settings, run, exc, "resume_turn")
        _fail_run(session, run, str(exc), settings=settings)
        await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=run)
        raise


def _claim_awaiting_run(session: Session, run: OpinionRun) -> bool:
    now = utcnow()
    result = session.execute(
        update(OpinionRun)
        .where(OpinionRun.id == run.id, OpinionRun.status == RunStatus.AWAITING_USER.value)
        .values(
            status=RunStatus.RUNNING_AGENT.value,
            lease_owner=uuid4().hex,
            lease_expires_at=now + timedelta(minutes=15),
            updated_at=now,
        )
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


def _addressed_message_text(original_text: str, button_text: str) -> str:
    lines = original_text.splitlines()
    if not lines:
        return _status_line(button_text)
    first = lines[0].strip()
    if first.startswith("<b>") and first.endswith("</b>"):
        title = first.removeprefix("<b>").removesuffix("</b>")
    else:
        title = first
    lines[0] = f"<b>{_status_label(button_text)} - {title}</b>"
    return "\n".join(lines)


def _status_line(button_text: str) -> str:
    return f"<b>{_status_label(button_text)}</b>"


def _status_label(button_text: str) -> str:
    normalized = button_text.strip().lower()
    if normalized == "approve":
        return "✅ Approved"
    if normalized == "reject":
        return "❌ Rejected"
    if normalized == "reply received":
        return "💬 Reply received"
    return f"Addressed: {button_text}"


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
    blocks = [
        "Telegram responses received.",
        "",
        "Interpretation rules:",
        "- Approve button callbacks are approval for that proposal.",
        "- Reject button callbacks are rejection for that proposal.",
        "- Free-text replies are contextual feedback, not approval. They may request revision, ask for more context, "
        "or explain rejection.",
        "- If a free-text reply asks for changed wording or otherwise modifies a proposal, send a revised proposal "
        "with fresh Approve and Reject buttons before making durable opinion edits.",
        "- Never infer approval from a free-text reply.",
    ]
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
    if configured:
        path = Path(configured)
        if path.exists() or not run.cycle_id:
            return path
    if run.cycle_id:
        return settings.runs_dir / "completed" / run.cycle_id / "batches" / str(run.batch)
    return RunPaths(settings.runs_dir).active_run_dir(run.id)


def _ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


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


def _fail_run(session: Session, run: OpinionRun, reason: str, *, settings: Settings | None = None) -> None:
    if (
        settings is not None
        and run.git_phase not in {GitPhase.COMMITTED.value, GitPhase.PUSHED.value, GitPhase.COMPLETED.value}
        and (_run_dir(run, settings) / "recovery" / run.id / "baseline").is_dir()
    ):
        archive_and_restore_run(settings, run, _run_dir(run, settings))
    if run.status in NON_TERMINAL_RUN_STATUSES:
        run.status = RunStatus.FAILED.value
    run.failure_reason = "run_failed" if run.cycle_id else reason
    _stop_cycle(session, run, "run_failed", "The opinion run stopped and needs recovery.")
    session.commit()


def _set_batch_status(session: Session, run: OpinionRun, status: BatchStatus) -> None:
    if not run.cycle_id:
        return
    batch = session.scalar(
        select(OpinionBatch).where(
            OpinionBatch.cycle_id == run.cycle_id,
            OpinionBatch.batch_number == run.batch,
        )
    )
    if batch is not None:
        batch.status = status.value


def _stop_cycle(session: Session, run: OpinionRun, code: str, summary: str) -> None:
    if not run.cycle_id:
        return
    cycle = session.get(OpinionCycle, run.cycle_id)
    if cycle is not None:
        cycle.status = CycleStatus.STOPPED.value
        cycle.failure_code = code
        cycle.failure_summary = summary
    _set_batch_status(session, run, BatchStatus.STOPPED)


def _complete_cycle_batch(
    session: Session,
    settings: Settings,
    run: OpinionRun,
    commit_sha: str | None,
    validation_summary: str,
) -> None:
    from opinions_agent.cycles import complete_cycle_directory
    from opinions_agent.fsio import write_json_atomic

    if not run.cycle_id:
        return
    cycle = session.get(OpinionCycle, run.cycle_id)
    batch = session.scalar(
        select(OpinionBatch).where(
            OpinionBatch.cycle_id == run.cycle_id,
            OpinionBatch.batch_number == run.batch,
        )
    )
    if cycle is None or batch is None:
        raise ValueError("cycle batch state is missing")
    batch.status = BatchStatus.COMPLETED.value
    batch.successful_run_id = run.id
    run_dir = _run_dir(run, settings)
    batch.bundle_path = str(run_dir)
    write_json_atomic(
        run_dir / "final.json",
        {
            "run_id": run.id,
            "status": RunStatus.COMPLETED.value,
            "commit_sha": commit_sha,
            "validation": validation_summary,
        },
    )
    next_batch = session.scalar(
        select(OpinionBatch).where(
            OpinionBatch.cycle_id == cycle.id,
            OpinionBatch.batch_number == run.batch + 1,
        )
    )
    if next_batch is not None:
        next_batch.status = BatchStatus.QUEUED.value
        cycle.current_batch = next_batch.batch_number
        session.commit()
        return
    cycle.status = CycleStatus.COMPLETED.value
    cycle.current_batch = cycle.batch_count
    cycle.failure_code = None
    cycle.failure_summary = None
    session.commit()
    completed_dir = complete_cycle_directory(settings, cycle.id)
    for stored_batch in session.scalars(select(OpinionBatch).where(OpinionBatch.cycle_id == cycle.id)):
        stored_batch.bundle_path = str(completed_dir / "batches" / str(stored_batch.batch_number))
    session.commit()


def abandon_run(session: Session, settings: Settings, run: OpinionRun) -> None:
    if run.cycle_id and run.git_phase in {GitPhase.COMMITTED.value, GitPhase.PUSHED.value}:
        raise ValueError("reconcile the recorded commit before abandoning this run")
    transition(run, RunStatus.ABANDONED)
    if run.cycle_id:
        archive_and_restore_run(settings, run, _run_dir(run, settings))
        _stop_cycle(session, run, "run_abandoned", "The interrupted run was abandoned. Retry the stored batch.")
        run.failure_reason = "run_abandoned"
        session.commit()
        return
    _finalize_run_artifacts(settings, run)
    session.commit()


def _allowed_chat(settings: Settings, chat_id: int) -> bool:
    return settings.telegram_allowed_chat_id is not None and settings.telegram_allowed_chat_id == chat_id


def next_update_offset(session: Session) -> int | None:
    max_seen = session.scalar(select(func.max(TelegramInteraction.update_id)))
    return int(max_seen) + 1 if max_seen is not None else None
