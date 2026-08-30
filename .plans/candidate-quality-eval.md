# Candidate quality eval

## Goal

Measure post-critic, pre-consolidation opinion quality separately from final reconciliation quality in the same Braintrust eval run.

## Design

- Add the frozen `candidate-opinions.jsonl` rows to each eval case output.
- Add `candidate_quality`, which applies the existing conceptual judge to candidate text and only `add` targets.
- Do not operation-grade candidates. Update targets are excluded because extraction does not yet have the existing opinion context needed to draft the final revision.
- Keep final `opinion_quality`, `operation_accuracy`, and `opinion_quality_v2` unchanged.
- Store candidate rows in Braintrust output so later rescoring does not depend on local run directories.
- Report a target-weighted `candidate_quality` summary using only add targets.

## Validation

- Test candidate conversion, update-target exclusion, missing historical snapshots, and target-weighted summaries.
- Run the full test suite, Ruff, Pyright, and `git diff --check`.
- Run a real four-week smoke eval on W04, W06, W08, and W11. Confirm Braintrust reports candidate and final metrics from the same generations.
