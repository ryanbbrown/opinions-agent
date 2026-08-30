# Consolidator quick view

The reviewed eval has 34 target claims. Only 3 should consolidate into existing opinions. The other 31 should remain new opinions.

## Current consolidator prompt

Source: [`src/opinions_agent/prompts.py`](../src/opinions_agent/prompts.py)

```text
You are an opinion consolidator. Each task names exactly one saved candidate ID. Decide only whether all or part of
that candidate belongs inside one existing opinion.

First call get_candidate_context with the candidate ID. It returns the candidate, its selected evidence, and the
current opinions document. Search that returned document for existing opinions that express the same durable belief.
Call get_opinion_sources only for a targeted current opinion ID when its existing support is needed to preserve the
opinion's complete claim.

Return native structured output as either null or one object with exactly these fields:
- existing_opinion_id: one current opinion ID;
- opinion_text: the complete resulting text for that existing opinion;
- evidence_ids: a non-empty subset of the candidate evidence IDs that move to it.

Return JSON null itself when all candidate evidence and claim should remain with the new opinion. Never encode null as
an object, placeholder opinion ID, `opinion-000000`, or the text "null".

Consolidation requires the same core belief, not merely the same section, topic, theme, or audience. Use this test: could
the candidate evidence directly support the existing opinion's current core claim before any wording change? If not,
return null. Return null when combining them would need an umbrella thesis, a bridge such as "and" or "while", or a
broader rewrite that grafts an adjacent claim onto the existing opinion. Similarity is not enough, and avoiding a new
opinion is not a goal. When unsure, return null.

Return an object only when the moved evidence truly strengthens or extends the named existing opinion's current core
belief. Preserve that core belief in the complete resulting text. Existing evidence stays attached and must not be
repeated. If the current opinion already expresses the moved evidence completely, opinion_text may be unchanged.

You may target only one existing opinion. You cannot discard evidence, create or rewrite the residual new opinion,
target several opinions, remove or split an opinion, reorder opinions, edit files, or write Telegram messages.
```

## The 3 expected consolidations

### W04-01 → `opinion-000003`

Evidence: *The Most Important Ideas in AI Right Now* — `rw:01kp1xajs4em2bhwcs3rz0j2wq`

Existing opinion:

> AI makes implementation cheaper, but it does not make judgment cheap; the scarce work becomes deciding what is worth building, what good looks like, and whether an agent's output is actually good.

Result after consolidation:

> As AI commoditizes implementation, high-quality intent becomes the scarce skill: having ideas worth pursuing, articulating what good looks like, and judging whether an agent's output is actually good.

Why: the new evidence strengthens the same belief about the scarce human skill after implementation becomes cheap.

### W08-05 → `opinion-000009`

Evidence: *Reality's Moat* — `reader-note:01kksy9drnnqysr6tb5e2n0pw3`

Existing opinion:

> AI commoditizes knowledge that can be specified or copied, while operational knowledge compounds in changing systems because staying current requires ongoing real-world learning. This moat disappears when the underlying system is replaced.

Result after consolidation:

> AI commoditizes knowledge that can be specified or copied, while operational scar tissue compounds in coupled, changing systems because each real-world surprise changes both the system and how future surprises should be interpreted. This moat disappears when the underlying system is replaced.

Why: the reader note gives the mechanism and sharper language for the same operational-knowledge moat.

### W12-01 → `opinion-000002`

Evidence: *How AI Productivity Fails* — `rw:01kt7p7hczwhjqkstr4zeqhpzx`, `rw:01kt7p7s76qx5c04gzkw0mn0tz`

Existing opinion:

> Making code cheap to generate does not make system comprehension cheap to skip.

Result after consolidation:

> Making code cheap to generate does not make ownership or system comprehension cheap to skip; people should understand AI-generated artifacts well enough to defend them under questioning.

Why: the new evidence extends the same comprehension belief with ownership and the requirement to defend the work.

## The 31 claims that should stay standalone

For these targets, the consolidator should return `null`:

- W04: `W04-02`, `W04-03`, `W04-04`, `W04-05`
- W05: `W05-01`, `W05-02`, `W05-03`, `W05-04`
- W06: `W06-01`, `W06-02`, `W06-03`, `W06-04`
- W08: `W08-01`, `W08-02`, `W08-03`, `W08-04`
- W10: `W10-01`, `W10-02`, `W10-03`
- W11: `W11-01`, `W11-02`, `W11-03`, `W11-04`, `W11-05`
- W12: `W12-02`, `W12-03`
- W13: `W13-01`, `W13-02`, `W13-03`, `W13-04`, `W13-05`

The four-week smoke made the failure mode clear: among the 12 add targets that completed, the workflow kept only 1 as an add and incorrectly revised an existing opinion for the other 11.
