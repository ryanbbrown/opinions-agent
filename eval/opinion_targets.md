# Opinion Eval Targets

## Judge rules

- The conceptual judge checks required concepts and stance. Extra elaboration does not fail by itself.
- Evidence precision separately penalizes citations outside the target's converted evidence.
- Added same-source specificity is allowed when the draft carries the core concepts.
- One selected evidence row has one opinion home. Different highlights from the same article can support different opinions.

## W04

### W04-01

**Operation:** update `opinion-000003`

**Section:** Agentic Software

As AI commoditizes implementation, high-quality intent becomes the scarce skill: having ideas worth pursuing, articulating what good looks like, and judging whether an agent's output is actually good.

**Core concepts**

- AI makes implementation cheap
- High-quality intent becomes the scarce skill
- Having worthwhile ideas matters
- Articulating what good looks like
- Judging whether the agent's output is good

**Assigned evidence IDs**

- `rw:01kp1xajs4em2bhwcs3rz0j2wq`

**Source excerpts**

- The Most Important Ideas in AI Right Now: “The new scarce skill isn't coding or prompting—it's being able to say what you actually want. And it has to be high-quality intent. The quality of the idea is always the most important thing. But the second most important is the ability to articulate it, define it as your actual goal, and orient the entire company around it.”

### W04-02

**Operation:** add

**Section:** Moats And Strategy

Expertise is dispersing from experts' heads into skills, SOPs, context files, and open-source projects, and once captured it never comes back out; advantages based only on undocumented expert memory will erode as AI reuses what gets captured.

**Core concepts**

- Expertise is moving out of experts' heads into captured forms (skills, SOPs, context files, open source)
- Capture is one-way: once out, it never comes back
- Advantages based only on undocumented expert memory erode

**Assigned evidence IDs**

- `rw:01kp1x7w709ae4n44b0z3g7h4w`

**Source excerpts**

- The Most Important Ideas in AI Right Now: “There's an articulation gap between what experts know and what's written down. Most expertise lives in people's heads. Cliff, the 62-year-old who knows how everything works but never documented any of it. When Cliff retires, that knowledge dies with him. What's happening now is that expertise is dispersing from brains into skills, SOPs, context files, open source projects. And once it's captured it never comes back out.”

### W04-03

**Operation:** add

**Section:** Agentic Software

Generalist base models are likely to beat domain-specific base models because intelligence from different fields builds on itself; domain-specific models mainly make sense if we hit physical limits in model size.

**Core concepts**

- Generalist models beat domain-specific models
- Because learning from many areas makes a model smarter overall; knowledge from different fields builds on each other
- Domain-specific mainly makes sense if model size hits physical limits

**Assigned evidence IDs**

- `reader-summary:01knheqfs4r61jy1ffvtbayqs8`

**Source excerpts**

- Why domain specific LLMs won't exist: an intuition: “Domain-specific large language models (LLMs) do not outperform general LLMs because intelligence from different fields builds on each other. General models learn from many areas, making them smarter overall.”

### W04-04

**Operation:** add

**Section:** Career And Work

Career growth is not something to wait for: managers can help, but ambitious people need to proactively tell their manager what they want, ask what must be true to reach the next level, and seek scope instead of assuming good work will be noticed.

**Core concepts**

- Career growth requires being proactive, not waiting for good work to be noticed
- Tell your manager the goal explicitly
- Ask what must be true to reach the next level

**Assigned evidence IDs**

- `rw:01kp1xj8s4sdw2nswebpn7pher`

**Source excerpts**

- Nobody Is Coming to Save Your Career: “If you've never told your manager you want to grow your career, this is the week you do it. It doesn't need to be a big formal conversation. In your next 1:1, try something like "I just wanted to let you know that getting to the next level is a goal of mine. I'd like to talk about what needs to be true for that to happen on this team."”

### W04-05

**Operation:** add

**Section:** Career And Work

In hiring, an impressive accomplishment only creates signal if the candidate can deliver it well; a truthful, practiced account of tradeoffs and close calls reveals more than a polished success story that hides how they actually think.

**Core concepts**

- An impressive accomplishment only counts if delivered well
- Truthful accounts of the tradeoffs and close calls reveal how you actually think
- That reveals more than a polished success story

**Assigned evidence IDs**

- `rw:01kp1wkxxh3a81jf620rm5kzns`
- `rw:01kp1wnk6d4ckysfzsj34sfpfk`
- `rw:01kp1wrn0b3b2ray7wa6yhf08e`

**Source excerpts**

- What I Learned From Nearly 1,000 Interviews at Amazon: “You can have the most impressive accomplishment of your career ready for your interview and completely waste it with bad delivery.”
- What I Learned From Nearly 1,000 Interviews at Amazon: “Write down your answers. Then record yourself delivering them. Watch the recording and take notes. Where did you ramble? Where did you fill space with filler words? Did you look nervous? Then do it again. And again.”
- What I Learned From Nearly 1,000 Interviews at Amazon: “You'd want the real version of what happened, including the parts that were hard and the calls that were close. You'd want to walk away feeling like you understood what it would be like to work with them on a tough problem. Give your interviewer that same thing. Be honest and let them see how you think. That's worth more than any polished answer.”

### W04 not converted

