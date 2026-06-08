# Apollo.io Enrichment Workflow

Apollo.io provides B2B contact and company intelligence via REST API.

## Authentication

```bash
# API key passed in request body (Apollo v1) or header (Apollo v2)
APOLLO_KEY="${APOLLO_API_KEY:-}"
```

If `APOLLO_API_KEY` is not set: skip all Apollo calls, add note `[Apollo: not configured — set APOLLO_API_KEY env var]` to the doc's Sources section.

---

## Endpoint 1 — Organization Enrichment

Returns company profile given a domain name.

```bash
curl -s -X POST "https://api.apollo.io/api/v1/organizations/enrich" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $APOLLO_KEY" \
  -H "Cache-Control: no-cache" \
  -d "{\"domain\": \"$DOMAIN\"}"
```

### Key fields to extract

| Apollo field | Maps to profile section |
|---|---|
| `organization.name` | Company Name |
| `organization.founded_year` | Founded |
| `organization.estimated_num_employees` | Company Size |
| `organization.annual_revenue_printed` | Revenue Estimate |
| `organization.industry` | Industry/Vertical |
| `organization.country` | HQ Location |
| `organization.city` | HQ City |
| `organization.linkedin_url` | LinkedIn URL |
| `organization.twitter_url` | Twitter |
| `organization.crunchbase_url` | Crunchbase |
| `organization.technologies` | Tech Stack (CRITICAL) |
| `organization.short_description` | What They Do |
| `organization.keywords` | Additional context |
| `organization.funding_events` | Funding rounds |
| `organization.total_funding` | Total funding raised |

### Tech stack AI signal detection

Scan `organization.technologies` array for:

```python
AI_SIGNALS = [
  # LLM / NLP
  "openai", "chatgpt", "gpt", "anthropic", "claude", "cohere",
  "hugging face", "langchain", "llm", "vertex ai", "bedrock",
  "azure openai", "mistral", "together ai", "replicate",

  # Cloud AI platforms
  "aws sagemaker", "google cloud ai", "azure ml", "databricks",

  # Image / Video AI
  "stable diffusion", "midjourney", "runway", "pika",

  # BytePlus/Volcengine signals
  "volcengine", "byteplus", "doubao", "火山引擎",

  # ML infrastructure
  "pytorch", "tensorflow", "triton", "ray serve", "mlflow",
  "weights & biases", "wandb", "kubeflow",

  # Vector DBs (signals LLM usage)
  "pinecone", "weaviate", "qdrant", "chroma", "milvus",
]

# If any match → add to "AI Stack" section with confidence: "Apollo tech stack"
```

---

## Endpoint 2 — People / Contacts Search

Find key stakeholders at the company.

```bash
curl -s -X POST "https://api.apollo.io/api/v1/mixed_people/search" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $APOLLO_KEY" \
  -d "{
    \"organization_domains\": [\"$DOMAIN\"],
    \"person_titles\": [
      \"CTO\", \"Chief Technology Officer\",
      \"Chief AI Officer\", \"VP AI\", \"Head of AI\",
      \"VP Engineering\", \"Director of Engineering\",
      \"Head of Machine Learning\", \"ML Lead\",
      \"VP Product\", \"Chief Product Officer\",
      \"VP Procurement\", \"Head of Vendor Management\"
    ],
    \"page\": 1,
    \"per_page\": 10
  }"
```

### Fields to extract per contact

```python
contact_fields = {
  "name": person["name"],
  "title": person["title"],
  "linkedin_url": person["linkedin_url"],
  # email: DO NOT include in wiki write (desensitization rule)
  # phone: DO NOT include
  "seniority": person.get("seniority"),
}
```

**Always redact email and phone before wiki write.**
Use `[contact@redacted]` placeholder if referenced.

---

## Endpoint 3 — Technology Check (alternative)

If you want to check if a specific technology is in their stack:

```bash
curl -s -X POST "https://api.apollo.io/api/v1/organizations/search" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $APOLLO_KEY" \
  -d "{
    \"q_organization_name\": \"$COMPANY_NAME\",
    \"organization_technology_names\": [\"OpenAI\", \"AWS Bedrock\"],
    \"page\": 1,
    \"per_page\": 5
  }"
```

---

## Error Handling

| HTTP Status | Meaning | Action |
|---|---|---|
| 200 | Success | Parse response |
| 401 | Invalid API key | Skip, note `[Apollo: invalid API key]` |
| 422 | Missing required field | Check domain format; retry with cleaned domain |
| 429 | Rate limit | Wait 2s, retry once; if still 429, skip |
| 404 | Company not found | Try with `www.` prefix stripped; if still 404, skip |

**Always fail gracefully** — if Apollo returns no data, note `[Apollo: no data found for domain $DOMAIN]` in the Sources section and continue with other agents.

---

## Apollo Data Quality Notes

- `estimated_num_employees` is a range estimate, not exact — present as "~X employees"
- `annual_revenue_printed` is Apollo's estimate — present as "est. $X" 
- `technologies` may be incomplete — cross-reference with website careers page
- Employee counts may lag 3–6 months behind actuals
- For Chinese companies: coverage is often lower; web enrichment will compensate
