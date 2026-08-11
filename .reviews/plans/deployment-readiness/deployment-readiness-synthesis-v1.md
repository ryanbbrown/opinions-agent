# Deployment readiness plan review synthesis

## Outcome

The v1 panel requested changes. The final plan incorporates the actionable findings without a second review round.

## Decisions added after review

- Replace timestamp-only evidence ownership with PostgreSQL evidence-version assignments.
- Require an explicit first-production evidence boundary.
- Persist completed no-evidence cycles.
- Reserve one global start lease before Reader sync or filesystem writes.
- Materialize every batch and critic context file when the cycle starts.
- Return from the start endpoint before any model call.
- Use a durable web worker for queued batches and automatic continuation.
- Reconcile queued, awaiting-user, interrupted, committed, and pushed run states at startup.
- Record git commit intent, base SHA, result SHA, and push phase.
- Archive partial edits and restore batch baselines before retry.
- Keep repository credentials out of remote URLs and redact operational failures.
- Send one Telegram notification when a cycle stops.
- Move workflow ownership from the volume cursor to PostgreSQL assignments and completed cycles.
- Keep sample and eval commands on the existing run-only path.
- Reuse `OpinionRun.batch` and remove the unused proposal batch field.
- Give the cron command narrow configuration and a no-restart policy.
- Add a ThinHarness 0.6.0 direct-API sample and compatibility screen.

## Chosen alternatives

- Use an evidence boundary and assignment ledger instead of copying the local corpus to Railway.
- Use a short-lived GitHub token through `GIT_ASKPASS` instead of embedding credentials in the repository URL.
- Use a queued web worker instead of holding the cron request through the first agent turn.
- Keep document groups whole when balanced, but split a blocking document when the result would be extremely uneven.
- Give split documents fixed cycle-wide critic context while keeping citations limited to the current batch.

## Review files

- `deployment-readiness-codex-v1.md`
- `deployment-readiness-claude-v1.md`
- `deployment-readiness-glm-5p2-v1.md`
- `deployment-readiness-manifest-v1.md`
