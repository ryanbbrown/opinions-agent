# opinions-agent

`opinions-agent` syncs Readwise Reader documents, summaries, full content, highlights, and notes into a durable
filesystem corpus, deterministically selects the current window of evidence for each run, asks an agent to propose
conceptual opinion changes, and resumes that same bounded agent conversation to update `OPINIONS.md`,
`OPINIONS_SOURCES.jsonl`, and `opinion-decisions.jsonl` only after Telegram approval.

The app owns sync state, selection, approval state, validation, and git commits. The agent proposes concepts first,
then performs approved artifact edits inside a write boundary limited to the three opinion artifacts.

## Storage shape

Durable corpus (`OPINIONS_DATA_DIR`, default `.readwise`):

```text
state.json                 # app-owned sync + workflow cursor state
documents.jsonl            # one normalized row per Reader document
highlights.jsonl           # one normalized row per highlight (primary query surface)
opinion-decisions.jsonl    # agent-authored compact decision summaries
documents/reader_<id>.md   # readable full document content
raw/reader_<id>.json       # untouched API payloads (not agent context)
memory/                    # placeholder memory files (no agent writes in v1)
```

Run bundles (`RUNS_DIR`, default `.runs`) hold active-run/debug artifacts only:

```text
active/<run_id>/selected-highlights.jsonl, selected-documents.jsonl
active/<run_id>/review/summary.md, initial-telegram.md
completed/<run_id>/final.json   # retained OPINIONS_COMPLETED_RUN_RETENTION_DAYS days (default 30)
```

The database keeps operational state only: runs, Telegram message/update idempotency, ThinHarness resume state, and
failure details. Proposal rows may exist as an audit cache, but they do not drive file mutations.

## Workflow

1. `sync` pulls Reader v3 documents/highlights/notes into the corpus (`state.json` advances only after all
   corpus writes succeed).
2. `opinion-run` refuses to start while any run is non-terminal, selects highlights between the workflow cursor
   and now, writes the run bundle, and starts one ThinHarness conversation.
3. The agent returns native structured output: `status` plus one or more Telegram message specs. The app sends those
   messages exactly, with deterministic `opinion-run:<run_id>:turn:<turn_seq>:message:<index>` idempotency keys, and
   stores Telegram's real `(chat_id, message_id)` values.
4. Telegram callbacks and replies are recorded against the stored outbound message by `(chat_id, message_id)`.
   Callback data must match a button that was actually sent. A single response does not resume the agent until every
   required message in the current turn has a response.
5. Exact uppercase `GO` and `SKIP` from `TELEGRAM_ALLOWED_CHAT_ID` resume the same agent conversation immediately as
   concrete user input. The app does not interpret these commands as proposal accept/reject decisions.
6. The agent writes the opinion artifacts directly when the conversation has enough approval or revision context, calls
   the same validator the app uses, and returns `done` or `blocked`.
7. After `done`, the app validates once more, rejects unrelated staged files, stages only `OPINIONS.md` and
   `OPINIONS_SOURCES.jsonl`, commits/pushes those files if changed, updates the opinion-ID high-water mark, advances
   the workflow cursor, and only then sends final success-style Telegram messages. `opinion-decisions.jsonl` lives in
   `OPINIONS_DATA_DIR` and is not committed to the opinions repo.

`OPINIONS.md` uses section headings with one-line bullet opinions and indented metadata comments:

```markdown
## Section

- Opinion sentence.
  <!-- opinion-id: opinion-000013 -->
  <!-- sources: rw:source-id, reader-note:document-id -->
```

Opinion IDs are agent-written and app-validated. IDs are stable, unique, and never reused after retirement. Source rows
in `OPINIONS_SOURCES.jsonl` use `evidence_id` and are invalid if they duplicate an `(opinion_id, evidence_id)` pair,
reference a missing opinion, use legacy `highlight_id`, omit required provenance fields, fail to match selected-run
evidence metadata for newly added evidence, or add evidence outside the current run bundle. Every accepted opinion must
have at least one machine-readable source row.

## Local Setup

```bash
uv sync
cp .env.example .env
docker compose up -d postgres
uv run alembic upgrade head      # or: uv run opinions-agent init-db (creates tables directly)
```

Required local variables: `DATABASE_URL`, `READWISE_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_ID`,
`HARNESS_MODEL` (+ `OPENAI_API_KEY` for the default model), and the `OPINIONS_*` repo settings shown in
`.env.example`.

Safety default: `OPINIONS_TARGET_FILE` defaults to `TEST_OPINIONS.md` so local runs never touch the real
`OPINIONS.md` by accident. Production (Railway) must set `OPINIONS_TARGET_FILE=OPINIONS.md` explicitly. Note that
approvals push to `OPINIONS_REPO_URL`, which defaults to the real repo — point `OPINIONS_REPO_DIR`/`OPINIONS_REPO_URL`
at a disposable repo when experimenting.

