# Meeting Questions Bank

Categorized question bank for AE and SA to use in customer meetings.
Questions follow a **consultative flow** — start from the customer's business reality,
surface their challenges through empathy and curiosity, then let BytePlus solutions
emerge naturally from the conversation. Never lead with the product.

---

## Core Philosophy: The Consultative Arc

Every question sequence follows this 5-step arc. Not every step needs its own question —
sometimes one question covers two steps at once. The goal is to guide the customer
to articulate their own pain, so the BytePlus solution feels like the obvious answer.

```
① Context anchor    → Show you understand their world ("You're in subscription, so growth
                       and unit economics are probably the two levers everything flows from...")
② Challenge surface → Let them describe the friction ("Where have you felt that getting harder?")
③ Strategy probe    → Understand how they're thinking about it ("What's the current approach?")
④ Implication       → Make the pain real ("What happens to your unit economics when X happens?")
⑤ Natural bridge    → (SA or AE) "Something we've done for companies in a similar situation is..."
```

**Rule:** The product is never the subject of the first question in any arc. We are their advisor first.

---

## Tag Reference

- `[ALWAYS]` — include in every meeting
- `[SUBSCRIPTION]` — SaaS, streaming, membership, app subscription models
- `[ECOMMERCE]` — retail, marketplace, D2C, platforms with product catalogs
- `[MEDIA]` — content platforms, entertainment, publishing, gaming
- `[MARKETING-AD]` — agencies, brands, ad platforms, performance marketing
- `[ENTERPRISE]` — large orgs, formal procurement, multi-stakeholder decisions
- `[STARTUP-GROWTH]` — post-PMF, scaling rapidly, cost-sensitive
- `[AI-UNKNOWN]` — no AI vendor detected in research
- `[AI-KNOWN]` — we know their current AI tools
- `[COMPETITOR-PRESENT]` — competitor AI vendor usage detected
- `[IMAGE-OPP]` — research signals image generation opportunity
- `[VIDEO-OPP]` — research signals video generation opportunity
- `[TEXT-OPP]` — research signals LLM/text opportunity
- `[CHANNEL-PARTNER]` — prospect looks more like a reseller/integrator than direct buyer

---

## AE Questions — Business Discovery

### Opening: Set the Right Tone

`[ALWAYS]` _(first thing, before any pitch)_
> "Before we get into what BytePlus does — I'd love to spend the first part of this conversation just understanding what's actually on your plate. What's the thing that's taking up most of your team's energy right now?"

_Purpose: Signals you're here to help, not to sell. Disarms the guard immediately. Their answer tells you which arc to follow._

---

### For Subscription Business Customers `[SUBSCRIPTION]`

> **① Context anchor:**
> "You're in a subscription model, so I imagine user growth and retention are the two metrics everything else has to serve — and AI features probably have to earn their place by moving one of those needles."

_Purpose: Show you understand their incentive structure without asking "what's your goal."_

> **② Challenge surface:**
> "As you've added AI-powered features — recommendations, generation, personalization — have you found that the AI cost structure is something you're actively managing, or is it still in the background?"

_Purpose: Opens the cost conversation without asking directly about budget._

> **③ Strategy probe:**
> "What's the current thinking on how to handle that as you scale? Are you trying to optimize the models you're already on, setting usage caps, or exploring different pricing structures with vendors?"

_Purpose: Understand their strategy before positioning ours._

> **④ Implication:**
> "When you look at your per-user AI cost vs. the revenue that user is generating — are there features or use cases where the unit economics start looking uncomfortably thin as you grow? Like, is there a ceiling where a feature stops being viable?"

_Purpose: Make the cost-of-scale pain concrete and quantifiable._

> **⑤ Bridge (natural):**
> "That's exactly the conversation a lot of our customers hit at around [X scale]. What we typically find is that model choice and inference optimization together can bring that cost down significantly without changing the product experience. Worth seeing if that's true for your use case."

---

### For E-commerce / Retail Customers `[ECOMMERCE]`

> **① Context anchor:**
> "With a product catalog the size of yours, content production is probably one of those operational challenges that never fully goes away — there's always more SKUs, more markets, more localization to do."

_Purpose: Acknowledge their operational reality; shows you've done homework on their scale._

> **② Challenge surface:**
> "How are you handling PDP content today — is it written manually, templated, partially automated? And honestly, what does the turnaround time and cost look like when you're adding a batch of new products?"

_Purpose: Let them describe the actual workflow and its friction without you guessing._

