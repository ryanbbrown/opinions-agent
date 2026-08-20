# Opinion Eval Status

This is the current handoff for eval optimization. Rewrite it as the state changes; do not append historical entries here. Use `eval/experiments.md` for the append-only experiment ledger.

## Current State

The current best lineage is the **structural-explicitness stack** (`exp/explicit-duty` → `exp/explicit-routing`), drafter **`openai:gpt-5.6-sol` at medium effort** — Ryan dropped gpt-5.5 mid-round (2026-07-12: "no need for gpt-5.5 anymore, let's just use sol"). Scoring version **`2026-07-10-coverage-concepts`**; all comparisons via `-rs-0710f` rescores. **Precision no longer gates** (Ryan, 2026-07-12: rejecting a bad proposal is cheap; the old ≥0.50 floor is retired as a promotion criterion — still reported). **The primary quality number is the target-weighted raw fraction (x/33 per full run)**, not the Braintrust headline (Ryan, 2026-07-21): the headline is a mean of week means — one case per week, so a 3-target week weighs like a 5-target week and single-run headlines drift from the raw fraction by up to ~0.015. Braintrust's SDK caps per-case scores at 1.0, so the headline itself cannot be made target-weighted with week-cases; instead `run_opinion_eval`/`rescore_opinion_eval` now print `opinion_quality (target-weighted): x/y` after every run and rescore, and that is the number to report and compare.

## Current Round: operation-gated quality v2 (started 2026-08-20)

The historical weekly eval remains available as v1 and still owns conceptual `opinion_quality`. Eval v2 copies that path and adds deterministic operation scoring. `opinion_quality_v2` requires both conceptual coverage and the labeled operation: add targets need add proposals; update targets need a revision that identifies the canonical base opinion. V2 uses its own Braintrust dataset and scoring version, and can rescore stored outputs without regenerating them.

The six clean production-method runs establish the stored-output baseline: **178/198 = 0.899 conceptual, 131/198 = 0.662 operation, and 115/198 = 0.581 V2**. The three cproxy prompt rounds were:

| variant | conceptual | operation | quality V2 | proposals (add/revise) |
| --- | --- | --- | --- | --- |
| **`v2-routing-threshold-r1`** | **28/33** | **28/33** | **24/33 = 0.727** | 66 (55/11) |
| `v2-revision-is-replacement-r1` | 24/33 | 28/33 | 23/33 = 0.697 | 62 (62/0) |
| `v2-routing-audit-r1` | 22/33 | 27/33 | 21/33 = 0.636 | 73 (66/7) |

Round 1 is the selected prompt state. It raises the revision threshold without suppressing revisions completely. Round 2 overcorrected to all adds, missed both labeled updates, and reduced recall and conceptual coverage. Round 3's extra audit did not help. Round 1 is a candidate, not a production promotion: it is one generation draw, and its conceptual score is below the six-run production baseline. The next useful step is unchanged round-1 replication, not more routing prose. Review ambiguous add/update labels before using V2 as a long-term optimizer, but do not change labels during a prompt comparison.

Full 9-week `opinion_quality`, the prior round's three live candidates (raw pass counts in parentheses; 33 targets/run):

| variant | per-run (x/33) | pooled raw | headline pooled | min | max |
| --- | --- | --- | --- | --- | --- |
| `exp/explicit-routing` (no critic, n=3) | 31 / 26 / 31 | 88/99 = 0.889 | 0.899 | 26/33 | 31/33 |
| `exp/explicit-critic` (cited-scope critic, n=3) | 29 / 30 / 28 | 87/99 = 0.879 | 0.885 | 28/33 | 30/33 |
| `exp/explicit-critic-docscope` (same-document critic, n=6) | 30 / 29 / 29 / 29 / 33 / 28 | **178/198 = 0.899** | 0.906 | 28/33 | **33/33** |

The r5–r7 replicates (Ryan-directed floor/peak checks) sharpened the picture in both directions. Peaks: not exclusive to the no-critic variant — docscope r6 posted the lineage's **only perfect full run (33/33)**, including both chronic W13 targets. Floor: r7 dipped to a new docscope low of 28/33 = 0.848 (misses: chronic W13-02, flippy W11-02, residual W11-04, plus W10-02 and W08-04 flips — W08-04 being the very class the docscope widening targets), so docscope's min now **ties** explicit-critic's rather than beating it, staying 2 targets above the no-critic 26/33 draw. Net at n=6: docscope leads on mean and peak, ties on floor, and the early "tightest spread" claim was partly a small-n artifact — single-run σ≈0.06 noise dominates everything except the traced fix: **W12-03 has passed all seven docscope runs** (subset + 6 fulls) after failing 3 of the prior 6 sol runs. Reference anchors: gpt-5.5 on explicit-routing full 0.950 (n=1, no re-runs by directive); terra on explicit-routing 0.894/0.806 pooled 0.850 (n=2, parked — terra omits evidence IDs and quotes document summaries as "Article — null", so recall/precision are meaningless and OPINIONS_SOURCES attribution would break; needs a copy-IDs-verbatim fix before more terra runs).

