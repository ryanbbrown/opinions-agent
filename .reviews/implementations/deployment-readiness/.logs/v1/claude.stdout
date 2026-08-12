## Verdict: changes requested

**Note on scope:** `git diff d91859e 1db1b68` is empty. The snapshot commit `1db1b68` contains no changes against the stated base, which is itself the last feature commit. I reviewed the real feature range `a023b62..1db1b68` (`cb14786` plan through `d91859e`), which matches the plan file. Confirm the intended base before the next round.

---

## Findings

### 1. Retry re-runs a batch whose commit is already pushed (high)

`src/opinions_agent/cycles.py:481` `retry_stopped_cycle` never inspects the failed run's git phase. `workflow.py:952` `_fail_run` calls `_stop_cycle` unconditionally, including for failures that happen *after* the push in `_complete_done_run` (`workflow.py:349-360`: `update_opinion_id_high_water`, `decision_log_hash`, `_complete_cycle_batch` all run after `git_phase = pushed`).

Failure scenario: the push succeeds, then `_complete_cycle_batch` raises because the batch row is missing or the volume write fails. The run becomes `failed` with `git_phase = "pushed"` and the cycle becomes `stopped`. `reconcile_startup` (`worker.py:27`) only scans `running_agent`, so it never sees this run. The operator runs `retry-cycle`, the batch returns to `queued`, and the agent re-processes evidence that is already committed and pushed — duplicate opinions on top of the pushed commit.

This violates plan requirements "Never rerun a batch whose pushed commit can be reconciled" and "Failure before database completion reconciles the remote commit". Suggested fix: in `retry_stopped_cycle`, look up `batch.latest_run_id`; if its `git_phase` is `committed`/`pushed` or `remote_contains_result` is true, call `complete_reconciled_run` instead of queueing. Also widen `reconcile_startup` to failed runs holding a `git_result_sha`.

### 2. A failed cycle run leaves the checkout dirty, so retry can never start (high)

`_fail_run` (`workflow.py:952`) does not call `archive_and_restore_run`. Only `abandon_run` and `reconcile_startup` restore artifacts. But `FAILED` is terminal (`workflow.py:69`), so `abandon-run` cannot run afterwards either.

Failure scenario: the agent edits `OPINIONS.md`, then validation raises inside `_complete_done_run`. `_fail_run` records the failure and leaves the edits in the working tree. The operator runs `retry-cycle`. The worker picks the batch, `start_materialized_opinion_run` calls `capture_run_baseline` (`workflow.py:196`), and `assert_targets_clean` raises "target files are already dirty". That call sits **outside** the `try` block, so no `_fail_run` and no Telegram notice fire. `worker_loop` (`worker.py:107-118`) swallows the exception, the batch stays `queued`, and the loop retries every two seconds forever while the cycle reports `active`. The weekly cron then returns a successful 200 no-op while nothing progresses.

Plan requirements "Restore the three writable artifacts to their recorded baseline before retry" and "Save a patch and copies of changed writable artifacts" are only met on the startup path. Suggested fix: archive and restore in `_fail_run` for cycle runs, and make `worker_loop` stop the cycle plus notify after a repeated claim failure instead of spinning.

### 3. `partition_evidence` enumerates partitions exhaustively (medium-high)

`cycles.py:133-169` `_best_boundaries` is a recursive search that collects **every** legal partition, then takes the minimum. Its only pruning is the per-batch row cap and the segment-count bound; it has no feasibility bound on remaining rows versus remaining batches.

Failure scenario: the first production cycle after `OPINIONS_INITIAL_EVIDENCE_AFTER` produces 500 evidence rows across many single-row documents. `batch_count` is 10, `target` is 50, so `low=25` and `high=50`. Each level branches about 26 ways, and infeasible prefixes are only detected at depth 10. The search explores on the order of 26^9 states and the cycle start hangs, holding the 15-minute start lease while cron waits on its 10-minute timeout.

The plan specified "a dynamic-programming search, which compares legal boundaries without brute-force enumeration". Suggested fix: memoize on `(start, batches_left)` keeping the best rank per state, or add the bound `remaining_rows <= batches_left * MAX_EVIDENCE_ROWS`. Please add the plan's required randomized-size test with a large row count and assert a wall-clock bound.

### 4. A crashed `starting` cycle blocks every later weekly start with no recovery path (medium-high)

`_unfinished_cycle` (`cycles.py:339`) includes `starting`, and `_existing_result` (`cycles.py:349`) maps anything not `stopped` to `"existing"`, which the endpoint returns as HTTP 200. Nothing reconciles cycles at startup — `reconcile_startup` only handles runs, and `init-runtime` (`cli.py:120`) queries cycles solely to decide whether to refresh the checkout.

Failure scenario: the process is killed by a redeploy during `sync_corpus` or `_materialize_cycle`. The `except` handler in `start_opinion_cycle` never runs, so the cycle stays `starting` with zero batches. The start lease expires after 15 minutes, but every later weekly start returns 200 "existing" and creates nothing. `retry-cycle` cannot help: `retry_stopped_snapshot` requires `failure_code == "snapshot_failed"` and `retry_stopped_cycle` requires status `stopped`. Recovery needs a manual database edit.

Suggested fix: at startup, mark any `starting` cycle with no batches as `stopped` with `failure_code = "snapshot_failed"`, so the existing snapshot-retry path applies and cron reports 409.

### 5. Leases are only checked at startup, so a short-lived crash leaves a stuck run (medium)

`worker.py:32` skips any `running_agent` run whose lease has not expired. Nothing re-examines leases after startup.

