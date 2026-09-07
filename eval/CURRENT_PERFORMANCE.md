# Current opinion-agent performance

This is the working baseline for the two-stage opinion workflow. The numbers are useful for prompt experiments, but they are not deployment guarantees.

## Reviewed test set

The checked-in test set has 35 expected opinions across W04–W13: 34 new opinions and one revision.

| Measure | Strict score | Review-adjusted score |
|---|---:|---:|
| At least one candidate independently covers each add target | 32/34 (94.1%) | 32/34 (94.1%) |
| Final opinion text covers the required concepts | 33/35 (94.3%) | 33/35 (94.3%) |
| Add or revise routing is correct | 32/35 (91.4%) | 34/35 (97.1%) |
| Both final opinion text and add-or-revise routing are correct | 30/35 (85.7%) | 32/35 (91.4%) |

The review adjustments accept two labeled-add cases where Ryan already considered the proposed revision reasonable: W08-04 and W13-05. W13-04 was also revised instead of added, but it remains unadjusted pending review.

The two substantive text misses omitted Figma's awkward position in W06-01 and the complete searchable-reference fallback in W13-01.

### Candidate routing and grouping

The full run produced 84 candidates. Every candidate was at most 81 words, below the validated 90-word maximum; mean length was 51.3 words and median length was 49.5 words.

Strict candidate grouping scored 92.86%. W05-02 split thin-harness architecture from the procedure for turning repeated work into a skill. W11-04 split network-building from the broader career-assets claim. The other scored weeks matched their target partitions exactly.

The semantic approval-unit score is 32/34. Both new W11 targets pass independently through candidates 004 and 011. W05-02 passes through candidate 001, and W11-04 passes through candidate 014. The two failures are the known W06-01 and W13-01 concept omissions. This score ignores extra candidates after one candidate passes; evidence precision measures their cited evidence separately.

### Evidence precision is not a current optimization target

Evidence recall was 100% and evidence precision was 48.5%. Ryan has deprioritized false candidate generation because rejecting an unsuitable proposal is cheap. Text fidelity, candidate grouping, and consolidation routing remain separately measurable.

The eval separates three questions:

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

- The concise prompt's full GPT run reached 32/34 strict concept quality while keeping all candidates below 90 words.
- Candidate grouping is strong under both the checked-in and discussed alternative partitions.
- Consolidator decisions remain useful after manual review, even where strict labels disagree.
- The remaining concept misses are isolated fidelity omissions rather than one shared prompt failure.
- Further prompt rules are not justified by the current results. Review W13-04 routing and the disputed partitions before another prompt experiment.
