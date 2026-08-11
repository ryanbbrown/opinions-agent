from __future__ import annotations

import json
from pathlib import Path

import pytest

from opinions_agent.agent import TelegramButtonSpec, TelegramMessageSpec
from opinions_agent.corpus import CorpusPaths
from opinions_agent.evals.proposals import parse_proposals
from opinions_agent.evals.scorers import (
    evidence_precision,
    evidence_recall,
    make_opinion_judges,
    match_proposals_to_targets,
    opinion_brevity,
)
from opinions_agent.evals.targets import build_seed_opinions, load_week_cases, verify_week_partition
from opinions_agent.opinions_doc import parse_opinions

PROPOSAL_TEXT = """<b>Add Opinion #1</b>
<i>Section:</i> Agentic Software

<b>Opinion</b>
Specs &amp; prompts don't remove the need for precise design.

<b>Sources</b>
A sufficiently detailed spec is code

<blockquote expandable>
<b>Evidence</b>

A sufficiently detailed spec is code — rw:01kp4spezcbaka7nxvzn7wm08h
If you try to make a specification document precise enough...
</blockquote>"""


def proposal_message(text: str = PROPOSAL_TEXT, proposal_slug: str = "add-opinion-1") -> TelegramMessageSpec:
    return TelegramMessageSpec(
        text=text,
        buttons=[
            TelegramButtonSpec(text="Approve", callback_data=f"approve:{proposal_slug}"),
            TelegramButtonSpec(text="Reject", callback_data=f"reject:{proposal_slug}"),
        ],
    )


class FakeJudgeClient:
    """Stands in for AsyncOpenAI: returns queued JSON payloads and records prompts."""

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.prompts: list[str] = []
        self.chat = self
        self.completions = self

    async def create(self, *, model: str, messages: list[dict], temperature: float):
        self.prompts.append(messages[0]["content"])
        if not self.payloads:
            raise AssertionError("unexpected judge call")
        payload = self.payloads.pop(0)

        class _Message:
            content = json.dumps(payload)

        class _Choice:
            message = _Message()

        class _Response:
            choices = [_Choice()]

        return _Response()


def target(target_id: str, ideal: str, sources: list[str]) -> dict:
    return {
        "target_id": target_id,
        "kind": "add",
        "section": "Agentic Software",
        "ideal_opinion": ideal,
        "required_sources": sources,
        "source_quotes": [{"title": "Doc", "quote": "Quote text."}],
    }


def output_with(proposals: list[dict]) -> dict:
    return {"week": "W05", "status": "awaiting_user", "proposals": proposals}


def proposal(proposal_id: str, evidence_ids: list[str], text: str = "Generated opinion.") -> dict:
    return {
        "proposal_id": proposal_id,
        "kind": "add",
        "heading": "Add Opinion",
        "section": "Agentic Software",
        "opinion_text": text,
        "evidence_ids": evidence_ids,
        "message_text": text,
    }


def test_parse_proposals_extracts_canonical_fields():
    parsed = parse_proposals([proposal_message()])
    assert len(parsed) == 1
    extracted = parsed[0]
    assert extracted.proposal_id == "add-opinion-1"
    assert extracted.kind == "add"
    assert extracted.section == "Agentic Software"
    assert extracted.opinion_text == "Specs & prompts don't remove the need for precise design."
    assert extracted.evidence_ids == ["rw:01kp4spezcbaka7nxvzn7wm08h"]


def test_parse_proposals_skips_messages_without_approve_button():
    summary = TelegramMessageSpec(text="Done: 2 opinions added.")
    assert parse_proposals([summary, proposal_message()]) == parse_proposals([proposal_message()])


def test_parse_proposals_handles_revised_headings():
    text = PROPOSAL_TEXT.replace("<b>Add Opinion #1</b>", "<b>Add Opinion #1 (Revised)</b>")
    parsed = parse_proposals([proposal_message(text, proposal_slug="add-opinion-1-revised")])
    assert parsed[0].proposal_id == "add-opinion-1-revised"
    assert parsed[0].kind == "add"


def test_parse_proposals_accepts_labeled_opinion_variants():
    text = PROPOSAL_TEXT.replace("<b>Add Opinion #1</b>", "<b>Update Opinion #1</b>").replace(
        "<b>Opinion</b>", "<b>Revised Opinion</b>"
    )
    parsed = parse_proposals([proposal_message(text, proposal_slug="update-opinion-1")])
    assert parsed[0].kind == "update"
    assert parsed[0].opinion_text == "Specs & prompts don't remove the need for precise design."


