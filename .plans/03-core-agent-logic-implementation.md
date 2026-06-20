# Core Agent Logic Implementation Plan

Date: 2026-06-17

## Goal

Implement the real `opinions-agent` runtime as one resumable ThinHarness conversation. The agent always has the same narrow read/write filesystem surface, returns Telegram messages as native structured output, and never gets raw git or Telegram-send tools. The app sends returned Telegram messages, records Telegram callbacks/replies, resumes the agent only when the awaited Telegram response set is complete or the user sends exact `GO`/`SKIP`, validates artifacts after the agent says it is done, then commits/pushes only the configured opinions files.

## Correct Runtime Model

The runtime loop is:

```text
app syncs Reader corpus
app selects run evidence and writes the run bundle
app starts or resumes one ThinHarness conversation
agent may read context and may edit only allowed artifact files
agent returns structured output containing Telegram messages and a done flag
app sends returned Telegram messages through Telegram and records Telegram's real message_id values
user clicks/replies in Telegram, or sends exact GO/SKIP
app records individual Telegram responses until the awaited response set is complete, or exact GO/SKIP arrives
app atomically claims awaiting_user -> running_agent and resumes the same ThinHarness conversation with concrete Telegram response context
agent returns more Telegram messages or says it is done
if done, app validates artifacts, commits/pushes allowed opinions files, finalizes run state, then sends/annotates final returned Telegram message text
```

There is no app-interpreted mutation command language. There is no `processed_proposals`, no `affected_opinion_ids`, no app-side proposal patch application, no commit tool, and no Telegram-send tool exposed to the agent. The app may recognize operational Telegram commands such as exact `GO` and `SKIP`, but it submits them into the same agent conversation as user input; it does not decide which conceptual proposals are final or which files to mutate.

## Current State And Main Gaps

- `workflow.py` still treats stored proposal rows as app-interpreted commands and applies each approval through `_apply_proposal_files`.
- `agent.py` exposes a proposal/revision interface rather than a generic "run/resume the conversation and return Telegram messages" interface.
- ThinHarness is currently configured with `builtin_tools=["read"]`; it does not yet expose the always-bounded `read/search/edit/write` file surface or the app-owned validation custom tool.
- The current structured output models are proposal records, not Telegram message lists.
- Telegram callbacks are tied to proposal database rows. The intended model should tie Telegram callbacks/replies to Telegram's real `message_id` and the original sent message text/buttons.
- `opinions_doc.py` parses an older numbered-heading format, while `docs/behavior.md` and root `OPINIONS.md` use section headings with bullet opinions and indented metadata comments.
- `opinions_doc.py` still contains app-side mutators such as add/update/remove opinion helpers. The final architecture should remove those mutators from the workflow path. Python code validates artifacts; the agent edits them directly.
- Artifact validation is incomplete: it does not enforce the contracted `OPINIONS.md` shape, source row schema, duplicate `(opinion_id, evidence_id)` rejection, newly added source rows coming from the current run bundle, or retired ID reuse.
- Reader document-level notes and backfill exclusion are behavior-contract gaps independent of the agent loop.
- Git commit safeguards need to reject unrelated staged files while still allowing unrelated unstaged working-tree dirt.

## Agent Output Shape

Replace proposal-command output with an app-facing turn result:

```python
from pydantic import BaseModel, Field

class TelegramButtonSpec(BaseModel):
    text: str
    callback_data: str | None = None

class TelegramMessageSpec(BaseModel):
    text: str
    buttons: list[TelegramButtonSpec] = Field(default_factory=list)
    reply_to_message_id: int | None = None
    force_reply: bool = False

class AgentTurnOutput(BaseModel):
    status: Literal["awaiting_user", "done", "blocked"]
    telegram_messages: list[TelegramMessageSpec] = Field(default_factory=list)
    notes: str | None = None
```

Rules:

