# Filesystem Readwise Opinions Workflow Plan

## Goal

Replace the current Readwise summary prototype with a filesystem-first corpus and an opinion-proposal workflow that:

- Syncs Readwise Reader documents, summaries, full content, and highlights into a durable corpus.
- Selects current-window highlights deterministically for each weekly or biweekly run.
- Lets the agent propose opinion changes against the selected highlights and the current opinions repo.
- Requires Telegram approval before mutating `OPINIONS.md` or `OPINIONS_SOURCES.jsonl`.
- Preserves traceability from each opinion to the highlights that support it.
- Runs locally and on Railway without assuming access to `/Users/ryanbrown/code/ryanbbrown`.

This plan intentionally keeps the first agent simple. Flexible memory files are created as part of the storage shape, but the initial prompt does not ask the agent to write to memory yet.

## Decisions

- The durable Readwise corpus is file-based, not SQL.
- The database remains the operational state store for runs, Telegram idempotency, statuses, ThinHarness resume state, commit metadata, and failure details.
- The primary highlight query surface is one global `.readwise/highlights.jsonl`.
- Current-run selected highlights are prepared by deterministic app code, not selected by the agent.
- Run bundles are not future context. They are active-run/debug artifacts only, and the agent must not read sibling run folders.
- The agent may search the global highlight corpus for historical context when needed.
- The app owns sync state, workflow cursor state, approval state, file mutations, and git commits.
- The agent proposes changes; the app applies approved changes.
- `OPINIONS.md` remains clean and public-facing, with hidden stable opinion IDs.
- `OPINIONS_SOURCES.jsonl` is committed next to `OPINIONS.md` and stores machine-readable provenance from opinions to highlights, including full highlight text.
- `opinion-decisions.jsonl` stores accepted/rejected proposal history for future agent context.
- On Railway, durable files live under a Railway volume mount. The opinions repo is cloned or updated at runtime into a configured writable directory.
- V1 enforces one active opinion run at a time. If a previous run is pending approval or revision, the scheduler exits without starting another run.
- V1 assumes one Railway web worker plus DB-backed idempotency for webhook safety. It does not add custom filesystem locking.

## Railway Constraints

Railway deploys from the application repository, not from local `/Users/ryanbrown/...` paths. The service can be connected to a GitHub repo for builds and deploys, but the target opinions repo must be fetched at runtime through git credentials or a future GitHub API adapter.

Railway volumes provide a persistent read/write directory mounted into the service container at runtime. Railway documents that the mount point is available to the service as a directory, and that relative paths only persist if the mounted path includes the app path, for example `/app/data`. Volumes are mounted when the container starts, not during build or pre-deploy commands. Railway also supports scheduled/manual backups for volume data.

Plan implications:

- Use `OPINIONS_DATA_DIR`, defaulting locally to `.readwise`, and on Railway to `$RAILWAY_VOLUME_MOUNT_PATH/readwise` or `/app/data/readwise`.
- Use `RUNS_DIR`, defaulting locally to `.runs`, and on Railway to `$RAILWAY_VOLUME_MOUNT_PATH/runs` or `/app/data/runs` so pending Telegram revision state survives restarts.
- Use `OPINIONS_REPO_DIR`, defaulting locally to `/Users/ryanbrown/code/ryanbbrown`, and on Railway to `$RAILWAY_VOLUME_MOUNT_PATH/opinions-repo` or `/app/data/opinions-repo`.
- Perform repo clone/update and filesystem initialization at runtime, not build time.
- Configure Railway volume backups for `.readwise`, active run state, and the cloned repo working tree if it holds unpushed state.

References:

- Railway volumes: https://docs.railway.com/volumes
- Railway volume reference: https://docs.railway.com/volumes/reference
- Railway volume backups: https://docs.railway.com/volumes/backups
- Railway services from GitHub repo: https://docs.railway.com/services

## Durable Filesystem Layout

```text
<OPINIONS_DATA_DIR>/
  state.json
  documents.jsonl
  highlights.jsonl
  opinion-decisions.jsonl
  documents/
    reader_<reader_document_id>.md
  raw/
    reader_<reader_document_id>.json
  memory/
    themes.md
    preferences.md
    open-questions.md

<RUNS_DIR>/
  active/
    <run_id>/
      brief.md
      selected-highlights.jsonl
      selected-documents.jsonl
      agent-output.json
  completed/
    <run_id>/
      final.json
```

