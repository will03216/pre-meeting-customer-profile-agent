# Apollo.io Enrichment Workflow

Apollo.io provides B2B contact and company intelligence via REST API.

## Authentication

```bash
# API key MUST be passed in the X-Api-Key header on every request.
APOLLO_KEY="${APOLLO_API_KEY:-}"
```

Passing `api_key` inside the JSON request body is no longer accepted — Apollo returns
`422` with `error_code: INVALID_API_KEY_LOCATION`. Never put the key in a URL query string.

Verify a key before a full run:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://api.apollo.io/api/v1/organizations/enrich" \
  -H "Content-Type: application/json" -H "X-Api-Key: $APOLLO_KEY" \
  -d '{"domain":"stripe.com"}'   # expect 200
```

Response headers carry the remaining quota: `x-minute-requests-left`,
`x-hourly-requests-left`, `x-rate-limit-24-hour`.

`APOLLO_API_KEY` is **recommended but not required**. If it is unset, or the verification call does not return `200`, skip all Apollo calls, note `[Apollo: skipped — <reason>]` in the Sources section, and let the rest of the pipeline run — never stop the prospection over Apollo.

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
| `organization.technology_names` | Tech Stack (CRITICAL) — flat array of strings |
| `organization.short_description` | What They Do |
| `organization.keywords` | Additional context |
| `organization.funding_events` | Funding rounds |
| `organization.total_funding` | Total funding raised |

### Tech stack AI signal detection

Scan the `organization.technology_names` array (flat list of strings, e.g.
`["AWS Bedrock", "Anthropic Claude", "ChatGPT", "PyTorch", ...]`) for:

> The legacy `organization.technologies` field is no longer returned. Reading it yields
> `None`, which makes AI-stack detection silently produce an empty section — always read
> `technology_names`, and match case-insensitively.

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

hits = [t for t in (org.get("technology_names") or [])
        if any(s in t.lower() for s in AI_SIGNALS)]

# If any match → add to "AI Stack" section with confidence: "Apollo tech stack"
```

Typical volume: 200–360 entries per mid-to-large company, so expect several hits.
An empty `technology_names` is a real "no data" signal, not a parsing failure —
verify with a known-good domain before concluding the company has no detectable stack.

---

## Endpoint 2 — People / Contacts Search

Find key stakeholders at the company.

**Two breaking changes — both easy to get wrong:**

1. The endpoint is `mixed_people/api_search`. The old `mixed_people/search` returns `422`:
   *"This endpoint is deprecated for API callers."*
2. The domain filter param is `q_organization_domains_list`. The old `organization_domains`
   is **silently ignored** on the new endpoint — no error, but the response contains people
   from completely unrelated companies. (Observed: filtering `stripe.com` with the old param
   returned `total_entries: 273548` with results from Integra Technologies, Extenda Retail,
   Seno Medical …; the correct param returned `total_entries: 7`, all genuinely Stripe.)

```bash
curl -s -X POST "https://api.apollo.io/api/v1/mixed_people/api_search" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $APOLLO_KEY" \
  -d "{
    \"q_organization_domains_list\": [\"$DOMAIN\"],
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

### Validate the response before using it

```python
people = resp.get("people") or []
# Guard: if the domain filter failed to apply, discard rather than write bad contacts.
if resp.get("total_entries", 0) > 500 or any(
    (p.get("organization") or {}).get("name", "").lower() not in company_name.lower()
    for p in people
):
    people = []   # note "[Apollo: contact filter unreliable — skipped]"
```

### Fields to extract per contact

Most API tiers return **masked** people records. Only these are populated:

| Field | Populated? |
|---|---|
| `title` | yes |
| `first_name` | yes |
| `organization.name` | yes |
| `has_email` / `has_direct_phone` | yes (booleans only) |
| `last_name_obfuscated` | yes (not a real name) |
| `name`, `last_name`, `linkedin_url`, `seniority`, `email` | **`null`** |

```python
contact_fields = {
  "first_name": person.get("first_name"),      # full name is usually null
  "title": person["title"],
  "org": (person.get("organization") or {}).get("name"),
  # email / phone: null on masked tiers, and DO NOT include even when present
}
```

**Use Apollo contacts as a title-distribution signal** — which roles exist in the org chart
and how the engineering/AI leadership is structured. It is not a named contact list.
Named decision-makers must come from the web-enrichment agent via public LinkedIn pages.

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
| 422 + `INVALID_API_KEY_LOCATION` | Key sent in body instead of header | Move key to `X-Api-Key` header |
| 422 + `"endpoint is deprecated"` | Old endpoint path | Use `mixed_people/api_search` |
| 422 | Missing required field | Check domain format; retry with cleaned domain |
| 429 | Rate limit | Wait 2s, retry once; if still 429, skip |
| 404 | Company not found | Try with `www.` prefix stripped; if still 404, skip |

**Silent failures have no status code** — a 200 does not mean the data is right. The two
known ones: an ignored domain filter (Endpoint 2, see above) and reading the removed
`technologies` field. Both must be caught by validating the parsed response, not the status.

**Always fail gracefully** — if Apollo returns no data, note `[Apollo: no data found for domain $DOMAIN]` in the Sources section and continue with other agents.

---

## Apollo Data Quality Notes

- `estimated_num_employees` is a range estimate, not exact — present as "~X employees"
- `annual_revenue_printed` is Apollo's estimate — present as "est. $X" 
- `technology_names` may be incomplete — cross-reference with website careers page
- People records are masked on most tiers (no full names / LinkedIn) — see Endpoint 2
- Employee counts may lag 3–6 months behind actuals
- For Chinese companies: coverage is often lower; web enrichment will compensate