- `telegram_messages` is the core output. The app sends these messages exactly through Telegram, subject only to Telegram API formatting constraints.
- The agent may return one or more Telegram messages. It will usually return one approval message per conceptual proposal, but the app must not require a fixed one-message-per-proposal shape.
- `status="awaiting_user"` means the app should send the returned messages and wait for Telegram callbacks/replies.
- `status="done"` means the app should run the shared validator, commit/push if configured opinion repo files changed, finalize run state, then send or annotate returned final messages with app-owned durability outcome.
- `status="blocked"` means the agent cannot make progress without manual intervention. The app records a terminal blocked/failed run state, preserves the active artifacts for inspection, sends any returned explanatory Telegram messages, and does not validate or commit.
- The app does not interpret message contents as file mutations.
- The agent may include Approve/Reject/Revise buttons in message specs. The app sends them, then later resumes the agent with the user's concrete Telegram response.

## Telegram Response Handling

When the app sends an agent-returned message, Telegram returns a real integer `message_id`. Store the outbound interaction with:

- run ID
- Telegram `message_id`
- chat ID
- full message text
- button labels/callback data that were sent
- raw Telegram send response if useful

When Telegram sends a callback or reply:

- Use `(chat_id, message_id)` from the callback/reply to find the stored outbound message. `TELEGRAM_ALLOWED_CHAT_ID` means there is only one authorized chat, but lookups should still include `chat_id` because Telegram message IDs are chat-scoped.
- For callbacks, verify the callback data matches a button that was stored for that outbound message before recording the response.
- Record the individual response idempotently. A callback or reply does not resume the agent by itself unless it completes the awaited response set.
- When every outbound message that requires a user response has been answered, atomically claim the run with `awaiting_user -> running_agent`. If the claim fails, another webhook already started or completed the resume.
- Resume the same ThinHarness conversation with a plain, concrete prompt fragment summarizing all newly recorded response context since the last agent turn, such as:

```text
Telegram responses received.

Original Telegram message_id: 1001
Original message text:
<stored text>

User action:
Approve
```

or:

```text
Telegram responses received.

Original Telegram message_id: 1001
Original message text:
<stored text>

User reply:
Please make this narrower and less absolute.
```

Do not invent separate app-local message IDs unless Telegram lacks a usable message ID for a specific interaction. The default identity is Telegram's real `message_id`.

Exact standalone `GO` and `SKIP` messages remain part of the Telegram UX. The app validates that they came from `TELEGRAM_ALLOWED_CHAT_ID` and that a run is awaiting user input, then atomically claims the run with `awaiting_user -> running_agent` before resuming. If the claim fails, another webhook already started or completed the resume. A successful claim resumes the same ThinHarness conversation with a concrete prompt fragment such as:

```text
Telegram command received.

Command:
GO
```

or:

```text
Telegram command received.

Command:
SKIP
```

The app does not itself decide what `GO` or `SKIP` means for individual conceptual proposals. The agent receives the command and returns the next Telegram messages, `done`, or `blocked`.

Outbound send idempotency must not depend on proposal rows. Each agent turn gets a monotonically increasing `turn_seq`; each returned Telegram message gets a deterministic idempotency key:

```text
opinion-run:<run_id>:turn:<turn_seq>:message:<index>
```

If a crash happens after the agent returns output but before all messages are sent, retrying the same turn sends only messages whose key has no stored successful Telegram `message_id`.

## ThinHarness Integration

Use one harness configuration shape for the whole run. The tool surface should not change by phase.

```python
from thinharness import Harness, HarnessConfig, NativeOutput, ToolResult, ToolSpec

config = HarnessConfig(
    root=common_root(read_paths + write_paths),
    model=settings.harness_model,
    builtin_tools=["read", "search", "jsonl_search", "list", "glob", "edit", "write"],
    read_paths=[str(path) for path in read_paths],
    write_paths=[str(path) for path in write_paths],
    output_dir=str(run_dir / ".thinharness" / "outputs"),
    output_type=NativeOutput(AgentTurnOutput),
    local_trace_dir=str(settings.local_trace_dir),
    local_tracing=settings.local_tracing_enabled,
    tracing=[tracing] if tracing is not None else [],
)
```

Write paths are always exactly:

- `settings.opinions_target_path`
- `settings.opinions_sources_path`
- `CorpusPaths(settings.opinions_data_dir).decisions_jsonl`

Read paths include:

- active run bundle
- corpus indexes
- readable document content
- memory files
- current opinion files
- source/provenance file
- decision log

