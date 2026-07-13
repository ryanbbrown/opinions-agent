# Opinion Eval Status

This is the current handoff for eval optimization. Rewrite it as the state changes; do not append historical entries here. Use `eval/experiments.md` for the append-only experiment ledger.

## Current State

The current best agent is **`exp/critic-2`**, drafter `openai:gpt-5.5` at **medium** effort (`config.py`). Score to beat: **0.865** pooled `opinion_quality` under scoring version **`2026-07-10-coverage-concepts`**, holding precision ≥ 0.50.

All five metrics (mean across weeks; `opinion_quality` pooled by week; `keep-the-list` shown as the prompt-only ceiling):

| metric | baseline-r1 | keep-the-list (pooled, 3 runs) | critic-2 (pooled, 4 runs) |
| --- | --- | --- | --- |
| opinion_quality | 0.562 | 0.825 | **0.865** |
| opinion_attempted | 0.944 | **0.979** | 0.959 |
| evidence_recall | 0.877 | 0.967 | **0.990** |
| evidence_precision | 0.575 | 0.532 | 0.521 |
| opinion_brevity | 0.939 | 0.781 | 0.705 |

Per-run critic-2 `opinion_quality`: {0.887, 0.846, 0.806, 0.919}. Canonical rescore experiments: `baseline-r1-rs-0710f`, `critic-2-r{1..4}-rs-0710f`, `keep-the-list-r{1..3}-rs-2026-07-10` (the plain `-rs-2026-07-10` critic-2/baseline experiments are stale; use the `-0710f` set).

Two questions were settled 2026-07-12 (full entries in the ledger):

- **Critic ablation (no-critic, n=2):** removing the critic costs −0.06 mean but drops the floor below any critic-2 run (0.765 vs 0.806) and loosens `opinion_attempted`; opinions get shorter. The critic is retained as a **floor/stability lever**, not a mean lever. The remaining headroom is in first-draft formation, not critique.
- **Drafter-model screen:** luna-high 0.681, terra-medium 0.388 (coverage collapse), opus-4.8-high 0.819 (0.936 on the 7 weeks it engaged, but refused all of W04 and wrote at ~2.8× golden length). Every non-gpt-5.5 failure is an **implicit-expectation failure** — coverage duty, eligibility threshold, length register — not a capability failure. gpt-5.5-medium stays the drafter.

## Current Round: structural explicitness rewrite (started 2026-07-12)

Working thesis: the prompt is an accretion of loop-era patches that works because gpt-5.5's natural behavior happens to match its implicit expectations — "redundancy is load-bearing" (lean-overhaul) is the signature of an under-structured prompt. Every promoted change in the ledger made an implicit behavior explicit; every failed leanness pass deleted structure the agent was using. The round's goal is to restate the prompt as explicit, well-organized contracts **without creating a sprawling, over-detailed mess** — see GOAL "Keep the prompts lean" for the explicit-≠-long discipline.

Behaviors currently implicit that candidate variants should make explicit (one experiment or small coherent group each; generalized wording only, per the anti-leakage rules):

1. **The proposal duty and per-cluster coverage expectation** — one proposal per argued highlight cluster; a selected week almost never legitimately yields zero. This is the terra/opus failure mode, and the ledger already proved the duty sentence is a single point of failure (lean-overhaul-2/2b).
2. **The eligibility threshold** — when a refusal is legitimate vs. the opus-style whole-week `proposals: []` shutout.
3. **A deterministic read-policy decision rule** — the current "visibly signals missing context" trigger list is a judgment call and is one of the two variance engines named in `eval/generation_determinism.md`.
4. **Update routing drafter-side** — search OPINIONS.md for the cluster's named anchors *before drafting* and propose a revision on a hit. Never tried on the drafter (only critic-side, which converted W13-05 inconsistently); opus converts W13-05, so it is prompt-addressable.
5. **The target register stated as fact** (golden mean ~34 words), not as compression pressure — pressure failed twice (compact-opinions, compact-default).

When a variant does badly — a week collapses, a model diverges, a screen regresses — **investigate the traces before designing the next variant** (per-target judge notes via `inspect_experiment.py`, Braintrust traces, worktree `.runs` DBs) and attribute the failure: refusal / routing / dropped concept / weakened paraphrase / infra error. GOAL "Reading results" makes this a protocol duty.

### Round base

Experiments this round branch from **`exp/explicit-base`** (worktree `.worktrees/explicit-base`): critic-2 prompts with the **critic step removed** (commit `90e23c0` on `exp/critic-2-no-critic`) plus the env-override config commit (`707d569`). Rationale: the critic rescues exactly the omissions the rewrite tries to prevent in the first draft, so it masks draft-formation deltas between variants — critic-less runs measure the rewrite directly, and cost less. The promotion bar stays critic-2's 0.865; a critic-less variant that clears it is a double win (simpler and better). If a winning rewrite lands close-but-below, re-adding the critic on top is an explicit composition experiment. What removal gives up: the floor (no-critic floor 0.765 vs critic-2's 0.806) and the audience effect (drafting for an auditor produces fuller drafts) — variants may need to state the completeness expectation explicitly to replace it.

### Screen models

Every variant screens on two drafters, named `<exp>` and `<exp>-sol`:

- **gpt-5.5 medium** — the promotion target. Promotion is unchanged: full 9-week replicates vs 0.865.
- **gpt-5.6-sol medium** — same cost, generally more capable; the explicitness diagnostic. If sol lags gpt-5.5 on the same prompt, the prompt is leaning on gpt-5.5-specific implicit behavior; a variant that closes sol's gap while holding gpt-5.5 is evidence the rewrite generalizes. Sol never gates promotion by itself.

