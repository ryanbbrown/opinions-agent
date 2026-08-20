# Behavior

This file records durable product behavior so plan reviews can check the intended behavior contract before implementation. It describes externally meaningful behavior, not internal module boundaries.

## Runtime Ownership

### Purpose

The app owns synchronization, evidence selection, Telegram routing, artifact validation, and git commits. The agent receives bounded context and a permanently bounded write surface for configured opinion and context artifacts. The app relies on the agent conversation contract to avoid premature opinion edits, and relies on the shared validator plus git durability gates before committing any artifact changes.

### Requirements

- RUNTIME-1: The agent must not write corpus source files, run bundles, database rows, or git commits directly.
- RUNTIME-2: The agent may write only configured opinion artifacts and configured agent context artifacts. The app does not dynamically grant and revoke file-writing tools by workflow phase; it keeps the write boundary narrow for the whole run.
- RUNTIME-3: The app exposes one deterministic artifact validator to the agent as a tool and runs the same validator once more before committing. There is no separate agent validator and app validator.
- RUNTIME-4: Local runs and deployed runs use the same workflow; environment variables select local paths, fake Telegram, real Telegram, and repository targets.

## Durable Corpus

### Purpose

The filesystem corpus is the durable, readable store of Reader-derived evidence. PostgreSQL owns workflow progress.

### Requirements

- CORPUS-1: `documents.jsonl` stores one normalized row per Reader parent document.
- CORPUS-2: `highlights.jsonl` stores one normalized row per Reader highlight or document-level note.
- CORPUS-3: Reader highlight rows use stable IDs with the `rw:<reader_id>` form.
- CORPUS-4: Reader document-level notes with non-empty `notes` text are represented as evidence rows in `highlights.jsonl` with stable IDs using the `reader-note:<reader_id>` form.
- CORPUS-5: Highlight-attached Reader note rows are stored on their parent highlight row as note text.
- CORPUS-6: `raw/reader_<id>.json` stores untouched Reader API payloads for debugging and recovery, but raw payloads are not part of the default agent read surface.
- CORPUS-7: `documents/reader_<id>.md` stores readable full document content for agent inspection when summaries and selected evidence are insufficient.
- CORPUS-8: `state.json` stores Reader sync watermarks. It does not decide whether evidence was processed.
- CORPUS-9: Sync is idempotent and advances `state.json` only after corpus writes succeed.
- CORPUS-10: `memory/` contains placeholder memory files; no automated memory-writing behavior is implemented.
- CORPUS-11: Reader documents tagged `backfill` or `.backfill` and their descendant highlights/notes are excluded from local backtest corpora and should not be selected for opinion runs.
- CORPUS-12: Tagged Reader documents with summaries are stored as normal document rows; summary-only evidence is synthesized into run bundles instead of being written into `highlights.jsonl`.

## Run Selection And Bundles

### Purpose

Each opinion run deterministically selects the evidence window, writes an inspectable run bundle, and gives the agent a bounded read surface.

### Requirements

