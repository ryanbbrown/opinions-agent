from __future__ import annotations

import json

import pytest

from opinions_agent.corpus import (
    CorpusPaths,
    CorpusState,
    DocumentRow,
    HighlightRow,
    OpinionDecision,
    append_decisions,
    highlight_ids,
    init_data_dirs,
    load_state,
    read_decisions,
    read_highlights,
    save_state,
    upsert_documents,
    upsert_highlights,
)
from opinions_agent.fsio import read_jsonl, upsert_jsonl, write_json_atomic, write_text_atomic


@pytest.fixture
def paths(tmp_path) -> CorpusPaths:
    corpus = CorpusPaths(tmp_path / "data")
    init_data_dirs(corpus)
    return corpus


def test_init_data_dirs_creates_memory_placeholders(paths: CorpusPaths) -> None:
    assert (paths.memory_dir / "themes.md").exists()
    assert (paths.memory_dir / "preferences.md").exists()
    assert (paths.memory_dir / "open-questions.md").exists()
    (paths.memory_dir / "themes.md").write_text("# Themes\n\n- existing note\n", encoding="utf-8")
    init_data_dirs(paths)
    assert "existing note" in (paths.memory_dir / "themes.md").read_text(encoding="utf-8")


def test_write_text_atomic_replaces_and_leaves_no_tmp(tmp_path) -> None:
    target = tmp_path / "nested" / "file.txt"
    write_text_atomic(target, "one")
    write_text_atomic(target, "two")
    assert target.read_text(encoding="utf-8") == "two"
    assert [p.name for p in target.parent.iterdir()] == ["file.txt"]


def test_upsert_jsonl_is_idempotent_and_preserves_order(tmp_path) -> None:
    path = tmp_path / "rows.jsonl"
    assert upsert_jsonl(path, [{"id": "a", "v": 1}, {"id": "b", "v": 1}], "id") == 2
    assert upsert_jsonl(path, [{"id": "a", "v": 2}, {"id": "c", "v": 1}], "id") == 1
    rows = read_jsonl(path)
    assert [row["id"] for row in rows] == ["a", "b", "c"]
    assert rows[0]["v"] == 2


def test_state_roundtrip(paths: CorpusPaths) -> None:
    state = load_state(paths)
    assert state == CorpusState()
    state.sync.reader_updated_after = "2026-06-12T10:00:00+00:00"
    state.workflow.last_completed_window_end = "2026-06-12T00:00:00+00:00"
    save_state(paths, state)
    loaded = load_state(paths)
    assert loaded.sync.reader_updated_after == "2026-06-12T10:00:00+00:00"
    assert loaded.workflow.last_completed_window_end == "2026-06-12T00:00:00+00:00"
    raw = json.loads(paths.state.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1


def test_document_and_highlight_upserts_do_not_duplicate(paths: CorpusPaths) -> None:
    document = DocumentRow(document_id="reader:d1", reader_id="d1", title="Doc")
    highlight = HighlightRow(highlight_id="rw:h1", document_id="reader:d1", reader_id="h1", text="Text")
    assert upsert_documents(paths, [document]) == 1
    assert upsert_documents(paths, [document]) == 0
    assert upsert_highlights(paths, [highlight]) == 1
    assert upsert_highlights(paths, [highlight.model_copy(update={"text": "New"})]) == 0
    assert len(read_highlights(paths)) == 1
    assert read_highlights(paths)[0].text == "New"
    assert highlight_ids(paths) == {"rw:h1"}


def test_decision_log_appends(paths: CorpusPaths) -> None:
    append_decisions(
        paths,
        [
            OpinionDecision(
                run_id="run-1",
                outcome="accepted",
                summary="Accepted a durable opinion.",
                affected_opinion_ids=["opinion-000001"],
                supporting_evidence_ids=["rw:h1"],
            )
        ],
    )
    append_decisions(
        paths,
        [
            OpinionDecision(
                run_id="run-1",
                outcome="rejected",
                summary="Rejected a weak idea.",
            )
        ],
    )
    decisions = read_decisions(paths)
    assert [d.outcome for d in decisions] == ["accepted", "rejected"]
    assert decisions[0].affected_opinion_ids == ["opinion-000001"]
    assert decisions[1].summary == "Rejected a weak idea."


def test_write_json_atomic_writes_sorted_pretty_json(tmp_path) -> None:
    target = tmp_path / "state.json"
    write_json_atomic(target, {"b": 1, "a": 2})
    text = target.read_text(encoding="utf-8")
    assert text.index('"a"') < text.index('"b"')
    assert text.endswith("\n")
