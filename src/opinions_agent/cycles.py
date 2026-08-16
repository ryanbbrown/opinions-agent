"""Weekly evidence assignment, balanced partitioning, and immutable cycle bundles."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths, HighlightRow, document_by_id, read_highlights
from opinions_agent.fsio import read_json, read_jsonl, write_json_atomic, write_jsonl_atomic, write_text_atomic
from opinions_agent.models import (
    NON_TERMINAL_RUN_STATUSES,
    BatchStatus,
    CycleStatus,
    GitPhase,
    OpinionBatch,
    OpinionCycle,
    OpinionEvidenceAssignment,
    OpinionRun,
    WorkflowLease,
)
from opinions_agent.reader import iso_utc, parse_iso
from opinions_agent.selection import _document_summary_evidence, _is_backfill_document

MAX_DOCUMENTS = 20
MAX_EVIDENCE_ROWS = 50


@dataclass(frozen=True)
class EvidenceVersion:
    row: HighlightRow
    fingerprint: str


@dataclass(frozen=True)
class PartitionBatch:
    rows: list[HighlightRow]

    @property
    def document_ids(self) -> list[str]:
        return list(dict.fromkeys(row.document_id for row in self.rows))


@dataclass(frozen=True)
class CycleStartResult:
    cycle_id: str
    status: str
    batch_count: int
    result_code: str
    created: bool


def evidence_fingerprint(row: HighlightRow) -> str:
    readable = {
        "document_id": row.document_id,
        "document_title": row.document_title,
        "document_author": row.document_author,
        "document_summary": row.document_summary,
        "source_url": row.source_url,
        "evidence_kind": row.evidence_kind,
        "text": row.text,
        "note": row.note,
        "highlighted_at": row.highlighted_at,
        "content_path": row.content_path,
    }
    payload = json.dumps(readable, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def partition_evidence(rows: list[HighlightRow]) -> list[PartitionBatch]:
    """Create the smallest legal deterministic partition with balanced row counts."""
    ordered = sorted(
        rows,
        key=lambda row: (
            parse_iso(row.highlighted_at) or datetime.min.replace(tzinfo=UTC),
            row.highlight_id,
        ),
    )
    if not ordered:
        return []
    document_count = len({row.document_id for row in ordered})
    split_required = document_count >= MAX_DOCUMENTS or len(ordered) >= MAX_EVIDENCE_ROWS
    minimum = max(
        2 if split_required else 1,
        math.ceil(document_count / MAX_DOCUMENTS),
        math.ceil(len(ordered) / MAX_EVIDENCE_ROWS),
    )
    groups = _document_groups(ordered)
    for batch_count in range(minimum, len(ordered) + 1):
        segments = [list(group) for group in groups]
        while len(segments) < len(ordered):
            found = _best_boundaries(segments, batch_count, len(ordered))
            if found is not None:
                return [PartitionBatch(rows=[row for segment in batch for row in segment]) for batch in found]
            index, cut = _split_near_global_boundary(segments, len(ordered) / batch_count, batch_count)
            segment = segments[index]
            if len(segment) <= 1:
                break
            segments[index : index + 1] = [segment[:cut], segment[cut:]]
        found = _best_boundaries(segments, batch_count, len(ordered))
        if found is not None:
            return [PartitionBatch(rows=[row for segment in batch for row in segment]) for batch in found]
    raise ValueError("could not create a legal evidence partition")


def _document_groups(rows: list[HighlightRow]) -> list[list[HighlightRow]]:
    by_document: dict[str, list[HighlightRow]] = {}
    order: list[str] = []
    for row in rows:
        if row.document_id not in by_document:
            by_document[row.document_id] = []
            order.append(row.document_id)
        by_document[row.document_id].append(row)
    return [by_document[document_id] for document_id in order]


def _split_near_global_boundary(
    segments: list[list[HighlightRow]], target: float, batch_count: int
) -> tuple[int, int]:
    candidates: list[tuple[float, int, int, int]] = []
    offset = 0
    boundaries = [target * number for number in range(1, batch_count)]
    for index, segment in enumerate(segments):
        for cut in range(1, len(segment)):
            global_position = offset + cut
            distance = min(abs(global_position - boundary) for boundary in boundaries)
            candidates.append((distance, -len(segment), index, cut))
        offset += len(segment)
    if not candidates:
        return 0, 0
    _, _, index, cut = min(candidates)
    return index, cut


def _best_boundaries(
    segments: list[list[HighlightRow]],
    batch_count: int,
    total_rows: int,
) -> list[list[list[HighlightRow]]] | None:
    target = total_rows / batch_count
    low = math.ceil(target * 0.5)
    high = math.floor(target * 1.5)
    @cache
    def search(
        start: int,
        batches_left: int,
        max_row_deviation: float,
        min_docs: int,
        max_docs: int,
    ) -> tuple[tuple, tuple[int, ...]] | None:
        if batches_left == 0:
            if start == len(segments):
                return (max_row_deviation, max_docs - min_docs, ()), ()
            return None
        maximum_end = len(segments) - batches_left + 1
        best: tuple[tuple, tuple[int, ...]] | None = None
        for end in range(start + 1, maximum_end + 1):
            batch = segments[start:end]
            row_count = sum(len(segment) for segment in batch)
            doc_count = len({row.document_id for segment in batch for row in segment})
            if row_count > MAX_EVIDENCE_ROWS or doc_count > MAX_DOCUMENTS or row_count > high:
                break
            if row_count < low:
                continue
            next_min = doc_count if min_docs == 0 else min(min_docs, doc_count)
            suffix = search(
                end,
                batches_left - 1,
                max(max_row_deviation, abs(row_count - target)),
                next_min,
                max(max_docs, doc_count),
            )
            if suffix is None:
                continue
            suffix_rank, suffix_ends = suffix
            boundary_ids = () if end == len(segments) else (segments[end - 1][-1].highlight_id,)
            rank = (suffix_rank[0], suffix_rank[1], boundary_ids + suffix_rank[2])
            candidate = rank, (end, *suffix_ends)
            if best is None or candidate[0] < best[0]:
                best = candidate
        return best

    found = search(0, batch_count, 0.0, 0, 0)
    if found is None:
        return None
    _, ends = found
    result: list[list[list[HighlightRow]]] = []
    start = 0
    for end in ends:
        result.append(segments[start:end])
        start = end
    return result


def acquire_lease(
    session: Session,
    name: str,
    *,
    owner_token: str,
    now: datetime,
    duration: timedelta = timedelta(minutes=15),
) -> bool:
    result = session.execute(
        update(WorkflowLease)
        .where(
            WorkflowLease.name == name,
            or_(WorkflowLease.expires_at <= now, WorkflowLease.owner_token == owner_token),
        )
        .values(owner_token=owner_token, expires_at=now + duration, updated_at=now)
    )
    if int(getattr(result, "rowcount", 0)) == 1:
        session.commit()
        return True
    session.add(WorkflowLease(name=name, owner_token=owner_token, expires_at=now + duration))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return False
    return True


def release_lease(session: Session, name: str, owner_token: str) -> None:
    lease = session.get(WorkflowLease, name)
    if lease is not None and lease.owner_token == owner_token:
        session.delete(lease)
        session.commit()


def week_key(value: datetime) -> str:
    year, week, _ = value.astimezone(UTC).isocalendar()
    return f"{year}-W{week:02d}"


async def start_opinion_cycle(
    *,
    session: Session,
    settings: Settings,
    sync_corpus: Callable[[], Awaitable[object]],
    notify_failure: Callable[[OpinionCycle], Awaitable[None]] | None = None,
    now: datetime | None = None,
) -> CycleStartResult:
    """Reserve a weekly cycle before sync, then freeze and assign its corpus snapshot."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    owner = uuid4().hex
    if not acquire_lease(session, "opinion-cycle-start", owner_token=owner, now=current):
        for _ in range(50):
            session.expire_all()
            existing = _unfinished_cycle(session)
            if existing is not None:
                return _existing_result(existing)
            await asyncio.sleep(0.02)
        raise RuntimeError("another cycle start has not finished its reservation")
    cycle: OpinionCycle | None = None
    try:
        unfinished = _unfinished_cycle(session)
        if unfinished is not None:
            return _existing_result(unfinished)
        previous = session.scalar(
            select(OpinionCycle)
            .where(OpinionCycle.status == CycleStatus.COMPLETED.value)
            .order_by(OpinionCycle.window_end.desc())
        )
        boundary = parse_iso(settings.initial_evidence_after)
        if previous is None and boundary is None:
            raise ValueError("OPINIONS_INITIAL_EVIDENCE_AFTER is required for the first cycle")
        if previous is not None:
            window_start = _ensure_utc(previous.window_end)
        else:
            assert boundary is not None
            window_start = _ensure_utc(boundary)
        if window_start.weekday() != 0 or window_start.time() != datetime.min.time():
            raise ValueError("weekly launch boundary must be Monday at 00:00 UTC")
        window_end = window_start + timedelta(days=7)
        if current < window_end:
            raise ValueError("next weekly window has not ended")
        target_week_key = week_key(window_start)
        existing_week = session.scalar(select(OpinionCycle).where(OpinionCycle.week_key == target_week_key))
        if existing_week is not None:
            return _existing_result(existing_week)
        cycle = OpinionCycle(
            week_key=target_week_key,
            status=CycleStatus.STARTING.value,
            window_start=window_start,
            window_end=window_end,
            initial_evidence_after=boundary if previous is None else previous.initial_evidence_after,
        )
        session.add(cycle)
        session.commit()
        await sync_corpus()
        versions = _eligible_versions(session, settings, cycle)
        batches = partition_evidence([version.row for version in versions])
        _materialize_cycle(session, settings, cycle, versions, batches)
        cycle.status = CycleStatus.ACTIVE.value if batches else CycleStatus.COMPLETED.value
        session.commit()
        if not batches:
            complete_cycle_directory(settings, cycle.id)
        return CycleStartResult(
            cycle_id=cycle.id,
            status=cycle.status,
            batch_count=cycle.batch_count,
            result_code="created" if batches else "no_evidence",
            created=True,
        )
    except Exception:
        if cycle is not None:
            cycle_id = cycle.id
            session.rollback()
            stored_cycle = session.get(OpinionCycle, cycle_id)
            if stored_cycle is None:
                raise
            stored_cycle.status = CycleStatus.STOPPED.value
            stored_cycle.failure_code = "snapshot_failed"
            stored_cycle.failure_summary = "The weekly evidence snapshot failed. Retry the stopped cycle."
            session.commit()
            if notify_failure is not None:
                await notify_failure(stored_cycle)
        raise
    finally:
        release_lease(session, "opinion-cycle-start", owner)