> **③ Strategy probe:**
> "When there's a campaign or a seasonal push and you need to move fast — where does content production sit on the critical path? Is it something that slows down how quickly you can get products live?"

_Purpose: Surfaces the velocity problem and business impact._

> **④ Implication:**
> "If that bottleneck wasn't there — if content production was essentially instant — what would that unlock? Faster market expansion, better SEO coverage, more aggressive A/B testing on product pages?"

_Purpose: Let them articulate the upside, so the ROI story is their words, not yours._

> **⑤ Bridge (natural):**
> "We've built content and image generation pipelines for retailers where that went from days to hours — or for high-volume use cases, to fully automated. Worth seeing if something like that would fit how your catalog team works."

**Additional probes for e-commerce:**

`[IMAGE-OPP]`
> "For product imagery — are you generating variations (backgrounds, angles, lifestyle shots) manually today, or mostly working with a fixed shoot? What's the cost per SKU look like?"

`[TEXT-OPP]`
> "On the localization side — when you expand into a new market, how does the content workflow change? Is translation + adaptation a significant cost line?"

---

### For Media / Content / Entertainment Customers `[MEDIA]`

> **① Context anchor:**
> "Content businesses live and die on production velocity and cost — I imagine the pressure is always to produce more, at higher quality, for the same or lower budget."

> **② Challenge surface:**
> "Where does the team feel that pressure most acutely right now — is it original content production, adaptation and localization, or something like social/promotional content that's always the first thing that gets squeezed?"

_Purpose: Let them pick the pain point; don't assume which content type matters most._

> **③ Strategy probe:**
> "How are you thinking about using AI to close that gap — is there active experimentation happening, or is the team still figuring out where AI fits without disrupting existing creative workflows?"

_Purpose: Gauge AI maturity and creative team buy-in (a common blocker)._

> **④ Implication:**
> "When a piece of content takes too long to produce, what does that mean for you — missed windows, reduced publishing frequency, or having to cut scope? What's the business cost of that?"

> **⑤ Bridge:**
> "We've worked with content teams where the shift was from 'AI replaces the creator' (which nobody wanted) to 'AI handles the scale problem so the team can focus on the high-value creative decisions.' That framing tends to get a lot more buy-in internally."

`[VIDEO-OPP]`
> "For video specifically — what's the ratio of AI-generated to human-produced content in your roadmap over the next year? Is that a number leadership has talked about, or still undefined?"

---

### For Marketing / Advertising Customers `[MARKETING-AD]`

> **① Context anchor:**
> "Marketing and advertising is one of the most volume-intensive content problems I've seen — you're producing variants for every channel, audience segment, format, and market simultaneously."

> **② Challenge surface:**
> "What's the creative production bottleneck that your team talks about most? Is it the sheer number of variations needed, turnaround time on briefs, or the cost of producing quality assets at that volume?"

> **③ Strategy probe:**
> "When a client asks for 50 ad variants for a campaign — what does that workflow look like today, and where does it break down?"

_Purpose: Surfaces the specific production workflow and where AI would insert._

> **④ Implication:**
> "If you could respond to a client brief with a full suite of creative variants same-day — what would that do to your competitive positioning, or your ability to take on more clients without growing headcount?"

> **⑤ Bridge:**
> "That's the case a lot of our agency customers make internally — not 'AI reduces headcount' but 'AI lets us take on briefs we'd have had to turn down.' That's a revenue expansion story, not a cost story."

---

### For Any Customer — Strategic Discovery `[ALWAYS]`

`[ALWAYS]`
> "I want to make sure I understand the right priority here — is AI for you right now more of a growth driver (features that attract or retain users) or a cost efficiency play (doing existing things cheaper)? Or both, but which one has the leadership team's attention most?"

_Purpose: Defines the selling angle — growth story vs. cost story vs. both._

`[ALWAYS]`
> "When you think about what would make this initiative successful in 12 months — is it a business outcome you'd point to, like revenue or retention, or is it more of a technical milestone, like shipping a specific feature?"

_Purpose: Anchor to outcomes, not technology. Let them define success._

`[EARLY-STAGE]`
> "It sounds like you're still in the exploration phase — which is actually a good time to have this conversation. What's the hypothesis you're testing? What would have to be true for you to decide 'yes, this is worth building'?"

_Purpose: Calibrates expectations; shows patience; avoids pushing a sale before they're ready._

