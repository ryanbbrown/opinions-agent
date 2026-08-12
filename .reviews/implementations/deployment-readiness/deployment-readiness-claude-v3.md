# Review: deployment readiness (v3)

## Verdict: changes requested

Two findings block a safe launch: a mid-cycle recovery path that wedges a cycle permanently, and a run-lease race that can destroy a live agent's edits. The rest of the diff is strong — the partitioner matches the plan's spec and its examples, the assignment ledger replaces the cursor cleanly, and the git phase machine, redaction, and Railway surfaces are faithful to the plan.

---

## Findings

### 1. High — Reconciled mid-cycle batch leaves the cycle `stopped` forever

`_complete_cycle_batch` resets `cycle.status`, `failure_code`, and `failure_summary` only on the final-batch branch (`src/opinions_agent/workflow.py:1067`). The non-final branch (`src/opinions_agent/workflow.py:1058-1065`) queues the next batch but leaves the cycle exactly as `_stop_cycle` left it.

Failure scenario — this is the plan's own required test "Failure after local commit reconciles through run ID and SHA":

1. Batch 1 of 3 commits, then the push raises. `_fail_run` → `_stop_cycle` sets cycle `stopped`, batch `stopped`, run `failed` (`src/opinions_agent/workflow.py:984-996`).
2. Next worker tick: `reconcile_startup` → `reconcile_git_durability` pushes the recorded SHA → `complete_reconciled_run` → `_complete_cycle_batch` marks batch 1 `completed` and batch 2 `queued`, **cycle still `stopped`**.
3. `worker.process_queued_once` only claims batches whose cycle is `active` (`src/opinions_agent/worker.py:106`), so batch 2 never starts.
4. `retry_stopped_cycle` requires the batch at `cycle.current_batch` to be `stopped`, but batch 2 is now `queued` (`src/opinions_agent/cycles.py:551`), so it raises `stopped cycle has no retryable batch`.

The cycle is unrecoverable without a manual database edit, and every later weekly cron start returns 409 against it. `complete_reconciled_run` should restore `cycle.status = active` and clear the failure fields whenever it queues a next batch.

No test covers this: `test_local_commit_failure_reconciles_without_another_agent_turn` and `test_pushed_commit_failure_reconciles_without_another_agent_turn` (`tests/test_workflow.py`) both use runs with `cycle_id is None`, so `_complete_cycle_batch` is never reached. `test_worker_continues_batches_after_telegram_completion` (`tests/test_cycles.py:240-244`) hand-sets both cycle and batch to `stopped` before calling `retry_stopped_cycle`, which is exactly the state reconciliation does *not* produce.

### 2. High — The 15-minute run lease is never renewed, so the worker can sweep a live Telegram-resumed turn

`_run_agent_turn` (`src/opinions_agent/workflow.py:305`) and `_claim_awaiting_run` (`src/opinions_agent/workflow.py:783`) stamp `lease_expires_at = now + 15 min` and never extend it during the turn. `worker_loop` polls every 2 seconds (`src/opinions_agent/worker.py:142`) and calls `reconcile_startup` on every tick (`src/opinions_agent/worker.py:73`), which treats any `running_agent` run with an expired lease as interrupted.

For worker-started runs this is safe: the loop is blocked inside its own `await`. But Telegram-resumed turns run in the FastAPI request task, concurrently with the idle worker loop. A resume turn is the long one — it drafts, runs one critic subagent per proposal, edits three artifacts, and validates. If it exceeds 15 minutes:

- `archive_and_restore_run` (`src/opinions_agent/worker.py:50`) runs `git reset` on the target files and overwrites `OPINIONS.md`, `OPINIONS_SOURCES.jsonl`, `opinion-decisions.jsonl`, and the opinion-ID high-water file from the baseline — while the agent still holds write access to them.
- The run flips to `failed` and the cycle to `stopped`, and a failure notice goes out, even though the model call is still in flight.
- The still-running turn then calls `transition(run, AWAITING_USER)` from `failed` and raises, so the user sees a hard failure plus silently reverted edits.

Either renew the lease from inside the agent turn (a heartbeat task, or refresh on each harness callback), or scope the expired-lease sweep to process startup rather than every worker tick. `test_worker_claim_serializes_agent_turns_and_expired_run_is_swept` (`tests/test_cycles.py:263`) only exercises the worker-owned case.

### 3. Medium — Unreconcilable failed runs cause a 2-second `git fetch` loop against GitHub

`reconcile_git_durability` calls `remote_contains_result`, which always runs a real `git fetch origin <branch>` (`src/opinions_agent/recovery.py:76-82`). A `failed` run with `git_result_sha` set that cannot be reconciled — phase `pushed` but the remote no longer contains the SHA, or phase `committed` with `HEAD` moved past it (`src/opinions_agent/recovery.py:115-119`) — returns `False` every time and stays a `reconcile_startup` candidate forever (`src/opinions_agent/worker.py:37-41`). The worker then fetches GitHub every 2 seconds indefinitely, which will hit rate limits and burn the token's quota. The same tick also inserts and deletes a `workflow_leases` row every 2 seconds.

### 4. Medium — A failing reconciliation crashes web startup instead of reporting unhealthy

`app.lifespan` calls `reconcile_startup` with no exception handling (`src/opinions_agent/app.py:38`). `complete_reconciled_run` runs `run_artifact_validation`, which raises on any artifact defect, and `reconcile_git_durability` raises `GitToolError` on any git failure. Either aborts the lifespan, so the container never binds and never serves `/healthz` at all — with `restartPolicyMaxRetries = 3`, the service goes down hard rather than reporting 503. The plan's intent ("Make health require … completed startup reconciliation") reads as a 503, which `startup_ready` already implements; catching and logging the reconciliation failure while leaving `startup_ready = False` matches it better.

