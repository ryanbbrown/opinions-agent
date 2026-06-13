# Review: filesystem-readwise-opinions-workflow (v1)

**Verdict: changes requested** — the architecture closely follows the plan and test coverage is strong, but there is one real invariant violation (stable opinion ID reuse), one production foot-gun in the defaults, and a couple of failure-path bugs worth fixing before this is exercised against the real repo.

Note: Bash was denied in this session, so I reviewed via file reads only. The git snapshot shows a clean tree with the feature in commit 71447e1; everything below refers to the committed code.

## Findings

### 1. Medium — Stable opinion IDs can be reused after removing the highest-numbered opinion
`next_opinion_id` (`src/opinions_agent/opinions_doc.py:91`) returns `highest + 1` over the IDs currently present in `OPINIONS.md` plus `OPINIONS_SOURCES.jsonl` (`src/opinions_agent/workflow.py:568`). But `remove_opinion` deletes the opinion from the doc **and** purges its source rows (`workflow.py:583`). So: approve `remove_opinion` for the highest-numbered opinion (say `opinion-000014`), then approve an `add_opinion` in a later run — the new opinion is assigned `opinion-000014` again. That breaks the plan's core invariant ("the hidden `opinion-id` is durable"): `opinion-decisions.jsonl` rows and git history now reference the same ID with two different meanings. Fix options: include the decision log's `opinion_id`s in `existing_ids`, or persist a max-issued counter in `state.json`. Add a test: remove highest opinion → add opinion → assert the removed ID is not reissued.

### 2. Medium — Default settings push to the real public repo, and the target-file default contradicts the plan
With no env vars set, `get_settings()` yields `opinions_repo_dir=/Users/ryanbrown/code/ryanbbrown` (the real checkout), `opinions_repo_url` pointing at the real GitHub repo, and `opinions_target_file="TEST_OPINIONS.md"` (`src/opinions_agent/config.py:84-87`). `commit_and_push_opinions_files` defaults to `push=True`. So a plain local `opinion-run` plus one Telegram approval commits **and pushes** `TEST_OPINIONS.md` + `OPINIONS_SOURCES.jsonl` to the real `ryanbbrown` repo's main branch. Two issues:
- The `TEST_OPINIONS.md` default diverges from the plan and from the README's Railway instructions (`OPINIONS_TARGET_FILE=OPINIONS.md`); if the env var is ever missed on Railway, the agent quietly maintains the wrong public file. The plan's env shape (`.plans/filesystem-readwise-opinions-workflow.md:381`) says the default should be `OPINIONS.md`.
- Whatever the intended safety posture is, "default = push to the real public repo" deserves an explicit guard (e.g., refuse to push without `OPINIONS_REPO_URL`/`OPINIONS_TARGET_FILE` explicitly set) or at least a README callout. Right now the README's local-setup section doesn't mention the `TEST_OPINIONS.md` default at all.

This looks like a deliberate-but-undocumented choice — please confirm intent and make the docs/config consistent either way.

### 3. Low/Medium — Error handlers can raise `invalid transition` and mask the original failure
`_complete_run_if_terminal` transitions the run to COMPLETED **before** `_finalize_run_artifacts` (`workflow.py:626-628`), and `_advance_workflow_cursor`/`finalize_run_dir` do filesystem work (`save_state`, `shutil.rmtree`). If either raises (e.g., OSError), the `except` in `approve_proposal` (`workflow.py:488-490`) calls `transition(run, RunStatus.FAILED)` from COMPLETED — an invalid transition — so a `ValueError` is raised *inside* the handler, masking the real error and leaving the run COMPLETED with the failure half-recorded. The same pattern exists in `start_opinion_run`'s handler (`workflow.py:169-171`): the guard only checks `status != FAILED`, but COMPLETED → FAILED is also invalid. Guard with `run.status in NON_TERMINAL_RUN_STATUSES` (or transition to FAILED only when the transition table allows it).

