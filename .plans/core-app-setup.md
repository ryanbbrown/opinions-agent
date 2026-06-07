# Core App Setup Plan

## Goal

Build the non-agent application shell for `opinions-agent`, leaving the opinion-generation agent logic as a replaceable box. The first working vertical slice should use real Readwise highlights, run a dummy ThinHarness agent that summarizes the N most recent highlights, ask for Telegram approval, then append the approved summary to a test opinions file and commit/push that file to `main`.

## Decisions From Interview

- Hosting target: Railway.
- Build locally first, but keep the app Railway-shaped from day one.
- Database: PostgreSQL locally and on Railway, selected through `DATABASE_URL`.
- Local PostgreSQL should run through Docker Compose.
- Railway PostgreSQL is acceptable for this project.
- Include Railway config immediately.
- Scheduling default: daily.
- Readwise should use the real API immediately.
- Telegram should be part of the dummy version.
- Dummy agent output should be a summary only.
- Approval is required before writing/committing.
- Telegram feedback should be flexible: the app should not rely only on exact `yes` / `no` strings.
- Target production file: `/Users/ryanbrown/code/ryanbbrown/OPINIONS.md`.
- Target test file: `/Users/ryanbrown/code/ryanbbrown/TEST_OPINIONS.md`.
- Railway must use configured repo/file paths rather than local `/Users/ryanbrown/...` paths.
- Commit behavior: commit and push only the target file.
- The app may push directly to `main`.
- Existing env vars:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_ALLOWED_CHAT_ID`
  - `READWISE_TOKEN`
  - `HARNESS_MODEL`
  - `OPENAI_API_KEY` or the equivalent provider key for `HARNESS_MODEL`
  - `LANGFUSE_SECRET_KEY`
  - `LANGFUSE_PUBLIC_KEY`
  - `LANGFUSE_BASE_URL`

## Initial Architecture

Use a small Python app with explicit adapters, commands, and a clear host-app/agent boundary:

```text
src/opinions_agent/
  app.py              # FastAPI webhook server and healthcheck
  cli.py              # local/dev/admin commands
  config.py           # env parsing
  db.py               # engine/session helpers
  models.py           # SQLAlchemy models
  readwise.py         # Readwise API client and sync logic
  highlight_export.py # export stable agent input files from DB highlights
  telegram.py         # Telegram Bot API adapter
  workflow.py         # orchestration between sync, agent, approval, Telegram, and commit
  agent.py            # ThinHarness builder and dummy summary runner
  tracing.py          # Langfuse OTLP tracing setup for ThinHarness
  repo_checkout.py    # ensure configured opinions repo checkout exists for local/Railway runs
  tools/
    git_ops.py        # constrained ThinHarness commit/push tool for one target file
