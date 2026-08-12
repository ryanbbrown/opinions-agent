# Deployment readiness

**Status: implemented locally. Railway staging and production deployment remain.**

## Goal

Prepare the finalized opinion methodology for a safe Railway launch.

The deployed system must:

- use the document-scope critic on `openai:gpt-5.6-sol` at medium effort;
- divide a large weekly evidence set into balanced runs;
- continue the runs automatically after each successful Telegram review;
- keep the weekly schedule separate from Telegram resume handling;
- survive duplicate starts, restarts, and partial failures without losing evidence; and
- pass a disposable Railway run before the real opinions repository is enabled.

Memory automation, `trace_read_policy`, and `section_quality` remain post-launch work.

## Terms

- A **cycle** is the fixed evidence snapshot created by one weekly start.
- A **batch** is one balanced part of a cycle.
- A **run** is one agent conversation for one batch.
- The **web service** stays running and receives Telegram and weekly start requests.
- The **cron service** starts once a week, asks the web service to start, and exits.
- A **fingerprint** is a stable hash of the evidence fields the agent can read.
- An **evidence version** is an evidence ID plus its fingerprint.
- A **lease** is a database ownership record that expires if its process stops.
- **Duplicate-safe** means repeated requests return the existing work instead of creating new work.

## Final decisions

### Methodology

- Integrate `exp/explicit-critic-docscope` into `main`.
- Use `openai:gpt-5.6-sol` with medium reasoning effort by default.
- Upgrade ThinHarness from 0.5.1 to 0.6.0.
- Run one critic subagent for each proposed opinion.
- Give the critic the cited rows and the fixed same-document context from the cycle.
- Let the critic request missing concepts.
- Do not let the critic rewrite text, remove concepts, or inspect unrelated documents.
- Rebuild source changes by hunk against current `main`.
- Do not copy whole experiment files over current `workflow.py`, `cli.py`, or eval modules.
- Do not merge `.runs-smoke/`, old lock files, or stale eval infrastructure.
- Add the experiment branch's critic tests and adapt them to ThinHarness 0.6.0.
- Record the production decision in `eval/STATUS.md` and `eval/experiments.md`.

### Cycle trigger

- A weekly start request reserves one cycle before it syncs Reader or writes bundles.
- The cycle's UTC week key makes repeated weekly requests return the same cycle.
- An unfinished earlier cycle blocks a new cycle.
- A normal unfinished cycle returns a successful no-op to cron.
- A stopped cycle returns a failure to cron and tells the operator how to retry it.
- A start request for an existing cycle does not sync Reader again.
- The cycle end is fixed when the reservation succeeds.
- A cycle never accepts more evidence after its snapshot is written.

### Split trigger

- Use one batch only when the cycle has fewer than 20 documents and fewer than 50 evidence rows.
- A cycle with at least 20 documents or at least 50 evidence rows uses at least two batches.
- Every batch has at most 20 distinct documents and at most 50 evidence rows.
- Increase the batch count until a legal balanced partition exists.
- Count Reader highlights, document notes, and synthesized document summaries as evidence rows.
- Count evidence after backfill exclusion and summary synthesis.

Examples:

- 19 documents and 49 rows produce one batch.
- 20 documents and 40 rows produce two balanced batches.
- 10 documents and 50 rows produce two batches near 25 and 25.
- 10 documents and 51 rows produce two batches near 25 and 26.
- 41 documents require at least three batches.
- 101 rows require at least three batches.

### Balanced partition

1. Sort evidence by source timestamp, then evidence ID.
2. Group rows by document and order groups by their first evidence row.
3. Calculate the smallest legal batch count, with two as the minimum after a split trigger.
4. Calculate equal evidence-row targets for that batch count.
5. Use a dynamic-programming search, which compares legal boundaries without brute-force enumeration.
6. Rank partitions by evidence-row balance, then document-count balance, then stable boundary IDs.
7. Accept the best whole-document partition when every batch stays within both hard limits.
8. Also require each batch to stay between half and one-and-a-half times its equal row target.
9. If no partition qualifies, split the blocking document at the row nearest the equal target.
10. Search again after adding the document segments.
11. Increase the batch count when no legal partition exists at the current count.

This rule keeps documents whole when the result remains reasonably balanced. It prevents one large batch followed by one tiny batch.

