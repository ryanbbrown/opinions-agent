from __future__ import annotations

import pytest

from opinions_agent.opinions_doc import (
    OpinionsDocError,
    add_opinion,
    append_source_rows,
    load_opinions,
    next_opinion_id,
    parse_opinions,
    remove_opinion,
    remove_sources_for_opinion,
    update_opinion,
    validate_opinions_files,
)

SAMPLE = """# OPINIONS

Some preamble text.

<!-- opinion-id: opinion-000013 -->
## 13. Small tools should make their state legible

Durable files, narrow logs, and clear checkpoints are often better than an opaque database.

<!-- opinion-id: opinion-000014 -->
## 14. Review should be cheap

Cheap review compounds.
"""


def test_parse_preserves_ids_and_roundtrips() -> None:
    doc = parse_opinions(SAMPLE)
    assert [opinion.opinion_id for opinion in doc.opinions] == ["opinion-000013", "opinion-000014"]
    assert doc.opinions[0].number == 13
    assert doc.opinions[0].title == "Small tools should make their state legible"
    assert "opaque database" in doc.opinions[0].body
    reparsed = parse_opinions(doc.render())
    assert reparsed.opinions == doc.opinions
    assert "Some preamble text." in doc.render()


def test_parse_rejects_duplicate_ids() -> None:
    duplicated = SAMPLE.replace("opinion-000014", "opinion-000013")
    with pytest.raises(OpinionsDocError, match="duplicate opinion id"):
        parse_opinions(duplicated)


def test_load_missing_file_returns_empty_document(tmp_path) -> None:
    doc = load_opinions(tmp_path / "OPINIONS.md")
    assert doc.opinions == []
    assert doc.render().startswith("# OPINIONS")


def test_next_opinion_id_uses_highest_seen() -> None:
    assert next_opinion_id(set()) == "opinion-000001"
    assert next_opinion_id({"opinion-000013", "opinion-000002"}) == "opinion-000014"


def test_add_opinion_assigns_next_visible_number() -> None:
    doc = parse_opinions(SAMPLE)
    updated = add_opinion(doc, opinion_id="opinion-000015", title="New belief", body="Body text.")
    assert updated.opinions[-1].number == 15
    assert "<!-- opinion-id: opinion-000015 -->" in updated.render()
    with pytest.raises(OpinionsDocError, match="already exists"):
        add_opinion(updated, opinion_id="opinion-000015", title="Again", body="x")


def test_update_opinion_changes_only_target() -> None:
    doc = parse_opinions(SAMPLE)
    updated = update_opinion(doc, opinion_id="opinion-000013", title=None, body="New body.")
    assert updated.get("opinion-000013").body == "New body."
    assert updated.get("opinion-000013").title == doc.get("opinion-000013").title
    assert updated.get("opinion-000014") == doc.get("opinion-000014")


def test_remove_opinion_deletes_only_target() -> None:
    doc = parse_opinions(SAMPLE)
    updated = remove_opinion(doc, opinion_id="opinion-000013")
    assert [opinion.opinion_id for opinion in updated.opinions] == ["opinion-000014"]
    with pytest.raises(OpinionsDocError, match="not found"):
        remove_opinion(updated, opinion_id="opinion-000013")


def test_source_rows_append_dedupe_and_remove(tmp_path) -> None:
    path = tmp_path / "OPINIONS_SOURCES.jsonl"
    row = {"opinion_id": "opinion-000013", "highlight_id": "rw:1", "highlight_text": "text"}
    assert append_source_rows(path, [row]) == 1
    assert append_source_rows(path, [row, {**row, "highlight_id": "rw:2"}]) == 1
    assert remove_sources_for_opinion(path, "opinion-000013") == 2
    assert remove_sources_for_opinion(path, "opinion-000013") == 0


def test_validate_opinions_files_rejects_orphan_sources() -> None:
    doc = parse_opinions(SAMPLE)
    validate_opinions_files(doc, [{"opinion_id": "opinion-000013", "highlight_id": "rw:1"}])
    with pytest.raises(OpinionsDocError, match="missing opinion"):
        validate_opinions_files(doc, [{"opinion_id": "opinion-000099", "highlight_id": "rw:1"}])
