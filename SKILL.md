---
name: polym-customer-prospect
version: 0.1.0
description: "Customer prospection for pre-meeting prep. Inputs: company name, company URL, contact name (all optional — missing info is never a hard blocker). Runs 4 parallel intelligence agents (Apollo, web enrichment, AI-news search, competitive scan), synthesises findings, scores BytePlus model opportunity, generates tailored AE/SA meeting questions, and writes a Lark prospection doc."
metadata:
  requires:
    bins: ["lark-cli"]
---

# polym-customer-prospect — Customer Prospection Skill

> **Depends on:** `lark-cli` (Lark doc creation)
> **Recommended env:** `APOLLO_API_KEY` (skill degrades gracefully without it)  ·  **Optional env:** `PROSPECTS_FOLDER_TOKEN`

## 1. When to Use This Skill

### 1.1 Trigger Scenarios

- "help me prepare for a customer meeting with Acme Corp"
- "prospect this company: example.com"
- "做一个客户调研 / 会前准备"
- "给我生成一个 customer profile: [company name]"
- "I have a call with [contact] from [company], help me prepare"

### 1.2 What This Skill Does NOT Do

- Does NOT replace real conversations — it primes them
- Does NOT write sensitive contract amounts to wiki (desensitize)
- Does NOT hallucinate data — every field is sourced or marked `[Not found]`

---

## 2. Input Parameters

| Parameter | Required | Notes |
|-----------|----------|-------|
| `customer_name` | No | The contact person's name (e.g., "Zhang Wei") |
| `company_name` | No | The company name (e.g., "Acme Corp") |
| `company_url` | No | The company domain or URL (e.g., "acme.com") |
| `sa_name` | No | SA's Lark display name for wiki attribution; infer from memory or ask |
| `meeting_date` | No | Upcoming meeting date; used for doc title |

**Missing-input protocol:**
- If `company_url` missing but `company_name` given → WebSearch to infer URL
- If `company_name` missing but `company_url` given → extract from website
- If both missing but `customer_name` given → LinkedIn search for their employer
- If all missing → ask the user for at least one identifier before proceeding
- `sa_name` → check memory; if not found, ask once then save to memory

---

## 3. Architecture Overview

```
Input (name / URL / contact)
         │
         ▼
Phase 0: Resolve & normalize inputs
         │
         ▼
Phase 1: ┌──────────────────────────────────────────────────────┐
PARALLEL │ Agent A  Apollo enrichment                           │
         │ Agent B  Company website + domain scrape             │
         │ Agent C  AI news + LinkedIn + funding search         │
         │ Agent D  Competitive intelligence scan               │
         └──────────────────────────────────────────────────────┘
         │
         ▼
Phase 2: Synthesis — merge, fill gaps, mark unknowns
         │
         ▼
Phase 3: BytePlus opportunity scoring (text / image / video / audio)
         │
         ▼
Phase 4: Generate tailored AE + SA meeting questions
         │
         ▼
Phase 5: Write Lark prospection document (always)
         │
         ▼
Return Lark doc URL to user
```

---

## 3.5 Phase −1 — Pre-flight Checks

Run **before Phase 0**. Blocking checks must pass before proceeding; optional checks skip gracefully.

### Check 1 — lark-cli (BLOCKING)

```bash
lark-cli --version 2>/dev/null || echo "NOT_INSTALLED"
lark-cli auth status          # no flags needed — already emits JSON; never pass --as (rejected on auth)
```

Read `identities.user.status` from the output: `ready` (or `needs_refresh`, which auto-refreshes
on the next call) means authenticated.

**If lark-cli is not installed** (`command not found` / exit 127) → this is an *install* gap that
the auth flow cannot fix. Fetch the official installation guide and follow the steps for the
user's OS, then verify with `lark-cli --version` and return to the check above:

```
help me to install CLI：https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md
```

Installation may need user approval (package manager / sudo / download) — surface the exact
commands the user has to run; never assume success silently.

**If installed but not authenticated** → run:

```bash
lark-cli auth login --domain docs,drive,wiki
```