- A 23-row and 27-row split is acceptable for a 50-row cycle.
- A 45-row and 5-row split is not acceptable. Split the blocking document instead.
- One document with exactly 50 rows splits near 25 and 25.
- A document segment with 50 rows must be alone because the row limit is 50.
- A split document can appear in adjacent batches.
- Each batch counts the split document once toward its document limit.

### Automatic continuation

- Materialize every batch before the first agent run starts.
- Start one run at a time.
- Batch one enters a durable queue after cycle creation.
- A web-service worker claims queued runs and sends the initial Telegram messages.
- Telegram callbacks, replies, `GO`, and `SKIP` resume the current run as they do now.
- A successful batch commits and pushes its accepted changes before the next batch starts.
- The next batch runs against the opinion files produced by the earlier batch.
- Batch completion queues the next batch and lets the Telegram request return.
- The worker starts the queued batch automatically.
- The cycle completes only after every batch succeeds.

## Evidence ownership and fixed snapshots

### Assignment ledger

PostgreSQL becomes the authority for cycle progress and evidence ownership.

- Store one assignment for each evidence version selected by a cycle.
- Fingerprint the fields the agent can read, including text, notes, and summaries.
- A material content change creates a new evidence version.
- A newly synced evidence version remains eligible even when its source timestamp is old.
- An assignment to an unfinished cycle stays with that cycle until recovery completes.
- A completed assignment is never selected again unless the evidence fingerprint changes.
- Remove the workflow cursor from `state.json` as an ownership mechanism.
- Keep Reader sync watermarks in `state.json`.
- Derive the reporting window start from the last completed cycle in PostgreSQL.

This prevents late Reader data from falling behind a timestamp cursor.

### First production cycle

- Require `OPINIONS_INITIAL_EVIDENCE_AFTER` before the first production cycle.
- The value is the earliest source timestamp included at launch.
- The first sync may fetch all Reader history.
- Record older evidence versions as `baseline_ignored` after that first sync.
- Select unassigned evidence versions at or after the launch boundary.
- Keep the launch boundary immutable after the first cycle is reserved.
- Set and test the same boundary in the Railway staging environment.

This prevents the first deployment from processing all history or silently losing the intended launch week.

### Immutable cycle files

- Write every batch's selected evidence and selected documents at cycle creation.
- Write fixed same-document context for the critic at cycle creation.
- Store cycle files under `RUNS_DIR/active/<cycle_id>/batches/<batch_number>/`.
- Point each run at its existing batch files.
- Never reconstruct later batches from the mutable corpus.
- Keep context-only rows separate from citable selected evidence.
- Let the critic read fixed cycle-wide context for a document split across batches.
- Keep provenance validation limited to the current batch's citable selected evidence.
- Move the whole cycle directory to `completed/` after the final batch.

### No-evidence cycle

- Persist a completed zero-batch cycle.
- Consume the UTC week key.
- Advance the reporting timeline to the fixed cycle end.
- Keep later unassigned evidence eligible, even when its source timestamp predates that end.
- Return a successful no-evidence response to cron.

## Durable data model

Add normalized PostgreSQL tables instead of storing mutable batch state in one JSON field.

### `opinion_cycles`

- cycle ID;
- unique UTC week key;
- status: `starting`, `active`, `stopped`, or `completed`;
- fixed window start and end;
- initial evidence boundary when applicable;
- total document, evidence, and batch counts;
- current batch;
- sanitized failure code and summary; and
- timestamps.

### `opinion_batches`

- cycle ID and one-based batch number, unique together;
- status: `queued`, `running`, `awaiting_user`, `stopped`, or `completed`;
- ordered evidence IDs and fingerprints;
- ordered document IDs;
- immutable bundle path;
- evidence and document counts;
- latest run ID;
- successful run ID; and
- timestamps.

### `opinion_evidence_assignments`

- evidence ID and content fingerprint, unique together;
- disposition: `baseline_ignored` or `cycle`;
- cycle ID and batch number when selected; and
- assignment timestamp.

### `workflow_leases`

- unique lease name;
- owner token;
- expiry timestamp; and
- updated timestamp.

### Existing run tables

