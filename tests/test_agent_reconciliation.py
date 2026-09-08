from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import seed_corpus

from opinions_agent.agent import (
    AttachOpinionDecision,
    IndependentOpinionDecision,
    NativeAgentTurnOutput,
    ReviseOpinionDecision,
    build_candidate_validation_tool,
    build_read_context,
    load_opinion_candidates,
    validate_consolidation,
)
from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths
from opinions_agent.fsio import write_jsonl_atomic
from opinions_agent.selection import RunPaths, select_run_highlights, write_run_bundle


def make_context(settings: Settings):
    seed_corpus(settings)
    highlights, documents = select_run_highlights(
        CorpusPaths(settings.opinions_data_dir),
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 6, 12, tzinfo=UTC),
    )
    bundle = write_run_bundle(
        run_id="candidate-test",
        run_paths=RunPaths(settings.runs_dir),
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 12, tzinfo=UTC),
        highlights=highlights,
        documents=documents,
    )
    return build_read_context(settings, bundle.run_dir)


def candidate(candidate_id: str, *evidence_ids: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "section": "Agentic Software",
        "opinion_text": f"Candidate opinion for {candidate_id}.",
        "evidence_ids": list(evidence_ids),
    }


def test_native_agent_output_requires_explicit_message_controls() -> None:
    from thinharness import NativeOutput
    from thinharness.output import OutputSchema

    output_schema = OutputSchema.build(NativeOutput(NativeAgentTurnOutput), "native")
    request = output_schema.structured_output_request()
    message_schema = output_schema.schema["properties"]["telegram_messages"]["items"]

    assert request is not None
    assert request.strict is True
    assert output_schema.schema["properties"]["status"]["enum"] == ["awaiting_user", "done"]
    assert set(message_schema["required"]) == {"text", "buttons", "force_reply"}
    assert (
        NativeAgentTurnOutput.model_validate(
            {
                "status": "done",
                "telegram_messages": [{"text": "Done.", "buttons": [], "force_reply": False}],
                "notes": "",
            }
        )
        .telegram_messages[0]
        .buttons
        == []
    )