`[SCALING]`
> "You've clearly already shipped AI — what's the thing that's working really well that you want to double down on, and what's the thing that's become a headache at scale that you need to solve?"

_Purpose: Acknowledge their progress, then find the pain._

---

### Budget & Procurement (Handle Gently)

`[ALWAYS]`
> "I'm not going to ask you for a budget number — but it would help me understand the context: is AI infrastructure sitting in a dedicated budget this year, or is it coming out of engineering or product headcount budgets? Just so I know how to frame a proposal."

_Purpose: Budget signal without the uncomfortable direct ask._

`[ENTERPRISE]`
> "For something like this, what does your evaluation process typically look like — is there a security or legal review, a formal vendor assessment, or can you move more quickly on a pilot basis?"

_Purpose: Surface procurement timeline and potential blockers._

`[SCALING]`
> "Just so I understand the scale of the current spend — are we talking order of magnitude: thousands a month, tens of thousands, or more? I want to make sure the numbers we'd be discussing are actually meaningful for you."

_Purpose: Understand migration potential; frame as helping them, not sizing the deal._

---

### Decision Process

`[ALWAYS]`
> "Who else will be involved in this decision — is there a technical lead, a VP of product, or an executive who'd want to weigh in? I want to make sure we get the right people in the room when the time comes."

_Purpose: Map the buying committee without sounding pushy._

`[COMPETITOR-PRESENT]`
> "I know you're working with [competitor] on some of this already — I'm curious, not competitive: what's worked well about that relationship, and what's brought you here to have additional conversations?"

_Purpose: Neutral framing; lets them surface their own dissatisfaction without pressure._

`[COMPETITOR-ABSENT]`
> "Have you had a chance to explore other options in this space? I'm curious what your framework is for evaluating vendors — what are the things you'd weight most heavily?"

_Purpose: Understand their evaluation criteria before they use them against you._

---

## SA Questions — Technical Discovery

### Principle: Understand Before Proposing

SA questions follow the same consultative arc. Don't start with "tell me your architecture" —
start with "help me understand what you're trying to achieve."

### Opening the Technical Conversation

`[ALWAYS]`
> "Before I start asking about your tech stack — can you walk me through the user experience you're trying to create? I find it's easier to think about the right technical approach once I understand what 'good' looks like from your user's perspective."

_Purpose: Grounds the technical conversation in user outcomes, not infrastructure._

`[ALWAYS]`
> "When a user encounters an AI-powered feature in your product — what's happening under the hood? Walk me through the journey from user action to AI output."

_Purpose: Gets them to explain their architecture naturally, without it feeling like an interrogation._

### For Subscription / Growth Companies `[SUBSCRIPTION]`

> "As you've scaled user numbers, has the AI cost per user stayed roughly flat, or have you seen it creep up? What's driving that — more features per user, heavier usage per feature, or something in the model tier you're on?"

_Purpose: Maps cost scaling pattern — critical for positioning BytePlus pricing._

> "Are there features where you've had to limit usage or add paywalls specifically because of AI cost — not because you wanted to gate the feature, but because the cost didn't work at unlimited scale?"

_Purpose: Surfaces concrete unit economics pain; opens the optimization conversation._

> "What's your inference setup — are you going direct API, or do you have any caching, batching, or async processing to keep costs manageable?"

_Purpose: Understand technical sophistication and what they've already tried._

### Current Architecture `[AI-KNOWN]`

> "You're using [tool] today — I'm curious how that's working for you technically, not from a sales perspective. What are the things it handles really well, and where are you working around its limitations?"

_Purpose: Let them describe gaps organically; shows you're not threatened by competitors._

`[AI-UNKNOWN]`
> "In terms of AI in your product — is that something you're building toward, or are there already AI-driven decisions or features running in production that users interact with today?"

_Purpose: Baseline AI maturity without assuming they're further along than they are._

### Scale & Performance

`[ALWAYS]`
> "Help me understand the scale you're designing for — roughly how many model calls per day, and is that mostly real-time user-facing, or async batch processing in the background?"

_Purpose: Critical for recommending right tier; frames the question as understanding, not qualifying._

`[SCALING]`
> "What does peak traffic look like for you — is it steady-state, or are there spikes (campaigns, launches, viral moments)? How does your AI system handle that today, and where does it struggle?"

_Purpose: Opens capacity planning and autoscaling conversation._

### Infrastructure & Integration

`[ALWAYS]`
> "What cloud is your infrastructure on, and is data residency or sovereignty a factor for you — either for internal policy or because of where your users are?"

