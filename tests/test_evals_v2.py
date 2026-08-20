from __future__ import annotations

import json
from types import SimpleNamespace

from opinions_agent.agent import TelegramButtonSpec, TelegramMessageSpec
from opinions_agent.evals.proposals import ParsedProposal as V1ParsedProposal
from opinions_agent.evals.v2.proposals import parse_proposals
from opinions_agent.evals.v2.runner import summarize_target_weighted_quality
from opinions_agent.evals.v2.scorers import make_opinion_judges


class FakeJudgeClient:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.chat = self
        self.completions = self

    async def create(self, *, model: str, messages: list[dict], temperature: float):
        payload = self.payloads.pop(0)
        message = SimpleNamespace(content=json.dumps(payload))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def target(*, kind: str = "add", base_text: str | None = None) -> dict:
    value = {
        "target_id": "W05-01",
        "kind": kind,
        "section": "Agentic Software",
        "ideal_opinion": "Precise design remains necessary.",
        "required_sources": ["rw:a"],
        "required_concepts": ["Precise design remains necessary"],
        "source_quotes": [],
    }
    if base_text is not None:
        value["base_opinion_id"] = "opinion-000001"
        value["base_opinion_text"] = base_text
    return value


def proposal(*, kind: str, current_text: str | None = None) -> dict:
    current = f"<b>Current</b>\n{current_text}\n\n" if current_text is not None else ""
    message_text = (
        f"<b>{kind.title()} Opinion #1</b>\n"
        "<i>Section:</i> Agentic Software\n\n"
        f"{current}"
        "<b>Opinion</b>\nPrecise design remains necessary.\n\n"
        "<b>Evidence</b>\nDoc — rw:a"
    )
    return {
        "proposal_id": "p1",
        "kind": kind,
        "heading": f"{kind.title()} Opinion #1",
        "section": "Agentic Software",
        "opinion_text": "Precise design remains necessary.",
        "current_opinion_text": current_text,
        "evidence_ids": ["rw:a"],
        "message_text": message_text,
    }


def expected(value: dict) -> dict:
    return {"targets": [value], "not_converted": []}


async def scores_for(settings, target_value: dict, proposal_value: dict):
    quality, attempted, operation, quality_v2 = make_opinion_judges(
        settings,
        client=FakeJudgeClient([{"pass": True, "missing": "", "rationale": "Complete."}]),
    )
    output = {"week": "W05", "proposals": [proposal_value]}
    expected_value = expected(target_value)
    return (
        await quality(None, output, expected_value),
        await attempted(None, output, expected_value),
        await operation(None, output, expected_value),
        await quality_v2(None, output, expected_value),
    )


def test_v2_parser_extracts_both_current_opinion_labels():
    for label in ("Current", "Current Opinion"):
        text = (
            "<b>Revise Opinion #1</b>\n"
            "<i>Section:</i> Agentic Software\n\n"
            f"<b>{label}</b>\nOld &amp; durable.\n\n"
            "<b>Opinion</b>\nNew wording.\n\n"
            "<b>Evidence</b>\nDoc — rw:a"
        )
        message = TelegramMessageSpec(
            text=text,
            buttons=[TelegramButtonSpec(text="Approve", callback_data="approve:p1")],
        )
        parsed = parse_proposals([message])
        assert parsed[0].current_opinion_text == "Old & durable."


def test_v1_proposal_contract_remains_frozen():
    assert "current_opinion_text" not in V1ParsedProposal.model_fields


async def test_v2_rejects_conceptually_correct_revision_for_add_target(settings):
    quality, _, operation, quality_v2 = await scores_for(settings, target(), proposal(kind="revise"))
    assert quality.score == 1.0
    assert operation.score == 0.0
    assert quality_v2.score == 0.0
    assert operation.metadata["targets"][0]["operation_reason"] == "add target proposed as revise"


async def test_v2_accepts_update_of_canonical_base_opinion(settings):
    base_text = "Existing opinion."
    quality, _, operation, quality_v2 = await scores_for(
        settings,
        target(kind="update", base_text=base_text),
        proposal(kind="revise", current_text=base_text),
    )
    assert quality.score == 1.0
    assert operation.score == 1.0
    assert quality_v2.score == 1.0


async def test_v2_rejects_update_of_wrong_base_opinion(settings):
    quality, _, operation, quality_v2 = await scores_for(
        settings,
        target(kind="update", base_text="Expected base."),
        proposal(kind="revise", current_text="Different opinion."),
    )
    assert quality.score == 1.0
    assert operation.score == 0.0
    assert quality_v2.score == 0.0
    assert operation.metadata["targets"][0]["operation_reason"] == (
        "revision does not identify the canonical base opinion"
    )


def test_v2_target_weighted_summary_supports_v2_metrics():
    results = [
        SimpleNamespace(
            scores={"operation_accuracy": 2 / 3, "opinion_quality_v2": 1 / 3},
            expected={"targets": [{}, {}, {}]},
        ),
        SimpleNamespace(
            scores={"operation_accuracy": 0.8, "opinion_quality_v2": 1.0},
            expected={"targets": [{}] * 5},
        ),
    ]
    assert summarize_target_weighted_quality(results, "operation_accuracy") == (
        "operation_accuracy (target-weighted): 6/8 = 0.7500"
    )
    assert summarize_target_weighted_quality(results, "opinion_quality_v2") == (
        "opinion_quality_v2 (target-weighted): 6/8 = 0.7500"
    )