def test_candidate_jsonl_round_trips_and_preserves_one_evidence_owner(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    context = make_context(settings)
    rows = [candidate("candidate-001", "rw:h0"), candidate("candidate-002", "rw:h1")]
    write_jsonl_atomic(context.candidate_opinions_jsonl, rows)

    loaded = load_opinion_candidates(context)

    assert [item.model_dump(mode="json") for item in loaded] == rows


def test_empty_candidate_file_is_valid(settings: Settings, opinions_repo: Path) -> None:
    context = make_context(settings)
    write_jsonl_atomic(context.candidate_opinions_jsonl, [])

    assert load_opinion_candidates(context) == []


def test_candidate_file_accepts_ninety_word_opinion(settings: Settings, opinions_repo: Path) -> None:
    context = make_context(settings)
    opinion_text = " ".join(f"word{index}" for index in range(90))
    write_jsonl_atomic(
        context.candidate_opinions_jsonl,
        [{**candidate("candidate-001", "rw:h0"), "opinion_text": opinion_text}],
    )

    assert load_opinion_candidates(context)[0].opinion_text == opinion_text


@pytest.mark.parametrize(
    ("rows", "error"),
    [
        ([candidate("candidate-001", "rw:not-selected")], "outside this run"),
        (
            [candidate("candidate-001", "rw:h0"), candidate("candidate-002", "rw:h0")],
            "belongs to more than one candidate",
        ),
        (
            [candidate("candidate-001", "rw:h0"), candidate("candidate-001", "rw:h1")],
            "duplicate candidate ID",
        ),
        (
            [{**candidate("candidate-001", "rw:h0"), "opinion_text": "  "}],
            "must not be empty",
        ),
        (
            [
                {
                    **candidate("candidate-001", "rw:h0"),
                    "opinion_text": " ".join(f"word{index}" for index in range(91)),
                }
            ],
            "must contain at most 90 words",
        ),
    ],
)
def test_candidate_file_rejects_invalid_rows(
    settings: Settings,
    opinions_repo: Path,
    rows: list[dict],
    error: str,
) -> None:
    context = make_context(settings)
    write_jsonl_atomic(context.candidate_opinions_jsonl, rows)

    with pytest.raises(ValueError, match=error):
        load_opinion_candidates(context)


async def test_candidate_validation_freezes_structure_while_allowing_critic_text_edits(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    context = make_context(settings)
    write_jsonl_atomic(context.candidate_opinions_jsonl, [candidate("candidate-001", "rw:h0")])
    tool = build_candidate_validation_tool(context=context)

    initial = await tool.handler(tool.parameters())
    write_jsonl_atomic(
        context.candidate_opinions_jsonl,
        [{**candidate("candidate-001", "rw:h0"), "opinion_text": "Critic-revised opinion text."}],
    )
    text_edit = await tool.handler(tool.parameters())
    write_jsonl_atomic(context.candidate_opinions_jsonl, [candidate("candidate-001", "rw:h1")])
    evidence_edit = await tool.handler(tool.parameters())

    assert initial.ok is True
    assert text_edit.ok is True
    assert evidence_edit.ok is False
    assert "critic feedback may edit opinion_text only" in evidence_edit.content


def test_independent_decision_keeps_complete_candidate_new(settings: Settings, opinions_repo: Path) -> None:
    context = make_context(settings)
    write_jsonl_atomic(context.candidate_opinions_jsonl, [candidate("candidate-001", "rw:h0", "rw:h1")])

    result = validate_consolidation(
        context=context,
        candidate_id="candidate-001",
        decision=IndependentOpinionDecision(kind="independent"),
    )

    assert result.operation == "keep_new"
    assert result.outcome == "new"
    assert result.moved_evidence_ids == []
    assert result.remaining_evidence_ids == ["rw:h0", "rw:h1"]


@pytest.mark.parametrize(
    ("evidence_ids", "outcome", "remaining_evidence_ids"),
    [
        (["rw:h0", "rw:h1"], "full", []),
        (["rw:h1"], "partial", ["rw:h0"]),
    ],
)
def test_attach_evidence_supports_full_and_partial_candidate_subsets(
    settings: Settings,
    opinions_repo: Path,
    evidence_ids: list[str],
    outcome: str,
    remaining_evidence_ids: list[str],
) -> None:
    context = make_context(settings)
    write_jsonl_atomic(context.candidate_opinions_jsonl, [candidate("candidate-001", "rw:h0", "rw:h1")])

    result = validate_consolidation(
        context=context,
        candidate_id="candidate-001",
        decision=AttachOpinionDecision(
            kind="attach",
            existing_opinion_id="opinion-000001",
            evidence_ids=evidence_ids,
        ),
    )

    assert result.operation == "attach_evidence"
    assert result.outcome == outcome
    assert result.moved_evidence_ids == evidence_ids
    assert result.remaining_evidence_ids == remaining_evidence_ids


@pytest.mark.parametrize(
    ("evidence_ids", "outcome", "remaining_evidence_ids"),
    [
        (["rw:h0", "rw:h1"], "full", []),
        (["rw:h1"], "partial", ["rw:h0"]),
    ],
)
def test_revise_opinion_supports_full_and_partial_candidate_subsets(
    settings: Settings,
    opinions_repo: Path,
    evidence_ids: list[str],
    outcome: str,
    remaining_evidence_ids: list[str],
) -> None:
    context = make_context(settings)
    write_jsonl_atomic(context.candidate_opinions_jsonl, [candidate("candidate-001", "rw:h0", "rw:h1")])

    result = validate_consolidation(
        context=context,
        candidate_id="candidate-001",
        decision=ReviseOpinionDecision(
            kind="revise",
            existing_opinion_id="opinion-000001",
            revised_opinion_text="Complete revised existing opinion.",
            evidence_ids=evidence_ids,
        ),
    )

    assert result.operation == "revise_opinion"
    assert result.outcome == outcome
    assert result.moved_evidence_ids == evidence_ids
    assert result.remaining_evidence_ids == remaining_evidence_ids


@pytest.mark.parametrize(
    ("decision", "error"),
    [
        (
            ReviseOpinionDecision(
                kind="revise",
                existing_opinion_id="opinion-999999",
                revised_opinion_text="Unknown existing opinion.",
                evidence_ids=["rw:h0"],
            ),
            "existing opinion ID not found",
        ),
        (
            ReviseOpinionDecision(
                kind="revise",
                existing_opinion_id="opinion-000001",
                revised_opinion_text="Wrong evidence.",
                evidence_ids=["rw:h1"],
            ),
            "outside the candidate",
        ),
    ],
)
def test_consolidation_rejects_unknown_opinions_and_out_of_candidate_evidence(
    settings: Settings,
    opinions_repo: Path,
    decision: ReviseOpinionDecision,
    error: str,
) -> None:
    context = make_context(settings)
    write_jsonl_atomic(context.candidate_opinions_jsonl, [candidate("candidate-001", "rw:h0")])

    with pytest.raises(ValueError, match=error):
        validate_consolidation(
            context=context,
            candidate_id="candidate-001",
            decision=decision,
        )
