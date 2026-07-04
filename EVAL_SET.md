# Opinion Agent Eval Set

This is a first-pass human-reviewable eval set assembled from review-session feedback and backtest analysis. It is intentionally Markdown-first; the cases can be converted to structured JSON/YAML later.

Use these cases to evaluate prompt/context changes for opinion proposal quality, not Telegram workflow correctness.

## Scoring Dimensions

- **Faithfulness:** Preserves the important concepts, examples, numbers, mechanisms, and caveats from selected evidence and any source context the agent reads.
- **Opinion-worthiness:** Distinguishes durable personal opinions from reference material, checklists, tactics, setup notes, and generic career/life advice.
- **Consolidation:** Combines evidence only when it supports the same central claim; splits distinct claims even when they share topic, source, or vocabulary.
- **Context use:** Reads source context when the selected packet visibly needs it, and uses concrete details recovered from that context.
- **Categorization:** Uses or creates sections that fit the opinion, especially for agent design/building-agent material.

## W04

### W04-01: High-Quality Intent Must Preserve Idea Quality

**Source:** `The Most Important Ideas in AI Right Now`

**Selected evidence:**

> The new scarce skill isn't coding or prompting—it's being able to say what you actually want. And it has to be high-quality intent. The quality of the idea is always the most important thing. But the second most important is the ability to articulate it, define it as your actual goal, and orient the entire company around it.

**Observed issue:** Earlier generated opinions preserved "articulating intent" but dropped the key claim that the underlying idea must itself be high-quality. Some runs also over-consolidated this with generalized hill-climbing / ideal-state evidence.

**Canonical target:**

> As AI commoditizes execution, the bottleneck moves to high-quality intent: having ideas worth pursuing, articulating what good looks like, and turning that intent into criteria that agents and organizations can optimize toward.

**Expected behavior:** Preserve both parts: idea quality is primary, and articulating high-quality intent is the next scarce capability. If merged with hill-climbing evidence, the merged claim must still be one central claim and not flatten either source.

**Pass criteria:**

- Mentions high-quality ideas or high-quality intent, not just "intent."
- Does not imply articulation is more important than the idea itself.
- Does not merge unrelated adjacent AI/product-management claims into a vague thesis.

### W04-02: Interview Accomplishment Delivery

**Source:** `What I Learned From Nearly 1,000 Interviews at Amazon`

**Selected evidence:**

> You can have the most impressive accomplishment of your career ready for your interview and completely waste it with bad delivery.

**Feedback:** The framing was decent but missed the core point that a super impressive accomplishment may not matter if delivered badly.

**Canonical target:**

> In hiring, an impressive accomplishment only creates signal if the candidate can deliver it well; a truthful, practiced account of tradeoffs and close calls reveals more than a polished success story that hides how they actually think.

**Expected behavior:** Capture that accomplishment quality alone is insufficient; delivery and evidence of thinking determine whether the accomplishment creates signal.

**Pass criteria:**

- Explicitly ties impressive accomplishments to bad delivery reducing their value.
- Keeps the "how you think under constraints" point if using the broader interview evidence.

### W04-03: Knowledge Base Highlight Is Usually Reference Material

**Source:** `LLM Knowledge Bases`

**Selected evidence:**

> I find myself developing additional tools to process the data, e.g. I vibe coded a small and naive search engine over the wiki, which I both use directly (in a web ui), but more often I want to hand it off to an LLM via CLI as a tool for larger queries.

**Expected behavior:** Usually skip this as reference/tooling inspiration unless there is strong supporting context that Ryan endorses a durable principle about knowledge systems.

**Canonical target:**

> No proposal.

**Pass criteria:**

- Either no proposal, or a clearly opinion-worthy claim supported by more than the narrow tooling note.
- Does not inflate a concrete implementation note into a broad knowledge-management doctrine without support.

## W05

### W05-01: Average Company Operations Should Be Framed Sharply

**Source:** `Exactly Why and How AI Will Replace Knowledge Work`

**Selected evidence:**