### 5. Medium — Web validation is gated on Railway-only environment markers

`validate_web_settings` runs only when `is_railway_runtime()` is true, which checks `RAILWAY_PROJECT_ID` / `RAILWAY_ENVIRONMENT_ID` / `RAILWAY_SERVICE_ID` (`src/opinions_agent/config.py`, `src/opinions_agent/app.py:31-33`, `src/opinions_agent/cli.py:119-122`). If Railway renames or omits those, the service starts silently with `environment="dev"` (the old `RAILWAY_VOLUME_MOUNT_PATH` fallback was removed), local plaintext tracing enabled, and no required-variable check — the opposite of the completion criterion "Unsafe production configuration prevents startup." Validating whenever `settings.environment in {"staging", "prod"}` **or** the Railway markers are present would fail closed in both directions.

### 6. Low — `secrets.compare_digest` raises on non-ASCII headers, returning 500 instead of 401

`src/opinions_agent/app.py:87` and `src/opinions_agent/app.py:112` pass raw header strings to `compare_digest`, which raises `TypeError` for any non-ASCII character. An attacker probing with a UTF-8 `Authorization` header gets a 500 and a stack trace in the logs rather than a clean 401. Encode both sides to bytes first.

### 7. Low — The run-retention sweep deletes completed cycle bundles and failed-edit archives

`complete_cycle_directory` moves `<cycle_id>` into `RUNS_DIR/completed/` (`src/opinions_agent/cycles.py:527-536`), the same directory `cleanup_completed_runs` prunes by mtime at `OPINIONS_COMPLETED_RUN_RETENTION_DAYS` (default 30) without checking the directory shape (`src/opinions_agent/selection.py:211-224`). That silently deletes the immutable evidence snapshot, the critic context, and the `recovery/<run_id>/failed` archives the plan says to keep for inspection.

### 8. Low — Document-level fields in the fingerprint re-queue whole documents

`evidence_fingerprint` hashes `document_title`, `document_author`, `document_summary`, and `content_path` alongside the row's own text and note (`src/opinions_agent/cycles.py:65-79`). A Reader-side title correction or summary refresh changes the fingerprint of **every** highlight in that document, so all of them become eligible again and get re-proposed in a later cycle. That is a defensible reading of "fingerprint the fields the agent can read," but it is a much wider re-processing trigger than "a material content change." Worth confirming this is intended before the first production cycle, since it is the kind of thing that shows up as a week of duplicate proposals.

### 9. Nit — `complete_reconciled_run` bypasses the run state machine

`src/opinions_agent/workflow.py:286` assigns `run.status = COMPLETED` directly. `failed → completed` is not in `VALID_TRANSITIONS`, so the declared state machine no longer describes the transitions the system actually performs, and `run.failure_reason` stays populated on a completed run.

---

## Tests the writer should run or add

1. **Cycle reconciliation continues the cycle.** Start a 2-batch cycle, fail batch 1's push, then run `reconcile_startup`. Assert the cycle returns to `active`, `failure_code` is `None`, and the next `process_queued_once` starts batch 2. This is the plan's "Failure after local commit reconciles through run ID and SHA" plus "Resume automatic continuation only after the retry succeeds" — currently only covered for non-cycle runs.
2. **Expired lease during a live Telegram resume.** Drive a resume turn with a blocking agent, expire `lease_expires_at`, tick `process_queued_once`, and assert the writable artifacts are untouched and the run is not swept.
3. **Repeated reconciliation of an unrecoverable failed run.** Count `git fetch` invocations across ~5 worker ticks for a `failed` run with a `git_result_sha` the remote does not contain; assert the count does not grow per tick.
4. **Retention sweep with a completed cycle present.** Age a `completed/<cycle_id>` directory past the retention window and assert `cleanup_completed_runs` does not remove it.
5. **Startup reconciliation failure.** Make `run_artifact_validation` raise during lifespan reconciliation; assert the app still serves and `/healthz` returns 503.
6. **Non-ASCII auth headers** on both `/internal/opinion-cycle/start` and `/telegram/webhook` return 401.
7. **Single-document exactly-50-row split.** `counts([50]) == [25, 25]` — the plan lists it explicitly; `tests/test_cycles.py` covers `[51]` and `[45, 5]` but not `[50]`.
8. Plan gate, unchanged: `uv lock --check`, `uv run pytest`, `uv run ruff check .`, `uv run pyright`, and the optional real-E2E run. I did not run any of these.

## Open questions

1. **What is the realistic p99 for a Telegram-resumed turn** with one critic subagent per proposal at `openai:gpt-5.6-sol` medium effort? That number decides whether finding 2 is a launch blocker or a staging-only concern.
2. **Is `HarnessConfig(effort=...)` the correct ThinHarness 0.6.0 field?** `src/opinions_agent/agent.py:227` replaces `extra_body={"reasoning": {"effort": ...}}`. `tests/test_validation.py:243` asserts the attribute exists but not that it reaches the provider — the plan's direct-API sample run is the only real check here.
3. **Should document-level fingerprint fields be narrowed** to the row's own text and note (finding 8)?
4. `railway.toml` sets `overlapSeconds` and `drainingSeconds`; the plan's phase 5 requires validating both Railway files against Railway's published JSON schema. I could not verify that offline — confirm it before deploying.
