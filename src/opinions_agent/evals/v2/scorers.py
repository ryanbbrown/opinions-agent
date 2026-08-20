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

Generated opinion:
{generated}

Grade in two steps:
1. Coverage. For each required core concept, decide whether the generated opinion expresses it. Wording may \
differ and concepts may be bridged together differently; what matters is that the idea is present and not \
weakened into a vaguer umbrella claim. A concept expressed but hollowed out into something noncommittal is not \
covered.
2. Stance. The generated opinion must take the same side as the canonical opinion. If it covers the concepts but \
argues a different or contradictory position, that is a failure.

The check is binary. The generated opinion passes only if every required core concept is covered and the stance \
agrees. Extra detail beyond the concept list — elaboration, mechanism, examples, or a second point — does not by \
itself cause a failure.

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

Generated opinion:
{generated}

Question: is the generated opinion an attempt at the same central claim as the canonical opinion — the same core
stance about the same subject — even if it is missing supporting concepts, named examples, numbers, or caveats?
Answer false only if it takes a genuinely different stance or centers a different claim entirely.

Answer with JSON only, no other text:
{{"same_claim": true | false, "note": "<one short sentence>"}}
"""

MATCH_PROMPT = """\
A batch of generated opinion proposals needs to be matched against a canonical target opinion.

Target opinion:
{ideal}

Candidate proposals:
{candidates}

Which single candidate expresses the same central claim as the target opinion? If none of them do, answer null.

Answer with JSON only, no other text:
{{"choice": <candidate number or null>}}
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
        matches = await match_proposals_to_targets(proposals, targets, client=client, model=model)
        per_target = []
        for target in targets:
            proposal = matches.get(target["target_id"])
            if proposal is None:
                per_target.append(
                    {
                        "target_id": target["target_id"],
                        "verdict": "unmatched",
                        "attempted": False,
                        "score": 0.0,
                        **_operation_result(target, None),
                    }
                )
                continue
            verdict = await _judge_pair(client, model, target, proposal)
            passed = verdict.get("pass") is True
            attempted, attempt_note = True, None
            if not passed:
                attempt = await _judge_attempt(client, model, target, proposal)
                attempted = attempt.get("same_claim") is True
                attempt_note = attempt.get("note")
            per_target.append(
                {
                    "target_id": target["target_id"],
                    "proposal_id": proposal.get("proposal_id"),
                    "generated": proposal.get("opinion_text"),
                    "verdict": "pass" if passed else "fail",
                    "missing": verdict.get("missing"),
                    "rationale": verdict.get("rationale"),
                    "concepts": verdict.get("concepts"),
                    "stance_agrees": verdict.get("stance_agrees"),
                    "attempted": attempted,
                    "attempt_note": attempt_note,
                    "score": 1.0 if passed else 0.0,
                    **_operation_result(target, proposal),
                }
            )
        return {"targets": per_target, "unmatched_proposals": _unmatched_proposal_ids(proposals, matches)}

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
                        "proposal_id": target.get("proposal_id"),
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
                        "proposal_id": target.get("proposal_id"),
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
                        "proposal_id": target.get("proposal_id"),
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


def _operation_result(target: dict, proposal: dict | None) -> dict:
    target_kind = target.get("kind", "add")
    expected_operation = "add" if target_kind == "add" else "update"
    if proposal is None:
        return {
            "operation_valid": False,
            "operation_reason": "no matched proposal",
            "expected_operation": expected_operation,
            "proposal_kind": None,
        }
    proposal_kind = proposal.get("kind")
    if target_kind == "add":
        valid = proposal_kind == "add"
        return {
            "operation_valid": valid,
            "operation_reason": "correct add" if valid else f"add target proposed as {proposal_kind or 'unknown'}",
            "expected_operation": expected_operation,
            "proposal_kind": proposal_kind,
        }
    if proposal_kind not in {"revise", "update"}:
        return {
            "operation_valid": False,
            "operation_reason": f"update target proposed as {proposal_kind or 'unknown'}",
            "expected_operation": expected_operation,
            "proposal_kind": proposal_kind,
        }
    expected_current = _normalize_opinion_text(target.get("base_opinion_text"))
    current = _normalize_opinion_text(
        proposal.get("current_opinion_text") or extract_current_opinion_text(proposal.get("message_text") or "")
    )
    valid = bool(expected_current) and current == expected_current
    return {
        "operation_valid": valid,
        "operation_reason": "correct update" if valid else "revision does not identify the canonical base opinion",
        "expected_operation": expected_operation,
        "proposal_kind": proposal_kind,
    }


