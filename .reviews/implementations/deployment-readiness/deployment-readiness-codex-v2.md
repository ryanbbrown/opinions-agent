# Verdict: changes requested

## Findings

1. **High — Failed edits are not restored before retry.** `_fail_run()` only updates database state (`src/opinions_agent/workflow.py:952`). `retry_stopped_cycle()` then queues the dirty batch (`src/opinions_agent/cycles.py:481`). The next run rejects dirty files during baseline capture. The worker silently retries forever (`src/opinions_agent/worker.py:107`). Archive and restore the failed run before allowing retry. Also clear any staged target files.

2. **High — A post-push error can rerun or strand a durable batch.** `_complete_done_run()` catches failures after push, database completion, and final Telegram delivery (`src/opinions_agent/workflow.py:352`, `src/opinions_agent/workflow.py:384`). It then stops the cycle through `_fail_run()`. Startup only reconciles `running_agent` runs (`src/opinions_agent/worker.py:27`). A pushed run marked failed can therefore run again. A Telegram failure after queuing the next batch can also stop the previous batch while `current_batch` points forward.

3. **High — An interrupted run can remain active forever after restart.** Startup skips a running run while its lease is unexpired (`src/opinions_agent/worker.py:32`). The worker later sees that active run and returns (`src/opinions_agent/worker.py:69`). Nothing reconciles it when the lease subsequently expires. Reconcile expired runs during worker polling, or invalidate leases owned by the previous process during startup.

4. **High — A crash can leave a cycle permanently in `starting`.** `_materialize_cycle()` commits batches and assignments (`src/opinions_agent/cycles.py:466`) before the caller commits `active` status (`src/opinions_agent/cycles.py:312`). A crash between these commits leaves durable bundles under a `starting` cycle. Neither startup nor the worker reconciles that state. Repeated starts then return the same unfinished cycle forever.

5. **High — Railway validation accepts an implicit SQLite database.** `get_settings()` supplies a SQLite default (`src/opinions_agent/config.py:85`). `validate_web_settings()` only checks that the resulting string is non-empty (`src/opinions_agent/config.py:120`). A missing Railway PostgreSQL reference therefore passes validation and stores operational state outside PostgreSQL. Require an explicit PostgreSQL `DATABASE_URL`.

6. **Medium — Remote reconciliation tests branch-tip equality, not ancestry.** `remote_contains_result()` only succeeds when the remote head equals the run SHA (`src/opinions_agent/recovery.py:62`). If another valid commit follows the run commit, recovery treats an already-pushed run as missing. It can then attempt a non-fast-forward push and block startup. Check whether the remote branch contains the SHA as an ancestor.

7. **Medium — The checkout can be ahead of the remote baseline.** `ensure_opinions_repo()` fetches and performs a fast-forward pull (`src/opinions_agent/repo_checkout.py:15`), but it never requires local `HEAD` to equal the remote branch. A clean local commit can become part of the next agent push. Compare both SHAs before baseline capture.

8. **Medium — The partitioner does not always choose the best balanced split.** The split offset ignores rows before the blocking document (`src/opinions_agent/cycles.py:105`). Document sizes `[5, 45]` split into `[30, 20]`, although `[25, 25]` is legal and better ranked. The existing test only checks the reversed `[45, 5]` order.

9. **Medium — Queued batch claims lack the required database lease.** The worker reads a queued batch and starts it without an atomic claim (`src/opinions_agent/worker.py:78`). Two workers can create separate runs for the same batch before either commits. The Railway replica setting reduces this risk but does not satisfy restart or duplicate-safety requirements.

## Missing or follow-up tests

The writer should run tests that cover:

- failure after edits, staging, commit, push, database completion, and final Telegram delivery;
- restart before lease expiry, followed by expiry without another restart;
- recovery of `starting` cycles with committed batches and assignments;
- retry with dirty and staged target files;
- a remote descendant of the recorded result SHA;
- a local branch ahead of its remote;
- missing, SQLite, and malformed Railway database URLs;
- reversed partition sizes `[5, 45]` and randomized partition ordering;
- concurrent worker claims and concurrent weekly starts;
- the full PostgreSQL Alembic migration and Railway schema checks.

No tests or builds were run, as required.

## Open questions

None.