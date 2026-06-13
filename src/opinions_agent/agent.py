from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths
from opinions_agent.tracing import make_langfuse_tracing

ProposalKind = Literal["add_opinion", "update_opinion", "remove_opinion", "add_sources"]


class TelegramButton(BaseModel):
    text: str
    callback_data: str


class TelegramMessageSpec(BaseModel):
    text: str
    buttons: list[TelegramButton] = Field(default_factory=list)
    reply_to_message_id: int | None = None
    force_reply: bool = False


class OpinionChangeProposal(BaseModel):
    proposal_id: str
    kind: ProposalKind
    opinion_id: str | None = None
    title: str | None = None
    current_text: str | None = None
    proposed_text: str | None = None
    rationale: str
    supporting_highlight_ids: list[str] = Field(default_factory=list)


class OpinionProposalOutput(BaseModel):
    status: Literal["awaiting_user", "needs_more_work"]
    proposals: list[OpinionChangeProposal] = Field(default_factory=list)
    notes: str | None = None


class ProposalValidationError(ValueError):
    pass


def validate_proposals(proposals: list[OpinionChangeProposal]) -> None:
    seen: set[str] = set()
    for proposal in proposals:
        if not proposal.proposal_id.strip():
            raise ProposalValidationError("proposal is missing a proposal_id")
        if proposal.proposal_id in seen:
            raise ProposalValidationError(f"duplicate proposal_id: {proposal.proposal_id}")
        seen.add(proposal.proposal_id)
        if proposal.kind == "add_opinion":
            if not proposal.title or not proposal.proposed_text:
                raise ProposalValidationError(f"{proposal.proposal_id}: add_opinion requires title and proposed_text")
        else:
            if not proposal.opinion_id:
                raise ProposalValidationError(f"{proposal.proposal_id}: {proposal.kind} requires opinion_id")
        if proposal.kind == "update_opinion" and not proposal.proposed_text:
            raise ProposalValidationError(f"{proposal.proposal_id}: update_opinion requires proposed_text")
        if proposal.kind in {"add_opinion", "update_opinion", "add_sources"} and not proposal.supporting_highlight_ids:
            raise ProposalValidationError(f"{proposal.proposal_id}: {proposal.kind} requires supporting highlights")


@dataclass(frozen=True)
class AgentReadContext:
    """The full read surface granted to the agent: current run bundle, corpus indexes,
    document content, memory, decision log, and the public opinions files. Raw payloads,
    state.json, old run directories, and git internals are intentionally excluded."""

    run_dir: Path
    documents_jsonl: Path
    highlights_jsonl: Path
    decisions_jsonl: Path
    documents_dir: Path
    memory_dir: Path
    opinions_md: Path
    sources_jsonl: Path

    def read_paths(self) -> list[Path]:
        return [
            self.run_dir,
            self.documents_jsonl,
            self.highlights_jsonl,
            self.decisions_jsonl,
            self.documents_dir,
            self.memory_dir,
            self.opinions_md,
            self.sources_jsonl,
        ]


def build_read_context(settings: Settings, run_dir: Path) -> AgentReadContext:
    corpus = CorpusPaths(settings.opinions_data_dir)
    return AgentReadContext(
        run_dir=run_dir,
        documents_jsonl=corpus.documents_jsonl,
        highlights_jsonl=corpus.highlights_jsonl,
        decisions_jsonl=corpus.decisions_jsonl,
        documents_dir=corpus.documents_dir,
        memory_dir=corpus.memory_dir,
        opinions_md=settings.opinions_target_path,
        sources_jsonl=settings.opinions_sources_path,
    )


class OpinionAgent:
    async def propose(
        self,
        *,
        run_id: str,
        context: AgentReadContext,
        settings: Settings,
    ) -> tuple[OpinionProposalOutput, dict | None]:
        raise NotImplementedError

    async def revise(
        self,
        *,
        run_id: str,
        feedback: str,
        previous_output: OpinionProposalOutput,
        context: AgentReadContext,
        settings: Settings,
        resume_state: dict | None,
    ) -> tuple[OpinionProposalOutput, dict | None]:
        raise NotImplementedError


class ThinHarnessOpinionAgent(OpinionAgent):
    async def propose(
        self,
        *,
        run_id: str,
        context: AgentReadContext,
        settings: Settings,
    ) -> tuple[OpinionProposalOutput, dict | None]:
        return await _run_harness(
            prompt=_proposal_prompt(run_id, context),
            context=context,
            settings=settings,
            resume_state=None,
        )

    async def revise(
        self,
        *,
        run_id: str,
        feedback: str,
        previous_output: OpinionProposalOutput,
        context: AgentReadContext,
        settings: Settings,
        resume_state: dict | None,
    ) -> tuple[OpinionProposalOutput, dict | None]:
        prompt = (
            _proposal_prompt(run_id, context)
            + "\n\nPrevious proposals:\n"
            + previous_output.model_dump_json(indent=2)
            + "\n\nUser feedback:\n"
            + feedback
            + "\n\nReturn a full replacement proposal batch that addresses the feedback."
        )
        return await _run_harness(prompt=prompt, context=context, settings=settings, resume_state=resume_state)


