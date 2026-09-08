# Keep user-directed opinion review open

## Scope

- User feedback may override the consolidator's initial add, attach, or revise operation. Preserve selected-evidence ownership and the frozen candidate snapshot; obtain approval for any revised proposal before applying it.
- Agent output permits only `awaiting_user` and `done`. Requests for help remain resumable through Telegram. App-owned technical failures still stop work and preserve recovery state.
- Remove the obsolete agent-blocked execution path and status. Do not add a fallback or migration for historical output.
- Test the native output contract and a help-message reply that resumes the same conversation without premature artifact changes. Keep technical failure notices independent of agent status output.
- Run relevant tests, full pytest, Ruff, and Pyright; commit and fast-forward main. Do not change unrelated prompts or generation rules.

## Production recovery

Inspect all writable artifact hashes against the stopped run's saved baseline before deciding recovery. Git cleanliness alone does not cover the decision log. Existing `retry-cycle` creates a new run from the fixed batch, not a new evidence selection. Preserve the failed attempt and its Telegram history rather than deleting records. Deploy the fix before retrying. Do not synthesize approvals from the prior attempt.
