from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import opinions_agent.workflow as workflow_module
from opinions_agent.agent import AgentTurnOutput, DeterministicOpinionAgent, OpinionAgent
from opinions_agent.config import Settings
from opinions_agent.corpus import (
    CorpusPaths,
    DocumentRow,
    HighlightRow,
    init_data_dirs,
    upsert_documents,
    upsert_highlights,
)
from opinions_agent.cycles import (
    evidence_fingerprint,
    partition_evidence,
    reconcile_starting_cycles,
    retry_stopped_cycle,
    retry_stopped_snapshot,
    start_opinion_cycle,
)
from opinions_agent.fsio import read_jsonl, write_json_atomic
from opinions_agent.models import (
    BatchStatus,
    CycleStatus,
    OpinionBatch,
    OpinionCycle,
    OpinionEvidenceAssignment,
    OpinionRun,
    RunStatus,
)
from opinions_agent.telegram import FakeTelegramClient
from opinions_agent.worker import process_queued_once, reconcile_startup
from opinions_agent.workflow import handle_telegram_update


def rows(sizes: list[int]) -> list[HighlightRow]:
    result: list[HighlightRow] = []
    index = 0
    for document_index, size in enumerate(sizes):
        for _ in range(size):
            result.append(
                HighlightRow(
                    highlight_id=f"rw:{index:03d}",
                    document_id=f"reader:{document_index:03d}",
                    reader_id=str(document_index),
                    text=f"evidence {index}",
                    highlighted_at=f"2026-06-{1 + index // 24:02d}T{index % 24:02d}:00:00+00:00",
                )
            )
            index += 1
    return result


def counts(sizes: list[int]) -> list[int]:
    return [len(batch.rows) for batch in partition_evidence(rows(sizes))]


def test_partition_thresholds_and_balance() -> None:
    assert counts([3] * 16 + [1]) == [49]
    assert counts([1] * 20) == [10, 10]
    assert counts([5] * 10) == [25, 25]
    assert sorted(counts([51])) == [25, 26]
    assert len(counts([1] * 41)) == 3
    assert len(counts([101])) == 3


def test_partition_splits_blocking_document_but_keeps_acceptable_boundaries() -> None:
    assert counts([45, 5]) == [25, 25]
    assert counts([5, 45]) == [25, 25]
    assert counts([23, 27]) == [23, 27]


def test_partition_preserves_every_evidence_version_and_caps() -> None:
    evidence = rows([63, 7, 45, 2, 1])
    batches = partition_evidence(evidence)

    flattened = [row.highlight_id for batch in batches for row in batch.rows]
    assert flattened == [row.highlight_id for row in evidence]
    assert all(len(batch.rows) <= 50 for batch in batches)
    assert all(len(set(batch.document_ids)) <= 20 for batch in batches)


def test_fingerprint_changes_when_readable_content_changes() -> None:
    row = rows([1])[0]

    assert evidence_fingerprint(row) != evidence_fingerprint(row.model_copy(update={"note": "new note"}))


def test_partition_large_document_set_finishes_quickly() -> None:
    started = monotonic()
    batches = partition_evidence(rows([2] * 120))
    assert monotonic() - started < 2
    assert len(batches) == 6
    assert all(len(batch.rows) <= 50 and len(batch.document_ids) <= 20 for batch in batches)


