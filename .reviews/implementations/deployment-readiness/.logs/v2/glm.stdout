# Review: deployment readiness (v2)

**Verdict: changes requested**

The cycle machinery, partitioner, immutable bundles, critic wiring, credential handling, and Railway surfaces are well-built and align with the plan. The partitioner matches every worked example in the plan, the git askpass path keeps the token out of args/config/logs, and the assignment ledger correctly replaces the timestamp cursor. One durability gap in the push-failure recovery path needs fixing before launch, plus a few smaller items.

## Findings (ordered by severity)

### 1. High — A push-failed batch can complete as a no-op on retry, stranding its commit off the remote
`src/opinions_agent/workflow.py:331-353` does the commit (`push=False`) and a separate `run_git push`. If the push raises, the `except` at `:387` calls `_fail_run`, which marks the run `FAILED` and stops the cycle — even though a local commit is already durable (`git_phase == COMMITTED`, `git_result_sha` set).

`reconcile_startup` (`src/opinions_agent/worker.py:24`) only inspects runs in `RUNNING_AGENT`. A crashed-after-commit run stays `RUNNING_AGENT` and is reconciled correctly, but a *caught* push failure is `FAILED`, so it is never reconciled. The only recovery path is `opinions-agent retry-cycle`, which calls `retry_stopped_cycle` (`cycles.py:455`) — this re-queues the batch for a fresh agent run instead of pushing the existing local commit, contradicting the plan's "Never rerun a batch whose pushed commit can be reconciled" and "Failure before database completion reconciles the remote commit."

Worse: on retry, `start_materialized_opinion_run` → `ensure_opinions_repo(refresh=True)` fast-forwards over the stranded commit (ff-only no-ops when local is ahead), and `capture_run_baseline` (`recovery.py:18`) records the stranded commit's HEAD as the baseline without comparing it to the remote. If the retried agent finds the edits already present, `commit_and_push_opinions_files` returns `changed=False, commit_sha=None`, the `if commit.commit_sha:` push is skipped, `git_phase` is recorded as `PUSHED`, and `_complete_cycle_batch` completes the batch with `commit_sha=None`. The cycle completes "successfully" but the stranded commit is never pushed — the remote silently loses that batch's work.

Suggested fix: have `reconcile_startup` (or the retry entry point) attempt `reconcile_git_durability` on `FAILED` runs whose `git_phase` is `COMMITTED`/`PUSHED` and `git_result_sha` is set, and/or have `retry_stopped_cycle` reconcile before re-queueing. Separately, `capture_run_baseline` should verify local HEAD matches the remote head before accepting it as the baseline (see finding 5).

### 2. Medium — No application logging; worker swallows failure diagnostics
There is no `logging`/`logger` use anywhere under `src/`. `worker_loop` (`worker.py:104`) catches `Exception`, rolls back, sets `worked=False`, and discards the exception. `_fail_run` (`workflow.py:955`) stores only `"run_failed"` for cycle runs, dropping `str(exc)`. The Telegram notice is intentionally generic (correct), but the detailed redacted diagnostic the plan requires ("Keep detailed redacted diagnostics in application logs") is never recorded — it is lost at the worker boundary. Add a `logger.exception(...)` in `worker_loop`'s except block (and ideally at the start-endpoint and `_complete_done_run` except blocks) so operators can diagnose stopped cycles.

### 3. Medium — Expired `RUNNING_AGENT` lease is reconciled only at process startup
`reconcile_startup` is the only place that reclaims an expired `running_agent` lease, and it runs once in the lifespan. The worker loop never reclaims. If a model call hangs without crashing the process, the worker is blocked inside `_run_agent_turn`, the lease expires, and nothing reclaims the run until an external restart — the cycle stalls indefinitely. Railway restarts on crash, but a hang does not trigger a restart. Consider a periodic in-worker lease sweep, or a watchdog that reclaims expired `RUNNING_AGENT` leases when no forward progress is observed.

### 4. Low — No-evidence new cycle returns HTTP 202, plan says 200
`cycles.py` returns `created=True, result_code="no_evidence"` for a zero-batch cycle, so `app.py:90` sets 202. The plan's HTTP contract says no-evidence returns 200. The cron trigger treats 200 and 202 identically (`cli.py:367`), so there is no functional impact today, but the contract should match. Either mark no-evidence as not-created, or special-case `result_code == "no_evidence"` to 200.

