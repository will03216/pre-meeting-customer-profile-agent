# Apollo.io Enrichment Contract

## Purpose

Apollo enrichment adds company firmographic and stakeholder candidate data for
small, niche, or ambiguous companies that are underserved by generic web search
(e.g. "Jellyfish", "Jellysmack", small B2B SaaS companies).

It sits between MCP/CRM and generic web search in the source priority chain:

```
Calendar/event > Lark prior docs > MCP/CRM > Apollo > Web search > Manual fallback
```

## When Apollo Is Invoked

Apollo is called when:
- `APOLLO_API_KEY` is set in the environment.
- `--no-apollo` is NOT passed.
- The customer identity has a domain or name to search by.

Apollo is NOT the default for every run — it activates only when the key is configured.

## Source Priority

1. Domain-exact match (highest confidence) — `organizations/enrich?domain=<domain>`
2. Name search fallback — `mixed_companies/search` with name + optional domain hint
3. People search — `mixed_people/search` filtered by vertical-aware title buckets

## Confidence Labels

| Confidence | Condition |
| --- | --- |
| `high_domain_exact` | Apollo returned the exact input domain |
| `medium_name_and_domain_match` | Name search matched and domain is consistent |
| `low_name_only` | Name match only, no domain to verify |
| `ambiguous` | Apollo returned a different domain; flagged, not promoted |
| `none` | No match or disabled |

## Domain Guard (Non-Negotiable)

If Apollo returns an organization whose domain differs from the input domain, the
result is flagged as `ambiguous_match` and stored in `warnings`. It is **never**
used to override the customer identity or primary domain.

## People Search

People are fetched only when org confidence is `high_domain_exact` or
`medium_name_and_domain_match`. Title buckets are vertical-aware:

| Vertical | Primary titles searched |
| --- | --- |
| marketing_adtech | CTO, VP Engineering, VP Marketing, CMO, CEO, Founder |
| ai_video_creative | CTO, VP Engineering, Head of AI, VP Product, CEO |
| enterprise_llm | CTO, Head of AI/ML, VP Infrastructure, Enterprise Architect, CEO |
| ecommerce | CTO, VP Engineering, VP Product, CEO |
| gaming | CTO, VP Engineering, Technical Director, VP Product, CEO |
| default | CTO, VP Engineering, VP Product, CEO, Founder |

## Confidence in Generated Documents

Apollo values are **never** labeled `Known`. They are labeled:
- `Likely: <value> (Apollo signal) (?)` — for firmographic fields
- `Tier 3 - Apollo enrichment` — in the Evidence Table

## Privacy Defaults

| Setting | Default | Override |
| --- | --- | --- |
| `APOLLO_REVEAL_EMAILS` | `0` (off) | set to `1` to include LinkedIn URLs |
| `APOLLO_REVEAL_PHONE_NUMBERS` | `0` (off) | not exposed even when `1` |
| `APOLLO_WATERFALL_ENABLED` | `0` (off) | set to `1` for name-search even when domain succeeds |

## Caching

- Cache key: SHA256 of endpoint + params (without `api_key`)
- Cache location: `.cache/prep_apollo/<key>.json`
- Default TTL: `APOLLO_CACHE_TTL_HOURS=24`
- Force refresh: `--apollo-refresh`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `APOLLO_API_KEY` | Apollo API key (required to enable) | (unset = disabled) |
| `APOLLO_MAX_PEOPLE` | Max stakeholder candidates per run | `5` |
| `APOLLO_CACHE_TTL_HOURS` | Cache TTL in hours | `24` |
| `APOLLO_WATERFALL_ENABLED` | Run name search even if domain matched | `0` |
| `APOLLO_REVEAL_EMAILS` | Include LinkedIn URLs in people output | `0` |
| `APOLLO_REVEAL_PHONE_NUMBERS` | Include phone numbers in people output | `0` |

## CLI Flags

| Flag | Description |
| --- | --- |
| `--no-apollo` | Disable Apollo for this run |
| `--apollo-refresh` | Bypass cache and fetch fresh data |
| `--apollo-max-people <n>` | Override `APOLLO_MAX_PEOPLE` for this run |
| `--apollo-debug` | Print Apollo API diagnostics to stderr |

## Security Rules (Non-Negotiable)

1. The API key is never printed in logs, errors, generated docs, test output, or debug output.
2. Personal emails and phone numbers are not exposed by default.
3. Waterfall enrichment is disabled by default.
4. Apollo firmographic values stay `Likely (Apollo signal)`, not `Known`.
5. Domain guard: different-domain results are flagged, never silently adopted.
6. No real API key is committed or printed in any generated file.

## Output Sections in Generated Doc

- **Essential Background Check**: Apollo adds rows for Employee Count, Revenue Signal,
  HQ/Location, Founded Year, LinkedIn URL, Technology Signals, and Company Description
  (only if the main description is missing or `To Validate`).
- **Apollo Stakeholder Candidates**: table with Name, Title, Dept/Seniority, Why Relevant,
  Source columns — inserted between Essential Background Check and Executive Prep Snapshot.
- **Evidence Table**: Apollo signals appear as `Tier 3 - Apollo enrichment` rows.
- **Run Report**: `source_status.apollo` shows the enrichment status for this run.