def _proposal_prompt(run_id: str, context: AgentReadContext) -> str:
    return f"""
You are the opinion proposal agent for opinions-agent, run {run_id}.

Start by reading the run brief at {context.run_dir / "brief.md"} and follow its instructions exactly.

Inputs for this run:
- Selected highlights (read all of them): {context.run_dir / "selected-highlights.jsonl"}
- Selected documents: {context.run_dir / "selected-documents.jsonl"}
- Current opinions: {context.opinions_md}
- Opinion provenance: {context.sources_jsonl}
- Prior proposal decisions: {context.decisions_jsonl}
- Global corpus indexes for historical context: {context.documents_jsonl} and {context.highlights_jsonl}
- Full document content, only when summaries/highlights are insufficient: {context.documents_dir}
- Memory notes: {context.memory_dir}

Return structured output only. Do not write files. Use supporting_highlight_ids values exactly as they appear in
selected-highlights.jsonl. Set status to "awaiting_user" when you have proposals (or an intentionally empty batch),
and "needs_more_work" only when you could not complete the analysis.
"""


async def _run_harness(
    *,
    prompt: str,
    context: AgentReadContext,
    settings: Settings,
    resume_state: dict | None,
) -> tuple[OpinionProposalOutput, dict | None]:
    from thinharness import Harness, HarnessConfig, PromptedOutput

    read_paths = context.read_paths()
    tracing = make_langfuse_tracing(settings)
    config = HarnessConfig(
        root=_common_root(read_paths),
        model=settings.harness_model,
        builtin_tools=["read"],
        read_paths=[str(path) for path in read_paths],
        output_dir=str(context.run_dir / ".thinharness" / "outputs"),
        output_type=PromptedOutput(OpinionProposalOutput),
        local_trace_dir=str(settings.local_trace_dir),
        local_tracing=settings.local_tracing_enabled,
        tracing=[tracing] if tracing is not None else [],
    )
    result = await Harness(config).run(prompt, resume_from=resume_state)
    output = (
        result.output
        if isinstance(result.output, OpinionProposalOutput)
        else OpinionProposalOutput.model_validate(result.output)
    )
    return output, result.resume_state


def _common_root(paths: list[Path]) -> Path:
    resolved = [path.expanduser().resolve() for path in paths]
    common = os.path.commonpath([str(path) for path in resolved])
    return Path(common)


class DeterministicOpinionAgent(OpinionAgent):
    """Deterministic fake agent for tests and local smoke runs; emits all four proposal kinds."""

    async def propose(
        self,
        *,
        run_id: str,
        context: AgentReadContext,
        settings: Settings,
    ) -> tuple[OpinionProposalOutput, dict | None]:
        return _deterministic_output(context), {"model": "deterministic"}

    async def revise(
        self,
        *,
        run_id: str,
        feedback: str,
        previous_output: OpinionProposalOutput,
        context: AgentReadContext,
        settings: Settings,
        resume_state: dict | None,
    ) -> tuple[OpinionProposalOutput, dict | None]:
        output = _deterministic_output(context, revision_note=feedback.strip())
        return output, resume_state or {"model": "deterministic"}


def _deterministic_output(context: AgentReadContext, revision_note: str | None = None) -> OpinionProposalOutput:
    from opinions_agent.fsio import read_jsonl
    from opinions_agent.opinions_doc import load_opinions

    highlights = read_jsonl(context.run_dir / "selected-highlights.jsonl")
    if not highlights:
        return OpinionProposalOutput(status="awaiting_user", proposals=[])
    existing = load_opinions(context.opinions_md).opinions
    first = highlights[0]
    last = highlights[-1]
    suffix = f" (revised: {revision_note})" if revision_note else ""

    proposals = [
        OpinionChangeProposal(
            proposal_id="prop_add",
            kind="add_opinion",
            title=f"Takeaway from {first.get('document_title') or 'recent reading'}",
            proposed_text=f"{first['text']}{suffix}",
            rationale="Deterministic add proposal from the first selected highlight.",
            supporting_highlight_ids=[first["highlight_id"]],
        )
    ]
    if existing:
        proposals.append(
            OpinionChangeProposal(
                proposal_id="prop_update",
                kind="update_opinion",
                opinion_id=existing[0].opinion_id,
                title=existing[0].title,
                current_text=existing[0].body,
                proposed_text=f"{existing[0].body}\n\nClarified by: {first['text']}{suffix}",
                rationale="Deterministic update proposal for the first existing opinion.",
                supporting_highlight_ids=[first["highlight_id"]],
            )
        )
        proposals.append(
            OpinionChangeProposal(
                proposal_id="prop_sources",
                kind="add_sources",
                opinion_id=existing[0].opinion_id,
                rationale="Deterministic add_sources proposal for the first existing opinion.",
                supporting_highlight_ids=[last["highlight_id"]],
            )
        )
    if len(existing) >= 2:
        proposals.append(
            OpinionChangeProposal(
                proposal_id="prop_remove",
                kind="remove_opinion",
                opinion_id=existing[1].opinion_id,
                current_text=existing[1].body,
                rationale="Deterministic remove proposal for the second existing opinion.",
                supporting_highlight_ids=[first["highlight_id"]],
            )
        )
    return OpinionProposalOutput(status="awaiting_user", proposals=proposals)
