"""Parse and mutate OPINIONS.md (hidden stable IDs) and OPINIONS_SOURCES.jsonl provenance."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from opinions_agent.fsio import append_jsonl, read_jsonl

OPINION_ID_RE = re.compile(r"^opinion-(\d{6})$")
MARKER_RE = re.compile(r"<!--\s*opinion-id:\s*(opinion-\d{6})\s*-->")
HEADING_RE = re.compile(r"^##\s*(\d+)\.\s*(.+?)\s*$", re.MULTILINE)

DEFAULT_PREAMBLE = "# OPINIONS\n"


class OpinionsDocError(ValueError):
    pass


@dataclass(frozen=True)
class Opinion:
    opinion_id: str
    number: int
    title: str
    body: str


@dataclass(frozen=True)
class OpinionsDocument:
    preamble: str
    opinions: list[Opinion]

    def get(self, opinion_id: str) -> Opinion:
        for opinion in self.opinions:
            if opinion.opinion_id == opinion_id:
                return opinion
        raise OpinionsDocError(f"opinion not found: {opinion_id}")

    def render(self) -> str:
        parts = [self.preamble.rstrip() + "\n"] if self.preamble.strip() else [DEFAULT_PREAMBLE]
        for opinion in self.opinions:
            block = [
                f"<!-- opinion-id: {opinion.opinion_id} -->",
                f"## {opinion.number}. {opinion.title}",
                "",
            ]
            if opinion.body.strip():
                block.extend([opinion.body.strip(), ""])
            parts.append("\n".join(block))
        return "\n".join(parts)


def parse_opinions(text: str) -> OpinionsDocument:
    markers = list(MARKER_RE.finditer(text))
    preamble = text[: markers[0].start()] if markers else text
    opinions: list[Opinion] = []
    seen_ids: set[str] = set()
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        block = text[marker.end() : end]
        opinion_id = marker.group(1)
        if opinion_id in seen_ids:
            raise OpinionsDocError(f"duplicate opinion id: {opinion_id}")
        seen_ids.add(opinion_id)
        heading = HEADING_RE.search(block)
        if heading is None:
            raise OpinionsDocError(f"opinion {opinion_id} is missing a '## N. Title' heading")
        body = block[heading.end() :].strip()
        opinions.append(
            Opinion(opinion_id=opinion_id, number=int(heading.group(1)), title=heading.group(2), body=body)
        )
    return OpinionsDocument(preamble=preamble, opinions=opinions)


def load_opinions(path: Path) -> OpinionsDocument:
    if not path.exists():
        return OpinionsDocument(preamble=DEFAULT_PREAMBLE, opinions=[])
    return parse_opinions(path.read_text(encoding="utf-8"))


def opinion_id_number(opinion_id: str) -> int:
    match = OPINION_ID_RE.match(opinion_id)
    if match is None:
        raise OpinionsDocError(f"invalid opinion id: {opinion_id}")
    return int(match.group(1))


def next_opinion_id(existing_ids: set[str]) -> str:
    highest = max((opinion_id_number(opinion_id) for opinion_id in existing_ids), default=0)
    return f"opinion-{highest + 1:06d}"


def add_opinion(doc: OpinionsDocument, *, opinion_id: str, title: str, body: str) -> OpinionsDocument:
    if any(opinion.opinion_id == opinion_id for opinion in doc.opinions):
        raise OpinionsDocError(f"opinion id already exists: {opinion_id}")
    number = max((opinion.number for opinion in doc.opinions), default=0) + 1
    opinion = Opinion(opinion_id=opinion_id, number=number, title=title.strip(), body=body.strip())
    return OpinionsDocument(preamble=doc.preamble, opinions=[*doc.opinions, opinion])


def update_opinion(doc: OpinionsDocument, *, opinion_id: str, title: str | None, body: str) -> OpinionsDocument:
    target = doc.get(opinion_id)
    updated = replace(target, title=(title or target.title).strip(), body=body.strip())
    return OpinionsDocument(
        preamble=doc.preamble,
        opinions=[updated if opinion.opinion_id == opinion_id else opinion for opinion in doc.opinions],
    )


def remove_opinion(doc: OpinionsDocument, *, opinion_id: str) -> OpinionsDocument:
    doc.get(opinion_id)
    return OpinionsDocument(
        preamble=doc.preamble,
        opinions=[opinion for opinion in doc.opinions if opinion.opinion_id != opinion_id],
    )


def read_sources(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def append_source_rows(path: Path, rows: list[dict[str, Any]]) -> int:
    """Append provenance rows, skipping (opinion_id, highlight_id) pairs already present."""
    existing = {(row["opinion_id"], row["highlight_id"]) for row in read_sources(path)}
    fresh = [row for row in rows if (row["opinion_id"], row["highlight_id"]) not in existing]
    append_jsonl(path, fresh)
    return len(fresh)


def remove_sources_for_opinion(path: Path, opinion_id: str) -> int:
    from opinions_agent.fsio import write_jsonl_atomic

    rows = read_sources(path)
    kept = [row for row in rows if row["opinion_id"] != opinion_id]
    if len(kept) != len(rows):
        write_jsonl_atomic(path, kept)
    return len(rows) - len(kept)


def validate_opinions_files(doc: OpinionsDocument, sources_rows: list[dict[str, Any]]) -> None:
    """Post-apply validation: unique stable IDs and no orphaned provenance rows."""
    seen: set[str] = set()
    for opinion in doc.opinions:
        if opinion.opinion_id in seen:
            raise OpinionsDocError(f"duplicate opinion id: {opinion.opinion_id}")
        seen.add(opinion.opinion_id)
    for row in sources_rows:
        if row["opinion_id"] not in seen:
            raise OpinionsDocError(f"source row references missing opinion: {row['opinion_id']}")