Failure scenario: the service restarts five minutes into a model turn. The lease is valid for another ten minutes, so `reconcile_startup` skips the run. The run stays `running_agent` forever, `process_queued_once` sees an active run and idles, and no notification is sent. A fresh process cannot own a lease it did not issue, so treat every `running_agent` run at startup as interrupted, or re-check expiry inside `worker_loop`.

### 6. Production validation is skipped when the volume variable is missing (medium)

`app.py:32` and `cli.py:117` both gate `validate_web_settings` on `settings.volume_mount_path is not None`. `config.py:82` also derives `environment` from the same variable. If `RAILWAY_VOLUME_MOUNT_PATH` is absent — a detached or misconfigured volume — the service skips **all** validation, resolves `environment` to `dev`, and serves with local defaults including `TEST_OPINIONS.md` and no start secret requirement. This is the exact case the plan's "Unsafe production configuration prevents startup" criterion targets. Gate on `OPINIONS_ENVIRONMENT in {"staging", "prod"}` instead, and let `validate_web_settings` report the missing mount path itself (it already checks that key).

### 7. `railway.toml` does not pin one replica (medium)

`railway.toml` sets `overlapSeconds = 0` and `drainingSeconds = 30`, but omits `numReplicas = 1`. The plan requires "Use one replica" and the whole design assumes a single in-process worker: the worker claims queued batches with no database lease (`worker.py:78-96`), contrary to "Use a database lease when the worker claims a queued run". Two replicas would start two runs for the same batch. Add `numReplicas = 1` explicitly. Please also confirm `overlapSeconds` and `drainingSeconds` against Railway's published schema — the plan's phase-5 check ("Validate both Railway files against Railway's published JSON schema") is not evidenced in the diff.

### 8. No pre-run check that the checkout matches the last successful remote commit (medium)

The plan's batch-baseline rule requires the checkout to match the last successful remote commit before each run. `capture_run_baseline` (`recovery.py:20`) only asserts the target files are clean and records local `HEAD`. Separately, `_complete_done_run` now passes `push=False` to `commit_and_push_opinions_files`, which also skips the pre-commit `fetch` (`git_ops.py:85`). A checkout left behind the remote — for example after a manual edit to the opinions repository — is only detected when the push is rejected, after the agent has already spent a full turn. Add an `ls-remote` comparison in `capture_run_baseline`.

### 9. `start_cycle_from_corpus` duplicates the production start path (low-medium)

`cycles.py:212-265` repeats about 50 lines of `start_opinion_cycle` and is used only by `tests/test_cycles.py`. It also omits the `except` handler that marks the cycle `stopped`, so the three tests that use it exercise a code path that differs from production in exactly the failure behavior under review. Project instructions call for the simplest implementation that meets current requirements. Delete it and have the tests call `start_opinion_cycle` with a no-op `sync_corpus`.

### 10. Migration and Alembic path details (low)

- `alembic/versions/0002_deployment_cycles.py:80` uses `next(...)` with no default. If the inspector reports the constraint differently, the migration fails with a bare `StopIteration` inside the deploy start command, which loops the deployment. Add a default and a clear error.
- `cli.py:349` resolves `alembic.ini` from the project root, but `alembic.ini` still holds `script_location = alembic` and `prepend_sys_path = .`, both relative to the working directory. The plan's "Resolve Alembic configuration from the project root instead of the caller's current directory" is only half met. Use `%(here)s/alembic`.

### 11. `complete_reconciled_run` handles non-cycle runs incompletely (low)

`workflow.py:204-217` calls `_complete_cycle_batch`, which returns immediately when `run.cycle_id` is empty, and then marks the run completed. A reconciled non-cycle run never gets `_finalize_run_artifacts`, so its bundle stays in `active/`. Recovery also sends no Telegram message after it completes a pushed batch and queues the next one, so the operator sees a silent resume.

---

## Missing or follow-up tests

The plan's "Required tests" list is only partly covered. These are named in the plan and absent from the diff:

- **Crash and recovery:** restart reclaims a queued run; restart preserves an awaiting-user run; expired running lease stops the cycle and permits retry; failure after agent edits archives and restores writable files *through a failing run* (the current test calls `archive_and_restore_run` directly); failure after push does not rerun the batch; retry never repeats a completed batch; startup does not pull over an active dirty checkout. `reconcile_startup` has no test at all.
- **Partition:** randomized document sizes satisfying both caps and the minimal feasible batch count, including a large-input case that would expose finding 3.
- **Assignment:** late new evidence with an old source timestamp entering a later cycle; a material content change creating a new eligible fingerprint end-to-end; later corpus mutation not changing a materialized batch; split-document critic context staying fixed and cycle-wide.
- **Cycle:** a no-evidence start creating one completed zero-batch cycle; cross-week concurrent starts creating one active cycle.
- **HTTP and configuration:** start endpoint 200 and 409 results (only 401 and 202 are covered); cron exit codes for 401, 409, and network failure (only 202 is covered); `/healthz` failing before reconciliation and on a missing volume path; production-only validation rules (only staging is asserted).

Commands the writer should run: `uv lock --check`, `uv run pytest`, `uv run ruff check .`, `uv run pyright`, and the `OPINIONS_RUN_REAL_E2E=1` optional end-to-end test. I did not run them.

---

## Open questions

1. Which commit range is authoritative for this review? The supplied base equals the feature tip.
2. Was the migration executed against a real PostgreSQL database with existing `opinion_proposals` rows? Nothing in the test suite exercises `0002`; tests build schemas with `init_db`.
3. Was `_best_boundaries` measured on a realistic first-cycle backlog, or only on the small fixtures in `test_cycles.py`?
4. `docs/behavior.md` GIT-11 states "It never repeats a pushed batch", but no code enforces that (finding 1). Is the contract intended to hold at launch, or is it aspirational?
