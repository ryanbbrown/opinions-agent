#!/usr/bin/env python3
"""Replay only consolidator calls from a completed production smoke run."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from opinions_agent.agent import (
    OpinionRelationshipResult,
    build_consolidator_subagent,
    build_harness_config,
    build_read_context,
    validate_consolidation,
)
from opinions_agent.config import Settings, get_settings


def _parse_selector(value: str) -> tuple[str, str]:
    commit, separator, candidate_id = value.partition(":")
    if not separator or not commit or not candidate_id.startswith("candidate-"):
        raise argparse.ArgumentTypeError("case must be COMMIT:CANDIDATE_ID")
    return commit, candidate_id


def _selected_candidates(
    source: dict[str, Any], selectors: list[tuple[str, str]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    requested = set(selectors)
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    available: set[tuple[str, str]] = set()
    for run in source["runs"]:
        commit = str(run["commit"])
        short_commit = commit[:7]
        for candidate in run["generated"]["candidates"]:
            keys = {
                (commit, candidate["candidate_id"]),
                (short_commit, candidate["candidate_id"]),
            }
            available.update(keys)
            if not requested or requested & keys:
                selected.append((run, candidate))
    missing = requested - available
    if missing:
        labels = ", ".join(f"{commit}:{candidate}" for commit, candidate in sorted(missing))
        raise ValueError(f"unknown replay cases: {labels}")
    return selected


def _case_settings(settings: Settings, case_dir: Path, trace_dir: Path) -> Settings:
    return replace(
        settings,
        braintrust_api_key="",
        braintrust_project_id="",
        braintrust_parent="",
        opinions_repo_url=str(case_dir / "opinions-repo"),
        opinions_repo_dir=case_dir / "opinions-repo",
        opinions_target_file="OPINIONS.md",
        opinions_sources_file="OPINIONS_SOURCES.jsonl",
        opinions_data_dir=case_dir / "data",
        runs_dir=case_dir,
        local_trace_dir=trace_dir,
        local_tracing_enabled=True,
        use_fake_telegram=True,
    )


async def _replay_one(
    *,
    settings: Settings,
    output_dir: Path,
    run: dict[str, Any],
    candidate: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    from thinharness import Harness

    commit = str(run["commit"])
    candidate_id = str(candidate["candidate_id"])
    run_dir = Path(run["run_dir"]).resolve()
    case_dir = Path(run.get("case_dir") or run_dir.parent).resolve()
    trace_dir = output_dir / "traces" / commit[:7] / candidate_id
    case_settings = _case_settings(settings, case_dir, trace_dir)
    context = build_read_context(case_settings, run_dir)
    subagent = build_consolidator_subagent(context=context)
    config_updates: dict[str, Any] = {
        "system_prompt": subagent.system_prompt,
        "output_type": subagent.output_type,
        "output_mode": subagent.output_mode,
        "output_retries": subagent.output_retries,
    }
    if subagent.max_model_requests is not None:
        config_updates["max_model_requests"] = subagent.max_model_requests
    if subagent.max_tool_calls is not None:
        config_updates["max_tool_calls"] = subagent.max_tool_calls
    if subagent.tool_retries is not None:
        config_updates["tool_retries"] = subagent.tool_retries
    config = build_harness_config(context=context, settings=case_settings).model_copy(update=config_updates)
    async with semaphore:
        result = await Harness(config, plugins=list(subagent.plugins), tools=list(subagent.tools)).run(candidate_id)
    if not isinstance(result.output, BaseModel):
        raise TypeError("consolidator replay did not return typed output")
    payload = result.output.model_dump(mode="json")
    relationship = OpinionRelationshipResult.model_validate(payload)
    validation = validate_consolidation(
        context=context,
        candidate_id=candidate_id,
        decision=relationship.decision,
    )
    candidate_evidence = set(candidate["evidence_ids"])
    expected = [
        operation for operation in run["ground_truth"] if candidate_evidence & set(operation["attached_evidence_ids"])
    ]
    return {
        "commit": commit,
        "production_run_id": run["production_run_id"],
        "candidate": candidate,
        "expected_operations": expected,
        "result": payload,
        "validation": validation.model_dump(mode="json"),
    }


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    exact = false_consolidations = correct_associations = 0
    for row in results:
        expected = row["expected_operations"]
        decision = row["result"]["decision"]
        if len(expected) != 1:
            continue
        operation = expected[0]
        if operation["operation"] == "add":
            if decision["kind"] == "independent":
                exact += 1
            else:
                false_consolidations += 1
            continue
        if decision["kind"] not in {"attach", "revise"}:
            continue
        if decision["existing_opinion_id"] == operation["opinion_id"]:
            correct_associations += 1
            if decision["kind"] == operation["operation"]:
                exact += 1
    return {
        "cases": len(results),
        "exact_candidate_routes": exact,
        "correct_update_associations": correct_associations,
        "false_consolidations_of_adds": false_consolidations,
    }


async def _run(args: argparse.Namespace) -> Path:
    source_report = args.source_report.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    source = json.loads(source_report.read_text(encoding="utf-8"))
    selected = _selected_candidates(source, args.case)
    semaphore = asyncio.Semaphore(args.max_concurrency)
    results = await asyncio.gather(
        *(
            _replay_one(
                settings=get_settings(),
                output_dir=output_dir,
                run=run,
                candidate=candidate,
                semaphore=semaphore,
            )
            for run, candidate in selected
        )
    )
    report = {
        "source_report": str(source_report),
        "selectors": [f"{commit}:{candidate}" for commit, candidate in args.case],
        "summary": _summarize(results),
        "results": results,
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--case", action="append", type=_parse_selector, default=[])
    parser.add_argument("--max-concurrency", type=int, default=4)
    args = parser.parse_args()
    if args.max_concurrency < 1:
        parser.error("--max-concurrency must be at least 1")
    print(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
