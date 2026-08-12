from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from opinions_agent.agent import DeterministicOpinionAgent
from opinions_agent.config import Settings
from opinions_agent.corpus import (
    CorpusPaths,
    DocumentRow,
    HighlightRow,
    init_data_dirs,
    upsert_documents,
    upsert_highlights,
)
from opinions_agent.cycles import evidence_fingerprint, partition_evidence, start_cycle_from_corpus, start_opinion_cycle
from opinions_agent.fsio import read_jsonl
from opinions_agent.models import BatchStatus, CycleStatus, OpinionBatch, OpinionCycle, OpinionEvidenceAssignment
from opinions_agent.telegram import FakeTelegramClient
from opinions_agent.worker import process_queued_once
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
    assert counts([51]) == [26, 25]
    assert len(counts([1] * 41)) == 3
    assert len(counts([101])) == 3


def test_partition_splits_blocking_document_but_keeps_acceptable_boundaries() -> None:
    assert counts([45, 5]) == [25, 25]
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


def test_cycle_materializes_all_batches_and_assigns_versions(session, settings: Settings, tmp_path) -> None:
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

    result = start_cycle_from_corpus(
        session=session,
        settings=settings,
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
        assert len(read_jsonl(tmp_path / batch.bundle_path / "selected-highlights.jsonl")) == batch.evidence_count
        assert (tmp_path / batch.bundle_path / "critic-context.jsonl").exists()

    duplicate = start_cycle_from_corpus(
        session=session,
        settings=settings,
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
    result = start_cycle_from_corpus(
        session=session,
        settings=settings,
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

    assert calls == 1
    assert first.created is True
    assert second.cycle_id == first.cycle_id and second.created is False