- Add `cycle_id` and `batch_count` to `OpinionRun`.
- Reuse `OpinionRun.batch` as the cycle batch number.
- Remove the unused `OpinionProposal.batch` column and its old unique constraint.
- Keep proposal IDs unique within one run.
- Add run lease fields and git durability fields described below.
- Use a new Alembic migration. Do not edit migration `0001`.

## Start serialization and background work

### Global start lease

- Acquire one PostgreSQL-backed start lease before Reader sync or filesystem writes.
- Let only the lease owner reserve a new cycle.
- Give the lease an expiry and owner token so a crashed start can be reclaimed.
- Check for an existing week key and unfinished cycle while holding the lease.
- Reserve the cycle before sync.
- Sync Reader, assign evidence, partition it, and write all bundles.
- Queue batch one, then release the lease.
- Use the cycle week constraint as a second duplicate guard.
- Test same-week and cross-week concurrent requests.

### Web-service worker

- Start one worker in the FastAPI lifespan.
- Use a database lease when the worker claims a queued run.
- Wake the worker after cycle creation and successful batch completion.
- Scan for queued work at startup so a restart cannot lose a queue signal.
- Return the start HTTP response after the snapshot and bundles are durable.
- Do not wait for the first model turn in the cron request.
- Keep one web replica and disable deployment overlap.

The cron request covers Reader sync and snapshot creation, but no model call. Give the cron client a ten-minute timeout and verify it in staging.

### Restart states

- Reclaim `pending_agent` runs through the worker.
- Keep `awaiting_user` runs available for normal Telegram resume.
- Treat an expired `running_agent` lease as an interrupted model call.
- Do not assume an interrupted model call can resume safely.
- Reconcile git state, archive partial edits, restore the batch baseline, and stop the cycle.
- Send one generic Telegram failure notification with a stable duplicate key.
- Let the operator retry the stopped batch.
- Allow `abandon-run` for pending and running runs when automatic reconciliation cannot finish.
- Reconcile commit phases automatically before deciding that a run is interrupted.

## Git durability and retry

### Batch baseline

Before each run starts:

- require the opinions checkout to match the last successful remote commit;
- record the base commit SHA;
- copy `OPINIONS.md`, `OPINIONS_SOURCES.jsonl`, and `opinion-decisions.jsonl` into the batch recovery area; and
- copy the opinion-ID high-water file into the recovery area; and
- require the configured writable files to be clean.

### Commit phases

Store these phases on the run:

1. `agent_editing`;
2. `commit_intent`, with run ID and base SHA;
3. `committed`, with local result SHA;
4. `pushed`, after the remote contains the result SHA; and
5. `completed`, after PostgreSQL and cycle artifacts are final.

- Use a deterministic commit message containing the run ID.
- Persist commit intent before creating the commit.
- Persist the local SHA before pushing.
- Confirm the remote contains that SHA before recording `pushed`.
- Queue the next batch only after `pushed` and database completion.
- On restart, inspect the base SHA, local HEAD, remote branch, and stored phase.
- Complete a partially recorded push when the remote already contains the result SHA.
- Recompute and persist the opinion-ID high-water mark from the pushed opinion file during reconciliation.
- Record and reconcile the decision-log content hash with the run phase.
- Never rerun a batch whose pushed commit can be reconciled.

### Failed edits

- Save a patch and copies of changed writable artifacts in the recovery area.
- Restore the three writable artifacts to their recorded baseline before retry.
- Keep the archived failed edits for inspection.
- Do not use destructive repository-wide reset commands.
- A retry creates a new run for the same stored batch.
- Keep the failed run as audit history.
- Reject retry while another run is active.
- Resume automatic continuation only after the retry succeeds.

### Repository credentials and errors

- Keep `OPINIONS_REPO_URL` free of credentials.
- Store a fine-grained GitHub token in `OPINIONS_GIT_TOKEN`.
- Supply the token to git through a noninteractive credential helper or `GIT_ASKPASS`.
- Never persist the token in `.git/config`, command arguments, or logs.
- Redact secrets and credential-bearing URLs from stored and displayed failures.
- Send generic operational failures to Telegram.
- Keep detailed redacted diagnostics in application logs.

## Run-only development paths

