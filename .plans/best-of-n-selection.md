# Best-of-N Draft Selection — design notes for the next experiment session

Handoff notes from the 2026-07-05 session. Read `eval/experiments.md` (through the `slot-structure` entry) and `eval/opinion_anatomy.md` first; this doc explains why selection is the next lever and sketches the design space so the next session starts from evidence, not from scratch.

> **Update (2026-07-05, critic-2 counterfactual probe — see ledger):** re-judging pre-critic drafts across all four critic-2 runs decomposed its +0.10 edge: revisions contribute ~+0.04 on average (never negative, largest on the worst run — the critic clips the left tail and creates the 0.70 floor), and the rest is an *audience effect* — drafts written for an omission-auditor are measurably fuller (44–48 words pre-critic vs anchor-examples' 42–45 finals) under identical writing rules. Design consequence for best-of-N: selection plays the critic's audit role, and the prompt should preserve the audience effect (tell the agent drafts will be judged for slot-completeness before one is chosen).

## Why selection, in one paragraph

`opinion_attempted` sits at 0.94–1.00 on every variant: the agent reliably proposes the right claims. `opinion_quality` sits at 0.49–0.68 because individual drafts randomly omit one or two load-bearing elements — a named specific (Price's Law, "operational scars", "the hook"), an enumeration member, a correction ("not X"), or the payoff clause. Three structurally different instruction designs were tried on 2026-07-05 alone (trimmed checklist → 0.531, compact default → 0.488, generative slot grammar → 0.600) and all leave roughly the same per-draft omission lottery; the judge-variance diagnostic had already shown the run-to-run spread is proposal variance, not judge noise. Instruction wording is exhausted as a lever. Sampling attacks the variance directly: draft N candidate phrasings per opinion, select the one that carries all the slots. Unlike critic-driven rewriting (critic-1, 0.452, rewrite churn broke stable targets), selection cannot produce anything worse than the best candidate.

## Design space

**Option A — pure prompt (start here).** Instruct the drafting flow in `prompts.py`: for each proposal, write 2–3 candidate phrasings that all try to carry every slot the argument provides, then compare candidates against the evidence (which slots does each carry?) and send the most complete one. Zero harness change, cheapest, fully inside the legal levers. Risk: self-selection in one context may anchor on the first draft; check traces to confirm candidates genuinely differ and selection is real.

**Option B — host-side selector tool (if A shows anchoring).** A `select_opinion_draft` ToolSpec in `agent.py` mirroring the critic-2 pattern: agent submits N candidate texts + evidence_ids; the host looks up evidence texts and asks a selector model (isolated context) which candidate carries the most load-bearing elements of the evidence's argument; returns the winning candidate **verbatim**. Precedent: critic/critic-2 added a ToolSpec in `agent.py` as a user-approved deviation from the prompts-only edit scope — get the same sign-off before touching `agent.py`.

## Selection rubric

Use the slot grammar from `eval/opinion_anatomy.md`: stance (including any correction of a default), engine (mechanism or enumeration members by name, both halves of a compound), payoff (prescription, consequence, rule, or bound). The selector question is "which candidate carries the most slots present in the evidence's argument?" — never "which is best written".

Lessons already paid for, do not relearn:

- **Selector never rewrites, never asks for removals, never enforces vocabulary** (critic-1 broke six stable targets exactly this way; critic-2's omission-only redesign fixed it).
- **Extra content never hurts the judge** — prefer the more complete candidate on ties; length is a reference metric (`opinion_brevity`), not a gate.
- **Compactness pressure converts directly into concept drops** (compact-default: perfect coverage, 0.488 quality). Do not tell drafts to be short; the 2–3 clause shape bounds length on its own (slot-structure landed ~41 words unprompted).
- **Anti-leakage:** the slot grammar is fine to use; per-opinion content from `eval/opinion_anatomy.md` or the targets is not. Run `uv run python eval/check_leakage.py .worktrees/<exp>` before every eval run.

## Practical parameters

- **N = 2–3.** Drafting is a small fraction of run cost (most tokens are evidence reading); a slot-structure-style run cost ~$0.55 total, so even 3× drafting headroom is cheap. Watch `duration` and `estimated_cost` on r1 anyway.
- **Base branch: `exp/critic-2` — the current best (promoted 2026-07-05).** Its precision holds above the floor (0.521 pooled, 0.540 on r4), unlike the critic-less anchor-examples lineage (0.497–0.507). Selection composes naturally with the omission-only critic: draft N, select the most slot-complete, then the critic checks the winner. If the combination underperforms, a critic-less fallback base with precision headroom is `exp/keep-the-list` (0.53); optionally include the slot-grammar RULES.md rewrite (`exp/slot-structure`, commit `0430853`, screened 0.600) as the drafting instruction.
- **Also test slot grammar with the critic directly.** A smaller experiment than best-of-N is `exp/critic-2` plus the slot-structure RULES.md rewrite (`0430853`): slot grammar shapes the first draft, then the omission-only critic audits it. This is worth a screen because slot-structure alone improved some slot-drop targets and bounded length, while critic-2 supplies the audit/audience effect that the critic-less branch lacked.
- **Score to beat: 0.780** (`critic-2` pooled: {0.877, 0.710, 0.700, 0.831}, floor 0.70) under `scoring_version: 2026-07-05-plain-language`. Screen with one run (`--variant <exp>`), replicate with `--run 2/3` only if the screen clears; precision floor 0.50 applies to the replicate mean.
- **The explicit second objective is length recovery.** critic-2 writes the longest opinions of any variant (`opinion_brevity` 0.695; r4 mean 49.5 words vs golden ~34). A best-of-N variant that holds quality within noise of 0.780 while lifting brevity meaningfully (say toward 0.85+) is a win worth promoting even without a quality gain — selection should prefer the *shortest slot-complete* candidate, which is exactly the tradeoff instructions alone could not buy (see compact-opinions/compact-default).
- **Plateau counter:** the 2026-07-05 stop (compact-opinions, compact-default, slot-structure) was superseded by the critic-2 promotion; best-of-N starts a fresh count.

## Session mechanics (footguns)

- **Main's working tree is intentionally uncommitted** (Ryan authorizes every commit). All current measurement infrastructure — plain-language targets, `--variant`/`--run` CLI, `opinion_brevity` scorer, thinharness 0.5.1 — exists only as dirty files on main. Experiment worktrees branch from `exp/*` commits that predate it, so after `git worktree add`, copy these from the main checkout into the worktree (uncommitted): `eval/opinion_targets.{jsonl,md}`, `src/opinions_agent/evals/{runner,scorers}.py`, `src/opinions_agent/cli.py`, `pyproject.toml`, `uv.lock`. Best fix: ask Ryan to commit main first, then rebranch — the copy step disappears.
- Commit only the lever changes to the `exp/` branch (prompt-only diff); never commit to main unprompted.
- `tests/test_prompts.py` asserts hardcoded prompt substrings (against the project's own testing rule); editing the drafting instructions in `prompts.py` may break assertions — drop the stale assertion rather than re-stating the new wording.
- Read scores with `uv run python eval/inspect_experiment.py <run> --vs keep-the-list-r1-rs-2026-07-05 keep-the-list-r2-rs-2026-07-05 keep-the-list-r3-rs-2026-07-05`.

## Resolved: critic-2 is the current best

`critic-2-r4` (fresh native run, 2026-07-05) scored 0.831 — all four critic-2 samples under current scoring are ≥ 0.70 ({0.877, 0.710, 0.700, 0.831}, mean 0.780) vs keep-the-list's {0.548, 0.727, 0.754}. Ryan confirmed promotion; the ledger header reflects it. Best-of-N therefore builds on top of critic-2, with selection upstream of the critic's omission check, and length recovery as the stated second objective.
