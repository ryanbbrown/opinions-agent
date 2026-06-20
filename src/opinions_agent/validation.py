from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths
from opinions_agent.fsio import read_json, read_jsonl, write_json_atomic
from opinions_agent.opinions_doc import (
    OpinionsDocError,
    load_opinions,
    opinion_id_number,
    parse_opinions,
    read_sources,
    validate_opinions_files,
)
from opinions_agent.tools.git_ops import run_git


@dataclass(frozen=True)
class ArtifactValidationResult:
    summary: str
    opinion_count: int
    source_count: int
    max_opinion_id: int
    high_water_mark: int


def run_artifact_validation(*, settings: Settings, run_dir: Path) -> ArtifactValidationResult:
    current_doc = load_opinions(settings.opinions_target_path)
    current_sources = read_sources(settings.opinions_sources_path)
    validate_opinions_files(current_doc, current_sources)
    _validate_decision_log(CorpusPaths(settings.opinions_data_dir).decisions_jsonl)

    baseline_doc = _baseline_opinions(settings)
    baseline_sources = _baseline_sources(settings)
    run_evidence = _selected_evidence_by_id(run_dir)
    high_water = max(
        read_opinion_id_high_water(settings),
        max((opinion_id_number(opinion.opinion_id) for opinion in baseline_doc.opinions), default=0),
    )

    baseline_ids = {opinion.opinion_id for opinion in baseline_doc.opinions}
    new_ids = [opinion.opinion_id for opinion in current_doc.opinions if opinion.opinion_id not in baseline_ids]
    reused = [opinion_id for opinion_id in new_ids if opinion_id_number(opinion_id) <= high_water]
    if reused:
        raise OpinionsDocError(f"new opinion ids must be greater than high-water {high_water}: {reused}")

    baseline_pairs = {
        (str(row.get("opinion_id")), str(row.get("evidence_id")))
        for row in baseline_sources
        if row.get("opinion_id") is not None and row.get("evidence_id") is not None
    }
    new_source_rows = [
        row
        for row in current_sources
        if (str(row.get("opinion_id")), str(row.get("evidence_id"))) not in baseline_pairs
    ]
    missing_evidence = sorted(
        {
            str(row["evidence_id"])
            for row in new_source_rows
            if str(row["evidence_id"]) not in run_evidence
        }
    )
    if missing_evidence:
        raise OpinionsDocError(f"new source rows reference evidence outside current run: {missing_evidence}")
    _validate_new_source_rows_against_run(new_source_rows, run_evidence)
    _validate_source_coverage(current_doc, current_sources)

    max_id = max((opinion_id_number(opinion.opinion_id) for opinion in current_doc.opinions), default=0)
    next_high_water = max(high_water, max_id)
    return ArtifactValidationResult(
        summary=f"validated {len(current_doc.opinions)} opinions and {len(current_sources)} source rows",
        opinion_count=len(current_doc.opinions),
        source_count=len(current_sources),
        max_opinion_id=max_id,
        high_water_mark=next_high_water,
    )


def read_opinion_id_high_water(settings: Settings) -> int:
    payload = read_json(CorpusPaths(settings.opinions_data_dir).opinion_id_high_water, default={}) or {}
    value = payload.get("highest", 0)
    return int(value)


def update_opinion_id_high_water(settings: Settings, highest: int) -> None:
    paths = CorpusPaths(settings.opinions_data_dir)
    current = read_opinion_id_high_water(settings)
    write_json_atomic(paths.opinion_id_high_water, {"highest": max(current, highest)})


def _selected_evidence_by_id(run_dir: Path) -> dict[str, dict[str, Any]]:
    return {str(row["highlight_id"]): row for row in read_jsonl(run_dir / "selected-highlights.jsonl")}


def _validate_decision_log(path: Path) -> None:
    read_jsonl(path)


def _validate_source_coverage(current_doc, current_sources: list[dict[str, Any]]) -> None:
    sources_by_opinion: dict[str, set[str]] = {}
    for row in current_sources:
        sources_by_opinion.setdefault(str(row["opinion_id"]), set()).add(str(row["evidence_id"]))
    missing = [opinion.opinion_id for opinion in current_doc.opinions if not sources_by_opinion.get(opinion.opinion_id)]
    if missing:
        raise OpinionsDocError(f"opinions missing machine-readable source rows: {missing}")
    inline_missing: list[str] = []
    for opinion in current_doc.opinions:
        machine_sources = sources_by_opinion.get(opinion.opinion_id, set())
        for evidence_id in opinion.sources:
            if evidence_id not in machine_sources:
                inline_missing.append(f"{opinion.opinion_id}:{evidence_id}")
    if inline_missing:
        raise OpinionsDocError(f"inline sources missing source rows: {inline_missing}")


def _validate_new_source_rows_against_run(
    new_source_rows: list[dict[str, Any]],
    run_evidence: dict[str, dict[str, Any]],
) -> None:
    comparisons = {
        "document_id": "document_id",
        "document_title": "document_title",
        "source_url": "source_url",
        "evidence_text": "text",
    }
    for row in new_source_rows:
        evidence = run_evidence[str(row["evidence_id"])]
        mismatched = [
            field
            for field, evidence_field in comparisons.items()
            if row.get(field) != evidence.get(evidence_field)
        ]
        if mismatched:
            raise OpinionsDocError(
                f"source row metadata does not match selected evidence {row['evidence_id']}: {mismatched}"
            )


def _git_show(repo_dir: Path, target_file: str) -> str:
    tracked = run_git(repo_dir, "ls-tree", "--name-only", "HEAD", "--", target_file)
    if not tracked.strip():
        return ""
    return run_git(repo_dir, "show", f"HEAD:{target_file}")


def _baseline_opinions(settings: Settings):
    return parse_opinions(_git_show(settings.opinions_repo_dir, settings.opinions_target_file))


def _baseline_sources(settings: Settings) -> list[dict[str, Any]]:
    text = _git_show(settings.opinions_repo_dir, settings.opinions_sources_file)
    if not text.strip():
        return []
    rows: list[dict[str, Any]] = []
    import json

    for line in text.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    validate_opinions_files(_baseline_opinions(settings), rows)
    return rows
