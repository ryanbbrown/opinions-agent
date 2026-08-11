# Plan review: deployment-readiness (v1)

**Verdict: changes requested**

The plan is thorough and the product behavior is mostly internally consistent. A few issues need resolution before implementation because they affect correctness of the deployed workflow or risk breaking the methodology-validation harness the deployment depends on.

## Findings (ordered by severity)

### 1. Eval and sample-run paths are not reconciled with the cycle-start operation (high)
`src/opinions_agent/workflow.py:82` (`start_opinion_run`) is the entry point for `opinion-run`, `sample-run`, `sample-session` (`cli.py:139,188,252`), and the eval runner (`evals/runner.py:281`). The plan says the HTTP endpoint and `opinion-run` route through "the same cycle-start operation," which "syncs Reader, selects the fixed snapshot, creates the cycle, and starts batch one" (lines 154, 159).

The eval runner seeds its own corpus and does **not** sync Reader, runs many weeks concurrently on disposable per-case databases, and passes explicit week windows. If the shared cycle-start operation always syncs Reader and imposes UTC-week-key cycle idempotency plus "one active run blocks later batches," the eval harness that validates the very methodology being deployed breaks. The plan never mentions `eval run`, `sample-run`, or `sample-session`. It must state either that those keep a run-only path (no cycle, no sync), or specify how cycle creation composes with disposable seeded corpora and explicit windows.

### 2. Dirty opinions checkout on restart is unspecified (medium)
The plan says "Make `init-runtime` safe to run on every web-service start" and "Preserve current run state when the service restarts" (lines 227, 233). The start command runs `init-runtime` then `serve` (line 174), and `init-runtime` calls `ensure_opinions_repo` (`cli.py:111`), which runs `git checkout <branch>` + `git pull --ff-only` (`repo_checkout.py:12-14`).

On a restart while a run is `AWAITING_USER` or `RUNNING_AGENT`, the checkout may have uncommitted opinion edits that the agent wrote but the app has not committed. `git pull --ff-only` on a dirty tree fails or conflicts. The plan does not define the safe behavior. It should specify: skip fetch/pull when a run is active or the tree is dirty, or only assert the checkout exists. Without this, a restart mid-run can corrupt the in-flight run.

### 3. Workflow cursor storage location is ambiguous (medium)
The plan says "Keep operational cycle state in PostgreSQL. Keep corpus and run evidence on the volume" (line 145) and "preserve every ... cursor ... across restarts" (line 15). But the workflow cursor currently lives in `state.json` on the volume (`corpus.py:28,104-106`; advanced at `workflow.py:742-747`). The plan never says whether the cursor moves into PostgreSQL (e.g., derived from the latest completed `OpinionCycle.window_end`) or stays on the volume.

If it stays on the volume, volume loss resets the cursor and the next cycle defaults to a seven-day window, reprocessing evidence. The plan should state where the cursor lives and confirm it is covered by volume backups or derived from PostgreSQL so the "preserve cursors" goal holds under volume loss.

### 4. Single-document 50-row partition contradiction (medium)
Split trigger: "at least 50 evidence rows must use at least two batches" (line 61). No-split rule: "keep all evidence from one document in the same batch when that document has 50 rows or fewer" (line 79). Oversized rule: split only when a document has "more than 50 evidence rows" (line 86).

A cycle with one document of exactly 50 rows must use ≥2 batches (trigger) but cannot be split (no-split, and oversized requires >50). The spec is unsatisfiable at that boundary. The plan should resolve it — e.g., split at ≥50, exempt single-document cycles, or change the trigger to "more than 50." The partition tests (lines 262-272) do not cover this case.

### 5. Within-document segment splitting is underspecified (medium)
For a document with >50 rows the plan says "split only that document into chronological segments. Keep each segment at or below 50 evidence rows" (lines 86-87). It does not say how to size segments, how segment boundaries participate in the imbalance-minimization pass (lines 82-84), or how segments are ordered against other document groups. The completion criterion "deterministic balanced batches" (line 363) and the partition tests need this algorithm pinned down, or two implementers will produce different batchings.

### 6. Cron-service environment requirements are not enumerated (medium)
The cron service needs `OPINIONS_START_URL` and `OPINIONS_START_SECRET` (lines 183-184), but the "Require these values on Railway" list (lines 199-214) is the web-service list only and omits `OPINIONS_START_URL` entirely. There is no cron-service env list. At deploy time `OPINIONS_START_URL` is easy to miss. Add a cron-service required-env section.

