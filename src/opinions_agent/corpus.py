"""Durable filesystem corpus: documents, highlights, decisions, and sync/workflow state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from opinions_agent.fsio import append_jsonl, read_json, read_jsonl, upsert_jsonl, write_json_atomic

SCHEMA_VERSION = 1

MEMORY_FILES = {
    "themes.md": "# Themes\n",
    "preferences.md": "# Preferences\n",
    "open-questions.md": "# Open Questions\n",
}


@dataclass(frozen=True)
class CorpusPaths:
    data_dir: Path

    @property
    def state(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def documents_jsonl(self) -> Path:
        return self.data_dir / "documents.jsonl"

    @property
    def highlights_jsonl(self) -> Path:
        return self.data_dir / "highlights.jsonl"

    @property
    def decisions_jsonl(self) -> Path:
        return self.data_dir / "opinion-decisions.jsonl"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    def document_md(self, reader_id: str) -> Path:
        return self.documents_dir / f"reader_{reader_id}.md"

    def raw_json(self, reader_id: str) -> Path:
        return self.raw_dir / f"reader_{reader_id}.json"


class DocumentRow(BaseModel):
    document_id: str
    reader_id: str
    title: str | None = None
    author: str | None = None
    source_url: str | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    saved_at: str | None = None
    updated_at: str | None = None
    content_path: str | None = None
    raw_path: str | None = None


class HighlightRow(BaseModel):
    highlight_id: str
    document_id: str
    reader_id: str
    document_title: str | None = None
    document_author: str | None = None
    document_summary: str | None = None
    source_url: str | None = None
    text: str
    note: str | None = None
    color: str | None = None
    highlighted_at: str | None = None
    highlighted_date: str | None = None
    highlighted_week: str | None = None
    updated_at: str | None = None
    content_path: str | None = None


class SyncState(BaseModel):
    readwise_export_updated_after: str | None = None
    reader_updated_after: str | None = None
    last_success_at: str | None = None


class WorkflowState(BaseModel):
    last_completed_window_start: str | None = None
    last_completed_window_end: str | None = None


class CorpusState(BaseModel):
    schema_version: int = SCHEMA_VERSION
    sync: SyncState = Field(default_factory=SyncState)
    workflow: WorkflowState = Field(default_factory=WorkflowState)


class OpinionDecision(BaseModel):
    proposal_id: str
    run_id: str
    decision: str
    kind: str
    opinion_id: str | None = None
    proposed_title: str | None = None
    supporting_highlight_ids: list[str] = Field(default_factory=list)
    decided_at: str


def init_data_dirs(paths: CorpusPaths) -> None:
    for directory in (paths.data_dir, paths.documents_dir, paths.raw_dir, paths.memory_dir):
        directory.mkdir(parents=True, exist_ok=True)
    for name, placeholder in MEMORY_FILES.items():
        memory_file = paths.memory_dir / name
        if not memory_file.exists():
            memory_file.write_text(placeholder, encoding="utf-8")


def load_state(paths: CorpusPaths) -> CorpusState:
    payload = read_json(paths.state)
    if payload is None:
        return CorpusState()
    return CorpusState.model_validate(payload)


def save_state(paths: CorpusPaths, state: CorpusState) -> None:
    write_json_atomic(paths.state, state.model_dump(mode="json"))


def upsert_documents(paths: CorpusPaths, rows: list[DocumentRow]) -> int:
    return upsert_jsonl(paths.documents_jsonl, [row.model_dump(mode="json") for row in rows], "document_id")


def upsert_highlights(paths: CorpusPaths, rows: list[HighlightRow]) -> int:
    return upsert_jsonl(paths.highlights_jsonl, [row.model_dump(mode="json") for row in rows], "highlight_id")


def read_documents(paths: CorpusPaths) -> list[DocumentRow]:
    return [DocumentRow.model_validate(row) for row in read_jsonl(paths.documents_jsonl)]


def read_highlights(paths: CorpusPaths) -> list[HighlightRow]:
    return [HighlightRow.model_validate(row) for row in read_jsonl(paths.highlights_jsonl)]


def append_decisions(paths: CorpusPaths, decisions: list[OpinionDecision]) -> None:
    append_jsonl(paths.decisions_jsonl, [decision.model_dump(mode="json") for decision in decisions])


def read_decisions(paths: CorpusPaths) -> list[OpinionDecision]:
    return [OpinionDecision.model_validate(row) for row in read_jsonl(paths.decisions_jsonl)]


def highlight_ids(paths: CorpusPaths) -> set[str]:
    return {str(row["highlight_id"]) for row in read_jsonl(paths.highlights_jsonl)}


def document_by_id(paths: CorpusPaths) -> dict[str, DocumentRow]:
    return {row.document_id: row for row in read_documents(paths)}


def write_raw_payload(paths: CorpusPaths, reader_id: str, payload: dict[str, Any]) -> Path:
    target = paths.raw_json(reader_id)
    write_json_atomic(target, payload)
    return target
