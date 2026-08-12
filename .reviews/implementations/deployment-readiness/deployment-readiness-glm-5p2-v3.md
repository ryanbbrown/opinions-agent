I have enough to complete the review.

# Code Review — Deployment Readiness (v3)

**Verdict: changes requested**

The methodology integration, partitioner, assignment ledger, immutable bundles, critic subagent surface, credential redaction, Railway configs, and the run-only reconciliation path are all solid and well-tested. Two recovery-path defects in the cycle worker are real and reachable, and the cycle reconciliation path is the least-tested part of the feature. Findings below are ordered by severity.

---

## Findings

### 1. Reconciled non-final cycle batch leaves the cycle STOPPED, deadlocking continuation (medium-high)

`src/opinions_agent/workflow.py:1062-1066` — `_complete_cycle_batch` queues the next batch but never resets `cycle.status`. The final-batch branch (1067-1070) clears `failure_code`/`failure_summary` and sets `COMPLETED`; the next-batch branch only sets `next_batch.status = QUEUED` and `cycle.current_batch`.

This is harmless on the normal completion path (the cycle is already `ACTIVE`), but it breaks the reconciliation path. Trace: a cycle batch's `git push` raises in `_complete_done_run` → `_fail_run` stops the cycle (`STOPPED`, `failure_code="run_failed"`, batch `STOPPED`) with `git_phase=COMMITTED` → on the next worker poll, `reconcile_startup` → `reconcile_git_durability` retries the push and succeeds → `complete_reconciled_run` → `_complete_cycle_batch` marks batch `COMPLETED`, queues batch N+1, but leaves `cycle.status = STOPPED`.

Result: the worker's queued-batch query requires `OpinionCycle.status == ACTIVE`, so batch N+1 is never claimed. The operator's `retry-cycle` then fails because `retry_stopped_cycle` looks for `batch_number == current_batch` (now N+1) with `status == STOPPED`, but batch N+1 is `QUEUED` — "stopped cycle has no retryable batch." The cycle is wedged with no CLI escape. The run-only equivalent of this scenario is tested (`test_local_commit_failure_reconciles_without_another_agent_turn`), but no test exercises a *cycle* batch through the same reconciliation, so this slipped through.

Fix: in the `next_batch is not None` branch, set `cycle.status = CycleStatus.ACTIVE.value`, `cycle.failure_code = None`, `cycle.failure_summary = None` before the commit. This is a no-op on the normal path and heals the reconciliation path.

### 2. Reclaimed PENDING_AGENT cycle runs skip repo ensure and baseline capture (medium)

`src/opinions_agent/workflow.py:243-258` — `run_pending_opinion_run` calls `_run_agent_turn` directly, unlike `start_materialized_opinion_run` which first calls `ensure_opinions_repo` + `capture_run_baseline`. A crash between run creation (`session.commit()` at line 217) and `capture_run_baseline` leaves a `PENDING_AGENT` run with `git_phase = None` and no baseline directory. On restart, `reconcile_startup` ignores `PENDING_AGENT` runs (its candidates are only `RUNNING_AGENT`/`FAILED`), so the worker reclaims it via `run_pending_opinion_run` and runs the agent with no baseline and no clean-checkout guarantee.

If that reclaimed turn fails mid-edit, `_fail_run`'s archive branch is skipped (no `recovery/<run_id>/baseline` dir), leaving dirty writable files in the checkout. The operator's `retry-cycle` then calls `start_materialized_opinion_run`, whose `capture_run_baseline` runs `assert_targets_clean` and raises on the leftover dirty files — so the retry wedges too. The plan explicitly requires baseline capture and clean-writable enforcement before each run starts (Git durability / Batch baseline).

Fix: in `run_pending_opinion_run`, before `_run_agent_turn`, when `run.git_phase is None` run `ensure_opinions_repo(settings)` + `capture_run_baseline(settings, run, _run_dir(run, settings))` + `session.commit()`, mirroring `start_materialized_opinion_run`.

### 3. Persistent push failure in `reconcile_git_durability` raises out of `reconcile_startup` and stalls the worker (medium-low)

