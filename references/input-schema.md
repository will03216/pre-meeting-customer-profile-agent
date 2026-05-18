# Render Helper Input Schema

`scripts/render_prep_doc.py` accepts a normalized JSON object with these keys. All optional keys may be omitted; missing values become `TBD - please confirm` or `To Validate`.

```json
{
  "meeting": {
    "title": "BytePlus <> Mythfactory",
    "start": "2026-05-13T11:00:00+01:00",
    "end": "2026-05-13T11:30:00+01:00",
    "timezone": "Europe/London",
    "organizer": {"name": "Sam Wallace", "email": "sam@example.com"},
    "sa": {"name": "SA Name", "email": "sa@example.com"},
    "url": "https://..."
  },
  "customer": {
    "name": "Mythfactory",
    "domain": "mythfactory.xyz",
    "website": "https://mythfactory.xyz",
    "industry": "Gaming / interactive entertainment",
    "hq": "Sydney, Australia",
    "company_size": "11-50",
    "description": "A studio building AI-driven NPC dialogue for indie games.",
    "confidence": "high"
  },
  "attendees": [
    {"name": "Douglas", "email": "douglas@mythfactory.xyz", "title": "CEO", "external": true}
  ],
  "enrichment": {
    "available": true,
    "confidence": "high",
    "known_use_cases": ["AI NPC dialogue"],
    "known_competitors": ["OpenAI", "Azure"],
    "known_risks": ["Latency sensitivity", "EU data residency"],
    "possible_byteplus_fit": [
      {"product": "Doubao / Seed LLM", "reason": "Potential dialogue workload", "confidence": "medium"}
    ],
    "suggested_questions": ["What is your current model / vendor stack?"],
    "source_links": [{"label": "Apollo enriched profile", "url": "https://..."}]
  },
  "prior_docs": [
    {"date": "2026-04-30", "title": "BytePlus <> Mythfactory - 30-04-2026", "url": "https://...", "engagement_rows": []}
  ],
  "prior_notes": [],
  "search_results": [
    {"label": "Gaming Seed LLM case study", "url": "https://...", "summary": "Trusted product doc"}
  ],
  "known": {
    "objectives": [],
    "pain_points": [],
    "budget_status": "",
    "contract_commitment": "",
    "poc_timeline": ""
  },
  "source_status": {
    "calendar": "available",
    "attendees": "available",
    "mcp": "available",
    "mira": "unavailable",
    "prior_docs": "none",
    "prior_notes": "none"
  }
}
```
