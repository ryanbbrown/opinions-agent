from __future__ import annotations

from types import SimpleNamespace

from opinions_agent.prompts import build_system_prompt, build_turn_prompt


def test_system_prompt_includes_rules_file_verbatim(tmp_path) -> None:
    rules = "# Test Rules\n\nSENTINEL: keep this exact rule text.\n"
    rules_path = tmp_path / "RULES.md"
    rules_path.write_text(rules, encoding="utf-8")

    prompt = build_system_prompt(rules_path=rules_path)

    assert f"Opinion selection rules from RULES.md:\n\n{rules.rstrip()}" in prompt
    assert "All Telegram message text is sent as Telegram HTML" in prompt
    assert "<blockquote expandable>" in prompt
    assert "Send one Telegram message per proposed opinion change" in prompt


def test_turn_prompt_separates_initial_run_context_from_resume_context(tmp_path) -> None:
    context = SimpleNamespace(
        run_dir=tmp_path / "runs" / "active" / "run-1",
        run_summary="# Opinion run run-1\n\nSelected highlights: 2",
        selected_highlights_jsonl=tmp_path / "runs" / "active" / "run-1" / "selected-highlights.jsonl",
        selected_documents_jsonl=tmp_path / "runs" / "active" / "run-1" / "selected-documents.jsonl",
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
    assert str(context.selected_highlights_jsonl) not in resume
    assert str(context.opinions_md) not in resume
    assert "Command:\nGO" in resume
