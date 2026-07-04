# Opinion Eval Targets

## W04

### W04 opinion 1

As AI commoditizes execution, the bottleneck moves to high-quality intent: having ideas worth pursuing, articulating what good looks like, and turning that intent into criteria that agents and organizations can optimize toward.

**Key components**
- AI commoditizes execution, so the bottleneck moves to high-quality intent.
- Idea quality is primary; the ability to articulate it and orient toward it comes second. Do not imply articulation matters more than the idea itself.
    - the current opinion doesn't really encode this? like it is yes what the evidence says, but our opinion just says "having ideas worth pursuing" which doesn't really capture the essence of this point
- Intent becomes explicit criteria or an ideal state that agents and organizations can optimize toward.
- Do not flatten the two sources into a vague merged thesis (e.g. "prompting is unbundled product management"); the merged claim must stay one central claim about high-quality intent.
    - this is making me realize that the second source maybe shouldn't be included? or at least it's not super important, the only thing that it contributes is maybe "agents and organizations" instead of just "organizations"?

**Sources**
- The Most Important Ideas in AI Right Now: "The new scarce skill isn't coding or prompting—it's being able to say what you actually want. And it has to be high-quality intent. The quality of the idea is always the most important thing. But the second most important is the ability to articulate it, define it as your actual goal, and orient the entire company around it."
- Nobody is Talking About Generalized Hill-Climbing (at Runtime): "The author proposes a new way to improve AI by clearly defining and testing an \"Ideal State\" for any task, making progress measurable and verifiable."

### W04 opinion 2

Captured expertise is a one-way ratchet: once tacit know-how becomes skills, SOPs, context files, or open-source examples, AI can reuse it everywhere, so advantages based only on undocumented expert memory will erode.

**Key components**
- Expertise is dispersing from people's heads into skills, SOPs, context files, and open-source examples.
- Once captured, it never comes back out — a one-way ratchet.
    - not sure if "one way rachet" is strictly required
- AI can reuse captured expertise everywhere.
- Advantages based only on undocumented expert memory will erode.

**Sources**
- The Most Important Ideas in AI Right Now: "There's an articulation gap between what experts know and what's written down. Most expertise lives in people's heads. Cliff, the 62-year-old who knows how everything works but never documented any of it. When Cliff retires, that knowledge dies with him. What's happening now is that expertise is dispersing from brains into skills, SOPs, context files, open source projects. And once it's captured it never comes back out."

### W04 opinion 3

Generalist base models are likely to beat domain-specific base models because reasoning gains compound across fields; specialization should usually live in tools, data, skills, and harnesses unless scaling hits physical limits.

**Key components**
- Generalist base models are likely to beat domain-specific base models.
- The reason: intelligence from different fields builds on itself, so reasoning gains compound across fields.
- Specialization belongs in tools, data, skills, and harnesses, not the base model.
- Keep the caveat: unless scaling hits physical limits.
    - does this come from the source article? or is it AI editorializing?

**Sources**
- Why domain specific LLMs won't exist: an intuition: "Domain-specific large language models (LLMs) do not outperform general LLMs because intelligence from different fields builds on each other. General models learn from many areas, making them smarter overall."

### W04 opinion 4

Career growth is not something to wait for: managers can help, but ambitious people need to proactively tell their manager what they want, ask what must be true to reach the next level, and seek scope instead of assuming good work will be noticed.

**Key components**
- Career growth is not something to wait for; managers can help but will not drive it.
- Explicitly tell your manager that reaching the next level is a goal.
- Ask what must be true to get there, and seek scope proactively.
- Do not assume good work will be noticed on its own.

**Sources**
- Nobody Is Coming to Save Your Career: "If you've never told your manager you want to grow your career, this is the week you do it. It doesn't need to be a big formal conversation. In your next 1:1, try something like \"I just wanted to let you know that getting to the next level is a goal of mine. I'd like to talk about what needs to be true for that to happen on this team.\""

### W04 opinion 5

In hiring, an impressive accomplishment only creates signal if the candidate can deliver it well; a truthful, practiced account of tradeoffs and close calls reveals more than a polished success story that hides how they actually think.

