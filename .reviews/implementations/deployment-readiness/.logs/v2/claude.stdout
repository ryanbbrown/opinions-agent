# Review: deployment readiness (v2)

## Verdict

**Changes requested.** The methodology integration, durable schema, partitioner, bundle materialization, and documentation match the plan well. Four recovery and configuration defects would surface on the first real Railway incident, and one performance defect can hang the start endpoint.

## Findings

### 1. A fast restart during a model call stalls the cycle permanently and silently (high)

`worker.py:32` treats a `running_agent` run as interrupted only when `lease_expires_at <= now`. The lease is 15 minutes (`workflow.py:277`). Railway restarts in seconds, so after a crash mid-turn the lease is still in the future. The run stays `running_agent`, `process_queued_once` returns `False` at `worker.py:76-77` forever, `retry_stopped_cycle` refuses with "run is still active" (`cycles.py:495-497`), and no Telegram notice is sent.

`reconcile_startup` runs once in the lifespan, so the stall never clears even after the lease expires. Only a manual `abandon-run` plus a second restart recovers. Re-check expired running leases inside `worker_loop`, not only at startup.

### 2. A failure before the agent turn loops forever without notice (high)

`start_materialized_opinion_run` wraps only `_run_agent_turn` in its `try`. `ensure_opinions_repo` (`workflow.py:184`) and `capture_run_baseline` (`workflow.py:205`) run outside it. `capture_run_baseline` calls `assert_targets_clean`, which raises when the checkout is dirty — the exact state the recovery design expects after an archived failure.

The exception reaches `worker_loop`, whose bare `except Exception: session.rollback()` (`worker.py:109-112`) discards it. The batch stays `queued`, the cycle stays `active`, no cycle-stopped notice is sent, and the worker retries every two seconds and re-fetches the repository each time.

### 3. A stopped cycle leaves no diagnostics anywhere (high)

`workflow.py:955` replaces the exception text with the literal `"run_failed"` for every cycle run. The Telegram notice is generic by design. `worker_loop` swallows its exception. No module in the change (`cycles.py`, `worker.py`, `recovery.py`, new `workflow.py` code) contains a single logging call.

The plan requires "Keep detailed redacted diagnostics in application logs." As written, an operator gets a failure code and nothing else. Log the redacted exception before overwriting `failure_reason`. `redact_git_error` already exists for that.

### 4. Web validation is gated on the one variable it must require (medium-high)

`app.py:32-33` and `cli.py:118-121` call `validate_web_settings` only when `settings.volume_mount_path is not None`, meaning only when `RAILWAY_VOLUME_MOUNT_PATH` is set. That variable is itself in the required list, so the check can never fire for its own key.

If the volume detaches or the variable is missing, validation is skipped entirely, `environment` falls back to `"dev"` (`config.py:93`), and the service writes the corpus, cycle bundles, and repository checkout to ephemeral container storage. Gate on `settings.environment in {"staging", "prod"}` instead. That is what `OPINIONS_ENVIRONMENT` exists for, and the plan requires an explicit value for it.

### 5. `partition_evidence` enumerates every legal partition (medium)

`_best_boundaries` (`cycles.py:143-169`) recurses over all boundary combinations and appends *every* valid partition to `candidates` before taking the minimum. Branching is bounded only by the row window and the hard caps, so cost grows exponentially with batch count.

A document-heavy cycle of 150 single-highlight documents needs eight batches with roughly twelve boundary choices each: about 3.5e7 candidates, each holding full row lists. That blocks the event loop, which also serves `/healthz`, the Telegram webhook, and the worker. Plan step 5 asks for "a dynamic-programming search, which compares legal boundaries without brute-force enumeration." Memoize on `(start, batches_left)` and keep only the best rank per state.

### 6. `start_cycle_from_corpus` cannot recover from a snapshot failure (medium)

`start_opinion_cycle` marks a failed reservation `stopped` / `snapshot_failed` (`cycles.py:323-334`), which makes `retry-cycle` work. The sibling `start_cycle_from_corpus` (`cycles.py:212-266`) has no such handler. If `partition_evidence` or `_materialize_cycle` raises, the cycle stays `starting`. `_unfinished_cycle` counts `starting`, so every later start returns `existing`, and `retry_stopped_snapshot` requires status `stopped`. The system wedges until someone edits the database.