@pytest.mark.parametrize("sizes", [[1] * 39, [3, 47, 2, 48], [17, 1, 17, 1, 17, 1]])
def test_partition_is_deterministic_and_uses_the_minimum_legal_batch_count(sizes: list[int]) -> None:
    evidence = rows(sizes)
    expected_ids = [row.highlight_id for row in evidence]
    batches = partition_evidence(list(reversed(evidence)))

    assert [row.highlight_id for batch in batches for row in batch.rows] == expected_ids
    assert len(batches) == max(2, (len(evidence) + 49) // 50, (len(sizes) + 19) // 20)
    assert all(len(batch.rows) <= 50 and len(batch.document_ids) <= 20 for batch in batches)


def test_partition_result_is_stable_across_random_input_orderings() -> None:
    evidence = rows([5, 45, 3, 17, 2])
    expected = [[row.highlight_id for row in batch.rows] for batch in partition_evidence(evidence)]

    for seed in range(10):
        shuffled = list(evidence)
        random.Random(seed).shuffle(shuffled)
        assert [[row.highlight_id for row in batch.rows] for batch in partition_evidence(shuffled)] == expected


async def test_cycle_materializes_all_batches_and_assigns_versions(session, settings: Settings, tmp_path) -> None:
    settings = settings.__class__(
        **{
            **settings.__dict__,
            "initial_evidence_after": "2026-06-01T00:00:00+00:00",
        }
    )
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    evidence = rows([45, 5])
    upsert_documents(
        corpus,
        [
            DocumentRow(document_id=f"reader:{index:03d}", reader_id=str(index), title=f"Doc {index}")
            for index in range(2)
        ],
    )
    upsert_highlights(corpus, evidence)

    result = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )

    assert result.created is True
    assert result.batch_count == 2
    cycle = session.get(OpinionCycle, result.cycle_id)
    assert cycle is not None
    batches = list(
        session.scalars(
            select(OpinionBatch).where(OpinionBatch.cycle_id == cycle.id).order_by(OpinionBatch.batch_number)
        )
    )
    assert [batch.status for batch in batches] == [BatchStatus.QUEUED.value, BatchStatus.PENDING.value]
    assert [batch.evidence_count for batch in batches] == [25, 25]
    assert len(list(session.scalars(select(OpinionEvidenceAssignment)))) == 50
    for batch in batches:
        selected = read_jsonl(tmp_path / batch.bundle_path / "selected-highlights.jsonl")
        context = read_jsonl(tmp_path / batch.bundle_path / "critic-context.jsonl")
        assert len(selected) == batch.evidence_count
        for document_id in {row["document_id"] for row in selected}:
            assert [row for row in context if row["document_id"] == document_id] == [
                row.model_dump(mode="json") for row in evidence if row.document_id == document_id
            ]
        assert (tmp_path / batch.bundle_path / "critic-context.jsonl").exists()

    first_bundle = Path(batches[0].bundle_path) / "selected-highlights.jsonl"
    frozen = first_bundle.read_bytes()
    upsert_highlights(corpus, [evidence[0].model_copy(update={"text": "changed after snapshot"})])
    assert first_bundle.read_bytes() == frozen

    duplicate = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 12, 1, tzinfo=UTC),
    )
    assert duplicate.cycle_id == result.cycle_id
    assert duplicate.created is False


async def test_worker_continues_batches_after_telegram_completion(
    session,
    settings: Settings,
    opinions_repo,
) -> None:
    settings = settings.__class__(
        **{
            **settings.__dict__,
            "initial_evidence_after": "2026-06-01T00:00:00+00:00",
        }
    )
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    evidence = rows([25, 25])
    upsert_documents(
        corpus,
        [
            DocumentRow(document_id=f"reader:{index:03d}", reader_id=str(index), title=f"Doc {index}")
            for index in range(2)
        ],
    )
    upsert_highlights(corpus, evidence)
    result = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    telegram = FakeTelegramClient()
    agent = DeterministicOpinionAgent()

    assert await process_queued_once(session, settings, agent, telegram) is True
    assert await handle_telegram_update(
        session=session,
        settings=settings,
        agent=agent,
        telegram=telegram,
        update={"update_id": 1, "message": {"message_id": 1, "chat": {"id": 12345}, "text": "GO"}},
    ) == "go"
    batches = list(
        session.scalars(
            select(OpinionBatch).where(OpinionBatch.cycle_id == result.cycle_id).order_by(OpinionBatch.batch_number)
        )
    )
    assert [batch.status for batch in batches] == [BatchStatus.COMPLETED.value, BatchStatus.QUEUED.value]
    first_successful_run = batches[0].successful_run_id
    cycle = session.get(OpinionCycle, result.cycle_id)
    assert cycle is not None
    cycle.status = CycleStatus.STOPPED.value
    batches[1].status = BatchStatus.STOPPED.value
    session.commit()

    retried = retry_stopped_cycle(session, result.cycle_id)

    assert retried.batch_number == 2
    assert batches[0].status == BatchStatus.COMPLETED.value
    assert batches[0].successful_run_id == first_successful_run

    assert await process_queued_once(session, settings, agent, telegram) is True
    assert await handle_telegram_update(
        session=session,
        settings=settings,
        agent=agent,
        telegram=telegram,
        update={"update_id": 2, "message": {"message_id": 2, "chat": {"id": 12345}, "text": "GO"}},
    ) == "go"
    cycle = session.get(OpinionCycle, result.cycle_id)
    assert cycle is not None and cycle.status == CycleStatus.COMPLETED.value
    assert (settings.runs_dir / "completed" / result.cycle_id).is_dir()


