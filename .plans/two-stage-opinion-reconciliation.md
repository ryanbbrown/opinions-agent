# Two-stage opinion extraction and consolidation

## Goal

Separate opinion writing from one narrow consolidation decision:

1. The main agent converts selected evidence into faithful candidate opinions.
2. A consolidator subagent identifies only candidates that belong inside an existing opinion.

The same resumable main agent conversation still owns extraction, critic feedback, Telegram discussion, approved file edits, and completion.

## Workflow

### 1. Write candidates

The main agent reads the selected evidence and writes `candidate-opinions.jsonl` in the existing active run directory. Each row contains:

```json
{
  "candidate_id": "candidate-001",
  "section": "Agentic Software",
  "opinion_text": "...",
  "evidence_ids": ["rw:..."]
}
```

The main agent creates one candidate for each eligible claim cluster. Existing opinions do not change whether a candidate is created. This is a prompt contract, not a new filesystem permission system.

The candidate file is run-scoped working state, not a durable checkpoint or opinions-repository artifact. The existing run lifecycle owns it. If the agent turn fails, the run fails and a retry recreates the candidate file from selected evidence.

### 2. Run the fidelity critic

The main agent calls the existing fidelity critic once per candidate. Each critic call names a candidate ID. The critic reads that candidate from the temporary file, fetches its cited evidence and fixed same-document context, and returns `READY` or `REVISE` with missing concepts.

The main agent applies critic feedback by editing the candidate file. There is no second critic call after consolidation.

### 3. Run the consolidator

After critic feedback, the main agent calls one consolidator subagent per candidate. These calls can run in parallel because the main agent already grouped related evidence into candidate opinions. Each consolidator call reads:

- its candidate row from the temporary file;
- the candidate's selected evidence;
- current `OPINIONS.md`;
- existing evidence rows from `OPINIONS_SOURCES.jsonl` when needed.

Each call asks one question:

> Should all or part of this candidate remain new, or should some of its evidence and claim be consolidated into one existing opinion?

The minimal typed response is `null` when all candidate evidence remains with the new opinion. Otherwise it is:

```json
{
  "existing_opinion_id": "opinion-000012",
  "opinion_text": "Complete revised existing opinion text.",
  "evidence_ids": ["rw:..."]
}
```

A non-null response must:

- name exactly one existing opinion ID;
- provide the complete resulting existing opinion text;
- list the candidate evidence IDs that move to that existing opinion.

The returned evidence IDs must be a non-empty subset of the candidate's evidence IDs. Existing evidence already attached to the opinion remains attached and does not need to be repeated. Candidate evidence absent from the response stays with the new candidate. If every candidate evidence ID is returned, no new-opinion proposal remains. If only some are returned, the main agent rewrites the new candidate around its remaining evidence.

The consolidator has no other actions. It cannot discard evidence, create a different new opinion, target several existing opinions from one call, remove an opinion, split an opinion, reorder opinions, or edit files. If an existing opinion already expresses the moved evidence fully, the consolidator may return its current text unchanged.

### 4. Write Telegram messages

The main agent writes Telegram messages as it does now:

- A `null` consolidator response becomes an add-opinion proposal using the candidate's existing text and evidence.
- A full consolidation becomes one revise-existing-opinion proposal and removes the new candidate.
- A partial consolidation becomes one revise-existing-opinion proposal plus a rewritten add-opinion proposal supported only by the evidence that remains.

The main agent owns the residual candidate rewrite without another critic call. Telegram remains agent-authored. The main agent can ask ordinary questions, explain a recommendation, respond to feedback, and reword proposals. The consolidator output is advisory input, not an immutable instruction that later messages must copy byte for byte.

User callbacks and replies resume the same main agent conversation. Only after approval does the main agent edit `OPINIONS.md`, `OPINIONS_SOURCES.jsonl`, and decision context. Existing validation, commit, push, and recovery behavior remains unchanged.

## Runtime design

### Run-scoped candidate workspace

Use `run_dir/candidate-opinions.jsonl` inside the existing active run directory. Grant the main agent write access to that file and grant the critic and consolidator read-only access.

Do not add a new temporary-directory lifecycle or checkpoint recovery. Existing failed-run handling remains unchanged, and a retry reruns extraction and recreates the file.

### Fidelity critic

Keep the current omission-only critic and parallel one-call-per-candidate behavior. Change its task input from copied opinion text and evidence IDs to a candidate ID. Its evidence tool loads the exact current candidate from the temporary file before returning the evidence context.