The three reserve-and-materialize blocks (`start_cycle_from_corpus`, `start_opinion_cycle`, `retry_stopped_snapshot`) are near-identical. Collapse them into one function with an optional sync callable. That removes the divergence and satisfies the project's simplest-implementation rule.

### 7. Nothing pins one replica, and the worker claims work without a lease (medium)

The plan requires "Use one replica" and "Use a database lease when the worker claims a queued run." `railway.toml` sets `overlapSeconds` and `drainingSeconds` but not `numReplicas = 1`. `process_queued_once` claims a batch with a plain `SELECT` and a non-atomic status write. The only atomic claim is `_claim_awaiting_run` on the Telegram path.

Two replicas would start the same batch twice and produce conflicting commits. Add `numReplicas = 1` to `railway.toml`, or use the `WorkflowLease` claim the plan specified. The table and `acquire_lease` already exist and serve only the cycle-start path today.

### 8. Migration 0002 is never exercised (medium)

`tests/conftest.py` builds the schema with `init_db` on SQLite. Nothing runs `alembic upgrade head`. Migration 0002 holds the riskiest untested code in the change: `alembic/versions/0002_deployment_cycles.py:88-92` uses `next(...)` over reflected unique constraints and raises a bare `StopIteration` if the reflected column order or name differs. The start command is `init-runtime && serve`, so a migration failure is a deploy failure.

### 9. Minor items

- `app.py:70-72`: `engine.connect()` raises `OperationalError` outside any handler, so an unreachable database returns HTTP 500 rather than the 503 the volume-path branch returns. Railway treats both as unhealthy, so this is cosmetic.
- `recovery.py:20-35`: `capture_run_baseline` asserts the target files are clean and records `HEAD`, but does not check the plan's first batch-baseline rule — "require the opinions checkout to match the last successful remote commit."
- `cli.py:122-131`: `init-runtime` decides `refresh` from active cycles only. Plan startup step 7 also covers non-terminal runs and recovery state.
- `_complete_done_run` records `pushed` immediately after `git push` returns. The plan asks to "Confirm the remote contains that SHA before recording `pushed`." `reconcile_git_durability` does verify, so this is a small deviation.

## Missing or follow-up tests

Plan-required cases with no coverage in the snapshot:

- Restart reclaims a queued run; restart preserves an awaiting-user run; an expired running lease stops the cycle and permits retry. `reconcile_startup` has no test at all.
- Start endpoint returns 200 and 409. Only 401 and 202 are covered (`tests/test_deployment.py:120-159`).
- Cron trigger maps 401, 409, and network failure to nonzero exit codes. Only 202 is covered.
- Health fails before reconciliation, on database failure, and on missing volume paths.
- Production validation rejects unsafe values. `railway_settings` accepts `environment="prod"` but only staging is validated, so the prod target-file and Braintrust rules never run.
- Randomized document sizes satisfy both caps and the minimal feasible batch count. `test_partition_preserves_every_evidence_version_and_caps` uses one fixed shape and does not assert minimality. Add a large document-heavy case; it will also expose finding 5.
- Late new evidence with an old source timestamp enters a later cycle.
- Later corpus mutation cannot change a materialized batch.
- Split-document critic context stays fixed and cycle-wide.
- A no-evidence start creates one completed zero-batch cycle.
- Cross-week concurrent starts create only one active cycle.
- Startup does not pull over an active dirty checkout.
- Railway configs validate against the current published schema.
- A migration test that runs `alembic upgrade head` against PostgreSQL.

Also run the plan's local gate before staging: `uv lock --check`, `uv run pytest`, `uv run ruff check .`, `uv run pyright`, and the optional real end-to-end test. I did not run any of these.

## Open questions

1. Is `start_cycle_from_corpus` intended to survive past this change, or was it a test seam? If it is a test seam, deleting it and testing `start_opinion_cycle` with a no-op sync removes finding 6 outright.
2. Does ThinHarness 0.6.0 accept `HarnessConfig(effort=...)` and `SubAgentConfig`? I could not verify the dependency from the snapshot. `tests/test_validation.py:243-245` asserts `config.effort` and `config.subagents[0].builtin_tools == []`, so a passing test run answers this.
3. The plan lists `running` and `awaiting_user` batch statuses; the implementation adds `pending` for batches two and later. That reads as an improvement over reusing `queued`. Confirm the plan text should follow.
