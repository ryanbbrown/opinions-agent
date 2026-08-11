# Plan review: deployment readiness (v1)

**Verdict: changes requested**

The plan is unusually complete for a launch plan, and the cycle/batch product model is coherent. The problems are concentrated in recovery, in when batch evidence is materialized, and in a few internally inconsistent numbers that the listed tests would encode as-is.

## Findings

### 1. A restart during an agent turn deadlocks the cycle, and the plan's recovery path cannot clear it

`.plans/deployment-readiness.md:233-234` says restarts preserve run state and `abandon-run` stays the manual escape hatch. The current state machine does not allow that escape. `VALID_TRANSITIONS` (`src/opinions_agent/workflow.py:39-52`) permits `ABANDONED` only from `awaiting_user`, so `abandon_run` (`src/opinions_agent/workflow.py:780-783`) raises `ValueError` for a run left in `running_agent` or `pending_agent`.

A deploy, an OOM kill, or the new `SIGTERM` grace period will leave a run in `running_agent` whenever it lands mid-turn. That run then satisfies `NON_TERMINAL_RUN_STATUSES`, so `find_active_run` (`src/opinions_agent/workflow.py:62-63`) blocks every later batch, and the plan's own rule at line 116 ("Reject retry requests when another run is active") blocks the retry command too. The only remaining fix is a manual `UPDATE` against production PostgreSQL.

Decide and state the recovery contract: either allow `pending_agent`/`running_agent` → `abandoned`, or add a startup sweep that fails orphaned in-flight runs. Automatic batch continuation makes this the single most likely production stall.

### 2. Batch evidence must be materialized at cycle creation, and the plan does not say so

Line 94-95 stores batch definitions in PostgreSQL and evidence bundles on the volume, but never fixes *when* each batch's bundle is written. Two facts make lazy materialization unsafe:

- Document-summary evidence is synthesized, not stored. `_document_summary_evidence` (`src/opinions_agent/selection.py:129-145`) builds rows with `reader-summary:<reader_id>` IDs that never exist in `highlights.jsonl` (behavior contract CORPUS-12). Those IDs cannot be looked up later; they can only be recomputed.
- Recomputation is not stable. `_select_document_summary_evidence` skips any document that has evidence rows (`src/opinions_agent/selection.py:76-83, 112-113`). If a later Reader sync adds one highlight to a summary-only document, that document's summary row stops being generated, and a stored ID in batch 3 becomes unresolvable.

The plan does allow a mid-cycle sync: line 154 syncs Reader on every start request, and line 55 returns the active cycle. A start request during an active cycle therefore mutates the corpus that later batches depend on.

Make this explicit: write every batch bundle to the volume at cycle creation, or skip the Reader sync when the request resolves to an existing active cycle. State whichever you choose, because the "fixed snapshot" guarantee at lines 47-56 depends on it.

### 3. The first production cycle silently drops the entire pre-window corpus

Line 51 sets `window_start` from the previous completed cursor. On a fresh Railway volume there is no cursor, and `_run_window` (`src/opinions_agent/workflow.py:76-79`) falls back to `window_end - 7 days`. The first production sync pulls the full Reader history into an empty corpus, the first cycle covers only the last seven days, and the cursor then advances past everything older. No later cycle can reach that evidence.

The plan has no seeding step for the production volume. Add one: either state the initial cursor explicitly (a launch-time backfill boundary) or copy the existing local corpus and `state.json` onto the volume before the first cycle. The "Railway test deployment" section (lines 325-341) should exercise the same seeding path, otherwise the test proves nothing about launch day.

### 4. The start endpoint runs sync plus a full agent turn inside one HTTP request, with no stated timeout on either side

Line 161 allows the endpoint to block until batch one's Telegram messages are sent. That request contains a full Reader sync, a git clone or pull, and one agent turn that spawns one critic subagent per proposal (`eval/STATUS.md:47`). Minutes, not seconds.

Nothing in the plan bounds it. The cron CLI is the risk: `httpx` defaults to a 5 second timeout, so a naive client fails while the cycle actually starts, and line 186 then reports failure for a successful trigger. Specify the cron client timeout explicitly (the existing `_set_webhook` at `src/opinions_agent/cli.py:328` uses `timeout=20`, still far too short here), and confirm Railway's edge proxy tolerates the duration. If it does not, return after cycle creation and drive batch one from a background task.

### 5. Retrying a failed batch will fail on dirty target files

Line 113 retries a stopped batch from its stored snapshot. Every run start calls `assert_targets_clean` (`src/opinions_agent/workflow.py:100`), which raises when `git status --porcelain` reports any change to the target files (`src/opinions_agent/tools/git_ops.py:44-47`). A batch that fails after the agent edited `OPINIONS.md` but before the commit boundary leaves exactly that state. The retry then aborts immediately, on every attempt.

