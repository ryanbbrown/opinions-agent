from __future__ import annotations

import json
from pathlib import Path

from opinions_agent.agent import AgentReadContext, build_critic_tool


class FakeCriticClient:
    """Stands in for AsyncOpenAI: returns a fixed critique and records prompts."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []
        self.chat = self
        self.completions = self

    async def create(self, *, model: str, messages: list[dict], temperature: float):
        self.prompts.append(messages[0]["content"])
        reply = self.reply

        class _Message:
            content = reply

        class _Choice:
            message = _Message()

        class _Response:
            choices = [_Choice()]

        return _Response()


def make_context(tmp_path: Path) -> AgentReadContext:
    selected = tmp_path / "selected-highlights.jsonl"
    rows = [
        {
            "highlight_id": "rw:a",
            "text": "Conway's law says architecture mirrors communication structure.",
            "document_title": "Org Design",
            "evidence_kind": "highlight",
            "note": "Restructure teams first.",
        },
        {"highlight_id": "rw:b", "text": "Unrelated row.", "document_title": "Other", "evidence_kind": "highlight"},
    ]
    selected.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return AgentReadContext(
        run_dir=tmp_path,
        run_summary="",
        selected_highlights_jsonl=selected,
        selected_documents_jsonl=tmp_path / "selected-documents.jsonl",
        documents_jsonl=tmp_path / "documents.jsonl",
        highlights_jsonl=tmp_path / "highlights.jsonl",
        decisions_jsonl=tmp_path / "decisions.jsonl",
        documents_dir=tmp_path,
        memory_dir=tmp_path,
        opinions_md=tmp_path / "OPINIONS.md",
        sources_jsonl=tmp_path / "sources.jsonl",
    )


async def test_critic_prompt_carries_cited_evidence_and_flags_unknown_ids(settings, tmp_path):
    client = FakeCriticClient("REVISE\n- Missing the mechanism.")
    tool = build_critic_tool(settings=settings, context=make_context(tmp_path), client=client)
    args = tool.parameters(opinion_text="Restructure teams before redesigning systems.", evidence_ids=["rw:a", "rw:x"])
    result = await tool.handler(args)
    assert result.ok is True
    assert result.content.startswith("REVISE")
    prompt = client.prompts[0]
    assert "Conway's law says architecture mirrors communication structure." in prompt
    assert "Ryan's note: Restructure teams first." in prompt
    assert "rw:x: (not in this run's selected evidence)" in prompt
    assert "Unrelated row." not in prompt
    assert "Restructure teams before redesigning systems." in prompt


async def test_critic_reports_client_failure_as_tool_error(settings, tmp_path):
    class ExplodingClient(FakeCriticClient):
        async def create(self, **kwargs):
            raise RuntimeError("proxy unavailable")

    tool = build_critic_tool(settings=settings, context=make_context(tmp_path), client=ExplodingClient("unused"))
    result = await tool.handler(tool.parameters(opinion_text="Claim.", evidence_ids=["rw:a"]))
    assert result.ok is False
    assert "proxy unavailable" in result.content
