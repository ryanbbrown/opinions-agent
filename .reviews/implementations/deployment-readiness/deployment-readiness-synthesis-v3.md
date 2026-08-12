# Deployment readiness implementation review synthesis v3

## Result

Changes are required before Railway staging.

This is the second valid implementation review. All reviewers used plan commit `cb14786` as the base and reviewed the frozen v3 snapshot recorded in the round manifest.

## Required fixes

### 1. Make the batch baseline a durable run precondition

- Sources: Codex 1 and GLM 2.
- Files: `src/opinions_agent/workflow.py`, `src/opinions_agent/recovery.py`, and `src/opinions_agent/worker.py`.
- Verified problem: the app commits a pending run before it records the baseline. A restart can claim that run and start the agent without a complete baseline. Restoration treats missing baseline files as files that were originally absent, so it can delete current artifacts.
- Required outcome: record a durable baseline-complete marker before any agent turn can start. Reclaimed pending runs must finish repository checks and baseline capture first. Archive, restore, abandon, and retry operations must fail safely when the baseline is incomplete.
- Validation: simulate a crash after pending-run creation and during baseline capture. Assert that the reclaimed run captures a complete baseline before the agent starts. Assert that recovery and abandonment never delete artifacts from an incomplete baseline.

### 2. Resume a reconciled non-final cycle

- Sources: Claude 1 and GLM 1.
- Files: `src/opinions_agent/workflow.py` and cycle recovery tests.
- Verified problem: commit reconciliation can complete a non-final batch and queue the next batch while leaving the cycle stopped. The worker only claims active cycles, and retry rejects the queued next batch. This leaves the cycle wedged.
- Required outcome: when reconciliation completes a non-final batch, set the cycle to active and clear its failure fields before queuing continuation. Final-batch reconciliation must still complete the cycle.
- Validation: reconcile a failed local commit in a two-batch cycle. Assert that batch one completes, the cycle becomes active, batch two queues, and the worker starts it. Cover final-batch reconciliation too.

### 3. Prevent recovery from sweeping a live agent turn

- Source: Claude 2.
- Files: `src/opinions_agent/workflow.py`, `src/opinions_agent/worker.py`, and lease tests.
- Verified problem: a running-agent lease expires after 15 minutes and is never renewed. The worker checks expiry every two seconds. A long Telegram-resumed turn can therefore be archived and restored while it still edits files.
- Required outcome: a live turn must keep ownership for its full execution. Recovery must still reclaim a turn after its process stops. Use a heartbeat, durable renewal, or an equivalent safe ownership rule. Do not allow the worker to restore artifacts while the owning turn is live.
- Validation: block a Telegram-resumed turn past the lease duration while the worker polls. Assert that the run and artifacts remain untouched. Then simulate process loss and assert that restart recovery stops and restores the run.

### 4. Make concurrent starts duplicate-safe

- Source: Codex 2.
- Files: `src/opinions_agent/cycles.py` and PostgreSQL concurrency tests.
- Verified problem: the start lease is committed before the owning request reserves its cycle. A concurrent request can lose the lease, observe no cycle yet, and raise an internal error.
- Required outcome: a concurrent loser must return the existing same-week or unfinished cycle. It must not return HTTP 500. Reserve atomically or retry the lookup for the bounded reservation interval.
- Validation: issue same-week and cross-week starts through separate PostgreSQL sessions. Assert one sync and one cycle. Assert that every caller receives a defined no-op or created result.

### 5. Enforce the exact partition balance range

- Source: Codex 3.
- Files: `src/opinions_agent/cycles.py` and partition tests.
- Verified problem: the partition search rounds the lower limit down and the upper limit up. It accepts integer batch sizes outside one-half to one-and-a-half times the equal target. For 51 rows, it can accept 12 and 39 rows.
- Required outcome: use exact comparisons, or use a ceiling for the lower bound and a floor for the upper bound. Keep the documented deterministic rank order and document-splitting rule.
- Validation: add `[12, 39]`, `[39, 12]`, one document with exactly 50 rows, and randomized cap and minimal-count cases.

### 6. Notify snapshot failures at cycle scope

- Source: Codex 4.
- Files: `src/opinions_agent/cycles.py`, `src/opinions_agent/worker.py`, `src/opinions_agent/workflow.py`, and notification tests.
- Verified problem: snapshot failure stops a cycle before any run exists. The run-based notice cannot report it. Startup reconciliation discards the stopped cycles returned by `reconcile_starting_cycles`.
- Required outcome: send one generic cycle-level Telegram notice for direct and startup-reconciled snapshot failures. Keep the notice free of exception text and credentials.
- Validation: cover direct snapshot failure and a reserved or partial starting cycle found on startup. Assert one notice in each case and no duplicate after another reconciliation.

### 7. Distinguish failure attempts in notification keys

- Source: Codex 5.
- Files: `src/opinions_agent/workflow.py` and notification tests.
- Verified problem: the failure notice key includes only cycle, batch, and failure code. A retry run that fails with the same code reuses the key and suppresses its notice.
- Required outcome: include the run ID or another durable attempt ID in run-scoped failure keys. Keep retries of the same delivery idempotent.
- Validation: fail two retry runs with the same code. Assert one notice per failed run and no duplicate notice for repeated reconciliation of either run.

