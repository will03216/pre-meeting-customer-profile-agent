# Web Enrichment Workflow

Covers company website scraping strategy, search query templates, competitor intelligence map, and opportunity scoring rubric.

---

## §1 — Domain Inference (when URL not provided)

```python
# Try in order until one succeeds:

# 1. Direct guess (works for most)
domains_to_try = [
  f"{slug}.com",
  f"{slug}.io",
  f"{slug}.ai",
  f"{slug}.co",
]
# slug = company_name.lower().replace(" ", "").replace(",", "")

# 2. WebSearch fallback
query = f'"{company_name}" official website'
# Extract first result domain that is not LinkedIn/Crunchbase/Wikipedia
```

---

## §2 — Website Scraping Strategy

Scrape in parallel (all attempts, ignore 404s):

| URL path | What to look for |
|----------|-----------------|
| `/` (homepage) | Core value prop, product names, hero copy |
| `/about` or `/company` | Founding story, mission, target market |
| `/products` or `/solutions` | Product lineup, use cases |
| `/customers` or `/case-studies` | Customer logos (shows market segment) |
| `/pricing` | B2B/B2C signal, scale tiers |
| `/careers` or `/jobs` | Active AI/ML hiring (investment signal) |
| `/blog` or `/engineering` | Technical blog posts mentioning AI |
| `/press` or `/news` | Company announcements |

### Career page AI signal keywords

Scan job postings for these to gauge AI investment level:

```python
CAREER_AI_SIGNALS = {
  "HIGH": ["LLM", "large language model", "foundation model", "generative AI",
           "prompt engineering", "RAG", "fine-tuning", "RLHF", "model training",
           "inference infrastructure", "AI platform"],
  "MEDIUM": ["machine learning", "deep learning", "NLP", "computer vision",
             "recommendation system", "ranking", "neural network"],
  "LOW": ["data science", "analytics", "business intelligence", "A/B testing"]
}

# Scoring: HIGH hits → strong AI investment; MEDIUM → active ML; LOW → data-driven but not AI-first
```

---

## §3 — Web Search Query Templates

### AI Stack Discovery

```
"{company}" AI OR "language model" OR LLM OR ChatGPT OR Claude OR Gemini 2024 OR 2025
"{company}" "powered by" OR "built with" OR "uses" AI OR GPT OR "machine learning"
site:{domain} AI OR model OR LLM OR inference OR embedding
"{company}" "AI partnership" OR "AI integration" OR "AI-powered"
```

### Third-Party AI Platform Detection (CRITICAL)

These platforms may **resell BytePlus/Volcengine models** or be direct competitors:

```
"{company}" "AWS Bedrock" OR "Amazon Bedrock"
"{company}" "Azure OpenAI" OR "Microsoft Azure" AI
"{company}" "Google Vertex" OR "Vertex AI"
"{company}" "Alibaba Cloud" OR "Aliyun" AI
"{company}" "Huawei Cloud" OR "ModelArts"
"{company}" "Volcengine" OR "BytePlus" OR "Doubao" OR "火山引擎"
```

If any hit → note under "Third-Party AI Platforms" with the platform name and confidence level.

### LinkedIn Company Intelligence

```
site:linkedin.com/company "{company}"
"{company}" linkedin employees headcount 2025
"{company}" linkedin recent posts AI
```

Extract from public LinkedIn page:
- Employee count (and trend vs. previous)
- Recent company updates mentioning AI
- Key executives visible in public profile
- Specialties listed

### Funding & Business Scale

```
"{company}" funding OR "raised" OR "Series" site:techcrunch.com OR site:crunchbase.com OR site:venturebeat.com
"{company}" revenue OR ARR OR "annual recurring" 2024 OR 2025
"{company}" MAU OR "monthly active users" OR "daily active" OR users site:press OR site:newsroom
"{company}" IPO OR acquisition OR merger 2024 OR 2025
```

### AI News (last 12 months)

```
"{company}" AI news after:2025-01-01
"{company}" model OR generative OR "artificial intelligence" site:techcrunch.com OR site:venturebeat.com OR site:theinformation.com
"{company}" AI announcement OR launch OR partnership 2025
```

---

## §4 — BytePlus Competitor Intelligence Map

