from __future__ import annotations

import json
from types import SimpleNamespace

from opinions_agent.agent import TelegramButtonSpec, TelegramMessageSpec
from opinions_agent.evals.proposals import ParsedProposal as V1ParsedProposal
from opinions_agent.evals.v2.proposals import parse_proposals
from opinions_agent.evals.v2.runner import _fetch_experiment_rows, summarize_target_weighted_quality
from opinions_agent.evals.v2.scorers import (
    candidate_grouping,
    make_candidate_independent_quality_judge,
    make_candidate_quality_judge,
    make_opinion_judges,
)


class FakeJudgeClient:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.requests: list[list[dict]] = []
        self.chat = self
        self.completions = self

    async def create(self, *, model: str, messages: list[dict], temperature: float):
        self.requests.append(messages)
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


async def test_candidate_quality_reuses_candidates_across_add_targets_and_excludes_updates(settings):
    client = FakeJudgeClient(
        [
            {"pass": True, "missing": "", "rationale": "Complete."},
            {"pass": True, "missing": "", "rationale": "Complete."},
        ]
    )
    judge = make_candidate_quality_judge(settings, client=client)
    first_add = target()
    second_add = {**target(), "target_id": "W05-02", "required_sources": ["rw:b"]}
    update_target = {
        **target(kind="update", base_text="Existing opinion."),
        "target_id": "W05-03",
        "required_sources": ["rw:c"],
    }
    output = {
        "week": "W05",
        "candidates": [
            {
                "candidate_id": "candidate-001",
                "section": "Agentic Software",
                "opinion_text": "Precise design remains necessary.",
                "evidence_ids": ["rw:a", "rw:b", "rw:c"],
            }
        ],
    }

    score = await judge(None, output, {"targets": [first_add, second_add, update_target], "not_converted": []})

    assert score.score == 1.0
    assert [item["target_id"] for item in score.metadata["targets"]] == ["W05-01", "W05-02"]
    assert [item["proposal_ids"] for item in score.metadata["targets"]] == [
        ["candidate-001"],
        ["candidate-001"],
    ]


async def test_candidate_independent_quality_passes_when_one_candidate_covers_the_target(settings):
    client = FakeJudgeClient(
        [
            {"pass": True, "missing": "", "rationale": "Complete alone."},
            {"pass": False, "missing": "Core claim.", "rationale": "Unrelated extra."},
        ]
    )
    judge = make_candidate_independent_quality_judge(settings, client=client)
    target_value = {**target(), "required_sources": ["rw:a", "rw:b"]}
    output = {
        "week": "W05",
        "candidates": [
            {
                "candidate_id": "candidate-001",
                "section": "Agentic Software",
                "opinion_text": "Complete target opinion.",
                "evidence_ids": ["rw:a"],
            },
            {
                "candidate_id": "candidate-002",
                "section": "Agentic Software",
                "opinion_text": "Unrelated extra opinion.",
                "evidence_ids": ["rw:b"],
            },
        ],
    }

    score = await judge(None, output, expected(target_value))

    assert score.score == 1.0
    assert score.metadata["targets"][0]["passing_candidate_ids"] == ["candidate-001"]


async def test_candidate_independent_quality_rejects_collectively_complete_split(settings):
    client = FakeJudgeClient(
        [
            {"pass": False, "missing": "Second half.", "rationale": "Only the first half."},
            {"pass": False, "missing": "First half.", "rationale": "Only the second half."},
        ]
    )
    judge = make_candidate_independent_quality_judge(settings, client=client)
    target_value = {**target(), "required_sources": ["rw:a", "rw:b"]}
    output = {
        "week": "W05",
        "candidates": [
            {
                "candidate_id": "candidate-001",
                "section": "Agentic Software",
                "opinion_text": "First load-bearing half.",
                "evidence_ids": ["rw:a"],
            },
            {
                "candidate_id": "candidate-002",
                "section": "Agentic Software",
                "opinion_text": "Second load-bearing half.",
                "evidence_ids": ["rw:b"],
            },
        ],
    }

    score = await judge(None, output, expected(target_value))

    assert score.score == 0.0
    assert score.metadata["targets"][0]["candidate_ids"] == ["candidate-001", "candidate-002"]
    assert score.metadata["targets"][0]["passing_candidate_ids"] == []
    assert all(
        "First load-bearing half." not in request[0]["content"]
        or "Second load-bearing half." not in request[0]["content"]
        for request in client.requests
    )


async def test_concept_quality_combines_candidates_with_target_evidence(settings):
    client = FakeJudgeClient([{"pass": True, "missing": "", "rationale": "Together complete."}])
    quality, _, _, _ = make_opinion_judges(settings, client=client)
    target_value = {**target(), "required_sources": ["rw:a", "rw:b"]}
    first = {**proposal(kind="add"), "proposal_id": "p1", "opinion_text": "First load-bearing half."}
    second = {
        **proposal(kind="add"),
        "proposal_id": "p2",
        "opinion_text": "Second load-bearing half.",
        "evidence_ids": ["rw:b"],
    }

    score = await quality(None, {"week": "W05", "proposals": [first, second]}, expected(target_value))

    assert score.score == 1.0
    assert score.metadata["targets"][0]["proposal_ids"] == ["p1", "p2"]
    request_text = client.requests[0][0]["content"]
    assert "First load-bearing half." in request_text
    assert "Second load-bearing half." in request_text