- Keep `start_opinion_run` as the low-level run-only operation.
- Keep `sample-run`, `sample-session`, and `eval run` on the run-only path.
- Do not sync Reader or enforce the weekly duplicate guard inside disposable eval cases.
- Keep explicit eval windows and concurrent disposable databases working.
- Keep `opinion-run` as the existing manual one-run command.
- Add `opinion-cycle` for local testing of the production cycle behavior.
- Use the cycle operation only for `opinion-cycle` and the internal HTTP start endpoint.

## HTTP and Railway

### Web service endpoint

Add `POST /internal/opinion-cycle/start`.

- Require `Authorization: Bearer <OPINIONS_START_SECRET>`.
- Compare the start and Telegram webhook secrets with `secrets.compare_digest`.
- Return HTTP 202 after a new cycle and its bundles are durable.
- Return HTTP 200 for same-week, active, completed, and no-evidence results.
- Return HTTP 409 for a stopped cycle that needs operator recovery.
- Return a small response with cycle ID, status, batch count, and result code.
- Do not return evidence text, paths, tokens, or raw failures.

### Web service configuration

- Use one replica.
- Attach one persistent volume.
- Set deployment overlap to zero.
- Keep corpus, cycle bundles, recovery files, and repository checkout under the volume.
- Use Railway PostgreSQL for operational state.
- Remove the unsupported `[[services]]` block from `railway.toml`.
- Use Railway's current `RAILPACK` builder.
- Start from the repository root.
- Run `uv run opinions-agent init-runtime && uv run opinions-agent serve`.
- Resolve Alembic configuration from the project root instead of the caller's current directory.
- Raise the Railway health timeout from 30 seconds to at least 300 seconds.
- Add a 30-second shutdown grace period.
- Keep `/healthz` read-only.
- Make health require a PostgreSQL response, required volume paths, and completed startup reconciliation.

### Recovery-aware startup

Run startup in this order:

1. validate web-service configuration;
2. create volume directories;
3. run database migrations;
4. inspect active cycles, runs, leases, and commit phases;
5. clone the repository only when it is missing;
6. reconcile an active checkout without pulling over in-flight edits;
7. fetch and fast-forward only when no active work or recovery state exists;
8. reconcile queued and interrupted work; and
9. start the web server and worker.

### Cron service

- Deploy the same repository as a second Railway service without a volume.
- Give it `railway.cron.toml`.
- Add a small `cron-trigger` CLI command.
- Require only `OPINIONS_START_URL` and `OPINIONS_START_SECRET` in that command.
- Do not load web-service production validation for the cron command.
- Post once with a ten-minute client timeout.
- Exit zero for 200 and 202 results.
- Exit nonzero for 401, 409, network failure, and server failure.
- Use `restartPolicyType = "NEVER"`.
- Configure one weekly UTC cron schedule in Railway.
- Choose the weekday and time during Railway setup.

The cron service never runs the opinion agent. It only asks the web service to create a cycle.

## Configuration validation

### All Railway web environments

Require explicit values for:

- `OPINIONS_ENVIRONMENT`, set to `staging` or `prod`;
- PostgreSQL `DATABASE_URL`;
- `RAILWAY_VOLUME_MOUNT_PATH`;
- `READWISE_TOKEN`;
- `TELEGRAM_BOT_TOKEN`;
- `TELEGRAM_ALLOWED_CHAT_ID`;
- `TELEGRAM_WEBHOOK_SECRET`;
- `OPINIONS_START_SECRET`;
- `OPENAI_API_KEY`;
- `OPINIONS_REPO_URL` without credentials;
- `OPINIONS_GIT_TOKEN`;
- `OPINIONS_REPO_BRANCH`;
- `OPINIONS_TARGET_FILE`;
- `OPINIONS_SOURCES_FILE`;
- `OPINIONS_INITIAL_EVIDENCE_AFTER`; and
- disabled fake Telegram and local plaintext tracing.

Require Braintrust keys when production tracing is enabled.

### Production-only rules

- Require `OPINIONS_TARGET_FILE=OPINIONS.md`.
- Require `OPINIONS_SOURCES_FILE=OPINIONS_SOURCES.jsonl`.
- Reject test filenames and fake Telegram.

### Staging-only rules

- Require `OPINIONS_TARGET_FILE=TEST_OPINIONS.md`.
- Use a disposable repository or branch.
- Use separate PostgreSQL and volume resources.
- Never reuse the production Git token.