No Anthropic drafters this round (if that changes: the `request_timeout=1800` fix lives uncommitted in the `critic-2-opus48` worktree and is mandatory). If a winning variant brings sol to parity, screen terra/luna (cheaper) on it as a possible cost win.

**First run of the round:** sol-medium baseline on the unmodified round base `exp/explicit-base` — subset first, full 9 weeks if the subset is sane — so variants have a sol reference. The drafter model/effort are env-overridable (`OPINION_AGENT_MODEL` / `OPINION_AGENT_REASONING_EFFORT`, shell env only — `.env` loads too late; already on the round base), so one worktree runs both screen models with no config edits.

## Screening Plan

- **Screen subset: `W04 W10 W12 W13`** (16/33 targets, ~48% full-run cost). Rationale and the full per-week per-model table are in the ledger's 2026-07-12 subset-baselines entry. In short: W04 = universal hard week + refusal mode + prompt-structure canary; W13 = routing (W13-05) + named-specific class; W10/W12 = cheap discriminators where weak models collapse, and W12 is the critic-floor tripwire.
- **Subset baselines** (`opinion_quality`, mean of week means):

  | model | subset baseline | full-run |
  | --- | --- | --- |
  | gpt-5.5 medium (critic-2, n=4) | **0.854** (runs 0.900 / 0.817 / 0.800 / 0.900) | 0.865 |
  | gpt-5.5 medium (no-critic round base, n=2) | **0.767** (runs 0.817 / 0.717; W12-03 fails both — the critic save) | 0.806 |
  | gpt-5.6-sol medium | not yet run | — |
  | opus-4.8 high (n=1, reference) | 0.75 | 0.819 |
  | luna high (n=1) | 0.55 | 0.681 |
  | terra medium (n=1) | 0.20 | 0.388 |

- Subset noise: one target flip in a 3-target week moves the mean 0.083; treat ±0.05–0.10 as the band. Subset screens are breakage tripwires, never validation — promotion always goes through full 9-week gpt-5.5 replicates.
- **Micro-screen `W04 W12`** (8 targets; gpt-5.5 pooled 0.85, runs 0.90/0.90/0.70/0.90) for rapid iteration only; graduate anything interesting to the 4-week subset.
- The old strong-week screen (`W06 W10 W11 W12`) is **deprecated** — it flattered the lean-overhaul family twice.
- Full eval: `W04 W05 W06 W07 W08 W10 W11 W12 W13` (W07 has no targets, precision only).

## The judge

`opinion_quality` is a **coverage-only** binary judge (v2). A matched proposal passes iff it expresses every required core concept for the target and takes the same stance as the canonical. The canonical is shown only as a stance reference; the judge never sees the source evidence (this killed the old evidence-bleed false negatives). Each target's checklist is `required_concepts` in `eval/opinion_targets.jsonl`, mirrored from `eval/opinion_targets.md`. Dilution/grafting is deliberately not its job — `evidence_precision` catches that deterministically. The judge is deterministic at temperature 0 (0 of 132 verdicts flipped on re-run), and it never sees the drafter model, so cross-model runs are judged identically; all run-to-run spread comes from the generations.

## Target file state

Every W04–W13 core-concept list is finalized — no `(open:)` flags remain. Cross-target rulings live in the "Judge rules" section at the top of `opinion_targets.md`. Not-core lists never reach the judge (only `required_concepts` do), so any leniency must be written into the concept wording. Simplified-canonical **candidates** are proposed inline in the `.md` (22 opinions) but not adopted — promoting them into the `.jsonl` `ideal_opinion` fields is a Ryan decision and would move stance-reference verdicts.

## Current Diagnosis

gpt-5.5 critic-2 hard weeks: W04 0.70, W08 0.75, W13 0.80; W11/W12 are at 1.00. Residual failure buckets:

- **Routing / coverage (no proposal produced):** W13-05 (0/4, never matched), W05-03 (2/4). Highest-leverage bucket; explicitness items 1–2 and 4 target it directly.
- **Concept-coverage fails (judge verdicts):** W04-05 (1/4), W08-02 (1/4), W06-01 (2/4) are the repeat offenders — the low-convergence, article-body-dependent tail per `eval/generation_determinism.md`; the read-policy rule (item 3) is the lever aimed at them.
- **Guardrails:** critic-2 precision 0.521 (floor 0.50) and brevity 0.705; a mean-raising change must not push precision below 0.50, and brevity should be watched, not optimized by pressure.

## Ops notes

- When a run posts a surprising aggregate, verify per-week `opinion_quality` coverage before comparing — an agent- or judge-side API failure leaves that week null and silently shrinks the mean's denominator. The tell: the reported mean disagrees with the mean implied by per-target verdicts.
- Cap concurrent full runs at 2 (three drew OpenAI 429s that killed week rows). Give concurrent processes distinct `RUNS_DIR` values — a shared run dir voided the first two no-critic ablation runs.
- `eval rescore --from-experiment <name>` re-judges stored generations without re-running the agent; use it after any concept or judge change. Pass `--experiment` to avoid auto-name collisions.

## Stop Rule

Do not stop after a few ordinary failures. Stop this phase only after **five consecutive experiments** fail to produce anything interesting: no promotion, no clear targeted-screen improvement, no useful mechanism insight, and no simplifying hold of current performance.

Current uninteresting-failure streak: **0** — reset by the 2026-07-12 round kickoff (critic ablation settled, model failure modes attributed, screen subset re-derived under the coverage judge).
