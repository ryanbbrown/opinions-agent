"""Braintrust scorers: deterministic evidence classification plus the opinion LLM judges."""

from __future__ import annotations

import asyncio
import html
import json
import re
from typing import Any

from braintrust import Score

from opinions_agent.config import Settings
from opinions_agent.evals.v2.proposals import extract_current_opinion_text

BRAINTRUST_PROXY_URL = "https://api.braintrust.dev/v1/proxy"
JUDGE_MODEL = "claude-sonnet-4-5"

JUDGE_PROMPT = """\
You are grading whether a generated opinion covers a fixed checklist of required core concepts, in a way that \
agrees with the stance of a canonical opinion.

Canonical opinion (stance reference only — do not require its exact wording or every detail it happens to contain):
{ideal}

Required core concepts — the generated opinion must express every one of these:
{concepts}

Generated opinion set:
{generated}

Grade in two steps:
1. Coverage. Decide whether the generated opinions collectively express each required core concept. One generated
opinion can cover several canonical targets, and several generated opinions can together cover one target. Ignore how
the content was split or merged; separate scorers grade grouping, evidence, and operation. Wording may differ and
concepts may be bridged differently, but a concept weakened into a vague umbrella claim is not covered.
2. Stance. The generated opinions that express the target must take the same side as the canonical opinion. Unrelated
opinions in the set do not matter.

The check is binary. The set passes only if every required core concept is covered and the stance agrees. Extra detail
beyond the concept list does not by itself cause a failure.

Answer with JSON only, no other text:
{{"concepts": [{{"concept": "<concept text>", "covered": true | false}}, ...], \
"stance_agrees": true | false, "pass": true | false, \
"missing": "<concepts missing or weakened; empty if none>", \
"rationale": "<one or two sentences>"}}
"""

ATTEMPT_PROMPT = """\
A generated opinion is being compared to a canonical opinion written from the same source evidence.

Canonical opinion:
{ideal}

Generated opinion set:
{generated}

Question: does at least one opinion, or a combination of the opinions, attempt the same central claim as the canonical
opinion — the same core stance about the same subject — even if supporting concepts, named examples, numbers, or
caveats are missing? Answer false only when the set contains no attempt at that claim.

Answer with JSON only, no other text:
{{"same_claim": true | false, "note": "<one short sentence>"}}
"""


def evidence_recall(input: Any, output: Any, expected: Any) -> Score:
    """Fraction of ground-truth-converted evidence IDs cited by at least one proposal."""
    converted = _converted_ids(expected)
    cited = _cited_ids(output)
    if not converted:
        return Score(name="evidence_recall", score=None, metadata={"reason": "no converted evidence in ground truth"})
    missing = sorted(converted - cited)
    return Score(
        name="evidence_recall",
        score=(len(converted) - len(missing)) / len(converted),
        metadata={"missing": missing, "converted": sorted(converted)},
    )


def evidence_precision(input: Any, output: Any, expected: Any) -> Score:
    """Of the week's evidence IDs cited in proposals, the fraction ground truth also converts."""
    converted = _converted_ids(expected)
    not_converted = {evidence["evidence_id"] for evidence in expected["not_converted"]}
    cited = _cited_ids(output)
    cited_in_week = cited & (converted | not_converted)
    cited_outside_week = sorted(cited - converted - not_converted)
    if not cited_in_week:
        return Score(
            name="evidence_precision",
            score=1.0,
            metadata={"reason": "no selected evidence cited", "cited_outside_week": cited_outside_week},
        )
    leaked = sorted(cited_in_week & not_converted)
    return Score(
        name="evidence_precision",
        score=1.0 - len(leaked) / len(cited_in_week),
        metadata={"leaked": leaked, "cited_outside_week": cited_outside_week},
    )