`<RUNS_DIR>` stores active-run/debug artifacts. Durable workflow state, including run status, Telegram message mapping, callback idempotency, and ThinHarness `resume_state`, remains in the database. Future runs do not receive read access to old run directories. Completed run artifacts are retained for 30 days by default and are configurable.

The opinions repo checkout is separate:

```text
<OPINIONS_REPO_DIR>/
  OPINIONS.md
  OPINIONS_SOURCES.jsonl
```

## Corpus Files

### `state.json`

App-owned sync and workflow cursor state. The agent does not write this file.

```json
{
  "schema_version": 1,
  "sync": {
    "readwise_export_updated_after": "2026-06-12T10:00:00Z",
    "reader_updated_after": "2026-06-12T10:00:00Z",
    "last_success_at": "2026-06-12T10:02:00Z"
  },
  "workflow": {
    "last_completed_window_start": "2026-06-01T00:00:00Z",
    "last_completed_window_end": "2026-06-12T00:00:00Z"
  }
}
```

`sync` tracks what the importer has downloaded or refreshed. `workflow` tracks the last fully terminal scheduled opinion window. The workflow cursor is advanced only after every proposal in a run reaches a terminal decision and any approved file changes have been committed.

### `documents.jsonl`

One normalized document row per Reader document. This is the document summary/index surface.

```json
{"document_id":"reader:01gwfvp9pyaabcdgmx14f6ha0","reader_id":"01gwfvp9pyaabcdgmx14f6ha0","title":"Example Article","author":"Jane Doe","source_url":"https://example.com/article","summary":"Reader generated summary.","tags":["ai","writing"],"saved_at":"2026-06-01T12:00:00Z","updated_at":"2026-06-10T09:00:00Z","content_path":"documents/reader_01gwfvp9pyaabcdgmx14f6ha0.md","raw_path":"raw/reader_01gwfvp9pyaabcdgmx14f6ha0.json"}
```

### `highlights.jsonl`

One normalized highlight row per highlight. This is the primary time-window corpus.

The row is intentionally denormalized with document title, summary, and content path so the first agent pass does not need joins.

```json
{"highlight_id":"rw:456","document_id":"reader:01gwfvp9pyaabcdgmx14f6ha0","reader_id":"01gwfvp9pyaabcdgmx14f6ha0","document_title":"Example Article","document_author":"Jane Doe","document_summary":"Reader generated summary.","source_url":"https://example.com/article","text":"Highlight text here.","note":"My note.","color":"yellow","highlighted_at":"2026-06-10T14:00:00Z","highlighted_date":"2026-06-10","highlighted_week":"2026-W24","updated_at":"2026-06-10T14:03:00Z","content_path":"documents/reader_01gwfvp9pyaabcdgmx14f6ha0.md"}
```

### `documents/<id>.md`

Readable full article/document text. The agent reads this only when highlights plus summary are insufficient.

### `raw/<id>.json`

Untouched API payloads for debugging, schema drift, and re-import. This is not normal agent context.

Raw files live outside `documents/` so the agent can be given read access to document content without also receiving raw API payloads.

### `opinion-decisions.jsonl`

App-owned proposal decision log. This is durable context the agent can read in future runs to avoid repeating rejected ideas and to understand prior approvals.

```json
{"proposal_id":"prop_001","run_id":"2026-06-12T100000Z","decision":"approved","kind":"add_opinion","opinion_id":"opinion-000013","supporting_highlight_ids":["rw:456","rw:789"],"decided_at":"2026-06-12T10:30:00Z"}
{"proposal_id":"prop_002","run_id":"2026-06-12T100000Z","decision":"rejected","kind":"add_opinion","proposed_title":"AI tools should explain themselves","supporting_highlight_ids":["rw:999"],"decided_at":"2026-06-12T10:31:00Z"}
```

The system does not track rejected highlights. Highlights are source evidence. The decision log tracks accepted or rejected opinion proposals.

## Opinions Files

### `OPINIONS.md`

Human-facing, public-friendly opinions file. Each opinion has a hidden stable ID.

```md
# OPINIONS

<!-- opinion-id: opinion-000013 -->
## 13. Small tools should make their state legible

A tool that hides its state makes users debug vibes instead of systems. Durable files, narrow logs, and clear checkpoints are often better than an opaque database.
```

The visible number can change later if opinions are reordered, but the hidden `opinion-id` is durable.

