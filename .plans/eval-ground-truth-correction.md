# Correct the opinion eval ground truth

## Goal

Make the executable eval use the reviewed 44-opinion state in `.html/opinion-evidence-timeline.html` without leaking later-week opinions into earlier seeds.

## Changes

1. Replace the pre-W04 seed in `OPINIONS.md` with 13 reviewed opinions and unique evidence assignments.
2. Change W04-01 from an add to an update of seed opinion 3.
3. Add a W08 update for the Reality’s Moat reader note so future evidence does not leak into the pre-W04 seed.
4. Add the missing teaching highlight to W10-03.
5. Remove examples from W13-02 and move that highlight to `not_converted`.
6. Change W13-05 from an update to a standalone AI-product eval opinion.
7. Keep `eval/opinion_targets.jsonl` and `eval/opinion_targets.md` equivalent.
8. Add regression tests for chronology, final count, sequential IDs, unique evidence ownership, and complete weekly partitions.
9. Bump both scoring versions and record the comparability boundary in eval documentation.

## Expected state

- Pre-W04 seed: 13 opinions and 30 unique evidence rows.
- W08 adds a third update because the approved Reality’s Moat reader note was created during W08, not before W04.
- Final W13 state: 44 opinions with sequential IDs.
- Assigned evidence: 93 unique rows with no evidence row assigned to more than one opinion.
- Weekly evidence partitions remain complete and disjoint.

## Verification

- `uv run pytest tests/test_evals.py tests/test_evals_v2.py tests/test_opinions_doc.py tests/test_validation.py`
- `uv run pytest`
- `uv run ruff check .`
- `uv run pyright`

A fresh V2 generation run is required before comparing performance with historical experiments.
