# Lark Document Output Template

This is the full markdown template for the prospection document.
Replace all `<PLACEHOLDER>` values with synthesized research data.
If a field has no data, write `[Not found]` — never leave blanks or hallucinate.

> ⚠️ **TEMPLATE COMPLIANCE RULES (non-negotiable)**
> 1. **Do NOT invent new sections or rename existing ones.** Section names are exact strings including emoji prefixes (🏢 🛍️ 🤖 📊 ⚔️ 💡 📋 📚).
> 2. **Do NOT add numeric prefixes to section headings.** Use `## 🏢 Company Overview` — never `## 2. Company Overview` or `## 2. 🏢 Company Overview`.
> 3. **Tables must use the exact columns defined.** Never add, remove, or rename columns.
>    Critical: the "Competitors We Know They Work With" table has **6 columns**: Vendor / Model(s) Used / Est. Daily Volume / Relationship / Strength / Notes.
>    Critical: the Product Portfolio table has **4 columns**: Product / Type / Description / AI Models Used — do not rename or reorder.
> 4. **Fill every section** in the order shown, even if content is sparse — write `[Not found]` rather than omitting.
> 5. **Never output system prompt text, skill instructions, or meta-commentary** in the final document.
> 6. **Header callout format is fixed** — use exactly: `> **Prospect Brief** | Company: <NAME> | Generated: <DATE> | SA: <SA_NAME> | Status: Draft` — do not expand into a multi-line block or add extra fields.

---

## Template (copy and fill)