### Model settings

- Load `.env` before resolving model and reasoning settings.
- Read both values through `Settings`.
- Make every run record `settings.harness_model`.
- Add the final defaults to `.env.example`.

## Failure visibility

- Send one generic Telegram message when a cycle stops.
- Include cycle ID, batch number, failure code, and retry command.
- Never include exception text or credentials.
- Use a stable duplicate key so restart reconciliation cannot send duplicates.
- Make a weekly cron request fail while a stopped cycle remains unresolved.
- Log successful no-ops for normal awaiting-user cycles.

## Behavior and documentation

Update `docs/behavior.md` before implementation.

- Extend existing run selection, Telegram, git, and corpus sections.
- Define cycle ownership, immutable snapshots, assignment, batching, and cursor replacement.
- Define automatic continuation and recovery boundaries.
- Define which state belongs in PostgreSQL and which files belong on the volume.
- Do not add a standalone deployment checklist to the behavior contract.

Update `README.md` with:

- cycle and retry commands;
- web and cron service setup;
- first-cycle boundary selection;
- staging and production variables;
- GitHub token setup;
- Telegram webhook setup;
- volume backups;
- Railway config validation; and
- staging promotion steps.

## Implementation phases

### 1. Final methodology and dependency

- Integrate final rules, prompts, critic tool, and critic tests by hunk.
- Upgrade ThinHarness to 0.6.0 and inspect its current types before adapting code.
- Fix model setting resolution.
- Run focused agent, prompt, validation, and eval tests.
- Run one direct-API sample and the `W04 W10 W12 W13` compatibility screen.
- Treat this as a compatibility check, not a new methodology search.

### 2. Behavior contract and durable schema

- Update `docs/behavior.md` with the reviewed behavior.
- Add cycle, batch, assignment, lease, and run durability fields through Alembic.
- Remove obsolete cursor and proposal-batch paths.
- Run migration, model, corpus, and state tests.

### 3. Assignment and balanced partition

- Add evidence fingerprints and baseline assignment.
- Add the deterministic partitioner.
- Materialize every immutable batch and critic context file.
- Run partition property tests and fixed-snapshot tests.

### 4. Cycle worker and recovery

- Add cycle start serialization, run claims, automatic continuation, and cursor replacement.
- Add git phases, startup reconciliation, failure archives, retry, and operator notifications.
- Preserve existing Telegram duplicate handling.
- Run workflow, crash-point, retry, and end-to-end tests.

### 5. Railway surfaces

- Add the internal start endpoint and cron trigger command.
- Add strict web validation and narrow cron validation.
- Fix health, startup order, shutdown timing, and Railway configs.
- Update `.env.example` and `README.md`.
- Validate both Railway files against Railway's published JSON schema.

### 6. Staging and production

- Run the complete local verification gate.
- Deploy staging with disposable resources.
- Complete one real Telegram cycle.
- Test same-week duplicate start and stopped-cycle reporting.
- Enable backups.
- Promote only the tested commit and configuration shape to production.

Every phase ends with passing focused tests before the next phase begins.

## Required tests

### Partition and assignment

- 19 documents and 49 rows stay in one batch.
- Exactly 20 documents trigger two balanced batches.
- Exactly 50 rows trigger two balanced batches.
- One document with exactly 50 rows splits near 25 and 25.
- 51 rows split near 25 and 26 when boundaries allow it.
- 41 documents and 101 rows require at least three batches.
- A 45-and-5 whole-document result splits the blocking document.
- A 23-and-27 whole-document result stays whole.
- Randomized document sizes satisfy both caps and minimal feasible batch count.
- Every evidence version appears exactly once.
- Material changes create a new eligible fingerprint.
- Late new evidence with an old source timestamp enters a later cycle.
- Later corpus mutation cannot change a materialized batch.
- Split-document critic context stays fixed and cycle-wide.

### Cycle and concurrency