`src/opinions_agent/recovery.py:102-128` — when `git_phase == COMMITTED` and the remote does not yet contain the result SHA, `reconcile_git_durability` retries `run_git(..., "push", ...)` with no try/except, and `remote_contains_result` does a `git fetch` (line 76-82) on every call. A persistent failure (GitHub outage, non-fast-forward) raises `GitToolError`. `reconcile_startup` calls this inside its candidate loop (`worker.py:43`) with no surrounding try, so the exception propagates to `process_queued_once`, which calls `reconcile_startup` at the top before its own try block (`worker.py:73`). `worker_loop` catches it, but every 2-second iteration repeats the same raise, so a single FAILED run with a recorded commit blocks all worker progress for the whole deployment (including starting unrelated cycles' batches) until the git condition clears. Telegram resumes still work (webhook path), but no new batch can start.

Fix: catch push/fetch errors in `reconcile_git_durability` and return `False` (leave the run for operator retry) instead of raising, so one unrecoverable run does not stall the worker.

### 4. Split-document critic context not verified (low)

`tests/test_cycles.py:129-180` asserts each batch's `critic-context.jsonl` contains all cycle-selected rows for that batch's documents, but uses `[45, 5]` (two whole documents, none split). The plan requires "Split-document critic context stays fixed and cycle-wide" — i.e., a document split across two batches must appear in *both* batches' `critic-context.jsonl`. `_materialize_cycle` builds `context_rows` from `all_rows_by_doc` for the batch's `document_ids`, so it should be correct, but no test pins it. Add a case where `partition_evidence` splits one document (e.g., `counts([51])` → `[25, 26]`) and assert both batch context files contain all 51 rows' document rows.

### 5. Alembic migration 0002 is never exercised (low)

Tests use `init_db` → `Base.metadata.create_all` (`src/opinions_agent/db.py:20`, `tests/conftest.py:37`), so `alembic/versions/0002_deployment_cycles.py` runs only on Railway Postgres. The proposal unique-constraint drop (looked up by `column_names == ["opinion_run_id", "batch", "proposal_id"]`) and the `opinion_runs` NOT NULL column adds are unverified. The lookup is robust, but a one-shot `alembic upgrade head` smoke test against a fresh Postgres (or SQLite with batch mode) would de-risk the first production deploy.

### 6. Railway schema validation not tested (low)

The plan lists "Railway configs validate against the current published schema" as a required test. `railway.toml` and `railway.cron.toml` are present and well-formed, but no test asserts schema conformance. Add a CI check against Railway's published JSON schema.

### 7. cron-trigger independence not asserted (low)

The code is correct: `_run` returns for `cron-trigger` before creating the engine (`cli.py:108-110`), and `validate_cron_settings` only needs `OPINIONS_START_URL`/`OPINIONS_START_SECRET`. The plan's required test "Cron command needs no database, volume, Reader, Telegram, or model settings" has no direct assertion. The existing cron tests mock httpx over a full `Settings` object. Consider a test that constructs `Settings` with only the two cron fields populated and asserts `_cron_trigger` does not touch the DB or filesystem.

---

## Missing / follow-up tests for the writer to run

- **Cycle-batch reconciliation** (covers finding 1): create a 2-batch cycle, start batch 1, force a push exception during `_complete_done_run`, assert the cycle is `STOPPED` and batch 1 `FAILED` with `git_phase=COMMITTED`; then run `reconcile_startup` with the push restored and assert the cycle returns to `ACTIVE`, batch 1 `COMPLETED`, batch 2 `QUEUED`, and `process_queued_once` then starts batch 2. Also test the final-batch variant reconciles to `COMPLETED`.
- **PENDING_AGENT reclamation** (covers finding 2): create a cycle run, set it to `PENDING_AGENT` with `git_phase=None` and no baseline dir (simulating a mid-setup crash), then assert `process_queued_once` captures the baseline and enforces clean targets before the agent turn; assert a dirty checkout stops the cycle.
- **Persistent push failure** (covers finding 3): a `COMMITTED` cycle run whose push keeps failing should leave the run `FAILED` and the cycle `STOPPED` without raising out of `reconcile_startup`, and a *second* cycle's queued batch should still start.
- Run the full local gate from the plan: `uv lock --check`, `uv run pytest`, `uv run ruff check .`, `uv run pyright`, then `OPINIONS_RUN_REAL_E2E=1 uv run pytest tests/test_real_e2e_optional.py`.
- Validate `railway.toml` / `railway.cron.toml` against Railway's published schema.

## Open questions

- The plan says "Wake the worker after cycle creation and successful batch completion." The implementation polls every 2 s (`worker.py:142`) instead of explicit wake. Functionally equivalent for single-replica automatic continuation, but confirm the 2 s poll cadence is acceptable for the Telegram review UX (a batch that completes via Telegram waits up to 2 s for the next to start).
- `validate_web_settings` requires Braintrust keys for *all* prod (`config.py:156`), while the plan says "when production tracing is enabled." Intentional strictness, or should prod allow tracing-disabled with no Braintrust keys?

## Residual risks

- Eligibility is by assignment + launch boundary, not by `window_end` (`cycles._eligible_versions`). This is per the plan's "late evidence" design, but it means a retried snapshot (which re-syncs) can pull evidence highlighted after the original reservation into the cycle. Confirm this is desired for snapshot retries.
- `complete_cycle_directory` (`cycles.py:527-536`) raises `FileNotFoundError` if both `active/` and `completed/` dirs are missing. Not reached in normal flow, but a partial filesystem state could surface it.
- The two correctness findings (1 and 2) are narrow edge cases (transient push failure on a non-final batch; crash in the setup window) but both produce states with no CLI recovery path, so I recommend fixing before the staging cycle rather than relying on staging to surface them.
