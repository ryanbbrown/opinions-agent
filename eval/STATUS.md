# Opinion Eval Status

This is the current handoff for eval optimization. Rewrite it as the state changes; do not append historical entries here. Use `eval/experiments.md` for the append-only experiment ledger.

## Current State

The goal is to improve `opinion_quality` without losing the evidence-classification guardrails. The current best agent remains **`exp/critic-2`**.

The judge was overhauled this round (see "The judge" below) and the per-target core-concept lists were finalized, so all numbers now live under scoring version **`2026-07-10-coverage-concepts`**. These are rescores of stored generations under the new judge, not fresh agent runs. `keep-the-list` is included as the **prompt-only ceiling** — the last variant promoted before the critic tool existed — so the table reads left-to-right as unmodified prompt → best prompt engineering → critic architecture.

All five metrics (mean across weeks; `opinion_quality` per-run is the pass-fraction pooled by week):

| metric | baseline-r1 | keep-the-list (pooled, 3 runs) | critic-2 (pooled, 4 runs) |
| --- | --- | --- | --- |
| opinion_quality | 0.562 | 0.825 | **0.865** |
| opinion_attempted | 0.944 | **0.979** | 0.959 |
| evidence_recall | 0.877 | 0.967 | **0.990** |
| evidence_precision | 0.575 | 0.532 | 0.521 |
| opinion_brevity | 0.939 | 0.781 | 0.705 |

Per-run `opinion_quality`: keep-the-list **{0.804, 0.871, 0.800}**, critic-2 **{0.887, 0.846, 0.806, 0.919}**. Score to beat for any new agent variant: **0.865** pooled quality, holding precision ≥ 0.50 and recall ≥ ~0.95.

Two things the table shows. (1) The critic buys **+0.040 quality over the prompt-only ceiling** (0.865 vs 0.825) — the same ~+0.04 gap that held under the old binary judge (0.653 vs 0.615), so the critic's edge is real and judge-independent, not an artifact of the new grader. (2) It pays for that with brevity (0.705 vs keep-the-list's 0.781 and baseline's 0.939 — longer opinions) and slightly lower precision (0.521 vs 0.532); keep-the-list actually posts the highest `opinion_attempted` (0.979). Any mean-raising change should watch precision and brevity, not just quality.

Canonical coverage-judge rescore experiments: `baseline-r1-rs-0710f`, `critic-2-r{1..4}-rs-0710f`, `keep-the-list-r{1..3}-rs-2026-07-10`. Note the plain `critic-2-*/baseline-*-rs-2026-07-10` experiments are **stale** — they predate the W05-02 Option A concept edit and score ~0.004 low; use the `-0710f` set.

## The judge

`opinion_quality` is now a **coverage-only** binary judge (v2). A matched proposal passes iff it expresses every required core concept for the target and takes the same stance as the canonical. The canonical is shown only as a stance reference; the judge never sees the source evidence (this killed the old evidence-bleed false negatives). Each target's checklist is `required_concepts` in `eval/opinion_targets.jsonl`, mirrored from `eval/opinion_targets.md`.