def candidate_grouping(input: Any, output: Any, expected: Any) -> Score:
    """Pairwise F1 for the evidence partition in the frozen candidate snapshot.

    Evidence selection is scored elsewhere. This score considers only converted evidence that appears in a candidate.
    Over-merged pairs lower precision; under-merged pairs lower recall.
    """
    if "candidates" not in output:
        return Score(
            name="candidate_grouping",
            score=None,
            metadata={"reason": "stored output has no candidate snapshot"},
        )
    expected_owner = {
        evidence_id: target["target_id"] for target in expected["targets"] for evidence_id in target["required_sources"]
    }
    candidate_evidence = [
        set(candidate.get("evidence_ids", [])) & set(expected_owner) for candidate in output["candidates"]
    ]
    observed = sorted(set().union(*candidate_evidence) if candidate_evidence else set())
    if len(observed) < 2:
        return Score(
            name="candidate_grouping",
            score=None,
            metadata={"reason": "fewer than two converted evidence items were cited"},
        )

    over_merged: list[list[str]] = []
    under_merged: list[list[str]] = []
    true_positive = false_positive = false_negative = 0
    for index, left in enumerate(observed):
        for right in observed[index + 1 :]:
            expected_together = expected_owner[left] == expected_owner[right]
            predicted_together = any({left, right} <= group for group in candidate_evidence)
            if expected_together and predicted_together:
                true_positive += 1
            elif predicted_together:
                false_positive += 1
                over_merged.append([left, right])
            elif expected_together:
                false_negative += 1
                under_merged.append([left, right])

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return Score(
        name="candidate_grouping",
        score=score,
        metadata={
            "precision": precision,
            "recall": recall,
            "over_merged_pairs": over_merged,
            "under_merged_pairs": under_merged,
            "observed_evidence": observed,
        },
    )


def opinion_brevity(input: Any, output: Any, expected: Any) -> Score:
    """Mean proposal length vs the week's mean target length: 1.0 at or below the golden length, lower when longer.

    A reference metric, not a gate — opinion_quality already guards under-writing, so shorter than golden caps at 1.0.
    """
    targets = expected["targets"]
    if not targets:
        return Score(name="opinion_brevity", score=None, metadata={"reason": "no opinion targets this week"})
    proposal_words = [
        len((proposal.get("opinion_text") or _strip_tags(proposal.get("message_text") or "")).split())
        for proposal in output.get("proposals", [])
    ]
    if not proposal_words or not sum(proposal_words):
        return Score(name="opinion_brevity", score=None, metadata={"reason": "no proposal text"})
    target_mean = sum(len(target["ideal_opinion"].split()) for target in targets) / len(targets)
    proposal_mean = sum(proposal_words) / len(proposal_words)
    return Score(
        name="opinion_brevity",
        score=min(1.0, target_mean / proposal_mean),
        metadata={"proposal_mean_words": round(proposal_mean, 1), "target_mean_words": round(target_mean, 1)},
    )


def make_candidate_quality_judge(settings: Settings, *, model: str = JUDGE_MODEL, client: Any = None):
    """Grade the complete frozen post-critic opinion set against add targets before consolidation."""
    conceptual_quality, _, _, _ = make_opinion_judges(settings, model=model, client=client)

    async def candidate_quality(input: Any, output: Any, expected: Any) -> Score:
        if "candidates" not in output:
            return Score(
                name="candidate_quality",
                score=None,
                metadata={"reason": "stored output has no candidate snapshot"},
            )
        targets = [target for target in expected["targets"] if target.get("kind", "add") == "add"]
        if not targets:
            return Score(name="candidate_quality", score=None, metadata={"reason": "no add targets this week"})
        proposals = [
            {
                "proposal_id": candidate["candidate_id"],
                "kind": "add",
                "section": candidate["section"],
                "opinion_text": candidate["opinion_text"],
                "evidence_ids": candidate["evidence_ids"],
                "message_text": candidate["opinion_text"],
            }
            for candidate in output["candidates"]
        ]
        score = await conceptual_quality(
            input,
            {"week": output.get("week"), "proposals": proposals},
            {**expected, "targets": targets},
        )
        return Score(name="candidate_quality", score=score.score, metadata=score.metadata)

    return candidate_quality