### Text / LLM Competitors

| Competitor | Signals to search for | Notes |
|---|---|---|
| OpenAI | "ChatGPT", "GPT-4", "GPT-4o", "OpenAI API" | Dominant; if using, note contract size signals |
| Anthropic | "Claude", "Claude 3", "Anthropic" | Strong in enterprise |
| Google | "Gemini", "PaLM 2", "Vertex AI" | Often bundled with GCP |
| Meta | "Llama", "Llama 3", "open source LLM" | Cost-sensitive customers |
| Mistral | "Mistral", "Mixtral" | Europe-focused |
| Cohere | "Cohere", "Command R" | Enterprise RAG |
| AI21 Labs | "Jurassic", "AI21" | Less common |

### Image Generation Competitors

| Competitor | Signals |
|---|---|
| Midjourney | "Midjourney", Discord AI art |
| Stability AI | "Stable Diffusion", "SDXL", "Stability" |
| Adobe | "Firefly", "Adobe AI" |
| DALL-E (OpenAI) | "DALL-E", "image generation OpenAI" |
| Ideogram | "Ideogram" |

### Video Generation Competitors

| Competitor | Signals |
|---|---|
| Runway ML | "Runway", "Gen-2", "Gen-3" |
| Pika Labs | "Pika", "Pika 1.0" |
| Kling (Kuaishou) | "Kling", "快手" video |
| Sora (OpenAI) | "Sora", "OpenAI video" |
| Google Veo | "Veo", "Google video generation" |
| HeyGen | "HeyGen", "AI avatar video" |
| D-ID | "D-ID", "talking head" |

### Cloud AI Platform Competitors

| Platform | Notes |
|---|---|
| AWS Bedrock | May access our models via Bedrock — confirm which |
| Azure OpenAI | Bundled with Microsoft enterprise agreements |
| Google Vertex AI | GCP customers often default here |
| Alibaba Cloud | Dominant in China; Qwen model |
| Huawei Cloud | ModelArts; APAC focus |

**Third-party reseller check:** If customer uses AWS Bedrock / Azure / Vertex, they may ALREADY be accessing BytePlus-compatible models or could be migrated to direct access for better pricing and control. Flag prominently.

---

## §5 — BytePlus Opportunity Scoring Rubric

### Current Model Roster — Single Source of Truth

**Every model recommendation in the prospection doc must name a model from this table.**
When the roster changes, edit this table only — nothing else in the skill hardcodes a model name.

| Modality | Model to recommend | Notes |
|---|---|---|
| Video generation | **Seedance 2.5** | Current flagship. Do not lead with Seedance 2.0 or earlier. |
| Image generation | **Seedream 5.0 Pro** | Current flagship. Do not lead with Seedream 4.5 / 5.0 Lite. |
| Speech / audio | **Seed Audio 1.0** | Use for all TTS, voice, dubbing and voice-cloning discussion. Supersedes the Seed TTS line — do not recommend Seed TTS. |
| Text / LLM | **Doubao** (current generation) | Confirm the exact tier with the AE before the meeting. |

Superseded models may still be *named* when describing what a customer already uses, or
when a customer asks about them directly. The rule is about what we **lead with**.

### How to Score (High / Medium / Low for each model type)

**Score High if 2+ of these are true:**
- Customer's core product relies on AI generation or AI assistance
- Their vertical has proven BytePlus use cases (see vertical map below)
- Active AI hiring (3+ open AI roles)
- Recent AI funding or AI product announcement
- No strong competitor lock-in signal
- Company size / scale warrants API-level consumption

**Score Medium if:**
- AI is on their roadmap but not yet core product
- Some competitor usage but no exclusive lock-in
- Mid-size company with moderate scale needs

**Score Low if:**
- No AI signals found
- Confirmed exclusive multi-year contract with competitor
- Very early stage (< 20 employees, pre-product)
- Regulated industry with strong data residency constraints (may still be an opportunity with proper compliance framing)

### Vertical Opportunity Map

