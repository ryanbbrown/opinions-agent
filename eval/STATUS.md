# Opinion Eval Status

## Current state

The executable ground truth was last corrected on 2026-09-02. The current scoring version is `2026-09-02-w12-standalone` in V1 and V2.

The corrected set has:

- 12 opinions in the pre-W04 seed
- 34 weekly targets: 33 adds and 1 update
- 45 opinions after applying all targets through W13
- 67 converted weekly evidence rows and 75 not-converted rows
- 93 unique evidence rows assigned across the final opinions
- no evidence row assigned to more than one opinion

W04-01 is the only update. It updates `opinion-000003` with the high-quality-intent evidence.

W08-05 is a standalone Reality’s Moat opinion. Its four earlier highlights use a checked-in eval availability override so all five evidence rows first appear together in W08. W12-01 is a standalone accountability and review-culture opinion; it does not update the seed comprehension-debt opinion. W13-05 is a standalone add about private eval sets and real user edge cases for AI products. It is separate from the seed opinion about private software test suites.

## Comparability boundary

All experiment scores from earlier scoring versions are historical only. The seed, canonical wording, evidence partitions, required concepts, and two operation labels changed. Do not rescore old outputs and compare them with the corrected set as if only the prompt changed.

The previous V2 routing candidate was `v2-routing-threshold-r1`, but its 28/33 conceptual, 28/33 operation, and 24/33 V2 results used the old ground truth. It is not the current baseline.

## Current measurement

[`eval/CURRENT_PERFORMANCE.md`](CURRENT_PERFORMANCE.md) records the current test-set and production-replay baseline, its manual review adjustments, and its limits.

V2 now stores frozen post-critic candidates and reports `candidate_quality` against add targets only. This measures extraction before consolidation. Final `opinion_quality`, `operation_accuracy`, and `opinion_quality_v2` continue to measure Telegram proposals after consolidation.

The W04/W06/W08 smoke scored 11/12 candidate targets = 0.917, in line with the earlier add-only full runs at 0.903 and 0.935. The same outputs scored 14/14 final conceptual quality but only 3/14 operation accuracy, proving the two stages can be diagnosed separately. A fourth smoke week, W11, failed on a provider read timeout and had no output.

Run all nine weeks before making a quality-promotion claim. A single smoke is enough only to verify the measurement path.

## Eval contract

- `OPINIONS.md` is the pre-W04 seed, not the final state.
- Weekly targets build the cumulative state in chronological order.
- One saved evidence row can have only one opinion home. Different highlights from the same article can support different opinions.
- Every selected weekly evidence row must be either converted or not converted, never both.
- V1 judges conceptual coverage. V2 also requires the labeled add or update operation.
- `candidate_quality` grades the frozen post-critic candidate snapshot against add targets only; W04-01 is excluded because extraction has not read the existing opinion needed to draft its revision.
- The primary aggregate is the target-weighted pass fraction, not the mean of week means shown as the Braintrust headline.

## Operations

All drafter and critic calls use `cproxy` on port 8113. Ports 8111 and 8112 belong to other work. Pass `OPINIONS_DATA_DIR` when running from a worktree because `.readwise` is local to the main checkout.
