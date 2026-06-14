# Behavior

This file records durable product behavior so plan reviews can check the intended behavior contract before
implementation. It describes externally meaningful behavior, not internal module boundaries.

## Runtime Ownership

### Purpose

The app owns synchronization, evidence selection, proposal workflow state, approval handling, opinion file mutation, and
git commits. The agent receives read-only context and returns structured proposal data.

### Requirements

- RUNTIME-1: The agent must not write opinion files, corpus files, run bundles, database rows, or git commits directly.
- RUNTIME-2: The app must validate agent proposal output before storing proposals or mutating opinion files.
- RUNTIME-3: The app must be runnable locally with the same workflow as deployment, with environment variables selecting
  local versus deployed services.
- RUNTIME-4: Local dry runs may use fake Telegram delivery, but the run/proposal/approval code path should remain the
  same as production except for the Telegram client.

## Durable Corpus

### Purpose

The filesystem corpus is the durable, readable store of Reader-derived evidence and app-owned workflow cursor state.

### Requirements

- CORPUS-1: `OPINIONS_DATA_DIR` contains `state.json`, `documents.jsonl`, `highlights.jsonl`,
  `opinion-decisions.jsonl`, `documents/`, `raw/`, and `memory/`.
- CORPUS-2: `documents.jsonl` stores one normalized row per Reader parent document.
- CORPUS-3: `highlights.jsonl` stores one normalized row per selected evidence item used by opinion runs.
- CORPUS-4: Reader highlight rows use stable IDs with the `rw:<reader_id>` form.
- CORPUS-5: Reader document-level notes with non-empty `notes` text are represented as evidence rows in
  `highlights.jsonl` with stable IDs using the `reader-note:<reader_id>` form.
- CORPUS-6: Highlight-attached Reader note rows are stored on their parent highlight row as note text rather than as
  separate evidence rows.
- CORPUS-7: `raw/reader_<id>.json` stores untouched Reader API payloads for debugging and recovery, but raw payloads are
  not part of the default agent read surface.
- CORPUS-8: `documents/reader_<id>.md` stores readable full document content for agent inspection when summaries and
  selected evidence are insufficient.
- CORPUS-9: `memory/` contains durable memory files intended for distilled guidance; no automated memory-writing
  behavior is currently implemented.
- CORPUS-10: Sync state advances only after all corpus writes for the sync succeed.

### Scenarios

- CORPUS-S1: If a sync fails before corpus writes complete, `state.json` must not advance to the failed batch's
  watermark.
- CORPUS-S2: Re-running sync with already-seen documents or evidence must upsert rows by stable ID instead of
  duplicating them.

## Run Selection And Bundles

### Purpose

Each opinion run deterministically selects the evidence window, writes an inspectable run bundle, and gives the agent a
bounded read surface.

### Requirements

- RUN-1: `opinion-run` refuses to start when another run is in a non-terminal status.
- RUN-2: Unless explicitly overridden, the run window starts at `state.json` `workflow.last_completed_window_end` or
  defaults to the previous seven days.
- RUN-3: Evidence selection includes rows whose timestamp is `window_start <= highlighted_at < window_end`.
- RUN-4: Selected evidence is sorted oldest-first, with stable ID tie-breaking.
- RUN-5: A run with no selected evidence does not create a database run.
- RUN-6: A created run writes an active run bundle under `RUNS_DIR/active/<run_id>/`.
- RUN-7: The active run bundle contains `brief.md`, `selected-highlights.jsonl`, and `selected-documents.jsonl`.
- RUN-8: The agent read surface includes the active run bundle, corpus indexes, readable document content, memory files,
  current opinion files, and opinion provenance files.
- RUN-9: Raw Reader payloads, old run directories, git internals, and app state files are excluded from the default
  agent read surface.
- RUN-10: Completed runs move from `active/` to `completed/` and write a `final.json` summary.
- RUN-11: Completed run directories are cleaned up according to `OPINIONS_COMPLETED_RUN_RETENTION_DAYS`.

## Proposal Generation

### Purpose

The agent proposes opinion changes; the app stores proposals as operational workflow state and requests user approval
before applying any change.

### Requirements

- PROPOSAL-1: Agent output must be structured as an `OpinionProposalOutput`.
- PROPOSAL-2: The app supports proposal kinds `add_opinion`, `update_opinion`, `remove_opinion`, and `add_sources`.
- PROPOSAL-3: Proposal IDs must be non-empty and unique within the run batch.
- PROPOSAL-4: `add_opinion` proposals require a title and proposed text.
- PROPOSAL-5: `update_opinion` proposals require an existing opinion ID and proposed text.
- PROPOSAL-6: `remove_opinion` and `add_sources` proposals require an existing opinion ID.
- PROPOSAL-7: `add_opinion`, `update_opinion`, and `add_sources` proposals require supporting evidence IDs.
- PROPOSAL-8: Supporting evidence IDs must come from the current run's selected evidence, not merely from historical
  corpus rows.
- PROPOSAL-9: Proposal rows are stored in the database as operational state. The agent does not write these rows.
- PROPOSAL-10: A run with an empty successful proposal batch completes and advances the workflow cursor.

## Telegram Approval

### Purpose

Telegram provides human approval for every proposed opinion change before the app mutates opinion files.

