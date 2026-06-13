**Verdict: changes requested**

**Findings**

1. **First approval fails when target/provenance files do not already exist.**  
   [workflow.py](/Users/ryanbrown/code/opinions-agent/.claude/worktrees/opinions-agent-imp-1/src/opinions_agent/workflow.py:534) calls `ensure_repo_file()` for both `OPINIONS.md` and `OPINIONS_SOURCES.jsonl`, and [repo_checkout.py](/Users/ryanbrown/code/opinions-agent/.claude/worktrees/opinions-agent-imp-1/src/opinions_agent/repo_checkout.py:35) creates missing files with `touch()`. Immediately after that, [workflow.py](/Users/ryanbrown/code/opinions-agent/.claude/worktrees/opinions-agent-imp-1/src/opinions_agent/workflow.py:539) rejects dirty target files. A missing `OPINIONS_SOURCES.jsonl` becomes an untracked dirty file, so the first approved proposal fails instead of creating the new provenance file. This is likely for existing target repos adopting the feature. Add a test where the repo has `OPINIONS.md` but no `OPINIONS_SOURCES.jsonl`.

2. **Proposal evidence is validated against the whole corpus, not the selected run window.**  
   The brief says current selected highlights are the only source for new proposals ([selection.py](/Users/ryanbrown/code/opinions-agent/.claude/worktrees/opinions-agent-imp-1/src/opinions_agent/selection.py:98)), but `_store_proposal_batch()` only checks whether supporting IDs exist anywhere in `.readwise/highlights.jsonl` ([workflow.py](/Users/ryanbrown/code/opinions-agent/.claude/worktrees/opinions-agent-imp-1/src/opinions_agent/workflow.py:181)). Since the agent can read the global corpus, stale/out-of-window highlights can be accepted and later committed. Also, `remove_opinion` can omit supporting highlights entirely because validation only requires them for add/update/add_sources ([agent.py](/Users/ryanbrown/code/opinions-agent/.claude/worktrees/opinions-agent-imp-1/src/opinions_agent/agent.py:66)). Validate against `selected-highlights.jsonl` for the run and require support for all proposal kinds unless unsupported removals are explicitly intended.

3. **Defaults still target `TEST_OPINIONS.md` while the feature/docs describe `OPINIONS.md`.**  
   The README describes applying to `OPINIONS.md` ([README.md](/Users/ryanbrown/code/opinions-agent/.claude/worktrees/opinions-agent-imp-1/README.md:5)), but both config and `.env.example` default to `TEST_OPINIONS.md` ([config.py](/Users/ryanbrown/code/opinions-agent/.claude/worktrees/opinions-agent-imp-1/src/opinions_agent/config.py:87), [.env.example](/Users/ryanbrown/code/opinions-agent/.claude/worktrees/opinions-agent-imp-1/.env.example:14)). A user copying the env example will mutate or create the wrong file. If this is a safety default, document it clearly; otherwise align the defaults with `OPINIONS.md`.

**Missing or Follow-Up Tests**

- Repo apply flow with existing `OPINIONS.md` and missing `OPINIONS_SOURCES.jsonl`.
- Agent proposal using a highlight outside the selected run window should be rejected.
- `remove_opinion` with empty `supporting_highlight_ids` should either be rejected or explicitly covered as allowed behavior.
- I did not run tests, builds, lint, or ad-hoc checks per the review constraints.

**Open Questions**

- Should the untracked `.reviews/implementations/...` logs be committed? The visible markdown review file is empty, and the rest appear to be generated stdout/stderr logs.