### `OPINIONS_SOURCES.jsonl`

Machine-readable provenance from opinions to supporting highlights.

```json
{"opinion_id":"opinion-000013","highlight_id":"rw:456","document_id":"reader:01gwfvp9pyaabcdgmx14f6ha0","document_title":"Example Article","source_url":"https://example.com/article","highlight_text":"A tool should make state inspectable...","added_at":"2026-06-12T10:00:00Z"}
```

This public file lets the agent understand why an existing opinion exists without cluttering `OPINIONS.md` with public footnotes. V1 stores full highlight text because the expected source corpus is public web content.

## Sync Workflow

1. Load `state.json`.
2. Fetch updated Reader/Readwise data.
3. Normalize documents and highlights.
4. Upsert `documents.jsonl` by `document_id`.
5. Upsert `highlights.jsonl` by `highlight_id`.
6. Write or refresh `documents/<id>.md`.
7. Write `raw/<id>.json`.
8. Atomically update `state.json` only after all corpus writes succeed.

Implementation notes:

- Prefer structured JSON parsing and atomic file replacement.
- Store ISO timestamps in UTC.
- Store derived `highlighted_date` and `highlighted_week` for convenience even after ThinHarness gains `gt/gte/lt/lte` JSONL filters.
- Keep raw payloads, but do not use raw files as normal agent context.

Verification:

- Fixture sync creates expected corpus files.
- Re-running fixture sync does not duplicate document or highlight rows.
- Failed sync does not advance `state.json`.
- `content.md` path in `documents.jsonl` and `highlights.jsonl` resolves under `OPINIONS_DATA_DIR`.

## Selection Workflow

1. Determine run range from CLI/scheduler configuration.
2. Refuse to start if the database has any active run in a non-terminal status.
3. Load `state.json` and use `workflow.last_completed_window_end` as the default lower bound.
4. Load `highlights.jsonl`.
5. Select highlights in the current window.
6. Create a database run record with status `pending_agent`.
7. Write `<RUNS_DIR>/active/<run_id>/selected-highlights.jsonl`.
8. Write `<RUNS_DIR>/active/<run_id>/selected-documents.jsonl` with one row per selected document.
9. Write `<RUNS_DIR>/active/<run_id>/brief.md`.

The agent should read all selected highlights during the initial pass because selected highlights are already the curated run input.

Verification:

- A pending active run prevents creating another run.
- The workflow cursor advances only after all proposals from the run are terminal and committed changes, if any, are pushed.
- Failed retry behavior is explicit in tests.
- Selected highlights include document summary and content path.
- Current run bundle does not include unrelated old run files.

## Agent Read/Write Boundary

Initial agent read access:

- Current active run directory only: `<RUNS_DIR>/active/<run_id>/`.
- Corpus index files: `<OPINIONS_DATA_DIR>/documents.jsonl`, `<OPINIONS_DATA_DIR>/highlights.jsonl`.
- Opinion decision log: `<OPINIONS_DATA_DIR>/opinion-decisions.jsonl`.
- Document content directory: `<OPINIONS_DATA_DIR>/documents/`.
- Memory directory: `<OPINIONS_DATA_DIR>/memory/`.
- Opinions files: `<OPINIONS_REPO_DIR>/OPINIONS.md`, `<OPINIONS_REPO_DIR>/OPINIONS_SOURCES.jsonl`.

Initial agent write access:

- None for corpus, decision-log, state, or opinions files.
- No memory writes in v1, even though the directory exists.

Future work can grant controlled memory writes after the workflow is clearer.

The agent must not read:

- Sibling or completed run directories.
- Raw API payloads unless explicitly added for debugging.
- Git internals.

## Initial Agent Instruction Shape

The agent should receive a brief like:

