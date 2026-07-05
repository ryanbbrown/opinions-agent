# Anatomy of the 33 golden opinions

Reference analysis of the eval test set (2026-07-05, plain-language targets), derived for the slot-structure experiment and kept as the basis for draft-selection rubrics. **Leakage warning:** this file describes the test set. Generalized structure (the slot grammar) may inform prompts; never copy any per-opinion content, phrasing, or the per-opinion breakdown below into `prompts.py` or `RULES.md`.

Every golden opinion is one or two sentences, 25–53 words, built from **2–3 load-bearing clauses** joined by a semicolon, colon, or "so". No opinion is a single bare claim. The recurring slots:

- **STANCE** — the claim itself, very often stated *against a default* ("X is not about Y", "not just", "instead of", "rather than")
- **ENGINE** — what makes it true: a because-mechanism, or the named members of an enumeration
- **PAYOFF** — the so-what: a prescription, consequence, decision rule, or bound ("so…", "should…", "only when…")

Slot frequencies across 33 opinions:

| Slot | Count | Note |
|---|---|---|
| ≥2 load-bearing clauses | 33/33 | the defining property |
| Correction of a default | 22/33 | the most common stance form |
| Explicit payoff clause | 19/33 | prescription, consequence, or rule |
| Enumeration (named members) | 16/33 | 3–5 members typical |
| Because-mechanism | 15/33 | |
| Bound / condition | 9/33 | "only when", "where", "if" |
| Named-entity anchor | 4/33 | Figma, Price's Law/√n, SQLite, "the hook" — rare |

Punctuation: ~21/33 use a semicolon joint, ~7 a colon joint, ~5 flow as a single sentence with "but/and".

## Per-opinion breakdown

| Target | Words | Structure |
|---|---|---|
| W04-01 | 34 | cause ("as AI commoditizes…") → stance : enumerated unpacking (3 members) |
| W04-02 | 37 | stance + enum (4 destinations) + ratchet mechanism ; consequence ("advantages will erode") |
| W04-03 | 31 | stance + because-mechanism ; bound ("mainly make sense if physical limits") |
| W04-04 | 44 | correction ("not something to wait for") : prescription enum (3 actions) + anti-default |
| W04-05 | 37 | bounded stance ("only creates signal if") ; contrast (truthful account vs polished story) |
| W05-01 | 34 | concession + correction ("do not remove the need") ; mechanism (detailed spec becomes code) |
| W05-02 | 32 | prescription enum (thin harness / skills / deterministic tools) → so-payoff (improvements compound) |
| W05-03 | 33 | correction ("does not need to beat idealized") ; recentered stance + mechanism |
| W05-04 | 38 | correction ("do not need work") ; enum (4 functions) → so-payoff + correction ("not just income") |
| W06-01 | 37 | anchored stance (Figma) : bound ("when product lives in code") → prescription + contrast |
| W06-02 | 28 | stance ; counterpart stance + rather-than contrast |
| W06-03 | 29 | prescription + enum (scope/build/review/reason) + instead-of contrast |
| W06-04 | 52 | stance : mechanism chain (slop → desloppify → leverage) ; bound ("if AI displaces… may fade") |
| W08-01 | 41 | correction ("not just… but") : mechanism (defaults generic) → so-prescription + anchor (the hook) |
| W08-02 | 33 | when-context + enum (repos/tests/docs/demos) → stance contrast ; prescription (operational proof) |
| W08-03 | 28 | concession + stance ; counterpart + because-mechanism (returns compound) |
| W08-04 | 27 | prescription ("should simplify") : do/don't pair (structure+examples vs if-else sprawl) |
| W10-01 | 25 | stance + two where-conditions + outcomes-not-effort contrast |
| W10-02 | 36 | correction ("not well-rounded") ; anchor (Price's Law, √n) + mechanism → so-prescription |
| W10-03 | 29 | stance + correction ("not just issue-closing") ; if-condition enum (3) → consequence (cognitive debt) |
| W11-01 | 34 | only-when bounded stance ; asset enum (4 members) |
| W11-02 | 30 | prescription enum (4 things to map) ; anti-pattern warning (rip-and-replace) |
| W11-03 | 33 | correction ("should not treat bash as necessary") ; replacement contrast (constrained tools) |
| W11-04 | 27 | prescription + enum (5 assets) + not-just correction enum (3) |
| W11-05 | 28 | stance + correction ("not endless escalation") ; because-mechanism → prescription enum (3 actions) |
| W12-01 | 27 | correction-stance ("cheap to generate ≠ cheap to skip") ; operational test (defend under questioning) |
| W12-02 | 31 | stance + correction ("not by how many workers") ; decision rule (what you can evaluate) |
| W12-03 | 33 | balanced two-part prescription + where-bound + shaping-not-approving correction |
| W13-01 | 43 | definition stance ("faithful compression") : tier enum (always-loaded / discoverable / searchable) |
| W13-02 | 33 | stance : if-condition enum (4) → consequence + instead-of correction |
| W13-03 | 30 | definition stance ; prescription ("expose unknowns quickly") + source enum (5) |
| W13-04 | 35 | mechanism ("leaderboard → trainable") → so-stance ; consequence (where durable value moves) |
| W13-05 | 46 | enum stance (4 artifact kinds) + because-mechanism ; anchor example (SQLite) |

## What the failures look like against this grammar

The compact-variant failures are precisely "filled fewer slots than the canon": W05-02 wrote stance+engine and dropped the payoff; W12-01 wrote the payoff and dropped the correction-stance; W10-02 wrote stance+payoff and dropped the engine's anchor; W11-04 dropped one enum member (operational scars). The current fidelity bullets say "don't drop ingredients" from freeform text; the canon says opinions are *assembled from slots*.