- RUN-1: `opinion-run` refuses to start when another run is in a non-terminal status.
- RUN-2: A manual run uses an explicit window or defaults to the previous seven days. Weekly cycles use assignments.
- RUN-3: Evidence selection includes rows whose timestamp is `window_start <= highlighted_at < window_end`. For tagged document-summary evidence, the timestamp is the document `saved_at` time.
- RUN-4: Selected evidence is sorted oldest-first, with stable ID tie-breaking.
- RUN-5: A run with no selected evidence does not create a database run.
- RUN-6: A created run writes an active run bundle under `RUNS_DIR/active/<run_id>/`.
- RUN-7: The active run bundle contains `selected-highlights.jsonl`, `selected-documents.jsonl`, and a `review/` directory for human-readable review artifacts.
- RUN-7A: `selected-highlights.jsonl` is the selected evidence file. It may contain Reader highlights, document-level notes, and synthesized tagged document-summary evidence with IDs using the `reader-summary:<reader_id>` form.
- RUN-8: Human review artifacts include the run summary and initial Telegram message transcript; they are for inspection and are not part of the agent read surface.
- RUN-9: The agent read surface includes selected run evidence files, corpus indexes, readable document content, memory files, current opinion files, opinion provenance files, and agent-maintained decision context.
- RUN-10: Raw Reader payloads, old run directories, git internals, human review artifacts, and app state files are excluded from the default agent read surface.
- RUN-11: Completed runs move from `active/` to `completed/` and write a `final.json` summary.
- RUN-12: Completed run directories are cleaned up according to `OPINIONS_COMPLETED_RUN_RETENTION_DAYS`.
- RUN-13: Local sample runs are disposable run-scoped executions. They copy selected opinion artifacts and corpus context under the run directory, point the agent at those copied paths, and must not grant the agent read/write access to the original opinion repository files.
- RUN-14: Human-readable sample run IDs may include the start timestamp and requested corpus week label so local runs can be inspected chronologically.
- RUN-15: Local sample sessions are disposable session-scoped executions. They copy opinion artifacts and corpus context once, keep database state, run artifacts, memory, decisions, and local git commits under the session directory, and let later week runs start from earlier approved session changes without touching the original opinion repository files.
- RUN-16: A weekly cycle owns one fixed seven-day evidence window, one fixed evidence snapshot, and one or more ordered batches.
- RUN-16A: The first weekly window starts at the fixed launch boundary. Each later window starts when the previous completed window ended.
- RUN-16B: A weekly window ends exactly seven days after it starts. A cycle cannot include evidence from a later weekly window.
- RUN-16C: Weekly windows use UTC boundaries from Monday at 00:00 through the next Monday at 00:00.
- RUN-17: PostgreSQL assigns each evidence ID and content fingerprint to one cycle. Changed content creates a new eligible evidence version.
- RUN-18: A first deployed cycle requires a fixed launch boundary. Older evidence versions become an ignored baseline.
- RUN-19: A cycle uses one batch only below both limits of 20 documents and 50 evidence rows.
- RUN-20: Reaching either limit creates at least two balanced batches. No batch can exceed either limit.
- RUN-21: The partition keeps documents whole when each batch remains within half to one-and-a-half times its equal row target.
- RUN-22: The partition can split a document across adjacent batches when whole-document boundaries produce an uneven result.
- RUN-23: The app writes every batch and fixed same-document critic context before it starts the first run.
- RUN-24: Later corpus changes cannot change a cycle bundle. Only selected evidence in the current batch is citable.
- RUN-25: A completed batch queues the next batch after its accepted repository changes are durable.
- RUN-26: A cycle completes after all batches complete. A cycle with no evidence completes with zero batches.
- RUN-27: Repeated starts for the next weekly window return existing work. An unfinished cycle blocks a later weekly cycle.
- RUN-28: Newly synced or changed evidence remains eligible when its source timestamp is before the current window start. Evidence at or after the current window end remains eligible for a later cycle.
- RUN-29: Recovery leaves a starting cycle unchanged while its start lease is valid. It treats the snapshot as interrupted only after that lease is absent or expired.
- RUN-30: Before a new run sends agent messages, it sends a start notice with the inclusive evidence dates. Multi-batch cycles also show the current batch number and total; single-batch runs omit the batch line.

## Agent Runtime Shape

### Purpose

An opinion run is handled as one resumable agent conversation with one bounded tool surface. The app pauses and resumes that conversation around Telegram approval and revision events while retaining ownership of operational state, validation, and git durability.

### Requirements

