# Behavior

This file records durable product behavior so plan reviews can check the intended behavior contract before implementation. It describes externally meaningful behavior, not internal module boundaries.

## Runtime Ownership

### Purpose

The app owns synchronization, evidence selection, proposal workflow state, approval routing, artifact validation, and git commits. The agent receives bounded context, asks for approval on conceptual opinion changes, and edits allowed opinion and context artifacts after approval or revision.

### Requirements

- RUNTIME-1: The agent must not write corpus source files, run bundles, database rows, or git commits directly.
- RUNTIME-2: The agent may write only configured opinion artifacts and configured agent context artifacts, and only as part of the approved opinion-edit workflow.
- RUNTIME-3: The app must validate agent proposal output before storing proposals and must validate opinion artifacts before committing them.
- RUNTIME-4: Local runs and deployed runs use the same workflow; environment variables select local paths, fake Telegram, real Telegram, and repository targets.

## Durable Corpus

### Purpose

The filesystem corpus is the durable, readable store of Reader-derived evidence and app-owned workflow cursor state.

### Requirements

- CORPUS-1: `documents.jsonl` stores one normalized row per Reader parent document.
- CORPUS-2: `highlights.jsonl` stores one normalized row per selected evidence item used by opinion runs.
- CORPUS-3: Reader highlight rows use stable IDs with the `rw:<reader_id>` form.
- CORPUS-4: Reader document-level notes with non-empty `notes` text are represented as evidence rows in `highlights.jsonl` with stable IDs using the `reader-note:<reader_id>` form.
- CORPUS-5: Highlight-attached Reader note rows are stored on their parent highlight row as note text.
- CORPUS-6: `raw/reader_<id>.json` stores untouched Reader API payloads for debugging and recovery, but raw payloads are not part of the default agent read surface.
- CORPUS-7: `documents/reader_<id>.md` stores readable full document content for agent inspection when summaries and selected evidence are insufficient.
- CORPUS-8: `state.json` stores app-owned sync and workflow cursors, including the Reader watermark and last completed opinion-run window.
- CORPUS-9: Sync is idempotent and advances `state.json` only after corpus writes succeed.
- CORPUS-10: `memory/` contains placeholder memory files; no automated memory-writing behavior is implemented.
- CORPUS-11: Reader documents tagged `backfill` or `.backfill` and their descendant highlights/notes are excluded from local backtest corpora and should not be selected for opinion runs.

## Run Selection And Bundles

### Purpose

Each opinion run deterministically selects the evidence window, writes an inspectable run bundle, and gives the agent a bounded read surface.

### Requirements

- RUN-1: `opinion-run` refuses to start when another run is in a non-terminal status.
- RUN-2: Unless explicitly overridden, the run window starts at `state.json` `workflow.last_completed_window_end` or defaults to the previous seven days.
- RUN-3: Evidence selection includes rows whose timestamp is `window_start <= highlighted_at < window_end`.
- RUN-4: Selected evidence is sorted oldest-first, with stable ID tie-breaking.
- RUN-5: A run with no selected evidence does not create a database run.
- RUN-6: A created run writes an active run bundle under `RUNS_DIR/active/<run_id>/`.
- RUN-7: The active run bundle contains `brief.md`, `selected-highlights.jsonl`, and `selected-documents.jsonl`.
- RUN-8: The agent read surface includes the active run bundle, corpus indexes, readable document content, memory files, current opinion files, opinion provenance files, and agent-maintained decision context.
- RUN-9: Raw Reader payloads, old run directories, git internals, and app state files are excluded from the default agent read surface.
- RUN-10: Completed runs move from `active/` to `completed/` and write a `final.json` summary.
- RUN-11: Completed run directories are cleaned up according to `OPINIONS_COMPLETED_RUN_RETENTION_DAYS`.

## Agent Runtime Shape

### Purpose

An opinion run is handled as one resumable agent conversation. The app pauses and resumes that conversation around Telegram approval and revision events while retaining ownership of operational state, validation, and git durability.

### Requirements

