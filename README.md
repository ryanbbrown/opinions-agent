# opinions-agent

`opinions-agent` syncs Readwise Reader documents, summaries, full content, and highlights into a durable
filesystem corpus, deterministically selects the current window of highlights for each run, asks an agent to
propose opinion changes, and applies each proposal to `OPINIONS.md` / `OPINIONS_SOURCES.jsonl` only after
per-proposal Telegram approval.

The app owns sync state, selection, approval, file mutations, and git commits. The agent only reads a restricted
set of paths and returns structured proposals.

## Storage shape

Durable corpus (`OPINIONS_DATA_DIR`, default `.readwise`):

```text
state.json                 # app-owned sync + workflow cursor state
documents.jsonl            # one normalized row per Reader document
highlights.jsonl           # one normalized row per highlight (primary query surface)
opinion-decisions.jsonl    # accepted/rejected proposal history
documents/reader_<id>.md   # readable full document content
raw/reader_<id>.json       # untouched API payloads (not agent context)
memory/                    # placeholder memory files (no agent writes in v1)
```

Run bundles (`RUNS_DIR`, default `.runs`) hold active-run/debug artifacts only:

```text
active/<run_id>/brief.md, selected-highlights.jsonl, selected-documents.jsonl
completed/<run_id>/final.json   # retained OPINIONS_COMPLETED_RUN_RETENTION_DAYS days (default 30)
```

The database keeps operational state only: runs, proposals, Telegram idempotency, ThinHarness resume state, and
failure details.

## Workflow

1. `sync` pulls Reader v3 documents/highlights/notes into the corpus (`state.json` advances only after all
   corpus writes succeed).
2. `opinion-run` refuses to start while any run is non-terminal, selects highlights between the workflow cursor
   and now, writes the run bundle, and asks the agent for proposals.
3. The app sends one Telegram message per proposal with Approve / Reject / Revise buttons.
4. Approve applies that proposal to `OPINIONS.md` + `OPINIONS_SOURCES.jsonl`, validates stable IDs and
   provenance, appends to `opinion-decisions.jsonl`, and commits/pushes only those two files. Reject records the
   decision without mutating files. Replying to a proposal message revises the whole batch (the previous batch is
   superseded).
5. When every proposal is terminal, the run completes and the workflow cursor in `state.json` advances.

Each opinion in `OPINIONS.md` carries a hidden stable ID (`<!-- opinion-id: opinion-000013 -->`); visible numbers
can be reordered later, the hidden ID is durable.

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

## Commands

```bash
uv run opinions-agent serve            # FastAPI web service (Telegram webhook + /healthz)
uv run opinions-agent init-runtime     # ensure data dirs, memory files, repo checkout, DB migrations
uv run opinions-agent sync             # Reader -> filesystem corpus
uv run opinions-agent opinion-run      # sync + select window + propose + request approval
uv run opinions-agent abandon-run ID   # abandon a stuck pending run (cursor does not advance)
uv run opinions-agent telegram-poll    # local alternative to the webhook
uv run opinions-agent set-telegram-webhook https://your-service.up.railway.app/telegram/webhook
```

Useful `opinion-run` flags: `--deterministic-agent` (no model calls), `--skip-sync`,
`--window-start/--window-end` (ISO timestamps, override the workflow cursor).

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
3. `opinion-run` either creates a run (Telegram messages arrive, one per proposal) or prints
   `no highlights in the current window` / the active-run refusal.
4. Approving a proposal pushes a commit to the opinions repo touching only `OPINIONS.md` and
   `OPINIONS_SOURCES.jsonl`.
5. After all proposals are decided, `state.json` `workflow.last_completed_window_end` advanced and the run folder
   moved to `completed/`.

If a push fails the run is marked failed with the git error in `failure_reason`; the local commit is preserved in
`OPINIONS_REPO_DIR` — push or reset it manually, then `abandon-run` if needed.

## Testing

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

The e2e test uses a disposable local git remote, the deterministic agent, and simulated Telegram updates. The
optional real-model path:

```bash
OPINIONS_RUN_REAL_E2E=1 uv run pytest tests/test_real_e2e_optional.py
```

## Artifacts

`.readwise/`, `.runs/`, and `.traces/` are gitignored (they can contain Readwise content). Disable plaintext
local traces in deployed environments with `THINHARNESS_DISABLE_LOCAL_TRACING=1`.