**Key components**
- Even the most impressive accomplishment can be wasted by bad delivery; delivery determines whether it creates signal.
- Delivery is practiced deliberately: write answers down, record yourself, iterate.
- A truthful account including the hard parts and close calls shows how the candidate thinks, and is worth more than a polished success story.
- Do not reduce this to generic "communication matters in interviews"; keep the link between accomplishment value and delivery quality.

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

**Key components**
- Specs can shift implementation out of code, but they do not remove the need for precise design.
- A spec detailed enough to reliably generate working software necessarily becomes code or something strongly resembling code.

**Sources**
- A sufficiently detailed spec is code: "If you try to make a specification document precise enough to reliably generate a working implementation you must necessarily contort the document into code or something strongly resembling code."

### W05 opinion 2

Agent systems should keep the harness thin, put reusable judgment and process in skills, and push repeatable execution into deterministic tools so model improvements compound without making reliability depend on the model.

**Key components**
- Keep the harness thin: run the model in a loop, read/write files, manage context, enforce safety.
- Reusable judgment and process go in skills.
- Repeatable execution gets pushed down into deterministic tooling.
- The payoff: model improvements compound without reliability depending on the model.

**Sources**
- Thin Harness, Fat Skills: "The harness is the program that runs the LLM. It does four things: runs the model in a loop, reads and writes your files, manages context, and enforces safety. That's it. That's the \"thin.\""
- Thin Harness, Fat Skills: "The principle is directional. Push intelligence up into skills. Push execution down into deterministic tooling. Keep the harness thin."
- Thin Harness, Fat Skills: "If I ask you to do something and it's the kind of thing that will need to happen again, you must: do it manually the first time on 3 to 10 items. Show me the output. If I approve, codify it into a skill file."

### W05 opinion 3

AI does not need to beat an idealized version of knowledge work; in many companies it only has to beat messy, inconsistent operations where simply following instructions reliably is already above the current bar.

**Key components**
- AI does not need to beat an idealized version of knowledge work; it competes with how companies actually operate.
- Keep the source's sharpness: the operational bar in most companies is extremely low ("descending to the core of the earth"), not merely imperfect. Do not soften this into "companies are sometimes inefficient."
- Reliably following instructions, repeatedly and uncreatively, is already above the bar in most companies most of the time.

**Sources**
- Exactly Why and How AI Will Replace Knowledge Work: "When you hear the argument that AI cannot compete with humans—inside of a company, this is what they have to compete with. This bar is not low. It is on the floor. It burned a hole through the floor. It is descending to the core of the earth. AI can follow instructions. The ability to follow instructions over and over, doing the same thing in a very uncreative way, is better than what is done in most companies most of the time."

### W05 opinion 4

If AI displaces work, the problem is not only lost income; work currently supplies agency, contribution, mastery, and connection, so post-work institutions need to replace those functions rather than merely give people leisure.

**Key components**
- Work supplies four things people actually need: agency, contribution, mastery, and connection. Preserve all four.
- If AI displaces work, the problem is not only lost income.
- Post-work institutions need to replace those functions, not merely provide leisure.
- Do not drop the AI-displacement framing; this is about what comes after cognitive labor, not a generic "work gives life meaning" claim.

**Sources**
- The Displacement of Cognitive Labor and What Comes After: "What people actually seem to need is not work specifically but four things that work happens to provide: agency (the sense that you're making choices that matter), contribution (the sense that you're valued by others), mastery (the sense that you're getting better at something), and connection (belonging to something larger than yourself)."

### W05 not converted

- Your harness, your memory: "Even if the whole harness isn't behind the API, model providers are incentivized to move more and more behind APIs - and are already doing so."
- Inside GitHub's Fake Star Economy: "Jono Bacon at StateShift recommends five metrics that correlate with real adoption: package downloads, issue quality, contributor retention, community discussion depth, and usage telemetry."

## W06

### W06 opinion 1

In agentic product work, Figma is in an awkward position: when the product ultimately lives in code, the design source of truth should move closer to executable code rather than a manual, pre-agentic replica of the system.

