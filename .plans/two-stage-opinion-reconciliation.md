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

The main agent applies critic feedback by editing only candidate opinion text, then validates the file again. That validation freezes `candidate-opinions.jsonl` as the immutable post-critic extraction snapshot. Consolidation does not mutate or delete its rows. There is no second critic call after consolidation.

### 3. Run the consolidator

After critic feedback, the main agent calls one consolidator subagent per candidate. These calls can run in parallel because the main agent already grouped related evidence into candidate opinions. Each consolidator call reads:

- its candidate row from the temporary file;
- the candidate's selected evidence;
- current `OPINIONS.md`;
- existing evidence rows from `OPINIONS_SOURCES.jsonl` when needed.

Each call asks one question:

> Should all or part of this candidate stay independent, attach to one existing opinion, or revise one existing opinion as the complete canonical statement of the same belief?

The root output always contains a required non-empty `reasoning` string before one tagged `decision` object:

```json
{"reasoning": "...", "decision": {"kind": "independent"}}
{"reasoning": "...", "decision": {"kind": "attach", "existing_opinion_id": "opinion-000012", "evidence_ids": ["rw:..."]}}
{"reasoning": "...", "decision": {"kind": "revise", "existing_opinion_id": "opinion-000012", "revised_opinion_text": "Complete revised existing opinion text.", "evidence_ids": ["rw:..."]}}
```

An `attach` or `revise` decision must name exactly one existing opinion ID and list a non-empty subset of the candidate's evidence IDs. A `revise` decision must also provide the complete resulting opinion text. Existing evidence already attached to the opinion remains attached and does not need to be repeated. Candidate evidence absent from the response stays with the new proposal. If every candidate evidence ID is returned, no new-opinion proposal remains. If only some are returned, the main agent authors residual proposal text around the remaining evidence. These decisions affect only conversation state and proposal routing; the frozen candidate row stays unchanged.

The consolidator has no other actions. It cannot discard evidence, create a different new opinion, target several existing opinions from one call, remove an opinion, split an opinion, reorder opinions, or edit files.

### 4. Write Telegram messages

The main agent writes Telegram messages as it does now:

- An `independent` decision becomes an add-opinion proposal using the candidate's existing text and evidence.
- A full `attach` or `revise` decision becomes one existing-opinion proposal and removes the candidate only from the proposal set, not from `candidate-opinions.jsonl`.
- A partial `attach` or `revise` decision becomes one existing-opinion proposal plus a rewritten add-opinion proposal supported only by the evidence that remains; its saved candidate row and evidence list stay unchanged.

The main agent owns the residual proposal rewrite without another critic call. Telegram remains agent-authored. The main agent can ask ordinary questions, explain a recommendation, respond to feedback, and reword proposals. The consolidator output is advisory input, not an immutable instruction that later messages must copy byte for byte.

User callbacks and replies resume the same main agent conversation. Only after approval does the main agent edit `OPINIONS.md`, `OPINIONS_SOURCES.jsonl`, and decision context. Existing validation, commit, push, and recovery behavior remains unchanged.

## Runtime design

### Run-scoped candidate workspace

Use `run_dir/candidate-opinions.jsonl` inside the existing active run directory. Grant the main agent write access for extraction and critic edits, and grant the critic and consolidator read-only access. After post-critic validation, the main agent treats the file as frozen; consolidation outcomes live only in conversation state and proposal text.

Do not add a new temporary-directory lifecycle or checkpoint recovery. Existing failed-run handling remains unchanged, and a retry reruns extraction and recreates the file.

### Fidelity critic

Keep the current omission-only critic and parallel one-call-per-candidate behavior. Change its task input from copied opinion text and evidence IDs to a candidate ID. Its evidence tool loads the exact current candidate from the temporary file before returning the evidence context.

### Consolidator

Add a dedicated `SubAgentConfig` with a typed root reasoning field and a nested tagged decision union. Run one call per candidate after critic feedback, in parallel. Give each call read-only access to its candidate and evidence, current opinions, and provenance.

The consolidator does not need its own persistent output file. The main agent receives each typed response in the same conversation and uses the results to write Telegram messages. Braintrust traces capture the responses for inspection.

### Main agent

Update the prompt and tool instructions to enforce this order:

1. write all candidates;
2. call one fidelity critic per candidate;
3. apply feedback to the candidate file;
4. freeze the post-critic candidate file and call one consolidator per candidate in parallel;
5. author residual proposal text for partial consolidations without changing the candidate snapshot;
6. write Telegram proposals;
7. resume after responses and apply approved durable edits.

The main agent remains responsible for all new-opinion writing. The consolidator either keeps the candidate independent, attaches evidence without rewriting the existing opinion, or supplies complete replacement text for one existing opinion.

## Eval scope

This implementation does not add or change eval targets, runners, or scorers. The current eval continues to measure the final Telegram proposals end to end. Separate extraction and consolidation evals need their own product decisions and plan later.

## Implementation sequence

### 1. Update the behavior contract

Before code changes, update `docs/behavior.md` to state:

- extraction always creates independent candidates;
- the fidelity critic runs once before consolidation;
- one consolidator call checks each candidate against existing opinions;
- `independent` keeps the complete candidate new and unchanged;
- `attach` and `revise` move a named evidence subset into one existing opinion;
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

- Add a typed root object with required reasoning plus `independent`, `attach`, and `revise` decision variants.
- Add the read-only consolidator subagent and call it once per candidate in parallel.
- Validate existing opinion IDs and require returned evidence IDs to be a non-empty subset of the scoped candidate's evidence.
- Update the main prompt to keep `independent` candidates new, omit fully moved candidates from add proposals, and author partial residual proposal text around remaining evidence without changing the frozen candidate snapshot.

Verification:

- `independent`: the complete candidate remains new.
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
- Consolidator actions other than independent, attach, or revise for one existing opinion.
- App-interpreted opinion mutations.
- New extraction or consolidation eval targets, runners, scorers, or fixtures.
- Compatibility with incomplete historical run attempts.
