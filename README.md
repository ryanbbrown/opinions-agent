# OPINIONS.md Agent

*Note: work in progress*

`opinions-agent` syncs Readwise Reader documents, summaries, full content, highlights, and notes into a durable
filesystem corpus, assigns new evidence versions to a weekly cycle, asks an agent to propose
conceptual opinion changes, and resumes that same bounded agent conversation to update `OPINIONS.md`,
`OPINIONS_SOURCES.jsonl`, and `opinion-decisions.jsonl` only after Telegram approval.

The app owns sync state, selection, approval state, validation, and git commits. The agent proposes concepts first,
then performs approved artifact edits inside a write boundary limited to the three opinion artifacts.

## Storage shape

Durable corpus (`OPINIONS_DATA_DIR`, default `.readwise`):

```text
state.json                 # Reader sync watermarks only
documents.jsonl            # one normalized row per Reader document
highlights.jsonl           # one normalized row per Reader highlight or document-level note
opinion-decisions.jsonl    # agent-authored compact decision summaries
documents/reader_<id>.md   # readable full document content
raw/reader_<id>.json       # untouched API payloads (not agent context)
memory/                    # placeholder memory files (no agent writes in v1)
```

Cycle bundles (`RUNS_DIR`, default `.runs`) hold fixed evidence snapshots and recovery artifacts:

```text
active/<cycle_id>/batches/<number>/selected-highlights.jsonl
active/<cycle_id>/batches/<number>/selected-documents.jsonl, critic-context.jsonl
active/<cycle_id>/batches/<number>/recovery/<run_id>/
completed/<cycle_id>/
```

PostgreSQL owns cycles, batches, evidence assignments, leases, runs, Telegram idempotency, and git durability phases.

## Workflow

1. `sync` pulls Reader v3 documents/highlights/notes into the corpus (`state.json` advances only after all
   corpus writes succeed).
2. `opinion-cycle` creates one fixed weekly snapshot. It balances batches at 20 documents or 50 evidence rows.
   `opinion-run` remains a manual run-only command and selects an explicit or previous-seven-day window.
   including Reader highlights, document-level notes, and tagged document summaries, writes the run bundle, and starts
   one ThinHarness conversation.
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
   the evidence assignment, and only then sends final success-style Telegram messages. The worker queues the next
   batch automatically. `opinion-decisions.jsonl` lives in
   `OPINIONS_DATA_DIR` and is not committed to the opinions repo.

`OPINIONS.md` uses section headings with one-line bullet opinions and indented metadata comments:

```markdown
## Section

- Opinion sentence.
  <!-- opinion-id: opinion-000013 -->
  <!-- sources: rw:source-id, reader-note:document-id, reader-summary:document-id -->
```

Opinion IDs are agent-written and app-validated. IDs are stable, unique, and never reused after retirement. Source rows
in `OPINIONS_SOURCES.jsonl` use `evidence_id` and are invalid if they duplicate an `(opinion_id, evidence_id)` pair,
reference a missing opinion, use legacy `highlight_id`, omit required provenance fields, fail to match selected-run
evidence metadata for newly added evidence, or add evidence outside the current run bundle. Every accepted opinion must
have at least one machine-readable source row.

## Local Setup

```bash
uv tool install --editable ../cproxy
codex login status
uv sync
cp .env.example .env
docker compose up -d postgres
uv run alembic upgrade head      # or: uv run opinions-agent init-db (creates tables directly)
```

Required local variables include `DATABASE_URL`, Reader and Telegram credentials, and the repository settings in
`.env.example`. Local ThinHarness calls use Codex CLI authentication through `cproxy`. The agent defaults to
`openai:gpt-5.6-sol` at medium effort. Braintrust keys enable tracing and are required for `eval run`.

Safety default: `OPINIONS_TARGET_FILE` defaults to `TEST_OPINIONS.md` so local runs never touch the real
`OPINIONS.md` by accident. Production (Railway) must set `OPINIONS_TARGET_FILE=OPINIONS.md` explicitly. Note that
approvals push to `OPINIONS_REPO_URL`, which defaults to the real repo — point `OPINIONS_REPO_DIR`/`OPINIONS_REPO_URL`
at a disposable repo when experimenting.

### Local model access

Run model-backed commands through `cproxy` on the opinions-agent port:

```bash
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent sample-run W04
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent eval run --weeks W04 W05
```

The 500-chain capacity supports concurrent eval cases and replaces the patched proxy previously used for evals. A one-shot command can let `cproxy run` manage the proxy lifetime.

Conversations that resume from another process need the same proxy to remain alive because `cproxy` holds response chains in memory. Keep it running in one terminal, then use `cproxy run` for every model-backed app command so each child receives the proxy environment:

```bash
# Terminal 1
cproxy serve --port 8113 --chains-max 500

# Terminal 2
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent serve
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent opinion-run
```

Do not restart `cproxy` while a local run is awaiting Telegram input; a restarted proxy cannot resume the prior in-memory response chain.

## Commands

```bash
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent serve
uv run opinions-agent init-runtime     # ensure data dirs, memory files, repo checkout, DB migrations
uv run opinions-agent sync             # Reader -> filesystem corpus
uv run opinions-agent opinion-cycle    # create a production-style weekly cycle
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent opinion-run
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent sample-run W04
uv run opinions-agent sample-session init review --opinions-file OPINIONS.md
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent sample-session run review W04 --send-telegram
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent sample-session poll review
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent eval run --weeks W04 W05
uv run opinions-agent abandon-run ID   # abandon a stuck pending or running run
uv run opinions-agent retry-cycle ID   # retry the stopped current batch from its fixed bundle
cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent telegram-poll
uv run opinions-agent set-telegram-webhook https://your-service.up.railway.app/telegram/webhook
```

Useful `opinion-run` flags: `--deterministic-agent` (no model calls), `--skip-sync`,
`--window-start/--window-end` (ISO timestamps, override the default seven-day window).

`sample-run W04` maps `W04` to the fourth chronological seven-day window in the local corpus, starting from the Monday
of the earliest dated highlight. It creates a readable run directory named `<timestamp>-W04` under `.runs/active/`,
copies the configured corpus plus a chosen opinions file into that directory, initializes a disposable local git remote,
and runs the normal agent workflow against those copied paths. The agent cannot read or write the original opinion repo
files during a sample run. Use `--opinions-file PATH` to choose the seed file; it defaults to `OPINIONS.md` in the
current working directory. If no sources file is supplied, sample setup derives `OPINIONS_SOURCES.jsonl` from inline
`<!-- sources: ... -->` comments and the copied corpus evidence rows. By default, sample runs use fake Telegram and
write review files only; pass `--send-telegram` to send the sample run's Telegram messages to the configured allowed
chat.

Use `sample-session` when you want to walk through several weeks against the same isolated copied state. `init` creates
`.runs/sessions/<name>/` with a copied corpus, copied opinion artifacts, local SQLite database, and disposable local git
remote. `run <name> W04` starts a week run against that session copy, and `poll <name>` processes Telegram responses
until the active run completes. Later weeks in the same session start from the session's updated `OPINIONS.md`, source
rows, memory files, and decision log; commits go only to the session's local `remote.git`, not the real opinions repo.

Deterministic local smoke run without Telegram sends:

```bash
OPINIONS_FAKE_TELEGRAM=1 uv run opinions-agent opinion-run --deterministic-agent
```

## Railway

Create two Railway services from this repository. Give the web service `railway.toml`. Give the cron service
`railway.cron.toml` as its custom config path.

- Attach one volume to the web service only. `OPINIONS_DATA_DIR`, `RUNS_DIR`, and `OPINIONS_REPO_DIR` default to
  `$RAILWAY_VOLUME_MOUNT_PATH/{readwise,runs,opinions-repo}` when the mount env var is present, or set them
  explicitly (e.g. `/app/data/readwise`). Volumes mount at container start, so all filesystem initialization is
  runtime work (`init-runtime`), never build time.
- Keep `OPINIONS_REPO_URL` free of credentials. Put a fine-grained repository token in `OPINIONS_GIT_TOKEN`.
  Grant it content read/write access only to the opinions repository.
- Set `RAILPACK_DEPLOY_APT_PACKAGES=git` on the web service. The runtime uses git to clone and push the opinions
  repository.