def _normalize_opinion_text(text: str | None) -> str:
    return " ".join((text or "").split())


async def match_proposals_to_targets(
    proposals: list[dict],
    targets: list[dict],
    *,
    client: Any,
    model: str,
) -> dict[str, dict | None]:
    """Pair proposals with targets by evidence overlap; an LLM classifier resolves ambiguous cases."""
    matches: dict[str, dict | None] = {}
    assigned: set[str] = set()
    for target in targets:
        required = set(target["required_sources"])
        candidates = [
            (len(required & set(proposal["evidence_ids"])), proposal)
            for proposal in proposals
            if proposal["proposal_id"] not in assigned and required & set(proposal["evidence_ids"])
        ]
        if not candidates:
            matches[target["target_id"]] = None
            continue
        best = max(overlap for overlap, _ in candidates)
        tied = [proposal for overlap, proposal in candidates if overlap == best]
        proposal = tied[0] if len(tied) == 1 else await _pick_candidate(client, model, target, tied)
        matches[target["target_id"]] = proposal
        if proposal is not None:
            assigned.add(proposal["proposal_id"])
    for target in targets:
        if matches[target["target_id"]] is not None:
            continue
        remaining = [proposal for proposal in proposals if proposal["proposal_id"] not in assigned]
        if not remaining:
            continue
        proposal = await _pick_candidate(client, model, target, remaining)
        matches[target["target_id"]] = proposal
        if proposal is not None:
            assigned.add(proposal["proposal_id"])
    return matches


def _converted_ids(expected: Any) -> set[str]:
    return {evidence_id for target in expected["targets"] for evidence_id in target["required_sources"]}


def _cited_ids(output: Any) -> set[str]:
    return {
        evidence_id
        for proposal in output.get("proposals", [])
        for evidence_id in proposal.get("evidence_ids", [])
    }


def _unmatched_proposal_ids(proposals: list[dict], matches: dict[str, dict | None]) -> list[str]:
    matched = {proposal["proposal_id"] for proposal in matches.values() if proposal is not None}
    return [proposal["proposal_id"] for proposal in proposals if proposal["proposal_id"] not in matched]


async def _pick_candidate(client: Any, model: str, target: dict, candidates: list[dict]) -> dict | None:
    numbered = "\n".join(
        f"{index}. {proposal.get('opinion_text') or proposal.get('heading') or '(no text)'}"
        for index, proposal in enumerate(candidates, start=1)
    )
    prompt = MATCH_PROMPT.format(ideal=target["ideal_opinion"], candidates=numbered)
    payload = await _judge_json(client, model, prompt)
    choice = payload.get("choice")
    if isinstance(choice, int) and 1 <= choice <= len(candidates):
        return candidates[choice - 1]
    return None


async def _judge_pair(client: Any, model: str, target: dict, proposal: dict) -> dict:
    concepts = "\n".join(f"- {concept}" for concept in target.get("required_concepts", []))
    generated = proposal.get("opinion_text") or _strip_tags(proposal.get("message_text") or "")
    prompt = JUDGE_PROMPT.format(ideal=target["ideal_opinion"], concepts=concepts or "(none)", generated=generated)
    return await _judge_json(client, model, prompt)


async def _judge_attempt(client: Any, model: str, target: dict, proposal: dict) -> dict:
    generated = proposal.get("opinion_text") or _strip_tags(proposal.get("message_text") or "")
    prompt = ATTEMPT_PROMPT.format(ideal=target["ideal_opinion"], generated=generated)
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
