"""Single-replica cycle worker and startup reconciliation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from opinions_agent.agent import OpinionAgent
from opinions_agent.config import Settings
from opinions_agent.models import BatchStatus, CycleStatus, OpinionBatch, OpinionCycle, OpinionRun, RunStatus
from opinions_agent.recovery import archive_and_restore_run, reconcile_git_durability
from opinions_agent.workflow import (
    TelegramSender,
    complete_reconciled_run,
    run_pending_opinion_run,
    start_materialized_opinion_run,
)


def reconcile_startup(session: Session, settings: Settings) -> list[OpinionRun]:
    """Reconcile durable commit phases and stop unsafe interrupted model calls."""
    now = datetime.now(UTC)
    stopped: list[OpinionRun] = []
    running = list(session.scalars(select(OpinionRun).where(OpinionRun.status == RunStatus.RUNNING_AGENT.value)))
    for run in running:
        if reconcile_git_durability(settings, run):
            complete_reconciled_run(session, settings, run)
            continue
        if run.lease_expires_at is None or _utc(run.lease_expires_at) > now:
            continue
        archive_and_restore_run(settings, run, _run_dir(run, settings))
        run.status = RunStatus.FAILED.value
        run.failure_reason = "interrupted_agent"
        if run.cycle_id:
            cycle = session.get(OpinionCycle, run.cycle_id)
            if cycle is not None:
                cycle.status = CycleStatus.STOPPED.value
                cycle.failure_code = "interrupted_agent"
                cycle.failure_summary = "The model call was interrupted. Retry the stored batch."
            batch = _batch_for_run(session, run)
            if batch is not None:
                batch.status = BatchStatus.STOPPED.value
        stopped.append(run)
    session.commit()
    return stopped


async def process_queued_once(
    session: Session,
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
) -> bool:
    pending_run = session.scalar(
        select(OpinionRun).where(OpinionRun.status == RunStatus.PENDING_AGENT.value).order_by(OpinionRun.created_at)
    )
    if pending_run is not None:
        await run_pending_opinion_run(
            session=session,
            settings=settings,
            agent=agent,
            telegram=telegram,
            run=pending_run,
        )
        return True
    active = session.scalar(
        select(OpinionRun).where(
            OpinionRun.status.in_(
                [RunStatus.RUNNING_AGENT.value, RunStatus.AWAITING_USER.value, RunStatus.PENDING_AGENT.value]
            )
        )
    )
    if active is not None:
        return False
    batch = session.scalar(
        select(OpinionBatch)
        .join(OpinionCycle, OpinionCycle.id == OpinionBatch.cycle_id)
        .where(
            OpinionBatch.status == BatchStatus.QUEUED.value,
            OpinionCycle.status == CycleStatus.ACTIVE.value,
            OpinionBatch.batch_number == OpinionCycle.current_batch,
        )
        .order_by(OpinionCycle.created_at, OpinionBatch.batch_number)
    )
    if batch is None:
        return False
    await start_materialized_opinion_run(
        session=session,
        settings=settings,
        agent=agent,
        telegram=telegram,
        batch=batch,
    )
    return True


async def worker_loop(
    SessionLocal: sessionmaker[Session],
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        with SessionLocal() as session:
            try:
                worked = await process_queued_once(session, settings, agent, telegram)
            except Exception:
                session.rollback()
                worked = False
        if not worked:
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except TimeoutError:
                pass


def _batch_for_run(session: Session, run: OpinionRun) -> OpinionBatch | None:
    if not run.cycle_id:
        return None
    return session.scalar(
        select(OpinionBatch).where(
            OpinionBatch.cycle_id == run.cycle_id,
            OpinionBatch.batch_number == run.batch,
        )
    )


def _run_dir(run: OpinionRun, settings: Settings):
    from pathlib import Path

    return Path((run.input_paths or {}).get("dir") or settings.runs_dir / "active" / run.id)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