- Exactly Why and How AI Will Replace Knowledge Work (`rw:01knsfwz445dshjfcp1187aq8y`, highlight)
- LLM Knowledge Bases (`rw:01knsg2ewdrn49pgs7qqce4bkf`, highlight)
- This is how you can properly manage your multiple interests (`reader-summary:01knx04re2w4fwn5heegajwf6x`, document_summary)
- We Have Learned Nothing (`reader-summary:01kp1vk3rsjj4wwp5mfqkh4nst`, document_summary)
- Nobody is Talking About Generalized Hill-Climbing (at Runtime) (`reader-summary:01kp1wzn737jegz28sg4ee3hzg`, document_summary)

## W05

### W05-01

**Operation:** add

**Section:** Agentic Software

Specs can shift implementation out of code, but they do not remove the need for precise design; a specification detailed enough to reliably generate working software starts to become code or code-like formal language.

**Core concepts**

- Precise design is still needed
- A spec detailed enough to reliably generate working software becomes code-like

**Assigned evidence IDs**

- `rw:01kp4spezcbaka7nxvzn7wm08h`

**Source excerpts**

- A sufficiently detailed spec is code: “If you try to make a specification document precise enough to reliably generate a working implementation you must necessarily contort the document into code or something strongly resembling code.”

### W05-02

**Operation:** add

**Section:** Agentic Software

Agent systems should keep the harness thin, put reusable judgment and process in skills, and push repeatable execution into deterministic tools so model improvements compound without making reliability depend on the model.

**Core concepts**

- Keep the harness thin
- Reusable judgment/process goes in skills
- Repeatable execution goes in deterministic tools
- The payoff/why: model improvements compound to lift the whole system

**Assigned evidence IDs**

- `rw:01kp4ry1ctwkkkh49m80pbk6dm`
- `rw:01kp4s1p54d7xewx3zfvv17wan`
- `rw:01kp4s84v3vh8njpq3y815kcfn`

**Source excerpts**

- Thin Harness, Fat Skills: “The harness is the program that runs the LLM. It does four things: runs the model in a loop, reads and writes your files, manages context, and enforces safety. That's it. That's the "thin."”
- Thin Harness, Fat Skills: “The principle is directional. Push intelligence up into skills. Push execution down into deterministic tooling. Keep the harness thin.”
- Thin Harness, Fat Skills: “If I ask you to do something and it's the kind of thing that will need to happen again, you must: do it manually the first time on 3 to 10 items. Show me the output. If I approve, codify it into a skill file.”

### W05-03

**Operation:** add

**Section:** AI Leverage And Organizations

AI does not need to beat an idealized version of knowledge work; in many companies it only has to beat messy, inconsistent operations where simply following instructions reliably is already above the current bar.

**Core concepts**

- AI doesn't have to beat idealized knowledge work
- It only has to beat messy/inconsistent real operations
- Reliably following instructions already clears the bar in many companies

**Assigned evidence IDs**

- `rw:01kp4wgb37kpzj9jyq45a5nyk6`

**Source excerpts**

- Exactly Why and How AI Will Replace Knowledge Work: “When you hear the argument that AI cannot compete with humans—inside of a company, this is what they have to compete with. This bar is not low. It is on the floor. It burned a hole through the floor. It is descending to the core of the earth. AI can follow instructions. The ability to follow instructions over and over, doing the same thing in a very uncreative way, is better than what is done in most companies most of the time.”

### W05-04

**Operation:** add

**Section:** Career And Work

People do not need work specifically; they need four things work happens to provide — agency, contribution, mastery, and connection — so if AI displaces work, whatever comes after has to supply those four functions, not just income.

**Core concepts**

- People need what work provides, not work itself
- The four by name: agency, contribution, mastery, connection
- Whatever replaces work must supply those four

**Assigned evidence IDs**

- `rw:01kp4ymck943np90xtvj52v2fh`

**Source excerpts**

