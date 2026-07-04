"""Structured opinion eval targets: load, verify against the corpus, and build seed week state."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from opinions_agent.corpus import CorpusPaths
from opinions_agent.fsio import read_jsonl
from opinions_agent.opinions_doc import Opinion, OpinionsDocument, next_opinion_id
from opinions_agent.sample_run import week_window_for_label
from opinions_agent.selection import select_run_highlights


class SourceQuote(BaseModel):
    title: str
    quote: str


class OpinionTarget(BaseModel):
    target_id: str
    kind: Literal["add", "update"] = "add"
    base_opinion_id: str | None = None
    section: str
    ideal_opinion: str
    required_sources: list[str]
    source_quotes: list[SourceQuote] = Field(default_factory=list)


class NotConvertedEvidence(BaseModel):
    evidence_id: str
    title: str
    evidence_kind: str


class WeekCase(BaseModel):
    week: str
    targets: list[OpinionTarget]
    not_converted: list[NotConvertedEvidence]

    def converted_evidence_ids(self) -> set[str]:
        return {evidence_id for target in self.targets for evidence_id in target.required_sources}


def default_targets_path() -> Path:
    cwd_targets = Path.cwd() / "eval" / "opinion_targets.jsonl"
    if cwd_targets.exists():
        return cwd_targets
    source_tree_targets = Path(__file__).resolve().parents[3] / "eval" / "opinion_targets.jsonl"
    if source_tree_targets.exists():
        return source_tree_targets
    raise FileNotFoundError("eval/opinion_targets.jsonl not found; run from the project root")


def default_base_opinions_path() -> Path:
    cwd_base = Path.cwd() / "OPINIONS.md"
    if cwd_base.exists():
        return cwd_base
    source_tree_base = Path(__file__).resolve().parents[3] / "OPINIONS.md"
    if source_tree_base.exists():
        return source_tree_base
    raise FileNotFoundError("OPINIONS.md not found; run from the project root")


def load_week_cases(path: Path | None = None) -> list[WeekCase]:
    return [WeekCase.model_validate(row) for row in read_jsonl(path or default_targets_path())]


def verify_week_partition(case: WeekCase, corpus: CorpusPaths) -> None:
    """Ground truth must label every selected evidence row for the week exactly once."""
    start, end = week_window_for_label(corpus, case.week)
    selected, _ = select_run_highlights(corpus, start, end)
    selected_ids = {highlight.highlight_id for highlight in selected}
    converted = case.converted_evidence_ids()
    not_converted = {evidence.evidence_id for evidence in case.not_converted}
    overlap = converted & not_converted
    if overlap:
        raise ValueError(f"{case.week}: evidence labeled both converted and not converted: {sorted(overlap)}")
    if converted | not_converted != selected_ids:
        unlabeled = sorted(selected_ids - converted - not_converted)
        stale = sorted((converted | not_converted) - selected_ids)
        raise ValueError(
            f"{case.week}: targets file does not match corpus selection (unlabeled={unlabeled}, stale={stale})"
        )


def build_seed_opinions(base_doc: OpinionsDocument, cases: list[WeekCase], week: str) -> OpinionsDocument:
    """The base document plus canonical target opinions from all eval weeks before `week`."""
    weeks = [case.week for case in cases]
    if week not in weeks:
        raise ValueError(f"unknown eval week: {week}")
    opinions = list(base_doc.opinions)
    for case in cases[: weeks.index(week)]:
        for target in case.targets:
            if target.kind == "update":
                opinions = _apply_update(opinions, target)
                continue
            opinions.append(
                Opinion(
                    opinion_id=next_opinion_id({opinion.opinion_id for opinion in opinions}),
                    section=target.section,
                    text=target.ideal_opinion,
                    sources=list(target.required_sources),
                )
            )
    return OpinionsDocument(preamble=base_doc.preamble, opinions=opinions)


def _apply_update(opinions: list[Opinion], target: OpinionTarget) -> list[Opinion]:
    if not any(opinion.opinion_id == target.base_opinion_id for opinion in opinions):
        raise ValueError(f"{target.target_id}: base opinion {target.base_opinion_id} not found in seed document")
    return [
        Opinion(
            opinion_id=opinion.opinion_id,
            section=opinion.section,
            text=target.ideal_opinion,
            sources=list(dict.fromkeys([*opinion.sources, *target.required_sources])),
        )
        if opinion.opinion_id == target.base_opinion_id
        else opinion
        for opinion in opinions
    ]