**Key components**
- Keep Figma named explicitly; do not generalize to "design tools" and drop the example.
- When the product ultimately lives in code, the design source of truth moves back toward executable code.
- Figma is left holding a largely manual, pre-agentic replica of the system that nobody would design from scratch today.

**Sources**
- Thoughts and Feelings around Claude Design: "as the source of truth shifts back to code, Figma is left in an odd spot: holding a largely manual, pre-agentic system that nobody in their right mind would design from scratch today."

### W06 opinion 2

In agent products, durable advantage should come from company-specific domain reasoning and business logic; the common stack underneath should increasingly be platform primitives rather than bespoke plumbing.

**Key components**
- Durable advantage in agent products comes from domain reasoning and business logic — judgment calls specific to your company, customers, and regulatory environment.
- The common stack underneath should increasingly be platform primitives you build on, not bespoke plumbing you build.

**Sources**
- The Agent Stack Bet: "The real value lives in domain reasoning and business logic - the judgment calls that are specific to your company, your customers, your regulatory environment. Everything underneath should be the platform you build on, not the plumbing you build."

### W06 opinion 3

Engineering interviews in an AI-native world should test how candidates scope, build, review, and reason with AI tools on representative product work instead of testing code mechanics without assistance.

**Key components**
- Interviews should test how candidates scope, build, review, and reason with AI tools.
- The work should be representative product building, not toy problems.
- The contrast: not testing code mechanics without assistance.

**Sources**
- The AI-native interview: "Sierra redesigned their engineering interviews to focus on real product building using AI tools instead of traditional coding tests. Candidates plan, build, and review a product during onsite sessions to show their skills and thinking."

### W06 opinion 4

The current AI slop era may be a temporary golden age for human-AI work: models create useful rough output at volume, while humans still add the judgment, taste, and context that make the work satisfying; if AI later owns more of that judgment, taste, and context, this window may close.

**Key components**
- The current era may be a temporary golden age for human-AI work; keep the conditional, time-bounded framing.
- Models create useful rough output ("slop") at volume, which provides real leverage on time and jobs.
- Humans still add the judgment, taste, and context, and that division makes the work satisfying right now.
- The window may close if AI later owns more of that judgment, taste, and context.

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

In AI-assisted creative work, the default output is a floor, not a result; taste means knowing what to reject and overriding generic hooks, structure, and visual defaults before shipping.

**Key components**
- The default AI output is a floor, not a result.
- Default hooks and openings are almost always generic and wrong.
- Taste is not just knowing what you want; it is knowing what to reject and being willing to override the defaults before shipping.

**Sources**
- Everyone using AI has about 12 months to develop these 3 moats: "you get a content draft from Claude and rewrite the first two sentences because the AI opened with something generic, even though the rest is solid. the hook is everything and the default hook is almost always wrong."
- Everyone using AI has about 12 months to develop these 3 moats: "taste isnt just knowing what you want. its knowing what to reject. its having an opinion about the defaults and being willing to override them."

### W08 opinion 2

When AI can cheaply generate repos, tests, docs, and demos, real use becomes a stronger trust signal than polished artifacts; for serious software, prefer products with operational proof from yourself or comparable customers.

**Key components**
- When AI cheaply generates repos, tests, docs, and demos, polished artifacts weaken as trust signals.
- Real use is the stronger signal: something used daily for weeks beats something spat out and barely exercised.
- For serious software, prefer operational proof from yourself or comparable customers.

**Sources**
- Vibe coding and agentic engineering are getting closer than I'd like: "So I realized what I value more than the quality of the tests and documentation is that I want somebody to have used the thing. If you've got a vibe coded thing which you have used every day for the past two weeks, that's much more valuable to me than something that you've just spat out and hardly even exercised."
- Vibe coding and agentic engineering are getting closer than I'd like: "I don't want a CRM unless at least two other giant enterprises have successfully used that CRM for six months."

### W08 opinion 3

Passive productivity like reading and podcasts is helpful, but it has diminishing returns; active productivity scales better because its returns compound the more time you spend creating.

