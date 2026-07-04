"""Braintrust scorers: deterministic evidence classification plus the opinion-quality LLM judge."""

from __future__ import annotations

import html
import json
import re
from typing import Any

from braintrust import Score

from opinions_agent.config import Settings

BRAINTRUST_PROXY_URL = "https://api.braintrust.dev/v1/proxy"
JUDGE_MODEL = "claude-sonnet-4-5"

JUDGE_PROMPT = """\
You are grading whether a generated opinion contains all the core concepts of a canonical opinion that a human \
already verified against the same source evidence.

Canonical opinion:
{ideal}

Source evidence behind the canonical opinion:
{evidence}

Generated opinion:
{generated}

The check is binary: does the generated opinion include all the core details and concepts of the canonical \
opinion?
- Core details and concepts are the central claim plus the named terms, mechanisms, examples, numbers, and \
caveats that carry the canonical opinion's meaning.
- Small wording differences are fine.
- Extra related content beyond the canonical opinion is fine and must not cause a failure.
- If any core detail or concept is missing, materially mis-stated, or replaced with a vaguer umbrella claim, \
the generated opinion fails.

Answer with JSON only, no other text:
{{"pass": true | false, "missing": "<core concepts missing or mis-stated, empty if none>", \
"rationale": "<one or two sentences>"}}
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


def make_opinion_quality_scorer(settings: Settings, *, model: str = JUDGE_MODEL, client: Any = None):
    """LLM-as-judge scorer comparing each generated opinion to its matched canonical target."""
    if client is None:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=BRAINTRUST_PROXY_URL, api_key=settings.braintrust_api_key)

    async def opinion_quality(input: Any, output: Any, expected: Any) -> Score:
        targets = expected["targets"]
        if not targets:
            return Score(name="opinion_quality", score=None, metadata={"reason": "no opinion targets this week"})
        proposals = output.get("proposals", [])
        matches = await match_proposals_to_targets(proposals, targets, client=client, model=model)
        per_target = []
        scores = []
        for target in targets:
            proposal = matches.get(target["target_id"])
            if proposal is None:
                per_target.append({"target_id": target["target_id"], "verdict": "unmatched", "score": 0.0})
                scores.append(0.0)
                continue
            verdict = await _judge_pair(client, model, target, proposal)
            score = 1.0 if verdict.get("pass") is True else 0.0
            per_target.append(
                {
                    "target_id": target["target_id"],
                    "proposal_id": proposal.get("proposal_id"),
                    "generated": proposal.get("opinion_text"),
                    "verdict": "pass" if score == 1.0 else "fail",
                    "missing": verdict.get("missing"),
                    "rationale": verdict.get("rationale"),
                    "score": score,
                }
            )
            scores.append(score)
        return Score(
            name="opinion_quality",
            score=sum(scores) / len(scores),
            metadata={"targets": per_target, "unmatched_proposals": _unmatched_proposal_ids(proposals, matches)},
        )

    return opinion_quality


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
    evidence = "\n".join(f"- {quote['title']}: \"{quote['quote']}\"" for quote in target.get("source_quotes", []))
    generated = proposal.get("opinion_text") or _strip_tags(proposal.get("message_text") or "")
    prompt = JUDGE_PROMPT.format(ideal=target["ideal_opinion"], evidence=evidence or "(none)", generated=generated)
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
