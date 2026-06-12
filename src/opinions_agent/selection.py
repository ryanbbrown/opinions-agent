"""Deterministic current-window highlight selection and active run bundle export."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from opinions_agent.corpus import CorpusPaths, DocumentRow, HighlightRow, document_by_id, read_highlights
from opinions_agent.fsio import write_jsonl_atomic, write_text_atomic
from opinions_agent.reader import iso_utc, parse_iso


@dataclass(frozen=True)
class RunPaths:
    runs_dir: Path

    @property
    def active_dir(self) -> Path:
        return self.runs_dir / "active"

    @property
    def completed_dir(self) -> Path:
        return self.runs_dir / "completed"

    def active_run_dir(self, run_id: str) -> Path:
        return self.active_dir / run_id

    def completed_run_dir(self, run_id: str) -> Path:
        return self.completed_dir / run_id


@dataclass(frozen=True)
class RunBundle:
    run_dir: Path
    brief_md: Path
    selected_highlights_jsonl: Path
    selected_documents_jsonl: Path
    highlights: list[HighlightRow]
    documents: list[DocumentRow]


def select_window(highlights: list[HighlightRow], window_start: datetime, window_end: datetime) -> list[HighlightRow]:
    """Select highlights with window_start <= highlighted_at < window_end, oldest first."""
    selected: list[tuple[datetime, HighlightRow]] = []
    for highlight in highlights:
        highlighted_at = parse_iso(highlight.highlighted_at)
        if highlighted_at is None:
            continue
        if window_start <= highlighted_at < window_end:
            selected.append((highlighted_at, highlight))
    selected.sort(key=lambda item: (item[0], item[1].highlight_id))
    return [highlight for _, highlight in selected]


def select_run_highlights(
    paths: CorpusPaths,
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[HighlightRow], list[DocumentRow]]:
    highlights = select_window(read_highlights(paths), window_start, window_end)
    documents_by_id = document_by_id(paths)
    seen: dict[str, DocumentRow] = {}
    for highlight in highlights:
        document = documents_by_id.get(highlight.document_id)
        if document is not None:
            seen.setdefault(document.document_id, document)
    return highlights, list(seen.values())


BRIEF_INSTRUCTIONS = """\
You help maintain Ryan's OPINIONS.md: a living set of durable beliefs, principles, heuristics, and taste judgments.

Read all selected highlights first. Each selected highlight includes document title, generated summary, highlight
text, notes, timestamps, and a path to full content.

Use document summaries and highlights as your primary evidence. Read full document content only when the
summary/highlights are insufficient, ambiguous, or potentially misleading.

Read OPINIONS.md to avoid duplicate opinions and to understand the current style. Read OPINIONS_SOURCES.jsonl to
understand which highlights already support existing opinions.

Read opinion-decisions.jsonl to avoid repeating rejected proposals and to understand recently accepted proposal
history.

Propose only opinion-worthy changes. An opinion-worthy item is a reusable belief, principle, heuristic, or judgment
Ryan might want to stand behind later. Do not merely summarize articles. Do not propose claims that are only
interesting facts, news, or one-off observations.

Consider four proposal types:

1. add_opinion: add a new opinion when selected highlights support a durable new belief.
2. update_opinion: update an existing opinion when new evidence clarifies, narrows, strengthens, or corrects it.
3. remove_opinion: remove an existing opinion when new evidence makes it stale, wrong, redundant, or too weak.
4. add_sources: add new sources to an existing opinion when selected highlights support it without text changes.

For each proposal, include the supporting highlight IDs and a short rationale. Current selected highlights are the
only source for new proposals. Historical highlights may be searched for context, conflict checking, or support
comparison, but do not treat old highlights as fresh evidence unless the current selected highlights independently
justify the action.

Return structured output only. Do not write files. The app will request Telegram approval before applying any change.
"""


def write_run_bundle(
    *,
    run_id: str,
    run_paths: RunPaths,
    window_start: datetime,
    window_end: datetime,
    highlights: list[HighlightRow],
    documents: list[DocumentRow],
) -> RunBundle:
    run_dir = run_paths.active_run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    highlights_path = run_dir / "selected-highlights.jsonl"
    documents_path = run_dir / "selected-documents.jsonl"
    brief_path = run_dir / "brief.md"

    write_jsonl_atomic(highlights_path, [row.model_dump(mode="json") for row in highlights])
    write_jsonl_atomic(documents_path, [row.model_dump(mode="json") for row in documents])

    titles = sorted({highlight.document_title or "Untitled" for highlight in highlights})
    brief = "\n".join(
        [
            f"# Opinion run {run_id}",
            "",
            f"Window: {iso_utc(window_start)} to {iso_utc(window_end)}",
            f"Selected highlights: {len(highlights)}",
            f"Selected documents: {len(documents)}",
            "",
            "Documents:",
            *[f"- {title}" for title in titles],
            "",
            BRIEF_INSTRUCTIONS,
        ]
    )
    write_text_atomic(brief_path, brief)
    return RunBundle(
        run_dir=run_dir,
        brief_md=brief_path,
        selected_highlights_jsonl=highlights_path,
        selected_documents_jsonl=documents_path,
        highlights=highlights,
        documents=documents,
    )


def finalize_run_dir(run_paths: RunPaths, run_id: str, final_payload: dict) -> Path:
    """Move a terminal run out of active/ and persist its final payload."""
    from opinions_agent.fsio import write_json_atomic

    completed_dir = run_paths.completed_run_dir(run_id)
    completed_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(completed_dir / "final.json", final_payload)
    active_dir = run_paths.active_run_dir(run_id)
    if active_dir.exists():
        shutil.rmtree(active_dir)
    return completed_dir


def cleanup_completed_runs(run_paths: RunPaths, *, retention_days: int, now: datetime | None = None) -> int:
    """Delete completed run directories older than the retention window. Returns directories removed."""
    if not run_paths.completed_dir.exists():
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    removed = 0
    for run_dir in run_paths.completed_dir.iterdir():
        if not run_dir.is_dir():
            continue
        modified = datetime.fromtimestamp(run_dir.stat().st_mtime, tz=UTC)
        if modified < cutoff:
            shutil.rmtree(run_dir)
            removed += 1
    return removed
