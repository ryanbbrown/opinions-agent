# Opinion Eval Optimization Goal

## Objective

Improve the opinion agent's prompts to raise its Braintrust eval scores, primarily `opinion_quality`, without regressing evidence classification. The only levers are `src/opinions_agent/prompts.py` and `RULES.md`. Run experiments as isolated variants, compare them in Braintrust, log every result, and advance the current best only when a variant clearly and repeatably beats it.

Target: lift mean `opinion_quality` from the 0.374 baseline to **0.70+**. That is a large gap, so pursue step-function changes — rethink how the prompt frames evidence triage and opinion writing — rather than marginal tweaks that only nudge the score inside the noise band. A change worth keeping should clear the current best clearly, not by a hair.

Read `eval/experiments.md` before every experiment so you build on prior results instead of repeating dead ends.

## Metrics

The eval runs the initial proposal phase for each eval week and produces five scores (see `src/opinions_agent/evals/scorers.py`):

- `opinion_quality` — **primary.** Binary LLM judge: a generated opinion passes only if it carries all core concepts of the canonical one; extra content is fine. Averaged across weeks that have targets.
- `opinion_attempted` — diagnostic funnel layer beneath quality: a target counts as attempted when its matched proposal expresses the same central claim, even if concepts were dropped. Separates "wrong claims proposed" from "right claims written incompletely".
- `evidence_recall` — guardrail. Fraction of ground-truth-converted evidence the proposals cited.
- `evidence_precision` — guardrail. Fraction of cited in-week evidence that ground truth also converts.
- `opinion_brevity` — reference. Mean proposal length vs the week's mean golden-target length: 1.0 at or below the golden length, lower when longer (0.5 = twice as long). Not a gate, but the golden set averages ~34 words and bloat past that register is a cost — prefer variants that hold quality at higher brevity.

Weeks in scope: `W04 W05 W06 W07 W08 W10 W11 W12 W13`. W07 has no target opinions, so it only exercises precision — expect `opinion_quality` and `evidence_recall` to be null there.

Baseline (unmodified prompts) sits at 0.374 `opinion_quality` (pooled over two samples), ~0.91 recall, ~0.58 precision. The ledger header pins the exact **score to beat**; how a variant earns promotion is defined in Validity and promotion.

## Edit scope

- You may edit **only** `src/opinions_agent/prompts.py` and `RULES.md`.
- Never edit `src/opinions_agent/evals/` (scorers, runner, targets), `eval/opinion_targets.*`, or `OPINIONS.md`. Changing the scorer or the targets games the metric instead of improving the agent.

## Anti-leakage rules

The test set is `eval/opinion_targets.jsonl` and its human-readable twin `eval/opinion_targets.md` (same content), plus the canonical opinions they seed into each week's `OPINIONS.md`. Improving the prompt by teaching it the answers is target leakage and is forbidden:

- Do not add any canonical opinion text, evidence snippet, source quote, or example phrasing that appears in the test set.
- Do not add a reworded or lightly-disguised version of a test case. The same underlying case with changed words still leaks; it only proves the prompt memorized that case.
- Improve with **generalized guidance** — principles about how to triage evidence, preserve concepts, split claims, and so on — or with **genuinely different examples** that exercise the same principle without being a test case in disguise.

If you are unsure whether an edit leaks, assume it does and generalize it.

## Keep the prompts lean

Simplicity, clarity, and conciseness are optimization targets, not afterthoughts. The failure mode of a blind optimization loop is a prompt that only ever grows: each experiment bolts on another instruction until `prompts.py` and `RULES.md` become a bloated, contradictory mess that reads worse and scores worse. Guard against it:

- Prefer edits that **remove, rewrite, or consolidate** over edits that only append. A change that lifts a score by sharpening or deleting existing text is worth more than one that adds a paragraph.
- Before adding an instruction, check whether `prompts.py` or `RULES.md` already covers it or contradicts it. Fix or replace the existing text instead of layering a second version on top.
- Treat length as a cost. A shorter or equal-length variant that holds its scores is better than a longer one, and is worth promoting on that basis alone.
- Watch for instructions that pull against each other. Contradictions confuse the agent and can lower scores more than a new instruction helps.

## Validity and promotion

Agent runs are stochastic: the same prompt scores differently run to run (measured spread ±3–6 points on `opinion_quality`, and individual targets flip pass/fail from randomness alone). A single run cannot confirm an improvement, and small deltas are noise. Screen cheaply, confirm only what looks real:

1. Run the variant once. If its `opinion_quality` is below the score to beat (pinned in the ledger header), stop — do not spend more runs. Log it and move on. A real step-function win clears the score to beat even on one noisy run; a variant that already dips below it is not worth chasing.
2. If the first run is at or above the score to beat, run it two more times. Promote when the mean of the runs beats the score to beat by more than the noise band. Per-target flips are diagnosis, not a gate: use them to understand why a variant won or lost, and accept some target churn when the mean gain is real.
3. Consistency is a second objective: measure the spread across those runs. Prefer variants that are both higher and more stable, since clearer rules should produce more consistent behavior — a high-but-erratic variant is worse than a slightly lower, stable one.
4. Guardrails: recall moves loosely with quality (dropped proposals surface as unmatched targets, which already hurt `opinion_quality`), so it needs no separate gate — just note big drops. Precision is the exception: extra proposals raise recall and never hurt `opinion_quality`, so precision is the only defense against proposal spam. Do not promote a variant whose replicate-mean `evidence_precision` is below 0.50.