| Vertical | Text/LLM | Image | Video | Audio | Key BytePlus Use Cases |
|---|---|---|---|---|---|
| E-commerce / Retail | H | H | H | M | Product description gen, background removal, product video ads, voice-over for ad creative |
| Media & Entertainment | M | M | H | H | Video generation, dubbing, localisation voice-over, content creation |
| Gaming | L | H | H | H | Asset generation, NPC voice + dialogue, cutscene gen |
| Marketing / AdTech | H | H | H | H | Copy gen, creative gen, video ads, multilingual voice-over |
| SaaS / Dev Tools | H | L | L | L | Code assist, docs gen, customer support |
| Fintech / Banking | H | L | L | M | Report gen, compliance docs, customer comms, IVR / voice agent |
| Healthcare | H | M | L | M | Medical summarization, patient comms, imaging (image), patient voice reminders |
| EdTech | H | M | H | H | Course content, tutoring, explainer videos, narration + pronunciation |
| Customer Service | H | L | L | H | Chatbot, agent assist, ticket classification, voice bot / IVR |
| Social / Creator | M | H | H | H | Content creation tools, filters, video effects, creator voice tools |
| Logistics / Supply Chain | M | L | L | L | Route optimization reports, comms |
| HR / Recruiting | H | L | L | L | JD gen, screening, onboarding docs |

### Volume Estimation Guide

Use headcount + vertical as proxy for monthly volume:

| Company Size | Consumer Product | Enterprise SaaS | Notes |
|---|---|---|---|
| < 50 employees | Low (< 1M tokens/mo) | Very Low | Proof-of-concept stage |
| 50–200 employees | Low–Medium | Low | Growing; good for pilot |
| 200–1000 employees | Medium (10–100M tokens/mo) | Medium | Significant spend potential |
| 1000–5000 employees | High (100M–1B tokens/mo) | Medium–High | Strong account |
| 5000+ employees | Very High (>1B tokens/mo) | High | Strategic account |

Image: 1 employee ≈ 0.1–1k images/month for internal tools; multiply 10x for consumer product
Video: consumer video platforms typically 10k–1M+ video minutes/month
Audio: voice bot / IVR ≈ 1–10k voice minutes per 100 daily support conversations;
       content localisation ≈ 1 audio hour per finished video hour per target language

---

## §6 — LinkedIn Deep Dive (Public Data Only)

LinkedIn company page structure (accessible without login):
- `linkedin.com/company/{slug}/` — About, employee count, specialties
- `linkedin.com/company/{slug}/posts/` — Recent company updates
- `linkedin.com/company/{slug}/jobs/` — Open positions

For people search, use WebSearch:
```
site:linkedin.com/in "{company}" (CTO OR "Chief AI" OR "VP Engineering" OR "Head of AI")
```

Extract:
- Employee count and growth trend ("+X% over past year" if shown)
- Recent posts mentioning AI, partnerships, product launches
- Specialties section (tells you their self-described focus areas)
- Follower count (brand reach signal)

**Important:** Do NOT attempt to log in or bypass LinkedIn's login wall. Public pages only.

---

## §7 — Crunchbase / Pitchbook / News Sources

```bash
# Crunchbase (public data)
WebFetch "https://www.crunchbase.com/organization/{slug}"

# Tech news sources to search
site:techcrunch.com "{company}" 2025
site:venturebeat.com "{company}" AI 2025
site:theinformation.com "{company}" (may be paywalled — use snippet only)
site:bloomberg.com "{company}" technology 2025
```

Extract:
- Funding rounds (date, amount, investors)
- Acquisitions made or target of acquisition
- Key product launches
- Leadership changes (new CTO, Head of AI = buying signal)

---

## §8 — Chinese Company Special Handling

For Chinese companies (PRC, HK, TW), additional sources:

```bash
# Chinese tech media
site:36kr.com "{company}" AI OR 人工智能
site:ifanr.com "{company}"
site:huxiu.com "{company}" AI
site:xinhuanet.com "{company}"

# Chinese social media signals (public Weibo/WeChat posts via search)
"{company}" AI model 2025 site:weibo.com
"{company}" 大模型 OR LLM OR 生成式AI

# Regulatory / government AI certification
"{company}" 国家互联网信息办公室 OR 生成式人工智能服务 备案
```

Note: For Chinese companies, BytePlus / Volcengine competitive positioning is often stronger than in Western markets. Check if customer qualifies for any government AI certification programs.