- AGENT-1: Proposal generation, revision handling, approval follow-up, artifact editing, artifact validation, and final user-facing responses are turns in the same resumable agent conversation for a run.
- AGENT-2: The app must not model proposal generation and artifact editing as separate harness definitions, independent agents, or per-proposal agent products.
- AGENT-3: The agent uses one harness definition with a bounded read surface that supports direct reads, directory discovery, globbing, text search, and JSONL search over allowed context.
- AGENT-4: The agent write surface is always available and always limited to configured opinion artifacts and configured agent context artifacts. The agent is instructed not to make durable opinion changes before approval or revision decisions justify those changes; the app does not attempt to infer every valid editing moment by toggling write tools.
- AGENT-5: Native structured agent output is for app-owned communication and status boundaries, such as Telegram messages, completion state, and summaries. It is not an app-interpreted file-mutation command language.
- AGENT-6: The agent edits files directly with filesystem tools and validates durable opinion edits with the shared validation tool before reporting the approved workflow complete.
- AGENT-7: The app must not commit artifact edits until the agent returns `done`, the same shared validator passes at the commit boundary, and commit/no-op handling succeeds.
- AGENT-8: If the agent cannot make progress without manual intervention, it returns `blocked`; the app records a terminal blocked or failed run state, sends the explanatory Telegram message, preserves active artifacts for inspection, and does not validate or commit.
- AGENT-9: A successful `done` run sends a final Telegram completion message after validation and commit/no-op handling. If the agent does not provide one, the app sends a deterministic fallback summary of opinion and evidence row changes.
- AGENT-10: The agent runs one fidelity critic for each proposed opinion before it sends proposals.
- AGENT-11: The critic can read cited rows and fixed same-document context. It cannot inspect unrelated documents or edit artifacts.

## Proposal And Editing Workflow

### Purpose

The agent proposes conceptual opinion changes and gets human approval or revision through Telegram. It has the same bounded write surface throughout the run, but durable opinion changes are only committed after the approved workflow reaches a validation-and-commit boundary.

### Requirements

- PROPOSAL-1: The agent proposes conceptual opinion changes for approval, not exact patches for the app to apply.
- PROPOSAL-2: A conceptual proposal may add, revise, remove, merge, split, reorder, or attach evidence to opinions.
- PROPOSAL-3: The app stores Telegram messages, callbacks, replies, `GO`/`SKIP` commands, and agent outputs as operational workflow state, but does not interpret proposal categories as file-mutation commands.
- PROPOSAL-4: Supporting evidence for proposals must come from the current run's selected evidence, not merely from historical corpus rows.
- PROPOSAL-5: User approval or revision applies to the conceptual change. The final file edits may differ from the original proposal when the user gives revision feedback.
- PROPOSAL-6: The app does not decide whether the agent may call file-edit tools on each turn. Instead, the conversation contract tells the agent when opinion edits are appropriate, and the app only treats edits as durable after approval or revision decisions are available and the approved workflow completes.
- PROPOSAL-7: The app provides the shared deterministic artifact validator to the agent as a tool. The agent must successfully validate durable opinion edits before returning `done`.
- PROPOSAL-8: The shared validator is not an editor. It does not normalize, deduplicate, allocate IDs, repair comments, or otherwise rewrite agent-edited artifacts.
- PROPOSAL-9: A run with no opinion-worthy changes may complete with `status="done"` and no artifact commit.

## Telegram Approval

### Purpose

Telegram provides human approval or revision for proposed conceptual opinion changes before those changes become durable committed opinion artifacts.

### Requirements

