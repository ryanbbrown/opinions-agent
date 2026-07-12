from __future__ import annotations

import os
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from opinions_agent.config import OPINION_AGENT_MODEL, OPINION_AGENT_REASONING_EFFORT, Settings
from opinions_agent.corpus import CorpusPaths
from opinions_agent.fsio import append_jsonl, read_jsonl, write_jsonl_atomic, write_text_atomic
from opinions_agent.opinions_doc import Opinion, OpinionsDocument, load_opinions, next_opinion_id
from opinions_agent.prompts import CRITIC_PROMPT, build_system_prompt, build_turn_prompt
from opinions_agent.tracing import make_braintrust_tracing
from opinions_agent.validation import run_artifact_validation

CRITIC_MODEL = "claude-opus-4-8"
CRITIC_PROXY_URL = "https://api.braintrust.dev/v1/proxy"


class TelegramButtonSpec(BaseModel):
    text: str
    callback_data: str | None = None


class TelegramMessageSpec(BaseModel):
    text: str
    buttons: list[TelegramButtonSpec] = Field(default_factory=list)
    reply_to_message_id: int | None = None
    force_reply: bool = False


class AgentTurnOutput(BaseModel):
    status: Literal["awaiting_user", "done", "blocked"]
    telegram_messages: list[TelegramMessageSpec] = Field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True)
class AgentReadContext:
    """The full read surface granted to the agent."""

    run_dir: Path
    run_summary: str
    selected_highlights_jsonl: Path
    selected_documents_jsonl: Path
    documents_jsonl: Path
    highlights_jsonl: Path
    decisions_jsonl: Path
    documents_dir: Path
    memory_dir: Path
    opinions_md: Path
    sources_jsonl: Path

    def read_paths(self) -> list[Path]:
        return [
            self.selected_highlights_jsonl,
            self.selected_documents_jsonl,
            self.documents_jsonl,
            self.highlights_jsonl,
            self.decisions_jsonl,
            self.documents_dir,
            self.memory_dir,
            self.opinions_md,
            self.sources_jsonl,
        ]

    def write_paths(self) -> list[Path]:
        return [self.opinions_md, self.sources_jsonl, self.decisions_jsonl]


def build_read_context(settings: Settings, run_dir: Path) -> AgentReadContext:
    run_dir = run_dir.expanduser().resolve()
    corpus = CorpusPaths(settings.opinions_data_dir.expanduser().resolve())
    return AgentReadContext(
        run_dir=run_dir,
        run_summary=(run_dir / "review" / "summary.md").read_text(encoding="utf-8"),
        selected_highlights_jsonl=run_dir / "selected-highlights.jsonl",
        selected_documents_jsonl=run_dir / "selected-documents.jsonl",
        documents_jsonl=corpus.documents_jsonl,
        highlights_jsonl=corpus.highlights_jsonl,
        decisions_jsonl=corpus.decisions_jsonl,
        documents_dir=corpus.documents_dir,
        memory_dir=corpus.memory_dir,
        opinions_md=settings.opinions_target_path.expanduser().resolve(),
        sources_jsonl=settings.opinions_sources_path.expanduser().resolve(),
    )


class OpinionAgent:
    async def run_turn(
        self,
        *,
        run_id: str,
        context: AgentReadContext,
        settings: Settings,
        prompt_fragment: str | None,
        resume_state: dict | None,
    ) -> tuple[AgentTurnOutput, dict | None]:
        raise NotImplementedError


class ThinHarnessOpinionAgent(OpinionAgent):
    async def run_turn(
        self,
        *,
        run_id: str,
        context: AgentReadContext,
        settings: Settings,
        prompt_fragment: str | None,
        resume_state: dict | None,
    ) -> tuple[AgentTurnOutput, dict | None]:
        prompt = build_turn_prompt(run_id, context, prompt_fragment)
        return await _run_harness(prompt=prompt, context=context, settings=settings, resume_state=resume_state)


def build_validation_tool(*, settings: Settings, run_dir: Path):
    from pydantic import BaseModel
    from thinharness import ToolResult, ToolSpec

    class ValidateOpinionArtifactsArgs(BaseModel):
        pass

    async def validate_opinion_artifacts(args: ValidateOpinionArtifactsArgs) -> ToolResult:
        try:
            result = run_artifact_validation(settings=settings, run_dir=run_dir)
        except Exception as exc:
            return ToolResult(ok=False, content=str(exc))
        return ToolResult(ok=True, content=result.summary)

    return ToolSpec(
        name="validate_opinion_artifacts",
        description="Validate OPINIONS.md, OPINIONS_SOURCES.jsonl, and opinion-decisions.jsonl before completion.",
        parameters=ValidateOpinionArtifactsArgs,
        handler=validate_opinion_artifacts,
        sequential=True,
    )