State what the retry does with the dirty working tree: discard the edits and re-run from the snapshot, or require an explicit operator confirmation before discarding. Note that line 111 ("keep unfinished batch bundles after failure") is about the volume, not the checkout, so it does not cover this.

### 6. Failure text reaches Telegram and the database, and can carry repository credentials

Line 223 forbids printing tokens, repository credentials, and start secrets. The current code sends raw exception text to Telegram (`src/opinions_agent/workflow.py:250`) and stores it in `run.failure_reason` (`src/opinions_agent/workflow.py:776`). `run_git` raises `GitToolError` with git's stderr (`src/opinions_agent/tools/git_ops.py:29-30`), and git echoes the remote URL in many failure messages. Line 209 requires `OPINIONS_REPO_URL` "with push access", which invites an embedded token.

Choose a credential mechanism that keeps the secret out of the URL (a git credential helper or a deploy key), or add an explicit redaction rule for failure text. The plan should say which.

### 7. The batch-count rules are internally inconsistent

- Lines 60-62 use a strict cycle-level trigger (fewer than 20 documents *and* fewer than 50 rows stays one batch) while line 63 uses an inclusive per-batch cap ("at or below both limits"). Line 73 then accepts two batches of 20 documents and 50 rows each — the exact shape that line 61 says must be split when it is the whole cycle. This is defensible, but it is not stated, and the test at line 267 ("Exactly 50 evidence rows triggers at least two balanced batches") sits directly on the boundary.
- Line 64 only covers the two-to-three step. Whole-document grouping plus contiguity can make any small count infeasible: three documents of 30 rows cannot fit in two batches under a 50-row cap. State the rule as "increase the batch count until a feasible partition exists", with one batch per document group as the guaranteed fallback.
- Lines 86-87 allow a segment of exactly 50 rows, but line 63 caps a batch at 50 rows. A maximal segment must therefore be alone in its batch. Say so, otherwise the test at line 272 contradicts the test at line 269.

### 8. `OpinionRun.batch` already exists

Line 141 adds `cycle_batch` and `cycle_batch_count`, but `src/opinions_agent/models.py:59` already has `batch`, and `OpinionProposal.batch` (`src/opinions_agent/models.py:79`) is part of a unique constraint. Neither is written anywhere in `src/`. The project forbids compatibility layers and prefers the simplest implementation, so reuse or remove the existing column rather than adding a parallel one with a different name.

### 9. Cron service gaps

- **Validation scope.** Lines 196-214 apply strict production validation whenever `OPINIONS_ENVIRONMENT=prod`. The cron service runs the same image with no volume and no database. If validation runs on any CLI entry point, the cron container fails before it can post. Scope the validation to the web service explicitly, and list the cron service's own required variables (`OPINIONS_START_URL`, `OPINIONS_START_SECRET`).
- **Restart policy.** `railway.toml:8-9` uses `ON_FAILURE` with 3 retries. A cron service must not inherit that; a rejected start request would retry against the web service. State `restartPolicyType = "NEVER"` for `railway.cron.toml`.
- **Silent stalls.** Line 187 treats an existing active cycle as a successful no-op, and line 26 counts a recoverably failed cycle as active. A cycle that stops on failure therefore produces a green cron run every week, forever, while evidence accumulates. Nothing in the plan notifies the operator: `_fail_run` sends no Telegram message, and a failed Telegram-triggered resume returns 500 to Telegram with no user-visible text. Add an operator notification when a cycle stops, or the automatic-continuation design has no failure signal.

### 10. Smaller items