- One weekly start freezes all bundles and queues only batch one.
- Two same-week starts create one sync, cycle, run, and Telegram sequence.
- Cross-week concurrent starts still create only one active cycle.
- Same-week retries return the existing cycle without another sync.
- A no-evidence start creates one completed zero-batch cycle.
- New evidence after snapshot waits for the next cycle.
- Batch completion queues the next batch automatically.
- Later batches see opinion commits and opinion-ID high-water changes from earlier batches.
- The reporting timeline advances only after the final batch.
- `sample-run`, `sample-session`, and concurrent eval cases remain run-only.

### Crash and recovery

- Restart reclaims a queued run.
- Restart preserves an awaiting-user run.
- Expired running lease stops the cycle and permits retry.
- Failure after bundle creation preserves assignments and bundles.
- Failure after agent edits archives and restores writable files.
- Failure after local commit reconciles through run ID and SHA.
- Failure after push does not rerun the batch.
- Failure before database completion reconciles the remote commit.
- Retry uses the stored batch and never repeats completed batches.
- Startup does not pull over an active dirty checkout.
- Repeated recovery sends one failure notification without raw exception text.

### HTTP, configuration, and Railway

- Start and Telegram webhook secrets use constant-time comparison.
- Start endpoint returns the defined 200, 202, 401, and 409 results.
- Cron trigger waits for a slow snapshot within its explicit timeout.
- Cron trigger maps response classes to correct exit codes.
- Cron command needs no database, volume, Reader, Telegram, or model settings.
- Shared, staging, and production validation reject unsafe values independently.
- Model and reasoning overrides load from `.env`.
- Health fails before reconciliation and when PostgreSQL or volume paths fail.
- Railway configs validate against the current published schema.
- Cold startup has enough health-check time for clone and migration.

### Methodology and full gates

- ThinHarness 0.6.0 critic tools expose only the intended surfaces.
- One critic call runs for each proposal.
- The critic receives cited rows and fixed same-document context.
- Direct-API sample and screen runs complete without harness regressions.
- The optional real agent end-to-end test passes through direct OpenAI access.

Run before staging:

```bash
uv lock --check
uv run pytest
uv run ruff check .
uv run pyright
OPINIONS_RUN_REAL_E2E=1 uv run pytest tests/test_real_e2e_optional.py
```

## Railway staging run

- Create or recover the Railway account.
- Connect this GitHub repository.
- Create staging web, cron, PostgreSQL, and volume resources.
- Use a disposable opinions repository and a separate Git token.
- Set `OPINIONS_ENVIRONMENT=staging` and `OPINIONS_TARGET_FILE=TEST_OPINIONS.md`.
- Choose an explicit first evidence boundary.
- Generate the web domain and register the Telegram webhook.
- Trigger the same cron command Railway will schedule.
- Complete every Telegram batch.
- Verify commits, sources, decisions, cycle state, assignments, and completed bundles.
- Trigger the same week again and verify no duplicate cycle appears.
- Exercise one stopped-cycle notification and retry in staging.
- Enable volume backups.

## Production launch

- Create production web, cron, PostgreSQL, and volume resources.
- Configure the final weekly UTC schedule.
- Use the production repository, target files, and dedicated Git token.
- Choose and record the first production evidence boundary.
- Register the production Telegram webhook.
- Enable volume backups.
- Deploy the staging-tested commit.
- Verify health, startup reconciliation, Braintrust traces, cron logs, Telegram messages, and repository writes.

## Completion criteria

- `main` contains the finalized methodology without experiment artifacts.
- ThinHarness 0.6.0 passes local, direct-API, and staging checks.
- Weekly starts are duplicate-safe and serialized before side effects.
- Large snapshots produce deterministic balanced batches.
- All batch bundles exist before the first run.
- Successful batches continue automatically and in order.
- Late evidence is not lost behind a timestamp cursor.
- Partial failure cannot duplicate a pushed batch or lose unfinished evidence.
- Stopped cycles notify the operator and can be retried.
- Railway cron only triggers the persistent web service.
- Unsafe production configuration prevents startup.
- A disposable Railway cycle succeeds before production is enabled.

## Review record

One panel reviewed the first draft on 2026-08-11:

- `.reviews/plans/deployment-readiness/deployment-readiness-codex-v1.md`
- `.reviews/plans/deployment-readiness/deployment-readiness-claude-v1.md`
- `.reviews/plans/deployment-readiness/deployment-readiness-glm-5p2-v1.md`

This revision incorporates the actionable findings. No second review round is planned.
