# Targets fixed by the core-concepts judge

Instances that **failed under the old judge** (`2026-07-05-plain-language`, canonical + source-evidence in the prompt) but **pass under the new concept-checklist judge** (coverage-only: canonical as stance reference, evidence removed). Pooled across the four critic-2 runs (r1/r2/r3/r4).

**11 targets, 12 instances flipped fail→pass.**

## W08-03  — flipped in 2/4 runs (r2, r4)

**Canonical opinion:** Passive productivity like reading and podcasts is helpful, but it has diminishing returns; active productivity scales better because its returns compound the more time you spend creating.

**Core concepts (what the new judge checks):**
- Passive consumption (reading, podcasts) helps but has limited/diminishing returns
- Active creating compounds and scales better

**Generated opinion(s) that now pass:**
- *(r2)* Active productivity compounds more than passive productivity: consuming information can make you well-informed, but creating, doing, and taking repeated action produce the exponential returns that passive reading, podcasts, and scrolling usually do not.
- *(r4)* Passive productivity—reading, podcasts, lurking—is useful but quickly diminishing; active production compounds, so learning should leave public or at least durable exhaust aimed at helping your past self rather than chasing likes.

## W04-04  — flipped in 1/4 runs (r3)

**Canonical opinion:** Career growth is not something to wait for: managers can help, but ambitious people need to proactively tell their manager what they want, ask what must be true to reach the next level, and seek scope instead of assuming good work will be noticed.

**Core concepts (what the new judge checks):**
- Career growth requires being proactive, not waiting for good work to be noticed
- Tell your manager the goal explicitly
- Ask what must be true to reach the next level

**Generated opinion(s) that now pass:**
- *(r3)* Your manager is a powerful career resource, not the owner of your career; if you want growth, make the goal explicit and ask what must become true on the team instead of waiting to be noticed.

## W05-04  — flipped in 1/4 runs (r4)

**Canonical opinion:** People do not need work specifically; they need four things work happens to provide — agency, contribution, mastery, and connection — so if AI displaces work, whatever comes after has to supply those four functions, not just income.

**Core concepts (what the new judge checks):**
- People need what work provides, not work itself
- The four by name: agency, contribution, mastery, connection
- Whatever replaces work must supply those four

**Generated opinion(s) that now pass:**
- *(r4)* People do not need work itself as much as the agency, contribution, mastery, and connection that work often provides; if AI weakens work as the default source of income and identity, new institutions should be judged by whether they recreate those four goods rather than by whether they preserve jobs for their own sake.

## W06-01  — flipped in 1/4 runs (r2)

**Canonical opinion:** In agentic product work, Figma is in an awkward position: when the product ultimately lives in code, the design source of truth should move closer to executable code rather than a manual, pre-agentic replica of the system.

**Core concepts (what the new judge checks):**
- Figma specifically is in an awkward position
- The product ultimately lives in code
- The design source of truth should move closer to code
- A manually maintained replica of the product is the wrong source of truth

**Generated opinion(s) that now pass:**
- *(r2)* Design tooling should move toward “truth to materials”: when agents are fluent in code and implementation is the real medium, keeping Figma as a manual, proprietary source of truth becomes brittle; the durable split is code-first design for production and freeform tools for exploration.

## W08-01  — flipped in 1/4 runs (r3)

**Canonical opinion:** In AI-assisted creative work, taste is not just knowing what you want but knowing what to reject: the default output is almost always generic, so have an opinion about the defaults — starting with the hook — and be willing to override them.

**Core concepts (what the new judge checks):**
- Taste is knowing what to reject, not just what you want
- Default AI output is almost always generic
- Have opinions about the defaults and override them

**Generated opinion(s) that now pass:**
- *(r3)* Taste matters more when implementation gets cheaper because AI defaults converge on the most probable patterns; real taste is the trained ability to know what good looks like, reject generic defaults, and spend attention after the AI finishes turning acceptable output into something specific and worth caring about.

## W10-02  — flipped in 1/4 runs (r1)

**Canonical opinion:** Career leverage is not about being well-rounded; Price's Law suggests that a small square-root-sized minority produces much of the output, so the goal is to find and compound your √n multiplier skills into a rare combination.