**Key components**
- Passive productivity (reading, podcasts) is helpful and makes you well-informed, but it has diminishing returns.
- Active productivity scales better because its returns compound the more time you spend creating.
- Do not editorialize beyond the source or fold in claims about doing things for claps, retweets, or audience rewards; that Learn In Public evidence stays unconverted.

**Sources**
- Being Someone who Does Things: "I can personally feel that having spent a decade or so doing lots of passively productive things has been helpful and made me pretty well-informed, but it hasn't been as powerful as if I'd spent more of that time doing actively productive things."

### W08 opinion 4

Agent prompts and harnesses should simplify as models improve: give clear structure and canonical examples, but avoid sprawling if-else prompts that try to pre-solve every edge case.

**Key components**
- Agent prompts and harnesses should simplify as models improve; growing complexity while models get better is a smell.
- Give clear structure and canonical examples that show expected behavior.
- Avoid sprawling if-else prompts that pre-solve every edge case; let the model handle edge cases.

**Sources**
- Your Agent's Compactor Matters More Than Its Context Window: "Anthropic found two failure modes: over-engineered system prompts with 2K+ words of if-else logic that break on edge cases, and vague prompts like \"be helpful\" that give the model nothing to work with. Their fix: organize prompts into clear sections (XML tags or markdown headers), use canonical examples to show expected behavior, and let the model handle edge cases instead of hard-coding them."
- Your Agent's Compactor Matters More Than Its Context Window: "One pattern worth noting: the teams shipping the best agents keep simplifying. Manus has been rewritten five times. Each rewrite removed things. If your agent harness is getting more complex while models get better, something is wrong."

### W08 not converted

- Everything I know about fundraising: "Founders should focus on building their product and talking to customers, not meeting VCs all the time."
- Learn In Public: "Don't judge your results by \"claps\" or retweets or stars or upvotes - just talk to yourself from 3 months ago. I keep an almost-daily dev blog written for no one else but me."

## W10

### W10 opinion 1

AI service replacement is most likely where customers already outsource repeatable execution or playbook-based work and judge the vendor by outcomes rather than visible effort.

**Key components**
- AI service replacement is most likely where the work is already outsourced — the customer has already accepted that someone else owns the execution.
- The vulnerable work is repeatable execution and playbook-based pattern application.
- The customer measures success by the outcome, not visible effort.

**Sources**
- Service as a Software: "Layer 1: Production work. The repeatable execution. Filing the tax return. Drafting the contract. Generating the report. Posting the invoice. Sending the follow-up"
- Service as a Software: "Layer 2: Pattern application. Translating a known problem into a working answer using a playbook the industry has refined for decades."
- Service as a Software: "The work is already outsourced. If a customer is paying a third party to do it, they have already accepted that someone else owns the execution"
- Service as a Software: "The customer measures success by the outcome, not the effort"

### W10 opinion 2

Career leverage is not about being well-rounded; Price's Law suggests that a small square-root-sized minority produces much of the output, so the goal is to find and compound your `√n` multiplier skills into a rare combination.

**Key components**
- Keep the Price's Law / `√n` framing explicitly: the square root of the number of people in a domain does about half the work. Do not paraphrase it away.
- Career leverage is not about being well-rounded.
- The goal is to find your two or three multiplier skills and compound them into a rare combination you are top 1% at.

**Sources**
- The Mathematical Reason Most People Never "Make It": "Double down on your √n skills. Get so good at your two or three multiplier skills that you're in the top 1% at the combination of those skills."
- The Mathematical Reason Most People Never "Make It": "Price's Law states that the square root of the number of people in a domain does 50% of the work."

### W10 opinion 3

AI coding should be used as a learning loop, not just an issue-closing machine; if the model removes all friction without forcing hypotheses, explanations, and reflection, cognitive debt accumulates.

**Key components**
- Use AI coding as a learning loop, not just an issue-closing machine.
- Friction was where the learning lived; sanding all of it away accumulates cognitive debt.
- Preserve the concrete mechanisms: form a hypothesis before asking, ask for the explanation before the code, and reflect on whether you learned anything or just closed issues.

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