async def test_operation_accuracy_allows_new_opinion_to_be_split_across_adds(settings):
    client = FakeJudgeClient([{"pass": True, "missing": "", "rationale": "Together complete."}])
    quality, _, operation, quality_v2 = make_opinion_judges(settings, client=client)
    target_value = {**target(), "required_sources": ["rw:a", "rw:b"]}
    first = {**proposal(kind="add"), "proposal_id": "p1"}
    second = {**proposal(kind="add"), "proposal_id": "p2", "evidence_ids": ["rw:b"]}
    output = {"week": "W05", "proposals": [first, second]}

    quality_score = await quality(None, output, expected(target_value))
    operation_score = await operation(None, output, expected(target_value))
    v2_score = await quality_v2(None, output, expected(target_value))

    assert quality_score.score == 1.0
    assert operation_score.score == 1.0
    assert v2_score.score == 1.0


def test_candidate_grouping_reports_over_merge_separately():
    targets = [target(), {**target(), "target_id": "W05-02", "required_sources": ["rw:b"]}]
    output = {
        "candidates": [
            {
                "candidate_id": "candidate-001",
                "section": "Agentic Software",
                "opinion_text": "One combined candidate.",
                "evidence_ids": ["rw:a", "rw:b"],
            }
        ]
    }

    score = candidate_grouping(None, output, {"targets": targets, "not_converted": []})

    assert score.score == 0.0
    assert score.metadata["over_merged_pairs"] == [["rw:a", "rw:b"]]
    assert score.metadata["under_merged_pairs"] == []


def test_candidate_grouping_reports_under_merge_separately():
    target_value = {**target(), "required_sources": ["rw:a", "rw:b"]}
    output = {
        "candidates": [
            {
                "candidate_id": "candidate-001",
                "section": "Agentic Software",
                "opinion_text": "First candidate.",
                "evidence_ids": ["rw:a"],
            },
            {
                "candidate_id": "candidate-002",
                "section": "Agentic Software",
                "opinion_text": "Second candidate.",
                "evidence_ids": ["rw:b"],
            },
        ]
    }

    score = candidate_grouping(None, output, expected(target_value))

    assert score.score == 0.0
    assert score.metadata["over_merged_pairs"] == []
    assert score.metadata["under_merged_pairs"] == [["rw:a", "rw:b"]]


async def test_candidate_quality_is_null_for_historical_output_without_snapshot(settings):
    judge = make_candidate_quality_judge(settings, client=FakeJudgeClient([]))

    score = await judge(None, {"week": "W05", "proposals": []}, expected(target()))

    assert score.score is None
    assert score.metadata == {"reason": "stored output has no candidate snapshot"}


def test_v2_rescore_fetches_every_page(settings, monkeypatch):
    pages = [
        {
            "events": [
                {
                    "input": {"week": "W05"},
                    "expected": {"targets": []},
                    "output": {"candidates": []},
                    "span_attributes": {"type": "eval"},
                }
            ],
            "cursor": "next-page",
        },
        {
            "events": [
                {
                    "input": {"week": "W04"},
                    "expected": {"targets": []},
                    "output": {"candidates": []},
                    "span_attributes": {"type": "eval"},
                }
            ],
            "cursor": "end-page",
        },
        {"events": [], "cursor": None},
    ]
    requests = []

    class Response:
        def __init__(self, payload):
            self.content = json.dumps(payload).encode()

        def raise_for_status(self):
            return None

    def post(url, **kwargs):
        requests.append(kwargs["json"])
        return Response(pages.pop(0))

    monkeypatch.setattr("opinions_agent.evals.v2.runner._get_experiment", lambda *_: {"id": "experiment-id"})
    monkeypatch.setattr("httpx.post", post)

    rows = _fetch_experiment_rows(settings, "source-run")

    assert [row["input"]["week"] for row in rows] == ["W04", "W05"]
    assert requests == [
        {"limit": 1000},
        {"limit": 1000, "cursor": "next-page"},
        {"limit": 1000, "cursor": "end-page"},
    ]


def test_v2_target_weighted_summary_supports_v2_metrics():
    results = [
        SimpleNamespace(
            scores={"candidate_quality": 0.5, "operation_accuracy": 2 / 3, "opinion_quality_v2": 1 / 3},
            expected={"targets": [{"kind": "update"}, {"kind": "add"}, {"kind": "add"}]},
        ),
        SimpleNamespace(
            scores={"candidate_quality": 0.75, "operation_accuracy": 0.8, "opinion_quality_v2": 1.0},
            expected={"targets": [{"kind": "update"}, {}, {}, {}, {}]},
        ),
    ]
    assert summarize_target_weighted_quality(results, "candidate_quality", target_kind="add") == (
        "candidate_quality (target-weighted): 4/6 = 0.6667"
    )
    assert summarize_target_weighted_quality(results, "operation_accuracy") == (
        "operation_accuracy (target-weighted): 6/8 = 0.7500"
    )
    assert summarize_target_weighted_quality(results, "opinion_quality_v2") == (
        "opinion_quality_v2 (target-weighted): 6/8 = 0.7500"
    )
