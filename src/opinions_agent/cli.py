from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

import uvicorn
from sqlalchemy import select

from opinions_agent.agent import DeterministicOpinionAgent, ThinHarnessOpinionAgent
from opinions_agent.config import get_settings
from opinions_agent.corpus import CorpusPaths, init_data_dirs
from opinions_agent.cycles import retry_stopped_cycle, retry_stopped_snapshot, start_opinion_cycle
from opinions_agent.db import init_db, make_engine, make_sessionmaker
from opinions_agent.models import CycleStatus, OpinionCycle, OpinionRun
from opinions_agent.reader import ReaderClient, parse_iso, sync_reader
from opinions_agent.repo_checkout import ensure_opinions_repo
from opinions_agent.sample_run import (
    prepare_sample_session_settings,
    prepare_sample_settings,
    sample_run_id,
    sample_session_dir,
    sample_session_settings,
    week_window_for_label,
)
from opinions_agent.selection import RunPaths, cleanup_completed_runs
from opinions_agent.telegram import FakeTelegramClient, TelegramClient
from opinions_agent.worker import reconcile_startup
from opinions_agent.workflow import (
    ActiveRunError,
    abandon_run,
    handle_telegram_update,
    next_update_offset,
    send_snapshot_failure_notice,
    start_opinion_run,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="opinions-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("serve")
    subparsers.add_parser("init-db")
    subparsers.add_parser("init-runtime")
    subparsers.add_parser("sync")
    subparsers.add_parser("opinion-cycle")
    retry_cycle = subparsers.add_parser("retry-cycle")
    retry_cycle.add_argument("cycle_id")
    subparsers.add_parser("cron-trigger")
    run_parser = subparsers.add_parser("opinion-run")
    run_parser.add_argument("--deterministic-agent", action="store_true")
    run_parser.add_argument("--window-start", help="ISO timestamp lower bound override")
    run_parser.add_argument("--window-end", help="ISO timestamp upper bound override")
    run_parser.add_argument("--skip-sync", action="store_true")
    sample = subparsers.add_parser("sample-run")
    sample.add_argument("week", help="Chronological corpus week label, such as W04")
    sample.add_argument("--opinions-file", default="OPINIONS.md")
    sample.add_argument("--sources-file")
    sample.add_argument("--deterministic-agent", action="store_true")
    sample.add_argument("--send-telegram", action="store_true")
    sample.add_argument("--sync", action="store_true")
    sample_session = subparsers.add_parser("sample-session")
    sample_session_subparsers = sample_session.add_subparsers(dest="sample_session_command", required=True)
    sample_session_init = sample_session_subparsers.add_parser("init")
    sample_session_init.add_argument("name")
    sample_session_init.add_argument("--opinions-file", default="OPINIONS.md")
    sample_session_init.add_argument("--sources-file")
    sample_session_run = sample_session_subparsers.add_parser("run")
    sample_session_run.add_argument("name")
    sample_session_run.add_argument("week", help="Chronological corpus week label, such as W04")
    sample_session_run.add_argument("--deterministic-agent", action="store_true")
    sample_session_run.add_argument("--send-telegram", action="store_true")
    sample_session_poll = sample_session_subparsers.add_parser("poll")
    sample_session_poll.add_argument("name")
    sample_session_poll.add_argument("--once", action="store_true")
    eval_parser = subparsers.add_parser("eval")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_run = eval_subparsers.add_parser("run")
    eval_run.add_argument("--weeks", nargs="+", required=True, help="Eval week labels, such as W04 W05")
    eval_run.add_argument("--deterministic-agent", action="store_true")
    eval_run.add_argument("--variant", help="Variant name; the run is named <variant>-r<run> with cohort metadata")
    eval_run.add_argument("--run", type=int, default=1, help="Replicate number within the variant")
    eval_run.add_argument("--experiment", help="Ad-hoc Braintrust experiment name (smoke runs; no cohort metadata)")
    eval_run.add_argument("--max-concurrency", type=int, default=3)
    eval_rescore = eval_subparsers.add_parser("rescore")
    eval_rescore.add_argument("--from-experiment", required=True, help="Existing Braintrust experiment to re-score")
    eval_rescore.add_argument("--experiment", help="Name override; defaults to <variant>-r<run>-rs-<scoring date>")
    eval_rescore.add_argument("--max-concurrency", type=int, default=3)
    eval_v2 = eval_subparsers.add_parser("v2")
    eval_v2_subparsers = eval_v2.add_subparsers(dest="eval_v2_command", required=True)
    eval_v2_run = eval_v2_subparsers.add_parser("run")
    eval_v2_run.add_argument("--weeks", nargs="+", required=True, help="Eval week labels, such as W04 W05")
    eval_v2_run.add_argument("--deterministic-agent", action="store_true")
    eval_v2_run.add_argument("--variant", help="Variant name; the run is named <variant>-r<run> with cohort metadata")
    eval_v2_run.add_argument("--run", type=int, default=1, help="Replicate number within the variant")
    eval_v2_run.add_argument("--experiment", help="Ad-hoc Braintrust experiment name (smoke runs; no cohort metadata)")
    eval_v2_run.add_argument("--max-concurrency", type=int, default=3)
    eval_v2_rescore = eval_v2_subparsers.add_parser("rescore")
    eval_v2_rescore.add_argument("--from-experiment", required=True, help="Existing Braintrust experiment to re-score")
    eval_v2_rescore.add_argument("--experiment", help="Name override; defaults to <variant>-r<run>-rs-<scoring date>")
    eval_v2_rescore.add_argument("--max-concurrency", type=int, default=3)
    abandon = subparsers.add_parser("abandon-run")
    abandon.add_argument("run_id")
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
    if args.command == "cron-trigger":
        await _cron_trigger(settings)
        return
    engine = make_engine(settings.database_url)
    SessionLocal = make_sessionmaker(engine)
    corpus = CorpusPaths(settings.opinions_data_dir)

    if args.command == "init-db":
        init_db(engine)
        return
    if args.command == "init-runtime":
        from opinions_agent.config import is_railway_runtime, validate_web_settings

        if settings.environment in {"staging", "prod"} or is_railway_runtime():
            validate_web_settings(settings)
        init_data_dirs(corpus)
        RunPaths(settings.runs_dir).active_dir.mkdir(parents=True, exist_ok=True)
        _migrate()
        with SessionLocal() as session:
            active_cycle = session.scalar(
                select(OpinionCycle).where(
                    OpinionCycle.status.in_(
                        [CycleStatus.STARTING.value, CycleStatus.ACTIVE.value, CycleStatus.STOPPED.value]
                    )
                )
            )
        ensure_opinions_repo(settings, refresh=active_cycle is None)
        print("runtime initialized")
        return
    if args.command == "sync":
        result = await sync_reader(ReaderClient(settings.readwise_token), corpus)
        print(
            f"fetched {result.fetched_rows} rows: "
            f"{result.new_documents} new documents, {result.new_highlights} new highlights"
        )
        return
    if args.command == "opinion-cycle":
        with SessionLocal() as session:
            telegram = TelegramClient(settings.telegram_bot_token)

            async def notify_failure(cycle) -> None:
                await send_snapshot_failure_notice(
                    session=session,
                    settings=settings,
                    telegram=telegram,
                    cycle=cycle,
                )

            result = await start_opinion_cycle(
                session=session,
                settings=settings,
                sync_corpus=lambda: sync_reader(ReaderClient(settings.readwise_token), corpus),
                notify_failure=notify_failure,
            )
        print(
            f"cycle {result.cycle_id}: {result.status}, {result.batch_count} batches, {result.result_code}"
        )
        return
    if args.command == "retry-cycle":
        with SessionLocal() as session:
            reconcile_startup(session, settings)
            cycle = session.get(OpinionCycle, args.cycle_id)
            if cycle is not None and cycle.failure_code == "snapshot_failed":
                telegram = TelegramClient(settings.telegram_bot_token)

                async def notify_failure(cycle) -> None:
                    await send_snapshot_failure_notice(
                        session=session,
                        settings=settings,
                        telegram=telegram,
                        cycle=cycle,
                    )

                result = await retry_stopped_snapshot(
                    session=session,
                    settings=settings,
                    cycle_id=args.cycle_id,
                    sync_corpus=lambda: sync_reader(ReaderClient(settings.readwise_token), corpus),
                    notify_failure=notify_failure,
                )
                print(f"cycle {result.cycle_id}: {result.status}, {result.batch_count} batches, {result.result_code}")
            else:
                batch = retry_stopped_cycle(session, args.cycle_id)
                print(f"queued cycle {args.cycle_id} batch {batch.batch_number}")
        return
    if args.command == "sample-run":
        if args.sync:
            await sync_reader(ReaderClient(settings.readwise_token), corpus)
        run_id = sample_run_id(args.week)
        window_start, window_end = week_window_for_label(corpus, args.week)
        sample_settings = prepare_sample_settings(
            settings=settings,
            run_id=run_id,
            opinions_file=Path(args.opinions_file).expanduser(),
            sources_file=Path(args.sources_file).expanduser() if args.sources_file else None,
        )
        sample_engine = make_engine(sample_settings.database_url)
        init_db(sample_engine)
        SampleSessionLocal = make_sessionmaker(sample_engine)
        agent = DeterministicOpinionAgent() if args.deterministic_agent else ThinHarnessOpinionAgent()
        telegram = TelegramClient(settings.telegram_bot_token) if args.send_telegram else FakeTelegramClient()
        with SampleSessionLocal() as session:
            run = await start_opinion_run(
                session=session,
                settings=sample_settings,
                agent=agent,
                telegram=telegram,
                window_start=window_start,
                window_end=window_end,
                run_id=run_id,
            )
        if run is None:
            print(f"no highlights in {args.week} ({window_start.isoformat()} to {window_end.isoformat()})")
            return
        run_dir = sample_settings.runs_dir / "active" / run_id
        print(f"created sample run {run.id} ({run.status})")
        print(f"run dir: {run_dir}")
        print(f"opinion artifact copy: {sample_settings.opinions_target_path}")
        print(f"source artifact copy: {sample_settings.opinions_sources_path}")
        if isinstance(telegram, FakeTelegramClient):
            print(f"fake telegram messages: {len(telegram.sent)}")
        else:
            print("telegram messages sent")
        return
    if args.command == "sample-session":
        if args.sample_session_command == "init":
            sample_settings = prepare_sample_session_settings(
                settings=settings,
                name=args.name,
                opinions_file=Path(args.opinions_file).expanduser(),
                sources_file=Path(args.sources_file).expanduser() if args.sources_file else None,
            )
            sample_engine = make_engine(sample_settings.database_url)
            init_db(sample_engine)
            RunPaths(sample_settings.runs_dir).active_dir.mkdir(parents=True, exist_ok=True)
            print(f"created sample session {args.name}")
            print(f"session dir: {sample_session_dir(settings, args.name)}")
            print(f"opinion artifact copy: {sample_settings.opinions_target_path}")
            print(f"source artifact copy: {sample_settings.opinions_sources_path}")
            return
        sample_settings = sample_session_settings(settings=settings, name=args.name)
        sample_engine = make_engine(sample_settings.database_url)
        init_db(sample_engine)
        SampleSessionLocal = make_sessionmaker(sample_engine)
        if args.sample_session_command == "run":
            window_start, window_end = week_window_for_label(CorpusPaths(sample_settings.opinions_data_dir), args.week)
            run_id = sample_run_id(args.week)
            agent = DeterministicOpinionAgent() if args.deterministic_agent else ThinHarnessOpinionAgent()
            telegram = TelegramClient(settings.telegram_bot_token) if args.send_telegram else FakeTelegramClient()
            with SampleSessionLocal() as session:
                try:
                    run = await start_opinion_run(
                        session=session,
                        settings=sample_settings,
                        agent=agent,
                        telegram=telegram,
                        window_start=window_start,
                        window_end=window_end,
                        run_id=run_id,
                    )
                except ActiveRunError as exc:
                    print(str(exc))
                    return
            if run is None:
                print(f"no highlights in {args.week} ({window_start.isoformat()} to {window_end.isoformat()})")
                return
            print(f"created sample session run {run.id} ({run.status})")
            print(f"session dir: {sample_session_dir(settings, args.name)}")
            print(f"run dir: {sample_settings.runs_dir / 'active' / run.id}")
            if isinstance(telegram, FakeTelegramClient):
                print(f"fake telegram messages: {len(telegram.sent)}")
            else:
                print("telegram messages sent")
            return
        if args.sample_session_command == "poll":
            await _poll(sample_settings, SampleSessionLocal, once=args.once)
            return
    if args.command == "eval":
        if args.eval_command == "run":
            from opinions_agent.evals.runner import run_opinion_eval

            result = await run_opinion_eval(
                settings,
                args.weeks,
                deterministic=args.deterministic_agent,
                variant=args.variant,
                run=args.run,
                experiment_name=args.experiment,
                max_concurrency=args.max_concurrency,
            )
            print(result.summary)
            return
        if args.eval_command == "rescore":
            from opinions_agent.evals.runner import rescore_opinion_eval

            result = await rescore_opinion_eval(
                settings,
                source_experiment=args.from_experiment,
                experiment_name=args.experiment,
                max_concurrency=args.max_concurrency,
            )
            print(result.summary)
            return
        if args.eval_command == "v2":
            from opinions_agent.evals.v2.runner import rescore_opinion_eval, run_opinion_eval

            if args.eval_v2_command == "run":
                result = await run_opinion_eval(
                    settings,
                    args.weeks,
                    deterministic=args.deterministic_agent,
                    variant=args.variant,
                    run=args.run,
                    experiment_name=args.experiment,
                    max_concurrency=args.max_concurrency,
                )
            else:
                result = await rescore_opinion_eval(
                    settings,
                    source_experiment=args.from_experiment,
                    experiment_name=args.experiment,
                    max_concurrency=args.max_concurrency,
                )
            print(result.summary)
            return

    with SessionLocal() as session:
        if args.command == "opinion-run":
            ensure_opinions_repo(settings)
            if not args.skip_sync:
                await sync_reader(ReaderClient(settings.readwise_token), corpus)
            cleanup_completed_runs(RunPaths(settings.runs_dir), retention_days=settings.completed_run_retention_days)
            agent = DeterministicOpinionAgent() if args.deterministic_agent else ThinHarnessOpinionAgent()
            telegram = (
                FakeTelegramClient() if settings.use_fake_telegram else TelegramClient(settings.telegram_bot_token)
            )
            try:
                run = await start_opinion_run(
                    session=session,
                    settings=settings,
                    agent=agent,
                    telegram=telegram,
                    window_start=parse_iso(args.window_start),
                    window_end=parse_iso(args.window_end),
                )
            except ActiveRunError as exc:
                print(str(exc))
                return
            if run is None:
                print("no highlights in the current window")
            else:
                print(f"created run {run.id} ({run.status})")
            return
        if args.command == "abandon-run":
            run = session.get(OpinionRun, args.run_id)
            if run is None:
                raise SystemExit(f"run not found: {args.run_id}")
            abandon_run(session, settings, run)
            print(f"abandoned run {run.id}")
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
                agent=ThinHarnessOpinionAgent(),
                telegram=TelegramClient(settings.telegram_bot_token),
                update=update,
            )
            print(result)
            return
        if args.command == "set-telegram-webhook":
            await _set_webhook(settings, args.url)
            return
    raise ValueError(args.command)


def _migrate() -> None:
    from alembic.config import Config

    from alembic import command

    project_root = Path(__file__).resolve().parents[2]
    command.upgrade(Config(str(project_root / "alembic.ini")), "head")


async def _cron_trigger(settings) -> None:
    import httpx

    from opinions_agent.config import validate_cron_settings

    validate_cron_settings(settings)
    async with httpx.AsyncClient(timeout=600) as client:
        response = await client.post(
            settings.opinions_start_url,
            headers={"Authorization": f"Bearer {settings.opinions_start_secret}"},
        )
    if response.status_code not in {200, 202}:
        raise SystemExit(f"cycle start failed with HTTP {response.status_code}")
    payload = response.json()
    print(
        f"cycle {payload.get('cycle_id')}: {payload.get('status')}, "
        f"{payload.get('batch_count')} batches, {payload.get('result_code')}"
    )


async def _poll(settings, SessionLocal, *, once: bool) -> None:
    telegram = TelegramClient(settings.telegram_bot_token)
    agent = ThinHarnessOpinionAgent()
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