def _unfinished_cycle(session: Session) -> OpinionCycle | None:
    return session.scalar(
        select(OpinionCycle)
        .where(
            OpinionCycle.status.in_([CycleStatus.STARTING.value, CycleStatus.ACTIVE.value, CycleStatus.STOPPED.value])
        )
        .order_by(OpinionCycle.created_at)
    )


def _existing_result(cycle: OpinionCycle) -> CycleStartResult:
    code = "stopped" if cycle.status == CycleStatus.STOPPED.value else "existing"
    return CycleStartResult(cycle.id, cycle.status, cycle.batch_count, code, False)


def _eligible_versions(session: Session, settings: Settings, cycle: OpinionCycle) -> list[EvidenceVersion]:
    corpus = CorpusPaths(settings.opinions_data_dir)
    documents = document_by_id(corpus)
    assignments = {(row.evidence_id, row.fingerprint) for row in session.scalars(select(OpinionEvidenceAssignment))}
    versions: list[EvidenceVersion] = []
    boundary = _ensure_utc(cycle.initial_evidence_after) if cycle.initial_evidence_after else None
    for row in _corpus_evidence(corpus):
        if _is_backfill_document(documents.get(row.document_id)):
            continue
        fingerprint = evidence_fingerprint(row)
        key = (row.highlight_id, fingerprint)
        if key in assignments:
            continue
        source_time = parse_iso(row.highlighted_at)
        if boundary is not None and source_time is not None and source_time < boundary:
            session.add(
                OpinionEvidenceAssignment(
                    evidence_id=row.highlight_id,
                    fingerprint=fingerprint,
                    disposition="baseline_ignored",
                )
            )
            continue
        if source_time is not None and source_time >= _ensure_utc(cycle.window_end):
            continue
        versions.append(EvidenceVersion(row, fingerprint))
    session.commit()
    versions.sort(
        key=lambda version: (
            parse_iso(version.row.highlighted_at) or _ensure_utc(cycle.window_end),
            version.row.highlight_id,
        )
    )
    return versions


