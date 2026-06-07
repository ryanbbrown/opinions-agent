from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy.orm import Session

from opinions_agent.agent import ThinHarnessSummaryAgent
from opinions_agent.config import get_settings
from opinions_agent.db import make_engine, make_sessionmaker
from opinions_agent.telegram import TelegramClient
from opinions_agent.workflow import handle_telegram_update

settings = get_settings()
engine = make_engine(settings.database_url)
SessionLocal = make_sessionmaker(engine)

app = FastAPI()


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    session: Session = Depends(get_session),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=401, detail="invalid telegram webhook secret")
    result = await handle_telegram_update(
        session=session,
        settings=settings,
        agent=ThinHarnessSummaryAgent(),
        telegram=TelegramClient(settings.telegram_bot_token),
        update=await request.json(),
    )
    return {"status": result}