### Requirements

- TELEGRAM-1: The app sends one Telegram message per pending proposal in the current batch.
- TELEGRAM-2: Proposal messages include Approve, Reject, and Revise actions.
- TELEGRAM-3: Only `TELEGRAM_ALLOWED_CHAT_ID` may approve, reject, or revise proposals.
- TELEGRAM-4: Telegram update IDs and callback query IDs are recorded for idempotency.
- TELEGRAM-5: Duplicate Telegram updates must not re-apply a proposal.
- TELEGRAM-6: Stale callbacks for terminal, superseded, or non-current-batch proposals must not mutate files.
- TELEGRAM-7: Free-text Telegram messages are ignored unless they reply to one of the run's outbound proposal messages.
- TELEGRAM-8: Revision feedback supersedes only pending proposals in the active batch; already approved proposals remain
  applied.
- TELEGRAM-9: A failed revision marks the run failed and records the failure reason.

## Opinion Files And Provenance

### Purpose

Accepted opinions and accepted supporting evidence are durable artifacts owned by the opinions repository, not transient
runtime state.

### Requirements

- OPINIONS-1: `OPINIONS.md` stores the current accepted opinions.
- OPINIONS-2: Each opinion has a stable `opinion-000001` style ID.
- OPINIONS-3: Opinion IDs are durable once the opinions repository is in active use; moving or reordering opinions must
  not change IDs.
- OPINIONS-4: `OPINIONS_SOURCES.jsonl` stores one row per supporting evidence item for each accepted opinion.
- OPINIONS-5: Multiple rows in `OPINIONS_SOURCES.jsonl` may reference the same opinion ID when multiple highlights or
  document notes support that opinion.
- OPINIONS-6: Source rows include the opinion ID, evidence ID, document ID, document title, source URL, evidence text,
  and timestamp when the source was attached.
- OPINIONS-7: `OPINIONS_SOURCES.jsonl` is the machine-readable provenance source. Inline comments in `OPINIONS.md` may
  be useful for humans but are not sufficient as the durable automation format.
- OPINIONS-8: Applying `add_opinion` assigns the next stable opinion ID based on existing opinion IDs, source rows, and
  accepted decision history so removed IDs are not reused.
- OPINIONS-9: Applying `update_opinion` changes the target opinion text and merges new source rows.
- OPINIONS-10: Applying `remove_opinion` removes the target opinion and removes its source rows.
- OPINIONS-11: Applying `add_sources` keeps opinion text unchanged and merges new source rows.
- OPINIONS-12: Source rows are deduplicated by `(opinion_id, evidence_id)`.
- OPINIONS-13: Post-apply validation rejects duplicate opinion IDs and source rows that reference missing opinions.

## Git Application

### Purpose

Approved changes become durable by committing and pushing only the configured opinions files.

### Requirements

- GIT-1: Before applying a proposal, the app ensures the configured opinions repository exists locally and is on the
  configured branch.
- GIT-2: The app refuses to apply a proposal when the configured target opinion files are already dirty.
- GIT-3: The app may create missing configured opinion files before applying the first approved proposal.
- GIT-4: The app commits only `OPINIONS_TARGET_FILE` and `OPINIONS_SOURCES_FILE`.
- GIT-5: The app refuses to commit if staged files include paths other than the configured opinion files.
- GIT-6: A no-op apply produces no commit SHA.
- GIT-7: Push failures mark the run failed and preserve the local commit for manual recovery.

## Decision History And Memory

### Purpose

The system keeps an audit trail of proposal decisions while leaving long-term distilled learning to memory files.

### Requirements

- DECISION-1: Accepted and rejected proposal decisions append rows to `opinion-decisions.jsonl`.
- DECISION-2: Decision rows include run ID, proposal ID, decision, proposal kind, opinion ID when applicable,
  supporting evidence IDs, and decision timestamp.
- DECISION-3: The decision log is an audit/history artifact and may be inspected by an agent when relevant.
- DECISION-4: The agent should not rely on reading the entire decision log every run as its primary long-term memory.
- DECISION-5: Distilled long-term guidance belongs in memory files, but automated memory updates are not currently
  implemented.

## Opinion Selection Rules

### Purpose

Opinion proposals should be plausible Ryan-endorsable stances rather than summaries, raw highlights, or generic
workflow practices.

### Requirements

- RULES-1: The agent cannot know endorsement directly; approval, rejection, and revision determine actual endorsement.
- RULES-2: Proposed opinions should be stances, judgments, predictions, prioritizations, tradeoffs, or decision rules.
- RULES-3: Proposed opinions should avoid obvious practices and consensus filler.
- RULES-4: Coding-agent tactics usually belong outside `OPINIONS.md` unless they generalize into a broader stance about
  software, human judgment, agents, verification, organizations, or system design.
- RULES-5: Document notes should carry more evidentiary weight than ordinary highlights.
- RULES-6: Market, strategy, taste, craft, career, and work-life claims can count when they guide future judgment.
- RULES-7: Opinions should be understandable in isolation; if a claim depends on a specific example, mechanism, or term
  of art, the opinion text should include enough context to remain clear later.
- RULES-8: Related opinions should be grouped into sections instead of being over-consolidated into vague thesis
  statements.
