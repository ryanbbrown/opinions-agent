from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import replace
from datetime import UTC, datetime

import pytest

import opinions_agent.cycles as cycles_module
from opinions_agent.config import Settings
from opinions_agent.corpus import (
    CorpusPaths,
    DocumentRow,
    HighlightRow,
    init_data_dirs,
    upsert_documents,
    upsert_highlights,
)
from opinions_agent.cycles import start_opinion_cycle
from opinions_agent.db import make_engine, make_sessionmaker


async def test_postgres_concurrent_starts_return_one_created_cycle(settings: Settings, monkeypatch) -> None:
    database_url = os.environ.get("OPINIONS_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("OPINIONS_TEST_POSTGRES_URL is not configured")
    engine = make_engine(database_url)
    SessionLocal = make_sessionmaker(engine)
    configured = replace(
        settings,
        database_url=database_url,
        initial_evidence_after="2026-06-01T00:00:00+00:00",
    )
    init_data_dirs(CorpusPaths(configured.opinions_data_dir))
    real_acquire = cycles_module.acquire_lease
    owner_has_lease = threading.Event()
    allow_reservation = threading.Event()
    sync_count = 0
    sync_lock = threading.Lock()

    def paused_acquire(*args, **kwargs):
        acquired = real_acquire(*args, **kwargs)
        if acquired and not owner_has_lease.is_set():
            owner_has_lease.set()
            assert allow_reservation.wait(timeout=5)
        return acquired

    async def sync() -> None:
        nonlocal sync_count
        with sync_lock:
            sync_count += 1
        corpus = CorpusPaths(configured.opinions_data_dir)
        upsert_documents(corpus, [DocumentRow(document_id="reader:concurrent", reader_id="concurrent", title="Doc")])
        upsert_highlights(
            corpus,
            [
                HighlightRow(
                    highlight_id="rw:concurrent",
                    document_id="reader:concurrent",
                    reader_id="concurrent",
                    text="Concurrent evidence.",
                    highlighted_at="2026-06-10T00:00:00+00:00",
                )
            ],
        )

    def invoke(now: datetime):
        with SessionLocal() as session:
            return asyncio.run(
                start_opinion_cycle(session=session, settings=configured, sync_corpus=sync, now=now)
            )

    monkeypatch.setattr(cycles_module, "acquire_lease", paused_acquire)
    first = asyncio.create_task(asyncio.to_thread(invoke, datetime(2026, 6, 12, tzinfo=UTC)))
    assert await asyncio.to_thread(owner_has_lease.wait, 5)
    second = asyncio.create_task(asyncio.to_thread(invoke, datetime(2026, 6, 12, 1, tzinfo=UTC)))
    await asyncio.sleep(0.1)
    allow_reservation.set()
    same_week = await asyncio.gather(first, second)

    cross_week = await asyncio.gather(
        asyncio.to_thread(invoke, datetime(2026, 6, 19, tzinfo=UTC)),
        asyncio.to_thread(invoke, datetime(2026, 6, 19, 1, tzinfo=UTC)),
    )

    assert sync_count == 1
    assert len({result.cycle_id for result in same_week + cross_week}) == 1
    assert sorted(result.created for result in same_week) == [False, True]
    assert all(result.created is False for result in cross_week)