`auth login` needs a scope selector — `--domain docs,drive,wiki` covers what this skill uses;
`--recommend` requests only the auto-approved set. **`--as` is not a valid flag on any `auth`
subcommand** — it selects identity on resource commands (`docs +fetch --as user`) only.
Verified against lark-cli 1.0.85.
For the non-blocking agent flow (`--no-wait` → show QR → `--device-code`), see
`polym-customer-one-pager` SKILL.md §0.

**If installed and authenticated → proceed.**

---

### Check 2 — Apollo API Key (NON-BLOCKING)

Apollo adds company size, revenue, tech stack and the org-chart signal. It makes the profile
much richer — but it is **never a reason to stop the run**. Agents B, C and D do not touch
Apollo and must always proceed.

```bash
[ -n "$APOLLO_API_KEY" ] && echo "SET" || echo "NOT_SET"
```

**If set — verify it works, without blocking on the result:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://api.apollo.io/api/v1/organizations/enrich" \
  -H "Content-Type: application/json" -H "X-Api-Key: $APOLLO_API_KEY" \
  -d '{"domain":"stripe.com"}'    # expect 200
```

| Result | Action |
|---|---|
| `200` | Run Agent A normally. |
| `401` / any non-200 | Agent A becomes a no-op. Tell the user once: *"Apollo key looks invalid (HTTP `<code>`) — continuing without Apollo enrichment."* Then **proceed with Agents B/C/D.** |
| Not set | Agent A becomes a no-op. Tell the user once: *"APOLLO_API_KEY is not set — continuing without Apollo enrichment. To enable it: `export APOLLO_API_KEY=<your-key>`, then reopen the terminal."* Then **proceed with Agents B/C/D.** |

**Never stop the pipeline over Apollo.** When Agent A is a no-op, record
`[Apollo: skipped — <reason>]` in the Sources section and carry that into Phase 2 (see the
degradation rules there).

---

## 4. Phase 0 — Input Parsing & Config

```bash
# Apollo key (optional — empty means Agent A is skipped, the run still proceeds)
APOLLO_KEY="${APOLLO_API_KEY:-}"

# Check Lark folder for prospection docs
PROSPECTS_FOLDER="${PROSPECTS_FOLDER_TOKEN:-}"
# If empty, docs will be created in root My Drive

# Normalize company URL (strip protocol/path, keep domain)
# e.g. "https://www.acme.com/about" → "acme.com"
DOMAIN=$(echo "$company_url" | sed 's|https\?://||;s|www\.||;s|/.*||')