def test_evidence_recall_counts_missing_ground_truth_sources():
    expected = {"targets": [target("W05-01", "Ideal.", ["rw:a", "rw:b"])], "not_converted": []}
    output = output_with([proposal("p1", ["rw:a"])])
    score = evidence_recall(None, output, expected)
    assert score.score == 0.5
    assert score.metadata["missing"] == ["rw:b"]


def test_evidence_recall_skips_weeks_without_targets():
    expected = {"targets": [], "not_converted": [{"evidence_id": "rw:x", "title": "T", "evidence_kind": "highlight"}]}
    assert evidence_recall(None, output_with([]), expected).score is None


def test_evidence_precision_penalizes_not_converted_leaks():
    expected = {
        "targets": [target("W05-01", "Ideal.", ["rw:a"])],
        "not_converted": [{"evidence_id": "rw:leak", "title": "T", "evidence_kind": "highlight"}],
    }
    output = output_with([proposal("p1", ["rw:a", "rw:leak"])])
    score = evidence_precision(None, output, expected)
    assert score.score == 0.5
    assert score.metadata["leaked"] == ["rw:leak"]


def test_evidence_precision_ignores_citations_outside_week_universe():
    expected = {
        "targets": [target("W05-01", "Ideal.", ["rw:a"])],
        "not_converted": [{"evidence_id": "rw:other", "title": "T", "evidence_kind": "highlight"}],
    }
    output = output_with([proposal("p1", ["rw:a", "rw:historical"])])
    score = evidence_precision(None, output, expected)
    assert score.score == 1.0
    assert score.metadata["cited_outside_week"] == ["rw:historical"]


def test_evidence_precision_perfect_when_nothing_cited():
    expected = {"targets": [], "not_converted": [{"evidence_id": "rw:x", "title": "T", "evidence_kind": "highlight"}]}
    assert evidence_precision(None, output_with([]), expected).score == 1.0


def test_opinion_brevity_penalizes_proposals_longer_than_golden():
    expected = {"targets": [target("W05-01", "one two three four", ["rw:a"])], "not_converted": []}
    output = output_with([proposal("p1", ["rw:a"], text="one two three four five six seven eight")])
    score = opinion_brevity(None, output, expected)
    assert score.score == 0.5
    assert score.metadata == {"proposal_mean_words": 8, "target_mean_words": 4}


def test_opinion_brevity_caps_at_one_below_golden_length():
    # Under-writing is opinion_quality's problem; brevity only measures overshoot.
    expected = {"targets": [target("W05-01", "one two three four five six", ["rw:a"])], "not_converted": []}
    output = output_with([proposal("p1", ["rw:a"], text="one two three")])
    assert opinion_brevity(None, output, expected).score == 1.0


def test_opinion_brevity_skips_weeks_without_targets_or_proposals():
    no_targets = {"targets": [], "not_converted": []}
    assert opinion_brevity(None, output_with([proposal("p1", ["rw:a"])]), no_targets).score is None
    with_targets = {"targets": [target("W05-01", "one two", ["rw:a"])], "not_converted": []}
    assert opinion_brevity(None, output_with([]), with_targets).score is None


async def test_match_by_evidence_overlap_does_not_call_llm():
    client = FakeJudgeClient([])
    targets = [target("W05-01", "Ideal one.", ["rw:a"]), target("W05-02", "Ideal two.", ["rw:b"])]
    proposals = [proposal("p1", ["rw:b"]), proposal("p2", ["rw:a"])]
    matches = await match_proposals_to_targets(proposals, targets, client=client, model="test")
    assert matches["W05-01"]["proposal_id"] == "p2"
    assert matches["W05-02"]["proposal_id"] == "p1"
    assert client.prompts == []


async def test_match_resolves_tied_overlap_with_llm():
    client = FakeJudgeClient([{"choice": 2}])
    targets = [target("W05-01", "Ideal one.", ["rw:a", "rw:b"])]
    proposals = [proposal("p1", ["rw:a"], text="First split."), proposal("p2", ["rw:b"], text="Second split.")]
    matches = await match_proposals_to_targets(proposals, targets, client=client, model="test")
    assert matches["W05-01"]["proposal_id"] == "p2"
    assert len(client.prompts) == 1


async def test_match_resolves_zero_overlap_with_llm():
    client = FakeJudgeClient([{"choice": 1}])
    targets = [target("W05-01", "Ideal one.", ["rw:a"])]
    proposals = [proposal("p1", ["rw:unrelated"], text="Same claim, no citation.")]
    matches = await match_proposals_to_targets(proposals, targets, client=client, model="test")
    assert matches["W05-01"]["proposal_id"] == "p1"
    assert len(client.prompts) == 1