**Core concepts (what the new judge checks):**
- Price's Law / √n: a small square-root-sized minority produces much of the output
- Find your multiplier skills and compound them into a rare combination

**Generated opinion(s) that now pass:**
- *(r1)* Price’s Law is a useful career heuristic: in power-law domains, the square root of contributors can produce half the output — 10 of 100 employees, 100 of 10,000 scientists, or 5 of 25 teammates — so strategy should focus on finding and compounding the few √n skills or outputs that drive most results; a top-10% writer plus top-10% strategist can become top-1% at strategic writing.

## W10-03  — flipped in 1/4 runs (r2)

**Canonical opinion:** AI coding should be used as a learning loop, not just an issue-closing machine; if the model removes all friction without forcing hypotheses, explanations, and reflection, cognitive debt accumulates.

**Core concepts (what the new judge checks):**
- Use AI coding to learn, not just to close tasks
- Removing all friction without hypotheses, explanations, and reflection destroys the learning

**Generated opinion(s) that now pass:**
- *(r2)* Making code cheap to generate does not make system comprehension or engineering learning cheap to skip; the default AI coding loop optimizes for closing tasks, so engineers should preserve some learning friction by forming hypotheses, asking for explanations before code, and checking whether sessions produced understanding rather than only closed issues.

## W11-01  — flipped in 1/4 runs (r4)

**Canonical opinion:** AI-native service firms only become software-like when delivery gets easier, faster, and better with each client; the durable asset is vertical workflow knowledge, reusable agents, process data, and proof that the system compounds.

**Core concepts (what the new judge checks):**
- Service firms become software-like only when each client gets easier, faster, and better (compounding)
- What accumulates: vertical workflow knowledge, reusable agents, process data

**Generated opinion(s) that now pass:**
- *(r4)* AI agencies deserve software-like multiples only when services are the deployment layer for owned vertical workflows: AI lowers the cost of building automation, not the cost of understanding the workflow, so each client should leave behind reusable playbooks, agents, process data, specialist talent, and faster, cleaner delivery. If client five is just as hard as client one, the firm is still selling labor with better tools.

## W12-03  — flipped in 1/4 runs (r2)

**Canonical opinion:** Use agents to remove routine work that does not benefit from synchronous involvement, but stay deliberately in the loop where taste develops and original work needs you shaping it rather than just approving it.

**Core concepts (what the new judge checks):**
- Hand agents the routine work that doesn't need you synchronously
- Stay deliberately in the loop where taste develops and original work happens
- Shaping the work, not just approving it

**Generated opinion(s) that now pass:**
- *(r2)* Move routine agent work from human-in-the-loop to human-on-the-loop only when there are real review surfaces and cadences; stay deliberately in the loop for creative, taste-making work because that is where original fingerprints and taste develop, not just approval.

## W13-02  — flipped in 1/4 runs (r3)

**Canonical opinion:** Agentic optimization is only as good as its loss function: if the target, constraints, instruments, and examples leave cheap paths open, the agent will exploit them instead of getting genuinely better.

**Core concepts (what the new judge checks):**
- Agentic optimization is only as good as its loss function
- Cheap paths left open get exploited instead of real improvement
- The ingredients: target, constraints, instruments, examples

**Generated opinion(s) that now pass:**
- *(r3)* Long-running agent loops should be treated as optimizers, not interns: without a loss function made of a target, constraints, instruments, and forced entropy, they will sprint down the cheapest path, overfit visible evals, or grind past time and budget; real expected-output examples let you run the production edge-case soak before shipping.

## W13-04  — flipped in 1/4 runs (r3)

**Canonical opinion:** Anything you can put on a leaderboard you can train against, so anything measurable is already on its way to commodity; durable value moves toward complex, private work that cannot be easily measured or copied.

**Core concepts (what the new judge checks):**
- Anything you can put on a leaderboard can be trained against
- So measurable work is already on its way to commodity
- Durable value moves to complex, private work that's hard to measure or copy

**Generated opinion(s) that now pass:**
- *(r3)* AI commoditizes work that can be publicly measured or leaderboarded; durable value shifts to private and expensive-to-establish correctness — company data, real user edge cases, permissions, accountability, workflow trust, and the authority to define what good means from inside the field.