### 7. Startup health-check timing vs. cold start (medium)
The start command is `init-runtime && serve` (line 174). During `init-runtime` (volume mkdir, git clone/checkout, Alembic upgrade) Uvicorn is not listening, so Railway `/healthz` probes fail. The current `healthcheckTimeout = 30` with `restartPolicyMaxRetries = 3` (`railway.toml:7-9`) can kill a slow cold start before Uvicorn binds. The plan addresses shutdown grace (line 232) but not startup probe timing. It should raise the timeout, use a startup probe, or state that `init-runtime` must complete within the window.

### 8. `OpinionRun.batch` vs. new `cycle_batch` is unreconciled (low)
`OpinionRun.batch` exists today (`models.py:59`) and participates in the `opinion_proposals` unique constraint (`models.py:75`). The plan adds `cycle_id`, `cycle_batch`, `cycle_batch_count` (line 141) without saying whether `batch` is repurposed as the cycle-batch number or kept as a separate per-run proposal batch. With no backwards-compatibility requirement, pick one and state it, to avoid two competing batch fields.

### 9. Start-endpoint blocking duration is ambiguous (low)
"The endpoint may wait until batch one's initial Telegram messages are sent" (line 161) versus the cron service "exits after the web service accepts or rejects the start request" (line 186). If "accepts" means the first LLM turn reaches `awaiting_user`, the cron request is long-lived and may exceed Railway's cron-job max duration. Clarify whether the endpoint returns after cycle creation (fast) or after the first turn completes (slow), and how the cron handles a slow turn.

### 10. `opinion-run` active-cycle behavior changes the local contract (low)
If `opinion-run` routes through cycle-start and cycle-start returns the active cycle as a no-op (line 155), the existing contract `test_active_run_blocks_new_run` (`tests/test_workflow.py:91-96`) and local dev behavior change from "refuses" to "no-op." The plan should state whether the no-op-on-active behavior applies to `opinion-run` or only to the HTTP start.

### 11. Railway schema validation method is unspecified (low)
The plan says "validate both Railway config files against Railway's current JSON schema" (line 323) but names no tool or command. The writer should specify how (for example `railway up --dry-run` or a documented linter) so the verification step is reproducible.

## Missing or follow-up tests the writer should run
- Partition: single document with exactly 50 rows (once finding 4 is resolved), and a single document with >50 rows covering segment sizing and determinism (finding 5).
- Restart-during-`AWAITING_USER`: run `init-runtime` against a checkout with uncommitted opinion edits; assert the tree is not clobbered and the run can resume (finding 2).
- Cross-batch opinion-ID high-water: batch 2 does not reuse IDs allocated by batch 1; verify against `read_opinion_id_high_water` and the baseline doc.
- Cursor durability after restart/volume-loss, wherever the cursor ends up living (finding 3).
- Cron CLI with a slow start endpoint: confirm exit code when the request exceeds the cron job's max duration (finding 9).
- Eval runner regression: `eval run` still produces per-week runs on disposable DBs without syncing Reader and without cycle idempotency blocking concurrent cases (finding 1).

## Open questions
- Does the workflow cursor move to PostgreSQL (derived from the latest completed cycle) or remain in `state.json` on the volume? (finding 3)
- Does the start endpoint return after cycle creation or after batch one's first turn completes? (finding 9)
- Do `eval run`, `sample-run`, and `sample-session` keep a run-only path, or do all route through cycle-start with mandatory Reader sync? (finding 1)

## Residual risks (not blockers)
- A failed cycle blocks all future weekly cycles until an operator runs the retry command (lines 109-116); the plan has no alerting. If the operator does not notice, weekly triggers accumulate as no-ops and the evidence window grows. Acceptable given the retry mechanism, but worth a monitoring note.
- ThinHarness 0.6.0 is a version bump from 0.5.1 (`pyproject.toml:20`) and the plan relies on the current `HarnessConfig`/`NativeOutput`/`ToolSpec` API (`agent.py:139-181`). The verification gate (pyright + tests) should catch breakage, but the plan does not call out verifying the 0.6.0 API surface explicitly.
- Single replica with a writable volume checkout means a redeploy can briefly overlap old and new replicas touching the same volume. Railway's one-replica deploy usually serializes this, but the plan does not address overlap during deploys.
