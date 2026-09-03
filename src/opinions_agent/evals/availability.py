"""Eval-only evidence availability overrides for historical backtests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from opinions_agent.fsio import read_jsonl
from opinions_agent.reader import parse_iso


class EvidenceAvailabilityOverride(BaseModel):
    evidence_ids: list[str] = Field(min_length=1)
    available_at: str
    reason: str = Field(min_length=1)


def default_evidence_availability_path() -> Path:
    cwd_path = Path.cwd() / "eval" / "evidence_availability.jsonl"
    if cwd_path.exists():
        return cwd_path
    source_tree_path = Path(__file__).resolve().parents[3] / "eval" / "evidence_availability.jsonl"
    if source_tree_path.exists():
        return source_tree_path
    raise FileNotFoundError("eval/evidence_availability.jsonl not found; run from the project root")


def load_evidence_availability(path: Path | None = None) -> dict[str, datetime]:
    overrides: dict[str, datetime] = {}
    for raw in read_jsonl(path or default_evidence_availability_path()):
        row = EvidenceAvailabilityOverride.model_validate(raw)
        available_at = parse_iso(row.available_at)
        if available_at is None:
            raise ValueError(f"invalid evidence availability timestamp: {row.available_at}")
        available_at = available_at.astimezone(UTC)
        for evidence_id in row.evidence_ids:
            if evidence_id in overrides:
                raise ValueError(f"duplicate evidence availability override: {evidence_id}")
            overrides[evidence_id] = available_at
    return overrides
