# Eval Optimization Experiments

Append-only ledger of prompt-optimization experiments, owned by the driver in the **main checkout** — worktree copies are disposable and invisible to each other, so results must be recorded here. One entry per experiment, newest at the bottom. See `eval/GOAL.md` for the protocol. Braintrust (project `opinions-agent`) holds the full scores and traces; this file is the narrative history so the loop can build on prior results without a round-trip.

Cost note: do not budget off Braintrust's `estimated_cost` — it prices every input token at full rate and ignores OpenAI's automatic prompt caching (thinharness discards the `cached_tokens` detail), so it runs ~1.8x high. A full 9-week run is ~$5, not ~$10.

**Current best:** `main` (baseline — unmodified prompts; branch experiments chain from here until a winner is promoted)

**Score to beat:** 0.374 mean `opinion_quality` (pooled baseline samples: 0.358 `baseline`, 0.390 `binary-judge-rescore`). On promotion, update this to the new best's replicate mean.

## Entry format

Each entry records:

- **Experiment** — matches the Braintrust `--experiment` name.
- **Hypothesis** — the change and why it should help.
- **Changed** — one-line summary of the `prompts.py` / `RULES.md` edit.
- **Scores** — mean `opinion_quality` (primary), `evidence_recall`, `evidence_precision`.
- **Verdict** — promoted or reverted, and why.
- **Learned** — anything that should steer the next experiment.

---

### baseline

- **Hypothesis:** Establish the unmodified-prompt scores that every variant must beat.
- **Changed:** none (current `prompts.py` and `RULES.md`).
- **Scores:** opinion_quality 0.358, evidence_recall 0.877, evidence_precision 0.575 (fresh 9-week run under the current binary judge). A prior run's outputs re-judged by the same judge (`binary-judge-rescore`) scored 0.390 / 0.939 / 0.589 — a ~3–6pt run-to-run spread on the same prompt, which is the noise floor variants must clear.
- **Verdict:** current best by default.
- **Learned:** Agent runs are stochastic (proposal count and which evidence converts vary per run); a single run's aggregate is noisy to ±3–6pt.

### fidelity-check

- **Hypothesis:** The dominant `opinion_quality` failure is the agent preserving a stance but dropping a load-bearing piece of the canonical claim. Operationalizing fidelity with a concrete pre-send check should lift quality where concepts were dropped.
- **Changed:** `RULES.md` "Opinion Writing Fidelity" — added a pre-send check that names the four categories most often lost (co-equal second half of a two-part claim; bounding conditions/caveats; named example/term/mechanism/number; the evidence's actual center of gravity vs a substituted thesis). `prompts.py` unchanged.
- **Scores:** opinion_quality 0.308 (−0.050), evidence_recall 0.849 (−0.028), evidence_precision 0.557 (−0.018). Single run.
- **Verdict:** Not promoted. Net-negative on a single run.
- **Learned:** The change has real directional signal — all 4 fail→pass flips (W04-01, W08-01, W08-03, W11-04) are exactly the concept-drop failures it targets. But 6 previously-passing targets flipped to fail (W04-03, W04-04, W05-02, W05-03, W11-03, W13-02), for net −2. With 10 targets flipping in one run and noise at ±3–6pt, a single run cannot separate the 4 real gains from noise churn — this is the concrete case for the multi-run + replicate rule. If revisited: run 2–3x to see whether the 4 gains replicate and the 6 losses are stable or noise, and test a leaner phrasing (the check added ~8 lines) to check whether a tighter version keeps the gains without the churn.