async def test_worker_claim_serializes_agent_turns_and_expired_run_is_swept(
    session,
    settings: Settings,
    opinions_repo,
) -> None:
    settings = settings.__class__(
        **{**settings.__dict__, "initial_evidence_after": "2026-06-01T00:00:00+00:00"}
    )
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    evidence = rows([1])
    upsert_documents(corpus, [DocumentRow(document_id=evidence[0].document_id, reader_id="0", title="Doc")])
    upsert_highlights(corpus, evidence)
    cycle_result = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )

    class BlockingAgent(OpinionAgent):
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.calls = 0

        async def run_turn(self, **kwargs):
            self.calls += 1
            self.started.set()
            await asyncio.Event().wait()
            return AgentTurnOutput(status="done", telegram_messages=[]), None

    agent = BlockingAgent()
    telegram = FakeTelegramClient()
    SessionLocal = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    with SessionLocal() as first_session, SessionLocal() as second_session:
        first = asyncio.create_task(process_queued_once(first_session, settings, agent, telegram))
        await agent.started.wait()
        assert await process_queued_once(second_session, settings, agent, telegram) is False
        assert agent.calls == 1
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

    run = session.scalar(select(OpinionRun).where(OpinionRun.cycle_id == cycle_result.cycle_id))
    assert run is not None and run.status == RunStatus.RUNNING_AGENT.value
    assert reconcile_startup(session, settings) == []
    run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()

    assert await process_queued_once(session, settings, DeterministicOpinionAgent(), telegram) is False
    assert run.status == RunStatus.FAILED.value
    assert session.get(OpinionCycle, cycle_result.cycle_id).status == CycleStatus.STOPPED.value
    assert len(telegram.sent) == 1


@pytest.mark.parametrize("failure_point", ["ensure_opinions_repo", "capture_run_baseline"])
async def test_cycle_setup_failure_stops_once_without_retry(
    session,
    settings: Settings,
    opinions_repo,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    settings = settings.__class__(
        **{**settings.__dict__, "initial_evidence_after": "2026-06-01T00:00:00+00:00"}
    )
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    evidence = rows([1])
    upsert_documents(corpus, [DocumentRow(document_id=evidence[0].document_id, reader_id="0", title="Doc")])
    upsert_highlights(corpus, evidence)
    result = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )

    def fail_setup(*args, **kwargs):
        raise RuntimeError(f"{failure_point} failed")

    monkeypatch.setattr(workflow_module, failure_point, fail_setup)
    telegram = FakeTelegramClient()
    with pytest.raises(RuntimeError, match="failed"):
        await process_queued_once(session, settings, DeterministicOpinionAgent(), telegram)

    cycle = session.get(OpinionCycle, result.cycle_id)
    runs = list(session.scalars(select(OpinionRun).where(OpinionRun.cycle_id == result.cycle_id)))
    assert cycle is not None and cycle.status == CycleStatus.STOPPED.value
    assert len(runs) == 1 and runs[0].status == RunStatus.FAILED.value
    assert len(telegram.sent) == 1
    assert await process_queued_once(session, settings, DeterministicOpinionAgent(), telegram) is False
    assert len(list(session.scalars(select(OpinionRun).where(OpinionRun.cycle_id == result.cycle_id)))) == 1
    assert len(telegram.sent) == 1


