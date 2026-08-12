# Deployment readiness implementation review synthesis v2

## Result

Changes are required before Railway staging.

This is the first valid implementation review. All reviewers used plan commit `cb14786` as the base and reviewed snapshot `cac0a65`.

## Required fixes

### 1. Reconcile commits before retrying a batch

- Sources: Codex 1 and 2, Claude 1, GLM 1.
- Files: `src/opinions_agent/workflow.py`, `src/opinions_agent/worker.py`, `src/opinions_agent/cycles.py`, and `src/opinions_agent/recovery.py`.
- Verified problem: a caught error after a local commit or push marks the run failed. Startup ignores failed runs. `retry-cycle` queues a new agent run and can duplicate or strand committed work.
- Required outcome: reconcile failed and interrupted runs with recorded commit state before any retry. Push a known local commit when safe. Complete a remotely present commit without another agent turn. Never stop a completed batch because its final Telegram delivery failed.
- Validation: cover failures after local commit, push, database completion, and final Telegram delivery. Assert that each path produces one remote commit and no repeated agent turn.

### 2. Archive and restore failed edits

- Sources: Codex 1, Claude 2, and the main-agent verification.
- Files: `src/opinions_agent/workflow.py`, `src/opinions_agent/recovery.py`, and `src/opinions_agent/worker.py`.
- Verified problem: `_fail_run` does not archive or restore agent edits. Baseline setup errors occur outside the guarded run path. The worker then hides the error and retries a dirty checkout forever.
- Required outcome: create durable run state before fallible repository setup. Stop the cycle after a setup failure. Archive and restore target files for pre-commit failures. Clear staged target files during restoration. Preserve committed files for git reconciliation.
- Validation: fail after unstaged edits, staged edits, repository refresh, and baseline capture. Assert a stopped cycle, one notification, a clean restored target set, and no retry loop.

### 3. Reconcile interrupted runs after startup

- Sources: Codex 3, Claude 1, and GLM 3.
- Files: `src/opinions_agent/worker.py` and `src/opinions_agent/workflow.py`.
- Verified problem: startup skips an unexpired running lease. The worker never checks it again, so the run can remain active forever.
- Required outcome: sweep running leases during worker polling. Stop and restore an expired agent turn. Keep awaiting-user runs unchanged. Reclaim queued and pending work safely.
- Validation: restart before lease expiry, advance past expiry without another restart, and assert that the cycle stops and becomes retryable.

### 4. Recover cycles left in `starting`

- Sources: Codex 4, Claude 6, and the main-agent verification.
- Files: `src/opinions_agent/cycles.py` and `src/opinions_agent/worker.py`.
- Verified problem: a process crash can leave a reserved cycle in `starting`. Later starts return that cycle forever. Snapshot retry only accepts stopped cycles with no batches.
- Required outcome: reconcile every starting cycle during startup. Promote a complete materialized snapshot to active. Complete a valid zero-batch snapshot. Mark an incomplete snapshot stopped and make it safe to retry without losing assignments.
- Validation: crash after reservation, after file creation, after batch commit, and before the final status commit.

### 5. Require explicit safe Railway configuration

- Sources: Codex 5, Claude 4, and the main-agent verification.
- Files: `src/opinions_agent/config.py`, `src/opinions_agent/app.py`, and `src/opinions_agent/cli.py`.
- Verified problem: missing volume configuration skips web validation. A default SQLite URL passes the database check. A Railway web process can start with ephemeral paths and local defaults.
- Required outcome: detect a Railway web runtime even when required variables are missing. Require an explicit `staging` or `prod` environment. Require a valid PostgreSQL URL. Require the volume and every existing web setting. Keep `cron-trigger` independent from web validation.
- Validation: reject missing environment, missing volume, SQLite, malformed URLs, unsafe staging values, and unsafe production values. Confirm that the cron command still needs only its URL and secret.

### 6. Replace exhaustive partition search and fix split placement

- Sources: Codex 8, Claude 5, and the main-agent verification.
- Files: `src/opinions_agent/cycles.py` and `tests/test_cycles.py`.
- Verified problem: `_best_boundaries` stores every legal partition. Runtime grows exponentially. A `[5, 45]` document order produces `30/20` instead of the legal `25/25` split.
- Required outcome: use a memoized dynamic-programming search. Keep the documented rank order. Place a split near the next global equal-row boundary, including rows before the blocking document.
- Validation: add `[5, 45]`, `[45, 5]`, randomized ordering, cap, uniqueness, minimal batch count, and a large document-heavy case with a practical time bound.

### 7. Serialize worker claims and pin one replica

- Sources: Codex 9 and Claude 7.
- Files: `src/opinions_agent/worker.py`, `src/opinions_agent/cycles.py`, and `railway.toml`.
- Verified problem: two workers can select the same queued batch before either creates a run. Railway does not pin one replica.
- Required outcome: use a PostgreSQL lease or an atomic database claim before processing pending runs or queued batches. Recover an expired claim. Add `numReplicas = 1` to Railway configuration.
- Validation: run concurrent worker claims and assert one run and one agent turn. Validate the Railway file against the published schema.