**Key components**
- Service firms only become software-like when delivery compounds: if client five is just as hard as client one, the company is still selling labor.
- AI lowers the cost of building automation, not the cost of understanding the workflow; the workflow is the moat.
- The durable assets: vertical workflow knowledge, reusable agents, process data, playbooks, and proof that delivery gets more efficient over time.

**Sources**
- 30x AI agencies: Why service firms may earn software level multiples: "AI lowers the cost of building the automation. It doesn't lower the cost of understanding the workflow. The workflow is the moat."
- 30x AI agencies: Why service firms may earn software level multiples: "If client five is just as hard as client one, the company is still selling labor. If client five is easier, faster, and better because the firm learned from the first four, something more valuable is forming."
- 30x AI agencies: Why service firms may earn software level multiples: "Buyers will want vertical workflow knowledge, implementation playbooks, reusable agents, specialist talent, process data, and proof that delivery gets more efficient over time."

### W11 opinion 2

Enterprise AI transformation should start by mapping end-to-end workflows, ROI, data layers, and tribal knowledge around existing systems; rip-and-replace migrations often slow adoption more than they help.

**Key components**
- Start by mapping every workflow and the per-workflow ROI of an agent to choose where to deploy.
- Account for the data layers that power the transformation: system of record, business rules, raw intake data, and the feedback/memory the agent accumulates.
- Work around existing systems and their tribal knowledge; rip-and-replace migrations often slow adoption more than they help.

**Sources**
- How to Transform a Company With AI: "You should map every workflow, figure out what the ROI of an agent would be in each particular workflow and how to approach it from an engineering perspective, then choose where to deploy the agents where they'd be a good fit."
- How to Transform a Company With AI: "Don't force massive migrations. Most companies have already spent years moving onto systems like Salesforce and NetSuite."
- How to Transform a Company With AI: "In most workflows, the data that powers the transformation falls into four categories: the system of record, the business rules, the raw intake data, and the feedback or memory the agent accumulates over time."

### W11 opinion 3

Reliable agent harnesses should not treat bash or arbitrary code execution as universally necessary; many enterprise tasks are better served by task-specific, constrained tools than by a model with general computer access.

**Key components**
- Bash and arbitrary code execution are not universally necessary for agents, even though harnesses ship them by default.
- Many problems don't need and shouldn't have bash + code; task-specific, constrained tools serve them better.
- The enterprise reliability angle: you don't necessarily want something executing arbitrary code.

**Sources**
- The Anatomy of an Agent Harness: "Harnesses ship with a bash tool so models can solve problems autonomously by writing & executing code."
- The Anatomy of an Agent Harness: "This frames a harness as being something design to solve lots of kinds of problems and bash + code helps. I think lots of problems don't need and shouldn't have bash + code."
- What is an Agent Harness: "when you want something reliable in enterprise you don't necessarily want it executing arbitrary code"

### W11 opinion 4

Career choices should be judged by the compounding assets they build - skills, reputation, network, options, and operational scars - not just immediate pay, title, or brand.

**Key components**
- Judge career choices by the compounding assets they build: skills, reputation, network, options, operational scars.
- The networks that matter are built through work delivered together, not networking for its own sake.
- Stop optimizing for the next move; optimize for the move after that.
- The contrast: not just immediate pay, title, or brand.