async def test_dirty_cycle_checkout_stops_before_agent_turn_and_preserves_existing_edit(
    session,
    settings: Settings,
    opinions_repo,
) -> None:
    settings = settings.__class__(
        **{**settings.__dict__, "initial_evidence_after": "2026-06-01T00:00:00+00:00"}
    )
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    evidence = rows([1])
    upsert_documents(corpus, [DocumentRow(document_id=evidence[0].document_id, reader_id="0", title="Doc")])
    upsert_highlights(corpus, evidence)
    result = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    original = settings.opinions_target_path.read_text(encoding="utf-8")
    settings.opinions_target_path.write_text("dirty checkout\n", encoding="utf-8")
    telegram = FakeTelegramClient()

    with pytest.raises(Exception, match="dirty"):
        await process_queued_once(session, settings, DeterministicOpinionAgent(), telegram)

    assert session.get(OpinionCycle, result.cycle_id).status == CycleStatus.STOPPED.value
    assert settings.opinions_target_path.read_text(encoding="utf-8") == "dirty checkout\n"
    settings.opinions_target_path.write_text(original, encoding="utf-8")


async def test_cycle_reserves_before_sync_and_duplicate_does_not_sync(
    session,
    settings: Settings,
) -> None:
    settings = settings.__class__(
        **{**settings.__dict__, "initial_evidence_after": "2026-06-01T00:00:00+00:00"}
    )
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    calls = 0

    async def sync() -> None:
        nonlocal calls
        calls += 1
        reserved = session.scalar(select(OpinionCycle))
        assert reserved is not None and reserved.status == CycleStatus.STARTING.value
        upsert_documents(corpus, [DocumentRow(document_id="reader:000", reader_id="0", title="Doc")])
        upsert_highlights(corpus, rows([1]))

    first = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=sync,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    second = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=sync,
        now=datetime(2026, 6, 12, 1, tzinfo=UTC),
    )
    next_week = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=sync,
        now=datetime(2026, 6, 19, tzinfo=UTC),
    )

    assert calls == 1
    assert first.created is True
    assert second.cycle_id == first.cycle_id and second.created is False
    assert next_week.cycle_id == first.cycle_id and next_week.created is False


async def test_failed_snapshot_keeps_reservation_and_can_retry(
    session,
    settings: Settings,
) -> None:
    settings = settings.__class__(
        **{**settings.__dict__, "initial_evidence_after": "2026-06-01T00:00:00+00:00"}
    )
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)

    async def fail_sync() -> None:
        upsert_documents(corpus, [DocumentRow(document_id="reader:000", reader_id="0", title="Doc")])
        upsert_highlights(corpus, rows([1]))
        raise RuntimeError("reader unavailable")

    with pytest.raises(RuntimeError, match="reader unavailable"):
        await start_opinion_cycle(
            session=session,
            settings=settings,
            sync_corpus=fail_sync,
            now=datetime(2026, 6, 12, tzinfo=UTC),
        )
    cycle = session.scalar(select(OpinionCycle))
    assert cycle is not None
    assert cycle.status == CycleStatus.STOPPED.value
    assert cycle.failure_code == "snapshot_failed"
    assert list(session.scalars(select(OpinionEvidenceAssignment))) == []

    async def successful_sync() -> None:
        return None

    result = await retry_stopped_snapshot(
        session=session,
        settings=settings,
        cycle_id=cycle.id,
        sync_corpus=successful_sync,
    )

    assert result.result_code == "retried"
    assert result.batch_count == 1
    assert session.get(OpinionCycle, cycle.id).status == CycleStatus.ACTIVE.value