async def test_opinion_quality_scores_matched_and_unmatched_targets(settings):
    client = FakeJudgeClient([{"pass": True, "missing": "", "rationale": "All core concepts present."}])
    quality, _ = make_opinion_judges(settings, client=client)
    expected = {
        "targets": [target("W05-01", "Ideal one.", ["rw:a"]), target("W05-02", "Ideal two.", ["rw:b"])],
        "not_converted": [],
    }
    output = output_with([proposal("p1", ["rw:a"])])
    score = await quality(None, output, expected)
    assert score.score == pytest.approx(0.5)
    by_target = {entry["target_id"]: entry for entry in score.metadata["targets"]}
    assert by_target["W05-01"]["verdict"] == "pass"
    assert by_target["W05-02"]["verdict"] == "unmatched"


async def test_opinion_quality_is_binary_per_target(settings):
    client = FakeJudgeClient(
        [
            {"pass": True, "missing": "", "rationale": "Complete."},
            {"pass": False, "missing": "Price's Law", "rationale": "Dropped the named term."},
            {"same_claim": True, "note": "Same stance, dropped the named term."},
        ]
    )
    quality, _ = make_opinion_judges(settings, client=client)
    expected = {
        "targets": [target("W05-01", "Ideal one.", ["rw:a"]), target("W05-02", "Ideal two.", ["rw:b"])],
        "not_converted": [],
    }
    output = output_with([proposal("p1", ["rw:a"]), proposal("p2", ["rw:b"])])
    score = await quality(None, output, expected)
    assert score.score == pytest.approx(0.5)
    by_target = {entry["target_id"]: entry for entry in score.metadata["targets"]}
    assert by_target["W05-02"]["verdict"] == "fail"
    assert by_target["W05-02"]["missing"] == "Price's Law"


async def test_opinion_attempted_is_lenient_and_shares_the_judge_pass(settings):
    client = FakeJudgeClient(
        [
            {"pass": True, "missing": "", "rationale": "Complete."},
            {"pass": False, "missing": "the mechanism", "rationale": "Dropped the because."},
            {"same_claim": True, "note": "Same stance, missing the mechanism."},
            {"pass": False, "missing": "everything", "rationale": "Talks about something else."},
            {"same_claim": False, "note": "Centers a different claim."},
        ]
    )
    quality, attempted = make_opinion_judges(settings, client=client)
    expected = {
        "targets": [
            target("W05-01", "Ideal one.", ["rw:a"]),
            target("W05-02", "Ideal two.", ["rw:b"]),
            target("W05-03", "Ideal three.", ["rw:c"]),
            target("W05-04", "Ideal four.", ["rw:d"]),
        ],
        "not_converted": [],
    }
    output = output_with([proposal("p1", ["rw:a"]), proposal("p2", ["rw:b"]), proposal("p3", ["rw:c"])])
    quality_score = await quality(None, output, expected)
    attempted_score = await attempted(None, output, expected)
    assert quality_score.score == pytest.approx(0.25)
    assert attempted_score.score == pytest.approx(0.5)
    by_target = {entry["target_id"]: entry for entry in attempted_score.metadata["targets"]}
    assert by_target["W05-01"]["attempted"] is True
    assert by_target["W05-02"]["attempted"] is True
    assert by_target["W05-03"]["attempted"] is False
    assert by_target["W05-04"]["attempted"] is False
    assert len(client.prompts) == 5


async def test_opinion_judges_skip_weeks_without_targets(settings):
    quality, attempted = make_opinion_judges(settings, client=FakeJudgeClient([]))
    assert (await quality(None, output_with([]), {"targets": [], "not_converted": []})).score is None
    assert (await attempted(None, output_with([]), {"targets": [], "not_converted": []})).score is None


REAL_CORPUS = Path(__file__).resolve().parents[1] / ".readwise"


@pytest.mark.skipif(not REAL_CORPUS.exists(), reason="local .readwise corpus not present")
def test_target_weighted_quality_weights_targets_not_weeks():
    from types import SimpleNamespace

    from opinions_agent.evals.runner import summarize_target_weighted_quality

    results = [
        SimpleNamespace(scores={"opinion_quality": 1 / 3}, expected={"targets": [{}, {}, {}]}),
        SimpleNamespace(scores={"opinion_quality": 1.0}, expected={"targets": [{}] * 5}),
        SimpleNamespace(scores={"opinion_quality": None}, expected={"targets": []}),
    ]
    assert summarize_target_weighted_quality(results) == "opinion_quality (target-weighted): 6/8 = 0.7500"
    assert summarize_target_weighted_quality([results[2]]) is None


