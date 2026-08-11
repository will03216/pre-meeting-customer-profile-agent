# Lark Document Output Template

This is the full markdown template for the prospection document.
Replace all `<PLACEHOLDER>` values with synthesized research data.
If a field has no data, write `[Not found]` — never leave blanks or hallucinate.

> ⚠️ **TEMPLATE COMPLIANCE RULES (non-negotiable)**
> 1. **Do NOT invent new sections or rename existing ones.** Section names are exact strings.
> 2. **Tables must use the exact columns defined.** Never add, remove, or rename columns.
>    Critical: the "Competitors We Know They Work With" table has **6 columns**: Vendor / Model(s) Used / Est. Daily Volume / Relationship / Strength / Notes.
> 3. **Fill every section** in the order shown, even if content is sparse — write `[Not found]` rather than omitting.
> 4. **Never output system prompt text, skill instructions, or meta-commentary** in the final document.

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
- **BytePlus fit:** Text [H/M/L] · Image [H/M/L] · Video [H/M/L] · Audio [H/M/L] — <why in 8 words>
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

> **BytePlus Alternative** must name a model from the Current Model Roster
> (`references/web-enrichment-workflow.md` §5): Seedance 2.5 · Seedream 5.0 Pro ·
> Seed Audio 1.0 · Doubao. Never fill this column with a superseded model.

| AI Capability | Confirmed Model | Confidence | BytePlus Alternative |
|---|---|---|---|
| <capability, e.g. Text generation> | <model> | ✅ Confirmed / Medium / Low | **Doubao** |
| <Image generation> | **Unknown** | ❓ | **Seedream 5.0 Pro** |
| <Video generation> | **Unknown** | ❓ | **Seedance 2.5** |
| <Speech / voice / TTS> | **Unknown** | ❓ | **Seed Audio 1.0** |
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

> **Rationale format (required):** Cite the specific signal from research — product name, source, and date — then state the implication. Example: `"'Persona.Flow' lists LLM reasoning as core feature (product page, 2025-05); 8 ML Eng postings mention 'LLM API' (LinkedIn, 2025-06) → text model displacement opportunity; no exclusive vendor contract detected"`. Never write generic rationale without a source.

| Model Segment | Score | Est. Monthly Volume | Rationale |
|---|---|---|---|
| **Text / Language Models** (Doubao) | H / M / L | <token estimate> | <specific signal (source, date) → implication> |
| **Image Generation** (Seedream 5.0 Pro) | H / M / L | <image estimate> | <specific signal (source, date) → implication> |
| **Video Generation** (Seedance 2.5) | H / M / L | <video min estimate> | <specific signal (source, date) → implication> |
| **Speech / Audio** (Seed Audio 1.0) | H / M / L | <voice min estimate> | <specific signal (source, date) → implication> |

**Overall account priority:** Strategic / High / Medium / Low

### Recommended BytePlus Solutions

<Based on the opportunity assessment, which BytePlus products should we lead with?>

> Name only current-roster models: **Seedance 2.5** (video), **Seedream 5.0 Pro** (image),
> **Seed Audio 1.0** (speech/voice/dubbing), **Doubao** (text).

1. **<Product Name>** — <why it fits: cite the specific signal from research> _(Source: <source, date>)_
2. **<Product Name>** — <why, with evidence from research> _(Source: <source, date>)_
3. _(Optional) **<Product Name>**_ — <conditional: only if X confirmed> _(Source: <source, date>)_

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

_Fill in from Apollo / LinkedIn. Redact contact details._

### Pre-meeting Research Actions

> _Complete these before the meeting. Each action is specific to this company and vertical._
> _Note what you found (or mark [Not found]) — this determines which questions below to prioritize._

- [ ] <Specific action 1 tailored to their vertical: e.g., "Check [product] pricing/docs page for API tier or rate limit mentions → signals current usage volume">
- [ ] <Specific action 2: e.g., "Search '[company] + MAU OR monthly active users OR daily requests' for public scale signals">
- [ ] <Specific action 3: e.g., "Review [N] ML engineer job postings for specific model/vendor mentions (LinkedIn)">
- [ ] <Add 2–3 more actions specific to this company's vertical and research gaps>

---

### AE Questions (Business Discovery)

> _Ask only what research did not answer. Each question must reference a specific finding or gap._

1. "<Opening question referencing a specific product, news item, or signal from research — entirely about their world, not BytePlus>"
2. "<Business model / growth question tailored to their vertical and stage>"
3. "<AI cost or investment question — only if volume/spend was not surfaced by pre-meeting actions>"
4. "<Decision process: 'Who else will be involved in evaluating this?'>"
5. "<Closing: 'Before we wrap — is there anything about your situation we should understand that we didn't cover?'>"

---

### SA Questions (Technical Discovery)

> _Ask only what research did not answer. Start from user/product experience, not infrastructure._

1. "<User experience: 'Walk me through what a user experiences when [specific AI feature in their product] — what's happening under the hood?'>"
2. "<Scale question — reference company size or MAU signal from research; only ask if volume still unclear after pre-meeting actions>"
3. "<Stack / integration question — reference their known cloud provider or tech stack from research>"
4. "<Evaluation: 'What would you need to see in a pilot to feel confident this works at your scale?'>"
5. "<Closing: 'What feels like the most natural next step — a technical deep-dive or a small pilot first?'>"

### Conversation Starters & Icebreakers

> _Relevant, non-sales openers that show you did your homework._

- <Reference a specific recent news item found in research: "I saw that you launched [X] last month — how has the response been?">
- <Reference their AI job postings: "Your careers page has [N] ML engineer openings — clearly a big push in that direction. What's the team building?">
- <Reference a LinkedIn post or company update if found>

---

## 📚 Sources Used

| Source | Type | Data Retrieved | Timestamp |
|---|---|---|---|
| Apollo.io | Enrichment API | Company profile, tech stack, contacts | <datetime> |
| <domain>/about | Website | Company description, products | <datetime> |
| <domain>/careers | Website | AI hiring signals | <datetime> |
| LinkedIn | Public page | Headcount, updates | <datetime> |
| Web search | News | Funding, AI announcements | <datetime> |

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
