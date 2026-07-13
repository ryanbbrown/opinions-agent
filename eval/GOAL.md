# Opinion Eval Optimization Goal

## Objective

Improve the opinion agent's Braintrust eval scores, primarily `opinion_quality`, without regressing evidence classification. Prompt and rule edits are the default levers, but critic-tool or harness changes are allowed when the hypothesis is explicitly about critic behavior, critic context, proposal routing, or coverage. Run experiments as isolated variants, compare them in Braintrust, log every result, and advance the current best only when a variant clearly and repeatably beats it.

Target: keep raising mean `opinion_quality` beyond the current best named in `eval/STATUS.md` and `eval/experiments.md`. The original 0.374 baseline has already been beaten; future changes still need step-function evidence, not marginal tweaks that only nudge the score inside the noise band. A change worth keeping should clear the current best clearly, not by a hair.

Read `eval/STATUS.md` and `eval/experiments.md` before every experiment so you start from the current plan and build on prior results instead of repeating dead ends.

## Metrics

The eval runs the initial proposal phase for each eval week and produces five scores (see `src/opinions_agent/evals/scorers.py`):

- `opinion_quality` — **primary.** Binary LLM judge: a generated opinion passes only if it carries all core concepts of the canonical one; extra content is fine. Averaged across weeks that have targets.
- `opinion_attempted` — diagnostic funnel layer beneath quality: a target counts as attempted when its matched proposal expresses the same central claim, even if concepts were dropped. Separates "wrong claims proposed" from "right claims written incompletely".
- `evidence_recall` — guardrail. Fraction of ground-truth-converted evidence the proposals cited.
- `evidence_precision` — guardrail. Fraction of cited in-week evidence that ground truth also converts.
- `opinion_brevity` — reference. Mean proposal length vs the week's mean golden-target length: 1.0 at or below the golden length, lower when longer (0.5 = twice as long). Not a gate, but the golden set averages ~34 words and bloat past that register is a cost — prefer variants that hold quality at higher brevity.

Weeks in scope: `W04 W05 W06 W07 W08 W10 W11 W12 W13`. W07 has no target opinions, so it only exercises precision — expect `opinion_quality` and `evidence_recall` to be null there.

Under the current coverage judge (`2026-07-10-coverage-concepts`), baseline (unmodified prompts) sits at 0.562 `opinion_quality`, 0.877 recall, 0.575 precision; the historical 0.374 figure was the old binary judge. The ledger header pins the exact **score to beat**; how a variant earns promotion is defined in Validity and promotion.

## Status and ledger files

- `eval/STATUS.md` is the living current-state handoff. It should be rewritten wholesale as time, experiments, current best, diagnosis, and next steps change. It is not an append-only log.
- `eval/experiments.md` is the append-only experiment ledger. Add one entry per experiment or diagnostic result worth preserving.
- Keep `eval/STATUS.md` short enough that a compacted or fresh session can read it quickly and know what to do next.

## Edit scope

- Preferred edit targets are `src/opinions_agent/prompts.py` and `RULES.md`.
- You may edit the agent/critic harness when the experiment hypothesis requires new critic behavior, critic context, proposal routing, or coverage machinery. Keep those changes as small as possible and test prompt construction/tool behavior directly.
- Swapping the drafter model in a worktree's `config.py` for a screen run is measurement, not an optimization lever. The promotion target model is `openai:gpt-5.5` at medium effort until Ryan explicitly decides a drafter switch.
- Never edit `src/opinions_agent/evals/` (scorers, runner, targets), `eval/opinion_targets.*`, or `OPINIONS.md` as an experiment lever. Changing the scorer or the targets games the metric instead of improving the agent. Temporary copied scorer/runner changes inside a disposable worktree are acceptable only for measurement reliability, such as bypassing a cached malformed judge response; record that caveat in the ledger.

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

The flip side: the levers with the best track record in the ledger are the ones that made an implicit expectation explicit (coverage-granularity, keep-the-list), and every failed leanness pass deleted structure the agent was actually using. Explicit and lean are not opposites. The goal is a prompt that states its contracts — what to propose, when a refusal is legitimate, when to read sources, how to write — clearly and exactly once, not a pile of accumulated patch bullets and not a sprawling over-detailed rule dump. Prefer restructuring a section around its contract over appending another bullet to it.

## Validity and promotion

Agent runs are stochastic: the same prompt scores differently run to run (measured spread ±3–6 points on `opinion_quality`, and individual targets flip pass/fail from randomness alone). A single run cannot confirm an improvement, and small deltas are noise. Screen cheaply, confirm only what looks real:

1. Screen the variant on the pinned screen subset (`eval/STATUS.md` pins the current subset weeks and per-model baselines), one run per screen model — currently gpt-5.5 medium and gpt-5.6-sol medium, named with distinct variants (`<exp>` and `<exp>-sol`) so Braintrust pooling keeps the models separate. Judge each run against its own model's subset baseline. Subset noise is coarse: one target flip in a 3-target week moves the subset mean 0.083, so treat ±0.05–0.10 as the band. If the gpt-5.5 subset run clearly regresses, stop — log it with a mechanism attribution and move on.
2. Subset screens are breakage tripwires, not validation — the old strong-week screen flattered a failing variant twice. If the screen looks like a real gain (or a clean hold for a simplification variant), run the full 9 weeks on gpt-5.5 medium. If that run is at or above the score to beat, run two more full replicates and promote when the replicate mean beats the score to beat by more than the noise band. Per-target flips are diagnosis, not a gate: use them to understand why a variant won or lost, and accept some target churn when the mean gain is real.
3. Consistency is a second objective: measure the spread across those runs. Prefer variants that are both higher and more stable, since clearer rules should produce more consistent behavior — a high-but-erratic variant is worse than a slightly lower, stable one.
4. Guardrails: recall moves loosely with quality (dropped proposals surface as unmatched targets, which already hurt `opinion_quality`), so it needs no separate gate — just note big drops. Precision is the exception: extra proposals raise recall and never hurt `opinion_quality`, so precision is the only defense against proposal spam. Do not promote a variant whose replicate-mean `evidence_precision` is below 0.50.
5. The sol screen never gates promotion by itself; it is the explicitness diagnostic. If a more capable same-cost model lags gpt-5.5 on the same prompt, the prompt is leaning on gpt-5.5-specific implicit behavior; a variant that closes sol's gap while holding gpt-5.5 is evidence the rewrite generalizes. If sol reaches parity on a winning variant, screen the cheaper 5.6 models (terra, luna) on it as a possible cost win.