> When you hear the argument that AI cannot compete with humans—inside of a company, this is what they have to compete with. This bar is not low. It is on the floor. It burned a hole through the floor. It is descending to the core of the earth.
>
> AI can follow instructions. The ability to follow instructions over and over, doing the same thing in a very uncreative way, is better than what is done in most companies most of the time.

**Feedback:** The generated opinion softened the source too much and appeared not to use enough surrounding context. It missed the sharper point that the way current average companies operate is not very good.

**Expected behavior:** If proposed, preserve the sharp claim about the low operational bar in typical companies. Do not turn it into a generic "AI helps organizations execute" statement.

**Canonical target:**

> AI does not need to beat an idealized version of knowledge work; in many companies it only has to beat messy, inconsistent operations where simply following instructions reliably is already above the current bar.

**Pass criteria:**

- Preserves the "bar is on the floor" idea in natural opinion language.
- Connects AI advantage to repeatable instruction-following versus messy company operations.

### W05-02: AI Displacement Must Preserve Work-Replacement Context

**Source:** `The Displacement of Cognitive Labor and What Comes After`

**Selected evidence:**

> What people actually seem to need is not work specifically but four things that work happens to provide: agency, contribution, mastery, and connection...

**Feedback:** Earlier output captured "agency, contribution, mastery, and connection" but missed that the article is specifically about AI displacing work and potentially making work unnecessary.

**Canonical target:**

> If AI displaces work, the problem is not only lost income; work currently supplies agency, contribution, mastery, and connection, so post-work institutions need to replace those functions rather than merely give people leisure.

**Expected behavior:** Include the AI-displacement / post-work frame when using this evidence.

**Pass criteria:**

- Mentions AI displacing work or work no longer being the default identity/institution.
- Preserves the four functions of work.

### W05-03: GitHub Fake-Star Metrics Are Borderline Reference

**Source:** `Inside GitHub's Fake Star Economy`

**Selected evidence:** Metrics such as downloads, issue quality, contributor retention, discussion depth, telemetry, fork-to-star ratio.

**Feedback:** This may be an interesting highlighted framework rather than a durable opinion. It is not terrible to propose, but it is an optimization target.

**Canonical target:**

> GitHub stars are too easy to fake to be a serious adoption signal by themselves; real open-source traction should be judged by costlier signals like downloads, issue quality, repeat contributors, deep discussion, telemetry, and a healthy fork-to-star ratio.

**Expected behavior:** Acceptable but lower priority. Prefer proposing only if it is framed as a durable signal/taste judgment, not just a copied metric list.

**Pass criteria:**

- If proposed, makes a clear judgment about costly adoption signals versus vanity metrics.
- Does not merely restate the checklist.

## W06

### W06-01: Preserve Figma In Claude Design Opinion

**Source:** `Thoughts and Feelings around Claude Design`

**Selected evidence:**

> as the source of truth shifts back to code, Figma is left in an odd spot: holding a largely manual, pre-agentic system that nobody in their right mind would design from scratch today.

**Feedback:** The generated opinion should stay closer to the raw highlight. Generalization to non-code tools and tools being close to what ships is fine, but Figma as an example is important and should be preserved.

**Canonical target:**

> In agentic product work, Figma is in an awkward position: when the product ultimately lives in code, the design source of truth should move closer to executable code rather than a manual, pre-agentic replica of the system.

**Expected behavior:** The opinion should include Figma as the concrete example or contrast, while still making the broader code-as-source-of-truth point.

**Pass criteria:**

- Mentions Figma by name.
- Preserves the "manual, pre-agentic system nobody would design from scratch today" idea.
- Does not abstract the example away into "design tools" only.

### W06-02: Golden Era / Slop Age Needs Temporal Context

**Source:** `Random thoughts while gazing at the misty AI Frontier`

**Selected evidence:**

> We are likely in the golden era of AI + humanity... Today, AI creates useful slop at volume, which means humans are still needed to desloppify the slop... If AI displaces people eventually or does more interesting work, this golden moment may fade or change.

**Feedback:** The output was good but could include more detail on what it means that the window may not last.

**Canonical target:**

> The current AI slop era may be a temporary golden age for human-AI work: models create useful rough output at volume, while humans still add the judgment, taste, and context that make the work satisfying; if AI later owns more of the interesting work too, this window may close.