def _corpus_evidence(corpus: CorpusPaths) -> list[HighlightRow]:
    highlights = read_highlights(corpus)
    document_ids_with_evidence = {row.document_id for row in highlights}
    rows = list(highlights)
    for document in document_by_id(corpus).values():
        if document.document_id in document_ids_with_evidence or _is_backfill_document(document):
            continue
        summary = (document.summary or "").strip()
        saved_at = parse_iso(document.saved_at)
        if document.tags and summary and saved_at is not None:
            rows.append(_document_summary_evidence(document, summary, saved_at))
    return rows


def _ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _materialize_cycle(
    session: Session,
    settings: Settings,
    cycle: OpinionCycle,
    versions: list[EvidenceVersion],
    batches: list[PartitionBatch],
) -> None:
    cycle_dir = settings.runs_dir / "active" / cycle.id
    cycle_dir.mkdir(parents=True, exist_ok=True)
    documents = document_by_id(CorpusPaths(settings.opinions_data_dir))
    version_by_id = {version.row.highlight_id: version for version in versions}
    all_rows_by_doc: dict[str, list[HighlightRow]] = {}
    for version in versions:
        all_rows_by_doc.setdefault(version.row.document_id, []).append(version.row)
    for number, batch in enumerate(batches, start=1):
        batch_dir = cycle_dir / "batches" / str(number)
        review_dir = batch_dir / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        selected_docs = [documents[doc_id] for doc_id in batch.document_ids if doc_id in documents]
        context_rows = [row for doc_id in batch.document_ids for row in all_rows_by_doc.get(doc_id, [])]
        write_jsonl_atomic(batch_dir / "selected-highlights.jsonl", [row.model_dump(mode="json") for row in batch.rows])
        write_jsonl_atomic(
            batch_dir / "selected-documents.jsonl",
            [row.model_dump(mode="json") for row in selected_docs],
        )
        write_jsonl_atomic(batch_dir / "critic-context.jsonl", [row.model_dump(mode="json") for row in context_rows])
        write_text_atomic(
            review_dir / "summary.md",
            f"# Opinion cycle {cycle.id}, batch {number} of {len(batches)}\n\n"
            f"Window: {iso_utc(cycle.window_start)} to {iso_utc(cycle.window_end)}\n"
            f"Selected evidence: {len(batch.rows)}\nSelected documents: {len(batch.document_ids)}\n",
        )
        model = OpinionBatch(
            cycle_id=cycle.id,
            batch_number=number,
            status=BatchStatus.QUEUED.value if number == 1 else BatchStatus.PENDING.value,
            evidence_versions=[
                {"evidence_id": row.highlight_id, "fingerprint": version_by_id[row.highlight_id].fingerprint}
                for row in batch.rows
            ],
            document_ids=batch.document_ids,
            bundle_path=str(batch_dir),
            evidence_count=len(batch.rows),
            document_count=len(batch.document_ids),
        )
        session.add(model)
        for row in batch.rows:
            session.add(
                OpinionEvidenceAssignment(
                    evidence_id=row.highlight_id,
                    fingerprint=version_by_id[row.highlight_id].fingerprint,
                    disposition="cycle",
                    cycle_id=cycle.id,
                    batch_number=number,
                )
            )
    cycle.document_count = len({version.row.document_id for version in versions})
    cycle.evidence_count = len(versions)
    cycle.batch_count = len(batches)
    cycle.current_batch = 1 if batches else 0
    cycle.failure_code = None
    cycle.failure_summary = None
    write_json_atomic(
        cycle_dir / "snapshot.json",
        {
            "cycle_id": cycle.id,
            "evidence_count": len(versions),
            "document_count": cycle.document_count,
            "batch_count": len(batches),
        },
    )
    session.commit()


