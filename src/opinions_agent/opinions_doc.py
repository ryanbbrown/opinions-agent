"""Parse and validate the durable OPINIONS.md bullet/comment format."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opinions_agent.fsio import read_jsonl

OPINION_ID_RE = re.compile(r"^opinion-(\d{6})$")
MARKER_RE = re.compile(r"<!--\s*opinion-id:\s*(opinion-\d{6})\s*-->")
SOURCES_RE = re.compile(r"<!--\s*sources:\s*(.*?)\s*-->")

DEFAULT_PREAMBLE = "# OPINIONS\n"


class OpinionsDocError(ValueError):
    pass


@dataclass(frozen=True)
class Opinion:
    opinion_id: str
    section: str
    text: str
    sources: list[str]


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
        if not self.opinions:
            return self.preamble.rstrip() + "\n"
        sections: dict[str, list[Opinion]] = {}
        for opinion in self.opinions:
            sections.setdefault(opinion.section, []).append(opinion)
        parts = [self.preamble.rstrip(), ""]
        for section, opinions in sections.items():
            parts.extend([f"## {section}", ""])
            for opinion in opinions:
                parts.append(f"- {opinion.text}")
                parts.append(f"  <!-- opinion-id: {opinion.opinion_id} -->")
                if opinion.sources:
                    parts.append(f"  <!-- sources: {', '.join(opinion.sources)} -->")
                parts.append("")
        return "\n".join(parts).rstrip() + "\n"


def parse_opinions(text: str) -> OpinionsDocument:
    lines = text.splitlines()
    first_section = next((index for index, line in enumerate(lines) if line.startswith("## ")), len(lines))
    preamble = "\n".join(lines[:first_section]).rstrip() + "\n" if first_section else DEFAULT_PREAMBLE
    opinions: list[Opinion] = []
    seen_ids: set[str] = set()
    section: str | None = None
    index = first_section
    while index < len(lines):
        line = lines[index]
        if line.startswith("## "):
            section = line[3:].strip()
            if not section:
                raise OpinionsDocError("empty opinion section heading")
            index += 1
            continue
        if not line.startswith("- "):
            index += 1
            continue
        if section is None:
            raise OpinionsDocError("opinion bullet appears before a section heading")
        text_line = line[2:].strip()
        if not text_line:
            raise OpinionsDocError(f"empty opinion bullet in section {section}")
        metadata: list[str] = []
        index += 1
        while index < len(lines) and not lines[index].startswith("## ") and not lines[index].startswith("- "):
            if lines[index].strip():
                metadata.append(lines[index].strip())
            index += 1
        markers = [match.group(1) for item in metadata if (match := MARKER_RE.fullmatch(item))]
        if len(markers) != 1:
            raise OpinionsDocError(f"opinion bullet must have exactly one opinion-id comment: {text_line}")
        opinion_id = markers[0]
        if opinion_id in seen_ids:
            raise OpinionsDocError(f"duplicate opinion id: {opinion_id}")
        seen_ids.add(opinion_id)
        source_values: list[str] = []
        for item in metadata:
            match = SOURCES_RE.fullmatch(item)
            if match:
                source_values = [value.strip() for value in match.group(1).split(",") if value.strip()]
        opinions.append(Opinion(opinion_id=opinion_id, section=section, text=text_line, sources=source_values))
    return OpinionsDocument(preamble=preamble or DEFAULT_PREAMBLE, opinions=opinions)


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


def read_sources(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def validate_opinions_files(doc: OpinionsDocument, sources_rows: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for opinion in doc.opinions:
        opinion_id_number(opinion.opinion_id)
        if opinion.opinion_id in seen:
            raise OpinionsDocError(f"duplicate opinion id: {opinion.opinion_id}")
        seen.add(opinion.opinion_id)

    source_pairs: set[tuple[str, str]] = set()
    required_source_fields = {
        "opinion_id",
        "evidence_id",
        "document_id",
        "document_title",
        "source_url",
        "evidence_text",
        "added_at",
    }
    for index, row in enumerate(sources_rows, start=1):
        missing_fields = sorted(required_source_fields - row.keys())
        if missing_fields:
            raise OpinionsDocError(f"source row {index} is missing required fields: {missing_fields}")
        opinion_id = row.get("opinion_id")
        evidence_id = row.get("evidence_id")
        if not isinstance(opinion_id, str) or not isinstance(evidence_id, str):
            raise OpinionsDocError(f"source row {index} must include string opinion_id and evidence_id")
        if not isinstance(row.get("evidence_text"), str) or not isinstance(row.get("added_at"), str):
            raise OpinionsDocError(f"source row {index} must include string evidence_text and added_at")
        if "highlight_id" in row:
            raise OpinionsDocError(f"source row {index} uses legacy highlight_id")
        if opinion_id not in seen:
            raise OpinionsDocError(f"source row references missing opinion: {opinion_id}")
        pair = (opinion_id, evidence_id)
        if pair in source_pairs:
            raise OpinionsDocError(f"duplicate source row: {opinion_id} {evidence_id}")
        source_pairs.add(pair)