- TELEGRAM-1: The agent returns one or more Telegram messages as structured output. It will usually return one HTML approval message per conceptual proposal, but the app must allow flexible message counts and layouts. Messages that require user input must include buttons or `force_reply`; plain `awaiting_user` messages can still be advanced by exact `GO` or `SKIP`.
- TELEGRAM-2: The app sends agent-returned Telegram messages as Telegram HTML with deterministic turn/message idempotency keys and stores the real Telegram `chat_id`, `message_id`, full text, buttons, run ID, and raw response/update details needed for idempotency and later resume context.
- TELEGRAM-2A: Proposal messages keep the proposed opinion, section, and source article titles visible. Full evidence text and raw evidence IDs belong inside expandable evidence blocks.
- TELEGRAM-2B: Revised proposal messages preserve the original proposal's visible number and conceptual identity. For example, a revision of `Add Opinion #2` is titled `Add Opinion #2 (Revised)`, not as a new proposal number.
- TELEGRAM-3: Only `TELEGRAM_ALLOWED_CHAT_ID` may drive the run through callbacks, replies, or exact standalone `GO`/`SKIP` commands.
- TELEGRAM-4: Telegram callbacks and reply messages are idempotent and scoped to the stored outbound message they reference by `(chat_id, message_id)`.
- TELEGRAM-5: For callbacks, the app finds the stored outbound message by `(chat_id, message_id)`, verifies the callback data matches a stored button on that message, durably records the callback, answers Telegram's callback query, and attempts to edit the original message to show the selected status and remove its keyboard.
- TELEGRAM-6: For replies, the app finds the stored outbound message being replied to by `(chat_id, message_id)`, durably records the concrete user reply, and attempts to edit the original message to show that a reply was received and remove its keyboard. A free-text reply is contextual feedback, not approval. It may request revision, ask for more context, or explain rejection, but only an approval callback authorizes durable edits for that proposal.
- TELEGRAM-7: Exact standalone `GO` and `SKIP` remain valid Telegram commands only from `TELEGRAM_ALLOWED_CHAT_ID` while a run is awaiting user input.
- TELEGRAM-8: A callback or reply does not by itself resume the agent. The app records individual responses until every outbound message awaiting a user response has been answered.
- TELEGRAM-9: When all expected responses are present, the app atomically claims the run with `awaiting_user -> running_agent` and resumes the same agent conversation with the relevant original message text/buttons plus concrete user actions/replies. If the claim fails, another request already started or completed the resume.
- TELEGRAM-10: Valid exact `GO` and `SKIP` commands attempt the same atomic `awaiting_user -> running_agent` claim immediately, then route the command into the same agent conversation as user input. The app does not itself decide which conceptual proposals are accepted, deferred, skipped, or ready for file edits.
- TELEGRAM-11: Free-text messages other than valid replies to stored outbound messages or exact standalone `GO`/`SKIP` commands do not start agent work.
- TELEGRAM-12: A failed agent resume marks the run failed and records the failure reason.
- TELEGRAM-13: A successful batch starts the next queued batch automatically. Telegram requests do not wait for that model call.
- TELEGRAM-14: A stopped cycle sends one generic failure notice. The notice contains no exception text or credential.
- TELEGRAM-15: Failure to edit an already-sent Telegram message is cosmetic. It does not discard a recorded response, fail the webhook, or block the run from resuming.

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
- OPINIONS-9: Approved agent edits may mutate `OPINIONS.md` and `OPINIONS_SOURCES.jsonl` within the allowed write boundary; the app validates the resulting artifacts with the shared validator instead of applying a fixed set of mutation commands.
- OPINIONS-10: Source rows are unique by `(opinion_id, evidence_id)`. Duplicate source rows are invalid and must be fixed by the agent, not silently deduplicated by the app.
- OPINIONS-11: The agent writes stable opinion IDs into `OPINIONS.md`. The app validates IDs but does not allocate, insert, rewrite, or repair them.
- OPINIONS-12: The app maintains an opinion ID high-water mark as the authoritative reuse guard. Newly introduced opinion IDs must be greater than the high-water mark unless they already existed at the `git HEAD` baseline. The app updates the high-water mark only after validation and commit/no-op handling succeeds.
- OPINIONS-13: Validation rejects malformed, missing, duplicate, or high-water-violating opinion IDs; source rows that reference missing opinions; opinions without machine-readable source rows; inline source comments without matching source rows; and newly added source rows whose metadata does not match the selected run evidence.
- OPINIONS-14: Newly added source rows in a completed run are valid only when their `evidence_id` appears in that run's selected evidence bundle. Historical corpus rows may provide context, but they are not fresh support for new source attachments.
- OPINIONS-15: The ideal source schema uses `evidence_id` only. There is no backwards-compatibility requirement for legacy `highlight_id` source rows.