## Commands

```bash
uv run opinions-agent serve            # FastAPI web service (Telegram webhook + /healthz)
uv run opinions-agent init-runtime     # ensure data dirs, memory files, repo checkout, DB migrations
uv run opinions-agent sync             # Reader -> filesystem corpus
uv run opinions-agent opinion-run      # sync + select window + start/resume Telegram approval loop
uv run opinions-agent sample-run W04   # local disposable run against copied artifacts under .runs/active/
uv run opinions-agent abandon-run ID   # abandon a stuck pending run (cursor does not advance)
uv run opinions-agent telegram-poll    # local alternative to the webhook
uv run opinions-agent set-telegram-webhook https://your-service.up.railway.app/telegram/webhook
```

Useful `opinion-run` flags: `--deterministic-agent` (no model calls), `--skip-sync`,
`--window-start/--window-end` (ISO timestamps, override the workflow cursor).

`sample-run W04` maps `W04` to the fourth chronological seven-day window in the local corpus, starting from the Monday
of the earliest dated highlight. It creates a readable run directory named `<timestamp>-W04` under `.runs/active/`,
copies the configured corpus plus a chosen opinions file into that directory, initializes a disposable local git remote,
and runs the normal agent workflow against those copied paths. The agent cannot read or write the original opinion repo
files during a sample run. Use `--opinions-file PATH` to choose the seed file; it defaults to `OPINIONS.md` in the
current working directory. If no sources file is supplied, sample setup derives `OPINIONS_SOURCES.jsonl` from inline
`<!-- sources: ... -->` comments and the copied corpus evidence rows. By default, sample runs use fake Telegram and
write review files only; pass `--send-telegram` to send the sample run's Telegram messages to the configured allowed
chat.

Deterministic local smoke run without Telegram sends:

```bash
OPINIONS_FAKE_TELEGRAM=1 uv run opinions-agent opinion-run --deterministic-agent
```

## Railway

Deploys build from this repo; the opinions repo and all durable files live outside the build:

- Attach a volume. `OPINIONS_DATA_DIR`, `RUNS_DIR`, and `OPINIONS_REPO_DIR` default to
  `$RAILWAY_VOLUME_MOUNT_PATH/{readwise,runs,opinions-repo}` when the mount env var is present, or set them
  explicitly (e.g. `/app/data/readwise`). Volumes mount at container start, so all filesystem initialization is
  runtime work (`init-runtime`), never build time.
- Set `OPINIONS_REPO_URL` to a token-backed HTTPS URL; the repo is cloned/updated at runtime into
  `OPINIONS_REPO_DIR`. Set `OPINIONS_TARGET_FILE=OPINIONS.md` and `OPINIONS_SOURCES_FILE=OPINIONS_SOURCES.jsonl`.
- Run `uv run opinions-agent init-runtime` on deploy (pre-start), then `serve`.
- Schedule `uv run opinions-agent opinion-run` weekly (Railway cron); biweekly is a schedule change, not a
  storage change. The scheduler exits cleanly if a previous run is still pending approval.
- Enable Railway volume backups for the mounted data directory; the opinions repo is separately durable via git.

Smoke checklist after a deploy:

1. `curl https://<service>/healthz` returns `{"status":"ok"}`.
2. `init-runtime` logged `runtime initialized` (dirs, repo checkout, migrations).
3. `opinion-run` either creates a run (agent-authored Telegram messages arrive) or prints
   `no highlights in the current window` / the active-run refusal.
4. Answering all required current-turn messages, or sending exact `GO` / `SKIP`, resumes the same agent conversation.
   Successful approved changes push a commit to the opinions repo touching only `OPINIONS.md` and
   `OPINIONS_SOURCES.jsonl`.
5. After the agent returns `done` and app validation/commit handling succeeds, `state.json`
   `workflow.last_completed_window_end` advances and the run folder moves to `completed/`.

If validation, commit, or push fails the run is marked failed with recovery context in `failure_reason`. Inspect the
opinions repo, `OPINIONS_DATA_DIR/opinion-decisions.jsonl`, and the active run snapshot before retrying. Failed runs
are terminal and do not block new runs, so no `abandon-run` is needed (that command is for runs stuck pending approval).

## Testing

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

The e2e test uses a disposable local git remote, the deterministic agent, and simulated Telegram updates. The required
developer completion gate for real ThinHarness/native-output behavior is isolated behind an explicit environment flag:

```bash
OPINIONS_RUN_REAL_E2E=1 uv run pytest tests/test_real_e2e_optional.py
```

## Artifacts

`.readwise/` and `.runs/` are gitignored because they can contain Reader content and run bundles. ThinHarness local
traces use its default location under `~/.thinharness/traces/`; disable plaintext local traces in deployed environments
with `THINHARNESS_DISABLE_LOCAL_TRACING=1`.