## Prior Round: brevity / scaffolding removal (started 2026-08-09)

Docscope proposals run **1.81x golden length**, so only 3/33 fit in a tweet against 30/33 of the goldens — which matters because Ryan wants to post these. The excess is **not** concept coverage (corr with required-concept count = -0.04); it is framing: a premise before the claim, a justification or restatement after it, and other opinions' claims reused as setup. But naive compression is not free: pooled over 6 docscope full runs, of the 12 targets that both passed and failed, the passing attempt was longer in **12/12** (mean +15.5 words).

Three RULES.md-only variants, all subset screens (16 targets) on sol medium, rescored from main:

| variant | quality | length | tweetable |
| --- | --- | --- | --- |
| docscope baseline | 14/16 | 1.84x | 0/16 |
| `exp/brevity-scope` (cut framing) | 28/32 = 0.875 (n=2) | 1.50x | 3–4/16 |
| **`exp/brevity-scope-2`** (+ procedures, + rank fidelity above cutting, + stay-long permission) | **32/32 = 1.000 (n=2)** | 1.63x | 1–4/16 |
| `exp/brevity-scope-3` (v2 minus stay-long) | 14/16 = 0.875 (n=1) | 1.50x | 5/16 |

**The subset oversold this and the full runs did not replicate it.** Two full 9-week sol runs of `exp/brevity-scope-2` came in at **28/33 and 28/33 → 56/66 = 0.848** (docscope: 178/198 = 0.899, n=6) at **1.68x** length (docscope full-run mean **1.82x**), tweet-fit 5/33 vs ~3/33 and 30/33 for the goldens. So the subset's quality gain disappeared and the length gain shrank from 11% to **7%**. Treat this as the reference case for why subset screens are tripwires, never validation: the effect did not merely get noisier at full size, it inverted.

**Round conclusion: no promotion.** The scaffolding diagnosis held — framing carries no required concept and the worst offenders did shrink — but framing is only ~7% of full-run length. The rest is fidelity-rule material (named anchors, full enumerations, de-compressed abstractions) that the rules deliberately require, and `lean-fidelity` already showed those rules are load-bearing (0.446 when consolidated). Recommended path: keep docscope, and derive tweet-length text from an already-approved opinion as a separate step instead of compressing the belief map to fit a character limit.

## Prior Round: structural explicitness rewrite (2026-07-12 to 2026-08-09)

Round history (variants 1–6, full entries in the ledger): the explicit duty contract (`explicit-duty`) plus drafter-side update routing (`explicit-routing`) lifted both screen models to 0.950 full-run quality without a critic — the round's central result. Variants 3–6 (deterministic reads, citation scope, selectivity, note-seeding) each held quality and taught a mechanism, but their purpose was the precision floor, which Ryan then retired; the stack tip for those fixes is `exp/explicit-notes` (quality 0.877 full on gpt-5.5), currently not the promotion path.

**Variant 7 (`exp/explicit-critic`, current tip under evaluation):** a thinharness **subagent** critic on top of explicit-routing — one call per proposal in parallel, sole tool a typed `get_evidence(evidence_ids)` fetch over the week's selected highlights; drafter passes draft text + cited IDs as free text; critic model inherits the drafter. Omission-only spine from critic-2 plus polarity and adjacent-move rules. Results above. Trace-audit findings that frame the next decision:

- **The critic works where citations are right:** four r1 REVISEs injected the judged target's missing load-bearing concept and the target passed (W04-01, W10-01, W10-03, W13-01); the unresolved-ID guardrail caught two fabricated citation sets. 32–34% REVISE rate — engaged, not rubber-stamping.
- **It cannot see citation-scope loss:** counterfactual replay of the 0.796 run's five misses through the critic saved only W04-04 — in the others the drafter dropped the concept *and* its citation together, so the cited-scope critic correctly READYs a coherent narrower claim.
- **The recurring miss (3× identical):** W12-03's "hand agents the routine work" half — present only in the parent document's **summary**, never in a selected highlight; drafter cites the one in-the-loop highlight, critic READYs. W11-04's "not pay/title/brand" list is the same shape (summary/body only).
- **Revise-type noise:** revised opinions inherit claims backed by prior-week sources the critic can't resolve; it flags the inherited half as unsupported. Needs revision-scoping in the critic prompt if kept.