**Expected behavior:** Preserve that the enjoyable window may fade as AI improves enough to take over more interesting work or displace work.

**Pass criteria:**

- Mentions temporariness.
- Explains why it may not last, not only that it may not last.

### W06-03: 1:1 Setup Is Reference Material

**Source:** `Run Excellent 1:1s`

**Feedback:** More like a reference for a manager setting up 1:1s than a durable opinion.

**Expected behavior:** Usually skip.

**Canonical target:**

> No proposal.

**Pass criteria:**

- No proposal, unless the generated opinion clearly generalizes into a durable management principle Ryan would likely endorse.

### W06-04: Security Product Notes Are Lower Priority

**Source:** `Agent Vault: The Open Source Credential Proxy and Vault for Agents`

**Feedback:** Security-related highlights are less likely to reflect durable personal opinions; note as possible optimization rather than a hard rule.

**Canonical target:**

> Agents should not handle long-lived credentials directly; access should be mediated by narrow proxies or vaults that attach secrets only at the boundary where they are needed.

**Expected behavior:** Fine to propose occasionally, but should not over-prioritize product/security trivia when stronger conceptual opinions are available.

**Pass criteria:**

- If proposed, frames as a general agent-safety principle, not a product feature summary.
- Avoid proposing if the week already has stronger, more Ryan-specific opinions.

## W07

### W07-01: One-Person Services Context Should Be Preserved

**Source:** `How to Build a One-Person Services-as-Software Company`

**Feedback:** The generated opinion was fine but hid that the article was about one-person services rather than a full startup-style company.

**Canonical target:**

> AI makes one-person services-as-software businesses more viable, but the durable edge is not passive automation; it is choosing a narrow niche, selling measurable outcomes, and compounding client relationships and delivery proof.

**Expected behavior:** Preserve that the context is one-person / solo services-as-software, not generic startup-building.

**Pass criteria:**

- Mentions solo, one-person, owner-operator, or equivalent.
- Does not inflate into generic venture/startup advice.

### W07-02: Networking Guide Is Borderline Career Advice

**Source:** `networking guide for a hardened technical introvert`

**Feedback:** Borderline "career advice I should follow" rather than a durable opinion.

**Expected behavior:** Usually skip or keep low priority.

**Canonical target:**

> No proposal.

**Pass criteria:**

- No proposal, unless it becomes a durable principle about weak ties / technical credibility rather than a tactical networking guide.

## W08

### W08-01: Learn In Public Should Not Editorialize Beyond Evidence

**Source:** `Learn In Public`

**Selected evidence:**

> Don’t judge your results by “claps” or retweets or stars or upvotes - just talk to yourself from 3 months ago. I keep an almost-daily dev blog written for no one else but me.

**Feedback:** The generated opinion was good but would need revision: it editorialized by saying the behavior builds more leverage and framed it as optimizing for applause. The key point is that doing builds leverage; doing it for claps/retweets is not necessary.

**Expected behavior:** Preserve the source's distinction between doing/learning and audience reward without adding unsupported "optimizing for applause" framing.

**Canonical target:**

> Learning in public is most useful when it is oriented toward your past self, not applause; the point is to make and share artifacts that compound your own learning, even if nobody rewards them immediately.

**Pass criteria:**

- Keeps focus on writing/creating for your past self or for learning.
- Does not overstate social-media motivation unless it is in evidence.

### W08-02: Reference For Later Should Usually Be Skipped

**Feedback:** One W08 proposal was more of a reference for later than a durable opinion.

**Expected behavior:** Filter saved-reference highlights unless they support a durable stance.

**Canonical target:**

> No proposal.

**Pass criteria:**

- No proposal for tactical/reference-only highlights.
- If proposed, contains a clear judgment, tradeoff, or principle.

## W10

### W10-01: Preserve `sqrt(N)` / Price's Law

**Source:** `The Mathematical Reason Most People Never "Make It"`

**Selected evidence:**

> Double down on your √n skills. Get so good at your two or three multiplier skills that you’re in the top 1% at the combination of those skills.
>
> Price’s Law states that the square root of the number of people in a domain does 50% of the work.