## Git Application

### Purpose

Approved changes become durable only after the app validates, commits, and pushes the configured opinions files. The agent may have the bounded file-edit tools throughout the run; git durability is the app-owned boundary.

### Requirements

- GIT-1: Before an opinion run starts an agent conversation with access to opinion artifacts, the app ensures the configured opinions repository exists locally, is on the configured branch, and has clean target opinion files.
- GIT-2: After the agent completes, the app runs the same shared validator once as a final guard before committing. The validator compares current working-tree artifacts to the `git HEAD` baseline for the configured opinion files. A final validation failure marks the run failed; the app does not repair the artifacts.
- GIT-3: The app commits only `OPINIONS_TARGET_FILE` and `OPINIONS_SOURCES_FILE`, and refuses to commit if staged files include other paths.
- GIT-4: A no-op approved durable change produces no commit SHA.
- GIT-5: Push failures mark the run failed and preserve the local commit for manual recovery.
- GIT-6: Success-style final Telegram messages are sent only after validation and commit/no-op handling succeed. If validation, commit, or push fails, the app sends an app-authored operational failure message instead of agent success wording.
- GIT-7: Each batch records its repository baseline before agent edits and requires its writable artifacts to be clean.
- GIT-8: A run records commit intent, local commit, remote push, and completion as separate durable phases.
- GIT-9: Restart recovery reconciles stored commit data with local and remote commits before it starts agent work again.
- GIT-10: Failed edits are archived, and only configured writable artifacts are restored from their recorded baseline.
- GIT-11: A retry creates a new run for the stored batch. It never repeats a pushed batch.
- GIT-12: Deployed staging writes `OPINIONS.md` and `OPINIONS_SOURCES.jsonl` only on the `staging` branch.
- GIT-13: Deployed production writes the same artifact names only on the `main` branch.
- GIT-14: Staging and production use separate runtime volumes and databases, so their decision context and workflow state remain isolated.

## Evals And Observability

### Purpose

Opinion quality is measured by running the initial proposal phase against human-verified weekly targets in disposable sandboxes, scored and browsable in Braintrust. Braintrust is also the single external tracing destination for agent runs.

### Requirements

- EVAL-1: `eval/opinion_targets.jsonl` is the reviewed, checked-in source of truth for eval ground truth. The synced Braintrust dataset is a browsable copy, never the source.
- EVAL-2: Ground truth labels every selected evidence row of an eval week as either converted (it backs a canonical target opinion) or not converted. Eval runs fail fast when the targets file no longer matches corpus selection.
- EVAL-3: Each eval week runs independently in a disposable sample run seeded with the base opinions file plus the canonical target opinions of all earlier eval weeks, never with agent output from prior eval runs.
- EVAL-4: Eval runs use fake Telegram, stop after the initial proposal phase, and cannot touch the real opinions repository.
- EVAL-5: Eval scoring covers deterministic evidence conversion recall and precision, plus an LLM judge that grades generated opinions against the canonical opinion text and its source evidence. Judge calls route through the Braintrust proxy.
- EVAL-6: Eval executions land in Braintrust as experiments. Dev and production agent runs land as logs in the same Braintrust project, stamped with an environment tag that defaults to `dev` locally and `prod` on Railway.
- EVAL-7: Braintrust traces carry the same full capture detail as local traces: messages, tool arguments, and tool results.
- EVAL-8: Eval v1 remains the historical proposal-content benchmark. Eval v2 runs the same cases and preserves the v1 quality score while also requiring each matched proposal to use the canonical add or update operation.
- EVAL-9: Eval v2 gives operation-gated quality credit only when conceptual quality passes and the proposal adds a canonical add target or revises the canonical base opinion for an update target. It reports operation correctness separately so content and routing failures remain distinguishable.

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