```

Prefer direct HTTP for Telegram and Readwise through `httpx`; do not add larger SDKs until the API surface justifies them.

Root-level project files should include:

- `pyproject.toml` with dependencies, `pytest`, `ruff`, `pyright`, and the `opinions-agent` console script.
- `alembic/` and `alembic.ini` at repo root.
- `compose.yaml` for local PostgreSQL.
- `.env.example` with all required variables.
- `.gitignore` entries for `.env`, `.runs/`, and any project-local trace directory.
- `railway.toml`.
- Updated `README.md` with local setup, commands, and Railway notes.

### Host App Responsibilities

The host app owns external systems and durable workflow state:

- Poll/sync Readwise.
- Save highlight batches to Postgres.
- Export selected highlight batches to stable JSONL/Markdown files for the agent.
- Receive Telegram updates through webhook and local polling.
- Validate `TELEGRAM_ALLOWED_CHAT_ID`.
- Start and resume ThinHarness runs.
- Persist ThinHarness `resume_state`.
- Configure ThinHarness Langfuse tracing.
- Send Telegram messages from structured agent output.
- Store outbound Telegram `message_id`s and inbound Telegram `update_id`s.
- Own scheduling, Railway web service setup, and Railway cron setup.
- Ensure the configured opinions repo checkout exists before agent runs that read/write opinions files.

### Opinions Repo Checkout

Local development can use `/Users/ryanbrown/code/ryanbbrown`, but Railway needs an explicit checkout strategy. Configure these instead of hard-coding local paths:

- `OPINIONS_REPO_URL`
- `OPINIONS_REPO_BRANCH`, default `main`
- `OPINIONS_REPO_DIR`, local default `/Users/ryanbrown/code/ryanbbrown`, Railway default an app-owned writable directory
- `OPINIONS_TARGET_FILE`, local default `TEST_OPINIONS.md` until the flow is proven
- bot git author name/email

The app should clone or update the configured repo before summary runs and before commit operations. If `OPINIONS_REPO_DIR` already exists locally, cloning is skipped and the app should fetch/update that checkout. Railway deployment also needs git authentication configured for pushing to the target repo, using either an SSH deploy key or a token-based HTTPS remote; choose one during implementation and document it in `README.md`.

### ThinHarness Agent Responsibilities

The agent should be given the smallest useful set of tools, and those tools should differ before and after approval:

- Pre-approval summary runs: read-only access to exported Readwise highlight/context files, existing opinions context files, and the resolved configured opinions target file.
- Post-approval commit runs: read access plus append/write access to the resolved configured opinions target file.
- Post-approval commit runs: a constrained `commit_and_push_opinions_file` tool.

The agent should not get shell access. It should not call Readwise directly in the first version. Readwise sync is app-owned preprocessing so agent runs are reproducible from saved inputs.

### Agent Input Files

For each run, the app should export a deterministic input bundle before invoking ThinHarness:

- selected highlights as JSONL
- a small Markdown run brief
- any existing memory/context files needed for the dummy flow

The DB remains source of truth for workflow state. Files are for agent context, auditability, and debugging.

Example shape only:

```text
.runs/<summary_run_id>/highlights.jsonl
.runs/<summary_run_id>/brief.md
```

### Agent Output Contract

The agent should not rely on plain final text becoming the Telegram response. It should return structured output that the host app sends after the run completes and the result is stored.

The output should include:

- workflow status: awaiting user, committed, rejected, or needs more work
- zero or more Telegram message specs
- optional revised summary text
- optional commit metadata once committed

Keep the schema small. The implementation can define exact Pydantic models in `agent.py`.

### Telegram Boundary

Do not give the agent a direct `send_telegram` tool in v1.

Reason: Telegram sends are side effects. If they happen inside the agent loop, retries or partial failures can duplicate messages and make state harder to resume. Instead, the agent returns structured Telegram message specs, and the host app sends them exactly once after persisting the run result.

Add a direct Telegram notification tool only later if progress messages become important. If that happens, require idempotency keys per message.

Telegram features to support in the structured message specs:

- plain text messages
- optional inline buttons
- optional `reply_to_message_id`
- optional force-reply behavior

Do not implement Telegram polls in v1. Polls are useful for voting, but this workflow needs approving or revising a mutable text artifact. Inline buttons plus free-text replies fit better.

### Approval Interaction

The first approval message should be concise:

- short summary preview
- source/run identifier if useful
- inline buttons for Approve / Reject / Revise
- allowance for free-text feedback

Inbound replies and callback queries should both route to the same pending `summary_run`. The host app stores the update and invokes the agent with the previous run context plus the user's feedback.

Approval authority is split deliberately:

- Inline button callbacks are interpreted deterministically by the host app as approve, reject, or revise.
- Free-text feedback goes to the agent for revision or clarification.
- Ambiguous free text should not silently become approval. It should produce a revised proposal or an explicit confirmation request.
- Stale callbacks for already completed/rejected runs should be acknowledged but should not mutate state.

## Dependencies

Approved starting dependencies:

- `fastapi`
- `uvicorn`
- `httpx`
- `pydantic`
- `sqlalchemy`
- `alembic`
- `psycopg`
- ThinHarness:
  - local development can temporarily use the local path dependency at `/Users/ryanbrown/code/thinharness`
  - Railway should use the PyPI `thinharness` package once the needed version is published
- ThinHarness tracing optional dependencies, via `thinharness[tracing]` or equivalent OpenTelemetry packages:
  - `opentelemetry-api`
  - `opentelemetry-sdk`
  - `opentelemetry-exporter-otlp-proto-http`
- `pytest`
- `ruff`
- `pyright`

Use `uv` for all Python operations.

Use `HARNESS_MODEL` to configure the dummy ThinHarness model. Default locally to `openai:gpt-5.2` unless `.env` says otherwise. The chosen provider key must be present locally and in Railway; for the OpenAI default this means `OPENAI_API_KEY`.

Use a structured-output mode compatible with the selected provider. If the selected provider does not support native structured output, use ThinHarness' prompted or tool-mode structured output instead of native mode.

## Data Model

Minimum tables:

- `readwise_sync_state`
  - stores `updated_after`, `page_cursor`, and last successful sync metadata
- `readwise_highlights`
  - stores Readwise highlight IDs, document metadata, text, timestamps, and raw JSON
- `summary_runs`
  - records each dummy agent run, input highlight IDs, exported input paths, generated summary, status, attempt counts, lock/lease timestamps, ThinHarness resume state if available, and optional external trace identifiers if exposed
- `summary_run_highlights`
  - records membership between `summary_runs` and Readwise highlight IDs so the same highlight batch is not repeatedly summarized by accident
- `telegram_interactions`
  - stores outbound approval message IDs, inbound reply/update IDs, callback query IDs, idempotency keys, chat ID, text, status, and parsed workflow linkage

Store raw external payloads as JSONB so the first version does not over-model Readwise or Telegram.

Do not store full ThinHarness traces or provider message transcripts in Postgres. Postgres stores app workflow state, resumability state, input/output artifacts, and external IDs. ThinHarness tracing should go to Langfuse, with local JSONL traces treated as local/dev diagnostics only.

Important uniqueness/idempotency constraints:

- Readwise highlight IDs are unique.
- Telegram inbound `update_id` is unique.
- Telegram callback query ID is unique when present.
- Outbound Telegram messages use a deterministic idempotency key per run/message purpose.
- `summary_run_highlights` prevents duplicate membership for a run.

Status transitions should be explicit enough to recover after restarts:

- `pending_agent`
- `awaiting_user`
- `revising`
- `approved`
- `committing`
- `committed`
- `rejected`
- `failed`

Use attempts and lock/lease timestamps around agent runs, Telegram sends, and git commits so a crashed cron/web process can retry safely without double-processing.

Highlight selection should treat these statuses as in-flight or processed and therefore blocking automatic re-selection:

- `pending_agent`
- `awaiting_user`
- `revising`
- `approved`
- `committing`
- `committed`
- `rejected`

Highlights attached only to `failed` runs may be eligible for retry after the run's lease expires or via an explicit retry/backfill command. `rejected` highlights are excluded from automatic retry, but explicit backfill/test commands may include them.

Use a database transaction plus row locks or an advisory lock when selecting highlights and creating `summary_runs`, so concurrent `daily-run` / `summarize-recent` invocations cannot select the same highlights.

## Workflow

1. `readwise-sync`
   - Fetch highlights from Readwise export API.
   - Use cursor-based pagination.
   - Store raw highlight/document data idempotently.
   - Maintain sync state for incremental runs.

2. `summarize-recent --limit N`
   - Select the N most recent synced highlights that are not already included in a blocking-status summary run, unless an explicit backfill/test flag asks for a known batch.
   - Export selected highlights to `.runs/<summary_run_id>/`.
   - Build a pre-approval ThinHarness agent with read-only access to exported run files and the resolved configured opinions target file.
   - Run the dummy ThinHarness agent.
   - Store the proposed summary as a pending `summary_run`.
   - Persist the agent structured output and resume state.
   - Send the structured Telegram message specs returned by the agent.
   - Store Telegram outbound message IDs.

3. Telegram webhook or local polling receives feedback.
   - Validate `TELEGRAM_ALLOWED_CHAT_ID`.
   - Attach inbound feedback to the pending summary run.
   - Resume or re-run the dummy agent loop with the feedback and stored summary context.
   - For button callbacks, let the host app apply the explicit action.
   - For free-text feedback, let the agent revise or ask for clarification.
   - Send the next structured Telegram message specs returned by the agent.

4. If approved:
   - Build a post-approval ThinHarness agent with append/write access to the resolved configured opinions target file.
   - Agent reads the resolved configured opinions target file.
   - Agent appends the final summary to the resolved configured opinions target file; do not overwrite the whole file.
   - Agent calls `commit_and_push_opinions_file`.
   - Tool commits only `OPINIONS_TARGET_FILE`.
   - Tool pushes to `origin OPINIONS_REPO_BRANCH`.
   - Mark the run as committed.
   - Send Telegram confirmation from structured output.

5. If rejected:
   - Mark the run as rejected.
   - Do not write to the opinions file.

6. If revised:
   - Store the revised summary.
   - Send a new Telegram approval message or update the pending run.

## ThinHarness Tooling

The dummy agent should be configured deliberately rather than given broad filesystem access.

Built-in ThinHarness tools:

- `read`
- `write`
- `search` if useful for context files
- optionally `list` / `glob` if the prompt needs discovery

Configured paths:

- read: exported `.runs/<summary_run_id>/` files
- read: relevant context/memory files
- pre-approval read: resolved configured opinions target file
- post-approval read/write: resolved configured opinions target file

Configure ThinHarness `root`, `read_paths`, and `write_paths` deliberately so the agent can see both `.runs/<summary_run_id>/` and the opinions repo target file even though they may live in different directory trees.

Custom tools:

- `commit_and_push_opinions_file`
  - validates the configured target path
  - checks whether the target file changed
  - stages only the target file
  - commits with a conventional commit message
  - pushes to `origin OPINIONS_REPO_BRANCH`
  - returns commit SHA/status to the agent

Do not implement a live `readwise_fetch` tool in v1. The Readwise adapter belongs in the host app, and the agent consumes stable exported inputs.

## ThinHarness Resume And Tracing

ThinHarness resume and tracing are separate concerns:

- Resume state is provider-specific data returned by `HarnessResult.resume_state`.
- The app should persist `resume_state` on pending `summary_runs`.
- When Telegram feedback arrives, the app should pass that stored state back through `Harness.run(..., resume_from=...)` if present.
- Traces are observability data, not the source of truth for resuming.
- If `resume_from` fails because `HARNESS_MODEL` changed while a run was awaiting user feedback, mark the run failed or restart from saved app context with an explicit note; do not silently lose the pending feedback.

Langfuse should be configured through ThinHarness' generic OTLP tracing helper. The ThinHarness e2e example uses `create_otlp_tracing` plus `TracingOptions`, with Langfuse Basic auth built from public and secret keys and endpoint:

```text
<LANGFUSE_BASE_URL>/api/public/otel/v1/traces
```

Implementation notes:

- Add a small app helper that creates the Langfuse OTLP tracer from `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL`.
- Pass `tracing=[TracingOptions(tracer=..., agent_name="opinions-agent", ...)]` when building the ThinHarness instance.
- Flush and shut down the tracer after short-lived cron/CLI runs.
- The always-on web process should flush after each run and shut down cleanly on process exit.
- Use a deliberate capture policy. For initial debugging, capturing messages/tool args/tool results is useful, but it sends Readwise highlight content and file diffs to Langfuse.
- Production default: enable Langfuse spans but do not capture full messages, tool args, or tool results unless explicitly configured for debugging.
- Local default: allow full capture while developing, with the trace directory treated as sensitive.
- Local plaintext ThinHarness tracing is enabled by default; set a project-local trace directory for development and disable local traces in deployed Railway if Langfuse is the external trace store.

## Git Behavior

The commit tool should commit only its configured opinions file:

```bash
git -C "$OPINIONS_REPO_DIR" add "$OPINIONS_TARGET_FILE"
git -C "$OPINIONS_REPO_DIR" commit -m "chore: append readwise summary"
git -C "$OPINIONS_REPO_DIR" push origin "$OPINIONS_REPO_BRANCH"
```

Before committing, verify that the configured file changed. Do not stage unrelated files. If unrelated local changes exist, leave them alone.

The app may invoke this behavior only through the constrained tool or equivalent app-owned helper. Do not expose general bash to the agent.

The commit tool should also handle or fail loudly on:

- missing git author identity
- missing/invalid push credentials
- non-fast-forward push
- remote changes on `OPINIONS_REPO_BRANCH`
- target file already dirty before the agent writes
- concurrent approvals trying to commit the same target file
- failed push after a local commit

Default v1 behavior should be conservative: fetch before committing, avoid staging unrelated files, push only after a successful single-file commit, and mark the run `failed` with enough detail for manual recovery if push fails.

## Telegram Handling

Support both local polling and production webhooks:

- `telegram-poll` for local development.
- `POST /telegram/webhook` for Railway.

Webhook requests should validate Telegram's secret token header once webhooks are configured. Both modes should normalize incoming Telegram updates into the same internal handler.

Inbound update types for v1:

- plain text `message`
- button `callback_query`

Outbound message features for v1:

- `sendMessage`
- inline keyboard buttons
- optional reply-to
- optional force-reply

The host app sends outbound messages from structured agent output. It should create an outbound intent row with a deterministic idempotency key before sending, acquire/lease that row for send, then update the DB with Telegram's returned `message_id`.

Telegram does not provide native idempotency for `sendMessage`, so retries must dedupe on the outbound intent row, not only on whether `message_id` is present. If a process crashes after sending but before recording `message_id`, the retry path should mark the intent as uncertain/failed for manual inspection rather than blindly sending a duplicate.

Callback button payloads should include the `summary_run_id` and requested action. The handler should validate the current run status before applying the action. Duplicate or stale callbacks should not re-run agent or git work.

## Commands

Local commands should mirror deployed commands:

```bash
uv run opinions-agent serve
uv run opinions-agent telegram-poll
uv run opinions-agent readwise-sync
uv run opinions-agent summarize-recent --limit 10
uv run opinions-agent process-pending-telegram
uv run opinions-agent set-telegram-webhook
uv run opinions-agent daily-run
```

The first manual test flow should be:

```bash
uv run opinions-agent readwise-sync
uv run opinions-agent summarize-recent --limit 10
uv run opinions-agent telegram-poll
```

For deployed testing, the equivalent path should be:

- Railway web service receives Telegram webhook replies.
- Railway cron or manual Railway command runs Readwise sync and summary creation.

`daily-run` should be the cron entry point once the vertical slice exists. It should ensure the opinions repo checkout, sync Readwise, select unprocessed highlights, create one pending summary run if there is new work, and send Telegram approval.

## Local Project Setup

Use root-level `alembic/` for migrations. Do not put migrations under `src/opinions_agent/` for v1.

`compose.yaml` should run local PostgreSQL with a persistent Docker volume and a `DATABASE_URL` compatible with SQLAlchemy + psycopg, for example:

```text
postgresql+psycopg://opinions:opinions@localhost:5432/opinions
```

`.env.example` should include placeholders for:

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_CHAT_ID`
- `TELEGRAM_WEBHOOK_SECRET`
- `READWISE_TOKEN`
- `HARNESS_MODEL`
- provider key for `HARNESS_MODEL`, such as `OPENAI_API_KEY`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_BASE_URL`
- `OPINIONS_REPO_URL`
- `OPINIONS_REPO_BRANCH`
- `OPINIONS_REPO_DIR`
- `OPINIONS_TARGET_FILE`
- bot git author name/email

Update `README.md` with the minimum setup path: install dependencies, start Postgres, run migrations, sync Readwise, create a summary run, poll Telegram locally, and run tests/lint/typecheck.

## Testing

Use `pytest` for automated tests, `ruff` for linting, and `pyright` for typechecking.

Automated tests should cover at minimum:

- Readwise sync idempotency.
- Highlight selection skips blocking-status runs and handles `failed` retry eligibility.
- Telegram duplicate `update_id` and duplicate callback query handling.
- Stale callbacks against completed/rejected runs.
- Outbound Telegram idempotency intent-row behavior.
- Commit tool stages only `OPINIONS_TARGET_FILE`.
- Commit tool no-ops or fails clearly when target file is unchanged.
- Commit tool detects non-fast-forward / push failure without staging unrelated files.
- Status transition validity.
- Pre-approval agent path cannot mutate the opinions target file.
- Resume from stored `resume_state`, plus behavior when the configured model no longer matches pending resume state.

## Railway Shape

Include `railway.toml` with the web service start command:

```bash
uv run opinions-agent serve
```

Expose:

- `GET /healthz`
- `POST /telegram/webhook`
- optionally `POST /readwise/webhook` later

Use Railway variables for secrets. The app should not depend on checked-in `.env` in production.

Railway should set `OPINIONS_REPO_DIR` to a writable app-owned directory. If a persistent Railway volume is configured, use that mount; otherwise the app must be able to clone on startup or before each run. Document the chosen git auth mechanism in `README.md`.

Cron should run daily in UTC. The cron command should eventually run:

```bash
uv run opinions-agent daily-run
```

Processing pending Telegram replies belongs to the always-on web service. Retrying stuck work can be a separate admin command if needed.

## Verification Criteria

- Local app starts with `uv run opinions-agent serve`.
- `GET /healthz` returns success.
- Local Postgres migrations apply cleanly.
- Real Readwise sync stores highlights.
- Re-running Readwise sync is idempotent.
- Selected highlights are exported to stable `.runs/<summary_run_id>/` files.
- `summarize-recent --limit N` does not repeatedly select already pending/processed highlights.
- Dummy ThinHarness summary run creates a pending DB record.
- Dummy ThinHarness summary run returns structured Telegram message specs.
- Host app sends an approval request to the configured chat.
- Telegram polling or webhook receives a reply from the configured chat.
- Feedback is persisted and routed to the correct pending `summary_run`.
- Duplicate Telegram updates/callbacks are ignored idempotently.
- Stale callbacks do not mutate completed/rejected runs.
- Approval causes the agent to read and append to the resolved configured opinions target file.
- Commit includes only `OPINIONS_TARGET_FILE`.
- Push goes to `origin OPINIONS_REPO_BRANCH`.
- Telegram receives a committed confirmation message.
- Rejection creates no file change and no commit.
- App restart during `awaiting_user` can resume the pending flow.
- Failed git push marks the run failed without staging unrelated files.
- Non-fast-forward remote state is detected and surfaced.
- Railway webhook smoke test succeeds.
- Railway cron smoke test succeeds.
- Relevant tests, typecheck, and lint pass before declaring implementation complete.

## Open Implementation Notes

- Keep `agent.py` intentionally thin so the real agent can replace the dummy summarizer later.
- Store enough context in the database to resume pending Telegram approval flows after process restart.
- Use Markdown files for durable memory/artifacts later, but use Postgres for queue/workflow state.
- Keep `OPINIONS.md` untouched until the test flow is proven against `TEST_OPINIONS.md`.
- Prefer structured agent output over Telegram side-effect tools in v1.
- Add Telegram side-effect tools only if progress messages become necessary, and require idempotency keys if they are added.