def make_candidate_independent_quality_judge(settings: Settings, *, model: str = JUDGE_MODEL, client: Any = None):
    """Grade whether one frozen candidate independently covers each add target."""
    if client is None:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=BRAINTRUST_PROXY_URL, api_key=settings.braintrust_api_key)

    async def candidate_independent_quality(input: Any, output: Any, expected: Any) -> Score:
        if "candidates" not in output:
            return Score(
                name="candidate_independent_quality",
                score=None,
                metadata={"reason": "stored output has no candidate snapshot"},
            )
        targets = [target for target in expected["targets"] if target.get("kind", "add") == "add"]
        if not targets:
            return Score(
                name="candidate_independent_quality",
                score=None,
                metadata={"reason": "no add targets this week"},
            )
        proposals = [
            {
                "proposal_id": candidate["candidate_id"],
                "kind": "add",
                "section": candidate["section"],
                "opinion_text": candidate["opinion_text"],
                "evidence_ids": candidate["evidence_ids"],
                "message_text": candidate["opinion_text"],
            }
            for candidate in output["candidates"]
        ]
        per_target = []
        for target in targets:
            linked = _proposals_for_target(proposals, target)
            verdicts = await asyncio.gather(*(_judge_pair(client, model, target, [proposal]) for proposal in linked))
            candidate_results = [
                {
                    "candidate_id": proposal["proposal_id"],
                    "pass": verdict.get("pass") is True,
                    "missing": verdict.get("missing"),
                    "rationale": verdict.get("rationale"),
                }
                for proposal, verdict in zip(linked, verdicts, strict=True)
            ]
            per_target.append(
                {
                    "target_id": target["target_id"],
                    "candidate_ids": [proposal["proposal_id"] for proposal in linked],
                    "passing_candidate_ids": [result["candidate_id"] for result in candidate_results if result["pass"]],
                    "pass": any(result["pass"] for result in candidate_results),
                    "candidates": candidate_results,
                }
            )
        return Score(
            name="candidate_independent_quality",
            score=sum(1 for target in per_target if target["pass"]) / len(per_target),
            metadata={"targets": per_target},
        )

    return candidate_independent_quality


