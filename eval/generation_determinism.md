# Can opinion generation be made near-deterministic?

Analysis of whether a single, template-like generation procedure — anchored as closely as possible to the source material — could produce essentially the same opinion from the same highlights every run, and what that would require of the golden set. Written 2026-07-06 at Ryan's direction, from the four critic-2 pool runs (`2026-07-05-plain-language`), the judge-calibration audit, and a full provenance audit of all 33 golden opinions against the corpus.

**Leakage warning:** like `eval/opinion_anatomy.md`, this file describes the test set. The generalized procedure may inform prompts; never copy per-target content, phrasing, or the per-target table below into `prompts.py` or `RULES.md`.

## The core finding

Reading all four critic-2 generations side by side for a sample of targets splits them into two clear populations:

- **Convergent targets** come out as nearly the same sentence every run — same clauses, same vocabulary, same order (W13-01's "faithful compression / L1/L2/L3", W04-03's generalist-vs-domain-specific, W06-02's domain-reasoning-vs-plumbing). These pass 4/4.
- **Divergent targets** come out genuinely different every run — different center, different framing, different imported details (W04-05 centers delivery-practice one run and the polished-vs-truthful contrast another; W08-02 centers "use > polish" twice and a *different highlight* — the Yglesias professionally-managed-software claim — once; W06-01 sometimes writes the highlight's Figma claim and sometimes the article's broader "truth to materials" thesis). These are the flaky and stubborn targets.

What separates the populations is not slot structure, length, or topic. It is **whether the golden opinion is fully pinned by the evidence the agent is required to cite**. When the golden is the union of the required highlights' claims restated in the source's own vocabulary, the model reliably writes the same sentence. When the golden contains anything the highlights don't pin — an article-body clause, an added inference, a dropped highlight — each run resolves the freedom differently.

A content-word overlap check across all 33 targets corroborates the sample reading: targets in the top half of cross-run vocabulary convergence pass 3.75/4 on average; the bottom half pass 2.62/4, and the stubborn set (W08-02, W05-03, W06-01, W04-05, W08-01/03/04) is exactly the low-convergence tail.

## Provenance audit of the 33 goldens

Each golden's load-bearing clauses were classified against its required sources: **HV** (near-verbatim in a required highlight/summary), **HR** (same claim reworded), **ART** (only in unhighlighted article body), **INF** (stated nowhere in the source). Verdict: could a mechanical "restate every required highlight's claim in the source's own vocabulary, add nothing unhighlighted" procedure reproduce this golden essentially every time?

**Tally: 18 YES · 8 MINOR-EDIT · 7 NO.**

| Target | Verdict | Reason |
|---|---|---|
| W04-01 | MINOR-EDIT | "commoditizes scaffolding"/"bottleneck" are unhighlighted body headers; the highlight's own framing ("coding/prompting stop being the scarce skill") would pin it |
| W04-02 | MINOR-EDIT | erosion-of-advantages payoff is unhighlighted body; the highlight ends at "never comes back out" |
| W04-03 | YES | every clause in the required summary |
| W04-04 | NO | 3 of 4 clauses (don't-wait thesis, managers-can-help, seek-scope) distill unhighlighted article; the highlight holds only the 1:1-script advice |
| W04-05 | YES | faithful weave of the three required highlights ("signal", "tradeoffs" cosmetic) |
| W05-01 | YES | payoff verbatim; concession is a fair inversion of the highlighted misconception |
| W05-02 | YES | all clauses HV/HR across the 3-highlight cluster |
| W05-03 | YES | core claim verbatim (its eval failures are coverage, not wording) |
| W05-04 | YES | four-functions enumeration verbatim from the highlight |
| W06-01 | YES | all clauses from the one Figma highlight (failures come from importing article framing instead) |
| W06-02 | YES | both clauses near-verbatim |
| W06-03 | MINOR-EDIT | required summary is descriptive about Sierra; golden generalizes to a normative "should" and imports body verbs |
| W06-04 | YES | near-verbatim single highlight |
| W08-01 | YES | "the hook" is in the required highlight |
| W08-02 | MINOR-EDIT | enumeration includes "repos" (body-only) and "demos" (nowhere); highlights give tests/documentation |
| W08-03 | NO | diminishing-returns/compounding mechanism and reading/podcasts examples come from two unhighlighted paragraphs; the lone highlight holds only the bare stance |
| W08-04 | YES | both highlights cover all three clauses |
| W10-01 | YES | ("visible" cosmetic) |
| W10-02 | MINOR-EDIT | "well-rounded" exists only in the article body; both other clauses verbatim from highlights |
| W10-03 | YES | "cognitive debt" is highlighted |
| W11-01 | YES | borderline: trims two highlighted list members (playbooks, specialist talent) |
| W11-02 | YES | all three clauses verbatim |
| W11-03 | YES | restates Ryan's own document notes |
| W11-04 | NO | asset list and pay/title/brand foil from unhighlighted body; the required highlight lists **brand as an asset**, the golden uses it as the foil |
| W11-05 | YES | all clauses from the three highlights |
| W12-01 | NO | adds unhighlighted "cheap to generate" premise AND drops the required highlight's slop-pushback claim |
| W12-02 | YES | clean two-highlight cluster |
| W12-03 | MINOR-EDIT | routine-work/synchronous clause is body-only (though the doc *summary* says "routine tasks"); the taste clause is verbatim |
| W13-01 | NO | "complete references remain searchable" clause is body-only; drops the required highlight's domain-expertise claim |
| W13-02 | NO | the target/constraints/instruments/examples taxonomy is article-body synthesis; highlights give only cheap-paths + expected-output-examples |
| W13-03 | MINOR-EDIT | "learning under uncertainty" stance is a body quote, not the required highlight |
| W13-04 | MINOR-EDIT | "complex, private work that can't be easily measured or copied" is verbatim the **document summary**, which is not in required_sources |
| W13-05 | NO | cross-week update: SQLite/specs/verification content lives in the prior opinion, not this week's evidence; its lone highlight shares a document and theme with W13-02, so clustering merges it |

Cross-checking verdicts against the critic-2 pool confirms the causal story in both directions:

- Audit-YES targets that still flake today (W04-05 1/4, W06-01 2/4, W08-04 2/4) fail by violating exactly the procedure's constraints: under-covering one required highlight's claim, or importing article framing instead of the highlight's. Nothing in the current instructions forces either.
- Audit-NO targets that often pass anyway (W13-01 4/4, W12-01 4/4, W04-04 3/4) pass because the agent happens to read the article and surface the body content that run — a per-run lottery. W10-02's one failure is precisely the run that didn't import "well-rounded."

Two structural failure modes sit outside writing entirely and no template fixes them: W05-03's misses are *coverage* (the proposal was never made), and W13-05's are *routing* (evidence that should update a prior-week opinion gets absorbed into a sibling cluster).

Alternate-center hygiene is otherwise clean: nearly every non-required sibling highlight is either another target's evidence or explicitly listed in `not_converted` — so "one proposal per highlight cluster" has well-defined boundaries in this corpus.

## Why the current setup cannot converge

Two instructions in the current prompts are the variance engine, and the golden set is co-adapted to them:

1. "Anchor it on the claim **the source** actually centers" — source-level, not highlight-level. On multi-claim documents each run may center a different claim (W08-02, W06-01).
2. The post-read enrichment rule — check whether the source contains a concrete example/mechanism/term "that would make the opinion more concrete, faithful, or memorable" — explicitly licenses importing unhighlighted content. Whether a given run imports the *right* body detail is a coin flip, and ~15 goldens are only reachable by winning it.

The goldens were evidently authored with the whole article in hand, so hitting them *requires* the lottery. This also explains why every instruction-level experiment since keep-the-list plateaued: templates and critics were being aimed at targets that are not functions of the evidence the agent is told to preserve. slot-structure failed not because a template is wrong but because the goldens are not fixpoints of any template over the highlights.

## The proposed procedure

Per document in the week's selection:

1. **Cluster.** Highlights (plus the document's note/summary row) that argue one claim form one cluster; one cluster → exactly one proposal. Distinct claims → separate proposals. Reference-material clusters → none.
2. **Slot each evidence row.** Each highlight contributes its claim to one slot: stance (with the source's correction-of-a-default if it states one) / mechanism / enumeration / bound / payoff.
3. **Compose by template.** Stance clause first; engine clause (mechanism or enumeration with members named exactly as the source names them); payoff clause if a highlight supplies one. Join with a semicolon, colon, or "so".
4. **Vocabulary constraint.** Every distinctive term comes verbatim from the evidence — named laws, coined terms, list members, product names. No new metaphors, no new categories, no umbrella abstractions ("not inventing new lingo").
5. **Coverage constraint.** Every highlighted claim in the cluster appears as a clause; nothing outside the cluster appears. Article reads only to complete a truncated highlight or resolve a referent — never to import concepts.
6. **Update routing.** Before drafting, search current OPINIONS.md for the cluster's named anchors/terms; on a hit, propose a revision that preserves the existing opinion's anchors and folds the new highlighted claim in.

Every content decision is then a function of the evidence set: what to include (all of it), what to exclude (everything else), which words (theirs). Residual freedom is connectives and clause order — which is what the already-convergent targets show today. "Deterministic" here means variance collapses to that level, not bit-identical output.

## What has to change for this to be measurable

The procedure only scores well if the goldens are its fixpoints. That means a golden-set revision (new `scoring_version`, Ryan-directed, outside the experiment loop):

- **8 minor edits** (W04-01, W04-02, W06-03, W08-02, W10-02, W12-03, W13-03, W13-04): drop or re-ground one clause per the table.
- **7 substantive decisions** (W04-04, W08-03, W11-04, W12-01, W13-01, W13-02, W13-05): either re-scope the golden to what the highlights actually pin, or accept that these targets test something other than highlight-faithful writing (article synthesis, cross-week routing) and score them separately.
- **Evidence-policy decision:** pin evidence as required highlights + document notes + the document's generated summary (the summary already appears in every selected-evidence row, is fixed text in the corpus, and several ART clauses — W13-04, W12-03, W06-03 — are actually summary content). That is strictly more recoverable than highlights-only at no determinism cost.
- **Judge alignment:** grade "does the proposal carry each required evidence row's claim" — which also fixes the evidence-bleed false negatives the judge-calibration audit found.
- **Instruction change:** replace source-level anchoring + the enrichment rule with the cluster/coverage/vocabulary procedure. This *replaces* the fidelity bullets rather than adding to them.

## Caveats

- **Product tradeoff.** Highlight-anchored opinions stop adding unhighlighted strategic payoffs (W04-02's erosion clause is genuinely good and genuinely not in the highlight). Two mitigations: the Telegram approval loop is where Ryan adds inference, and highlighting itself becomes the interface — the payoff clause gets pinned by highlighting the sentence that states it.
- **Leakage discipline.** Golden edits must be anchored to the highlights, never to observed agent generations, or the revision quietly becomes "whatever the agent writes."
- **Coverage and routing stay separate.** W05-03 (proposal never made) and W13-05 (update routing) need their own deterministic rules (step 6 plus a propose-every-stance-cluster duty); no writing template touches them.
- **Precision guardrail.** The procedure barely changes eligibility judgment; the `not_converted` layer and the 0.50 precision floor still do that work.
