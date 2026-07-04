"""Braintrust-native opinion eval: run the initial proposal phase per week and stream experiments."""

from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

from opinions_agent.agent import DeterministicOpinionAgent, ThinHarnessOpinionAgent
from opinions_agent.config import OPINION_AGENT_MODEL, OPINION_AGENT_REASONING_EFFORT, Settings
from opinions_agent.corpus import CorpusPaths
from opinions_agent.db import init_db, make_engine, make_sessionmaker
from opinions_agent.evals.proposals import parse_proposals
from opinions_agent.evals.scorers import evidence_precision, evidence_recall, make_opinion_judges
from opinions_agent.evals.targets import (
    WeekCase,
    build_seed_opinions,
    default_base_opinions_path,
    load_week_cases,
    verify_week_partition,
)
from opinions_agent.opinions_doc import OpinionsDocument, load_opinions
from opinions_agent.sample_run import prepare_sample_settings, sample_run_id, week_window_for_label
from opinions_agent.selection import select_run_highlights
from opinions_agent.telegram import FakeTelegramClient
from opinions_agent.tracing import flush_braintrust_tracing
from opinions_agent.workflow import start_opinion_run

EVAL_PROJECT_NAME = "opinions-agent"
TARGETS_DATASET_NAME = "opinion-targets"


async def run_opinion_eval(
    settings: Settings,
    weeks: list[str],
    *,
    deterministic: bool = False,
    experiment_name: str | None = None,
    max_concurrency: int = 3,
):
    if not settings.braintrust_api_key or not settings.braintrust_project_id:
        raise ValueError("BRAINTRUST_API_KEY and BRAINTRUST_PROJECT_ID are required to run evals")
    from braintrust import EvalAsync, EvalCase

    cases = load_week_cases()
    cases_by_week = {case.week: case for case in cases}
    normalized = [week.strip().upper() for week in weeks]
    unknown = [week for week in normalized if week not in cases_by_week]
    if unknown:
        raise ValueError(f"weeks not in eval targets: {unknown} (available: {[case.week for case in cases]})")
    selected_cases = [case for case in cases if case.week in set(normalized)]

    corpus = CorpusPaths(settings.opinions_data_dir)
    for case in selected_cases:
        verify_week_partition(case, corpus)
    base_doc = load_opinions(default_base_opinions_path())
    all_rows = {case.week: _dataset_row(case, cases, corpus) for case in cases}
    _sync_targets_dataset(settings, list(all_rows.values()))
    data = [all_rows[case.week] for case in selected_cases]

    async def task(input: dict) -> dict:
        return await run_week_case(
            settings,
            cases_by_week[input["week"]],
            cases,
            base_doc=base_doc,
            deterministic=deterministic,
            parent=_current_parent(),
        )

    opinion_quality, opinion_attempted = make_opinion_judges(settings)
    result = await EvalAsync(
        EVAL_PROJECT_NAME,
        project_id=settings.braintrust_project_id,
        data=[
            EvalCase(
                input=row["input"], expected=row["expected"], metadata=row["metadata"], tags=[row["metadata"]["week"]]
            )
            for row in data
        ],
        task=task,
        scores=[evidence_recall, evidence_precision, opinion_quality, opinion_attempted],
        experiment_name=experiment_name,
        metadata={
            "model": OPINION_AGENT_MODEL,
            "reasoning_effort": OPINION_AGENT_REASONING_EFFORT,
            "environment": settings.environment,
            "agent": "deterministic" if deterministic else "thinharness",
            "weeks": [case.week for case in selected_cases],
        },
        max_concurrency=max_concurrency,
    )
    flush_braintrust_tracing()
    return result


async def rescore_opinion_eval(
    settings: Settings,
    *,
    source_experiment: str,
    experiment_name: str | None = None,
    max_concurrency: int = 3,
):
    """Re-score stored outputs from an existing experiment into a new experiment, without re-running the agent."""
    if not settings.braintrust_api_key or not settings.braintrust_project_id:
        raise ValueError("BRAINTRUST_API_KEY and BRAINTRUST_PROJECT_ID are required to run evals")
    from braintrust import EvalAsync, EvalCase

    rows = _fetch_experiment_rows(settings, source_experiment)
    outputs_by_week = {row["input"]["week"]: row["output"] for row in rows}

    async def task(input: dict) -> dict:
        return outputs_by_week[input["week"]]

    opinion_quality, opinion_attempted = make_opinion_judges(settings)
    result = await EvalAsync(
        EVAL_PROJECT_NAME,
        project_id=settings.braintrust_project_id,
        data=[
            EvalCase(
                input=row["input"], expected=row["expected"], metadata=row["metadata"], tags=[row["input"]["week"]]
            )
            for row in rows
        ],
        task=task,
        scores=[evidence_recall, evidence_precision, opinion_quality, opinion_attempted],
        experiment_name=experiment_name,
        metadata={"rescored_from": source_experiment, "environment": settings.environment},
        max_concurrency=max_concurrency,
    )
    return result


