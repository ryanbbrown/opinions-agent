# Opinion Eval Status

This is the current handoff for eval optimization. Rewrite it as the state changes; do not append historical entries here. Use `eval/experiments.md` for the append-only experiment ledger.

## Current State

The goal is to improve `opinion_quality` without losing the evidence-classification guardrails. The current best remains `exp/critic-2`.

Current score to beat: **0.780** mean `opinion_quality` under `2026-07-05-plain-language`.

Critic-2 pool:

- `critic-2-r1-rs-2026-07-05`: 0.877
- `critic-2-r2-rs-2026-07-05`: 0.710
- `critic-2-r3-rs-2026-07-05`: 0.700
- `critic-2-r4`: 0.831

Pooled guardrails: attempted 0.959, recall 0.990, precision 0.521, brevity 0.695. Precision floor remains 0.50.

## Current Diagnosis

Critic-2 works because it gives the drafter an omission-auditor audience and clips bad drafts with local fidelity feedback. It is not a full editorial critic. It usually helps when the proposal already exists, cites the right evidence, and is missing a load-bearing concept that appears in that cited evidence.

The most common remaining misses are not all the same kind:

- Some are direct highlight-preservation misses: the source clearly says the missing piece, but the proposal generalizes it away.
- Some are routing/coverage misses: evidence is cited in a neighboring claim, but the target opinion is not proposed.
- W13-05 is the clearest update-routing case: new private-eval evidence should update an existing tests/specs/SQLite opinion, but the agent often folds it into a broader measurable-work moat claim.
- The recent current-opinions critic context experiment showed that giving the critic more context can convert update/coverage misses in a targeted screen, but it did not hold on the full run and may encourage shorter broader revisions.

Recent failed follow-ups:

- `critic-preserve`: stricter local critic rubric; targeted screen 0.620.
- `critic-opinions-context`: critic received current `OPINIONS.md`; targeted screen 0.780, full run 0.746.
- `critic-opinions-recheck`: critic context plus rechecking revised drafts; targeted screen 0.620.

## Next Directions

Explore these from `exp/critic-2`, unless a later experiment becomes the new current best.

### 1. Strong Editorial Critic

Try a critic that is fundamentally allowed to do more than local wording repair.

The critic should receive enough context to make an editorial judgment:

- the draft opinion and cited evidence
- current opinions
- all selected evidence for the document or week when feasible
- if the full document is too long, a bounded but meaningful amount of source context around all selected highlights from the document
- any existing context the critic already receives

The critic's job is to critique the proposal fully. It should be allowed to say the proposed opinion is bad, too broad, routed to the wrong existing opinion, missing a separate claim, should be reworked wholesale, should preserve an existing anchor, or should be split/combined if that is the right editorial feedback.

Do not over-constrain the critic to omission-only feedback in this path. Give it principles for what a good opinion should look like, enough source/current-opinion context, and let it decide what feedback matters. It can still give minor wording or fidelity feedback when that is all that is needed.

### 2. Better First-Draft Generation

Keep critic-2's local critic design, but improve the generation side so the first draft preserves highlighted claims better before the critic sees it.

The target failure mode is not hard reasoning. Many missed cases are gettable from the selected highlight or nearby source text. Try prompt changes that make the drafter enumerate the source's claim ingredients before drafting, preserve exact contrast/payoff/setup clauses, and avoid turning concrete evidence into a cleaner umbrella claim.

This path should focus on getting the right proposal identity and source ingredients into the first draft. The critic can then do local repair as designed.

### 3. Prompt Simplification

Lower priority, but worth trying if the first two paths do not produce useful movement.

Critic-2 may be carrying prompt bloat from prior experiments. Try simplifying or consolidating the prompt while holding performance within noise. A simpler prompt that keeps critic-2-level quality is valuable because it creates room for future additions and may reduce contradictory instruction pressure.

## Screening Plan

Use targeted screens first when the hypothesis is aimed at known misses. The current miss-heavy targeted set is:

`W04 W05 W06 W08 W13`

Comparable critic-2 subset baseline: opinion_quality **0.718**, attempted 0.935, recall 0.983, precision 0.568, brevity 0.758.

If a targeted screen clearly improves the miss pattern and guardrails hold, run the full eval:

`W04 W05 W06 W07 W08 W10 W11 W12 W13`

Only replicate/promote if the full run clears the ledger's score to beat and the replicate mean beats it by more than the noise band.

## Stop Rule

Do not stop after a few ordinary failures. Stop this phase only after **five consecutive experiments** fail to produce anything interesting: no promotion, no clear targeted-screen improvement, no useful mechanism insight, and no simplifying hold of current performance.

Current uninteresting-failure streak: **1**. `critic-opinions-context` was not promoted, but it was interesting because it produced a targeted-screen win and useful mechanism insight. `critic-opinions-recheck` was the next ordinary failed screen.