**Feedback:** The generated opinion would be accepted with revision, but it did not capture the `sqrt(N)` point.

**Canonical target:**

> Career leverage is not about being well-rounded; Price's Law suggests that a small square-root-sized minority produces much of the output, so the goal is to find and compound your `√n` multiplier skills into a rare combination.

**Expected behavior:** Preserve Price's Law / square-root framing or the `√n` language, because the user explicitly cared about it and it was already in selected evidence.

**Pass criteria:**

- Mentions `sqrt`, `√n`, square root, or Price's Law.
- Keeps the multiplier-skills interpretation.
- Does not reduce the source to generic "skill stacking" advice.

### W10-02: Hiring Criteria Was Fine To Raise But Rejected

**Source:** `every company has the same hiring criteria`

**Feedback:** Fine to raise, but rejected. In general, not many takes/opinions are related to hiring/security unless strongly Ryan-specific.

**Expected behavior:** Lower priority; okay to propose but not a strong accept target.

**Canonical target:**

> Early-stage hiring should overweight intelligence, agency, and character over years of experience; specialized expertise can often be rented, but ownership and judgment need to live inside the team.

**Pass criteria:**

- If proposed, frame as a hiring principle rather than copying the source's company-specific TextQL posture.

## W11

### W11-01: Good Outputs Should Remain Good

**Feedback:** Several W11 proposals were "great" or "good" in review-v5.

**Canonical targets:**

> AI-native service firms only become software-like when delivery gets easier, faster, and better with each client; the durable asset is vertical workflow knowledge, reusable agents, process data, and proof that the system compounds.

> Enterprise AI transformation should start by mapping real workflows, ROI, tribal knowledge, and data boundaries, then inserting agents into existing systems where they fit instead of forcing rip-and-replace migrations.

> Agent harnesses should be sized to the task and risk; reliable enterprise workflows often need narrower tools, explicit permissions, and deterministic execution rather than arbitrary code as the universal default.

**Expected behavior:** These are positive controls. Prompt changes should not make the agent worse at clean synthesis when the selected evidence already supports the opinion.

**Pass criteria:**

- Preserves workflow moat / compounding service-firm idea.
- Preserves operational-redesign framing for AI transformation.
- Preserves task/risk-specific harness framing.

### W11-02: Category Flexibility For Agent-Design Claims

**Feedback source:** Later W13 feedback noted that some opinions were more about building agents / agent design rather than broad `Agentic Software`. W11 harness opinions are also candidates for this behavior.

**Expected behavior:** Agent should feel free to create or use more specific sections such as `Agent Design` or `Building Agents` when several opinions cluster there.

**Canonical target:**

> Agent-design opinions should be placed in a more specific section such as `Agent Design` or `Building Agents` when the broader `Agentic Software` section becomes too coarse.

**Pass criteria:**

- Does not always anchor to existing broad sections.
- Announces category/section moves in final summary when applying edits.

## W12

### W12-01: Fingerprints / Attention Design

**Source:** `Escape from agentic loop`

**Selected evidence:**

> Some of the day I want to be deeply, deliberately in the loop, because that is where taste develops and where original work happens — the kind that has my fingerprints on it, not just my approval.

**Feedback:** Good, but might benefit from more context or clarification of "fingerprints on the result."

**Canonical target:**

> The goal of agentic work is not maximum delegation; use agents to remove routine work, but stay deliberately in the loop where taste develops and original work needs your fingerprints rather than just your approval.

**Expected behavior:** Preserve that the human should stay deliberately in the loop for taste-developing original work, not merely approve finished outputs.

**Pass criteria:**

- Mentions taste/original work/fingerprints or equivalent.
- Does not reduce the claim to generic "humans should review AI."

### W12-02: Mid-Career Satisfaction Is Usually Rejected

**Source:** `On mid-career satisfaction`

**Feedback:** Fine to raise, but rejected / borderline career advice.

**Expected behavior:** Lower priority or skip.

**Canonical target:**

> No proposal.

**Pass criteria:**

- If proposed, do not overfit to generic career-advice listicles.

## W13

