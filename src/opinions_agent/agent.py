from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from opinions_agent.config import Settings
from opinions_agent.tracing import make_langfuse_tracing


class TelegramButton(BaseModel):
    text: str
    callback_data: str


class TelegramMessageSpec(BaseModel):
    text: str
    buttons: list[TelegramButton] = Field(default_factory=list)
    reply_to_message_id: int | None = None
    force_reply: bool = False


class AgentOutput(BaseModel):
    status: Literal["awaiting_user", "committed", "rejected", "needs_more_work"]
    telegram_messages: list[TelegramMessageSpec] = Field(default_factory=list)
    revised_summary: str | None = None
    commit_sha: str | None = None


class SummaryAgent:
    async def propose(
        self,
        *,
        run_id: str,
        input_paths: dict[str, str],
        target_file: Path,
        settings: Settings,
    ) -> tuple[AgentOutput, dict | None]:
        raise NotImplementedError

    async def revise(
        self,
        *,
        run_id: str,
        current_summary: str,
        feedback: str,
        input_paths: dict[str, str],
        target_file: Path,
        settings: Settings,
        resume_state: dict | None,
    ) -> tuple[AgentOutput, dict | None]:
        raise NotImplementedError


class ThinHarnessSummaryAgent(SummaryAgent):
    async def propose(
        self,
        *,
        run_id: str,
        input_paths: dict[str, str],
        target_file: Path,
        settings: Settings,
    ) -> tuple[AgentOutput, dict | None]:
        return await _run_harness(
            prompt=_proposal_prompt(run_id, input_paths, target_file),
            run_dir=Path(input_paths["dir"]),
            read_paths=[Path(input_paths["dir"]), target_file],
            settings=settings,
            resume_state=None,
        )

    async def revise(
        self,
        *,
        run_id: str,
        current_summary: str,
        feedback: str,
        input_paths: dict[str, str],
        target_file: Path,
        settings: Settings,
        resume_state: dict | None,
    ) -> tuple[AgentOutput, dict | None]:
        prompt = (
            _proposal_prompt(run_id, input_paths, target_file)
            + "\n\nPrevious summary:\n"
            + current_summary
            + "\n\nUser feedback:\n"
            + feedback
            + "\n\nRevise the summary unless the feedback is ambiguous. Do not approve it."
        )
        return await _run_harness(
            prompt=prompt,
            run_dir=Path(input_paths["dir"]),
            read_paths=[Path(input_paths["dir"]), target_file],
            settings=settings,
            resume_state=resume_state,
        )


class DeterministicSummaryAgent(SummaryAgent):
    async def propose(
        self,
        *,
        run_id: str,
        input_paths: dict[str, str],
        target_file: Path,
        settings: Settings,
    ) -> tuple[AgentOutput, dict | None]:
        summary = _deterministic_summary(Path(input_paths["highlights_jsonl"]))
        return _approval_output(run_id, summary), {"model": "deterministic"}

    async def revise(
        self,
        *,
        run_id: str,
        current_summary: str,
        feedback: str,
        input_paths: dict[str, str],
        target_file: Path,
        settings: Settings,
        resume_state: dict | None,
    ) -> tuple[AgentOutput, dict | None]:
        summary = f"{current_summary}\n\nRevision note: {feedback.strip()}"
        return _approval_output(run_id, summary), resume_state or {"model": "deterministic"}


def _proposal_prompt(run_id: str, input_paths: dict[str, str], target_file: Path) -> str:
    return (
        f"""
You are the dummy summary agent for opinions-agent.

Read {input_paths["brief_md"]} and {input_paths["highlights_jsonl"]}. You may read the current target file at
{target_file}, but do not write to any file.

Return structured output only. Create a concise summary of the highlights, set status to "awaiting_user", put the
summary in revised_summary, and include one Telegram message asking for approval.
The Telegram message must include Approve, Reject, and Revise buttons with callback_data values:
- run:{run_id}:approve
- run:{run_id}:reject
- run:{run_id}:revise
"""
    )


async def _run_harness(
    *,
    prompt: str,
    run_dir: Path,
    read_paths: list[Path],
    settings: Settings,
    resume_state: dict | None,
) -> tuple[AgentOutput, dict | None]:
    from thinharness import Harness, HarnessConfig, PromptedOutput

    root = _common_root([*read_paths, run_dir])
    tracing = make_langfuse_tracing(settings)
    config = HarnessConfig(
        root=root,
        model=settings.harness_model,
        builtin_tools=["read"],
        read_paths=[str(path) for path in read_paths],
        output_dir=str(run_dir / ".thinharness" / "outputs"),
        output_type=PromptedOutput(AgentOutput),
        local_trace_dir=str(settings.local_trace_dir),
        local_tracing=settings.local_tracing_enabled,
        tracing=[tracing] if tracing is not None else [],
    )
    result = await Harness(config).run(prompt, resume_from=resume_state)
    output = result.output if isinstance(result.output, AgentOutput) else AgentOutput.model_validate(result.output)
    return output, result.resume_state


def _common_root(paths: list[Path]) -> Path:
    resolved = [path.expanduser().resolve() for path in paths]
    common = os.path.commonpath([str(path) for path in resolved])
    return Path(common)


def _approval_output(run_id: str, summary: str) -> AgentOutput:
    return AgentOutput(
        status="awaiting_user",
        revised_summary=summary,
        telegram_messages=[
            TelegramMessageSpec(
                text=f"{summary}\n\nApprove this summary?",
                buttons=[
                    TelegramButton(text="Approve", callback_data=f"run:{run_id}:approve"),
                    TelegramButton(text="Reject", callback_data=f"run:{run_id}:reject"),
                    TelegramButton(text="Revise", callback_data=f"run:{run_id}:revise"),
                ],
            )
        ],
    )


def _deterministic_summary(highlights_path: Path) -> str:
    import json

    rows = [json.loads(line) for line in highlights_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    titles = sorted({row.get("document_title") or "Untitled" for row in rows})
    first_text = rows[0]["text"] if rows else "No highlights."
    return f"Summary of {len(rows)} highlight(s) from {', '.join(titles)}: {first_text[:220]}"
