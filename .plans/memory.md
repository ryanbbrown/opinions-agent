# Memory

A record of the memory ideas discussed on 2026-08-09, kept so the thinking survives the conversation.

**Status: deferred until after launch.** Nothing here is committed to. See "Why defer" at the end.

## The constraint that shapes everything

Memory can only come from direct user feedback. It cannot come from the agent's own judgement, because without feedback every opinion the agent writes looks correct to it.

A bare rejection is not enough to write a memory from. Rejecting a proposal often means "this is a reasonable thing to raise, I just don't agree with it strongly enough to add it" — and it would be fine for the agent to raise the same idea again later. If the agent writes memory from bare rejections, it will write far too much, and it will suppress ideas that deserve another chance.

So memory writes trigger only on feedback where the user says something.

## What already exists

- Every Telegram reply is already stored durably in Postgres (`TelegramInteraction.text`), tied to the message it answers. Raw feedback capture is not a thing that needs building.
- `opinion-decisions.jsonl` is the agent-authored decision log — the current active learning channel.
- `memory/` holds `themes.md`, `preferences.md`, and `open-questions.md`. The agent can read them. It cannot write them: `write_paths()` covers only `OPINIONS.md`, `OPINIONS_SOURCES.jsonl`, and `opinion-decisions.jsonl`. The files are header-only placeholders.

The minimum baseline version of memory is therefore: append all written feedback to one file the agent reads. Everything below is about what happens beyond that.

## The ideas

### 1. A separate memory file the agent writes to

The agent distils feedback into new entries in a memory file. Simplest version of "learn without me changing the code."

### 2. Editing `RULES.md`

Two directions, and they are not equally safe.

- **Adding a rule.** The agent notices "if I had known X, I would not have done this" and writes a new rule.
- **Removing a rule.** An existing rule has been contradicted by feedback three separate times, so the rule goes.

Removal is not really memory, but it addresses a real problem — see the conflicting-context problem below. Removal should require confirmation before it happens. It is dangerous for the agent to do on its own, especially since there is no example of it in the sample data. Unclear how important it turns out to be.

### 3. Reading the whole feedback log every run

Straightforward, but the log grows with every run, so context cost grows without bound. Not ideal on its own.

### 4. Routing feedback into files that get treated differently

Rather than distilling into one memory file, the agent's job is to organise feedback by kind. Rough categories that came up:

- which opinions to include versus not include
- how to write opinions
- things not relevant or not needed later

This is a form of memory as routing rather than memory as summarising.

## The conflicting-context problem

If the agent reads a file of historical feedback and that feedback contradicts a rule in `RULES.md`, the agent is now working from conflicting context. It will probably follow `RULES.md`, because that text is part of its actual system prompt, and it may do the wrong thing as a result.

This is the argument for rule removal being part of the design rather than a separate nice-to-have. Any memory design that adds a second source of guidance has to say how conflicts with `RULES.md` resolve.

## Evaluation

Memory needs its own eval, separate from the opinion eval. The existing eval cannot host it: it seeds each week as if every prior week were perfect, specifically so mistakes do not compound, and memory is the compounding channel. It also runs the proposal turn only, so it contains no feedback at all.

A memory eval would have to supply feedback, which means scripting or simulating the user side.

## Why defer

- The input does not exist yet. Memory consumes direct feedback, and the system has never run live with real feedback. Building it now means inventing synthetic feedback in the user's own voice and grading against a simulated user.
- The four ideas above answer different questions, and which one is right depends on what the feedback actually looks like. Mostly wording corrections points to a preferences file. Mostly eligibility complaints points to `RULES.md` edits. Mostly one-off disagreements means the append-only log is already the whole answer.
- Deferring loses no data, because Postgres already stores every reply. The feedback log can be extracted retroactively.
- Hand-editing `RULES.md` is the manual version of memory. Doing it manually for the first stretch produces a diff that is the ground truth for what an automated version should have done.

Revisit once there are real weeks of live feedback to look at.