### W13-01: Vertical Agent Should Preserve Shortcut Excel Example

**Source:** `Building a Good Vertical Agent`

**Selected evidence:**

> a good agent is a faithful compression of its task distribution.
>
> Almost every optimization trades compression of information against speed of discovery...

**Ground-truth note:** This is the one true `highlight_looks_sufficient_but_is_not` case. The selected packet looks usable, but the full source includes the concrete Shortcut Excel-agent example, which should be used as a memory hook and helps categorization.

**Feedback:** The opinion was good but should mention that the example comes from the Shortcut Excel agent.

**Canonical target:**

> A good vertical agent is a faithful compression of its task distribution: the Shortcut Excel-agent example shows why common capabilities belong in fast prompt context, rarer capabilities belong in discoverable tiers, and raw references should remain reachable as a bounded escape hatch.

**Expected behavior:** Keep the abstract compression/tiered-context claim and include the Shortcut Excel-agent example or at least mention Shortcut/Excel as the concrete example.

**Pass criteria:**

- Mentions Shortcut and/or Excel.
- Preserves task-distribution compression.
- Places under a specific agent-design/building-agents category if available.

### W13-02: The Untrainable Should Split Capability/Moat Claim

**Source:** `The Untrainable`

**Selected evidence:**

> anything you can put on a leaderboard, you can train against, so anything measurable is already on its way to commodity.

**Feedback:** The first point from `The Untrainable` is really its own opinion about what agents/AI will be able to do from a capability perspective.

**Expected behavior:** Do not over-merge this with unrelated `/goal` eval-set evidence unless the combined claim is clearly about private evals / ground truth as moat. Consider a separate capability/commoditization opinion.

**Canonical target:**

> Anything you can put on a public leaderboard is already on its way to commodity, because models can train against measurable benchmarks; durable capability work moves toward private, messy, user-specific edge cases.

**Pass criteria:**

- Either proposes a standalone opinion about public benchmarks/measurable tasks becoming commoditized, or combines only with evidence that supports the same central moat/eval claim.
- Does not lose the capability implication.

### W13-03: Preserve SQLite Example In Eval/Moat Opinion

**Source:** Existing opinion plus `/goal + Loss Functions` and `The Untrainable`

**Existing/current opinion context:**

> In AI-generated software, tests, specs, and verification artifacts are durable assets because they encode what must remain true, not just how the current code happens to work; SQLite's closed test suite is a clearer moat than its open source implementation.

**Feedback:** The agent should not remove the SQLite example; it was demonstrative and useful. Adding `/goal` evidence can be good, but integration needs care.

**Canonical target:**

> In AI-generated products, private eval sets, real user edge cases, specs, and verification artifacts are more durable than the artifact itself, because they encode what good means and what must remain true; SQLite's closed test suite is a clearer moat than its open source implementation.

**Expected behavior:** Preserve SQLite when revising this opinion, while integrating private evals/user edge cases if useful.

**Pass criteria:**

- Mentions SQLite.
- Connects SQLite to closed/private test suite as a moat.
- If `/goal` evidence is added, integrates it as private eval/ground-truth support rather than replacing the example.

### W13-04: `/goal` Loss Function Is A Separate Agent-Loop Opinion

**Source:** `/goal + Loss Functions: How to Distill a Product in 30 Hours with One Prompt [Full Playbook]`

**Selected evidence:**

> Every cheap path you don't fence off is a direction the optimizer will sprint down.
>
> If you can get real expected-output examples up front — what good looks like, at scale — you run the soak before you ship...

**Canonical target:**

> Autonomous agent loops need adversarially designed loss functions, not just goals; if examples, evals, constraints, and instruments do not fence off cheap shortcuts, the agent will optimize the metric by overfitting or cheating instead of getting genuinely better.

**Expected behavior:** This is a good standalone agent-loop/eval opinion. It should not necessarily be merged with `The Untrainable` or the SQLite moat opinion unless the central claim is private evals as moat.

**Pass criteria:**

- Preserves optimizer / cheap-path / loss-function framing.
- Keeps it in an agent-design or agent-loop category.
- Does not over-consolidate with unrelated AI-market benchmark claims.
