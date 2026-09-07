from __future__ import annotations

from types import SimpleNamespace

from opinions_agent.prompts import (
    OPINION_SELECTION_INSTRUCTIONS,
    build_system_prompt,
    build_turn_prompt,
)


def test_system_prompt_includes_selection_instructions_without_filesystem_dependency(tmp_path, monkeypatch) -> None:
    expected = build_system_prompt()

    monkeypatch.chdir(tmp_path)

    assert build_system_prompt() == expected
    assert expected.count(OPINION_SELECTION_INSTRUCTIONS.strip()) == 1


def test_turn_prompt_separates_initial_run_context_from_resume_context(tmp_path) -> None:
    context = SimpleNamespace(
        run_dir=tmp_path / "runs" / "active" / "run-1",
        run_summary="# Opinion run run-1\n\nSelected highlights: 2",
        selected_highlights_jsonl=tmp_path / "runs" / "active" / "run-1" / "selected-highlights.jsonl",
        selected_documents_jsonl=tmp_path / "runs" / "active" / "run-1" / "selected-documents.jsonl",
        candidate_opinions_jsonl=tmp_path / "runs" / "active" / "run-1" / "candidate-opinions.jsonl",
        opinions_md=tmp_path / "opinions" / "OPINIONS.md",
        sources_jsonl=tmp_path / "opinions" / "OPINIONS_SOURCES.jsonl",
        decisions_jsonl=tmp_path / "data" / "opinion-decisions.jsonl",
        documents_jsonl=tmp_path / "data" / "documents.jsonl",
        highlights_jsonl=tmp_path / "data" / "highlights.jsonl",
        documents_dir=tmp_path / "data" / "documents",
        memory_dir=tmp_path / "data" / "memory",
    )

    initial = build_turn_prompt("run-1", context, prompt_fragment=None)
    resume = build_turn_prompt("run-1", context, prompt_fragment="Telegram command received.\n\nCommand:\nGO")

    assert context.run_summary in initial
    assert str(context.selected_highlights_jsonl) in initial
    assert str(context.run_dir / "review" / "summary.md") not in initial
    assert str(context.opinions_md) in initial
    assert str(context.candidate_opinions_jsonl) in initial
    assert str(context.selected_highlights_jsonl) not in resume
    assert str(context.opinions_md) not in resume
    assert str(context.candidate_opinions_jsonl) not in resume
    assert "Command:\nGO" in resume
