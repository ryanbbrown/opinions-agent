# Opinion Selection Rules

These rules describe how this project should decide whether a highlight, document note, or synthesized claim is worth
proposing as an opinion.

## Core Definition

An opinion is a personally endorsable stance, not merely an interesting claim.

The agent cannot know endorsement directly. Its job is to propose claims that look plausibly Ryan-endorsable based on
highlights, document notes, prior accepted/rejected decisions, and surrounding context. Actual endorsement happens when
Ryan approves, rejects, or revises the proposal.

## Generation Rules

- Prefer stances over summaries.
  A proposed opinion should make a judgment, prioritization, prediction, tradeoff, or decision rule. It should not just
  restate what an article said.

- Avoid claims that are universally held.
  If nearly every thoughtful person in the relevant context would agree, the claim is probably not opinion-worthy unless
  it is part of a sharper synthesis. The contrast does not need to be stated explicitly; the opinion sentence itself
  should carry the stance.

- Avoid obvious practices.
  Useful practices do not automatically count as opinions. "Write a plan before using a coding agent" is probably a
  workflow rule. "Humans should own intent and verification more than generated implementation" is an opinion.

- Make opinions understandable in isolation.
  If an opinion depends on a specific example, mechanism, or term of art, include enough context in the opinion sentence
  or bullet. The reader should not need to remember the source material to understand the claim.

- Split distinct claims instead of over-consolidating.
  Broad themes can contain multiple opinions. For example, "AI shifts value toward judgment" and "top builders gain
  disproportionately from AI" are related but distinct.

- Use sections to manage related opinions.
  The document should support multiple opinions under broader headings rather than forcing one flat list or merging
  specific takes into vague thesis statements.

- Preserve unresolved tensions in scratch work.
  If evidence supports two related stances that are not actually contradictory, keep both. If they conflict, preserve the
  tension until Ryan decides which stance to endorse.

- Treat document notes as stronger evidence than ordinary highlights.
  A document note is already closer to Ryan's interpretation, so it should carry extra weight when deciding whether a
  claim is plausibly Ryan-endorsable.

- Market and strategy predictions can count.
  Claims about the direction of AI, company structure, moats, careers, and software work are eligible when they are
  broad enough to guide future judgment.

- Taste judgments can count.
  Beliefs about polish, craft, signal, quality, and what makes software or writing good are eligible opinions.

- Career and work-life judgments can count.
  Pragmatic beliefs about jobs, leverage, learning, and useful work are eligible when they are durable rather than
  merely circumstantial.

## Confidence

The final opinions document does not need explicit confidence labels by default.

For scratch analysis, the agent can think in rough buckets:

- strong candidate
- tentative candidate
- probably workflow note
- probably interesting-only

But approved opinions should usually enter the document as normal opinions unless Ryan explicitly asks for a separate
hypotheses section.

## Coding-Agent Boundary

Coding-agent tactics usually belong outside `OPINIONS.md`, likely in a personal README or workflow document.

They can become opinions when they generalize into a stance about software, human judgment, AI agents, verification,
organizational leverage, or system design.

Examples:

- Workflow note: "Use a plan file before implementing."
- Opinion: "In agentic software work, humans should own intent and verification more than implementation."
- Workflow note: "Stay in the smart half of the context window."
- Opinion: "Agent performance depends heavily on context design, not only model capability."

## Practical Proposal Test

Before proposing an opinion, ask:

1. Is this a stance rather than a summary?
2. Is it more than an obvious or consensus practice?
3. Is it plausibly Ryan-endorsable from the evidence?
4. Is it broader than a one-off workflow tactic?
5. Is it specific enough to guide future judgment?
6. Is it understandable without rereading the source material?
7. Should it be split into multiple opinions instead of merged?