**Variant 8 (`exp/explicit-critic-docscope`, production choice):** Ryan selected the same-document critic on 2026-08-11. The production implementation gives each critic the cited rows, the fixed same-document summary and evidence, and no unrelated documents. The pooled result is 178/198 = 0.899 across six full runs. No clean explicit-routing-on-proxy datapoint exists, so the backend confound remains recorded.

## Screening Plan

- Sol medium is the only screen model (single subset screen per variant); promotion = full 9-week sol replicates.
- **Screen subset: `W04 W10 W12 W13`** (16/33 targets, ~48% full-run cost); sol subset anchor **0.950** (explicit-routing and explicit-critic both hit it). Subset noise: one target flip in a 3-target week moves the mean 0.083; treat ±0.05–0.10 as the band. Subset screens are tripwires, never validation.
- **Micro-screen `W04 W12`** for rapid iteration only. The old strong-week screen (`W06 W10 W11 W12`) is deprecated.
- Full eval: `W04 W05 W06 W07 W08 W10 W11 W12 W13` (W07 has no targets, precision only).
- Sol's chronic misses on this lineage are **W13-02 / W13-04**; W11-02 has failed 2 of 3 critic runs. Everything else flips run-to-run (σ≈0.06 single-run from per-target flips at 33 targets).

## The judge

V1 `opinion_quality` is a **coverage-only** binary judge. A matched proposal passes iff it expresses every required core concept for the target and takes the same stance as the canonical. The canonical is shown only as a stance reference; the judge never sees the source evidence (this killed the old evidence-bleed false negatives). Each target's checklist is `required_concepts` in `eval/opinion_targets.jsonl`, mirrored from `eval/opinion_targets.md`. Dilution/grafting is deliberately not its job — `evidence_precision` catches that deterministically. The judge is deterministic at temperature 0 (0 of 132 verdicts flipped on re-run), and it never sees the drafter model, so cross-model runs are judged identically; all run-to-run spread comes from the generations.

## Target file state

Every W04–W13 core-concept list is finalized — no `(open:)` flags remain. Cross-target rulings live in the "Judge rules" section at the top of `opinion_targets.md`. Not-core lists never reach the judge (only `required_concepts` do), so any leniency must be written into the concept wording. Simplified-canonical **candidates** are proposed inline in the `.md` (22 opinions) but not adopted — promoting them into the `.jsonl` `ideal_opinion` fields is a Ryan decision and would move stance-reference verdicts.

## Ops notes

- **All drafter/critic LLM calls route through `cproxy` on port 8113** (ChatGPT-subscription OAuth, no API credits): run `cproxy serve --port 8113 --chains-max 500` as the persistent background process, then launch evals through `cproxy run` with the same options. The 500-chain capacity prevents concurrent eval cases from evicting resumable chains. Ports 8111/8112 are Ryan's other work — never touch. Judge calls are safe because scorers pin `base_url` to the Braintrust proxy. Worktrees have no local corpus — also pass `OPINIONS_DATA_DIR=<main>/.readwise`.
- ChatGPT-backend upstream 5xx/transport errors are a transient run-killer: `grep -c "provider request failed"` in the run log before rescoring; a run with killed weeks cannot be rescored (rows missing output) — void it and rerun.
- When a run posts a surprising aggregate, verify per-week `opinion_quality` coverage before comparing — the reported mean must match the verdict-implied mean from per-target verdicts.
- Cap concurrent full runs at 2; give concurrent runs distinct `RUNS_DIR` values.
- `rescore_opinion_eval(settings, source_experiment=..., experiment_name='<name>-rs-0710f')` from main re-judges stored generations under the current judge.
- thinharness pinned at **v0.6.0**; the `subagent` gateway must be listed in `builtin_tools`.

## Stop Rule

Do not stop after a few ordinary failures. Stop this phase only after **five consecutive experiments** fail to produce anything interesting: no promotion, no clear targeted-screen improvement, no useful mechanism insight, and no simplifying hold of current performance.

Current uninteresting-failure streak: **0** — variant 7 raised the floor and produced the citation-scope attribution plus the variant-8 mechanism.