_Purpose: Compliance question framed naturally._

`[ALWAYS]`
> "How are you thinking about the privacy of what goes into model calls? If user data is in the prompt, what's your current approach to making sure that's handled appropriately?"

_Purpose: Opens BytePlus data privacy differentiator; often a real concern they haven't fully solved._

`[TEXT-OPP]`
> "For your language AI use cases — are you doing primarily generation, or is there classification, extraction, or summarization involved too? And what languages do you need to support?"

`[IMAGE-OPP]`
> "For image generation — what does the output need to look like? Product-on-white, lifestyle, UI assets, something else? And what's the throughput you'd need — per-request or batch?"

`[VIDEO-OPP]`
> "For video — is the goal generating new video from scratch, or transforming existing content (editing, style transfer, dubbing)? And what duration and resolution are you working with?"

### Evaluation & POC

`[ALWAYS]`
> "When you evaluate AI model quality for your use case — how do you do that? Is there a benchmark, a test set, or is it more of a 'I'll know it when I see it' assessment?"

_Purpose: Opens the POC conversation; defines success criteria before you start._

`[ALWAYS]`
> "If we ran a quick pilot — what would you need to see to feel confident this could work at your scale? Let's try to define that upfront so we're not flying blind."

_Purpose: Set clear POC success criteria; avoids scope creep._

`[COMPETITOR-PRESENT]`
> "If we're going head-to-head with [competitor] in an evaluation — what are the dimensions where you'd want to see us do better? I'd rather know that now so we focus the right things in the POC."

_Purpose: Direct and honest; shows confidence; surfaces the real evaluation criteria._

---

## Closing Questions `[ALWAYS]`

_(End of meeting — always)_
> "This has been really useful — before we wrap up, is there anything about your situation that you think we should understand that we didn't cover? Sometimes the most important context comes out at the end."

_Purpose: Surface hidden objections or requirements._

_(End of meeting — always)_
> "Based on what we talked about, what feels like the most natural next step to you — would it make sense to set up a technical deep-dive with your engineering team, or would a small pilot be more useful first?"

_Purpose: Co-create next steps; avoids "I'll send you a proposal" which often dies._

---

## Situation-Specific Question Sets

### Subscription SaaS `[SUBSCRIPTION]`

**AE Consultative Arc:**
1. "What's driving AI to be a priority right now — is it a competitive response, or an internal hypothesis about retention or engagement?"
2. "For the AI features you've shipped — have they moved the retention needle in a way you can measure, or is it still early to know?"
3. "As you've scaled, has the AI cost structure started to become a real line item in your unit economics, or is it still small relative to other infrastructure?"
4. "If AI cost doubled because you added a major new use case — would that be something your current pricing model absorbs, or would you need to re-evaluate the feature?"

**SA Technical Arc:**
1. "Walk me through your AI feature's architecture — where does the model call sit in your user request path?"
2. "What's your token or cost per active user per month looking like today? And is that trending up as engagement grows?"
3. "Have you done any prompt optimization, caching, or model distillation to control costs, or is it still mostly pass-through to the model API?"
4. "What would you need to see to feel comfortable switching providers — is it quality parity on a specific benchmark, or is it purely about pricing?"

### E-commerce / Retail `[ECOMMERCE]`

**AE Consultative Arc:**
1. "How big is the catalog, and roughly how much of that has PDP content you're actually happy with — complete descriptions, good imagery, localized for each market?"
2. "What does 'shipping a new product' actually require in terms of content work — how many people, how many days, and where's the bottleneck?"
3. "Are there SKUs that are underperforming on search or conversion that you think are partly a content quality problem?"
4. "If content production was essentially free and instant — what would you do with that? Launch in new markets faster? A/B test more aggressively? Something else?"

**SA Technical Arc:**
1. "For any automated content you're producing today — what does that pipeline look like? Is it template-based, or are you calling a model directly?"
2. "What's your image pipeline — where do product images go after the shoot, and what format/resolution do downstream systems need?"
3. "For moderation of AI-generated content before it goes live — do you have a review step, or are you comfortable with fully automated output?"
4. "If you were generating images at scale — thousands per day — what throughput and latency would you need? And are there brand guidelines or style references the model would need to follow?"

### Media / Content / Entertainment `[MEDIA]`