def reconcile_starting_cycles(session: Session, settings: Settings) -> list[OpinionCycle]:
    """Promote complete snapshots and stop incomplete reserved cycles."""
    start_lease = session.get(WorkflowLease, "opinion-cycle-start")
    if start_lease is not None and _ensure_utc(start_lease.expires_at) > datetime.now(UTC):
        return []
    stopped: list[OpinionCycle] = []
    cycles = list(session.scalars(select(OpinionCycle).where(OpinionCycle.status == CycleStatus.STARTING.value)))
    for cycle in cycles:
        marker = read_json(settings.runs_dir / "active" / cycle.id / "snapshot.json")
        batches = list(
            session.scalars(
                select(OpinionBatch).where(OpinionBatch.cycle_id == cycle.id).order_by(OpinionBatch.batch_number)
            )
        )
        batch_count = int((marker or {}).get("batch_count", -1))
        assignments = list(
            session.scalars(
                select(OpinionEvidenceAssignment).where(OpinionEvidenceAssignment.cycle_id == cycle.id)
            )
        )
        valid = (
            marker is not None
            and marker.get("cycle_id") == cycle.id
            and batch_count == len(batches)
            and marker.get("evidence_count") == sum(batch.evidence_count for batch in batches)
            and marker.get("document_count") == cycle.document_count
            and len(assignments) == marker.get("evidence_count")
        )
        if valid:
            for batch in batches:
                bundle = Path(batch.bundle_path)
                selected = read_jsonl(bundle / "selected-highlights.jsonl")
                selected_versions = [
                    {
                        "evidence_id": row["highlight_id"],
                        "fingerprint": evidence_fingerprint(HighlightRow.model_validate(row)),
                    }
                    for row in selected
                ]
                if (
                    len(selected) != batch.evidence_count
                    or selected_versions != batch.evidence_versions
                    or not (bundle / "selected-documents.jsonl").is_file()
                    or not (bundle / "critic-context.jsonl").is_file()
                ):
                    valid = False
                    break
        if valid and batch_count == 0:
            cycle.status = CycleStatus.COMPLETED.value
            cycle.failure_code = None
            cycle.failure_summary = None
            session.commit()
            complete_cycle_directory(settings, cycle.id)
        elif valid:
            cycle.status = CycleStatus.ACTIVE.value
            cycle.current_batch = 1
            cycle.failure_code = None
            cycle.failure_summary = None
            batches[0].status = BatchStatus.QUEUED.value
            session.commit()
        else:
            for assignment in session.scalars(
                select(OpinionEvidenceAssignment).where(OpinionEvidenceAssignment.cycle_id == cycle.id)
            ):
                session.delete(assignment)
            for batch in batches:
                session.delete(batch)
            cycle.status = CycleStatus.STOPPED.value
            cycle.failure_code = "snapshot_failed"
            cycle.failure_summary = "The weekly evidence snapshot was interrupted. Retry the stopped cycle."
            cycle.batch_count = 0
            cycle.current_batch = 0
            session.commit()
            stopped.append(cycle)
    return stopped