Do not expose shell, git, network, or Telegram-send tools.

Use native structured output, not `PromptedOutput`. The configured model must support native structured output for `AgentTurnOutput`; if the configured model cannot do that, fail configuration rather than silently switching to prompted JSON. This keeps `resume_state` available without relying on provider-visible JSON prose instructions.

## ThinHarness Custom Validation Tool

ThinHarness custom tools are `ToolSpec` instances passed to `Harness(..., tools=[...])`. They do not go in `builtin_tools`.

```python
from pydantic import BaseModel
from thinharness import ToolResult, ToolSpec

class ValidateOpinionArtifactsArgs(BaseModel):
    pass

async def validate_opinion_artifacts(args: ValidateOpinionArtifactsArgs) -> ToolResult:
    try:
        result = run_artifact_validation(settings=settings, run_dir=run_dir)
    except Exception as exc:
        return ToolResult(ok=False, content=str(exc))
    return ToolResult(ok=True, content=result.summary)

validation_tool = ToolSpec(
    name="validate_opinion_artifacts",
    description="Validate OPINIONS.md, OPINIONS_SOURCES.jsonl, and opinion-decisions.jsonl before durable completion.",
    parameters=ValidateOpinionArtifactsArgs,
    handler=validate_opinion_artifacts,
    sequential=True,
)

result = await Harness(config, tools=[validation_tool]).run(prompt, resume_from=run.resume_state)
```

There is exactly one deterministic validator implementation. The agent calls it through this ThinHarness tool before returning `done`; the app calls the same function one final time after `Harness.run(...)` returns `status="done"` and before committing. Same code path, same checks, same result shape. If final validation fails, the app marks the run failed and does not repair the files.

The validator compares the current working-tree artifacts against the pristine baseline at `git HEAD` in `OPINIONS_REPO_DIR`. This depends on the app enforcing clean configured target files before the run starts and not committing those files until the agent returns `done`. The `git HEAD` baseline is stable across multi-turn resumes and is used to identify newly added source rows and newly introduced opinion IDs.

The validator is not an editor. It must not normalize, deduplicate, allocate IDs, rewrite comments, or repair files. It only reports whether the current artifacts satisfy the contract.

## App-Owned Commit Boundary

The app commits only after `Harness.run(...)` returns and `AgentTurnOutput.status == "done"`.

Commit sequence:

1. Run the same artifact validator exposed to the agent: `OPINIONS.md`, `OPINIONS_SOURCES.jsonl`, newly added source rows against current run evidence, newly introduced opinion IDs against the high-water mark, and parseability of `opinion-decisions.jsonl`.
2. Inspect git state in `OPINIONS_REPO_DIR`.
3. Refuse unrelated staged files.
4. Allow unrelated unstaged files outside configured target files.
5. Stage only `OPINIONS_TARGET_FILE` and `OPINIONS_SOURCES_FILE`.
6. If those files have changes, commit and push once.
7. If those files have no changes, record a no-op completion with no commit SHA.
8. Update app-owned high-water opinion ID state only after validation and commit/no-op handling succeeds.
9. Advance workflow cursor and move the run bundle to completed only after successful validation, commit/no-op handling, and high-water update.
10. Send or annotate any final `telegram_messages` returned by the agent with app-owned durability metadata.

The agent does not know the commit SHA before returning. If a Telegram completion message should include the SHA, the app appends operational commit metadata to the agent's returned message or sends a separate app-authored operational footer. The app must not send success-style final Telegram messages before validation and commit/no-op handling succeed. If validation, commit, or push fails, the app sends an app-authored operational failure message instead of the agent's success wording.

## Data Model Changes

Keep the database focused on app-owned operational state:

- `opinion_runs.resume_state`: ThinHarness resume state.
- `opinion_runs.status`: include non-terminal `running_agent` while ThinHarness is in flight, and terminal `blocked` or map agent-declared blocked output to `failed` with an explicit reason.
- `opinion_runs.agent_output`: last `AgentTurnOutput`.
- `opinion_runs.turn_seq`: monotonically increasing agent-output turn sequence for outbound Telegram idempotency keys.
- `telegram_interactions`: inbound and outbound Telegram updates/messages, including real Telegram `message_id`.
- Retain proposal rows only if useful as an audit cache of agent-returned approval messages. They must not drive file mutations or app decisions about which concepts are accepted, deferred, skipped, or ready to edit.