```text
You help maintain Ryan's OPINIONS.md: a living set of durable beliefs, principles, heuristics, and taste judgments.

Read all selected highlights first. Each selected highlight includes document title, generated summary, highlight text, notes, timestamps, and a path to full content.

Use document summaries and highlights as your primary evidence. Read full document content only when the summary/highlights are insufficient, ambiguous, or potentially misleading.

Read OPINIONS.md to avoid duplicate opinions and to understand the current style. Read OPINIONS_SOURCES.jsonl to understand which highlights already support existing opinions.

Read opinion-decisions.jsonl to avoid repeating rejected proposals and to understand recently accepted proposal history.

Propose only opinion-worthy changes. An opinion-worthy item is a reusable belief, principle, heuristic, or judgment Ryan might want to stand behind later. Do not merely summarize articles. Do not propose claims that are only interesting facts, news, or one-off observations.

Consider four proposal types:

1. Add a new opinion when selected highlights support a durable new belief.
2. Update an existing opinion when new evidence clarifies, narrows, strengthens, or corrects it.
3. Remove an existing opinion when new evidence makes it stale, wrong, redundant, or too weak.
4. Add new sources to an existing opinion when selected highlights support it without requiring text changes.

For each proposal, include the supporting highlight IDs and a short rationale. Current selected highlights are the only source for new proposals. Historical highlights may be searched for context, conflict checking, or support comparison, but do not treat old highlights as fresh evidence unless the current selected highlights independently justify the action.

Return structured output only. Do not write files. The app will request Telegram approval before applying any change.
```

## Agent Output Contract

Replace the current summary-focused output with an opinion-change proposal.

Sketch:

```python
class OpinionProposalOutput(BaseModel):
    status: Literal["awaiting_user", "needs_more_work"]
    proposals: list[OpinionChangeProposal]
    telegram_messages: list[TelegramMessageSpec]

class OpinionChangeProposal(BaseModel):
    proposal_id: str
    kind: Literal["add_opinion", "update_opinion", "remove_opinion", "add_sources"]
    opinion_id: str | None
    title: str | None
    current_text: str | None
    proposed_text: str | None
    rationale: str
    supporting_highlight_ids: list[str]
```

Telegram message text should be per proposal. Each proposal/action gets its own Telegram message with Approve, Reject, and Revise buttons.

Verification:

- Deterministic fake agent can emit all four proposal types.
- Structured output validation catches missing proposal IDs and unsupported proposal kinds.
- Real ThinHarness path returns parseable structured output.

## Telegram Approval Workflow

1. Agent returns proposal batch.
2. App stores `agent-output.json` and outbound Telegram intent rows/file records.
3. App sends one Telegram approval message per proposal.
4. User chooses Approve, Reject, or Revise for each proposal.
5. Approve applies that proposal.
6. Reject records a rejected proposal decision and does not mutate opinions files.
7. Revise resumes the agent with user feedback and the same active run context.
8. The run becomes terminal only after all proposals are approved or rejected, or the run is explicitly abandoned.

Verification:

- Duplicate Telegram updates are idempotent.
- Stale callbacks do not mutate completed runs.
- Revision failure leaves run state inspectable and retryable.

## Applying Approved Changes

The app applies approved proposals, not the agent.

Allowed mutations:

- `OPINIONS.md`
- `OPINIONS_SOURCES.jsonl`
- `<OPINIONS_DATA_DIR>/opinion-decisions.jsonl`
- `<OPINIONS_DATA_DIR>/state.json`
- database run/proposal state

Proposal handling:

- `add_opinion`: append a new opinion with the next stable ID and visible number.
- `update_opinion`: replace only the body/title of the target opinion ID.
- `remove_opinion`: physically delete the target opinion from `OPINIONS.md`. Git history is the recovery path.
- `add_sources`: append source rows only.

After applying opinions changes:

1. Validate `OPINIONS.md` stable IDs are unique.
2. Validate every `OPINIONS_SOURCES.jsonl` `opinion_id` exists in `OPINIONS.md`.
3. Validate every proposed supporting highlight ID exists in `highlights.jsonl`.
4. Append an accepted or rejected row to `opinion-decisions.jsonl`.
5. If all proposals in the run are terminal, advance the workflow cursor in `state.json`.
6. Commit only allowed opinions repo files.

Git commit allowed files:

- `OPINIONS.md`
- `OPINIONS_SOURCES.jsonl`

`state.json` and `opinion-decisions.jsonl` live in the app data volume, not in the public opinions repo.

Verification:

- Commit includes only allowed opinions files.
- Dirty unrelated files in the cloned opinions repo are left alone.
- Failed push leaves run state failed with recovery instructions.

## Railway Deployment Shape

Environment variables:

```text
OPINIONS_DATA_DIR=/app/data/readwise
RUNS_DIR=/app/data/runs
OPINIONS_REPO_URL=https://<token>@github.com/ryanbbrown/ryanbbrown.git
OPINIONS_REPO_BRANCH=main
OPINIONS_REPO_DIR=/app/data/opinions-repo
OPINIONS_TARGET_FILE=OPINIONS.md
OPINIONS_SOURCES_FILE=OPINIONS_SOURCES.jsonl
OPINIONS_GIT_AUTHOR_NAME=opinions-agent
OPINIONS_GIT_AUTHOR_EMAIL=opinions-agent@example.com
```

Runtime startup should:

- Ensure data directories exist.
- Ensure memory placeholder files exist.
- Ensure the opinions repo checkout exists and is on the configured branch.
- Run DB migrations for operational state.

Scheduler:

- Railway cron or scheduled job runs `uv run opinions-agent daily-run` or a renamed `opinion-run`.
- Run frequency defaults to weekly; biweekly can be configured by date range logic rather than folder structure.

Webhook:

- FastAPI service handles Telegram replies.
- Pending active run status, Telegram idempotency, outbound message IDs, proposal decisions, and ThinHarness `resume_state` live in the database so approval/revision survives redeploys.

Backups:

- Enable Railway volume backups for the mounted data directory.
- The public opinions repo is separately durable through git.

## Implementation Phases

### Phase 1: Filesystem primitives

- Add path config for `OPINIONS_DATA_DIR`, `OPINIONS_SOURCES_FILE`, and durable `RUNS_DIR`.
- Implement atomic JSON/JSONL helpers.
- Implement corpus read/write helpers for `documents.jsonl`, `highlights.jsonl`, `opinion-decisions.jsonl`, and `state.json`.
- Add tests with temp directories.

### Phase 2: Sync import

- Replace current DB Readwise corpus storage with filesystem sync. Keep the DB for operational workflow state.
- Normalize fixture payloads into corpus files.
- Add content markdown conversion if Reader returns HTML.
- Make the Readwise Export API vs. Reader API join explicit before implementation. The plan expects Reader document summaries/full content and highlight rows with stable IDs.

### Phase 3: Selection and active run state

- Implement deterministic selection from `highlights.jsonl` plus `state.json` workflow cursor.
- Refuse to start a new scheduled run while any non-terminal run exists in the DB.
- Write active run bundle.
- Restrict agent read paths to current run, corpus indexes, document markdown files, memory, opinion decision log, and opinions files.

### Phase 4: Opinion proposal agent

- Introduce opinion proposal Pydantic models.
- Update ThinHarness prompt and structured output type.
- Keep deterministic fake agent for tests.
- Telegram message generation remains app-owned from structured output.

### Phase 5: Apply approved proposals

- Implement `OPINIONS.md` parser/updater using stable IDs.
- Implement `OPINIONS_SOURCES.jsonl` append/validation.
- Implement `opinion-decisions.jsonl` append and `state.json` workflow cursor updates.
- Update git helper to commit an allowed file set.

### Phase 6: Railway readiness

- Update README with volume setup, env vars, and runtime clone behavior.
- Ensure startup/init command handles mounted volume.
- Add a Railway smoke checklist.
- Run local deterministic e2e against a disposable opinions repo.

## Test Plan

Run before declaring implementation complete:

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

Targeted tests:

- Corpus upsert idempotency.
- Sync state is not advanced on failed sync.
- Workflow cursor is not advanced until every proposal in the run is terminal.
- Starting a run is refused while another run is active.
- Active run bundle is current-run only.
- Agent read paths do not include old run folders or raw payload files.
- Opinion parser preserves IDs.
- New opinion append assigns next stable ID.
- Update opinion changes only target opinion.
- Remove opinion physically deletes only the target opinion.
- Add sources appends provenance without opinion text changes.
- Per-proposal Telegram approval applies only the approved proposal.
- Git helper commits only `OPINIONS.md` and `OPINIONS_SOURCES.jsonl`.
- Telegram duplicate/stale handling remains idempotent.
- Deterministic end-to-end: sync fixture, select highlights, propose changes, approve, update opinions/sources/decision log/state cursor, commit allowed files.

## Open Questions

- Which exact API path should be the v1 source of truth for highlights and Reader document joins: Readwise v2 export plus Reader v3 enrichment, or Reader v3 highlight documents with parent IDs?
- Should opinion stable IDs remain sequential (`opinion-000013`) or switch to collision-resistant IDs while keeping visible numbering sequential?
- What recovery behavior should run state use after a git push failure leaves the local checkout ahead of origin?