def make_opinion_judges(settings: Settings, *, model: str = JUDGE_MODEL, client: Any = None):
    """Build conceptual, attempted, operation, and operation-gated quality scorers over one shared evaluation."""
    if client is None:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=BRAINTRUST_PROXY_URL, api_key=settings.braintrust_api_key)

    evaluations: dict[str, asyncio.Task] = {}

    async def _evaluate(output: Any, expected: Any) -> dict | None:
        targets = expected["targets"]
        if not targets:
            return None
        proposals = output.get("proposals", [])
        per_target = []
        matched_proposal_ids: set[str] = set()
        for target in targets:
            target_proposals = _proposals_for_target(proposals, target)
            matched_proposal_ids.update(proposal["proposal_id"] for proposal in target_proposals)
            if not target_proposals:
                per_target.append(
                    {
                        "target_id": target["target_id"],
                        "proposal_ids": [],
                        "verdict": "unmatched",
                        "attempted": False,
                        "score": 0.0,
                        **_operation_result(target, []),
                    }
                )
                continue
            verdict = await _judge_pair(client, model, target, target_proposals)
            passed = verdict.get("pass") is True
            attempted, attempt_note = True, None
            if not passed:
                attempt = await _judge_attempt(client, model, target, target_proposals)
                attempted = attempt.get("same_claim") is True
                attempt_note = attempt.get("note")
            per_target.append(
                {
                    "target_id": target["target_id"],
                    "proposal_ids": [proposal["proposal_id"] for proposal in target_proposals],
                    "generated": _generated_opinion_set(target_proposals),
                    "verdict": "pass" if passed else "fail",
                    "missing": verdict.get("missing"),
                    "rationale": verdict.get("rationale"),
                    "concepts": verdict.get("concepts"),
                    "stance_agrees": verdict.get("stance_agrees"),
                    "attempted": attempted,
                    "attempt_note": attempt_note,
                    "score": 1.0 if passed else 0.0,
                    **_operation_result(target, target_proposals),
                }
            )
        return {
            "targets": per_target,
            "unmatched_proposals": [
                proposal["proposal_id"] for proposal in proposals if proposal["proposal_id"] not in matched_proposal_ids
            ],
        }

    def _shared_evaluation(input: Any, output: Any, expected: Any) -> asyncio.Task:
        week = next(
            (source["week"] for source in (input, output) if isinstance(source, dict) and source.get("week")), None
        )
        if week is None or week not in evaluations:
            task = asyncio.ensure_future(_evaluate(output, expected))
            if week is None:
                return task
            evaluations[week] = task
        return evaluations[week]

    async def opinion_quality(input: Any, output: Any, expected: Any) -> Score:
        evaluation = await _shared_evaluation(input, output, expected)
        if evaluation is None:
            return Score(name="opinion_quality", score=None, metadata={"reason": "no opinion targets this week"})
        targets = evaluation["targets"]
        return Score(
            name="opinion_quality",
            score=sum(target["score"] for target in targets) / len(targets),
            metadata={"targets": targets, "unmatched_proposals": evaluation["unmatched_proposals"]},
        )

    async def opinion_attempted(input: Any, output: Any, expected: Any) -> Score:
        evaluation = await _shared_evaluation(input, output, expected)
        if evaluation is None:
            return Score(name="opinion_attempted", score=None, metadata={"reason": "no opinion targets this week"})
        targets = evaluation["targets"]
        return Score(
            name="opinion_attempted",
            score=sum(1 for target in targets if target["attempted"]) / len(targets),
            metadata={
                "targets": [
                    {
                        "target_id": target["target_id"],
                        "proposal_ids": target.get("proposal_ids", []),
                        "attempted": target["attempted"],
                        "note": target.get("attempt_note"),
                    }
                    for target in targets
                ]
            },
        )

    async def operation_accuracy(input: Any, output: Any, expected: Any) -> Score:
        evaluation = await _shared_evaluation(input, output, expected)
        if evaluation is None:
            return Score(name="operation_accuracy", score=None, metadata={"reason": "no opinion targets this week"})
        targets = evaluation["targets"]
        return Score(
            name="operation_accuracy",
            score=sum(1 for target in targets if target["operation_valid"]) / len(targets),
            metadata={
                "targets": [
                    {
                        "target_id": target["target_id"],
                        "proposal_ids": target.get("proposal_ids", []),
                        "operation_valid": target["operation_valid"],
                        "operation_reason": target["operation_reason"],
                        "expected_operation": target["expected_operation"],
                        "proposal_kind": target.get("proposal_kind"),
                    }
                    for target in targets
                ]
            },
        )

    async def opinion_quality_v2(input: Any, output: Any, expected: Any) -> Score:
        evaluation = await _shared_evaluation(input, output, expected)
        if evaluation is None:
            return Score(name="opinion_quality_v2", score=None, metadata={"reason": "no opinion targets this week"})
        targets = evaluation["targets"]
        return Score(
            name="opinion_quality_v2",
            score=sum(target["score"] for target in targets if target["operation_valid"]) / len(targets),
            metadata={
                "targets": [
                    {
                        "target_id": target["target_id"],
                        "proposal_ids": target.get("proposal_ids", []),
                        "conceptual_verdict": target["verdict"],
                        "operation_valid": target["operation_valid"],
                        "operation_reason": target["operation_reason"],
                        "score": target["score"] if target["operation_valid"] else 0.0,
                    }
                    for target in targets
                ]
            },
        )

    return opinion_quality, opinion_attempted, operation_accuracy, opinion_quality_v2