Recommended status flow:

```text
pending_agent -> awaiting_user -> running_agent -> awaiting_user
pending_agent -> awaiting_user -> running_agent -> completed
pending_agent -> awaiting_user -> running_agent -> blocked
pending_agent -> awaiting_user -> running_agent -> failed
```

`running_agent` is an app lock/idempotency state while `Harness.run(...)` is in flight. It is not a write-permission state. Enter it only through an atomic claim from `awaiting_user`, such as a conditional update that succeeds only when the current status is still `awaiting_user`. Ordinary callback/reply handling records responses without claiming the run until all expected responses are present; exact `GO` and `SKIP` attempt the claim immediately.

## Prompt Contract

The system prompt should be explicit:

- You always have a narrow file edit surface.
- Do not make durable opinion changes until the Telegram conversation has enough approval/revision context.
- Return Telegram messages for anything the user should approve, reject, revise, or be told. You will often return one message per conceptual proposal, but you may return fewer or more when that better fits the conversation.
- When you are done with the run, return `status="done"` and any final Telegram messages.
- If you cannot make progress without manual intervention, return `status="blocked"` with a clear Telegram message explaining what needs attention.
- Call `validate_opinion_artifacts` before returning `done` if you changed durable opinion artifacts.
- Do not ask the app to apply patch commands.
- Do not claim a commit happened; the app commits after you return.

## Opinion Artifact Work

Replace `opinions_doc.py` mutation behavior with validation-only artifact code before relying on the real agent:

- Parse `## Section` headings.
- Parse one-line bullet opinions followed by indented metadata comments.
- Require exactly one valid `<!-- opinion-id: opinion-000001 -->` per opinion.
- Validate `OPINIONS_SOURCES.jsonl` rows use `evidence_id`, not `highlight_id`, as the canonical source-row field.
- Reject duplicate `(opinion_id, evidence_id)` rows.
- Reject source rows referencing missing opinions.
- Compare `OPINIONS_SOURCES.jsonl` at `git HEAD` to the current working tree and reject newly added source rows whose `evidence_id` is not present in the active run's `selected-highlights.jsonl`.
- Keep corpus/run evidence rows using `highlight_id`; in the ideal source schema, `OPINIONS_SOURCES.jsonl.evidence_id` has the same value as the selected evidence row's `highlight_id` (`rw:...` for highlights and `reader-note:...` for document-level notes).
- Use an app-owned opinion ID high-water mark under `OPINIONS_DATA_DIR` as the authoritative retired/reuse guard. New IDs introduced in the working tree must be greater than the high-water mark unless they already existed at the `git HEAD` baseline. Update the high-water mark only after validation and commit/no-op handling succeed.
- Remove app-side OPINIONS mutators from the workflow path: no Python `add_opinion`, `update_opinion`, `remove_opinion`, app-side ID allocation, source-row dedupe, or file repair. The agent edits artifacts directly, and the single validator reports contract violations.
- This is a greenfield codebase with no backwards-compatibility requirement. Migrate source code, fixtures, tests, and docs directly to the final `OPINIONS.md` bullet/comment format and `OPINIONS_SOURCES.jsonl.evidence_id` schema. Do not add transitional parsers for the old numbered-heading format or legacy `highlight_id` source rows.

## Corpus And Selection Work

Implement behavior-contract gaps:

- Reader document-level notes become evidence rows in `highlights.jsonl` with `reader-note:<note_reader_id>`.
- Highlight-attached Reader notes remain on the parent highlight row.
- Reader documents tagged `backfill` or `.backfill` and descendant highlights/notes are excluded from opinion run selection.
- If a highlight's parent document is missing, include it by default and surface the missing parent as data-quality context.

## Required Testing Strategy

Implementation is not complete until all required test layers pass. Unit tests are necessary but insufficient; the real ThinHarness agent must also complete an agent-only end-to-end run with real LLM calls before the coding agent can consider development done.

### Unit Tests

Fast deterministic tests should cover:

- The shared validator accepts valid final `OPINIONS.md`, `OPINIONS_SOURCES.jsonl`, and `opinion-decisions.jsonl` artifacts.
- The validator rejects malformed, missing, duplicate, and high-water-violating opinion IDs.
- The validator rejects malformed source rows, duplicate `(opinion_id, evidence_id)` rows, source rows referencing missing opinions, and newly added source rows whose `evidence_id` is not in the active run bundle.
- The validator uses the same code path when called directly, through the ThinHarness validation tool, and as the final pre-commit guard.
- Git boundary checks reject unrelated staged files, allow unrelated unstaged files outside configured targets, produce no commit SHA for no-op changes, and update the high-water mark only after durable success.
- Telegram routing looks up outbound messages by `(chat_id, message_id)`, verifies callback data against stored buttons, records individual responses without premature resume, triggers resume only when all expected responses are present or valid exact `GO`/`SKIP` arrives, dedupes repeated updates, and atomically prevents double resume at the readiness boundary.

### Fake-Agent App Integration Tests

Required app integration tests should use fake Telegram and a deterministic fake agent, not real LLM calls. They prove app-owned orchestration:

- Start a run, receive multiple agent-returned Telegram messages, send/store them with deterministic turn/message idempotency keys, and persist real fake-Telegram `(chat_id, message_id)` values.
- Respond to only one required message and verify the app records the response but does not resume the agent.
- Respond to all required messages and verify the app atomically claims `awaiting_user -> running_agent`, resumes the fake agent once, validates artifacts, updates high-water state, finalizes the run, and sends success metadata only after durable completion.
- Exercise exact `GO`, exact `SKIP`, `blocked`, final validation failure, push/commit failure, duplicate callbacks/replies, and readiness-boundary races.

### Real ThinHarness Agent-Only End-To-End

This is a required completion gate, not an optional smoke test.

Before implementation is declared complete, run an agent-only end-to-end test using the real `ThinHarnessOpinionAgent`, the real configured ThinHarness tools, native structured output, the shared validator tool, and real LLM calls. This test must not send real Telegram messages and must not commit or push. It should:

1. Build an isolated temporary corpus, run bundle, opinions repo working tree, `OPINIONS.md`, `OPINIONS_SOURCES.jsonl`, `opinion-decisions.jsonl`, and high-water state.
2. Invoke the real ThinHarness agent for the initial turn.
3. Assert the agent returns valid native structured `AgentTurnOutput` with `status="awaiting_user"`, at least one Telegram message suitable for review, and a usable `resume_state`.
4. Resume the same conversation with concrete sample Telegram response context, such as an approval, revision request, `GO`, or `SKIP`.
5. Continue until the agent returns `done` or `blocked`.
6. If the agent returns `done`, assert the shared validator passes on the edited artifacts, the agent did not claim a commit happened, and no app commit/push was performed.
7. If the agent returns `blocked`, assert it includes a clear user-facing Telegram message and no validation/commit path runs.

The real-agent E2E may be isolated from normal fast unit-test runs by requiring explicit environment configuration for API credentials and model selection, but it is still mandatory for developer completion. A coding agent must not report the implementation complete without running it successfully and reporting the result.

### ThinHarness Boundary Tests

Focused tests should also verify the harness boundary itself:

- `builtin_tools=["read", "search", "jsonl_search", "list", "glob", "edit", "write"]` is selected successfully.
- Writes to `OPINIONS.md`, `OPINIONS_SOURCES.jsonl`, and `opinion-decisions.jsonl` are allowed.
- Writes outside the configured write paths are rejected.
- The shared validation tool is registered as a custom `ToolSpec`.
- Native structured `awaiting_user` output returns a resumable `resume_state`.

## Implementation Phases

1. Artifact validator and OPINIONS code cleanup.
   - Replace `opinions_doc.py` mutators with validation-only parsing for the final `OPINIONS.md` bullet/comment format.
   - Implement the single shared validator used by both the ThinHarness tool and final app commit guard.
   - Validate source rows, duplicate `(opinion_id, evidence_id)` pairs, missing opinion references, high-water ID violations, newly added evidence IDs against the active run bundle, and decision-log JSONL parseability.
   - Use `git HEAD` as the artifact baseline for before/after validation.
   - Migrate tests and fixtures directly to the final format and schema.
   - Verify with focused validator tests.