### 8. Bound failed git reconciliation without blocking work

- Sources: Claude 3 and GLM 3.
- Files: `src/opinions_agent/recovery.py`, `src/opinions_agent/worker.py`, and recovery tests.
- Verified problem: an unreconcilable failed run fetches and may push every two seconds. A git exception escapes reconciliation and prevents the worker from processing unrelated queued work.
- Required outcome: isolate failures per run. Use durable or restart-safe backoff for repeated remote checks. Do not fetch or push every worker tick. Keep the failed run stopped for operator action while unrelated safe work can proceed.
- Validation: run several worker ticks with a persistent fetch or push failure. Assert bounded git calls, no uncaught reconciliation error, and progress for unrelated eligible work.

### 9. Keep the web process available when startup reconciliation fails

- Source: Claude 4.
- Files: `src/opinions_agent/app.py`, `src/opinions_agent/worker.py`, and health tests.
- Verified problem: a git or artifact-validation error during lifespan reconciliation aborts FastAPI startup. The app cannot serve the intended unhealthy response.
- Required outcome: bind the web process and keep readiness false after a reconciliation error. Serve HTTP 503 from health until reconciliation succeeds. Log only redacted diagnostics. Continue bounded reconciliation attempts without starting unsafe agent work.
- Validation: make git reconciliation and artifact validation fail during lifespan startup. Assert that the app serves, health returns 503, diagnostics are redacted, and readiness can become healthy after recovery succeeds.

### 10. Fail closed for explicit staging and production environments

- Source: Claude 5.
- Files: `src/opinions_agent/config.py`, `src/opinions_agent/app.py`, and `src/opinions_agent/cli.py`.
- Verified problem: web validation runs only when Railway marker variables exist. An explicitly configured staging or production process can skip validation when those markers are absent.
- Required outcome: validate the web service when the environment is `staging` or `prod`, or when Railway markers are present. Keep `cron-trigger` independent from web validation.
- Validation: reject unsafe explicit staging and production settings without Railway markers. Confirm that dev remains local and cron still needs only the start URL and secret.

### 11. Handle non-ASCII authorization values as unauthorized

- Source: Claude 6.
- Files: `src/opinions_agent/app.py` and endpoint tests.
- Verified problem: `secrets.compare_digest` raises for non-ASCII strings. A malformed start or Telegram header can return HTTP 500.
- Required outcome: compare encoded bytes or otherwise make every invalid header return HTTP 401 without logging its value.
- Validation: send non-ASCII headers to both protected endpoints. Assert HTTP 401 and no raw header in logs.

### 12. Preserve completed cycle and recovery artifacts

- Source: Claude 7.
- Files: `src/opinions_agent/selection.py`, `src/opinions_agent/cycles.py`, and retention tests.
- Verified problem: completed cycle directories use the same parent as disposable completed runs. The retention sweep can delete immutable cycle bundles and failed-edit archives.
- Required outcome: retention cleanup must identify disposable run artifacts precisely. It must not delete completed cycle bundles or their recovery archives.
- Validation: age a completed cycle directory and a disposable completed run beyond the retention period. Assert that cleanup removes only the disposable run.

### 13. Record reconciled completion through the state model

- Source: Claude 9.
- Files: `src/opinions_agent/models.py`, `src/opinions_agent/workflow.py`, and recovery tests.
- Verified problem: reconciled completion assigns the completed status directly and leaves the old failure reason on a completed run. The declared transition model does not describe recovery from failed to completed.
- Required outcome: define and use the valid recovery transition. Clear stale failure state when a known pushed commit completes successfully.
- Validation: reconcile a failed pushed run. Assert completed status, completed git phase, no failure reason, and valid cycle continuation.

### 14. Fill focused contract test gaps

- Sources: missing-test sections from Codex, Claude, and GLM.
- Files: cycle, deployment, workflow, and migration tests.
- Required outcome: add meaningful tests for split-document critic context, the exact 50-row split, the minimal cron configuration, and cycle commit reconciliation. Keep the PostgreSQL `0001` to `0002` upgrade check and Railway schema validation in the final gate.
- Validation: use production interfaces and independent expected results. Do not assert prompt wording.

## No action

- Keep document-level fields in the evidence fingerprint. The approved plan defines the fingerprint as all evidence fields the agent can read. A changed title or summary is a changed evidence version under that rule.
- Keep Braintrust keys mandatory in production. Production runs must create Braintrust traces, and the keys are available for Railway configuration.
- Keep ThinHarness reasoning configuration unchanged. The real direct-API run already verified the current ThinHarness 0.6.0 path.
- Keep the two-second worker poll. It meets automatic continuation and does not affect the required fixes.
- Do not run another full review panel. This is the second requested review cycle. Use focused inspection and the complete validation gate after fixes.

## Required final gate

Run these checks after all fixes:

```bash
uv lock --check
uv run pytest
uv run ruff check .
uv run pyright
OPINIONS_RUN_REAL_E2E=1 uv run pytest tests/test_real_e2e_optional.py
```

Also run the Braintrust-scored screen with the local `.env`, the PostgreSQL migration, Railway schema validation, wheel check, and `W04 W10 W12 W13` compatibility samples. Do not deploy to Railway during this fix step.
