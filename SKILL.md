---
name: polym-customer-prospect
version: 0.1.0
description: "Customer prospection for pre-meeting prep. Inputs: company name, company URL, contact name (all optional — missing info is never a hard blocker). Runs 5 parallel intelligence agents (Apollo, web enrichment, AI-news search, competitive scan, SA Wiki), synthesises findings, scores BytePlus model opportunity, generates tailored AE/SA meeting questions, writes a Lark prospection doc, and archives to SA Wiki."
metadata:
  requires:
    bins: ["lark-cli"]
---

# polym-customer-prospect — Customer Prospection Skill

> **Depends on:** `lark-cli` (Lark doc creation + wiki queries — all wiki access is inlined, no external skill required)
> **Optional env:** `APOLLO_API_KEY` · `PROSPECTS_FOLDER_TOKEN`

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
         │ Agent E  SA Wiki existing knowledge                  │
         └──────────────────────────────────────────────────────┘
         │
         ▼
Phase 2: Synthesis — merge, fill gaps, mark unknowns
         │
         ▼
Phase 3: BytePlus opportunity scoring (text / image / video)
         │
         ▼
Phase 4: Generate tailored AE + SA meeting questions
         │
         ▼
Phase 5: Write Lark prospection document (always)
         │
         ▼
Return Lark doc URL to user
         │
         ▼
Phase 6: Ask user — archive summary to SA Wiki write_queue? (optional — wait for confirmation)
```

---

## 4. Phase 0 — Input Parsing & Config

```bash
# Check Apollo key
APOLLO_KEY="${APOLLO_API_KEY:-}"
[ -z "$APOLLO_KEY" ] && echo "[WARN] APOLLO_API_KEY not set — Apollo enrichment will be skipped"

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

**CRITICAL: Launch all 5 agents in a single `Agent(...)` batch (same message).** Do not run sequentially.

### Agent A — Apollo Organization + People Enrichment

See [`references/apollo-workflow.md`](references/apollo-workflow.md) for full API details.

```bash
# Organization enrichment — API key in header (required by Apollo v2)
curl -s -X POST "https://api.apollo.io/api/v1/organizations/enrich" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $APOLLO_KEY" \
  -H "Cache-Control: no-cache" \
  -d "{\"domain\": \"$DOMAIN\"}"

# People/contacts at the company (focus: CTO, Head of AI, Engineering VP, Procurement)
curl -s -X POST "https://api.apollo.io/api/v1/mixed_people/search" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $APOLLO_KEY" \
  -d "{
    \"organization_domains\": [\"$DOMAIN\"],
    \"person_titles\": [\"CTO\",\"Chief AI Officer\",\"VP Engineering\",\"Head of AI\",\"ML Lead\",\"Procurement\"],
    \"page\": 1,
    \"per_page\": 10
  }"
```

**Extract from Apollo response:**
- Company size (employees), revenue estimate, industry, founded year, HQ location
- Technology stack (`technologies` field — critical for AI tool detection)
- LinkedIn URL, Twitter, Crunchbase
- Key contacts: name, title, LinkedIn, email (redact email in wiki write)
- Funding info if available

**If `APOLLO_KEY` is empty:** skip this agent, note `[Apollo: skipped — API key not configured]` in output.

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

# --- Industry-vertical override ---
# For media / broadcast / sports / entertainment companies, the relevant AI competitive
# landscape is NOT consumer generative AI (Runway / Midjourney / OpenAI) but
# broadcast-specific production tools. Detect industry first, then add vertical searches.

industry_lower = industry.lower()  # from Phase 0 synthesis (Apollo/Website)