- Set `OPENAI_API_KEY` for direct model access. Railway does not use local-only `cproxy` or Codex CLI authentication.
- Keep the web service at one replica. The checked-in command initializes storage and migrations before `serve`.
- Set `OPINIONS_START_URL=https://<web-domain>/internal/opinion-cycle/start` and the same random
  `OPINIONS_START_SECRET` on both services. The cron service needs only those two values.
- Choose one weekly UTC cron schedule in the Railway cron service settings. The cron only sends the start request.
- Set the launch boundary to Monday at 00:00 UTC. Each cycle processes the next complete seven-day window, even while catching up.
- Register `https://<web-domain>/telegram/webhook` with `set-telegram-webhook`. Use the configured webhook secret.
- Enable Railway volume backups for the mounted data directory; the opinions repo is separately durable via git.

For staging, use separate PostgreSQL, volume, Telegram credentials, repository token, and disposable repository or
branch. Set `OPINIONS_ENVIRONMENT=staging` and `OPINIONS_TARGET_FILE=TEST_OPINIONS.md`. For production, set
`OPINIONS_ENVIRONMENT=prod` and `OPINIONS_TARGET_FILE=OPINIONS.md`. Both require
`OPINIONS_SOURCES_FILE=OPINIONS_SOURCES.jsonl` and an explicit `OPINIONS_INITIAL_EVIDENCE_AFTER` timestamp. This
timestamp is the oldest evidence version that the first cycle can assign.

Complete one staging cycle before production. Test a repeated same-week start and one stopped-batch retry. Then enable
backups and promote the same commit and configuration shape to production.

Smoke checklist after a deploy:

1. `curl https://<service>/healthz` returns `{"status":"ok"}`.
2. `init-runtime` logged `runtime initialized` (dirs, repo checkout, migrations).
3. `cron-trigger` returns a cycle ID. A repeated request returns the active cycle.
4. Answering all required current-turn messages, or sending exact `GO` / `SKIP`, resumes the same agent conversation.
   Successful approved changes push a commit to the opinions repo touching only `OPINIONS.md` and
   `OPINIONS_SOURCES.jsonl`.
5. After every batch succeeds, the next batch starts automatically. The cycle folder moves to `completed/` last.

If validation, commit, or push fails, the cycle stops. Inspect its recovery archive, then run `retry-cycle ID`.
The retry uses the stored batch. It does not select evidence again.

## Testing

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

The e2e test uses a disposable local git remote, the deterministic agent, and simulated Telegram updates. The required
developer completion gate for real ThinHarness/native-output behavior is isolated behind an explicit environment flag:

```bash
OPINIONS_RUN_REAL_E2E=1 cproxy run --port 8113 --chains-max 500 -- uv run pytest tests/test_real_e2e_optional.py
```

## Evals

`eval/opinion_targets.jsonl` is the checked-in ground truth converted from `EVAL_TARGETS.md`: per eval week it lists canonical target opinions (ideal text, required source evidence IDs, source quotes) and the selected evidence that should not become opinions. `cproxy run --port 8113 --chains-max 500 -- uv run opinions-agent eval run --weeks W04 ... W13` runs the initial proposal phase for each week in a disposable sample run (fake Telegram, no approvals, seeded with the base `OPINIONS.md` plus canonical targets from earlier eval weeks), parses the proposal messages, and streams a Braintrust experiment with three scores: `evidence_recall` and `evidence_precision` (deterministic evidence classification) and `opinion_quality` (binary LLM judge via the Braintrust proxy: pass only when a generated opinion contains all core concepts of the canonical one; extra content is fine). The targets file also syncs to the `opinion-targets` Braintrust dataset for browsing; the checked-in file remains the source of truth. Experiment rows are tagged with their week, and agent traces nest under the experiment. Flags: `--deterministic-agent` (pipeline smoke; replaces the agent's model calls, but the judge still calls the Braintrust proxy for weeks with targets), `--experiment`, `--max-concurrency`.

`uv run opinions-agent eval rescore --from-experiment NAME` re-scores an existing experiment's stored outputs into a
new experiment without re-running the agent — the cheap loop for judge calibration.

## Artifacts

`.readwise/` and `.runs/` are gitignored because they can contain Reader content and run bundles. ThinHarness local
traces use its default location under `~/.thinharness/traces/`; disable plaintext local traces in deployed environments
with `THINHARNESS_DISABLE_LOCAL_TRACING=1`.
