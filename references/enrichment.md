# Enriched Customer Profile MCP

Query customer enrichment after extracting customer name/domain/attendee candidates and before final rendering.

Recommended request:

```json
{
  "mode": "pre_meeting_profile_fill",
  "customer_name_candidate": "Mythfactory",
  "company_domain": "mythfactory.xyz",
  "attendee_emails": ["douglas@mythfactory.xyz"],
  "attendee_names": ["Douglas"],
  "meeting_title": "BytePlus <> Mythfactory",
  "meeting_date": "2026-05-13",
  "calendar_organizer": "Sam Wallace",
  "requested_context": [
    "company_background",
    "industry",
    "hq",
    "company_size",
    "stakeholders",
    "known_use_cases",
    "known_competitors",
    "known_risks",
    "possible_byteplus_fit",
    "suggested_questions",
    "source_links"
  ]
}
```

Expected response fields:

- `matched`, `confidence`, `source`, `last_updated`.
- `customer`: canonical name, website, domain, industry, HQ, company size, description.
- `stakeholders`: name, email, title, source.
- `account_context`: known use cases, competitors, risks.
- `possible_byteplus_fit`: product, reason, confidence.
- `suggested_questions`.
- `source_links`.

Confidence rules:

- High: exact company domain, exact CRM/C360 account id, exact email-to-company mapping.
- Medium: company name match plus at least one attendee match, or meeting title match plus similar domain.
- Low: fuzzy company name only, or personal-email enrichment without verified company mapping.

Rendering:

- High confidence may be plain text.
- Medium/low confidence must be rendered as `Likely: ... (?)`, italic text with `(?)`, or `To Validate`.
- If MCP is unavailable, continue generation and add this run-report note: `Enriched Customer Profile MCP unavailable. Background enrichment fields may require manual review.`