2. ThinHarness runtime skeleton.
   - Add `AgentTurnOutput`.
   - Replace proposal-specific agent methods with a generic start/resume method returning `AgentTurnOutput`.
   - Configure `builtin_tools=["read", "search", "jsonl_search", "list", "glob", "edit", "write"]`, fixed `write_paths`, fixed `read_paths`, native structured output, and the shared-validator `ToolSpec`.
   - Verify with unit tests that the custom validation tool is registered and out-of-bounds writes fail.

3. Telegram loop.
   - Send agent-returned `telegram_messages` with `opinion-run:<run_id>:turn:<turn_seq>:message:<index>` idempotency keys.
   - Store real Telegram `chat_id`, `message_id`, text, buttons, and raw response.
   - Record callbacks/replies against stored outbound messages by `(chat_id, message_id)` and stored callback data.
   - Resume the agent only after all expected responses are recorded, or after valid exact `GO`/`SKIP`.
   - Implement exact `GO`/`SKIP` handling as Telegram user messages that are passed into the same agent conversation after the atomic `awaiting_user -> running_agent` claim, not as app-side decisions about accepted, deferred, skipped, or editable concepts.

4. Remove app-applied proposal mutations.
   - Stop calling `_apply_proposal_files`.
   - Stop treating proposal kind rows as mutation commands.
   - Keep any proposal table only as an operational audit/cache if still useful.

5. App commit boundary.
   - After `status="done"`, run the same validator, commit/push allowed opinion files, update high-water ID state, advance cursor, finalize run, then send/append commit metadata.
   - Add crash/idempotency tests for duplicate callbacks, readiness-boundary races, and concurrent `GO`/`SKIP` attempts.

6. Corpus gaps.
   - Add document-level notes.
   - Add backfill exclusion.
   - Update tests.

7. README and docs cleanup.
   - Update `README.md` to describe the final conversation runtime, native structured output, shared validator, `GO`/`SKIP` routing, final source schema, and no app-side proposal mutation.

8. End-to-end verification.
   - Deterministic fake agent returns Telegram messages, receives fake Telegram responses, edits files, returns `done`, and lets the app validate/commit.
   - Run the required real ThinHarness agent-only E2E with real LLM calls, no real Telegram sends, and no commit/push.
   - Replace old proposal-command workflow tests wholesale with conversation/runtime-boundary tests; do not preserve tests that assume app-side proposal mutation or per-proposal commits.
   - Run `uv run pytest`, `uv run ruff check .`, and `uv run pyright`.

## Acceptance Criteria

- One ThinHarness conversation per run, resumed across Telegram interactions.
- Same bounded read/write file tool surface on every agent run.
- Custom validation tool implemented with `ToolSpec` and passed through `Harness(config, tools=[...])`.
- The validation tool and final pre-commit guard call the same deterministic validator implementation.
- Agent structured output is a list of Telegram message specs plus status.
- Agent output uses native structured output, not prompted JSON instructions.
- App sends Telegram messages using turn/message idempotency keys and stores Telegram's real `(chat_id, message_id)`.
- App records individual callbacks/replies and resumes the agent only when all expected responses are present or valid exact `GO`/`SKIP` arrives.
- App atomically claims `awaiting_user -> running_agent` before every agent resume.
- App routes exact `GO`/`SKIP` commands into the same agent conversation and does not decide which concepts are accepted, deferred, skipped, or ready to edit.
- App uses `git HEAD` as the validator baseline and maintains a high-water opinion ID guard updated only after durable completion.
- Agent can return `blocked`; the app records a terminal blocked/failed state, sends explanatory messages, and does not validate/commit.
- Agent has no raw git, shell, network, or Telegram-send tools.
- App commits only after `Harness.run(...)` returns `status="done"` and app-side validation passes; success-style final Telegram messages are sent only after validation and commit/no-op handling succeed.
- App never interprets agent proposal categories as file mutation commands.
- Development is not complete until the required real ThinHarness agent-only E2E has passed with real LLM calls.