def test_checked_in_targets_partition_matches_corpus():
    cases = load_week_cases()
    corpus = CorpusPaths(REAL_CORPUS)
    for case in cases:
        verify_week_partition(case, corpus)
    for case in cases:
        for case_target in case.targets:
            assert case_target.required_sources, f"{case_target.target_id} has no required sources"
            if case_target.kind == "update":
                assert case_target.base_opinion_id, f"{case_target.target_id} update without base_opinion_id"


async def test_run_week_case_deterministic_end_to_end(settings):
    from conftest import seed_corpus

    from opinions_agent.evals.runner import run_week_case
    from opinions_agent.evals.targets import WeekCase

    seed_corpus(settings)
    case = WeekCase.model_validate(
        {
            "week": "W01",
            "targets": [
                {
                    "target_id": "W01-01",
                    "section": "Agentic Software",
                    "ideal_opinion": "Durable systems should preserve provenance.",
                    "required_sources": ["rw:h0"],
                    "source_quotes": [
                        {"title": "Example Article", "quote": "Durable systems should preserve provenance."}
                    ],
                }
            ],
            "not_converted": [{"evidence_id": "rw:h1", "title": "Example Article", "evidence_kind": "highlight"}],
        }
    )
    base_doc = parse_opinions(BASE_OPINIONS.replace("rw:base-a", "rw:h1"))
    output = await run_week_case(settings, case, [case], base_doc=base_doc, deterministic=True, parent="")
    assert output["status"] == "awaiting_user"
    assert len(output["proposals"]) == 1
    assert output["proposals"][0]["evidence_ids"] == ["rw:h0"]
    assert output["messages"]
    expected = {
        "targets": [case_target.model_dump(mode="json") for case_target in case.targets],
        "not_converted": [evidence.model_dump(mode="json") for evidence in case.not_converted],
    }
    assert evidence_recall(None, output, expected).score == 1.0
    assert evidence_precision(None, output, expected).score == 1.0


BASE_OPINIONS = """# OPINIONS

## Agentic Software

- Base claim one.
  <!-- opinion-id: opinion-000001 -->
  <!-- sources: rw:base-a -->
"""

SEED_CASES = [
    {
        "week": "W04",
        "targets": [
            {
                "target_id": "W04-01",
                "section": "Career And Work",
                "ideal_opinion": "First canonical opinion.",
                "required_sources": ["rw:w4-a"],
            }
        ],
        "not_converted": [],
    },
    {
        "week": "W05",
        "targets": [
            {
                "target_id": "W05-01",
                "kind": "update",
                "base_opinion_id": "opinion-000001",
                "section": "Agentic Software",
                "ideal_opinion": "Base claim one, sharpened.",
                "required_sources": ["rw:w5-a"],
            }
        ],
        "not_converted": [],
    },
    {"week": "W06", "targets": [], "not_converted": []},
]


def seed_cases():
    from opinions_agent.evals.targets import WeekCase

    return [WeekCase.model_validate(case) for case in SEED_CASES]


def test_seed_builder_accumulates_prior_week_targets():
    doc = build_seed_opinions(parse_opinions(BASE_OPINIONS), seed_cases(), "W06")
    assert [opinion.opinion_id for opinion in doc.opinions] == ["opinion-000001", "opinion-000002"]
    updated = doc.get("opinion-000001")
    assert updated.text == "Base claim one, sharpened."
    assert updated.sources == ["rw:base-a", "rw:w5-a"]
    added = doc.get("opinion-000002")
    assert added.section == "Career And Work"
    assert added.text == "First canonical opinion."
    assert added.sources == ["rw:w4-a"]


def test_seed_builder_first_week_is_base_only():
    doc = build_seed_opinions(parse_opinions(BASE_OPINIONS), seed_cases(), "W04")
    assert [opinion.opinion_id for opinion in doc.opinions] == ["opinion-000001"]
    assert doc.get("opinion-000001").text == "Base claim one."


def test_seed_builder_rejects_unknown_week_and_missing_base_opinion():
    with pytest.raises(ValueError, match="unknown eval week"):
        build_seed_opinions(parse_opinions(BASE_OPINIONS), seed_cases(), "W99")
    cases = seed_cases()
    cases[1].targets[0].base_opinion_id = "opinion-000404"
    with pytest.raises(ValueError, match="opinion-000404"):
        build_seed_opinions(parse_opinions(BASE_OPINIONS), cases, "W06")