A variant that meaningfully simplifies the prompts while holding all scores within noise is also promotable (see Keep the prompts lean).

## Reading results

- Each run prints its Braintrust experiment URL — open it for aggregate scores, per-row drill-down, and full traces.
- In the Braintrust experiments table, filter `metadata.scoring_version = '<current version>'` to see only score-comparable experiments, and group by `metadata.variant` for pooled per-variant scores. `eval rescore` brings an older experiment's stored outputs into the current scoring version (re-judged against the live targets, named `<variant>-r<N>-rs-<date>`).
- For the loop, `uv run python eval/inspect_experiment.py <run> [<run2> ...] [--vs <baseline-run> ...]` pools replicate runs of one variant — pooled means, per-run spread, per-target pass counts with the judge's missing-concept notes — and diffs them against pooled baseline runs. It reads verdicts already stored on the runs, so it never re-runs the judge.
- Braintrust's `estimated_cost` is accurate for runs made with thinharness ≥ 0.5.1 (bumped 2026-07-05). Experiments recorded before that ignore OpenAI's prompt caching and read ~1.8x high — a full 9-week run shown as ~$10 actually cost ~$5.
- When a run, a week, or one screen model does badly, do not stop at the aggregate: read the per-target judge notes (`inspect_experiment.py`), the Braintrust traces, and the worktree `.runs` artifacts, and attribute the failure to a mechanism — refusal (zero proposals for a week), routing (unmatched target), dropped concept, weakened paraphrase, or infra error (429 / timeout / null-week shrunken denominator; always check per-week judge coverage first). A failed screen only counts as progress if it leaves an attribution the next variant can act on.

## Experiment protocol

Each experiment is its own git worktree on its own `exp/<name>` branch. main is never committed to: the current best is a branch pointer, and experiments chain off it. Worktrees are disposable and live under the gitignored `.worktrees/`; the ledger and driver scripts run from the main checkout.

The current best starts as `main` (the committed eval harness with unmodified prompts) and advances to a winning `exp/` branch as promotions happen. `eval/experiments.md` names the current-best branch and pins the score to beat.

1. Read `eval/STATUS.md` for the current state and next-step plan, then read `eval/experiments.md` to avoid repeating tried variants.
2. Branch a worktree from the current-best branch and give it its keys (`.env` is gitignored, so it is not inherited):
   ```
   git worktree add .worktrees/<exp> -b exp/<exp> <current-best-branch>   # use main for the first round
   cp .env .worktrees/<exp>/.env
   ```
   Branching from the current-best branch inherits every earlier promoted change.
3. In the worktree, edit the minimal files needed for the hypothesis, respecting the anti-leakage rules. Prefer `prompts.py` and/or `RULES.md`; use agent/critic harness edits only when the experiment is about critic behavior, critic context, proposal routing, or coverage.
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

   Screens use the pinned subset weeks from `eval/STATUS.md` instead of the full list. For the sol screen of the same variant, prefix the run with `OPINION_AGENT_MODEL=openai:gpt-5.6-sol` and use `--variant <exp>-sol` (the drafter model and `OPINION_AGENT_REASONING_EFFORT` are env-overridable as of main's config change; they read the shell environment, not `.env`). Give concurrent runs distinct `RUNS_DIR` values — two processes sharing a run dir voided a pair of ablation runs.
7. Read the scores with `eval/inspect_experiment.py` (see Reading results), then apply the screen→replicate rule from Validity and promotion. Replication reruns reuse the same worktree with `--run 2`/`--run 3` (naming the experiments `<exp>-r2`/`-r3`).
8. Append a result entry to the main checkout's `eval/experiments.md`, never the worktree copy. Use the format that file documents.
9. Rewrite the main checkout's `eval/STATUS.md` when the current best, diagnosis, stop count, or next-step plan changes. Keep it current-state only; do not append history there.
10. If the variant is a confirmed winner, promote it by pointing **Current best** in the ledger at `exp/<exp>` and updating **Score to beat** to the variant's replicate mean; the next experiment branches from there. Nothing merges into main. Otherwise keep the branch and worktree for reference and deprioritize the variant — never delete non-winners, since a dead end still records what not to retry.
11. Continue until the stop criterion.

Always run a `baseline` experiment first (current prompts, unchanged) so every variant has something to beat.

## Stop criterion

Stop when the current phase plateaus: five consecutive experiments fail to produce anything interesting. "Interesting" means at least one of: promotion; a clear targeted-screen improvement worth full-run validation; a useful mechanism insight that changes the next plan; or a meaningful prompt/harness simplification that holds current performance within noise. Ordinary failed screens count toward the stop threshold.

When driving with `/goal`, phrase the condition against what `eval/STATUS.md` and the ledger show, for example:

```
/goal Per eval/STATUS.md and eval/experiments.md, continue until a variant is promoted or five consecutive experiments fail to produce promotion, targeted-screen improvement, useful mechanism insight, or simplification that holds performance.
```