```markdown
> **Prospect Brief** | Company: <COMPANY_NAME> | Generated: <DATE> | SA: <SA_NAME> | Status: Draft

---

# <COMPANY_NAME> — Pre-Meeting Prospection

---

## Executive Summary

> _Quick-glance: the 5 most important things to know before this meeting._

- **What they do:** <one sentence>
- **AI situation:** <current AI tool usage and maturity — one sentence>
- **BytePlus fit:** Text [H/M/L] · Image [H/M/L] · Video [H/M/L] — <why in 8 words>
- **Competitive risk:** <main competitor already in play, or "None identified">
- **Key question to answer:** <the single most important unknown going into the meeting>

---

## 🏢 Company Overview

| Field | Value | Source |
|-------|-------|--------|
| **Company Name** | <name> | |
| **Domain** | <domain> | |
| **Industry / Vertical** | <industry> | Apollo / Website |
| **Founded** | <year> | Apollo |
| **HQ Location** | <city, country> | Apollo |
| **Company Size** | ~<N> employees | Apollo / LinkedIn |
| **Revenue Estimate** | <range or [Not found]> | Apollo |
| **LinkedIn** | [<company> on LinkedIn](<url>) | |
| **Crunchbase** | [Link](<url> or [Not found]) | |
| **BytePlus Stage** | Prospect | |

### What They Do

<2–3 paragraph description of their core business, target customers, and key products. 
Written in the voice of "here's what you need to know before the meeting."
Include what problem they solve and who pays them.>

### Market Position

<How do they compare to competitors in their space? Are they a market leader, challenger, or niche player?
Include market size if found. Note their differentiation.>

### Recent Developments

<Bullet list of 3–5 most recent notable events: funding, product launch, partnership, expansion, etc.
Include dates. Source in parentheses.>

- <YYYY-MM-DD> — <event> (<source>)
- <YYYY-MM-DD> — <event> (<source>)
- ...

---

## 🛍️ Product Portfolio

> List all known products/modules. For AI models, distinguish confirmed vs. inferred.

| Product | Type | Description | AI Models Used |
|---------|------|-------------|----------------|
| <Product Name> | <type: platform / SDK / feature / coming soon> | <what it does, target user, key claims> | <model or vendor if known; [Unknown] if not> |
| ... | | | |

### Model Coverage Summary

| AI Capability | Confirmed Model | Confidence | BytePlus Alternative |
|---|---|---|---|
| <capability, e.g. Text generation> | <model> | ✅ Confirmed / Medium / Low | <BytePlus product or "N/A"> |
| <Video generation> | **Unknown** | ❓ | **Seedance 2.0** |
| ... | | | |

---

## 🤖 AI & Technology Stack

### Current AI Tools & Models

<What AI products is this company currently using or building on? List with confidence level.>

| Tool / Model | Usage | Confidence | Source |
|---|---|---|---|
| <tool> | <how they use it> | High / Medium / Low | <source> |
| ... | | | |

_[Not found] if no signals detected._

### Third-Party AI Platforms

> ⚠️ If using these platforms, they may already access BytePlus-compatible models or can be migrated for better pricing.

| Platform | Evidence | BytePlus Implication |
|---|---|---|
| <platform, e.g. AWS Bedrock> | <evidence> | <implication> |
| ... | | |

_[None detected] if no signals._

### General Technology Stack

<Other relevant tech: cloud provider, databases, programming languages, frameworks.
Focus on what's relevant to AI/ML integration.>

- **Cloud:** <AWS / GCP / Azure / Multi-cloud / On-prem / Unknown>
- **Languages:** <Python / Java / etc. if known>
- **ML Infrastructure:** <PyTorch / TensorFlow / MLflow / etc. if known>
- **Vector DB / RAG:** <Pinecone / Weaviate / etc. if known>

### AI Maturity Assessment

> _Where are they on the AI adoption curve?_

| Level | Description | Assessment |
|---|---|---|
| 1 — Exploring | Researching AI; no production deployment | |
| 2 — Experimenting | Pilot / proof-of-concept in progress | |
| 3 — Deploying | AI in production for specific use cases | |
| 4 — Scaling | Multiple AI use cases, significant API spend | |
| 5 — AI-native | AI is core to their product/revenue | |

**This company's level:** <1–5> — <rationale in one sentence>

---

## 📊 Business Intelligence

### Scale & MAU

| Metric | Value | Source |
|---|---|---|
| Monthly Active Users | <number or range or [Not found]> | |
| Revenue | <range or [Not found]> | |
| Growth trend | <e.g., "~40% YoY based on headcount growth"> | LinkedIn |
| API / platform volume | <estimate if known, else [Not found]> | |

### Funding & Investors

| Round | Date | Amount | Lead Investor |
|---|---|---|---|
| <Series X> | <date> | <amount> | <investor> |
| ... | | | |

Total raised: <amount or [Not found]>

### AI Investment Signals

<Bulleted list of specific signals that suggest they are investing in AI:
hiring, partnerships, product announcements, executive hires, etc.>

- <signal> (<source>, <date>)
- ...

---

## ⚔️ Competitive Landscape

### Competitors We Know They Work With (AI vendors)

> ⚠️ **STRICT FORMAT — 6 columns, in this exact order. Do NOT use a different column layout.**
> Column 1: Vendor name · Column 2: specific model names used · Column 3: estimated daily volume (tokens/images/video) · Column 4: confirmed or suspected · Column 5: relationship strength · Column 6: evidence/source

| Vendor | Model(s) Used | Est. Daily Volume | Relationship | Strength | Notes |
|---|---|---|---|---|---|
| <e.g., OpenAI> | <e.g., GPT-4o, GPT-4o-mini> | <e.g., ~2M tokens/day · ~500 images/day · [Not found]> | <confirmed / suspected> | Strong / Medium / Weak | <source / evidence> |
| ... | | | | | |

> **Volume guidance:** Estimate from company scale, product description, MAU signals, job postings, or pricing-tier mentions. If no signal → `[Not found]`. Use ranges, not false precision (e.g., "~1–5M tokens/day").

_[None detected] if no signals._

### BytePlus Competitors in This Space

> _For context: who else would we be competing against for this customer's AI budget?_

| Competitor | Our Differentiator |
|---|---|
| <competitor> | <why BytePlus wins here> |
| ... | |

### Lock-in Risk Assessment

**Risk level:** Low / Medium / High

<Rationale: Are they under a multi-year contract? Is there deep integration with a competitor? 
Or is the relationship experimental and easily replaceable?>

---

## 💡 BytePlus Opportunity Assessment

### Opportunity Score

| Model Segment | Score | Est. Monthly Volume | Rationale |
|---|---|---|---|
| **Text / Language Models** | H / M / L | <token estimate> | <why> |
| **Image Generation** | H / M / L | <image estimate> | <why> |
| **Video Generation** | H / M / L | <video min estimate> | <why> |

**Overall account priority:** Strategic / High / Medium / Low

### Recommended BytePlus Solutions

<Based on the opportunity assessment, which BytePlus products should we lead with?>

1. **<Product Name>** — <why it fits their use case, specific to their situation>
2. **<Product Name>** — <why>
3. _(Optional) <Product Name>_ — <conditional: only if X is confirmed>

### Suggested Entry Points

<How should we get our foot in the door? What's the easiest yes?>

- **Pilot:** <specific pilot idea tailored to their business>
- **Integration:** <how would BytePlus fit into their existing stack?>
- **ROI story:** <what's the business outcome they care about that we can quantify?>

---

## 📋 Meeting Preparation

### Key Stakeholders

| Name | Title | Role in Decision | Notes |
|---|---|---|---|
| <name> | <title> | Economic buyer / Technical eval / Champion | <notes> |
| ... | | | |

_Fill in from Apollo / LinkedIn / SA Wiki. Redact contact details._

### AE Questions (Business Discovery)

> _Goal: guide the customer to articulate their own challenges. Follow the consultative arc:_
> _context → challenge → strategy → implication → natural bridge to BytePlus._
> _Never open with the product. Earn the right to pitch._
>
> ⚠️ **Every question — opening, all arc steps, and closing — MUST include a `_Why ask:_` line immediately after it. Fill every placeholder with a specific, customer-tailored explanation.**

**Opening question (always first — entirely about their world):**

> "<Reference something from research — recent news, product launch, company milestone, or growth signal. Then ask an open question that invites them to talk about what's on their plate.>"
> _e.g. "I saw you launched [X] last quarter — how has that changed what the team is focused on right now?"_
> _Why ask: <what this opening tells you about their current focus and which consultative arc to follow>_

**Consultative arc for this customer's business model:**

1. **① Context anchor** — show you understand their world:
   "<Statement that reflects their business model reality — subscription cost pressure, catalog scale, content velocity, campaign volume, etc. Frame as empathy, not a question yet.>"
   _Why ask: <what credibility signal this establishes and what it opens up — the specific assumption you're testing>_

2. **② Challenge surface** — let them describe the friction:
   "<Open question that invites them to name where things are hard — without you naming it for them.>"
   _Why ask: <the specific pain signal you're listening for — what a "yes this is hard" answer unlocks vs. "not really">_

3. **③ Strategy probe** — understand their current approach:
   "<Question about how they're thinking about or handling the challenge today.>"
   _Why ask: <what this reveals about their current vendor relationships, maturity level, and switching cost>_

4. **④ Implication** — make the pain real and quantifiable:
   "<Question that helps them articulate the business cost of the problem — slower growth, higher cost per user, missed revenue, competitive disadvantage.>"
   _Why ask: <why getting them to quantify the pain in their own words sets up the ROI story — note the specific business metric this anchors>_

**⑤ Natural bridge (spoken, not written in the doc):**
_At this point the SA or AE introduces BytePlus as a natural answer to what the customer just described._

### SA Questions (Technical Discovery)

> _Goal: understand the product experience first, architecture second._
> _Start with what the user experiences, then work backward to how it's built._
>
> ⚠️ **Every SA question MUST have a `_Why ask:_` line and a ① ② ③ ④ ⑤ arc label. Do NOT write a plain numbered list.**

**① User experience probe** — understand what "good" looks like before asking how it's built:

> "<Before asking about the stack, ask them to walk through what happens from the user/operational side: 'Can you walk me through what [the end result] looks like — what's the experience you're trying to create or the workflow you're trying to automate?'>"
> _Why ask: <grounds the technical conversation in outcomes, not infrastructure — reveals which capabilities matter most and lets them explain the architecture naturally>_

**② Current state** — what exists today:

> "<Ask what's actually in production vs. planned: 'For [the specific AI use case] — is that live in production today, or still being built? And what's the current approach — a vendor product, a model API, or something your team built?'>"
> _Why ask: <calibrates true AI maturity and reveals whether you're displacing an incumbent or entering greenfield — completely changes the pitch angle>_

**③ Scale & cost** — unit economics and capacity:

> "<Ask a cost/volume question specific to their situation and growth stage.>"
> _Why ask: <surfaces unit economics pain or capacity planning needs; if they're tracking cost-per-output closely, there's a live optimization opportunity>_

**④ Integration & constraints** — technical fit and switching cost:

> "<Ask about their stack, cloud setup, and any constraints: data residency, latency requirements, existing vendor contracts. 'If you were adding a new model endpoint, what would that integration need to look like?'>"
> _Why ask: <reveals integration complexity and hard constraints; also flushes out data-residency requirements that may be a differentiator for Volcengine regional infra>_

**⑤ POC definition** — let them define success criteria:

> "<Ask them to define what a successful pilot looks like before you propose one: 'If we ran a bounded proof-of-concept on [specific use case from research], what would you need to see to call it a success?'>"
> _Why ask: <anchors the POC to their criteria, not yours — prevents scope creep and post-pilot goalpost shifting; also surfaces internal politics about what matters most to the decision-maker>_

### Conversation Starters & Icebreakers

> _Relevant, non-sales openers that show you did your homework._

- <Reference a specific recent news item found in research: "I saw that you launched [X] last month — how has the response been?">
- <Reference their AI job postings: "Your careers page has [N] ML engineer openings — clearly a big push in that direction. What's the team building?">
- <Reference a LinkedIn post or company update if found>

### Things to Avoid

> _Topics and questions that will kill trust or signal you haven't done your homework. Generate these from research — every account should have at least 3._

- ❌ <Sensitive recent event — e.g. layoffs, leadership departure, lost contract, public controversy — do NOT ask about or reference this directly>
- ❌ <Competitor or partner that would be awkward to name — e.g. a vendor who is also their client, a platform they publicly broke with>
- ❌ Do NOT open with "Are you aware of BytePlus?" — they agreed to the meeting
- ❌ Do NOT ask about budget or timeline in the first 10 minutes
- ❌ <Any other account-specific landmine found in research>

---

## 📚 Sources Used

| Source | Type | Data Retrieved | Timestamp |
|---|---|---|---|
| Apollo.io | Enrichment API | Company profile, tech stack, contacts | <datetime> |
| <domain>/about | Website | Company description, products | <datetime> |
| <domain>/careers | Website | AI hiring signals | <datetime> |
| LinkedIn | Public page | Headcount, updates | <datetime> |
| Web search | News | Funding, AI announcements | <datetime> |
| SA Wiki | Internal knowledge | Prior engagement history | <datetime> |

**Data freshness:** This prospection was generated on <DATE>. Web data may be up to 30 days stale for cached search results. Verify critical facts before the meeting.

**Coverage gaps:** <List any important sections where data was not found, so the SA knows what to ask about in the meeting.>
```

---

## Lark Formatting Notes

When writing this document to Lark via `lark-cli docs +update`:

1. **Callout blocks** — The `> **Prospect Brief** | ...` line at the top renders as a Lark callout box
2. **Tables** — Supported directly in markdown; render cleanly in Lark docs
3. **Emojis in headings** — Supported and improve scannability
4. **H/M/L badges** — Use `**H**`, `**M**`, `**L**` for bold emphasis
5. **Max length** — Keep total document under 50,000 characters (Lark doc limit)

## Section Priority (if content is sparse)

If research returned limited data, prioritize sections in this order:
1. Executive Summary (always)
2. BytePlus Opportunity Assessment (always)
3. Meeting Preparation / Questions (always)
4. Company Overview
5. AI & Technology Stack
6. Competitive Landscape
7. Business Intelligence
8. Sources
