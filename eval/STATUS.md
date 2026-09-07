# Opinion Eval Status

## Current state

The executable ground truth was last corrected on 2026-09-07. V2 uses scoring version `2026-09-07-w11-workflow-split`; V1 retains its existing scoring version.

The corrected set has:

- 12 opinions in the pre-W04 seed
- 35 weekly targets: 34 adds and 1 update
- 46 opinions after applying all targets through W13
- 68 converted weekly evidence rows and 74 not-converted rows
- 94 unique evidence rows assigned across the final opinions
- no evidence row assigned to more than one opinion

W04-01 is the only update. It updates `opinion-000003` with the high-quality-intent evidence.

W08-05 is a standalone Reality’s Moat opinion. Its four earlier highlights use a checked-in eval availability override so all five evidence rows first appear together in W08. W11-02 covers workflow mapping, ROI, tribal knowledge, and intermediate evaluation checkpoints; W11-06 separately covers preserving existing systems during AI adoption. The data-layer highlight remains not converted. W12-01 is a standalone accountability and review-culture opinion; it does not update the seed comprehension-debt opinion. W13-05 is a standalone add about private eval sets and real user edge cases for AI products. It is separate from the seed opinion about private software test suites.

## Comparability boundary

All experiment scores from earlier scoring versions are historical only. The seed, canonical wording, evidence partitions, required concepts, and two operation labels changed. Do not rescore old outputs and compare them with the corrected set as if only the prompt changed.

The previous V2 routing candidate was `v2-routing-threshold-r1`, but its 28/33 conceptual, 28/33 operation, and 24/33 V2 results used the old ground truth. It is not the current baseline.

## Current measurement

[`eval/CURRENT_PERFORMANCE.md`](CURRENT_PERFORMANCE.md) records the current test-set and production-replay baseline, its manual review adjustments, and its limits.

V2 stores frozen post-critic candidates and reports `candidate_quality` against add targets before consolidation. Conceptual quality is many-to-many: one evidence-linked candidate can cover several targets, and several candidates can collectively cover one target. `candidate_independent_quality` separately asks whether at least one candidate covers the complete add target by itself. Update targets remain excluded because their canonical text includes the existing opinion that extraction has not read. `candidate_grouping` compares the candidate evidence partition with the target partition. Final `opinion_quality`, `operation_accuracy`, and `opinion_quality_v2` measure Telegram proposals after consolidation without using grouping as a proxy for concept coverage.

The W04/W06/W08 smoke scored 11/12 candidate targets = 0.917, in line with the earlier add-only full runs at 0.903 and 0.935. The same outputs scored 14/14 final conceptual quality but only 3/14 operation accuracy, proving the two stages can be diagnosed separately. A fourth smoke week, W11, failed on a provider read timeout and had no output.

A five-week prompt screen added a validated 90-word candidate maximum and tested three concise grouping and fidelity variants on GPT-5.6 Sol and Claude Opus 5. The selected first variant kept the best cross-model balance. After the W11 ground-truth correction, its full nine-week GPT validation scored collective and independent candidate quality 32/34, final concept quality 33/35, operation accuracy 32/35, operation-gated quality 30/35, and candidate grouping 92.86%. Across 84 candidates, mean length was 51.3 words and the maximum was 81. See `eval/experiments.md` for the strict and reviewed-label comparison.

## Eval contract

- `OPINIONS.md` is the pre-W04 seed, not the final state.
- Weekly targets build the cumulative state in chronological order.
- One saved evidence row can have only one opinion home. Different highlights from the same article can support different opinions.
- Every selected weekly evidence row must be either converted or not converted, never both.
- V1 judges conceptual coverage. V2 also requires the labeled add or update operation.
- Conceptual scores aggregate all evidence-linked opinions for each target and can reuse one opinion across targets. They do not penalize splitting or merging.
- `candidate_quality` grades the frozen post-critic candidate set collectively against add targets; update targets require existing-opinion context that extraction does not read.
- `candidate_independent_quality` requires at least one candidate to cover an add target by itself; extra candidates do not make the target fail.
- `candidate_grouping` reports whether converted evidence was over-merged or under-merged before consolidation.
- The primary aggregate is the target-weighted pass fraction, not the mean of week means shown as the Braintrust headline.

## Operations

All drafter and critic calls use `cproxy` on port 8113. Ports 8111 and 8112 belong to other work. Pass `OPINIONS_DATA_DIR` when running from a worktree because `.readwise` is local to the main checkout.