async def test_no_evidence_cycle_completes_and_late_evidence_is_selected_next_week(
    session,
    settings: Settings,
) -> None:
    settings = settings.__class__(
        **{**settings.__dict__, "initial_evidence_after": "2026-06-01T00:00:00+00:00"}
    )
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)

    empty = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    assert empty.result_code == "no_evidence"
    assert session.get(OpinionCycle, empty.cycle_id).status == CycleStatus.COMPLETED.value
    assert (settings.runs_dir / "completed" / empty.cycle_id).is_dir()

    late = rows([1])[0].model_copy(update={"highlighted_at": "2026-06-05T00:00:00+00:00"})
    upsert_documents(corpus, [DocumentRow(document_id=late.document_id, reader_id="0", title="Late")])
    upsert_highlights(corpus, [late])
    next_cycle = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 19, tzinfo=UTC),
    )

    assert next_cycle.batch_count == 1
    batch = session.scalar(select(OpinionBatch).where(OpinionBatch.cycle_id == next_cycle.cycle_id))
    assert batch is not None and [row["evidence_id"] for row in batch.evidence_versions] == [late.highlight_id]


async def test_changed_evidence_version_is_eligible_after_prior_cycle_completes(
    session,
    settings: Settings,
) -> None:
    settings = settings.__class__(
        **{**settings.__dict__, "initial_evidence_after": "2026-06-01T00:00:00+00:00"}
    )
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    original = rows([1])[0]
    upsert_documents(corpus, [DocumentRow(document_id=original.document_id, reader_id="0", title="Doc")])
    upsert_highlights(corpus, [original])
    first = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    first_cycle = session.get(OpinionCycle, first.cycle_id)
    assert first_cycle is not None
    first_cycle.status = CycleStatus.COMPLETED.value
    session.commit()

    changed = original.model_copy(update={"note": "a later correction"})
    upsert_highlights(corpus, [changed])
    second = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 19, tzinfo=UTC),
    )

    assignments = list(
        session.scalars(
            select(OpinionEvidenceAssignment).where(OpinionEvidenceAssignment.evidence_id == original.highlight_id)
        )
    )
    assert second.batch_count == 1
    assert {assignment.fingerprint for assignment in assignments} == {
        evidence_fingerprint(original),
        evidence_fingerprint(changed),
    }


async def test_reconcile_starting_cycle_promotes_complete_snapshot_or_stops_partial_one(
    session,
    settings: Settings,
) -> None:
    settings = settings.__class__(
        **{**settings.__dict__, "initial_evidence_after": "2026-06-01T00:00:00+00:00"}
    )
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    evidence = rows([1])
    upsert_documents(corpus, [DocumentRow(document_id=evidence[0].document_id, reader_id="0", title="Doc")])
    upsert_highlights(corpus, evidence)
    complete = await start_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=_no_sync,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    complete_cycle = session.get(OpinionCycle, complete.cycle_id)
    assert complete_cycle is not None
    complete_cycle.status = CycleStatus.STARTING.value
    session.commit()

    assert reconcile_starting_cycles(session, settings) == []
    assert session.get(OpinionCycle, complete.cycle_id).status == CycleStatus.ACTIVE.value

    complete_cycle.status = CycleStatus.COMPLETED.value
    partial = OpinionCycle(
        week_key="2026-W25",
        status=CycleStatus.STARTING.value,
        window_start=datetime(2026, 6, 12, tzinfo=UTC),
        window_end=datetime(2026, 6, 19, tzinfo=UTC),
    )
    session.add(partial)
    session.commit()
    partial_dir = settings.runs_dir / "active" / partial.id
    partial_dir.mkdir(parents=True)
    write_json_atomic(partial_dir / "snapshot.json", {"cycle_id": partial.id, "batch_count": 1})

    assert [cycle.id for cycle in reconcile_starting_cycles(session, settings)] == [partial.id]
    assert session.get(OpinionCycle, partial.id).status == CycleStatus.STOPPED.value

    reserved = OpinionCycle(
        week_key="2026-W26",
        status=CycleStatus.STARTING.value,
        window_start=datetime(2026, 6, 19, tzinfo=UTC),
        window_end=datetime(2026, 6, 26, tzinfo=UTC),
    )
    session.add(reserved)
    session.commit()
    assert [cycle.id for cycle in reconcile_starting_cycles(session, settings)] == [reserved.id]
    assert session.get(OpinionCycle, reserved.id).status == CycleStatus.STOPPED.value


async def _no_sync() -> None:
    return None