### 5. Low — `capture_run_baseline` does not verify the checkout matches the remote
`recovery.py:18` asserts writable targets are clean and records `git_base_sha = rev-parse HEAD`, but never compares HEAD to `origin/<branch>`. The plan's batch-baseline section requires "the opinions checkout to match the last successful remote commit." A divergent local HEAD (e.g., the stranded commit in finding 1, or a manual edit) is accepted silently; divergence only surfaces later as a non-fast-forward push failure. Add an `ls-remote` equality check before recording the baseline.

### 6. Low — Lifespan does not clone/fetch the repo; depends on `init-runtime` in the startCommand
`app.py` lifespan does `init_data_dirs`, `mkdir`, and `reconcile_startup`, but never calls `ensure_opinions_repo`. `/healthz` requires `opinions_repo_dir.is_dir()`, and `reconcile_startup` calls `run_git` against that dir. This works on Railway because `railway.toml` runs `init-runtime && serve`, but `serve` alone on a fresh volume never becomes healthy and the lifespan crashes on `run_git`. The plan's recovery-aware startup ordered clone/reconcile inside the startup sequence. Either move the clone/fetch into the lifespan, or document that `serve` requires a prior `init-runtime`.

### 7. Low — `BatchStatus.PENDING` is not in the plan's documented batch enum
The plan lists batch statuses as `queued, running, awaiting_user, stopped, completed`. The code adds `PENDING = "pending"` (`models.py:57`) for not-yet-queued batches. This is reasonable but undocumented — note it in `docs/behavior.md` or align the enum.

### 8. Low — Braintrust keys required unconditionally in prod
`config.py:147` raises in `prod` whenever Braintrust keys are missing. The plan says "Require Braintrust keys when production tracing is enabled," implying tracing is optional. If prod tracing is mandatory, confirm that intent; otherwise gate the check on tracing being enabled.

## Missing or follow-up tests the writer should run

The plan's required-test list is only partly covered. Notable gaps:

- **Crash/recovery:** "Failure after push does not rerun the batch," "Failure before database completion reconciles the remote commit," "Expired running lease stops the cycle and permits retry," "Restart reclaims a queued run," "Restart preserves an awaiting-user run," "Startup does not pull over an active dirty checkout." None of these are exercised. The finding-1 scenario (push failure → retry no-op → stranded commit) is exactly the kind of bug a recovery test would catch.
- **HTTP contract:** 409 (stopped cycle) and 200 (existing/no-evidence) response codes are not asserted; only 401 and 202 are. Cron exit codes for 401/409/network/server failure (`cli.py:366`) are not tested.
- **No-evidence cycle:** "A no-evidence start creates one completed zero-batch cycle" and "The reporting timeline advances only after the final batch" are not tested.
- **Concurrency:** "Cross-week concurrent starts still create only one active cycle" is not tested.
- **Eligibility durability:** "Late new evidence with an old source timestamp enters a later cycle," "Later corpus mutation cannot change a materialized batch," and "Split-document critic context stays fixed and cycle-wide" are not tested. The partition tests cover balance, but not immutability or cross-cycle eligibility.
- **Health:** "Health fails before reconciliation and when PostgreSQL or volume paths fail" is not tested.
- **Methodology full gate:** Run the plan's pre-staging gate — `uv lock --check`, `uv run pytest`, `uv run ruff check .`, `uv run pyright`, and `OPINIONS_RUN_REAL_E2E=1 uv run pytest tests/test_real_e2e_optional.py` — plus the `W04 W10 W12 W13` compatibility screen and one direct-API sample to confirm ThinHarness 0.6.0 critic surfaces behave end-to-end.

A targeted test to add for finding 1: simulate a push failure on a cycle batch (mock `run_git push` to raise once), confirm the run is `FAILED`/cycle `STOPPED`, then run `retry-cycle` and assert the stranded commit is pushed (remote head equals the stranded SHA) rather than a new agent run duplicating or no-op-ing over it.

## Open questions

- Is the caught-push-failure path intended to be operator-retry-only, or should it self-heal like the crash path? The plan reads as the latter (reconcile before re-running), which is why finding 1 is filed as a bug rather than a design choice.
- Should prod require Braintrust keys always, or only when tracing is enabled (finding 8)?
- Is `serve` expected to be runnable without `init-runtime` (finding 6), or is the combined startCommand the only supported entry point?
