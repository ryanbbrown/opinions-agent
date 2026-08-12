from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from opinions_agent.agent import ThinHarnessOpinionAgent
from opinions_agent.config import get_settings, is_railway_runtime, validate_web_settings
from opinions_agent.corpus import CorpusPaths, init_data_dirs
from opinions_agent.cycles import start_opinion_cycle as create_opinion_cycle
from opinions_agent.db import make_engine, make_sessionmaker
from opinions_agent.diagnostics import log_operational_failure
from opinions_agent.reader import ReaderClient, sync_reader
from opinions_agent.selection import RunPaths
from opinions_agent.telegram import TelegramClient
from opinions_agent.worker import reconcile_startup, worker_loop
from opinions_agent.workflow import handle_telegram_update, send_cycle_failure_notice, send_snapshot_failure_notice

settings = get_settings()
engine = make_engine(settings.database_url)
SessionLocal = make_sessionmaker(engine)
startup_ready = False
LOGGER = logging.getLogger(__name__)


def _set_startup_ready(value: bool) -> None:
    global startup_ready
    startup_ready = value


def _secret_matches(provided: str | None, expected: str) -> bool:
    return bool(expected) and secrets.compare_digest((provided or "").encode(), expected.encode())


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.environment in {"staging", "prod"} or is_railway_runtime():
        validate_web_settings(settings)
    init_data_dirs(CorpusPaths(settings.opinions_data_dir))
    RunPaths(settings.runs_dir).active_dir.mkdir(parents=True, exist_ok=True)
    telegram = TelegramClient(settings.telegram_bot_token)
    with SessionLocal() as session:
        reconciliation = reconcile_startup(session, settings)
        for cycle in reconciliation.stopped_cycles:
            try:
                await send_snapshot_failure_notice(session=session, settings=settings, telegram=telegram, cycle=cycle)
            except Exception as exc:
                log_operational_failure(LOGGER, settings, exc, phase="startup_snapshot_notice", cycle_id=cycle.id)
        for run in reconciliation.stopped_runs:
            try:
                await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=run)
            except Exception as exc:
                log_operational_failure(
                    LOGGER,
                    settings,
                    exc,
                    phase="startup_run_notice",
                    cycle_id=run.cycle_id or "none",
                    batch=run.batch,
                    run_id=run.id,
                )
    _set_startup_ready(reconciliation.healthy)
    stop = asyncio.Event()
    task = asyncio.create_task(
        worker_loop(
            SessionLocal,
            settings,
            ThinHarnessOpinionAgent(),
            telegram,
            stop,
            _set_startup_ready,
        )
    )
    try:
        yield
    finally:
        _set_startup_ready(False)
        stop.set()
        await task


app = FastAPI(lifespan=lifespan)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@app.get("/healthz")
def healthz() -> dict[str, str]:
    if not startup_ready:
        raise HTTPException(status_code=503, detail="startup reconciliation is incomplete")
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    for path in (settings.opinions_data_dir, settings.runs_dir, settings.opinions_repo_dir):
        if not path.is_dir():
            raise HTTPException(status_code=503, detail="required volume path is unavailable")
    return {"status": "ok"}


@app.post("/internal/opinion-cycle/start")
async def start_opinion_cycle(
    response: Response,
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> dict[str, str | int]:
    expected = f"Bearer {settings.opinions_start_secret}"
    if not _secret_matches(authorization, expected):
        raise HTTPException(status_code=401, detail="invalid start secret")

    async def sync_corpus() -> object:
        return await sync_reader(ReaderClient(settings.readwise_token), CorpusPaths(settings.opinions_data_dir))

    async def notify_failure(cycle) -> None:
        await send_snapshot_failure_notice(
            session=session,
            settings=settings,
            telegram=TelegramClient(settings.telegram_bot_token),
            cycle=cycle,
        )

    result = await create_opinion_cycle(
        session=session,
        settings=settings,
        sync_corpus=sync_corpus,
        notify_failure=notify_failure,
    )
    if result.result_code == "stopped":
        response.status_code = 409
    elif result.created and result.result_code != "no_evidence":
        response.status_code = 202
    return {
        "cycle_id": result.cycle_id,
        "status": result.status,
        "batch_count": result.batch_count,
        "result_code": result.result_code,
    }


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    session: Session = Depends(get_session),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    expected = settings.telegram_webhook_secret
    if expected and not _secret_matches(x_telegram_bot_api_secret_token, expected):
        raise HTTPException(status_code=401, detail="invalid telegram webhook secret")
    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=ThinHarnessOpinionAgent(),
        telegram=TelegramClient(settings.telegram_bot_token),
        update=await request.json(),
    )
    return {"status": result}
