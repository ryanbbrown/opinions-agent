# Current opinion-agent performance

This is the working baseline for the two-stage opinion workflow. The numbers are useful for prompt experiments, but they are not deployment guarantees.

## Reviewed test set

The checked-in test set has 34 expected opinions across W04–W13: 33 new opinions and one revision.

| Measure | Strict score | Review-adjusted score |
|---|---:|---:|
| Opinion text covers the required concepts | 30/34 (88.2%) | 31/34 (91.2%) |
| Add or revise routing is correct | 32/34 (94.1%) | 34/34 (100%) |
| Both opinion text and routing are correct | 28/34 (82.4%) | 31/34 (91.2%) |

The review adjustments are narrow:

- The quality judge misread “do not vibe-code products yourself” as “do not use products yourself.” The generated opinion did include real use as the trust signal, so W08-02 is a quality pass after review.
- W08-04 and W13-05 were labeled as new opinions, but their proposed revisions were also acceptable outcomes. They remain strict routing failures so the test labels do not move to fit one run.

The three substantive text misses omitted Figma's awkward position, Price's Law, and the warning against rip-and-replace adoption.

### Candidate routing and grouping

The writer produced 42 candidates that cited evidence assigned to the 34 expected opinions. The consolidator made 40/42 strictly labeled routing decisions correctly. The two other decisions were the acceptable W08-04 and W13-05 revisions.

All six cases with more than one candidate for one expected opinion split highlights from the same article. Four expected opinions became two candidates; two became three candidates. This produced the eight-candidate difference between 42 and 34. The target-level quality scorer selects one candidate for each expected opinion, so it does not penalize the extra overlapping candidate.

### Evidence precision remains the main test-set gap

The full generation run produced 93 candidates. Only 42 cited evidence assigned to expected opinions; 51 used only evidence labeled as not suitable for an opinion. The incomplete end-to-end run reported about 49% evidence precision. These extra candidates were excluded from the scorer-only text and routing results above.

The next quality work should therefore separate three questions:

1. Did the writer select evidence that should become an opinion?
2. Did the writer group related evidence into the right number of opinions?
3. Did each opinion preserve the evidence's important concepts?

## Historical production replay

The production smoke test reconstructed 29 candidates from seven previously approved production runs, then ran the current consolidator against the opinion state that existed before each run. Exact archives were unavailable, so the replay derived its input from accepted Git changes. It is a routing diagnostic, not a clean test of writer precision or text quality.

| Measure | Result |
|---|---:|
| Strict candidate route | 20/29 (69.0%) |
| New-opinion labels kept independent | 16/19 (84.2%) |
| Expected updates associated with the correct existing opinion | 5/9 (55.6%) |
| Exact attach-versus-revise operation among expected updates | 4/9 (44.4%) |

The strict score understates practical usefulness:

- The consolidator combined three candidates that production had added as new opinions. Ryan judged all three consolidation proposals acceptable. One also exposed an upstream generation problem: the generated candidate had lost the distinction that would have kept it separate.
- At least one missed historical revision was also acceptable as an independent opinion.
- Historical accepted operations are useful examples, but they were not created as a clean consolidation ground truth and can support more than one reasonable answer.

The production replay supports a limited conclusion: the consolidator now avoids clear over-consolidation in the reviewed cases, but update recall and attach-versus-revise choices need more examples before they can be measured confidently.

## Current read

- Conceptual writing quality is about 91% after review, which matches the earlier 11/12 smoke result.
- Consolidator decisions look useful after manual review, even where strict labels disagree.
- Evidence selection is the largest known problem.
- Same-article evidence grouping is a separate, smaller problem that the current target-level quality score can hide.
- A complete nine-week end-to-end run is still needed after the request-timeout fix. The current baseline combines frozen candidate artifacts, a consolidator-only replay, and a scorer-only pass because several final turns in the source run timed out.

## Next prompt experiment

Keep workflow instructions unchanged: evidence reads, candidate-file writes, critic calls, candidate validation, consolidation, Telegram proposals, and approval handling are process contracts.

Test a shorter opinion-selection and opinion-writing guide separately. Replace most abstract explanation with contrastive examples that show:

- a durable opinion versus an interesting fact or reference note;
- one argument supported by several highlights versus two independent arguments from one article;
- a complete opinion that keeps its mechanism, named term, bound, or correction versus a vague compression that drops one;
- a personal or familiar stance worth keeping versus empty consensus.

Keep a short rule above the examples: write one independently useful, personally endorsable belief per opinion, and preserve every detail that the belief depends on.

Treat this as a measured experiment, not an automatic cleanup. Earlier attempts to merge or shorten the fidelity rules reduced quality because the separate reminders were load-bearing. The example-based version should first run on a small diagnostic subset, then on the frozen-candidate quality path before an expensive end-to-end run.
