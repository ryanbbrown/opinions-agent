# Opinion Eval Targets

## Judge rules (cross-target)

General rulings for judge v2; they apply to every target, so they live here instead of in per-target Not core lists.

- Dilution fails: adding a co-equal claim that isn't in the canonical is a fail, even when every core concept is covered (ruling on W04-05's rehearsal half).
- Merging sources fails: folding in content from a different source — including not-converted ones — is straying, not synthesis (W08-03's Learn-in-Public half).
- Added same-source specificity is fine: extra concrete detail from the target's own source must not fail a draft that carries the core concepts (W12-03's HITL/HOTL vocabulary).
- Open: narrowing tolerance — concrete restatements in place of the general principle (W13-04's company-data/edge-cases/permissions phrasing) were accepted when the concepts were carried; how much narrowing is OK isn't pinned yet.

## W04

### W04 opinion 1

As AI commoditizes scaffolding, the bottleneck moves to high-quality intent: having ideas worth pursuing, articulating what good looks like, and turning that intent into criteria that agents and organizations can optimize toward.

*Simplified candidate: As AI commoditizes scaffolding, the bottleneck moves to high-quality intent: having ideas worth pursuing and being able to articulate what good looks like.*

**Core concepts**
- AI makes scaffolding/implementation cheap
- The bottleneck/scarce thing becomes high-quality intent
- The quality of the idea itself matters
- Articulating what good looks like

**Not core**
- "Turning intent into criteria that agents and organizations can optimize toward" — in the canonical, but not required

**Sources**
- The Most Important Ideas in AI Right Now: "The new scarce skill isn't coding or prompting—it's being able to say what you actually want. And it has to be high-quality intent. The quality of the idea is always the most important thing. But the second most important is the ability to articulate it, define it as your actual goal, and orient the entire company around it."
- Nobody is Talking About Generalized Hill-Climbing (at Runtime): "The author proposes a new way to improve AI by clearly defining and testing an \"Ideal State\" for any task, making progress measurable and verifiable."

### W04 opinion 2

Expertise is dispersing from experts' heads into skills, SOPs, context files, and open-source projects, and once captured it never comes back out; advantages based only on undocumented expert memory will erode as AI reuses what gets captured.

*Simplified candidate: Expertise is dispersing from experts' heads into captured forms like skills and docs, and once captured it never comes back out; advantages based only on undocumented expert memory erode as AI reuses what gets captured.*

**Core concepts**
- Expertise is moving out of experts' heads into captured forms (skills, SOPs, context files, open source)
- Capture is one-way: once out, it never comes back
- Advantages based only on undocumented expert memory erode

**Not core**
- The exact four capture forms as an enumeration — a representative set is fine

**Sources**
- The Most Important Ideas in AI Right Now: "There's an articulation gap between what experts know and what's written down. Most expertise lives in people's heads. Cliff, the 62-year-old who knows how everything works but never documented any of it. When Cliff retires, that knowledge dies with him. What's happening now is that expertise is dispersing from brains into skills, SOPs, context files, open source projects. And once it's captured it never comes back out."

### W04 opinion 3

Generalist base models are likely to beat domain-specific base models because intelligence from different fields builds on itself; domain-specific models mainly make sense if we hit physical limits in model size.

*Simplified candidate: Generalist models are likely to beat domain-specific ones because knowledge from different fields builds on each other; domain-specific models mainly make sense if we hit physical limits in model size.*

**Core concepts**
- Generalist models beat domain-specific models
- Because learning from many areas makes a model smarter overall; knowledge from different fields builds on each other (note: canonical says "builds on itself", source says "builds on each other" — rewrite candidate)
- Domain-specific mainly makes sense if model size hits physical limits

**Not core**
- "Base model" phrasing — general/foundation models in any words

**Sources**
- Why domain specific LLMs won't exist: an intuition: "Domain-specific large language models (LLMs) do not outperform general LLMs because intelligence from different fields builds on each other. General models learn from many areas, making them smarter overall."

### W04 opinion 4

Career growth is not something to wait for: managers can help, but ambitious people need to proactively tell their manager what they want, ask what must be true to reach the next level, and seek scope instead of assuming good work will be noticed.

*Simplified candidate: Career growth is not something to wait for: proactively tell your manager what you want and ask what must be true to reach the next level, instead of assuming good work will be noticed.*

**Core concepts**
- Career growth requires being proactive, not waiting for good work to be noticed
- Tell your manager the goal explicitly
- Ask what must be true to reach the next level

**Not core**
- "Seek scope" as a distinct required action

**Sources**
- Nobody Is Coming to Save Your Career: "If you've never told your manager you want to grow your career, this is the week you do it. It doesn't need to be a big formal conversation. In your next 1:1, try something like \"I just wanted to let you know that getting to the next level is a goal of mine. I'd like to talk about what needs to be true for that to happen on this team.\""

### W04 opinion 5

In hiring, an impressive accomplishment only creates signal if the candidate can deliver it well; a truthful, practiced account of tradeoffs and close calls reveals more than a polished success story that hides how they actually think.

**Core concepts**
- An impressive accomplishment only counts if delivered well
- Truthful accounts of the tradeoffs and close calls reveal how you actually think
- That reveals more than a polished success story

**Not core**
- The literal "polished vs truthful" vocabulary

**Sources**
- What I Learned From Nearly 1,000 Interviews at Amazon: "You can have the most impressive accomplishment of your career ready for your interview and completely waste it with bad delivery."
- What I Learned From Nearly 1,000 Interviews at Amazon: "Write down your answers. Then record yourself delivering them. Watch the recording and take notes. Where did you ramble? Where did you fill space with filler words? Did you look nervous? Then do it again. And again."
- What I Learned From Nearly 1,000 Interviews at Amazon: "You'd want the real version of what happened, including the parts that were hard and the calls that were close. You'd want to walk away feeling like you understood what it would be like to work with them on a tough problem. Give your interviewer that same thing. Be honest and let them see how you think. That's worth more than any polished answer."

### W04 not converted

- We Have Learned Nothing: "Startup advice often leads everyone to build the same kind of company, causing most to fail. True success requires doing things differently, not following fixed rules."
- LLM Knowledge Bases: "I find myself developing additional tools to process the data, e.g. I vibe coded a small and naive search engine over the wiki, which I both use directly (in a web ui), but more often I want to hand it off to an LLM via CLI as a tool for larger queries."

## W05

### W05 opinion 1

Specs can shift implementation out of code, but they do not remove the need for precise design; a specification detailed enough to reliably generate working software starts to become code or code-like formal language.

*Simplified candidate: A specification detailed enough to reliably generate working software starts to become code; precise design doesn't go away.*

**Core concepts**
- Precise design is still needed
- A spec detailed enough to reliably generate working software becomes code-like

**Not core**
- "Formal language" phrasing
- "Specs can shift implementation out of code" — in the canonical, but it's the advocates' claim the article rebuts ("agentic coding advocates claim... their claims are misleading"), restated as a concession; not required (rewrite candidate)

**Sources**
- A sufficiently detailed spec is code: "If you try to make a specification document precise enough to reliably generate a working implementation you must necessarily contort the document into code or something strongly resembling code."

### W05 opinion 2

Agent systems should keep the harness thin, put reusable judgment and process in skills, and push repeatable execution into deterministic tools so model improvements compound without making reliability depend on the model.

*Simplified candidate: Agent systems should keep the harness thin, put reusable judgment and process in skills, and push repeatable execution into deterministic tools, so model improvements compound to lift the whole system.*

**Core concepts**
- Keep the harness thin
- Reusable judgment/process goes in skills
- Repeatable execution goes in deterministic tools
- The payoff/why: model improvements compound to lift the whole system

**Not core**
- The reliability-decoupling half of the payoff (reliability doesn't depend on the model) — in the canonical, but the compounding why alone satisfies the requirement

**Sources**
- Thin Harness, Fat Skills: "The harness is the program that runs the LLM. It does four things: runs the model in a loop, reads and writes your files, manages context, and enforces safety. That's it. That's the \"thin.\""
- Thin Harness, Fat Skills: "The principle is directional. Push intelligence up into skills. Push execution down into deterministic tooling. Keep the harness thin."
- Thin Harness, Fat Skills: "If I ask you to do something and it's the kind of thing that will need to happen again, you must: do it manually the first time on 3 to 10 items. Show me the output. If I approve, codify it into a skill file."

### W05 opinion 3

AI does not need to beat an idealized version of knowledge work; in many companies it only has to beat messy, inconsistent operations where simply following instructions reliably is already above the current bar.

**Core concepts**
- AI doesn't have to beat idealized knowledge work
- It only has to beat messy/inconsistent real operations
- Reliably following instructions already clears the bar in many companies

(Eval note: this target's failures were missing proposals, not judge verdicts.)

**Sources**
- Exactly Why and How AI Will Replace Knowledge Work: "When you hear the argument that AI cannot compete with humans—inside of a company, this is what they have to compete with. This bar is not low. It is on the floor. It burned a hole through the floor. It is descending to the core of the earth. AI can follow instructions. The ability to follow instructions over and over, doing the same thing in a very uncreative way, is better than what is done in most companies most of the time."

### W05 opinion 4

People do not need work specifically; they need four things work happens to provide — agency, contribution, mastery, and connection — so if AI displaces work, whatever comes after has to supply those four functions, not just income.

*Simplified candidate: People do not need work specifically; they need four things it happens to provide — agency, contribution, mastery, and connection — so whatever replaces work has to supply those four.*

**Core concepts**
- People need what work provides, not work itself
- The four by name: agency, contribution, mastery, connection
- Whatever replaces work must supply those four

**Not core**
- The "not just income" foil — in the canonical, but any contrast (income, job-preservation) is fine

**Sources**
- The Displacement of Cognitive Labor and What Comes After: "What people actually seem to need is not work specifically but four things that work happens to provide: agency (the sense that you're making choices that matter), contribution (the sense that you're valued by others), mastery (the sense that you're getting better at something), and connection (belonging to something larger than yourself)."

### W05 not converted

- Your harness, your memory: "Even if the whole harness isn't behind the API, model providers are incentivized to move more and more behind APIs - and are already doing so."
- Inside GitHub's Fake Star Economy: "Jono Bacon at StateShift recommends five metrics that correlate with real adoption: package downloads, issue quality, contributor retention, community discussion depth, and usage telemetry."

## W06

### W06 opinion 1

In agentic product work, Figma is in an awkward position: when the product ultimately lives in code, the design source of truth should move closer to executable code rather than a manual, pre-agentic replica of the system.

*Simplified candidate: Figma is in an awkward position: when the product ultimately lives in code, the design source of truth should move closer to executable code rather than a manually maintained, pre-agentic replica.*

**Core concepts**
- Figma is in an awkward position (naming Figma is required)
- The product ultimately lives in code
- The design source of truth should move closer to code
- A manually maintained replica of the product is the wrong source of truth

**Not core**
- The literal phrase "agentic product work"

**Sources**
- Thoughts and Feelings around Claude Design: "as the source of truth shifts back to code, Figma is left in an odd spot: holding a largely manual, pre-agentic system that nobody in their right mind would design from scratch today."

### W06 opinion 2

In agent products, durable advantage should come from company-specific domain reasoning and business logic; the common stack underneath should increasingly be platform primitives rather than bespoke plumbing.

**Core concepts**
- Durable advantage comes from company-specific domain reasoning and business logic
- The layer underneath should be platform primitives, not bespoke plumbing

**Sources**
- The Agent Stack Bet: "The real value lives in domain reasoning and business logic - the judgment calls that are specific to your company, your customers, your regulatory environment. Everything underneath should be the platform you build on, not the plumbing you build."

### W06 opinion 3

Engineering interviews in an AI-native world should test how candidates scope, build, review, and reason with AI tools on representative product work instead of testing code mechanics without assistance.

**Core concepts**
- Interviews should test working with AI tools
- On representative product work (scope, build, review, reason)
- Instead of traditional unassisted coding tests

**Sources**
- The AI-native interview: "Sierra redesigned their engineering interviews to focus on real product building using AI tools instead of traditional coding tests. Candidates plan, build, and review a product during onsite sessions to show their skills and thinking."

### W06 opinion 4

The current AI slop era may be a golden age for human-AI work: models create useful slop at volume, humans are still needed to desloppify it, and that combination gives real leverage while keeping the work fun; if AI eventually displaces people or takes over the more interesting work, this moment may fade.

*Simplified candidate: Right now is likely a golden age of human-AI work: AI produces useful output at volume, humans are still needed to clean it up, and that combination gives real leverage — a moment that may fade if AI eventually displaces people or takes over the interesting work.*

**Core concepts**
- Right now is likely a golden age of human+AI work
- AI produces useful slop at volume
- Humans are still needed to clean it up
- The combination gives real leverage
- It may fade if AI displaces people or takes the interesting work

**Not core**
- The "slop/desloppify" vocabulary itself, if the mechanism is carried in other words
- "Keeps the work fun" — color on the leverage claim, not required

**Sources**
- Random thoughts while gazing at the misty AI Frontier: "We are likely in the golden era of AI + humanity. Before the last few years, AI was inaccessible, not very generalizable, and could only do specific tasks. In the future, AI may become superhuman at most tasks and take over a lot of work some people find fun. Today, AI creates useful slop at volume, which means humans are still needed to desloppify the slop, but the slop provides real leverage on time and jobs, which means it is fun to be working right now. If AI displaces people eventually or does more interesting work, this golden moment may fade or change."

### W06 not converted

- Output isn't design: "The hard part of design is rarely generating the form. It is understanding the problem well enough to know what and how something should exist at all."
- Agent Vault: The Open Source Credential Proxy and Vault for Agents: "Agent Vault is an open source tool that keeps secrets safe by acting as a proxy between AI agents and services. It stops agents from seeing or handling sensitive credentials directly."
- Run Excellent 1:1s: "Great 1:1 meetings happen when the person leads the conversation and the manager listens and coaches with questions."

## W07

### W07 not converted

- How to Build a One-Person Services-as-Software Company: "One person can now run a profitable AI services business that used to need a whole team, thanks to AI cutting costs and boosting efficiency. Success comes from picking a niche, offering clear results, and doing steady outreach with smart messaging."
- networking guide for a hardened technical introvert: "Networking helps introverted technical people get more opportunities. Build many simple, genuine weak connections you can give value to."

## W08

### W08 opinion 1

In AI-assisted creative work, taste is not just knowing what you want but knowing what to reject: the default output is almost always generic, so have an opinion about the defaults — starting with the hook — and be willing to override them.

*Simplified candidate: In AI-assisted creative work, taste is not just knowing what you want but knowing what to reject: the default output is almost always generic, so have an opinion about the defaults and be willing to override them.*

**Core concepts**
- Taste is knowing what to reject, not just what you want
- Default AI output is almost always generic
- Have opinions about the defaults and override them

**Not core**
- "Starting with the hook" — in the canonical, but an illustrative anchor, not required

**Sources**
- Everyone using AI has about 12 months to develop these 3 moats: "you get a content draft from Claude and rewrite the first two sentences because the AI opened with something generic, even though the rest is solid. the hook is everything and the default hook is almost always wrong."
- Everyone using AI has about 12 months to develop these 3 moats: "taste isnt just knowing what you want. its knowing what to reject. its having an opinion about the defaults and being willing to override them."

### W08 opinion 2

When AI can cheaply generate repos, tests, and docs, real use becomes a stronger trust signal than polished artifacts; for serious software, prefer products with operational proof from yourself or comparable customers.

**Core concepts**
- AI makes polished artifacts (repos, tests, docs) cheap to generate
- So polished artifacts stop being proof
- Real use is the stronger trust signal
- For serious software: want proof of real use by yourself or comparable customers

**Not core**
- The exact artifact list membership

**Sources**
- Vibe coding and agentic engineering are getting closer than I'd like: "So I realized what I value more than the quality of the tests and documentation is that I want somebody to have used the thing. If you've got a vibe coded thing which you have used every day for the past two weeks, that's much more valuable to me than something that you've just spat out and hardly even exercised."
- Vibe coding and agentic engineering are getting closer than I'd like: "I don't want a CRM unless at least two other giant enterprises have successfully used that CRM for six months."

### W08 opinion 3

Passive productivity like reading and podcasts is helpful, but it has diminishing returns; active productivity scales better because its returns compound the more time you spend creating.

*Simplified candidate: Passive productivity like reading and podcasts is helpful but has diminishing returns; active productivity scales better because its returns compound.*

**Core concepts**
- Passive consumption (reading, podcasts) helps but has limited/diminishing returns
- Active creating compounds and scales better

**Not core**
- The qualifier "the more time you spend creating" as a separate requirement

**Sources**
- Being Someone who Does Things: "I can personally feel that having spent a decade or so doing lots of passively productive things has been helpful and made me pretty well-informed, but it hasn't been as powerful as if I'd spent more of that time doing actively productive things."

### W08 opinion 4

Agent prompts and harnesses should simplify as models improve: give clear structure and canonical examples, but avoid sprawling if-else prompts that try to pre-solve every edge case.

*Simplified candidate: Agent prompts and harnesses should simplify as models improve: give clear structure and canonical examples, and don't hard-code every edge case with if-else logic — let the model handle them.*

**Core concepts**
- Prompts and harnesses should get simpler as models improve
- Give clear structure and canonical examples
- Don't hard-code every edge case with if-else logic; let the model handle them

**Sources**
- Your Agent's Compactor Matters More Than Its Context Window: "Anthropic found two failure modes: over-engineered system prompts with 2K+ words of if-else logic that break on edge cases, and vague prompts like \"be helpful\" that give the model nothing to work with. Their fix: organize prompts into clear sections (XML tags or markdown headers), use canonical examples to show expected behavior, and let the model handle edge cases instead of hard-coding them."
- Your Agent's Compactor Matters More Than Its Context Window: "One pattern worth noting: the teams shipping the best agents keep simplifying. Manus has been rewritten five times. Each rewrite removed things. If your agent harness is getting more complex while models get better, something is wrong."

### W08 not converted

- Everything I know about fundraising: "Founders should focus on building their product and talking to customers, not meeting VCs all the time."
- Learn In Public: "Don't judge your results by \"claps\" or retweets or stars or upvotes - just talk to yourself from 3 months ago. I keep an almost-daily dev blog written for no one else but me."

## W10

### W10 opinion 1

AI service replacement is most likely where customers already outsource repeatable execution or playbook-based work and judge the vendor by outcomes rather than visible effort.

**Core concepts**
- AI replaces services most easily where the work is already outsourced
- Repeatable, playbook-based work
- Where customers judge by outcomes, not effort

**Sources**
- Service as a Software: "Layer 1: Production work. The repeatable execution. Filing the tax return. Drafting the contract. Generating the report. Posting the invoice. Sending the follow-up"
- Service as a Software: "Layer 2: Pattern application. Translating a known problem into a working answer using a playbook the industry has refined for decades."
- Service as a Software: "The work is already outsourced. If a customer is paying a third party to do it, they have already accepted that someone else owns the execution"
- Service as a Software: "The customer measures success by the outcome, not the effort"

### W10 opinion 2

Career leverage is not about being well-rounded; Price's Law suggests that a small square-root-sized minority produces much of the output, so the goal is to find and compound your `√n` multiplier skills into a rare combination.

*Simplified candidate: Price's Law suggests that a small, square-root-sized minority produces much of the output, so the goal is to find and compound your `√n` multiplier skills into a rare combination.*

**Core concepts**
- Price's Law / √n: a small square-root-sized minority produces much of the output
- Find your multiplier skills and compound them into a rare combination

**Not core**
- The explicit "not about being well-rounded" negation — in the canonical, not required (candidate to trim from the canonical in the final canonical-edit pass)

**Sources**
- The Mathematical Reason Most People Never "Make It": "Double down on your √n skills. Get so good at your two or three multiplier skills that you're in the top 1% at the combination of those skills."
- The Mathematical Reason Most People Never "Make It": "Price's Law states that the square root of the number of people in a domain does 50% of the work."

### W10 opinion 3

AI coding should be used as a learning loop, not just an issue-closing machine; if the model removes all friction without forcing hypotheses, explanations, and reflection, cognitive debt accumulates.

*Simplified candidate: Use AI coding to learn, not just to close tasks; if the model removes all friction without forcing hypotheses, explanations, and reflection, cognitive debt accumulates.*

**Core concepts**
- Use AI coding to learn, not just to close tasks
- Removing all friction without hypotheses, explanations, and reflection destroys the learning
- The phenomenon is named "cognitive debt" — this exact term is required, not a paraphrase

**Not core**
- The "learning loop" / "issue-closing machine" metaphors — in the canonical, but the golden's own phrasing; the learn-vs-just-close-tasks concept is what's required

**Sources**
- Don't Outsource the Learning: "We all want fewer keystrokes, so the tools have sanded the friction away. The trouble is that friction was where the learning lived."
- Don't Outsource the Learning: "Form a hypothesis before you ask."
- Don't Outsource the Learning: "Ask for the explanation before the code"
- Don't Outsource the Learning: "I've started ending coding sessions with a simple question: did I learn anything today, or did I just close issues?"

### W10 not converted

- Today's harness is Tomorrow's Prompt: "Harnesses have a short shelf life, and it's getting shorter. What took an engineering team a quarter last year is a flag on Gemini call today."
- every company has the same hiring criteria: "it seems like the only thing that matters is being a smart generalist are you competent? prove itare you high agency? prove itdo you have integrity? prove it"

## W11

### W11 opinion 1

AI-native service firms only become software-like when delivery gets easier, faster, and better with each client; the durable asset is vertical workflow knowledge, reusable agents, process data, and proof that the system compounds.

*Simplified candidate: AI-native service firms only become software-like when delivery gets easier, faster, and better with each client; what accumulates is vertical workflow knowledge, reusable agents, and process data.*

**Core concepts**
- Service firms become software-like only when each client gets easier, faster, and better (compounding)
- What accumulates: vertical workflow knowledge, reusable agents, process data

**Not core**
- The literal words "durable asset" and "proof"
- Exact enumeration membership — playbooks / specialist-talent variants are fine

**Sources**
- 30x AI agencies: Why service firms may earn software level multiples: "AI lowers the cost of building the automation. It doesn't lower the cost of understanding the workflow. The workflow is the moat."
- 30x AI agencies: Why service firms may earn software level multiples: "If client five is just as hard as client one, the company is still selling labor. If client five is easier, faster, and better because the firm learned from the first four, something more valuable is forming."
- 30x AI agencies: Why service firms may earn software level multiples: "Buyers will want vertical workflow knowledge, implementation playbooks, reusable agents, specialist talent, process data, and proof that delivery gets more efficient over time."

### W11 opinion 2

Enterprise AI transformation should start by mapping end-to-end workflows, ROI, data layers, and tribal knowledge around existing systems; rip-and-replace migrations often slow adoption more than they help.

*Simplified candidate: Enterprise AI transformation should start by mapping end-to-end workflows and per-workflow ROI; rip-and-replace migrations often slow adoption more than they help.*

**Core concepts**
- Start by mapping end-to-end workflows and per-workflow ROI
- Don't rip-and-replace existing systems; it slows adoption

**Not core**
- Understanding data layers and tribal knowledge around existing systems — part of mapping the workflows, not a separate requirement

**Sources**
- How to Transform a Company With AI: "You should map every workflow, figure out what the ROI of an agent would be in each particular workflow and how to approach it from an engineering perspective, then choose where to deploy the agents where they'd be a good fit."
- How to Transform a Company With AI: "Don't force massive migrations. Most companies have already spent years moving onto systems like Salesforce and NetSuite."
- How to Transform a Company With AI: "In most workflows, the data that powers the transformation falls into four categories: the system of record, the business rules, the raw intake data, and the feedback or memory the agent accumulates over time."

### W11 opinion 3

Reliable agent harnesses should not treat bash or arbitrary code execution as universally necessary; many enterprise tasks are better served by task-specific, constrained tools than by a model with general computer access.

**Core concepts**
- Bash / arbitrary code execution isn't universally necessary in agent harnesses
- Constrained, task-specific tools serve many enterprise tasks better

**Sources**
- The Anatomy of an Agent Harness: "Harnesses ship with a bash tool so models can solve problems autonomously by writing & executing code."
- The Anatomy of an Agent Harness: "This frames a harness as being something design to solve lots of kinds of problems and bash + code helps. I think lots of problems don't need and shouldn't have bash + code."
- What is an Agent Harness: "when you want something reliable in enterprise you don't necessarily want it executing arbitrary code"

### W11 opinion 4

Career choices should be judged by the compounding assets they build - skills, reputation, network, options, and operational scars - not just immediate pay, title, or brand.

*Simplified candidate: Career choices should be judged by the compounding assets they build, not by immediate pay, title, or brand.*

**Core concepts**
- Judge career choices by the compounding assets they build
- Not by immediate pay, title, or brand

**Not core**
- The specific assets (skills, reputation, network, options, operational scars) — representative set, none individually required

**Sources**
- The Career Bets That Compound (And the Ones That Don't): "The networks that matter are built through work - through projects you delivered together, problems you solved together, hard situations you got through together."
- The Career Bets That Compound (And the Ones That Don't): "stop optimizing for the next move. Start optimizing for the move after that."
- The Career Bets That Compound (And the Ones That Don't): "Joining a great company early gives you the brand, the network, the wealth, the operational scars, and the credibility to start your own thing later."

### W11 opinion 5

High agency needs recovery and self-context, not endless escalation; because there is no final level, ambitious people should deliberately look back, accept their current state, and take breaks.

*Simplified candidate: High agency needs recovery and remembering your own context, not just always improving; because there is no final level, pause to reflect, accept where you are, and take breaks.*

**Core concepts**
- High agency needs recovery and remembering your own context, not just always improving
- There is no final level
- Respond by pausing to reflect, accepting where you are, and taking breaks

**Not core**
- The exact look-back / accept / break triad wording
- The word "self-context" — the canonical's own compression of the source's "remember the context that surrounds you"

**Sources**
- How to avoid feeling low as a high-agency person: "There is no final level of growth to be achieved. You will be a work in progress until you die. Learn to take a break."
- How to avoid feeling low as a high-agency person: "there is no endgame to a high-agency growth mindset. The more you get ahead in life, the more levels you unlock."
- How to avoid feeling low as a high-agency person: "Your situation, circumstances, and life are unique to you. Remember the context that surrounds you."

### W11 not converted

- Why founder conviction matters more than ever: "Return to customers before returning to investors. When conviction wavers, the fastest way to restore it is a direct conversation with someone whose problem you are solving."

## W12

### W12 opinion 1

Making code cheap to generate does not make ownership or system comprehension cheap to skip; people should understand AI-generated artifacts well enough to defend them under questioning.

*Simplified candidate: You still have to take ownership of AI-generated work: understand it well enough to defend it under questioning, even when AI produced it.*

**Core concepts**
- You still have to take ownership of AI-generated work — you're accountable for the artifact even when AI produced it
- Understand it well enough to defend it under questioning

**Not core**
- The "cheap to generate ↔ cheap to skip" parallel framing — the golden's own rhetoric, not required

**Sources**
- How AI Productivity Fails: "Hold people accountable for the artifact even when AI generated it; build pushback culture with harsh, specific feedback when output crosses into slop"
- How AI Productivity Fails: "you have to understand what you ship well enough to defend it under questioning"

### W12 opinion 2

Agentic throughput is capped by human review bandwidth, not by how many workers the UI can spawn; the right amount of parallelism is the work you can actually evaluate without surrendering standards.

**Core concepts**
- Throughput is capped by human review bandwidth, not by how many agents you can spawn
- Right parallelism = what you can actually review without dropping standards

**Sources**
- The Orchestration Tax: "optimizing the non bottleneck part doesn't increase throughput. You just grow the pile of unfinished work sitting in front of the bottleneck."
- The Orchestration Tax: "The right number of parallel agents is how many you can actually code review properly. For most of us this is a low single digit."

### W12 opinion 3

Use agents to remove routine work that does not benefit from synchronous involvement, but stay deliberately in the loop where taste develops and original work needs you shaping it rather than just approving it.

**Core concepts**
- Hand agents the routine work that doesn't need you synchronously
- Stay deliberately in the loop where taste develops and original work happens
- Shaping the work, not just approving it

**Sources**
- Escape from agentic loop: "Some of the day I want to be deeply, deliberately in the loop, because that is where taste develops and where original work happens - the kind that has my fingerprints on it, not just my approval."

### W12 not converted

- The Death of the Three-Act Playbook: "As the cost of writing software drops to zero, I find myself valuing ambition above all else. Unreasonable, unrelenting ambition. I think the three-act play is dead."
- On mid-career satisfaction: "Competence in your role - Flow when doing your work - Culture & people fit - Work-life harmony - How you feel most Sunday evenings"

## W13

### W13 opinion 1

A good vertical agent is a faithful compression of its task distribution: common capabilities belong in fast, always-loaded prompt context, rarer capabilities belong in discoverable tiers, and complete underlying references should remain searchable for the rare cases the curated layers do not cover.

**Core concepts**
- A good vertical agent is a faithful compression of its task distribution
- Common capabilities: always loaded, instant
- Rarer capabilities: discoverable on demand
- Complete references stay searchable for the rare uncovered cases

**Sources**
- Building a Good Vertical Agent: "I've spent almost a year now building the Shortcut agent, which is widely considered the most accurate spreadsheet agent around"
- Building a Good Vertical Agent: "a good agent is a faithful compression of its task distribution."
- Building a Good Vertical Agent: "Almost every optimization trades compression of information against speed of discovery. Put something in L1 and it's instant, but it costs prompt tokens on every single task whether it's used or not. Push it to L3 and it costs nothing until needed - but then it costs several tool calls to find."
- Building a Good Vertical Agent: "The compression in those system prompts and curated specs is really an encoding of the distribution of your users and the tasks they do"

### W13 opinion 2

Agentic optimization is only as good as its loss function: if the target, constraints, instruments, and examples leave cheap paths open, the agent will exploit them instead of getting genuinely better.

*Simplified candidate: Agentic optimization is only as good as its loss function: if the target and constraints leave cheap paths open, the agent will exploit them instead of getting genuinely better.*

**Core concepts**
- Agentic optimization is only as good as its loss function (an implicit version is enough — e.g. "an agent only gets as good as the objective you give it")
- Cheap paths left open get exploited instead of real improvement
- The loss function needs at minimum a clear target and constraints

**Not core**
- Instruments and examples — representative, not each required (the article's own list is target / constraints / instruments / forced entropy; the golden swapped in "examples")

**Sources**
- /goal + Loss Functions: How to Distill a Product in 30 Hours with One Prompt [Full Playbook]: "Every cheap path you don't fence off is a direction the optimizer will sprint down."
- /goal + Loss Functions: How to Distill a Product in 30 Hours with One Prompt [Full Playbook]: "If you can get real expected-output examples up front - what good looks like, at scale - you run the soak before you ship"

### W13 opinion 3

Building new software is learning under uncertainty; the right move is to expose the unknown parts to valuable feedback quickly, whether from CI, teammates, users, customers, or your own use.

*Simplified candidate: Building new software is learning under uncertainty; the right move is to expose the unknown parts to valuable feedback quickly.*

**Core concepts**
- Building new software is learning under uncertainty
- Get the unknown parts in front of valuable feedback fast

**Not core**
- The full feedback-source list (CI, teammates, users, customers, own use) — in the canonical, but a representative set is fine

**Sources**
- Building Software Is Learning: "Because building new software is learning! If you're building something new and you don't yet fully know how exactly it's supposed to work, you will learn what exactly it is that you're building as you're doing it."
- Building Software Is Learning: "the most important thing you can do when you're building something new: reducing the time it takes you to go from \"let me try something\" to getting your ass whooped by reality."
- Building Software Is Learning: "Feedback comes in all shapes and sizes: feedback from the CI system on main, feedback from colleagues, feedback from users, feedback from you once you actually use it."

### W13 opinion 4

Anything you can put on a leaderboard you can train against, so anything measurable is already on its way to commodity; durable value moves toward complex, private work that cannot be easily measured or copied.

**Core concepts**
- Anything you can put on a leaderboard can be trained against
- So measurable work is already on its way to commodity
- Durable value moves to complex, private work that's hard to measure or copy

**Sources**
- The Untrainable: "anything you can put on a leaderboard, you can train against, so anything measurable is already on its way to commodity."

### W13 opinion 5

In AI-generated products, private eval sets, real user edge cases, specs, and verification artifacts are more durable than the artifact itself, because they encode what good means and what must remain true; SQLite's closed test suite is a clearer moat than its open source implementation.

*Simplified candidate: In AI-generated products, private eval sets, real user edge cases, and verification artifacts are more durable than the artifact itself, because they encode what good means and what must remain true.*

**Core concepts**
- Private eval sets, user edge cases, specs, and verification artifacts are more durable than the artifact itself
- They encode what good means and what must remain true

**Not core**
- The SQLite closed-test-suite example — in the canonical, not required
- Exact membership of the durable-artifact list (eval sets, edge cases, specs, verification artifacts) — a representative set is fine

(Eval note: this target's failures were proposal routing/coverage, not judge verdicts.)

**Sources**
- Existing opinion context: "In AI-generated software, tests, specs, and verification artifacts are durable assets because they encode what must remain true, not just how the current code happens to work; SQLite's closed test suite is a clearer moat than its open source implementation."
- /goal + Loss Functions: How to Distill a Product in 30 Hours with One Prompt [Full Playbook]: "For the entire history of software, \"we built it\" was the moat. That era is closing. The next one belongs to whoever owns what the artifact never contained: the eval set nobody else can score against. The list of edge cases your users actually trip on. The ground truth you measure privately."

### W13 not converted

- Every Agentic Engineering Hack I Know: saved as possible reference material rather than a standalone opinion target.
- What's That Smell in San Francisco?: unrelated to the opinion themes in this eval set.
- I wrote this ~3 months ago, and since then: "Most genuinely useful coding agent workflow/feature will get integrated into the major harnesses before too long"
