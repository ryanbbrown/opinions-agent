# Verdict: changes requested

## Findings

1. **High — Late-synced evidence can be skipped permanently.**
   `.plans/deployment-readiness.md:53` says evidence synced after a snapshot waits for the next cycle. Selection currently uses the evidence creation timestamp (`src/opinions_agent/selection.py:51`). Reader sync can fetch older evidence later (`src/opinions_agent/reader.py:292`). After the cursor advances, that evidence falls before the next window. Track first ingestion or unassigned evidence instead of relying only on source timestamps.

2. **High — The proposed uniqueness constraint does not serialize start side effects.**
   `.plans/deployment-readiness.md:154-157` performs Reader sync and snapshot work before the final duplicate guard. Concurrent requests can both sync the shared JSONL corpus, create bundles, call the agent, and send Telegram messages. Different week keys can also create two active cycles. Reserve one global start operation in PostgreSQL before any side effect.

3. **High — Batch completion is not crash-consistent across git, PostgreSQL, and the volume.**
   The plan requires completed batches to remain completed (`.plans/deployment-readiness.md:99-104`). Current completion commits and pushes before database completion (`src/opinions_agent/workflow.py:203-239`, `src/opinions_agent/tools/git_ops.py:86-89`). A restart after push can cause the batch to run again. Define durable commit intent, store the base and resulting SHA, and reconcile repository state before retry or continuation.

4. **High — Retry does not define how to handle partial edits in the shared checkout.**
   A failed agent can leave `OPINIONS.md`, sources, or decision data modified. The new retry run could inherit those edits or fail the clean-target check. `.plans/deployment-readiness.md:113-116` must define how to archive failed changes and restore the last successful batch state.

5. **High — Restart behavior for in-flight runs remains undefined.**
   `.plans/deployment-readiness.md:227-234` says to preserve run state, but a process can stop while a run is `pending_agent` or `running_agent`. No request will automatically reclaim that run after startup. Define leases or startup reconciliation. Specify whether the app resumes the turn or marks the batch retryable.

6. **Medium — No-evidence cycles have ambiguous idempotency and cursor behavior.**
   The endpoint can return a no-evidence result (`.plans/deployment-readiness.md:155`), but the plan does not say whether it persists a cycle. Without a durable record, another same-week request can create a different snapshot. The plan must also decide whether a no-evidence cycle advances the workflow cursor.

7. **Medium — Staging and production validation requirements conflict.**
   `.plans/deployment-readiness.md:199-214` requires `OPINIONS_TARGET_FILE=OPINIONS.md` on Railway. The staging checklist requires a disposable file at line 332. If strict validation applies only to production, staging can use the real repository default from `src/opinions_agent/config.py:88`. Define shared Railway checks and separate environment-specific repository checks.

8. **Medium — Oversized-document batching weakens the document-scope critic.**
   `.plans/deployment-readiness.md:86-88` splits one document across batches. The critic receives only uncited selected rows from its run (`.plans/deployment-readiness.md:38-42`). An argument spanning two segments loses same-document context. Define whether the critic receives cycle-wide context and how cross-segment evidence supports provenance.

9. **Low — The model settings can still ignore `.env`.**
   Current model constants load before `load_dotenv()` (`src/opinions_agent/config.py:7-8,75-84`). Merely adding variables to `.env.example` will not make local overrides work. Read model and effort through `Settings`, then use those fields in the harness.

## Missing or follow-up tests

The writer should add and run tests for:

- Evidence fetched after a snapshot with an older source timestamp entering the next cycle.
- A late note or update to old evidence entering a later cycle.
- Concurrent same-week and cross-week starts causing one sync, cycle, run, and Telegram send.
- Process failure after bundle creation, local commit, push, database completion, and Telegram send.
- Restart recovery for pending, running, awaiting-user, and commit-in-progress runs.
- Retry after the agent leaves dirty opinion artifacts.
- Repeated no-evidence starts and the following cycle’s window.
- Staging rejection of production repository defaults.
- An oversized document whose argument crosses segment boundaries.
- Model and reasoning overrides loaded from `.env`.

## Open questions

- Does selection ownership use source timestamps, first-ingestion time, or an explicit unassigned-evidence ledger?
- Should a no-evidence request create a completed zero-batch cycle and advance the cursor?
- Should an interrupted running turn resume automatically or require an operator retry?