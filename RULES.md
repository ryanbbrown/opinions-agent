# Opinion Selection Rules

These rules describe how this project should decide whether a highlight, document note, or synthesized claim is worth proposing as an opinion.

## Core Definition

An opinion is a personally endorsable stance, not merely an interesting claim.

The agent cannot know endorsement directly. Its job is to propose claims that look plausibly Ryan-endorsable based on highlights, document notes, prior accepted/rejected decisions, and surrounding context. Actual endorsement happens when Ryan approves, rejects, or revises the proposal.

## Generation Rules

- **Prefer stances over summaries:** A proposed opinion should make a judgment, prioritization, prediction, tradeoff, causal claim, or decision rule. It should not just restate what an article said. A causal claim about how systems, markets, or people behave is a stance in its own right — do not convert it into a how-to recipe; when you do state a prescription, keep the causal claim that justifies it in the same opinion.
- **Avoid empty consensus, not familiar claims:** If a claim is so bland that stating it guides no decision, it is not opinion-worthy. But do not reject a claim merely because it sounds familiar: a familiar practice or belief argued with a specific mechanism, bound, or tradeoff can still be an endorsable stance. The contrast does not need to be stated explicitly; the opinion sentence itself should carry the stance.
- **Filter reference material, not topics:** A highlight that is a checklist, template, step list, fact, or tactic dump without an argued stance is reference material — do not turn it into an opinion. But when a source argues for a practice by giving the mechanism, tradeoff, or consequence that makes it matter, the argued stance is eligible even when the practice is common. "Write a plan before using a coding agent" is probably a workflow rule; "Humans should own intent and verification more than generated implementation" is an opinion.
- **Make opinions understandable in isolation:** If an opinion depends on a specific example, mechanism, or term of art, include enough context in the opinion sentence or bullet. The reader should not need to remember the source material to understand the claim.
- **One proposal per argument:** Broad themes can contain multiple opinions. Merge evidence into one proposal only when it supports the same central claim; shared topic, shared source, or adjacent theme is not enough. When two documents each argue their own claim on the same theme, propose them separately — bundling two arguments into one proposal forces a single approve/reject on both and waters each down. The reverse also holds: when several documents argue the same claim, write one opinion that carries each document's contribution to it.
- **Extend existing opinions instead of skipping near-duplicates:** When selected evidence strengthens, extends, or bounds an opinion already in OPINIONS.md, propose a revision of that opinion that folds the new concept in, citing the new evidence. Treat evidence as duplicate only when it adds nothing the existing opinion does not already say.
- **Preserve unresolved tensions in scratch work:** If evidence supports two related stances that are not actually contradictory, keep both. If they conflict, preserve the tension until Ryan decides which stance to endorse.
- **Treat document notes as stronger evidence than ordinary highlights:** A document note is already closer to Ryan's interpretation, so it should carry extra weight when deciding whether a claim is plausibly Ryan-endorsable.
- **Market and strategy predictions can count:** Claims about the direction of AI, company structure, moats, careers, and software work are eligible when they are broad enough to guide future judgment.
- **Taste judgments can count:** Beliefs about polish, craft, signal, quality, and what makes software or writing good are eligible opinions.
- **Career, work-life, and self-management judgments can count:** Pragmatic beliefs about jobs, leverage, learning, useful work, ambition, energy, and pace are eligible when they are durable rather than merely circumstantial. Do not filter a stance for being personal or reflective rather than analytical; stances about how to work and live are as endorsable as claims about AI and markets.

## Opinion Writing Fidelity

A well-formed opinion compresses one argument without losing its parts. Anchor it on the claim the source actually centers, and alongside the stance itself preserve:

- **The mechanism.** Keep the "because" that makes the claim work. "Organizations ship their org chart" is weaker than "system architecture mirrors team communication structure (Conway's law), so restructure the teams before trying to redesign the system."
- **The concrete anchors.** If the evidence hangs the claim on a named term, law, example, product, number, or formula, keep that name in the opinion sentence itself. Named specifics make an opinion more durable and memorable, not less — do not swap them for generic abstractions.
- **The full enumeration.** When the argument enumerates its members — the categories, layers, kinds of assets, or steps that make up the claim — keep the whole enumeration by name in the opinion. Do not compress a list into a vague plural ("several factors") and do not keep only its most familiar members; the least familiar member is usually what makes the opinion distinctive.
- **The bounds and corrections.** If the source bounds the claim — a condition, an exception, an "only when Y" — the bound is part of the claim. Likewise, when the claim corrects a default assumption — rejecting a familiar position, or insisting a familiar factor is insufficient on its own — state that correction explicitly instead of writing only the positive replacement; dropping the negation turns a correction into a platitude.
- **Both halves of the argument.** When a single argument has two co-equal parts — a stance plus its consequence, a rejected default plus its replacement, a claim plus its counterweight — one opinion should carry both. If evidence says a durable advantage requires both proprietary distribution and faster feedback loops, do not compress that to "distribution matters." This applies within one argument; distinct arguments still get separate proposals.

Compress by tightening the wording, not by deleting these ingredients. Default to the faithful, fuller opinion: Ryan can approve a shorter revision, but a missing core concept forces unnecessary back-and-forth.

## Confidence

The final opinions document does not need explicit confidence labels by default.

For scratch analysis, the agent can think in rough buckets:

- strong candidate
- tentative candidate
- probably workflow note
- probably interesting-only

But approved opinions should usually enter the document as normal opinions unless Ryan explicitly asks for a separate hypotheses section.

## Coding-Agent Boundary

Coding-agent tactics usually belong outside `OPINIONS.md`, likely in a personal README or workflow document.

They can become opinions when they generalize into a stance about software, human judgment, AI agents, verification, organizational leverage, or system design.

Examples:

- Workflow note: "Use a plan file before implementing."
- Opinion: "In agentic software work, humans should own intent and verification more than implementation."
- Workflow note: "Stay in the smart half of the context window."
- Opinion: "Agent performance depends heavily on context design, not only model capability."

## Practical Proposal Test

Before proposing an opinion, ask:

1. Is this a stance rather than a summary?
2. Would it guide a real decision, rather than stating empty consensus?
3. Is it plausibly Ryan-endorsable from the evidence?
4. Is it broader than a one-off workflow tactic?
5. Is it specific enough to guide future judgment?
6. Is it understandable without rereading the source material?
7. Should it be split into multiple opinions instead of merged?
