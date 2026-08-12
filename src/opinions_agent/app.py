from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from opinions_agent.agent import ThinHarnessOpinionAgent
from opinions_agent.config import get_settings, validate_web_settings
from opinions_agent.corpus import CorpusPaths, init_data_dirs
from opinions_agent.cycles import start_opinion_cycle as create_opinion_cycle
from opinions_agent.db import make_engine, make_sessionmaker
from opinions_agent.reader import ReaderClient, sync_reader
from opinions_agent.selection import RunPaths
from opinions_agent.telegram import TelegramClient
from opinions_agent.worker import reconcile_startup, worker_loop
from opinions_agent.workflow import handle_telegram_update, send_cycle_failure_notice

settings = get_settings()
engine = make_engine(settings.database_url)
SessionLocal = make_sessionmaker(engine)
startup_ready = False


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global startup_ready
    if settings.volume_mount_path is not None:
        validate_web_settings(settings)
    init_data_dirs(CorpusPaths(settings.opinions_data_dir))
    RunPaths(settings.runs_dir).active_dir.mkdir(parents=True, exist_ok=True)
    telegram = TelegramClient(settings.telegram_bot_token)
    with SessionLocal() as session:
        stopped_runs = reconcile_startup(session, settings)
        for run in stopped_runs:
            await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=run)
    startup_ready = True
    stop = asyncio.Event()
    task = asyncio.create_task(
        worker_loop(
            SessionLocal,
            settings,
            ThinHarnessOpinionAgent(),
            telegram,
            stop,
        )
    )
    try:
        yield
    finally:
        startup_ready = False
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
    if not settings.opinions_start_secret or not secrets.compare_digest(authorization or "", expected):
        raise HTTPException(status_code=401, detail="invalid start secret")
    async def sync_corpus() -> object:
        return await sync_reader(ReaderClient(settings.readwise_token), CorpusPaths(settings.opinions_data_dir))

    result = await create_opinion_cycle(session=session, settings=settings, sync_corpus=sync_corpus)
    if result.result_code == "stopped":
        response.status_code = 409
    elif result.created:
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
    if expected and not secrets.compare_digest(x_telegram_bot_api_secret_token or "", expected):
        raise HTTPException(status_code=401, detail="invalid telegram webhook secret")
    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=ThinHarnessOpinionAgent(),
        telegram=TelegramClient(settings.telegram_bot_token),
        update=await request.json(),
    )
    return {"status": result}