# If company_url not given, infer domain via WebSearch:
# query: "<company_name> official website"
# Extract first plausible result domain
```

---

## 5. Phase 1 — Parallel Intelligence Gathering

**CRITICAL: Launch all 4 agents in a single `Agent(...)` batch (same message).** Do not run sequentially.

### Agent A — Apollo Organization + People Enrichment

See [`references/apollo-workflow.md`](references/apollo-workflow.md) for full API details.

**Auth: the API key MUST go in the `X-Api-Key` header.** Passing `api_key` in the request body is rejected with `422 INVALID_API_KEY_LOCATION`.

```bash
# Organization enrichment
curl -s -X POST "https://api.apollo.io/api/v1/organizations/enrich" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $APOLLO_KEY" \
  -H "Cache-Control: no-cache" \
  -d "{\"domain\": \"$DOMAIN\"}"

# People/contacts at the company (focus: CTO, Head of AI, Engineering VP, Procurement)
# NOTE: endpoint is mixed_people/api_search — the old mixed_people/search returns 422 (deprecated).
# NOTE: the domain filter param is q_organization_domains_list. Using organization_domains
#       is SILENTLY IGNORED and returns people from unrelated companies.
curl -s -X POST "https://api.apollo.io/api/v1/mixed_people/api_search" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $APOLLO_KEY" \
  -d "{
    \"q_organization_domains_list\": [\"$DOMAIN\"],
    \"person_titles\": [\"CTO\",\"Chief AI Officer\",\"VP Engineering\",\"Head of AI\",\"ML Lead\",\"Procurement\"],
    \"page\": 1,
    \"per_page\": 10
  }"
```

**Sanity check the people response before using it:** every returned person's `organization.name` must match the target company. If `total_entries` is in the thousands, the domain filter did not apply — discard the result rather than writing unrelated contacts into the doc.

**Extract from Apollo response:**
- Company size (employees), revenue estimate, industry, founded year, HQ location
- Technology stack (`technology_names` field — critical for AI tool detection; the older
  `technologies` field is no longer returned and will silently read as empty)
- LinkedIn URL, Twitter, Crunchbase
- Key contacts: title + `first_name` (see masking note below)
- Funding info if available

**Contact masking:** on most API tiers the people search returns `name`, `last_name`,
`linkedin_url`, `seniority` and `email` as `null` — only `title`, `first_name` and the
`has_email` / `has_direct_phone` booleans are populated. Treat Apollo contacts as a
*title-distribution signal* (who exists in the org chart), not as a named contact list.
Named decision-makers must come from Agent B/C via public LinkedIn pages.

**If `APOLLO_KEY` is empty, or a call fails at runtime:** skip this agent, note `[Apollo: skipped — <reason>]` in the Sources section, and let the other agents finish. Do not stop the run and do not retry more than once.

---

### Agent B — Company Website + Domain Enrichment

```python
# Step 1: Fetch homepage
WebFetch(url=f"https://{domain}", max_length=20000)

# Step 2: Fetch /about, /company, /team pages (try in parallel)
WebFetch(url=f"https://{domain}/about")
WebFetch(url=f"https://{domain}/company")
WebFetch(url=f"https://{domain}/team")

# Step 3: Check for AI/tech mentions in careers page (signals active AI investment)
WebFetch(url=f"https://{domain}/careers")
```

**Extract:**
- Core business description (what they do)
- Target customers / markets
- Key products or services
- Any AI/ML mentions on the homepage
- Job postings mentioning AI/LLM/ML (signals investment level)
- Pricing page hints (B2B vs B2C, scale signals)

---

### Agent C — AI News, LinkedIn & Funding Search

Run these **WebSearch** queries in parallel:

```python
searches = [
  # AI tool usage
  f'"{company_name}" AI OR "large language model" OR LLM OR "machine learning" OR GPT OR Claude OR Gemini',

  # LinkedIn company page (public)
  f'site:linkedin.com/company "{company_name}"',

  # Recent news (funding, product, headcount)
  f'"{company_name}" (funding OR "Series" OR IPO OR acquisition OR layoff OR headcount) 2024 OR 2025 OR 2026',

  # AI news specifically
  f'"{company_name}" (AI OR model OR "machine learning") news 2025 OR 2026',

  # MAU / scale metrics (often in press releases or earnings)
  f'"{company_name}" (MAU OR "monthly active" OR users OR revenue OR "annual recurring") 2024 OR 2025',

  # Third-party AI provider usage (critical: are they using a reseller of our models?)
  f'"{company_name}" (OpenAI OR Anthropic OR "Google Vertex" OR "AWS Bedrock" OR "Azure OpenAI" OR Cohere OR Mistral OR "BytePlus" OR "Volcengine" OR "Doubao")',
]
```

**Extract:**
- AI tools and models currently in use
- Any mention of third-party AI platform (AWS Bedrock, Azure OpenAI, etc.) — these may resell our models
- Recent AI-related announcements or partnerships
- LinkedIn: employee count, recent updates, key people
- Funding rounds and amounts (keep ranges, not exact if sensitive)
- MAU / scale signals

---

### Agent D — Competitive Intelligence Scan

```python
searches = [
  # Which BytePlus competitors have a relationship with this customer?
  f'"{company_name}" (Runway OR "Pika" OR "Stable Diffusion" OR Midjourney OR "Adobe Firefly" OR "Kling" OR "Sora")',
  f'"{company_name}" (OpenAI OR Anthropic OR Cohere OR "AI21" OR Mistral OR "Llama" OR Gemini)',
  f'"{company_name}" (AWS OR Azure OR "Google Cloud" OR Alibaba OR "Huawei Cloud" OR Tencent) AI',

  # Product reviews mentioning AI vendors
  f'site:g2.com OR site:capterra.com "{company_name}"',

  # Tech blog posts from the company (self-reported stack)
  f'site:{domain} (AI OR model OR LLM OR "machine learning" OR inference)',
  f'site:medium.com OR site:dev.to OR site:engineering.{domain} "{company_name}" AI',
]
```

**Extract:**
- Confirmed competitor relationships (strong signal = case study, blog post, integration)
- Suspected competitor usage (medium signal = job posting mentioning tool, conference talk)
- **Specific model used** — not just vendor but model version (e.g., GPT-4o vs GPT-4o-mini, Claude 3.5 Sonnet vs Haiku, Gemini 1.5 Pro vs Flash)
- **Estimated daily volume** — look for: requests/day, images/day, videos/day, token counts, MAU × session depth, API pricing tier mentions, "serving X million" in press releases or job postings. Use ranges if uncertain (e.g., "~1–5M tokens/day"). Mark `[Not found]` if no signal.
- Competitor positioning vs BytePlus for this customer's use case
- Any vendor lock-in signals (multi-year contract, deep SDK integration, credits committed)

**BytePlus competitor reference map** (see [`references/web-enrichment-workflow.md`](references/web-enrichment-workflow.md) §4):

| Segment | Key Competitors |
|---------|----------------|
| Text / LLM | OpenAI GPT-4o, Anthropic Claude, Google Gemini, Meta Llama, Mistral, Cohere |
| Image generation | Midjourney, Stable Diffusion, DALL-E 3, Adobe Firefly, Ideogram |
| Video generation | Runway ML, Pika Labs, Sora (OpenAI), Google Veo, Kling (Kuaishou) |
| Cloud AI platforms | AWS Bedrock, Azure OpenAI Service, Google Vertex AI, Alibaba Cloud, Huawei Cloud |

---

## 6. Phase 2 — Synthesis

> **LANGUAGE RULE (non-negotiable): The final prospection document MUST be written entirely in English — all section titles, table content, narrative text, meeting questions, and bullet points. The only exception is quoted company names, brand names, or proper nouns that are inherently non-English (e.g., "火山引擎" → "Volcengine / 火山引擎"). The user's conversation language does NOT affect the output language.**

After all 4 agents return, merge into a unified profile. Rules:

1. **Conflict resolution** (for company facts): Apollo data > Website > Web search. When Apollo is unavailable, Website becomes the primary source.
2. **Gap marking**: Any field with no data across all sources → write `[Not found]`. Never hallucinate.
3. **Confidence scoring**: For each key claim, note source in parentheses: `(Apollo)`, `(Website)`, `(LinkedIn)`, `(Web search)`.
4. **Dedup**: If multiple sources say the same thing, cite the most authoritative.
5. **AI usage flagging**: If any source mentions a competitor's AI product → flag prominently in Competitive Landscape section.
6. **Third-party reseller check**: If customer uses AWS Bedrock / Azure OpenAI / Google Vertex → note "may already access our models via [platform]; confirm which models".
7. **Apollo-skipped degradation**: When Agent A was a no-op, still produce the full document. Specifically:
   - Company size / revenue / founded year / funding → fill from Website and Web search, else `[Not found]`.
   - The Apollo-derived tech-stack signal is gone → build the AI Stack section from the careers page, engineering blog and news signals only, and lower every affected confidence to `Low` or `Medium`.
   - Contacts → derive from public LinkedIn pages via Agent C; do not leave the section empty.
   - Add one line at the top of the Sources section: `[Apollo: skipped — <reason>] — company firmographics and tech-stack confidence are reduced.`
   - Opportunity scores are still produced, but note in the rationale where the evidence is thinner than usual.

---

## 7. Phase 3 — BytePlus Opportunity Scoring

Score each model segment **High / Medium / Low** with rationale. See scoring rubric in [`references/web-enrichment-workflow.md`](references/web-enrichment-workflow.md) §5.

**Which model to name:** always take the model name from the **Current Model Roster** table at
the top of [`references/web-enrichment-workflow.md`](references/web-enrichment-workflow.md) §5 —
currently **Seedance 2.5** (video), **Seedream 5.0 Pro** (image), **Seed Audio 1.0** (speech/audio),
**Doubao** (text). Never lead with a superseded model.

**Quick heuristics:**

| Signal | Text/LLM | Image | Video | Audio |
|--------|-----------|-------|-------|-------|
| Customer service / support platform | High | Low | Low | High |
| E-commerce / retail | Medium | High | High | Medium |
| Media / content / entertainment | Medium | Medium | High | High |
| Gaming | Low | High | High | High |
| Fintech / banking | High | Low | Low | Medium |
| Healthcare | High | Low | Low | Medium |
| Marketing / advertising | High | High | High | High |
| SaaS / developer tools | High | Low | Low | Low |
| Education / EdTech | High | Medium | Medium | High |
| Active AI product (LLM API buyer) | High | Medium | Low | Medium |
| Multi-language product or localisation effort | Medium | Low | Medium | High |
| Job postings for ML/AI roles | +1 level across all | | | |
| Recent AI funding round | +1 level across all | | | |
| Confirmed competitor usage | note lock-in risk | | | |

**Volume estimate** (monthly tokens / images / video minutes / voice minutes) — use company size + industry as proxy:
- < 100 employees → seed / early: Low volume
- 100–1000 employees → growth: Medium volume
- 1000+ employees, consumer product → High volume
- Add LinkedIn headcount trend (growing = higher volume trajectory)

**Rationale writing rule:** Each rationale cell must cite the specific evidence found in research — product name, source, and date. Format: `<signal> (<source>, <date>) → <implication>`. Never write a generic inference without a source.
- ✅ GOOD: `"Product 'X' homepage lists 'LLM reasoning' as core feature (website, 2025-05); 8 ML Eng job postings mention 'LLM API' (LinkedIn, 2025-06) → text model displacement opportunity; no exclusive vendor confirmed"`
- ❌ BAD: `"AEO services need LLMs; Doubao could serve non-Google workflows"`

The same sourcing rule applies to **Recommended BytePlus Solutions**: every recommendation must cite the specific signal or product finding that justifies it, with source.

---

## 8. Phase 4 — Meeting Question Generation

Based on synthesis findings, select and adapt questions from [`references/meeting-questions-bank.md`](references/meeting-questions-bank.md).

### Core Principle: Consultative Arc, Not Interrogation

Questions must follow the **5-step consultative arc** from the questions bank:
① Context anchor → ② Challenge surface → ③ Strategy probe → ④ Implication → ⑤ Natural bridge

**Never lead with the product.** The goal is to guide the customer to articulate their own pain,
so BytePlus solutions emerge as the obvious answer — not as a pitch.

### Selection Logic

**Step 1 — Identify the primary business model tag from research:**
- Subscription/SaaS → use `[SUBSCRIPTION]` arc
- E-commerce / catalog-heavy → use `[ECOMMERCE]` arc
- Media / content / gaming → use `[MEDIA]` arc
- Marketing / agency → use `[MARKETING-AD]` arc
- Hardware/integrator/reseller → use `[CHANNEL-PARTNER]` arc
- Large org with formal procurement → add `[ENTERPRISE]` overlay

**Step 2 — Layer situation-specific follow-ups:**
- AI stack unknown → add `[AI-UNKNOWN]` probes
- Competitor detected → add `[COMPETITOR-PRESENT]` questions (frame neutrally, not aggressively)
- Image/video/text/audio opportunity scored High → add the corresponding `[IMAGE-OPP]`/`[VIDEO-OPP]`/`[TEXT-OPP]`/`[AUDIO-OPP]` probes

**Step 3 — Output format (non-negotiable):**

The Meeting Preparation section in the Lark doc must follow this structure, in this order:

**Block 1 — Pre-meeting Research Actions** (3–6 items, vertical-specific)
Actions the SA/AE completes *before* the meeting — things resolvable without being in the room.
Format: `- [ ] <specific action> → [finding or Not found]`
Actions must be tailored to this company's vertical and the gaps left after Phase 1–2.
Examples by vertical:
- AI tools company: `[ ] Check product docs / pricing page for API tier or rate limit mentions → signals current usage volume`
- E-commerce: `[ ] Count active product categories on catalog page → signals PDP content scale`
- Media/gaming: `[ ] Search "[company] + content production OR AI pipeline" on engineering blog`
- Any: `[ ] Search "[company] + MAU OR monthly active OR daily requests" for public scale signals`

**Block 2 — AE Questions** (3–5 items)
Only questions that the pre-meeting research did NOT answer.
Numbered list. No arc labels (① ② ③). No "Why ask" or "Purpose" annotations.
Each question must reference a specific finding or gap from research.

**Block 3 — SA Questions** (3–5 items)
Only questions that the pre-meeting research did NOT answer.
Numbered list. No "Why ask" or "Purpose" annotations.
Start from user/product experience, not infrastructure.

**Block 4 — Conversation Starters** (2–3 items)
Non-sales openers referencing specific findings: recent news, product launch, ML job postings.

**Step 4 — Question specificity rule:**
Every question and action must be specific to this company. If it could apply to any company in any industry, rewrite it.
- ❌ NEVER: "Are you using any AI tools?" / "What are your AI goals?"
- ✅ ALWAYS: "Your careers page has [exact N from research] ML engineer openings — what's that team building?" (cite the count found)
- ✅ ALWAYS: "You launched [Product X found in research] in [month] — has AI cost become a real line item since then?"

**Never write "Why ask" or "Purpose" annotations in the output document.**

**Questions to avoid:** never open with the product, never ask for budget directly in the first 10 minutes, never ask "are you aware of BytePlus?"

---

## 9. Phase 5 — Write Lark Prospection Document

### 9.1 Create the document

```bash
# Title format: "Prospect · <Company> · <YYYY-MM-DD>"
DOC_TITLE="Prospect · $COMPANY_NAME · $(date +%Y-%m-%d)"

# Step 1: write content to a file in the current working directory (lark-cli requires relative paths)
cat > ./prospect_content.md << 'EOF'
<filled template>
EOF

# Step 2: create the document
# MUST pass --api-version v2. The v1 interface is shut down, and v1-only flags are rejected:
#   --markdown       → use --content with --doc-format markdown
#   --folder-token   → use --parent-token
lark-cli docs +create \
  --api-version v2 \
  --title "$DOC_TITLE" \
  ${PROSPECTS_FOLDER:+--parent-token "$PROSPECTS_FOLDER"} \
  --content "@prospect_content.md" \
  --doc-format markdown \
  --as user
# → returns doc_id (doc_token) and doc_url

# Step 3: if content is too large for +create, overwrite after creation.
# Note: v2 uses --command overwrite, not --mode overwrite (v1-only, rejected).
lark-cli docs +update \
  --api-version v2 \
  --doc "<doc_id_from_create>" \
  --command overwrite \
  --content "@prospect_content.md" \
  --doc-format markdown \
  --as user

rm ./prospect_content.md
```

### 9.2 Language requirement

**ALL document content must be in English.** This applies regardless of what language the user spoke during the session. Section headers, table content, narrative paragraphs, meeting questions, bullet points — everything in English. Brand names and proper nouns keep their original form (e.g., company names, product names).

### 9.3 Document sections (in order)

1. **Header callout** — Quick-glance metadata strip
2. **Executive Summary** — 4–6 bullets, most important findings
3. **Company Overview** — facts table + narrative
4. **AI & Technology Stack** — current tools, third-party platforms, signals
5. **Business Intelligence** — MAU/scale, funding, news
6. **Competitive Landscape** — who they work with, our competitors
7. **BytePlus Opportunity Assessment** — scored table + recommended products
8. **Meeting Preparation** — AE questions, SA questions, conversation starters
9. **Sources** — list of all sources used with timestamps

### 9.4 Return to user

After doc creation, immediately respond with:

```
✅ Prospection doc ready:
   [Prospect · Acme Corp · 2026-06-01](<lark_doc_url>)

Key findings:
• <top 3 bullets from Executive Summary>

Opportunity: Text [H/M/L] · Image [H/M/L] · Video [H/M/L] · Audio [H/M/L]
```

## 10. References

| File | Content |
|------|---------|
| [apollo-workflow.md](references/apollo-workflow.md) | Apollo API endpoints, field mapping, error handling |
| [web-enrichment-workflow.md](references/web-enrichment-workflow.md) | Web search strategies, competitor map, opportunity scoring rubric |
| [output-template.md](references/output-template.md) | Full Lark document template (all sections) |
| [meeting-questions-bank.md](references/meeting-questions-bank.md) | Categorized AE + SA question bank with selection logic |