- **Health check timing.** `railway.toml:6` sets `healthcheckTimeout = 30`. Line 173 runs volume init, repository checkout, and migrations before Uvicorn starts. A cold clone plus migrations can exceed 30 seconds. Raise it and say so.
- **Split documents versus provenance validation.** Lines 86-88 may place one document's segments in different batches. `run_artifact_validation` rejects new source rows whose evidence is outside the current run's bundle (`src/opinions_agent/validation.py:60-66`, behavior contract OPINIONS-14). An opinion drafted in batch 3 cannot cite that document's batch-2 rows. Confirm this is acceptable, or exclude split documents from the "same opinion across batches" expectation.
- **Migration working directory.** `_migrate` builds `Config("alembic.ini")` from a relative path (`src/opinions_agent/cli.py:302`), and `alembic.ini` uses relative `script_location`. Startup must run from the app root. Worth one line in the plan since migrations now gate serving traffic.
- **Webhook secret comparison.** Line 152 requires a constant-time compare for the start secret, but `src/opinions_agent/app.py:37` still compares the Telegram webhook secret with `!=` and skips the check entirely when the secret is empty. Production validation requires the variable, so the bypass is closed, but the two secrets should be handled the same way.
- **`OPINIONS_FAKE_TELEGRAM=0`.** Line 213 requires a literal value. `use_fake_telegram` (`src/opinions_agent/config.py:100`) is truthy only for `1`/`true`/`yes`. Validate "fake Telegram is disabled", not the exact string.
- **Cursor location.** Line 145 puts operational cycle state in PostgreSQL, but the workflow cursor stays in `state.json` on the volume (`src/opinions_agent/workflow.py:742-747`, behavior contract CORPUS-8). Two stores now advance together and can diverge after a restore. If you keep the split, say why.
- **No-evidence cycles.** Line 155 returns "a no-evidence result", but the plan never says whether a cycle row is created, whether the week key is consumed, or whether the cursor advances. All three matter for the following week's window.
- **Behavior contract scope.** Line 253 directs `docs/behavior.md` to gain "production safety contracts". `CLAUDE.md` warns against standalone deployment and runtime sections. Fold the durable parts (cycle ownership, snapshot immutability, cursor advancement, recovery boundaries) into the existing workflow sections instead of adding a deployment section.

### 11. Methodology promotion and the ThinHarness upgrade are bundled without a quality check

`exp/explicit-critic-docscope` pins ThinHarness `v0.5.1`… actually `v0.5.3` (`git show exp/explicit-critic-docscope:pyproject.toml`), and `main` pins `v0.5.1`. Every docscope number in `eval/STATUS.md` was produced on 0.5.3. Line 36 jumps production to 0.6.0 at the same moment the critic lands, and the critic depends on harness subagent APIs (`SubAgentConfig`, `builtin_tools=[..., "subagent"]`).

The Verification block (lines 310-323) is unit tests, lint, typecheck, and one real end-to-end run. `CLAUDE.md` requires prompt-content changes to be verified with sample runs or evals. Add at least one sample run or one screen-subset eval on 0.6.0 before promotion, or split the harness upgrade into its own step.

Two related cautions for the rebuild at line 43: the experiment branch predates `main` on files it also touches. It lacks the `message_id is None` callback guard in `src/opinions_agent/workflow.py:441-443` and lacks the eval cohort flags in `src/opinions_agent/cli.py:75-81`. A file-level copy of `workflow.py`, `cli.py`, or `evals/` silently reverts both. The plan's "Files and modules" list also omits `tests/test_critic.py`, which the branch adds.

## Tests the writer should add or run

- Recovery from an orphaned in-flight run: force a run to `running_agent`, then assert the operator can clear it and that the cycle resumes. This is the gap in finding 1 and no listed test covers it.
- Batch materialization under corpus mutation: create a cycle, sync new Reader rows that add a highlight to a summary-only document, then start batch 2 and assert its evidence matches the snapshot exactly.
- Retry after a batch fails with edited target files still in the working tree.
- First cycle on an empty corpus and empty `state.json`: assert the documented window, not the seven-day fallback by accident.
- Cron CLI against a slow endpoint: assert it waits rather than timing out at the client default.
- Cycle survives a process restart: reload cycle, batch, and cursor state from PostgreSQL and the volume, then continue. The plan claims this at line 15 but lists no test.
- No-evidence start: assert the cycle row, week key, and cursor end state.
- Partition property test: for randomized document sizes, assert every batch respects both caps, every evidence ID appears exactly once, and the batch count is minimal among feasible counts.
- A failure notification test, once finding 9 is resolved.

## Open questions

1. What clears a run left in `running_agent` by a restart, and does that path also unblock the batch retry?
2. Are all batch bundles written at cycle creation, or materialized per batch? If per batch, how are synthesized `reader-summary:` rows rebuilt?
3. What is the initial cursor for the first production cycle, and is the local corpus seeded onto the volume before launch?
4. Does the start request sync Reader before or after it discovers an existing active cycle?
5. Is two batches of exactly 20 documents and 50 rows intended to be legal (line 73) while the same shape as a single cycle is not (line 61)?
6. How does the opinions repository credential reach git without appearing in `OPINIONS_REPO_URL`?
7. Who is notified when a cycle stops, given that the weekly cron reports success either way?

## Residual risks if you ship as planned

The docscope evaluation ran entirely through the local proxy, while production uses the direct OpenAI API — `eval/STATUS.md:47` already flags the backend confound. `opinion-decisions.jsonl` and the opinion ID high-water mark live only on the volume, so volume backups are the sole protection for decision history. And a single replica with one writable checkout means any deploy during an awaiting-user run interrupts a live Telegram conversation.
