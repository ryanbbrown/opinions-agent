from __future__ import annotations

import pytest

from opinions_agent.opinions_doc import (
    OpinionsDocError,
    load_opinions,
    next_opinion_id,
    parse_opinions,
    validate_opinions_files,
)

SAMPLE = """# OPINIONS

Some preamble text.

## Agentic Software

- Small tools should make their state legible.
  <!-- opinion-id: opinion-000013 -->
  <!-- sources: rw:1, reader-note:2 -->

- Review should be cheap.
  <!-- opinion-id: opinion-000014 -->
"""


def test_parse_preserves_ids_sections_sources_and_roundtrips() -> None:
    doc = parse_opinions(SAMPLE)
    assert [opinion.opinion_id for opinion in doc.opinions] == ["opinion-000013", "opinion-000014"]
    assert doc.opinions[0].section == "Agentic Software"
    assert doc.opinions[0].text == "Small tools should make their state legible."
    assert doc.opinions[0].sources == ["rw:1", "reader-note:2"]
    reparsed = parse_opinions(doc.render())
    assert reparsed.opinions == doc.opinions
    assert "Some preamble text." in doc.render()


def test_parse_rejects_duplicate_ids() -> None:
    duplicated = SAMPLE.replace("opinion-000014", "opinion-000013")
    with pytest.raises(OpinionsDocError, match="duplicate opinion id"):
        parse_opinions(duplicated)


def test_parse_rejects_missing_or_duplicate_marker() -> None:
    missing = SAMPLE.replace("  <!-- opinion-id: opinion-000014 -->", "")
    with pytest.raises(OpinionsDocError, match="exactly one opinion-id"):
        parse_opinions(missing)


def test_load_missing_file_returns_empty_document(tmp_path) -> None:
    doc = load_opinions(tmp_path / "OPINIONS.md")
    assert doc.opinions == []
    assert doc.render().startswith("# OPINIONS")


def test_next_opinion_id_uses_highest_seen() -> None:
    assert next_opinion_id(set()) == "opinion-000001"
    assert next_opinion_id({"opinion-000013", "opinion-000002"}) == "opinion-000014"


def test_validate_opinions_files_rejects_orphan_duplicate_and_legacy_sources() -> None:
    doc = parse_opinions(SAMPLE)
    row = source_row("opinion-000013", "rw:1")
    validate_opinions_files(doc, [row])
    with pytest.raises(OpinionsDocError, match="missing opinion"):
        validate_opinions_files(doc, [source_row("opinion-000099", "rw:1")])
    with pytest.raises(OpinionsDocError, match="duplicate source row"):
        validate_opinions_files(
            doc,
            [
                row,
                row,
            ],
        )
    with pytest.raises(OpinionsDocError, match="legacy highlight_id"):
        validate_opinions_files(doc, [{**row, "highlight_id": "rw:1"}])


def source_row(opinion_id: str, evidence_id: str) -> dict:
    return {
        "opinion_id": opinion_id,
        "evidence_id": evidence_id,
        "document_id": "reader:doc",
        "document_title": "Doc",
        "source_url": "https://example.com",
        "evidence_text": "Evidence.",
        "added_at": "2026-06-01T00:00:00+00:00",
    }