def build_critic_tool(*, settings: Settings, context: AgentReadContext, client: Any = None):
    from thinharness import ToolResult, ToolSpec

    if client is None:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=CRITIC_PROXY_URL, api_key=settings.braintrust_api_key)

    class CritiqueOpinionDraftArgs(BaseModel):
        opinion_text: str
        evidence_ids: list[str]

    async def critique_opinion_draft(args: CritiqueOpinionDraftArgs) -> ToolResult:
        try:
            rows = {row["highlight_id"]: row for row in read_jsonl(context.selected_highlights_jsonl)}
            blocks = []
            for evidence_id in args.evidence_ids:
                row = rows.get(evidence_id)
                if row is None:
                    blocks.append(f"- {evidence_id}: (not in this run's selected evidence)")
                    continue
                note = f"\n  Ryan's note: {row['note']}" if row.get("note") else ""
                blocks.append(
                    f"- {row.get('document_title') or 'Untitled'} "
                    f"({row.get('evidence_kind') or 'highlight'}) — {evidence_id}\n"
                    f"  {row.get('text') or ''}{note}"
                )
            prompt = CRITIC_PROMPT.format(
                evidence="\n".join(blocks) or "(none cited)", opinion_text=args.opinion_text
            )
            response = await client.chat.completions.create(
                model=CRITIC_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            critique = (response.choices[0].message.content or "").strip()
        except Exception as exc:
            return ToolResult(ok=False, content=str(exc))
        return ToolResult(ok=True, content=critique)

    return ToolSpec(
        name="critique_opinion_draft",
        description=(
            "Independent fidelity review of one draft opinion against its cited evidence. Pass the exact proposed "
            "opinion text and its evidence_ids; returns READY or REVISE with the specific gaps to fix."
        ),
        parameters=CritiqueOpinionDraftArgs,
        handler=critique_opinion_draft,
    )


def _model_extra_body() -> dict:
    """Effort settings shaped for the harness model's provider; merged verbatim into each request payload."""
    provider = OPINION_AGENT_MODEL.split(":", 1)[0]
    if provider == "anthropic":
        return {
            "output_config": {"effort": OPINION_AGENT_REASONING_EFFORT},
            "thinking": {"type": "adaptive"},
            "max_tokens": 64000,
        }
    return {"reasoning": {"effort": OPINION_AGENT_REASONING_EFFORT}}


def build_harness_config(*, context: AgentReadContext, settings: Settings):
    from thinharness import HarnessConfig

    read_paths = context.read_paths()
    write_paths = context.write_paths()
    tracing = make_braintrust_tracing(settings)
    return HarnessConfig(
        root=_common_root(read_paths + write_paths),
        model=OPINION_AGENT_MODEL,
        request_timeout=1800,
        extra_body=_model_extra_body(),
        system_prompt=build_system_prompt(),
        builtin_tools=["read", "search", "jsonl_search", "list", "glob", "edit", "write"],
        read_paths=[str(path) for path in read_paths],
        write_paths=[str(path) for path in write_paths],
        output_dir=str(context.run_dir / ".thinharness" / "outputs"),
        output_type=AgentTurnOutput,
        output_mode="auto",
        local_trace_dir=str(settings.local_trace_dir),
        local_tracing=settings.local_tracing_enabled,
        tracing=[tracing] if tracing is not None else [],
    )


async def _run_harness(
    *,
    prompt: str,
    context: AgentReadContext,
    settings: Settings,
    resume_state: dict | None,
) -> tuple[AgentTurnOutput, dict | None]:
    from thinharness import Harness

    config = build_harness_config(context=context, settings=settings)
    tools = [
        build_validation_tool(settings=settings, run_dir=context.run_dir),
        build_critic_tool(settings=settings, context=context),
    ]
    result = await Harness(config, tools=tools).run(
        prompt,
        resume_from=resume_state,
    )
    output = (
        result.output
        if isinstance(result.output, AgentTurnOutput)
        else AgentTurnOutput.model_validate(result.output)
    )
    return output, result.resume_state


def _common_root(paths: list[Path]) -> Path:
    resolved = [path.expanduser().resolve() for path in paths]
    try:
        common = os.path.commonpath([str(path) for path in resolved])
    except ValueError as exc:
        raise ValueError(f"agent read/write paths do not share a common root: {resolved}") from exc
    return Path(common)


class DeterministicOpinionAgent(OpinionAgent):
    """Deterministic fake agent for tests and local smoke runs."""

    async def run_turn(
        self,
        *,
        run_id: str,
        context: AgentReadContext,
        settings: Settings,
        prompt_fragment: str | None,
        resume_state: dict | None,
    ) -> tuple[AgentTurnOutput, dict | None]:
        if prompt_fragment is None:
            return _deterministic_awaiting_output(context), {"model": "deterministic", "run_id": run_id}
        if "\nSKIP\n" in f"\n{prompt_fragment.strip()}\n":
            _append_decision(context, run_id, "skipped")
            return AgentTurnOutput(
                status="done",
                telegram_messages=[TelegramMessageSpec(text="Skipped this opinion run; no artifact changes.")],
            ), resume_state
        _apply_deterministic_edit(context, run_id)
        run_artifact_validation(settings=settings, run_dir=context.run_dir)
        return AgentTurnOutput(
            status="done",
            telegram_messages=[TelegramMessageSpec(text="Applied approved opinion updates.")],
        ), resume_state


def _deterministic_awaiting_output(context: AgentReadContext) -> AgentTurnOutput:
    highlights = read_jsonl(context.selected_highlights_jsonl)
    if not highlights:
        return AgentTurnOutput(status="done", telegram_messages=[TelegramMessageSpec(text="No selected evidence.")])
    first = highlights[0]
    title = escape(str(first.get("document_title") or "Untitled"))
    text = escape(str(first["text"]))
    highlight_id = escape(str(first["highlight_id"]))
    return AgentTurnOutput(
        status="awaiting_user",
        telegram_messages=[
            TelegramMessageSpec(
                text=(
                    "<b>Add Opinion #1</b>\n"
                    "<i>Section:</i> Agentic Software\n\n"
                    "<b>Opinion</b>\n"
                    f"{text} Deterministic opinion.\n\n"
                    "<b>Sources</b>\n"
                    f"{title}\n\n"
                    "<blockquote expandable>\n"
                    "<b>Evidence</b>\n\n"
                    f"{title} — {highlight_id}\n"
                    f"{text}\n"
                    "</blockquote>"
                ),
                buttons=[
                    TelegramButtonSpec(text="Approve", callback_data="approve:add-deterministic-opinion"),
                    TelegramButtonSpec(text="Reject", callback_data="reject:add-deterministic-opinion"),
                ],
            )
        ],
    )


def _apply_deterministic_edit(context: AgentReadContext, run_id: str) -> None:
    highlights = read_jsonl(context.selected_highlights_jsonl)
    if not highlights:
        return
    first = highlights[0]
    doc = load_opinions(context.opinions_md)
    existing_ids = {opinion.opinion_id for opinion in doc.opinions}
    opinion_id = next_opinion_id(existing_ids)
    opinion = Opinion(
        opinion_id=opinion_id,
        section="Agentic Software",
        text=f"{first['text']} Deterministic opinion.",
        sources=[first["highlight_id"]],
    )
    updated = OpinionsDocument(preamble=doc.preamble, opinions=[*doc.opinions, opinion])
    write_text_atomic(context.opinions_md, updated.render())
    sources = read_jsonl(context.sources_jsonl)
    sources.append(
        {
            "opinion_id": opinion_id,
            "evidence_id": first["highlight_id"],
            "document_id": first.get("document_id"),
            "document_title": first.get("document_title"),
            "source_url": first.get("source_url"),
            "evidence_text": first.get("text"),
            "added_at": first.get("highlighted_at"),
        }
    )
    write_jsonl_atomic(context.sources_jsonl, sources)
    _append_decision(context, run_id, "approved", opinion_id=opinion_id, evidence_id=first["highlight_id"])


def _append_decision(
    context: AgentReadContext,
    run_id: str,
    decision: str,
    *,
    opinion_id: str | None = None,
    evidence_id: str | None = None,
) -> None:
    append_jsonl(
        context.decisions_jsonl,
        [
            {
                "run_id": run_id,
                "decision": decision,
                "affected_opinion_ids": [opinion_id] if opinion_id else [],
                "supporting_evidence_ids": [evidence_id] if evidence_id else [],
                "summary": f"Deterministic {decision} decision.",
            }
        ],
    )