def _fetch_experiment_rows(settings: Settings, experiment_name: str) -> list[dict]:
    import gzip
    import json

    import httpx

    headers = {"Authorization": f"Bearer {settings.braintrust_api_key}"}
    listing = httpx.get(
        "https://api.braintrust.dev/v1/experiment",
        params={"project_id": settings.braintrust_project_id, "experiment_name": experiment_name},
        headers=headers,
        timeout=30,
    )
    listing.raise_for_status()
    experiments = [obj for obj in listing.json()["objects"] if obj["name"] == experiment_name]
    if not experiments:
        raise ValueError(f"experiment not found in Braintrust project: {experiment_name}")
    fetch = httpx.post(
        f"https://api.braintrust.dev/v1/experiment/{experiments[0]['id']}/fetch",
        headers=headers,
        json={"limit": 1000},
        timeout=120,
        follow_redirects=True,
    )
    fetch.raise_for_status()
    try:
        payload = json.loads(fetch.content)
    except ValueError:
        payload = json.loads(gzip.decompress(fetch.content))
    rows = [
        {
            "input": event["input"],
            "expected": event["expected"],
            "output": event["output"],
            "metadata": {**(event.get("metadata") or {}), "rescored_from": experiment_name},
        }
        for event in payload["events"]
        if (event.get("span_attributes") or {}).get("type") == "eval"
    ]
    if not rows:
        raise ValueError(f"experiment {experiment_name} has no eval rows to rescore")
    missing = [row["input"].get("week") for row in rows if not row.get("output") or not row.get("expected")]
    if missing:
        raise ValueError(f"experiment {experiment_name} rows missing output or expected: {missing}")
    return sorted(rows, key=lambda row: row["input"]["week"])


async def run_week_case(
    settings: Settings,
    case: WeekCase,
    all_cases: list[WeekCase],
    *,
    base_doc: OpinionsDocument,
    deterministic: bool,
    parent: str,
) -> dict:
    run_id = f"{sample_run_id(case.week)}-eval"
    seed_doc = build_seed_opinions(base_doc, all_cases, case.week)
    with tempfile.TemporaryDirectory() as seed_dir:
        seed_path = Path(seed_dir) / "OPINIONS.md"
        seed_path.write_text(seed_doc.render(), encoding="utf-8")
        sample_settings = prepare_sample_settings(settings=settings, run_id=run_id, opinions_file=seed_path)
    sample_settings = replace(
        sample_settings,
        braintrust_parent=parent,
        telegram_allowed_chat_id=settings.telegram_allowed_chat_id or 1,
    )
    engine = make_engine(sample_settings.database_url)
    init_db(engine)
    SessionLocal = make_sessionmaker(engine)
    telegram = FakeTelegramClient()
    agent = DeterministicOpinionAgent() if deterministic else ThinHarnessOpinionAgent()
    window_start, window_end = week_window_for_label(CorpusPaths(sample_settings.opinions_data_dir), case.week)
    with SessionLocal() as session:
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
        return {"week": case.week, "run_id": run_id, "status": "no_evidence", "proposals": [], "messages": []}
    messages = [spec for _, spec in telegram.sent]
    return {
        "week": case.week,
        "run_id": run_id,
        "status": run.status,
        "proposals": [proposal.model_dump() for proposal in parse_proposals(messages)],
        "messages": [spec.text for spec in messages],
        "run_dir": str(sample_settings.runs_dir / "active" / run_id),
    }


def _dataset_row(case: WeekCase, all_cases: list[WeekCase], corpus: CorpusPaths) -> dict:
    start, end = week_window_for_label(corpus, case.week)
    selected, _ = select_run_highlights(corpus, start, end)
    prior_weeks = [earlier.week for earlier in all_cases[: [c.week for c in all_cases].index(case.week)]]
    return {
        "input": {
            "week": case.week,
            "opinions_seed": f"canonical-through-{prior_weeks[-1]}" if prior_weeks else "base",
            "selected_evidence": [
                {
                    "evidence_id": highlight.highlight_id,
                    "evidence_kind": highlight.evidence_kind,
                    "title": highlight.document_title,
                    "text": highlight.text,
                    "note": highlight.note,
                }
                for highlight in selected
            ],
        },
        "expected": {
            "targets": [target.model_dump(mode="json") for target in case.targets],
            "not_converted": [evidence.model_dump(mode="json") for evidence in case.not_converted],
        },
        "metadata": {"week": case.week, "source_file": "EVAL_TARGETS.md"},
    }


def _sync_targets_dataset(settings: Settings, rows: list[dict]) -> None:
    from braintrust import init_dataset

    dataset = init_dataset(project_id=settings.braintrust_project_id, name=TARGETS_DATASET_NAME)
    for row in rows:
        dataset.insert(
            input=row["input"],
            expected=row["expected"],
            metadata=row["metadata"],
            id=row["metadata"]["week"],
        )
    dataset.flush()


def _current_parent() -> str:
    """Parent agent OTLP traces on the running experiment.

    The Braintrust OTel endpoint accepts project/experiment parents but rejects span slugs
    (403), so per-case nesting is not possible; experiment-level nesting keeps eval traces
    with their experiment instead of in project logs.
    """
    try:
        from braintrust import current_span

        span = current_span()
        parent_object_id = getattr(span, "parent_object_id", None)
        if str(getattr(span, "parent_object_type", "")) == "experiment" and parent_object_id is not None:
            return f"experiment_id:{parent_object_id.get()}"
    except Exception:
        pass
    return ""
