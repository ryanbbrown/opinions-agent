"""Weekly evidence assignment, balanced partitioning, and immutable cycle bundles."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths, HighlightRow, document_by_id, read_highlights
from opinions_agent.fsio import write_jsonl_atomic, write_text_atomic
from opinions_agent.models import (
    BatchStatus,
    CycleStatus,
    OpinionBatch,
    OpinionCycle,
    OpinionEvidenceAssignment,
    WorkflowLease,
)
from opinions_agent.reader import iso_utc, parse_iso
from opinions_agent.selection import _is_backfill_document

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
            index = _blocking_segment(segments, len(ordered) / batch_count)
            segment = segments[index]
            if len(segment) <= 1:
                break
            cut = max(1, min(len(segment) - 1, round(len(ordered) / batch_count)))
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


def _blocking_segment(segments: list[list[HighlightRow]], target: float) -> int:
    candidates = [(len(segment) - target, len(segment), -index, index) for index, segment in enumerate(segments)]
    return max(candidates)[-1]


def _best_boundaries(
    segments: list[list[HighlightRow]],
    batch_count: int,
    total_rows: int,
) -> list[list[list[HighlightRow]]] | None:
    target = total_rows / batch_count
    low = math.floor(target * 0.5)
    high = math.ceil(target * 1.5)
    candidates: list[tuple[tuple, list[list[list[HighlightRow]]]]] = []

    def search(start: int, batches_left: int, built: list[list[list[HighlightRow]]]) -> None:
        if batches_left == 0:
            if start != len(segments):
                return
            row_counts = [sum(len(segment) for segment in batch) for batch in built]
            doc_counts = [len({row.document_id for segment in batch for row in segment}) for batch in built]
            boundaries = tuple(batch[-1][-1].highlight_id for batch in built[:-1])
            rank = (
                max(abs(count - target) for count in row_counts),
                max(doc_counts) - min(doc_counts),
                boundaries,
            )
            candidates.append((rank, [list(batch) for batch in built]))
            return
        maximum_end = len(segments) - batches_left + 1
        for end in range(start + 1, maximum_end + 1):
            batch = segments[start:end]
            row_count = sum(len(segment) for segment in batch)
            doc_count = len({row.document_id for segment in batch for row in segment})
            if row_count > MAX_EVIDENCE_ROWS or doc_count > MAX_DOCUMENTS or row_count > high:
                break
            if row_count < low:
                continue
            search(end, batches_left - 1, [*built, batch])

    search(0, batch_count, [])
    return min(candidates, key=lambda candidate: candidate[0])[1] if candidates else None


def acquire_lease(
    session: Session,
    name: str,
    *,
    owner_token: str,
    now: datetime,
    duration: timedelta = timedelta(minutes=15),
) -> bool:
    lease = session.get(WorkflowLease, name)
    if lease is not None and lease.expires_at > now and lease.owner_token != owner_token:
        return False
    if lease is None:
        lease = WorkflowLease(name=name, owner_token=owner_token, expires_at=now + duration)
        session.add(lease)
    else:
        lease.owner_token = owner_token
        lease.expires_at = now + duration
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


def start_cycle_from_corpus(
    *,
    session: Session,
    settings: Settings,
    now: datetime | None = None,
) -> CycleStartResult:
    """Reserve one weekly cycle, assign evidence versions, and write every bundle."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    owner = uuid4().hex
    if not acquire_lease(session, "opinion-cycle-start", owner_token=owner, now=current):
        existing = _unfinished_cycle(session)
        if existing is None:
            raise RuntimeError("another cycle start owns the start lease")
        return _existing_result(existing)
    try:
        existing_week = session.scalar(select(OpinionCycle).where(OpinionCycle.week_key == week_key(current)))
        if existing_week is not None:
            return _existing_result(existing_week)
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
        cycle = OpinionCycle(
            week_key=week_key(current),
            status=CycleStatus.STARTING.value,
            window_start=previous.window_end if previous else boundary,
            window_end=current,
            initial_evidence_after=boundary if previous is None else previous.initial_evidence_after,
        )
        session.add(cycle)
        session.commit()
        versions = _eligible_versions(session, settings, cycle)
        batches = partition_evidence([version.row for version in versions])
        _materialize_cycle(session, settings, cycle, versions, batches)
        cycle.status = CycleStatus.ACTIVE.value if batches else CycleStatus.COMPLETED.value
        session.commit()
        return CycleStartResult(
            cycle_id=cycle.id,
            status=cycle.status,
            batch_count=cycle.batch_count,
            result_code="created" if batches else "no_evidence",
            created=True,
        )
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
    boundary = cycle.initial_evidence_after
    for row in read_highlights(corpus):
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
        versions.append(EvidenceVersion(row, fingerprint))
    session.commit()
    versions.sort(
        key=lambda version: (
            parse_iso(version.row.highlighted_at) or cycle.window_end,
            version.row.highlight_id,
        )
    )
    return versions


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
    session.commit()


def complete_cycle_directory(settings: Settings, cycle_id: str) -> Path:
    active = settings.runs_dir / "active" / cycle_id
    completed = settings.runs_dir / "completed" / cycle_id
    completed.parent.mkdir(parents=True, exist_ok=True)
    if completed.exists():
        shutil.rmtree(completed)
    active.rename(completed)
    return completed