- AGENT-1: Proposal generation, revision handling, approval follow-up, artifact editing, artifact validation, and final user-facing responses are turns in the same resumable agent conversation for a run.
- AGENT-2: The app must not model proposal generation and artifact editing as separate harness definitions, independent agents, or per-proposal agent products.
- AGENT-3: The agent uses one harness definition with a bounded read surface that supports direct reads, directory discovery, text search, and JSONL search over allowed context.
- AGENT-4: The agent write surface is always limited to configured opinion artifacts and configured agent context artifacts. The agent must not edit opinion artifacts before approval or revision decisions permit artifact edits, and the app must not commit artifact edits until the approved edit workflow has completed and validation passes.
- AGENT-5: Structured agent output is for app-owned communication and status boundaries, such as Telegram proposal messages, completion state, and summaries. It is not an app-interpreted file-mutation command language.
- AGENT-6: When writes are allowed, the agent edits files directly with filesystem tools and validates those edits with the app-provided validation tool before completing the edit turn.

## Proposal And Editing Workflow

### Purpose

The agent proposes conceptual opinion changes, gets human approval or revision through Telegram, and then edits the allowed opinion and context artifacts directly within the write boundary.

### Requirements

- PROPOSAL-1: The agent proposes conceptual opinion changes for approval, not exact patches for the app to apply.
- PROPOSAL-2: A conceptual proposal may add, revise, remove, merge, split, reorder, or attach evidence to opinions.
- PROPOSAL-3: The app stores proposal, approval, rejection, and revision context as operational workflow state, but does not interpret proposal categories as file-mutation commands.
- PROPOSAL-4: Supporting evidence for proposals must come from the current run's selected evidence, not merely from historical corpus rows.
- PROPOSAL-5: User approval or revision applies to the conceptual change. The final file edits may differ from the original proposal when the user gives revision feedback.
- PROPOSAL-6: After approval or revision decisions are available, the agent edits the allowed opinion and context artifacts directly to reflect the accepted conceptual changes.
- PROPOSAL-7: The app provides deterministic artifact validation to the agent as a tool. The agent must successfully validate its edits before completing the approved opinion-edit workflow.
- PROPOSAL-8: The app does not normalize, deduplicate, repair, or otherwise rewrite agent-edited artifacts. It may run the same validation once after the agent completes as a final guard before committing.
- PROPOSAL-9: A run with an empty successful proposal batch completes and advances the workflow cursor.

## Telegram Approval

### Purpose

Telegram provides human approval or revision for every proposed conceptual opinion change before the agent edits opinion artifacts.

### Requirements

- TELEGRAM-1: The app sends one Telegram approval message per pending conceptual proposal with Approve, Reject, and Revise actions.
- TELEGRAM-2: Only `TELEGRAM_ALLOWED_CHAT_ID` may approve, reject, or revise proposals.
- TELEGRAM-3: Telegram callbacks and reply messages are idempotent and scoped to current pending proposals.
- TELEGRAM-4: Revision feedback supersedes only pending proposals in the active batch; already approved conceptual decisions remain accepted.
- TELEGRAM-5: A failed revision marks the run failed and records the failure reason.
- TELEGRAM-6: Approve, Reject, and Revise interactions record user decisions but do not by themselves start the approved edit workflow while other proposals in the active batch remain pending.
- TELEGRAM-7: The approved edit workflow starts when every proposal in the active batch has been addressed, or when the allowed user sends exactly `GO` or `SKIP` as a standalone uppercase message.
- TELEGRAM-8: A standalone `GO` message is valid only from `TELEGRAM_ALLOWED_CHAT_ID`, only for an active run with at least one addressed proposal, and only when the message text is exactly `GO`.
- TELEGRAM-9: When `GO` starts the approved edit workflow before every proposal is addressed, still-pending proposals remain pending and actionable after the addressed subset is processed.
- TELEGRAM-10: A standalone `SKIP` message is valid only from `TELEGRAM_ALLOWED_CHAT_ID`, only for an active run with at least one pending proposal, and only when the message text is exactly `SKIP`.
- TELEGRAM-11: When `SKIP` starts the approved edit workflow before every proposal is addressed, still-pending proposals in the active batch are finalized as deferred for that run.
- TELEGRAM-12: Free-text messages other than valid revision replies, standalone `GO`, or standalone `SKIP` do not start agent work.

## Opinion Files And Provenance

### Purpose

Accepted opinions and accepted supporting evidence are durable artifacts owned by the opinions repository, not transient runtime state.

### Requirements

- OPINIONS-1: `OPINIONS.md` stores the current accepted opinions.
- OPINIONS-2: Each opinion has a stable `opinion-000001` style ID stored as a hidden HTML comment directly under the opinion it identifies.
- OPINIONS-3: The canonical `OPINIONS.md` format is grouped by `##` section headings, with each opinion represented as one Markdown bullet line followed by indented metadata comments. The bullet is usually one sentence but may contain multiple sentences on the same Markdown line.
- OPINIONS-4: Opinion metadata comments use this shape:

```markdown
## Section

- Opinion sentence.
  <!-- opinion-id: opinion-000001 -->
  <!-- sources: rw:..., reader-note:... -->
```

- OPINIONS-5: Agent edits preserve existing section groupings, opinion IDs, bullet text, and metadata comments except where the approved conceptual change requires an edit.
- OPINIONS-6: `OPINIONS_SOURCES.jsonl` stores one row per supporting evidence item for each accepted opinion, so multiple rows may reference the same opinion ID.
- OPINIONS-7: Source rows include the opinion ID, evidence ID, document ID, document title, source URL, evidence text, and timestamp when the source was attached.
- OPINIONS-8: `OPINIONS_SOURCES.jsonl` is the machine-readable provenance source. Inline `sources` comments in `OPINIONS.md` are useful for local review and human orientation, but they do not replace source rows.
- OPINIONS-9: Approved agent edits may mutate `OPINIONS.md` and `OPINIONS_SOURCES.jsonl` within the allowed write boundary; the app validates the resulting artifacts instead of applying a fixed set of mutation commands.
- OPINIONS-10: Source rows are unique by `(opinion_id, evidence_id)`. Duplicate source rows are invalid and must be fixed by the agent, not silently deduplicated by the app.
- OPINIONS-11: The agent writes stable opinion IDs into `OPINIONS.md`. The app validates IDs but does not allocate, insert, or rewrite them.
- OPINIONS-12: Removed opinion IDs are retired and must not be reused. Validation rejects malformed, missing, duplicate, or retired/reused opinion IDs and source rows that reference missing opinions.

## Git Application

### Purpose

Approved changes become durable after the agent edits the allowed opinion artifacts and the app validates, commits, and pushes only the configured opinions files.

### Requirements

- GIT-1: Before the agent edits approved opinion artifacts, the app ensures the configured opinions repository exists locally, is on the configured branch, and has clean target opinion files.
- GIT-2: After the agent completes, the app validates the edited artifacts once as a final guard before committing. A final validation failure marks the run failed; the app does not repair the artifacts.
- GIT-3: The app commits only `OPINIONS_TARGET_FILE` and `OPINIONS_SOURCES_FILE`, and refuses to commit if staged files include other paths.
- GIT-4: A no-op approved edit produces no commit SHA.
- GIT-5: Push failures mark the run failed and preserve the local commit for manual recovery.

## Decision History

### Purpose

The system keeps compact, agent-maintained history of finalized proposal threads so future runs can learn from approvals, rejections, revisions, and user preferences without reading raw Telegram transcripts.

### Requirements

- DECISION-1: The database stores granular operational conversation state, including Telegram messages, callbacks, agent follow-ups, and user replies.
- DECISION-2: `opinion-decisions.jsonl` is an agent-maintained context artifact, not the operational source of truth.
- DECISION-3: `opinion-decisions.jsonl` stores one compact summary row per finalized conceptual proposal thread, not one row per message, database proposal row, or revision batch.
- DECISION-4: A decision row includes the initial proposed concept, supporting evidence IDs, final outcome, final accepted concept when applicable, affected opinion IDs when known, and a concise summary of important back-and-forth.
- DECISION-5: If the user asks for more context, requests wording changes, or otherwise changes the proposal before deciding, the decision row summarizes that interaction instead of preserving the full transcript.
- DECISION-6: Accepted decision rows describe the conceptual change that was actually accepted, which may differ from the initial proposal.
- DECISION-7: Rejected, superseded, abandoned, or deferred decision rows explain why the thread did not become an opinion when that reason is available.
- DECISION-8: The agent writes or updates the decision row for approved, rejected, superseded, abandoned, and deferred conceptual proposal threads after the thread reaches a terminal outcome.
- DECISION-9: The agent should usually append new decision summaries and should edit prior decision summaries only for explicit memory cleanup or known-error correction.
- DECISION-10: The app may check that `opinion-decisions.jsonl` remains parseable, but it does not semantically validate decision summaries.
- DECISION-11: The decision log is available for audit and targeted inspection, but the agent should not rely on reading the entire log every run as primary long-term memory.
- DECISION-12: Distilled long-term guidance belongs in memory files, but automated memory updates are not currently required.