def _operation_result(target: dict, proposals: list[dict]) -> dict:
    target_kind = target.get("kind", "add")
    expected_operation = "add" if target_kind == "add" else "update"
    if not proposals:
        return {
            "operation_valid": False,
            "operation_reason": "no evidence-linked proposal",
            "expected_operation": expected_operation,
            "proposal_kind": None,
        }

    required_sources = set(target["required_sources"])
    routed_sources = set().union(*(set(proposal.get("evidence_ids", [])) for proposal in proposals))
    proposal_kinds = {proposal.get("kind") or "unknown" for proposal in proposals}
    proposal_kind = next(iter(proposal_kinds)) if len(proposal_kinds) == 1 else "mixed"
    if not required_sources <= routed_sources:
        return {
            "operation_valid": False,
            "operation_reason": "required evidence is not fully routed",
            "expected_operation": expected_operation,
            "proposal_kind": proposal_kind,
        }
    if target_kind == "add":
        valid = proposal_kinds == {"add"}
        return {
            "operation_valid": valid,
            "operation_reason": "correct add" if valid else f"add target proposed as {proposal_kind}",
            "expected_operation": expected_operation,
            "proposal_kind": proposal_kind,
        }
    if not proposal_kinds <= {"revise", "update"}:
        return {
            "operation_valid": False,
            "operation_reason": f"update target proposed as {proposal_kind}",
            "expected_operation": expected_operation,
            "proposal_kind": proposal_kind,
        }
    expected_current = _normalize_opinion_text(target.get("base_opinion_text"))
    currents = {
        _normalize_opinion_text(
            proposal.get("current_opinion_text") or extract_current_opinion_text(proposal.get("message_text") or "")
        )
        for proposal in proposals
    }
    valid = bool(expected_current) and currents == {expected_current}
    return {
        "operation_valid": valid,
        "operation_reason": "correct update" if valid else "revision does not identify the canonical base opinion",
        "expected_operation": expected_operation,
        "proposal_kind": proposal_kind,
    }


def _normalize_opinion_text(text: str | None) -> str:
    return " ".join((text or "").split())


def _proposals_for_target(proposals: list[dict], target: dict) -> list[dict]:
    required_sources = set(target["required_sources"])
    return [proposal for proposal in proposals if required_sources & set(proposal.get("evidence_ids", []))]


def _converted_ids(expected: Any) -> set[str]:
    return {evidence_id for target in expected["targets"] for evidence_id in target["required_sources"]}


def _cited_ids(output: Any) -> set[str]:
    return {evidence_id for proposal in output.get("proposals", []) for evidence_id in proposal.get("evidence_ids", [])}


def _generated_opinion_set(proposals: list[dict]) -> str:
    return "\n\n".join(
        f"[{proposal['proposal_id']}]\n"
        f"{proposal.get('opinion_text') or _strip_tags(proposal.get('message_text') or '')}"
        for proposal in proposals
    )


async def _judge_pair(client: Any, model: str, target: dict, proposals: list[dict]) -> dict:
    concepts = "\n".join(f"- {concept}" for concept in target.get("required_concepts", []))
    generated = _generated_opinion_set(proposals)
    prompt = JUDGE_PROMPT.format(ideal=target["ideal_opinion"], concepts=concepts or "(none)", generated=generated)
    return await _judge_json(client, model, prompt)


async def _judge_attempt(client: Any, model: str, target: dict, proposals: list[dict]) -> dict:
    prompt = ATTEMPT_PROMPT.format(ideal=target["ideal_opinion"], generated=_generated_opinion_set(proposals))
    return await _judge_json(client, model, prompt)


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


async def _judge_json(client: Any, model: str, prompt: str) -> dict:
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = (response.choices[0].message.content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"judge did not return JSON: {text[:200]!r}")
    return json.loads(text[start : end + 1])
