"""Single-replica cycle worker and bounded startup reconciliation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from opinions_agent.agent import OpinionAgent
from opinions_agent.config import Settings
from opinions_agent.cycles import acquire_lease, reconcile_starting_cycles, release_lease
from opinions_agent.diagnostics import log_operational_failure
from opinions_agent.models import BatchStatus, CycleStatus, GitPhase, OpinionBatch, OpinionCycle, OpinionRun, RunStatus
from opinions_agent.recovery import archive_and_restore_run, reconcile_git_durability
from opinions_agent.workflow import (
    TelegramSender,
    complete_reconciled_run,
    run_pending_opinion_run,
    send_cycle_failure_notice,
    send_snapshot_failure_notice,
    start_materialized_opinion_run,
)

LOGGER = logging.getLogger(__name__)
RECONCILE_BACKOFF_BASE = timedelta(minutes=5)
RECONCILE_BACKOFF_MAX = timedelta(hours=1)


@dataclass(frozen=True)
class ReconciliationResult:
    stopped_runs: list[OpinionRun]
    stopped_cycles: list[OpinionCycle]
    healthy: bool


def reconcile_startup(session: Session, settings: Settings) -> ReconciliationResult:
    """Reconcile snapshots, commits, and expired model turns without leaking one failure."""
    now = datetime.now(UTC)
    stopped_runs: list[OpinionRun] = []
    stopped_cycles: list[OpinionCycle] = []
    healthy = True
    try:
        stopped_cycles = reconcile_starting_cycles(session, settings)
    except Exception as exc:
        session.rollback()
        log_operational_failure(LOGGER, settings, exc, phase="starting_cycle_reconciliation")
        healthy = False

    candidates = list(
        session.scalars(
            select(OpinionRun).where(OpinionRun.status.in_([RunStatus.RUNNING_AGENT.value, RunStatus.FAILED.value]))
        )
    )
    for candidate in candidates:
        run = session.get(OpinionRun, candidate.id)
        if run is None:
            continue
        if run.reconcile_after is not None and _utc(run.reconcile_after) > now:
            healthy = False
            continue
        try:
            needs_git_reconciliation = run.git_phase in {
                GitPhase.COMMIT_INTENT.value,
                GitPhase.COMMITTED.value,
                GitPhase.PUSHED.value,
            }
            if needs_git_reconciliation and reconcile_git_durability(settings, run):
                complete_reconciled_run(session, settings, run)
                run.reconcile_after = None
                run.reconcile_attempts = 0
                session.commit()
                continue
            if run.status == RunStatus.FAILED.value:
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
            stopped_runs.append(run)
            session.commit()
        except Exception as exc:
            session.rollback()
            run = session.get(OpinionRun, candidate.id)
            if run is not None:
                run.reconcile_attempts += 1
                multiplier = 2 ** min(run.reconcile_attempts - 1, 4)
                run.reconcile_after = now + min(RECONCILE_BACKOFF_BASE * multiplier, RECONCILE_BACKOFF_MAX)
                session.commit()
                log_operational_failure(
                    LOGGER,
                    settings,
                    exc,
                    phase="run_reconciliation",
                    cycle_id=run.cycle_id or "none",
                    batch=run.batch,
                    run_id=run.id,
                )
            healthy = False
    return ReconciliationResult(stopped_runs, stopped_cycles, healthy)


async def process_queued_once(
    session: Session,
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    *,
    readiness: Callable[[bool], None] | None = None,
) -> bool:
    reconciliation = reconcile_startup(session, settings)
    if readiness is not None:
        readiness(reconciliation.healthy)
    for cycle in reconciliation.stopped_cycles:
        try:
            await send_snapshot_failure_notice(session=session, settings=settings, telegram=telegram, cycle=cycle)
        except Exception as exc:
            log_operational_failure(
                LOGGER,
                settings,
                exc,
                phase="snapshot_failure_notice",
                cycle_id=cycle.id,
            )
    for run in reconciliation.stopped_runs:
        try:
            await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=run)
        except Exception as exc:
            log_operational_failure(
                LOGGER,
                settings,
                exc,
                phase="run_failure_notice",
                cycle_id=run.cycle_id or "none",
                batch=run.batch,
                run_id=run.id,
            )
    owner = uuid4().hex
    now = datetime.now(UTC)
    if not acquire_lease(session, "opinion-worker-claim", owner_token=owner, now=now):
        return False
    try:
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
    finally:
        release_lease(session, "opinion-worker-claim", owner)


async def worker_loop(
    SessionLocal: sessionmaker[Session],
    settings: Settings,
    agent: OpinionAgent,
    telegram: TelegramSender,
    stop: asyncio.Event,
    readiness: Callable[[bool], None] | None = None,
) -> None:
    while not stop.is_set():
        with SessionLocal() as session:
            try:
                worked = await process_queued_once(
                    session,
                    settings,
                    agent,
                    telegram,
                    readiness=readiness,
                )
            except Exception as exc:
                session.rollback()
                log_operational_failure(LOGGER, settings, exc, phase="worker_iteration")
                if readiness is not None:
                    readiness(False)
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


def _run_dir(run: OpinionRun, settings: Settings) -> Path:
    return Path((run.input_paths or {}).get("dir") or settings.runs_dir / "active" / run.id)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