def complete_cycle_directory(settings: Settings, cycle_id: str) -> Path:
    active = settings.runs_dir / "active" / cycle_id
    completed = settings.runs_dir / "completed" / cycle_id
    if completed.exists() and not active.exists():
        return completed
    completed.parent.mkdir(parents=True, exist_ok=True)
    if completed.exists():
        shutil.rmtree(completed)
    active.rename(completed)
    return completed


def retry_stopped_cycle(session: Session, cycle_id: str) -> OpinionBatch:
    cycle = session.get(OpinionCycle, cycle_id)
    if cycle is None:
        raise ValueError(f"cycle not found: {cycle_id}")
    if cycle.status != CycleStatus.STOPPED.value:
        raise ValueError(f"cycle {cycle_id} is not stopped")
    batch = session.scalar(
        select(OpinionBatch).where(
            OpinionBatch.cycle_id == cycle_id,
            OpinionBatch.batch_number == cycle.current_batch,
        )
    )
    if batch is None or batch.status != BatchStatus.STOPPED.value:
        raise ValueError("stopped cycle has no retryable batch")
    latest_run = session.get(OpinionRun, batch.latest_run_id) if batch.latest_run_id else None
    if latest_run is not None and latest_run.git_phase in {
        GitPhase.COMMIT_INTENT.value,
        GitPhase.COMMITTED.value,
        GitPhase.PUSHED.value,
    }:
        raise ValueError("reconcile the recorded commit before retrying this batch")
    active = session.scalar(select(OpinionRun).where(OpinionRun.status.in_(NON_TERMINAL_RUN_STATUSES)))
    if active is not None:
        raise ValueError(f"run {active.id} is still active")
    batch.status = BatchStatus.QUEUED.value
    cycle.status = CycleStatus.ACTIVE.value
    cycle.failure_code = None
    cycle.failure_summary = None
    session.commit()
    return batch


