# Braintrust Experiment Links

Quick links for the experiment lineage. Scores are mean `opinion_quality`, grouped by `scoring_version`: `2026-07-04-binary-judge` = the original targets, `2026-07-05-plain-language` = the plain-language targets revised on 2026-07-05 (rescored from the same stored outputs, no agent re-runs; those experiments carry the `-rs-2026-07-05` suffix).

Project: [opinions-agent experiments](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments)

To see only the current cohort, filter the experiments table with `metadata.scoring_version = '2026-07-05-plain-language'` and group by `metadata.variant`; save it as a view.

## baseline — original starting point (unchanged prompts)

- [baseline-r1](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/baseline-r1) — 0.374 original
- [baseline-r1-rs-2026-07-05](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/baseline-r1-rs-2026-07-05) — 0.456

## keep-the-list — score-to-beat variant (RULES.md list structure)

- [keep-the-list-r1](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/keep-the-list-r1) — 0.487 original
- [keep-the-list-r2](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/keep-the-list-r2) — 0.698 original
- [keep-the-list-r3](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/keep-the-list-r3) — 0.660 original

Rescored:

- [keep-the-list-r1-rs-2026-07-05](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/keep-the-list-r1-rs-2026-07-05) — 0.548
- [keep-the-list-r2-rs-2026-07-05](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/keep-the-list-r2-rs-2026-07-05) — 0.754
- [keep-the-list-r3-rs-2026-07-05](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/keep-the-list-r3-rs-2026-07-05) — 0.727

## anchor-examples — concrete-anchors RULES.md variant (critic-2's base)

- [anchor-examples-r1](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/anchor-examples-r1) — 0.683 original
- [anchor-examples-r2](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/anchor-examples-r2) — 0.508 original
- [anchor-examples-r3](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/anchor-examples-r3) — 0.677 original

Rescored:

- [anchor-examples-r1-rs-2026-07-05](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/anchor-examples-r1-rs-2026-07-05) — 0.790
- [anchor-examples-r2-rs-2026-07-05](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/anchor-examples-r2-rs-2026-07-05) — 0.565
- [anchor-examples-r3-rs-2026-07-05](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/anchor-examples-r3-rs-2026-07-05) — 0.677

## compact-opinions — drop old-target compensations, compact plain opinions (worktree exp/compact-opinions)

- [compact-opinions-r1](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/compact-opinions-r1) — 0.531 (brevity 0.86; screen fail, precision 0.497)

## compact-default — compact closing only, full bullets kept (worktree exp/compact-default)

- [compact-default-r1](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/compact-default-r1) — 0.488 (brevity 0.835, attempted/recall 1.000; screen fail)

## slot-structure — generative stance/engine/payoff grammar (worktree exp/slot-structure)

- [slot-structure-r1](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/slot-structure-r1) — 0.600 (brevity 0.826; screen fail, precision 0.497)

## critic-2 — omission-only critic tool (worktree exp/critic-2)

- [critic-2-r1](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/critic-2-r1) — 0.790 original
- [critic-2-r2](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/critic-2-r2) — 0.598 original
- [critic-2-r3](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/critic-2-r3) — 0.571 original
- [critic-2-r4](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/critic-2-r4) — 0.831 (fresh native run, current scoring)

Rescored:

- [critic-2-r1-rs-2026-07-05](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/critic-2-r1-rs-2026-07-05) — 0.877
- [critic-2-r2-rs-2026-07-05](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/critic-2-r2-rs-2026-07-05) — 0.710
- [critic-2-r3-rs-2026-07-05](https://www.braintrust.dev/app/Ryan/p/opinions-agent/experiments/critic-2-r3-rs-2026-07-05) — 0.700