if any(kw in industry_lower for kw in [
    "media", "broadcast", "television", "tv", "film", "entertainment",
    "sports", "production", "studio", "streaming", "news", "radio", "publishing"
]):
    searches += [
      # Sports highlight / clip automation
      f'"{company_name}" ("WSC Sports" OR Grabyo OR Deltatre OR "Pixellot" OR "Stats Perform" OR "Second Spectrum")',

      # Cloud production & asset management AI
      f'"{company_name}" (Blackbird OR Veritone OR "Imagen" OR "Limecraft" OR "Cognizin" OR "Dalet" OR "Avid" OR "Grass Valley")',

      # Broadcast real-time graphics & data viz AI
      f'"{company_name}" (Vizrt OR "Ross Video" OR ChyronHego OR "Singular" OR "Brainstorm" OR "Flowics")',

      # Post-production AI (editing, colour, audio)
      f'"{company_name}" ("DaVinci Resolve" OR "Adobe Premiere" OR "Frame.io" OR "Topaz" OR "Mocha" OR "Assimilate" OR "Cinedeck")',

      # Virtual advertising & AR overlay (sports-specific)
      f'"{company_name}" ("Hawk-Eye" OR "Supponor" OR "Invisible" OR "StadiumAI" OR "TGI Sport" OR "Sportcast" OR "Repucom")',

      # Conference / trade press signals (IBC, NAB, ISE are primary broadcast AI venues)
      f'"{company_name}" (IBC OR NAB OR ISE OR "Broadcast Beat" OR "TVBEurope" OR "Broadcast Magazine") AI OR "machine learning" OR "generative"',
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
| **Media/Broadcast (vertical)** | WSC Sports, Grabyo, Deltatre, Pixellot, Vizrt, Ross Video, ChyronHego, Veritone, Blackbird, Dalet, Avid AI, Supponor, Hawk-Eye, Second Spectrum |

---

### Agent E — SA Wiki Existing Knowledge

Query the SA Wiki directly using lark-cli. **Do NOT call any external skill — all wiki access is self-contained here.**

```bash
# SA Wiki constants (hardcoded — no external skill needed)
BASE_TOKEN="UXPdbPJ3kaheZvs2Nc8lLGCcglh"
KI_TABLE="tblLKeA8N3ipyEQv"        # knowledge_index
VIEW_CUSTOMERS="vewFNHm7XG"        # customers view

# Step 0: Refresh token FIRST — run this before every lark-cli call to avoid 99991668
FRESH_TOKEN=$(curl -sX GET "https://mira.byteintl.net/mira/openapi/v1/auth/session/uat/signed" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$MIRA_CURRENT_USERID\",\"user_sign\":\"$MIRA_USER_SIGN\"}" \
  | jq -r '.data.user_access_token')
# Use FRESH_TOKEN inline with every lark-cli call below (same shell invocation)

# Step 1: Search knowledge_index for the company
X_Mira_User_Access_Token="$FRESH_TOKEN" lark-cli base +record-search \
  --base-token $BASE_TOKEN --table-id $KI_TABLE \
  --json "{\"keyword\":\"$company_name\",\"search_fields\":[\"Title\",\"Summary\",\"Keywords\",\"Customer\"],\"page_size\":10}" \
  --format json --as user

# Step 2: If hits found — fetch PROFILE and TIMELINE docs (use same FRESH_TOKEN)
X_Mira_User_Access_Token="$FRESH_TOKEN" lark-cli docs +fetch --api-version v2 --doc <profile_doc_token> --as user
X_Mira_User_Access_Token="$FRESH_TOKEN" lark-cli docs +fetch --api-version v2 --doc <timeline_doc_token> --as user

# Step 3: Browse customers view directly
X_Mira_User_Access_Token="$FRESH_TOKEN" lark-cli base +record-list \
  --base-token $BASE_TOKEN --table-id $KI_TABLE \
  --view-id $VIEW_CUSTOMERS --limit 50 --format json --as user

# Step 4: Search Lark messages for recent internal discussions
X_Mira_User_Access_Token="$FRESH_TOKEN" lark-cli im +messages-search \
  --query "$company_name" --count 20 --as user
```

**ALWAYS attempt these commands** — Mira has lark-cli built-in. The token refresh (Step 0) must run first every time; passing `FRESH_TOKEN` inline keeps it in scope for that shell invocation. If Step 0 fails (MIRA_CURRENT_USERID or MIRA_USER_SIGN not set), note `[SA Wiki: skipped — token refresh env vars missing]` and continue.

**Extract:**
- Prior engagement history (meetings, POC status, issues)
- Known contacts at the customer
- Previous BytePlus proposals or demos
- Outstanding issues or blockers
- SA team's current assessment of the relationship

---

## 6. Phase 2 — Synthesis

> **LANGUAGE RULE (non-negotiable): The final prospection document MUST be written entirely in English — all section titles, table content, narrative text, meeting questions, and bullet points. The only exception is quoted company names, brand names, or proper nouns that are inherently non-English (e.g., "火山引擎" → "Volcengine / 火山引擎"). The user's conversation language does NOT affect the output language.**

After all 5 agents return, merge into a unified profile. Rules:

1. **Conflict resolution**: Apollo data > Website > Web search > Wiki (for company facts). Wiki > all for engagement history.
2. **Gap marking**: Any field with no data across all sources → write `[Not found]`. Never hallucinate.
3. **Confidence scoring**: For each key claim, note source in parentheses: `(Apollo)`, `(Website)`, `(LinkedIn)`, `(Web search)`, `(SA Wiki)`.
4. **Dedup**: If multiple sources say the same thing, cite the most authoritative.
5. **AI usage flagging**: If any source mentions a competitor's AI product → flag prominently in Competitive Landscape section.
6. **Third-party reseller check**: If customer uses AWS Bedrock / Azure OpenAI / Google Vertex → note "may already access our models via [platform]; confirm which models".
7. **Strategic ownership signal detection**: Scan investor / parent company data for any of the following signals. If found, tag the synthesis result with `[STRATEGIC-OWNERSHIP: <reason>]` — this tag MUST be carried through to Phase 3 scoring, the Executive Summary, and the Opportunity Assessment sections.

   | Signal | Tag reason |
   |---|---|
   | Chinese company holds ≥10% equity (e.g. SouthWind, Tencent, Alibaba, IDG, Hillhouse, Sequoia China, CITIC) | "Chinese majority/minority investor — procurement chain receptive to Chinese-origin tech vendors; BytePlus/Volcengine internal approval friction lower" |
   | ByteDance or any ByteDance portfolio company is a parent/investor | "ByteDance ecosystem — existing internal relationship pathway; may already use Volcengine products" |
   | Company is a subsidiary of an existing Volcengine/BytePlus customer | "Parent already a BytePlus customer — framework agreement may extend" |
   | Company is actively expanding into APAC / China market | "APAC expansion — Seedance/Seedream APAC aesthetic and Volcengine regional infra are direct differentiators" |
   | Chinese PE/VC holds ≥10% (even if company is Western) | "Chinese capital alignment — decision-makers familiar with Chinese tech ecosystem" |

---

## 7. Phase 3 — BytePlus Opportunity Scoring

Score each model segment **High / Medium / Low** with rationale. See scoring rubric in [`references/web-enrichment-workflow.md`](references/web-enrichment-workflow.md) §5.

**Quick heuristics:**

| Signal | Text/LLM | Image | Video |
|--------|-----------|-------|-------|
| Customer service / support platform | High | Low | Low |
| E-commerce / retail | Medium | High | High |
| Media / content / entertainment | Medium | Medium | High |
| Gaming | Low | High | High |
| Fintech / banking | High | Low | Low |
| Healthcare | High | Low | Low |
| Marketing / advertising | High | High | High |
| SaaS / developer tools | High | Low | Low |
| Education / EdTech | High | Medium | Medium |
| Active AI product (LLM API buyer) | High | Medium | Low |
| Job postings for ML/AI roles | +1 level across all | | |
| Recent AI funding round | +1 level across all | | |
| Confirmed competitor usage | note lock-in risk | | |
| `[STRATEGIC-OWNERSHIP]` tag from Phase 2 | +1 level across all + add "Strategic: [ownership reason]" note to Rationale column | | |

**Volume estimate — ALWAYS fill this column, even without direct data.** Use company size + industry as proxy. Never leave blank or write "N/A".

| Company size | Text/LLM tokens (monthly) | Images (monthly) | Video (monthly) |
|---|---|---|---|
| < 100 employees | ~1–10M tokens | ~5–50K images | ~100–500 video-min |
| 100–500 employees | ~10–100M tokens | ~50K–500K images | ~500–5K video-min |
| 500–2,000 employees | ~100M–1B tokens | ~500K–5M images | ~5K–50K video-min |
| 2,000+ employees, B2B SaaS | ~500M–5B tokens | ~1M–10M images | ~10K–100K video-min |
| 2,000+ employees, consumer product | ~1B–50B tokens | ~5M–100M images | ~50K–1M video-min |

- **Use ranges, not single numbers** (e.g., "~10–100M tokens/mo")
- If direct data found (MAU × avg session depth, pricing tier, press release): use that and note the source
- If only company size known: use the proxy table above and annotate `(est.)`
- If video or image doesn't apply to their business: write `[N/A — not applicable]`
- Add LinkedIn headcount trend: fast-growing company → use the upper end of the range

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
- Image/video/text opportunity scored High → add the corresponding `[IMAGE-OPP]`/`[VIDEO-OPP]`/`[TEXT-OPP]` probes
- `[STRATEGIC-OWNERSHIP]` tag present → **fold** one ownership-probe question into the existing ③ Strategy probe step (do NOT create a new section or add it outside the arc). Blend it naturally: after asking how they're handling the current challenge, follow with something like "Does [parent company] have a preferred technology-vendor ecosystem, or any guidance on partnerships that flows down to the operating units?" Frame as governance curiosity. It stays inside the arc — do not break out a separate "Strategic-ownership probe" block.

**Step 3 — Always include:**
- 1 opening question that is entirely about their world, not BytePlus
- 2–3 AE business questions following the arc for their business model
- 3–5 SA technical questions starting from user experience, not architecture
- 2 closing questions (always the same — surface hidden context + co-create next step)

**Step 3a — `_Why ask:_` annotation is MANDATORY on every single question. No exceptions.**

After each AE and SA question, write one line in italics:
> _Why ask: <explain the strategic signal you're listening for, or what this answer unlocks>_

Rules:
- AE questions: explain the business intelligence the answer provides (e.g., "Tells us whether this is a cost story or a growth story — shapes the entire pitch angle")
- SA questions: explain what technical signal or architecture insight you're probing for (e.g., "Reveals whether they already have caching in place — if not, that's an easy quick win to offer")
- The "Why ask:" must be specific to THIS customer's situation — not a generic description of the question's purpose
- The closing questions also need "Why ask:" lines

Format example:
```
**② Challenge surface:**
> "As you've scaled your AI features, has the cost per active user been something your team is actively watching, or is it still too early to see?"
> _Why ask: Opens the unit-economics conversation without asking about budget. If they say "we're watching it closely," we have a live pain point — if "not yet," we plant the seed for when it becomes one._
```

**Step 4 — Make every question specific.** Reference something found in research:
- Generic (BAD): "Are you using any AI tools?"
- Generic (BAD): "What are your AI goals?"
- Specific (GOOD): "Your careers page has 12 ML engineer openings — I'm curious what that team is building. Is that for a new product feature, or scaling something already in production?"
- Specific (GOOD): "You launched [product] six months ago. As that's ramped up, has the AI cost structure started to become a real line item, or is usage still light enough that it's not on the radar yet?"

**Questions to avoid:** See "Questions to Avoid" section in the bank — especially: never open with the product, never ask for budget directly in the first 10 minutes, never ask "are you aware of BytePlus?"

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
lark-cli docs +create \
  --title "$DOC_TITLE" \
  ${PROSPECTS_FOLDER:+--folder-token "$PROSPECTS_FOLDER"} \
  --markdown "@prospect_content.md" \
  --as user
# → returns doc_id (doc_token) and doc_url

# Step 3: if content is too large for +create, use +update --mode overwrite after creation
lark-cli docs +update \
  --doc "<doc_id_from_create>" \
  --mode overwrite \
  --markdown "@prospect_content.md" \
  --as user

rm ./prospect_content.md
```

### 9.2 Language requirement

**ALL document content must be in English.** This applies regardless of what language the user spoke during the session. Section headers, table content, narrative paragraphs, meeting questions, bullet points — everything in English. Brand names and proper nouns keep their original form (e.g., company names, product names).

### 9.3 Document sections (in order)

> ⚠️ **ALL 10 sections are mandatory. Follow `references/output-template.md` exactly for column layouts and subsection structure.**

1. **Header callout** — Quick-glance metadata strip. If `[STRATEGIC-OWNERSHIP]` tag is present, include the ownership signal visibly in or immediately below the header.
2. **Executive Summary** — 4–6 bullets, most important findings. If synthesis carries a `[STRATEGIC-OWNERSHIP]` tag → add a dedicated bullet: "**Strategic relationship:** <ownership signal and BytePlus implication in one sentence>"
3. **Company Overview** — facts table + narrative + Recent Developments bullets
4. **🛍️ Product Portfolio** — product/service table + Model Coverage Summary table (MANDATORY — do not skip)
5. **AI & Technology Stack** — current tools, third-party platforms, AI Maturity Assessment
6. **Business Intelligence** — MAU/scale, funding, news, AI Investment Signals
7. **Competitive Landscape** — "Competitors We Know They Work With" table (6 columns: Vendor / Model(s) Used / Est. Daily Volume / Relationship / Strength / Notes) — Est. Daily Volume is mandatory; estimate from company scale if no direct signal, use `[Not found]` only if neither direct data nor proxy is feasible + lock-in assessment
8. **BytePlus Opportunity Assessment** — scored table (Text/Image/Video) with Est. Monthly Volume MANDATORY in every row (use Phase 3 proxy table if no direct data — never leave blank) + recommended products + suggested entry points. If synthesis carries a `[STRATEGIC-OWNERSHIP]` tag → the first Recommended Solution must explicitly name the ownership angle (e.g. "Chinese parent company alignment means BytePlus/Volcengine faces lower procurement friction than Western alternatives — lead with this in the first meeting")
9. **Meeting Preparation** — Key Stakeholders + AE consultative arc questions (① Context anchor → ② Challenge surface → ③ Strategy probe → ④ Implication → ⑤ Natural bridge; every step labeled; every question has `_Why ask:_`) + SA technical arc questions (① User experience probe → ② Current state → ③ Scale & cost → ④ Integration & constraints → ⑤ POC definition; every step labeled with ① ② ③ ④ ⑤; every question has `_Why ask:_`) + Conversation Starters & Icebreakers + **Things to Avoid** (MANDATORY — minimum 3 account-specific items; always present, never skip)
10. **Sources** — list of all sources used with timestamps + coverage gaps

### 9.4 Return to user

After doc creation, immediately respond with:

```
✅ Prospection doc ready:
   [Prospect · Acme Corp · 2026-06-01](<lark_doc_url>)

Key findings:
• <top 3 bullets from Executive Summary>

Opportunity: Text [H/M/L] · Image [H/M/L] · Video [H/M/L]
```

## 10. References

| File | Content |
|------|---------|
| [apollo-workflow.md](references/apollo-workflow.md) | Apollo API endpoints, field mapping, error handling |
| [web-enrichment-workflow.md](references/web-enrichment-workflow.md) | Web search strategies, competitor map, opportunity scoring rubric |
| [output-template.md](references/output-template.md) | Full Lark document template (all sections) |
| [meeting-questions-bank.md](references/meeting-questions-bank.md) | Categorized AE + SA question bank with selection logic |
