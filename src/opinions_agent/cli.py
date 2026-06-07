from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

import uvicorn

from opinions_agent.agent import DeterministicSummaryAgent, ThinHarnessSummaryAgent
from opinions_agent.config import get_settings
from opinions_agent.db import init_db, make_engine, make_sessionmaker
from opinions_agent.readwise import ReadwiseClient, sync_readwise
from opinions_agent.repo_checkout import ensure_opinions_repo
from opinions_agent.telegram import FakeTelegramClient, TelegramClient
from opinions_agent.workflow import handle_telegram_update, next_update_offset, summarize_recent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="opinions-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("serve")
    subparsers.add_parser("init-db")
    subparsers.add_parser("readwise-sync")
    daily = subparsers.add_parser("daily-run")
    daily.add_argument("--limit", type=int, default=10)
    summarize = subparsers.add_parser("summarize-recent")
    summarize.add_argument("--limit", type=int, default=10)
    summarize.add_argument("--deterministic-agent", action="store_true")
    poll = subparsers.add_parser("telegram-poll")
    poll.add_argument("--once", action="store_true")
    process = subparsers.add_parser("process-pending-telegram")
    process.add_argument("update_json")
    webhook = subparsers.add_parser("set-telegram-webhook")
    webhook.add_argument("url")
    args = parser.parse_args(argv)

    if args.command == "serve":
        uvicorn.run("opinions_agent.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
        return
    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    SessionLocal = make_sessionmaker(engine)

    if args.command == "init-db":
        init_db(engine)
        return

    with SessionLocal() as session:
        if args.command == "readwise-sync":
            inserted = await sync_readwise(session, ReadwiseClient(settings.readwise_token))
            print(f"synced {inserted} new highlights")
            return
        if args.command == "summarize-recent":
            ensure_opinions_repo(settings)
            agent = DeterministicSummaryAgent() if args.deterministic_agent else ThinHarnessSummaryAgent()
            telegram = (
                FakeTelegramClient() if settings.use_fake_telegram else TelegramClient(settings.telegram_bot_token)
            )
            run = await summarize_recent(
                session=session,
                settings=settings,
                agent=agent,
                telegram=telegram,
                limit=args.limit,
            )
            print(f"created run {run.id}" if run else "no highlights to summarize")
            return
        if args.command == "daily-run":
            ensure_opinions_repo(settings)
            await sync_readwise(session, ReadwiseClient(settings.readwise_token))
            telegram = (
                FakeTelegramClient() if settings.use_fake_telegram else TelegramClient(settings.telegram_bot_token)
            )
            run = await summarize_recent(
                session=session,
                settings=settings,
                agent=ThinHarnessSummaryAgent(),
                telegram=telegram,
                limit=args.limit,
            )
            print(f"created run {run.id}" if run else "no highlights to summarize")
            return
        if args.command == "telegram-poll":
            await _poll(settings, SessionLocal, once=args.once)
            return
        if args.command == "process-pending-telegram":
            import json

            update: dict[str, Any] = json.loads(args.update_json)
            result = await handle_telegram_update(
                session=session,
                settings=settings,
                agent=ThinHarnessSummaryAgent(),
                telegram=TelegramClient(settings.telegram_bot_token),
                update=update,
            )
            print(result)
            return
        if args.command == "set-telegram-webhook":
            await _set_webhook(settings, args.url)
            return
    raise ValueError(args.command)


async def _poll(settings, SessionLocal, *, once: bool) -> None:
    telegram = TelegramClient(settings.telegram_bot_token)
    agent = ThinHarnessSummaryAgent()
    while True:
        with SessionLocal() as session:
            offset = next_update_offset(session)
        updates = await telegram.get_updates(offset=offset)
        for update in updates:
            with SessionLocal() as session:
                await handle_telegram_update(
                    session=session,
                    settings=settings,
                    agent=agent,
                    telegram=telegram,
                    update=update,
                )
        if once:
            return


async def _set_webhook(settings, url: str) -> None:
    import httpx

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
            json={"url": url, "secret_token": settings.telegram_webhook_secret},
        )
        response.raise_for_status()
        print(response.json())