**AE Consultative Arc:**
1. "What content format is most expensive or time-consuming to produce right now — and is that the format where demand is growing fastest?"
2. "When your editorial or creative team hears 'AI-generated content,' what's the reaction? Excited, skeptical, or somewhere in the middle?"
3. "If AI could handle 80% of a content type and your team focused on the 20% that requires real human judgment — which content type would that be most valuable for?"
4. "How are you thinking about AI-generated content from a brand and quality risk perspective — do you have a review workflow for that?"

**SA Technical Arc:**
1. "What's your content pipeline today — from brief to published? Where does the most time go?"
2. "For video specifically — what's the production ratio: how many hours does it take to produce one minute of final output?"
3. "What's your current output format and resolution requirement, and do you need audio generation alongside video?"
4. "How would AI-generated content fit into your existing CMS or asset management workflow?"

### Gaming `[MEDIA]`

**AE Consultative Arc:**
1. "Where in the development pipeline does your team feel most time-pressured — environment art, character animation, NPC dialogue, or something else?"
2. "When asset production slips, does that push the release timeline or do you cut scope? What's the business cost of that?"
3. "Is AI for content generation (assets, narrative) on your roadmap, or are you more focused on AI for player experience (dynamic difficulty, NPC behavior)?"

**SA Technical Arc:**
1. "What art style does the game use — realistic, stylized, pixel art? How important is stylistic consistency across AI-generated and human-made assets?"
2. "For NPC dialogue — real-time generation or pre-generated cache? Do you need voice synthesis alongside?"
3. "What game engine and asset pipeline are you on? Where would AI generation plug in — pre-production, in-engine, or post-processing?"

### Marketing / Advertising `[MARKETING-AD]`

**AE Consultative Arc:**
1. "When a client asks for a full suite of creative variants — different formats, different audiences, different markets — what does that look like in terms of time and cost today?"
2. "Are there briefs you've had to turn down or scope down specifically because the production cost didn't work at the margin they were offering?"
3. "If you could respond to a brief with 50 high-quality variants in hours instead of days — what would that do to the size of briefs you could take on, or your competitive win rate?"

**SA Technical Arc:**
1. "What does your current creative production workflow look like at the tool level — what software, and where's the handoff between strategy, creative, and production?"
2. "For brand consistency — how would you ensure AI-generated assets stay on-brand? Style guides, reference images, or human review as the last step?"
3. "What throughput are we talking — how many creatives per campaign, per month?"

### Enterprise / Formal Procurement `[ENTERPRISE]`

**AE Consultative Arc:**
1. "For a decision of this scope, who are the stakeholders that typically need to be aligned — engineering, legal/compliance, finance, executive sponsor?"
2. "Is there an existing AI vendor on an approved vendor list that we'd be supplementing, or would we be going through a new vendor assessment?"
3. "What's the evaluation timeline — and is there a business event (product launch, budget cycle, board review) that's creating a deadline?"

**SA Technical Arc:**
1. "What's your data classification situation — what data can leave your perimeter to an external API, and what needs to stay internal or in a private cloud?"
2. "Have you done a DPIA or similar assessment for AI model usage? What came out of that?"
3. "What's your requirement for audit logs, model version pinning, and explainability?"

### Channel Partners / Resellers `[CHANNEL-PARTNER]`

**AE Consultative Arc:**
1. "You clearly have deep relationships with customers in [vertical] — are you seeing demand from them for AI-powered capabilities alongside the [current product/service]?"
2. "If you were to add an AI generation layer to what you offer — would that be as a standalone new service, or more tightly integrated into the existing offering?"
3. "What would the ideal partnership model look like for you — reselling API credits, revenue share on consumption, or a co-developed product?"

**SA Technical Arc:**
1. "What does your integration development look like — do you have an engineering team that builds on top of APIs, or would we need to provide more of a turnkey solution?"
2. "For your clients, what's the typical integration path — API direct, SDK, or embedded into a platform they're already on?"

---

## Questions to Avoid

These create friction without value — cut them:

- ❌ "Are you aware of BytePlus?" _(they agreed to the meeting)_
- ❌ "What's your budget?" _(too blunt; use the indirect version above)_
- ❌ "Why would you choose us over [competitor]?" _(sounds insecure)_
- ❌ "Can you sign by [date]?" _(no relationship yet)_
- ❌ "Have you heard of Doubao / Seedance?" _(show, don't quiz)_
- ❌ "What are your AI goals?" _(too generic; you should already know from research)_
- ❌ Opening with: "Let me tell you about BytePlus..." _(earn the right to pitch first)_
- ❌ Asking about budget or timeline in the first 10 minutes _(kills the trust arc)_