### 4. Low — Approve has a non-idempotent crash window (push succeeds, DB commit doesn't)
In `approve_proposal` (`workflow.py:467-475`), the git commit+push and the `opinion-decisions.jsonl` append both happen before `session.commit()`. A crash in between leaves the proposal PENDING; the user taps Approve again (new `callback_query_id`, so dedup doesn't catch it) and `_apply_proposal_files` re-runs: `update_opinion`/`add_sources` are effectively idempotent, but `add_opinion` appends a **duplicate opinion with a fresh ID**, and the decision log gets a duplicate row. V1 explicitly accepts single-worker + DB idempotency, so this may be acceptable as a documented residual risk — but it's worth either noting in the README's recovery section or making `add_opinion` re-apply detection cheap (e.g., skip if an opinion with identical title+body already exists).

### 5. Low — Any free-text message in the allowed chat triggers a full batch revision
`_find_run_for_message` (`workflow.py:677-700`) falls back to "the single AWAITING_USER run" for any non-reply text message. A stray "thanks" or unrelated message to the bot supersedes every pending proposal and re-runs the agent (token cost + lost pending batch; the previous proposals can no longer be approved). The plan's flow was Revise-button → reply. Consider requiring `reply_to_message` (the Revise callback already says "Reply with revision notes"), and returning a hint otherwise.

### 6. Low — README recovery guidance conflicts with the transition table
README (`README.md:111-112`) says after a failed push to "push or reset it manually, then `abandon-run` if needed" — but a failed run is in FAILED, which is terminal (`VALID_TRANSITIONS[FAILED] = set()`), so `abandon_run` raises `invalid opinion run transition: failed -> abandoned`. Since FAILED already doesn't block new runs, either drop the abandon-run suggestion for failed runs or allow FAILED → ABANDONED.

### Informational / residual risks
- **Harness root breadth**: `_common_root` (`src/opinions_agent/agent.py:224-227`) takes `os.path.commonpath` of the read paths. Locally, with the data dir under the project and the opinions repo at `/Users/ryanbrown/code/ryanbbrown`, the harness `root` becomes `/Users/ryanbrown/code` or higher. If thinharness's `root` grants any access beyond `read_paths`, that's a boundary leak — please verify thinharness semantics.
- **Late-arriving highlights are silently skipped**: a highlight whose `highlighted_at` falls inside an already-completed window (synced late, e.g. offline device) is never selected because the cursor advanced past it. Deterministic-by-design, but worth a line in the README.
- **Webhook with empty secret accepts any request** (`src/opinions_agent/app.py:37`); the chat allow-list still gates effects, but unauthenticated POSTs can insert inbound rows. Fine for v1; consider requiring the secret outside local dev.
- `run.input_paths["dir"]` stores whatever path form `runs_dir` had (relative locally), and revision resolves it relative to cwd (`workflow.py:440-444`) — consistent only if commands always run from the project root.

## Missing / follow-up tests (writer should run)
1. The plan's gate: `uv run pytest`, `uv run ruff check .`, `uv run pyright` (I could not run these in this session — please confirm they pass).
2. New test for finding 1: approve `remove_opinion` on the highest-numbered opinion, then approve an `add_opinion`, assert the stable ID is not reused.
3. Test for finding 3: make `_finalize_run_artifacts` raise (e.g., monkeypatch `shutil.rmtree`) during the last approval and assert the original error surfaces and run state is coherent.
4. An `abandon_run` test (currently only reachable via CLI, untested), including the FAILED-run case from finding 6.
5. A `start_opinion_run` test with no explicit window that exercises `_run_window`'s cursor path and the 7-day fallback (`workflow.py:92-105`) — currently every workflow test passes explicit windows.
6. A test that `add_sources` targeting a nonexistent `opinion_id` fails the run loudly (path exists via `doc.get` → `OpinionsDocError`, but is untested).

## Open questions
- Is the `TEST_OPINIONS.md` default (config + `.env.example`) an intentional guard for local runs against the real checkout? If so, document it and make the Railway path fail loudly when `OPINIONS_TARGET_FILE` is unset; if not, change the default to `OPINIONS.md` per the plan.
- Does thinharness's `root` confer read access beyond the explicit `read_paths`? If yes, `_common_root` over-grants locally.