### 8. Verify local and remote git ancestry

- Sources: Codex 6 and 7, Claude 9, and GLM 5.
- Files: `src/opinions_agent/recovery.py` and `src/opinions_agent/repo_checkout.py`.
- Verified problem: remote reconciliation only accepts exact branch-tip equality. Baseline capture accepts a clean local branch that is ahead of or different from the remote branch.
- Required outcome: treat the recorded run commit as durable when it is an ancestor of the fetched remote branch. Require local `HEAD` to equal the fetched remote branch before a new agent turn.
- Validation: cover a remote descendant, a local branch ahead, a local branch behind, and a diverged branch.

### 9. Keep redacted operational diagnostics

- Sources: Claude 3 and GLM 2.
- Files: `src/opinions_agent/worker.py`, `src/opinions_agent/workflow.py`, and a narrow redaction helper.
- Verified problem: the worker discards exceptions. Cycle records and Telegram messages are intentionally generic, so operators receive no diagnostic detail.
- Required outcome: log the exception type, redacted message, cycle ID, batch number, and run ID. Do not log credentials or raw authorization values. Keep stored and Telegram failures generic.
- Validation: capture logs for a failure containing fake secrets. Assert useful context is present and every secret is absent.

### 10. Match the HTTP and health contracts

- Sources: GLM 4 and the missing-test sections from all reports.
- Files: `src/opinions_agent/app.py`, `src/opinions_agent/cli.py`, and `tests/test_deployment.py`.
- Verified problem: a new no-evidence cycle returns 202, although the plan requires 200. Existing, stopped, cron failure, and health failure paths lack tests.
- Required outcome: return 200 for no evidence and existing work, 202 only for newly queued work, and 409 for stopped work. Keep health read-only and unhealthy until database, volume, and reconciliation checks pass.
- Validation: cover endpoint 200, 202, 401, and 409; cron 200, 202, 401, 409, network, and server failures; and health startup, database, and volume failures.

### 11. Remove the duplicate cycle-start path

- Sources: Claude 6 and the main-agent verification.
- Files: `src/opinions_agent/cycles.py` and `tests/test_cycles.py`.
- Verified problem: `start_cycle_from_corpus` duplicates production reservation and materialization. It omits production failure handling and exists only for tests.
- Required outcome: delete the duplicate function. Test `start_opinion_cycle` with a no-op or fixture sync function.
- Validation: run all cycle tests through the production cycle interface.

### 12. Harden migration and project-root resolution

- Sources: Claude 8, the invalid-round Claude report item 10, and the main-agent verification.
- Files: `alembic/versions/0002_deployment_cycles.py`, `alembic.ini`, and migration tests.
- Verified problem: constraint lookup can raise an unexplained `StopIteration`. Alembic paths remain relative to the caller despite loading the root configuration file.
- Required outcome: fail with a clear migration error when the old constraint is absent. Resolve Alembic paths with `%(here)s`. Keep the tested PostgreSQL 0001-to-0002 upgrade.
- Validation: run the migration against PostgreSQL with an existing 0001 schema and representative rows. Run `init-runtime` outside the repository directory.

### 13. Preserve run-only recovery

- Source: invalid-round Claude report item 11, verified by the main agent.
- Files: `src/opinions_agent/workflow.py` and recovery tests.
- Verified problem: `complete_reconciled_run` marks a non-cycle run complete without moving its artifacts from `active`.
- Required outcome: finalize non-cycle artifacts during commit reconciliation. Do not change disposable eval and sample selection behavior.
- Validation: reconcile one run-only pushed commit and assert its final artifacts and database state.

### 14. Fill the remaining durability test gaps

- Sources: missing-test sections from Codex, Claude, and GLM.
- Files: cycle, deployment, workflow, and recovery tests.
- Required outcome: add meaningful tests for late old-timestamp evidence, changed fingerprints, immutable bundles, fixed split-document critic context, no-evidence cycles, cross-week concurrent starts, startup with a dirty active checkout, and retry without repeating completed batches.
- Validation: each test must use the production interface and an independent expected result.

## No action

- Keep Braintrust keys mandatory in production. `docs/behavior.md` says production agent runs land in Braintrust, and the launch checklist requires trace verification.
- Keep `init-runtime && serve` as the supported Railway web entry point. `serve` alone does not need to clone a fresh repository.
- Do not add internal batch status details to `docs/behavior.md`. The contract already states that later batches wait until the prior batch succeeds.
- Do not special-case database health errors to 503. Any non-success response makes Railway mark the service unhealthy.

## Required final gate

Run these checks after all fixes:

```bash
uv lock --check
uv run pytest
uv run ruff check .
uv run pyright
OPINIONS_RUN_REAL_E2E=1 uv run pytest tests/test_real_e2e_optional.py
```

Also rerun the PostgreSQL migration, Railway schema validation, wheel check, and `W04 W10 W12 W13` compatibility samples when code on those paths changes.