Deliberately **not** the quality judge's job: dilution / cross-source grafting. Two dilution formulations (half-off-list, different-subject) both over-fired on legitimate same-subject elaboration and cratered the pool; the judge can't separate a graft from rich elaboration without seeing provenance. The real signal — a proposal citing a not-converted source (e.g. W08-03 r4's public-learning half) — is caught deterministically by `evidence_precision` instead. Keep dilution out of the concept judge.

The judge is deterministic at temperature 0: a consistency re-run flipped 0 of 132 per-target verdicts. All run-to-run pool spread comes from the generations, not the grader.

## Target file state

Every W04–W13 core-concept list is finalized — no `(open:)` flags remain. Cross-target rulings live in the "Judge rules" section at the top of `opinion_targets.md`. A key mechanic: **Not-core lists never reach the judge** (only `required_concepts` do), so any leniency must be written into the concept wording, not a Not-core note.

Simplified-canonical **candidates** are proposed inline in the `.md` (italic "Simplified candidate" line under 22 of the opinions) but are not yet adopted — the `.jsonl` `ideal_opinion` fields still hold the original canonicals, so scores are unaffected until a candidate is promoted.

## Current Diagnosis

Baseline's low quality (0.562) is a concept-coverage problem: it drops required concepts or weakens them to vaguer umbrella claims. Prompt engineering alone (keep-the-list) recovers most of that gap to 0.825; critic-2's omission-auditor adds the last +0.040 to 0.865. Under this judge the two variants share the same floor (critic-2 worst run 0.806 vs keep-the-list 0.800), so the critic's lift here comes from raising the middle and upper runs, not from rescuing the worst one — the left-tail-clipping the ledger documented for the critic was a binary-judge-era effect, when keep-the-list bottomed near 0.55 and had a tail to clip.

critic-2's residual failures under the coverage judge (× of 4 runs) split into two kinds:

- **Routing / coverage (no proposal produced — `unmatched`, not a judge call):** W13-05 (4/4), W05-03 (2/4). These are the targets already annotated "failures were proposal routing/coverage, not judge verdicts." This is the highest-leverage remaining bucket and is agent-side, not judge-side.
- **Concept-coverage fails (judge verdict):** W04-05 (3/4), W08-02 (3/4), W06-01 (2/4) are the repeat offenders; W10-03, W08-04, W04-01, W04-02, W04-04 fail once each. W10-03's single fail is correct-by-design (the draft never used the required term "cognitive debt").

## Ops notes

- When a run posts a surprising aggregate, verify per-week `opinion_quality` coverage before comparing it — an agent- or judge-side API failure leaves that week's quality null and silently shrinks the mean's denominator. The tell: the reported mean disagrees with the mean implied by per-target verdicts.
- Cap concurrent full runs at 2. Three simultaneous runs drew OpenAI 429 quota errors that killed week rows mid-run.
- `eval rescore --from-experiment <name>` re-judges stored generations without re-running the agent and rebuilds `expected` from the live targets file — use it to re-score after a concept or judge change instead of paying for regeneration. Pass `--experiment` to name the output and avoid the date-truncated auto-name colliding.

## Next Directions

1. **Proposal routing (W13-05, W05-03).** The largest residual bucket is targets that get no matched proposal at all. This is agent-side and independent of the judge — worth a dedicated look at why these weeks' evidence doesn't convert into a proposal.
2. **Concept-coverage repeat offenders (W04-05, W08-02, W06-01).** These fail on judge verdicts across runs; check whether the draft weakens a load-bearing concept or the concept wording is mis-calibrated.
3. **Precision/brevity guardrails.** critic-2 sits at precision 0.521 and brevity 0.705; a mean-raising agent change must not push precision below 0.50.
4. **Adopt simplified canonicals.** If the italic candidates in `opinion_targets.md` are approved, promote them into the `.jsonl` `ideal_opinion` fields and rescore (canonical is the stance reference, so changes can move verdicts).

## Screening Plan

- Full eval: `W04 W05 W06 W07 W08 W10 W11 W12 W13` (W07 has no targets). Replicate/promote per `eval/GOAL.md`.
- Subset screens (miss-heavy `W04 W05 W06 W08 W13`; strong-week tripwire `W06 W10 W11 W12`) still work as cheap tripwires, but their critic-2 baselines were set under the old plain-language judge — re-establish them under `2026-07-10-coverage-concepts` before using them to judge a hold.

## Stop Rule

Do not stop after a few ordinary failures. Stop this phase only after **five consecutive experiments** fail to produce anything interesting: no promotion, no clear targeted-screen improvement, no useful mechanism insight, and no simplifying hold of current performance.

Current uninteresting-failure streak: **0** — reset by the judge overhaul this round (coverage-only judge + finalized concept lists + division of labor with `evidence_precision`), which is a structural improvement to how quality is measured.