### Consolidator

Add a dedicated `SubAgentConfig` with a typed nullable response. Run one call per candidate after critic feedback, in parallel. Give each call read-only access to its candidate and evidence, current opinions, and provenance.

The consolidator does not need its own persistent output file. The main agent receives each typed response in the same conversation and uses the results to write Telegram messages. Braintrust traces capture the responses for inspection.

### Main agent

Update the prompt and tool instructions to enforce this order:

1. write all candidates;
2. call one fidelity critic per candidate;
3. apply feedback to the candidate file;
4. call one consolidator per candidate in parallel;
5. rewrite any partially consolidated candidates around their remaining evidence;
6. write Telegram proposals;
7. resume after responses and apply approved durable edits.

The main agent remains responsible for all new-opinion writing. The consolidator supplies only complete replacement text for an existing opinion.

## Eval scope

This implementation does not add or change eval targets, runners, or scorers. The current eval continues to measure the final Telegram proposals end to end. Separate extraction and consolidation evals need their own product decisions and plan later.

## Implementation sequence

### 1. Update the behavior contract

Before code changes, update `docs/behavior.md` to state:

- extraction always creates independent candidates;
- the fidelity critic runs once before consolidation;
- one consolidator call checks each candidate against existing opinions;
- `null` keeps the complete candidate new and unchanged;
- non-null responses move a named evidence subset into one existing opinion;
- the main agent rewrites a partially consolidated candidate around its remaining evidence;
- temporary candidate files do not add recovery checkpoints;
- the main agent still owns Telegram and approved durable edits;

Verification: review the behavior diff against this plan.

### 2. Add the run-scoped candidate workspace

- Add the candidate model and `run_dir/candidate-opinions.jsonl` path to the run context.
- Let the main agent create and edit the candidate JSONL file.
- Validate candidate IDs, non-empty text and sections, selected evidence IDs, and unique evidence ownership.
- Use the existing run cleanup and failed-run handling.

Verification:

- Candidate JSONL round-trip and validation tests.
- A failed attempt followed by retry reruns extraction and recreates the file.
- An empty candidate file supports the existing no-proposal completion path.

### 3. Point the critic at saved candidates

- Add candidate lookup by ID to the critic evidence tool.
- Update the main and critic prompts.
- Keep critic calls parallel and omission-only.

Verification:

- The critic receives the current saved candidate rather than copied task text.
- Missing and duplicate candidate IDs fail clearly.
- Prompt-construction tests check inputs and tool access, not exact wording.

### 4. Add per-candidate consolidation

- Add a typed nullable consolidation response model.
- Add the read-only consolidator subagent and call it once per candidate in parallel.
- Validate existing opinion IDs and require returned evidence IDs to be a non-empty subset of the scoped candidate's evidence.
- Update the main prompt to keep `null` candidates new, remove fully consolidated candidates, and rewrite partially consolidated candidates around remaining evidence.

Verification:

- `null`: the complete candidate remains new.
- Full consolidation: all evidence moves to one existing opinion and no new candidate remains.
- Partial consolidation: selected evidence moves and the main agent rewrites the remaining new candidate.
- Existing wording unchanged with new evidence attached.
- Unknown opinion IDs fail.
- Missing, duplicate, or out-of-candidate evidence IDs fail.
- One candidate cannot target several existing opinions.
- No second fidelity critic call occurs.
- No durable opinion files change before user approval.

### 5. Documentation and full verification

Update `README.md` and sample-run documentation.

Run:

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

Before implementation review, run the real ThinHarness workflow through cproxy on W04 and W08. Use the shared `.readwise` corpus, real drafter, fidelity-critic, and consolidator calls, fake Telegram delivery, and the current V2 scorer. Inspect both run artifacts and traces to confirm candidates are written, each critic reads its candidate by ID, consolidation runs once per candidate, and Telegram proposals reflect full and partial outcomes. Record the experiment URL and per-target results for the implementation reviewer.

## Out of scope

- A second fidelity critic pass after consolidation.
- Deterministic Telegram rendering.
- Durable candidate or consolidation checkpoints.
- Mid-turn crash resume.
- Consolidator actions other than null or consolidation into one existing opinion.
- App-interpreted opinion mutations.
- New extraction or consolidation eval targets, runners, scorers, or fixtures.
- Compatibility with incomplete historical run attempts.