**Sources**
- The Career Bets That Compound (And the Ones That Don't): "The networks that matter are built through work - through projects you delivered together, problems you solved together, hard situations you got through together."
- The Career Bets That Compound (And the Ones That Don't): "stop optimizing for the next move. Start optimizing for the move after that."
- The Career Bets That Compound (And the Ones That Don't): "Joining a great company early gives you the brand, the network, the wealth, the operational scars, and the credibility to start your own thing later."

### W11 opinion 5

High agency needs recovery and self-context, not endless escalation; because there is no final level, ambitious people should deliberately look back, accept their current state, and take breaks.

**Key components**
- High agency needs recovery and self-context, not endless escalation.
- There is no final level; the more you get ahead, the more levels you unlock.
- Deliberately look back, accept your current state within your own unique context, and take breaks.

**Sources**
- How to avoid feeling low as a high-agency person: "There is no final level of growth to be achieved. You will be a work in progress until you die. Learn to take a break."
- How to avoid feeling low as a high-agency person: "there is no endgame to a high-agency growth mindset. The more you get ahead in life, the more levels you unlock."
- How to avoid feeling low as a high-agency person: "Your situation, circumstances, and life are unique to you. Remember the context that surrounds you."

### W11 not converted

- Why founder conviction matters more than ever: "Return to customers before returning to investors. When conviction wavers, the fastest way to restore it is a direct conversation with someone whose problem you are solving."

## W12

### W12 opinion 1

Making code cheap to generate does not make ownership or system comprehension cheap to skip; people should understand AI-generated artifacts well enough to defend them under questioning.

**Key components**
- Cheap code generation does not make ownership or system comprehension cheap to skip.
- People are accountable for the artifact even when AI generated it.
- The bar: understand what you ship well enough to defend it under questioning.

**Sources**
- How AI Productivity Fails: "Hold people accountable for the artifact even when AI generated it; build pushback culture with harsh, specific feedback when output crosses into slop"
- How AI Productivity Fails: "you have to understand what you ship well enough to defend it under questioning"

### W12 opinion 2

Agentic throughput is capped by human review bandwidth, not by how many workers the UI can spawn; the right amount of parallelism is the work you can actually evaluate without surrendering standards.

**Key components**
- Agentic throughput is capped by human review bandwidth, not by how many workers you can spawn.
- Optimizing the non-bottleneck doesn't increase throughput; it just grows the pile of unfinished work in front of the bottleneck.
- The right number of parallel agents is what you can actually review properly without surrendering standards — usually low single digits.

**Sources**
- The Orchestration Tax: "optimizing the non bottleneck part doesn't increase throughput. You just grow the pile of unfinished work sitting in front of the bottleneck."
- The Orchestration Tax: "The right number of parallel agents is how many you can actually code review properly. For most of us this is a low single digit."

### W12 opinion 3

The goal of agentic work is not maximum delegation; use agents to remove routine work, but stay deliberately in the loop where taste develops and original work needs your fingerprints rather than just your approval.

**Key components**
- The goal of agentic work is not maximum delegation.
- Use agents to remove routine work, but stay deeply, deliberately in the loop where taste develops and original work happens.
- Keep the fingerprints-versus-approval distinction: original work carries your fingerprints, not just your sign-off.

**Sources**
- Escape from agentic loop: "Some of the day I want to be deeply, deliberately in the loop, because that is where taste develops and where original work happens - the kind that has my fingerprints on it, not just my approval."

### W12 not converted

- The Death of the Three-Act Playbook: "As the cost of writing software drops to zero, I find myself valuing ambition above all else. Unreasonable, unrelenting ambition. I think the three-act play is dead."
- On mid-career satisfaction: "Competence in your role - Flow when doing your work - Culture & people fit - Work-life harmony - How you feel most Sunday evenings"

## W13

### W13 opinion 1

A good vertical agent is a faithful compression of its task distribution: the Shortcut Excel-agent example shows why common capabilities belong in fast prompt context, rarer capabilities belong in discoverable tiers, and complete underlying references should remain searchable for rare cases the curated layers do not cover.

**Key components**
- A good vertical agent is a faithful compression of its task distribution — the compression encodes the distribution of users and tasks.
- The tiering: common capabilities in fast prompt context, rarer capabilities in discoverable tiers, complete references searchable for the rare cases the curated layers miss.
- Every optimization trades compression of information against speed of discovery.
- Keep the Shortcut Excel-agent example by name; the concrete example matters.

**Sources**
- Building a Good Vertical Agent: "I've spent almost a year now building the Shortcut agent, which is widely considered the most accurate spreadsheet agent around"
- Building a Good Vertical Agent: "a good agent is a faithful compression of its task distribution."
- Building a Good Vertical Agent: "Almost every optimization trades compression of information against speed of discovery. Put something in L1 and it's instant, but it costs prompt tokens on every single task whether it's used or not. Push it to L3 and it costs nothing until needed - but then it costs several tool calls to find."
- Building a Good Vertical Agent: "The compression in those system prompts and curated specs is really an encoding of the distribution of your users and the tasks they do"

### W13 opinion 2

Agentic optimization is only as good as its loss function: if the target, constraints, instruments, and examples leave cheap paths open, the agent will exploit them instead of getting genuinely better.

**Key components**
- Agentic optimization is only as good as its loss function.
- Every cheap path you don't fence off is a direction the optimizer will sprint down.
- Real expected-output examples up front — what good looks like, at scale — let you run the soak before you ship.

**Sources**
- /goal + Loss Functions: How to Distill a Product in 30 Hours with One Prompt [Full Playbook]: "Every cheap path you don't fence off is a direction the optimizer will sprint down."
- /goal + Loss Functions: How to Distill a Product in 30 Hours with One Prompt [Full Playbook]: "If you can get real expected-output examples up front - what good looks like, at scale - you run the soak before you ship"

### W13 opinion 3

Building new software is learning under uncertainty; the right move is to expose the unknown parts to valuable feedback quickly, whether from CI, teammates, users, customers, or your own use.

**Key components**
- Building new software is learning: you learn what you're building as you build it.
- The key move is minimizing the time from "let me try something" to getting reality's feedback.
- Feedback comes in many forms: CI, colleagues, users, customers, and your own use.

**Sources**
- Building Software Is Learning: "Because building new software is learning! If you're building something new and you don't yet fully know how exactly it's supposed to work, you will learn what exactly it is that you're building as you're doing it."
- Building Software Is Learning: "the most important thing you can do when you're building something new: reducing the time it takes you to go from \"let me try something\" to getting your ass whooped by reality."
- Building Software Is Learning: "Feedback comes in all shapes and sizes: feedback from the CI system on main, feedback from colleagues, feedback from users, feedback from you once you actually use it."

### W13 opinion 4

Anything you can put on a public leaderboard is already on its way to commodity, because models can train against measurable benchmarks; durable capability work moves toward private, messy, user-specific edge cases.

**Key components**
- Anything you can put on a leaderboard you can train against, so anything measurable is already on its way to commodity.
- Durable capability work moves toward private, messy, user-specific edge cases.
- This is a standalone opinion about AI capability trajectory; do not merge it into the private-evals/verification-artifacts opinion.

**Sources**
- The Untrainable: "anything you can put on a leaderboard, you can train against, so anything measurable is already on its way to commodity."

### W13 opinion 5

In AI-generated products, private eval sets, real user edge cases, specs, and verification artifacts are more durable than the artifact itself, because they encode what good means and what must remain true; SQLite's closed test suite is a clearer moat than its open source implementation.

**Key components**
- Private eval sets, real user edge cases, specs, and verification artifacts are more durable than the artifact itself.
- They are durable because they encode what good means and what must remain true, not how the current code happens to work.
- Keep the SQLite example: the closed test suite is a clearer moat than the open source implementation. Do not remove it when revising.
- "We built it" as the moat is ending; the next moat is what the artifact never contained.

**Sources**
- Existing opinion context: "In AI-generated software, tests, specs, and verification artifacts are durable assets because they encode what must remain true, not just how the current code happens to work; SQLite's closed test suite is a clearer moat than its open source implementation."
- /goal + Loss Functions: How to Distill a Product in 30 Hours with One Prompt [Full Playbook]: "For the entire history of software, \"we built it\" was the moat. That era is closing. The next one belongs to whoever owns what the artifact never contained: the eval set nobody else can score against. The list of edge cases your users actually trip on. The ground truth you measure privately."

### W13 not converted

- Every Agentic Engineering Hack I Know: saved as possible reference material rather than a standalone opinion target.
- What's That Smell in San Francisco?: unrelated to the opinion themes in this eval set.
- I wrote this ~3 months ago, and since then: "Most genuinely useful coding agent workflow/feature will get integrated into the major harnesses before too long"
