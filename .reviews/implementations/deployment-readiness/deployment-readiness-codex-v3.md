# Verdict: changes requested

## Findings

1. High — Pending runs can bypass baseline capture and later delete artifacts.

   `start_materialized_opinion_run` commits the pending run before it captures the recovery baseline (`src/opinions_agent/workflow.py:216`). After a crash, the worker starts that run without checking or creating its baseline (`src/opinions_agent/worker.py:80`).

   Recovery and abandonment restore files unconditionally (`src/opinions_agent/worker.py:50`, `src/opinions_agent/workflow.py:1081`). Missing baseline files cause `_restore` to delete the current artifacts (`src/opinions_agent/recovery.py:137`).

   Make baseline completion a durable precondition for a reclaimable pending run. Make restoration fail safely when its baseline is incomplete.

2. Medium — Concurrent starts can return HTTP 500 instead of existing work.

   Lease acquisition commits before the first caller reserves its cycle (`src/opinions_agent/cycles.py:207`, `src/opinions_agent/cycles.py:285`). A concurrent caller can lose the lease before that reservation becomes visible.

   That caller finds no unfinished cycle and raises `RuntimeError` (`src/opinions_agent/cycles.py:257`). This violates the duplicate-safe contract.

   Wait for the reservation, retry the lookup, or reserve the cycle atomically with lease ownership.

3. Medium — Fractional balance limits accept partitions outside the required range.

   `_best_boundaries` rounds the lower limit down and upper limit up (`src/opinions_agent/cycles.py:152`). For 51 rows, it accepts 12 and 39 rows.

   The exact permitted range is 12.75 through 38.25. This prevents the required blocking-document split.

   Use exact comparisons, or use `ceil` for the lower bound and `floor` for the upper bound.

4. Medium — Snapshot failures never send the required Telegram notice.

   Cycle creation records `snapshot_failed` and raises (`src/opinions_agent/cycles.py:302`). No run exists, so the run-based notification function cannot report this failure.

   Startup reconciliation also discards the stopped cycles returned by `reconcile_starting_cycles` (`src/opinions_agent/worker.py:34`). Operators only see the cron failure.

   Add a cycle-level notification path for direct and startup-reconciled snapshot failures.

5. Medium — A repeated failure after retry does not send another notice.

   The notification key includes only the cycle, batch, and failure code (`src/opinions_agent/workflow.py:520`). A new retry run commonly fails with the same code.

   The prior interaction then suppresses the new failure notice. Include the run ID or a durable failure-attempt ID in the key.

## Missing or follow-up tests

- Simulate a crash after the pending-run commit but before baseline capture.
- Verify recovery and abandonment never delete files without a complete baseline.
- Run same-week and cross-week starts concurrently through separate PostgreSQL sessions.
- Add partition cases for document sizes `[12, 39]` and `[39, 12]`.
- Test snapshot failure notifications after direct failure and startup reconciliation.
- Test two retry attempts that fail with the same code.
- Exercise migration `0001` through `0002` against PostgreSQL.
- Run the full verification gate and the disposable Railway staging cycle from the plan.

No tests were executed because the review rules prohibit execution.

## Open questions

None.