- The Displacement of Cognitive Labor and What Comes After: “What people actually seem to need is not work specifically but four things that work happens to provide: agency (the sense that you're making choices that matter), contribution (the sense that you're valued by others), mastery (the sense that you're getting better at something), and connection (belonging to something larger than yourself).”

### W05 not converted

- Agentic Engine Optimization (AEO) (`rw:01kp4tvfzshf5bfprv5cmgnqbr`, highlight)
- How To Solve Problems Of Long Running, Autonomous Agentic Engineering Workflows (`rw:01kp4v5fs5ce4ysgvds7xwzg5p`, highlight)
- How To Solve Problems Of Long Running, Autonomous Agentic Engineering Workflows (`reader-note:01knn2619wja5ygv0h56hzrxx3`, highlight)
- Your harness, your memory (`rw:01kp4vwhm6v4yqstt09yrh5zzk`, highlight)
- Your harness, your memory (`reader-note:01kp4rp233sc76tdfp7mf2xjnr`, highlight)
- Exactly Why and How AI Will Replace Knowledge Work (`rw:01kp4wp88w5x9h6tw262wz0xka`, highlight)
- Exactly Why and How AI Will Replace Knowledge Work (`rw:01kp4wyjyj8h776b4ekmn0ecft`, highlight)
- Exactly Why and How AI Will Replace Knowledge Work (`rw:01kp4x720vr9y3n95az6b745a6`, highlight)
- Exactly Why and How AI Will Replace Knowledge Work (`reader-note:01knpm2zp6692xxhfyrtz3j8me`, highlight)
- The Displacement of Cognitive Labor and What Comes After (`rw:01kp4xz07e417q0zddz23ctdqh`, highlight)
- The Displacement of Cognitive Labor and What Comes After (`rw:01kp4y683602xj8ej1eh8c6gc7`, highlight)
- The Displacement of Cognitive Labor and What Comes After (`rw:01kp4y8ksxz00qnnwdwv5qmd8f`, highlight)
- The Displacement of Cognitive Labor and What Comes After (`rw:01kp4yfeqs5y8xwyqej0k515kx`, highlight)
- The Displacement of Cognitive Labor and What Comes After (`rw:01kp4yh2jmvcpf0e2sx2ae94kw`, highlight)
- The advisor strategy: Give Sonnet an intelligence boost with Opus (`reader-note:01kp68t708tyd1rdb5wmdt4y6s`, highlight)
- Inside GitHub's Fake Star Economy (`rw:01kp99ker8ppyc380xc4a76cdj`, highlight)

## W06

### W06-01

**Operation:** add

**Section:** Agentic Software

In agentic product work, Figma is in an awkward position: when the product ultimately lives in code, the design source of truth should move closer to executable code rather than a manual, pre-agentic replica of the system.

**Core concepts**

- Figma specifically is in an awkward position
- The product ultimately lives in code
- The design source of truth should move closer to code
- A manually maintained replica of the product is the wrong source of truth

**Assigned evidence IDs**

- `rw:01kpph104zd1vdw0vkdqpsc6m9`

**Source excerpts**

- Thoughts and Feelings around Claude Design: “as the source of truth shifts back to code, Figma is left in an odd spot: holding a largely manual, pre-agentic system that nobody in their right mind would design from scratch today.”

### W06-02

**Operation:** add

**Section:** Moats And Strategy

In agent products, durable advantage should come from company-specific domain reasoning and business logic; the common stack underneath should increasingly be platform primitives rather than bespoke plumbing.

**Core concepts**

- Durable advantage comes from company-specific domain reasoning and business logic
- The layer underneath should be platform primitives, not bespoke plumbing

**Assigned evidence IDs**

- `rw:01kps6pym55wbe9p3jhk8mpd4x`

**Source excerpts**

- The Agent Stack Bet: “The real value lives in domain reasoning and business logic - the judgment calls that are specific to your company, your customers, your regulatory environment. Everything underneath should be the platform you build on, not the plumbing you build.”

### W06-03

**Operation:** add

**Section:** Career And Work

Engineering interviews in an AI-native world should test how candidates scope, build, review, and reason with AI tools on representative product work instead of testing code mechanics without assistance.

**Core concepts**

- Interviews should test working with AI tools
- On representative product work (scope, build, review, reason)
- Instead of traditional unassisted coding tests

**Assigned evidence IDs**

- `reader-summary:01kpxgvdm8h04w0k41wv4nrjgb`

**Source excerpts**

- The AI-native interview: “Sierra redesigned their engineering interviews to focus on real product building using AI tools instead of traditional coding tests. Candidates plan, build, and review a product during onsite sessions to show their skills and thinking.”

### W06-04

**Operation:** add

**Section:** Taste, Craft, And Signal

The current AI slop era may be a golden age for human-AI work: models create useful slop at volume, humans are still needed to desloppify it, and that combination gives real leverage while keeping the work fun; if AI eventually displaces people or takes over the more interesting work, this moment may fade.

**Core concepts**

- Right now is likely a golden age of human+AI work
- AI produces useful slop at volume
- Humans are still needed to clean it up
- The combination gives real leverage
- It may fade if AI displaces people or takes the interesting work

**Assigned evidence IDs**

- `rw:01kps7gne0fanp8tbn80gk6m75`

**Source excerpts**

- Random thoughts while gazing at the misty AI Frontier: “We are likely in the golden era of AI + humanity. Before the last few years, AI was inaccessible, not very generalizable, and could only do specific tasks. In the future, AI may become superhuman at most tasks and take over a lot of work some people find fun. Today, AI creates useful slop at volume, which means humans are still needed to desloppify the slop, but the slop provides real leverage on time and jobs, which means it is fun to be working right now. If AI displaces people eventually or does more interesting work, this golden moment may fade or change.”

### W06 not converted

- Output isn’t design (`rw:01kpph97738cjs82rt1rx0dtzc`, highlight)
- Output isn’t design (`rw:01kppha22vcqedvq4826m6bwdd`, highlight)
- Why you should be mysterious (`rw:01kppnbjv8zsshckt47x756cze`, highlight)
- Why ChatGPT Cites One Page Over Another (Study of 1.4M Prompts) (`rw:01kps72hrn6jg1pz60g042b6x1`, highlight)
- Random thoughts while gazing at the misty AI Frontier (`rw:01kps7ca36w5a2cwqbjnwd9e30`, highlight)
- Random thoughts while gazing at the misty AI Frontier (`rw:01kps7erhy3gj8j5ztbxk5nmzp`, highlight)
- Random thoughts while gazing at the misty AI Frontier (`rw:01kps7mf3m0r5qkywxfc3y4ex7`, highlight)
- The AI engineering stack we built internally — on the platform we ship (`reader-note:01kps6a2tbesnhhcwp8eqah391`, highlight)
- Agent Vault: The Open Source Credential Proxy and Vault for Agents (`reader-summary:01kq0y6qzn9azdx9sf6bxc212b`, document_summary)
- A new way to think about composing skills to increase leverage: Skill Graphs 2.0 (`reader-summary:01kq0y72hsstfmbje13d753r4n`, document_summary)
- Run Excellent 1:1s  (`reader-summary:01kq3zdjbmb2n6v2600cmmaw75`, document_summary)

## W07

### W07 not converted

- How to Build a One-Person Services-as-Software Company (`reader-summary:01kq924c3ndp0ng67ka9m7b51k`, document_summary)
- networking guide for a hardened technical introvert (`reader-summary:01kqnhsf2hgj5cahs24nfthfm5`, document_summary)

## W08

### W08-01

**Operation:** add

**Section:** Taste, Craft, And Signal

In AI-assisted creative work, taste is not just knowing what you want but knowing what to reject: the default output is almost always generic, so have an opinion about the defaults — starting with the hook — and be willing to override them.

**Core concepts**

- Taste is knowing what to reject, not just what you want
- Default AI output is almost always generic
- Have opinions about the defaults and override them

**Assigned evidence IDs**

- `rw:01kqx6150aqwx36jrn6m7w15mw`
- `rw:01kqx62f1hr4jw9seen2t9k8xv`

**Source excerpts**

- Everyone using AI has about 12 months to develop these 3 moats: “you get a content draft from Claude and rewrite the first two sentences because the AI opened with something generic, even though the rest is solid. the hook is everything and the default hook is almost always wrong.”
- Everyone using AI has about 12 months to develop these 3 moats: “taste isnt just knowing what you want. its knowing what to reject. its having an opinion about the defaults and being willing to override them.”

### W08-02

**Operation:** add

**Section:** Taste, Craft, And Signal

When AI can cheaply generate repos, tests, and docs, real use becomes a stronger trust signal than polished artifacts; for serious software, prefer products with operational proof from yourself or comparable customers.

**Core concepts**

- AI makes polished artifacts (repos, tests, docs) cheap to generate
- So polished artifacts stop being proof
- Real use is the stronger trust signal
- For serious software: want proof of real use by yourself or comparable customers

**Assigned evidence IDs**

- `rw:01kqza7w92hqnr2n1hratd69ja`
- `rw:01kqzacv41vz7vwqtds7faevws`

**Source excerpts**

- Vibe coding and agentic engineering are getting closer than I'd like: “So I realized what I value more than the quality of the tests and documentation is that I want somebody to have used the thing. If you've got a vibe coded thing which you have used every day for the past two weeks, that's much more valuable to me than something that you've just spat out and hardly even exercised.”
- Vibe coding and agentic engineering are getting closer than I'd like: “I don't want a CRM unless at least two other giant enterprises have successfully used that CRM for six months.”

### W08-03

**Operation:** add

**Section:** Career And Work

Passive productivity like reading and podcasts is helpful, but it has diminishing returns; active productivity scales better because its returns compound the more time you spend creating.

**Core concepts**

- Passive consumption (reading, podcasts) helps but has limited/diminishing returns
- Active creating compounds and scales better

**Assigned evidence IDs**

- `rw:01kr1c8j4a6aph5qyrbswghyyg`

**Source excerpts**

- Being Someone who Does Things: “I can personally feel that having spent a decade or so doing lots of passively productive things has been helpful and made me pretty well-informed, but it hasn't been as powerful as if I'd spent more of that time doing actively productive things.”

### W08-04

**Operation:** add

**Section:** Agentic Software

Agent prompts and harnesses should simplify as models improve: give clear structure and canonical examples, but avoid sprawling if-else prompts that try to pre-solve every edge case.

**Core concepts**

- Prompts and harnesses should get simpler as models improve
- Give clear structure and canonical examples
- Don't hard-code every edge case with if-else logic; let the model handle them

**Assigned evidence IDs**

- `rw:01kr1e39kwmpkhr3jmqz7ayjtz`
- `rw:01kr1gd42xk8r6ttgm3as7dx56`

**Source excerpts**

- Your Agent's Compactor Matters More Than Its Context Window: “Anthropic found two failure modes: over-engineered system prompts with 2K+ words of if-else logic that break on edge cases, and vague prompts like "be helpful" that give the model nothing to work with. Their fix: organize prompts into clear sections (XML tags or markdown headers), use canonical examples to show expected behavior, and let the model handle edge cases instead of hard-coding them.”
- Your Agent's Compactor Matters More Than Its Context Window: “One pattern worth noting: the teams shipping the best agents keep simplifying. Manus has been rewritten five times. Each rewrite removed things. If your agent harness is getting more complex while models get better, something is wrong.”

### W08-05

**Operation:** update `opinion-000009`

**Section:** Moats And Strategy

AI commoditizes knowledge that can be specified or copied, while operational scar tissue compounds in coupled, changing systems because each real-world surprise changes both the system and how future surprises should be interpreted. This moat disappears when the underlying system is replaced.

**Core concepts**

- AI commoditizes knowledge that can be specified or copied
- Operational scar tissue compounds in coupled, changing systems
- Each real-world surprise changes both the system and how future surprises should be interpreted
- A newcomer cannot catch up merely by studying the current state
- The moat disappears when the underlying system is replaced

**Assigned evidence IDs**

- `reader-note:01kksy9drnnqysr6tb5e2n0pw3`

**Source excerpts**

- Reality's Moat: “Operational knowledge = ‘scar tissue’: unspecifiable know-how earned by actually operating in a coupled, shifting system, where each surprise changes both the system and what you know about it. It’s divergent knowledge that others can’t reach just by studying current data or code.”

### W08 not converted

- Everything I know about fundraising (`reader-summary:01kqw23expe6ftzt2fw6h4zsf7`, document_summary)
- Everyone using AI has about 12 months to develop these 3 moats (`rw:01kqx6dn4kznxyee56kam1dtwk`, highlight)
- Vibe coding and agentic engineering are getting closer than I'd like (`rw:01kqza5d6z2e6rxd05srywx3js`, highlight)
- Vibe coding and agentic engineering are getting closer than I'd like (`rw:01kqzac9jvear55ar5ctk4kb14`, highlight)
- Learn In Public (`rw:01kr054spqb6fgydpqhwakzfrj`, highlight)
- Treat Agent Output Like Compiler Output (`rw:01kr1n6wwxqskhtwwvekd2kvek`, highlight)

## W10

### W10-01

**Operation:** add

**Section:** AI Leverage And Organizations

AI service replacement is most likely where customers already outsource repeatable execution or playbook-based work and judge the vendor by outcomes rather than visible effort.

**Core concepts**

- AI replaces services most easily where the work is already outsourced
- Repeatable, playbook-based work
- Where customers judge by outcomes, not effort

**Assigned evidence IDs**

- `rw:01ks48kzxb83phc9391h8cf8rb`
- `rw:01ks48m61rmne707ncmvybtzep`
- `rw:01ks48n8bwnm9z99f78pykbdz0`
- `rw:01ks48npm5g6axxxm14749q10z`

**Source excerpts**

- Service as a Software: “Layer 1: Production work. The repeatable execution. Filing the tax return. Drafting the contract. Generating the report. Posting the invoice. Sending the follow-up”
- Service as a Software: “Layer 2: Pattern application. Translating a known problem into a working answer using a playbook the industry has refined for decades.”
- Service as a Software: “The work is already outsourced. If a customer is paying a third party to do it, they have already accepted that someone else owns the execution”
- Service as a Software: “The customer measures success by the outcome, not the effort”

### W10-02

**Operation:** add

**Section:** Career And Work

Career leverage is not about being well-rounded; Price's Law suggests that a small square-root-sized minority produces much of the output, so the goal is to find and compound your √n multiplier skills into a rare combination.

**Core concepts**

- Price's Law / √n: a small square-root-sized minority produces much of the output
- Find your multiplier skills and compound them into a rare combination

**Assigned evidence IDs**

- `rw:01ks4a57xnehk7pvt344an40r0`
- `rw:01ks4a6rrzwhhxew6vxs7d1h4k`

**Source excerpts**

- The Mathematical Reason Most People Never "Make It": “Double down on your √n skills. Get so good at your two or three multiplier skills that you're in the top 1% at the combination of those skills.”
- The Mathematical Reason Most People Never "Make It": “Price's Law states that the square root of the number of people in a domain does 50% of the work.”

### W10-03

**Operation:** add

**Section:** Agentic Software

AI coding should be used as a learning loop, not just an issue-closing machine; if the model removes all friction without forcing hypotheses, explanations, and reflection, cognitive debt accumulates.

**Core concepts**

- Use AI coding to learn, not just to close tasks
- Removing all friction without hypotheses, explanations, and reflection destroys the learning
- The phenomenon is named "cognitive debt" — this exact term is required, not a paraphrase

**Assigned evidence IDs**

- `rw:01ks4c170xt36eey5bq8sj0n5c`
- `rw:01ks4c4wb18w1f86pc9dmj85ba`
- `rw:01ks4c4zva18j35mcqvabwm870`
- `rw:01ks4c5y6tq22mq95sm432mc83`
- `rw:01ks4c5kbce54yadfx1fwytfz2`

**Source excerpts**

- Don't Outsource the Learning: “We all want fewer keystrokes, so the tools have sanded the friction away. The trouble is that friction was where the learning lived.”
- Don't Outsource the Learning: “Form a hypothesis before you ask.”
- Don't Outsource the Learning: “Ask for the explanation before the code”
- Don't Outsource the Learning: “I've started ending coding sessions with a simple question: did I learn anything today, or did I just close issues?”
- Don't Outsource the Learning: “Ask the model to teach you what it just did. After it writes a clever function, ask what concepts it used and what you'd need to read to understand the design choice.”

### W10 not converted

- Today's harness is Tomorrow's Prompt (`rw:01ks488cgkvh7ryjd6q0scctz6`, highlight)
- In 2023, Stanford professor Graham Weaver gave his last lecture... (`rw:01ks48wjd3k62vshv2sjxgsnpz`, highlight)
- In 2023, Stanford professor Graham Weaver gave his last lecture... (`rw:01ks48ya7b8dszjzmsphsg9tvg`, highlight)
- every company has the same hiring criteria (`rw:01ks4adej3wt1j4pc643pbh81q`, highlight)
- Jobs Are Dead. Long Live the $10 Million Niche. (`rw:01ks4apq6fqv55z2w9brx3017d`, highlight)

## W11

### W11-01

**Operation:** add

**Section:** Moats And Strategy

AI-native service firms only become software-like when delivery gets easier, faster, and better with each client; the durable asset is vertical workflow knowledge, reusable agents, process data, and proof that the system compounds.

**Core concepts**

- Service firms become software-like only when each client gets easier, faster, and better (compounding)
- What accumulates: vertical workflow knowledge, reusable agents, process data

**Assigned evidence IDs**

- `rw:01ksk7bdz0gp2cdf3p1ctd280t`
- `rw:01ksk7d2kahx9fp1brv5n7aqs1`
- `rw:01ksk7dsefqbz5scnqznv9yyk9`

**Source excerpts**

- 30x AI agencies: Why service firms may earn software level multiples: “AI lowers the cost of building the automation. It doesn't lower the cost of understanding the workflow. The workflow is the moat.”
- 30x AI agencies: Why service firms may earn software level multiples: “If client five is just as hard as client one, the company is still selling labor. If client five is easier, faster, and better because the firm learned from the first four, something more valuable is forming.”
- 30x AI agencies: Why service firms may earn software level multiples: “Buyers will want vertical workflow knowledge, implementation playbooks, reusable agents, specialist talent, process data, and proof that delivery gets more efficient over time.”

### W11-02

**Operation:** add

**Section:** AI Leverage And Organizations

Enterprise AI transformation should start by mapping end-to-end workflows, ROI, data layers, and tribal knowledge around existing systems; rip-and-replace migrations often slow adoption more than they help.

**Core concepts**

- Start by mapping end-to-end workflows and per-workflow ROI
- Don't rip-and-replace existing systems; it slows adoption

**Assigned evidence IDs**

- `rw:01kskr0rbgy1rkw3y1gq9jw55g`
- `rw:01kskr18czcpb0gsrgex1jn5qc`
- `rw:01kskr1kaf1k792d3t6q8xj596`

**Source excerpts**

- How to Transform a Company With AI: “You should map every workflow, figure out what the ROI of an agent would be in each particular workflow and how to approach it from an engineering perspective, then choose where to deploy the agents where they'd be a good fit.”
- How to Transform a Company With AI: “Don't force massive migrations. Most companies have already spent years moving onto systems like Salesforce and NetSuite.”
- How to Transform a Company With AI: “In most workflows, the data that powers the transformation falls into four categories: the system of record, the business rules, the raw intake data, and the feedback or memory the agent accumulates over time.”

### W11-03

**Operation:** add

**Section:** Agentic Software

Reliable agent harnesses should not treat bash or arbitrary code execution as universally necessary; many enterprise tasks are better served by task-specific, constrained tools than by a model with general computer access.

**Core concepts**

- Bash / arbitrary code execution isn't universally necessary in agent harnesses
- Constrained, task-specific tools serve many enterprise tasks better

**Assigned evidence IDs**

- `rw:01kskq8p9jv6843n8xhktvc31b`
- `reader-note:01kp70dfsh9taejhdym1d5qm4a`
- `reader-note:01kqctk7cvpm01de2a4dbxn9hf`

**Source excerpts**

- The Anatomy of an Agent Harness: “Harnesses ship with a bash tool so models can solve problems autonomously by writing & executing code.”
- The Anatomy of an Agent Harness: “This frames a harness as being something design to solve lots of kinds of problems and bash + code helps. I think lots of problems don't need and shouldn't have bash + code.”
- What is an Agent Harness: “when you want something reliable in enterprise you don't necessarily want it executing arbitrary code”

### W11-04

**Operation:** add

**Section:** Career And Work

Career choices should be judged by the compounding assets they build - skills, reputation, network, options, and operational scars - not just immediate pay, title, or brand.

**Core concepts**

- Judge career choices by the compounding assets they build
- Not by immediate pay, title, or brand

**Assigned evidence IDs**

- `rw:01ksv22qgqjrmckm733rhy3br4`
- `rw:01ksv259vfm1xwns6ksyfcb3z0`
- `rw:01ksvjrngk7z25y7ygtv1cd6rv`

**Source excerpts**

- The Career Bets That Compound (And the Ones That Don't): “The networks that matter are built through work - through projects you delivered together, problems you solved together, hard situations you got through together.”
- The Career Bets That Compound (And the Ones That Don't): “stop optimizing for the next move. Start optimizing for the move after that.”
- The Career Bets That Compound (And the Ones That Don't): “Joining a great company early gives you the brand, the network, the wealth, the operational scars, and the credibility to start your own thing later.”

### W11-05

**Operation:** add

**Section:** Career And Work

High agency needs recovery and self-context, not endless escalation; because there is no final level, ambitious people should deliberately look back, accept their current state, and take breaks.

**Core concepts**

- High agency needs recovery and remembering your own context, not just always improving
- There is no final level
- Respond by pausing to reflect, accepting where you are, and taking breaks

**Assigned evidence IDs**

- `rw:01ksjznkpkmd1p430mjrnt1dfa`
- `rw:01kskp6r68fqp6eewx9v87pt8f`
- `rw:01kskp7frjqgykp69s4ja2g51q`

**Source excerpts**

- How to avoid feeling low as a high-agency person: “There is no final level of growth to be achieved. You will be a work in progress until you die. Learn to take a break.”
- How to avoid feeling low as a high-agency person: “there is no endgame to a high-agency growth mindset. The more you get ahead in life, the more levels you unlock.”
- How to avoid feeling low as a high-agency person: “Your situation, circumstances, and life are unique to you. Remember the context that surrounds you.”

### W11 not converted

- Why founder conviction matters more than ever (`rw:01ksgcr1rbdnx687dbpxcrvqe1`, highlight)
- Why founder conviction matters more than ever (`rw:01ksk6zfw8w6n8hm9w17qf6fcz`, highlight)
- Why founder conviction matters more than ever (`rw:01ksk72s17myy9345maf3w8n16`, highlight)
- Why founder conviction matters more than ever (`rw:01ksk73apxtb4e4psg1e1fbser`, highlight)
- Forward Deployed Engineering 101 (`rw:01kskdka8pn546x269sscxrjbs`, highlight)
- Forward Deployed Engineering 101 (`rw:01kskdxwnen4fmrjggtkznerh8`, highlight)
- Today we reduced headcount by 22% (`rw:01kske3vaettcj0c3jf4yarj2e`, highlight)
- Today we reduced headcount by 22% (`rw:01kske457vzf6kdrafezs7yfcf`, highlight)
- Today we reduced headcount by 22% (`rw:01kske4z05dah4p3myaacrkk16`, highlight)
- Today we reduced headcount by 22% (`rw:01kske5emtqagzs36gtxcq20qn`, highlight)
- Today we reduced headcount by 22% (`rw:01kske681vdf0k03n3x26p2pqc`, highlight)
- How to crack any job in the world (`rw:01kskndadx8jcx3nh145z5cewf`, highlight)
- Being Someone who Does Things (`rw:01kskpa1zyerk2wwwmj5z5sdnt`, highlight)
- What is an Agent Harness (`rw:01kskqk46hg9xcamg3630em7dp`, highlight)
- What is an Agent Harness (`rw:01kskqpk1dwrgfje63ggesnpmd`, highlight)
- How to Transform a Company With AI (`rw:01kskqztmnk2twgh2g0ygfydwr`, highlight)
- Attention, all you geniuses with products, but no marketing skills (`reader-summary:01ksrrvmkd2gmwnt656fxf66fr`, document_summary)
- The Career Bets That Compound (And the Ones That Don’t) (`rw:01ksv26gg8k8vr20jd8p25vq9d`, highlight)
- The Career Bets That Compound (And the Ones That Don’t) (`rw:01ksvjsb11mfv49z57byp5eb7k`, highlight)
- Is SaaS dead? (`rw:01kswcrdg0544ppn0agb1whjjw`, highlight)
- I wrote this ~3 months ago, and since then (`rw:01kszp5hzcj2y18f5gcj4vjqbq`, highlight)

## W12

### W12-01

**Operation:** update `opinion-000002`

**Section:** Agentic Software

Making code cheap to generate does not make ownership or system comprehension cheap to skip; people should understand AI-generated artifacts well enough to defend them under questioning.

**Core concepts**

- You still have to take ownership of AI-generated work — you're accountable for the artifact even when AI produced it
- Understand it well enough to defend it under questioning

**Assigned evidence IDs**

- `rw:01kt7p7hczwhjqkstr4zeqhpzx`
- `rw:01kt7p7s76qx5c04gzkw0mn0tz`

**Source excerpts**

- How AI Productivity Fails: “Hold people accountable for the artifact even when AI generated it; build pushback culture with harsh, specific feedback when output crosses into slop”
- How AI Productivity Fails: “you have to understand what you ship well enough to defend it under questioning”

### W12-02

**Operation:** add

**Section:** Agentic Software

Agentic throughput is capped by human review bandwidth, not by how many workers the UI can spawn; the right amount of parallelism is the work you can actually evaluate without surrendering standards.

**Core concepts**

- Throughput is capped by human review bandwidth, not by how many agents you can spawn
- Right parallelism = what you can actually review without dropping standards

**Assigned evidence IDs**

- `rw:01kt868v6vctcfvazfy805hpmn`
- `rw:01kt86bmyk96v9fbg4z9g1a945`

**Source excerpts**

- The Orchestration Tax: “optimizing the non bottleneck part doesn't increase throughput. You just grow the pile of unfinished work sitting in front of the bottleneck.”
- The Orchestration Tax: “The right number of parallel agents is how many you can actually code review properly. For most of us this is a low single digit.”

### W12-03

**Operation:** add

**Section:** Taste, Craft, And Signal

Use agents to remove routine work that does not benefit from synchronous involvement, but stay deliberately in the loop where taste develops and original work needs you shaping it rather than just approving it.

**Core concepts**

- Hand agents the routine work that doesn't need you synchronously
- Stay deliberately in the loop where taste develops and original work happens
- Shaping the work, not just approving it

**Assigned evidence IDs**

- `rw:01ktd4kw43j7714py2smmacmpt`

**Source excerpts**

- Escape from agentic loop: “Some of the day I want to be deeply, deliberately in the loop, because that is where taste develops and where original work happens - the kind that has my fingerprints on it, not just my approval.”

### W12 not converted

- How AI Productivity Fails (`rw:01kt7p4cbmezxk8726nep3e0bp`, highlight)
- On mid-career satisfaction (`rw:01kt7vycxyn55bjcfqv5f1cc3n`, highlight)
- The Death of the Three-Act Playbook (`rw:01kt7w2ts4mye7fk3x5zzammd1`, highlight)
- How I Run an AI Agency Solo (No Employees, $40k MRR) (`reader-note:01ktafn2y96395c7w34zbm3swh`, highlight)

## W13

### W13-01

**Operation:** add

**Section:** Agentic Software

A good vertical agent is a faithful compression of its task distribution: common capabilities belong in fast, always-loaded prompt context, rarer capabilities belong in discoverable tiers, and complete underlying references should remain searchable for the rare cases the curated layers do not cover.

**Core concepts**

- A good vertical agent is a faithful compression of its task distribution
- Common capabilities: always loaded, instant
- Rarer capabilities: discoverable on demand
- Complete references stay searchable for the rare uncovered cases

**Assigned evidence IDs**

- `rw:01ktzkwnv9j8qwz0pe54r15dyr`
- `rw:01ktzkxkv9845tfj42wc7qegbb`
- `rw:01ktzm06bzb7fb6g4j2g639n96`

**Source excerpts**

- Building a Good Vertical Agent: “I've spent almost a year now building the Shortcut agent, which is widely considered the most accurate spreadsheet agent around”
- Building a Good Vertical Agent: “a good agent is a faithful compression of its task distribution.”
- Building a Good Vertical Agent: “Almost every optimization trades compression of information against speed of discovery. Put something in L1 and it's instant, but it costs prompt tokens on every single task whether it's used or not. Push it to L3 and it costs nothing until needed - but then it costs several tool calls to find.”
- Building a Good Vertical Agent: “The compression in those system prompts and curated specs is really an encoding of the distribution of your users and the tasks they do”

### W13-02

**Operation:** add

**Section:** Agentic Software

Agentic optimization is only as good as its loss function: if the target, constraints, and instruments leave cheap paths open, the agent will exploit them instead of getting genuinely better.

**Core concepts**

- Agentic optimization is only as good as its loss function
- Cheap paths left open get exploited instead of producing genuine improvement
- The loss function needs a clear target, constraints, and instruments

**Assigned evidence IDs**

- `rw:01kv16ca95y0hhdjhnxqf1zfzh`

**Source excerpts**

- /goal + Loss Functions: How to Distill a Product in 30 Hours with One Prompt [Full Playbook]: “Every cheap path you don't fence off is a direction the optimizer will sprint down.”

### W13-03

**Operation:** add

**Section:** Agentic Software

Building new software is learning under uncertainty; the right move is to expose the unknown parts to valuable feedback quickly, whether from CI, teammates, users, customers, or your own use.

**Core concepts**

- Building new software is learning under uncertainty
- Get the unknown parts in front of valuable feedback fast

**Assigned evidence IDs**

- `rw:01kts5rs2pw3jm9emexfz68dv8`

**Source excerpts**

- Building Software Is Learning: “Because building new software is learning! If you're building something new and you don't yet fully know how exactly it's supposed to work, you will learn what exactly it is that you're building as you're doing it.”
- Building Software Is Learning: “the most important thing you can do when you're building something new: reducing the time it takes you to go from "let me try something" to getting your ass whooped by reality.”
- Building Software Is Learning: “Feedback comes in all shapes and sizes: feedback from the CI system on main, feedback from colleagues, feedback from users, feedback from you once you actually use it.”
- Building Software Is Learning: “as soon as possible, as often as possible, ship things on which we can get feedback on, in a way that gives us valuable feedback - by CI, by production, by our teammates, by select users, by select customers, by all of our users.”

### W13-04

**Operation:** add

**Section:** Moats And Strategy

Anything you can put on a leaderboard you can train against, so anything measurable is already on its way to commodity; durable value moves toward complex, private work that cannot be easily measured or copied.

**Core concepts**

- Anything you can put on a leaderboard can be trained against
- So measurable work is already on its way to commodity
- Durable value moves to complex, private work that's hard to measure or copy

**Assigned evidence IDs**

- `rw:01ktzm222bgxfw5cfbpdapyaet`

**Source excerpts**

- The Untrainable: “anything you can put on a leaderboard, you can train against, so anything measurable is already on its way to commodity.”

### W13-05

**Operation:** add

**Section:** Agentic Software

For AI products, private eval sets and real user edge cases can be more durable than the product artifact because they define quality against failure modes competitors cannot see.

**Core concepts**

- AI products have private eval sets and real user edge cases
- Those private evaluation assets can be more durable than the product artifact
- They define quality against failure modes competitors cannot see

**Assigned evidence IDs**

- `rw:01kv1xmg4addxx1z2p41kz4jbh`

**Source excerpts**

- /goal + Loss Functions: How to Distill a Product in 30 Hours with One Prompt [Full Playbook]: “For the entire history of software, "we built it" was the moat. That era is closing. The next one belongs to whoever owns what the artifact never contained: the eval set nobody else can score against. The list of edge cases your users actually trip on. The ground truth you measure privately.”

### W13 not converted

- Every Agentic Engineering Hack I Know (June 2026) (`rw:01ktmenvxzd3w7rhtwfkqaxf7j`, highlight)
- Loop Engineering. (`rw:01ktse1fcnfwy4xndhqyeq9b4f`, highlight)
- What's That Smell in San Francisco? (`rw:01ktw0jffgva6kgmj64ts00kjw`, highlight)
- I wrote this ~3 months ago, and since then (`reader-note:01ksxmgsd5k9982t94yj7appsz`, highlight)
- /goal + Loss Functions: How to Distill a Product in 30 Hours with One Prompt [Full Playbook] (`rw:01kv1x5hr6jvdszvnvn7zgx4p7`, highlight)