async def retry_stopped_snapshot(
    *,
    session: Session,
    settings: Settings,
    cycle_id: str,
    sync_corpus: Callable[[], Awaitable[object]],
    notify_failure: Callable[[OpinionCycle], Awaitable[None]] | None = None,
) -> CycleStartResult:
    """Rebuild a reserved cycle whose sync or bundle creation stopped before batch one."""
    cycle = session.get(OpinionCycle, cycle_id)
    if cycle is None:
        raise ValueError(f"cycle not found: {cycle_id}")
    if cycle.status != CycleStatus.STOPPED.value or cycle.failure_code != "snapshot_failed":
        raise ValueError(f"cycle {cycle_id} has no failed snapshot")
    if session.scalar(select(OpinionBatch).where(OpinionBatch.cycle_id == cycle_id)) is not None:
        raise ValueError("cycle already has a retryable batch")
    owner = uuid4().hex
    now = datetime.now(UTC)
    if not acquire_lease(session, "opinion-cycle-start", owner_token=owner, now=now):
        raise RuntimeError("another cycle start owns the start lease")
    try:
        cycle.status = CycleStatus.STARTING.value
        cycle.failure_code = None
        cycle.failure_summary = None
        session.commit()
        await sync_corpus()
        versions = _eligible_versions(session, settings, cycle)
        batches = partition_evidence([version.row for version in versions])
        _materialize_cycle(session, settings, cycle, versions, batches)
        cycle.status = CycleStatus.ACTIVE.value if batches else CycleStatus.COMPLETED.value
        session.commit()
        if not batches:
            complete_cycle_directory(settings, cycle.id)
        return CycleStartResult(
            cycle_id=cycle.id,
            status=cycle.status,
            batch_count=cycle.batch_count,
            result_code="retried" if batches else "no_evidence",
            created=False,
        )
    except Exception:
        session.rollback()
        cycle = session.get(OpinionCycle, cycle_id)
        if cycle is not None:
            cycle.status = CycleStatus.STOPPED.value
            cycle.failure_code = "snapshot_failed"
            cycle.failure_summary = "The weekly evidence snapshot failed. Retry the stopped cycle."
            session.commit()
            if notify_failure is not None:
                await notify_failure(cycle)
        raise
    finally:
        release_lease(session, "opinion-cycle-start", owner)