A variant that meaningfully simplifies the prompts while holding all scores within noise is also promotable (see Keep the prompts lean).

## Reading results

- Each run prints its Braintrust experiment URL — open it for aggregate scores, per-row drill-down, and full traces.
- In the Braintrust experiments table, filter `metadata.scoring_version = '<current version>'` to see only score-comparable experiments, and group by `metadata.variant` for pooled per-variant scores. `eval rescore` brings an older experiment's stored outputs into the current scoring version (re-judged against the live targets, named `<variant>-r<N>-rs-<date>`).
- For the loop, `uv run python eval/inspect_experiment.py <run> [<run2> ...] [--vs <baseline-run> ...]` pools replicate runs of one variant — pooled means, per-run spread, per-target pass counts with the judge's missing-concept notes — and diffs them against pooled baseline runs. It reads verdicts already stored on the runs, so it never re-runs the judge.
- Braintrust's `estimated_cost` is accurate for runs made with thinharness ≥ 0.5.1 (bumped 2026-07-05). Experiments recorded before that ignore OpenAI's prompt caching and read ~1.8x high — a full 9-week run shown as ~$10 actually cost ~$5.

## Experiment protocol

Each experiment is its own git worktree on its own `exp/<name>` branch. main is never committed to: the current best is a branch pointer, and experiments chain off it. Worktrees are disposable and live under the gitignored `.worktrees/`; the ledger and driver scripts run from the main checkout.

The current best starts as `main` (the committed eval harness with unmodified prompts) and advances to a winning `exp/` branch as promotions happen. `eval/experiments.md` names the current-best branch and pins the score to beat.

1. Read `eval/experiments.md` and pick a hypothesis not already tried.
2. Branch a worktree from the current-best branch and give it its keys (`.env` is gitignored, so it is not inherited):
   ```
   git worktree add .worktrees/<exp> -b exp/<exp> <current-best-branch>   # use main for the first round
   cp .env .worktrees/<exp>/.env
   ```
   Branching from the current-best branch inherits every earlier promoted change.
3. In the worktree, edit `prompts.py` and/or `RULES.md` for the hypothesis, respecting the anti-leakage rules.
4. From the main checkout, run the leakage tripwire: `uv run python eval/check_leakage.py .worktrees/<exp>`. It flags word n-grams newly added to the lever files (relative to main) that also appear in the test set. Review every hit and generalize any real leak before proceeding. It only catches verbatim and near-verbatim leaks, so the anti-leakage rules above still apply in full.
5. Commit the change to the experiment's own branch — never main: `git -C .worktrees/<exp> commit -am "exp/<exp>: <hypothesis>"`. Committing is what lets a later experiment build on this one.
6. Run the eval from the worktree, pointing at the shared corpus (the gitignored `.readwise` lives only in the main checkout) and naming the variant:
   ```
   OPINIONS_DATA_DIR=/Users/ryanbrown/code/opinions-agent/.readwise \
   uv run --directory .worktrees/<exp> opinions-agent eval run \
     --weeks W04 W05 W06 W07 W08 W10 W11 W12 W13 \
     --variant <exp>
   ```
   The experiment is named `<exp>-r1` and stamped with `variant`, `run`, and `scoring_version` metadata (`scoring_version` is the runner's pinned constant marking which targets/judges graded the run — experiments are score-comparable only within the same value). Runs dir, sqlite DB, seeded `OPINIONS.md`, `RULES.md`, and targets all resolve inside the worktree.
7. Read the scores with `eval/inspect_experiment.py` (see Reading results), then apply the screen→replicate rule from Validity and promotion. Replication reruns reuse the same worktree with `--run 2`/`--run 3` (naming the experiments `<exp>-r2`/`-r3`).
8. Append a result entry to the main checkout's `eval/experiments.md`, never the worktree copy. Use the format that file documents.
9. If the variant is a confirmed winner, promote it by pointing **Current best** in the ledger at `exp/<exp>` and updating **Score to beat** to the variant's replicate mean; the next experiment branches from there. Nothing merges into main. Otherwise keep the branch and worktree for reference and deprioritize the variant — never delete non-winners, since a dead end still records what not to retry.
10. Continue until the stop criterion.

Always run a `baseline` experiment first (current prompts, unchanged) so every variant has something to beat.

## Stop criterion

Stop when either mean `opinion_quality` reaches the **0.70** target, or it plateaus — three consecutive experiments fail to beat the current best. When driving with `/goal`, phrase the condition against what the ledger shows, for example:

```
/goal Per eval/experiments.md, mean opinion_quality reached 0.70, or the last 3 experiments failed to beat the current best.
```
