from __future__ import annotations

from types import SimpleNamespace

from opinions_agent.prompts import build_system_prompt, build_turn_prompt


def test_system_prompt_treats_replies_as_feedback_not_approval() -> None:
    prompt = build_system_prompt()

    assert "Only an Approve button callback is approval" in prompt
    assert "treat that reply as contextual feedback" in prompt
    assert "send a revised proposal message with fresh Approve and Reject buttons" in prompt
    assert "Never infer approval from a free-text reply" in prompt
    assert "<b>Add Opinion #2 (Revised)</b>" in prompt
    assert "include one final plain Telegram message summarizing" in prompt
    assert "instead of &apos; or &quot;" in prompt
    assert "After any source or surrounding-context read" in prompt
    assert "concrete example, mechanism, caveat" in prompt
    assert "Do not collapse concrete source detail back into a generic abstraction" in prompt
    assert "## Evidence And Workflow" in prompt
    assert "## Telegram Message Format" in prompt


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
