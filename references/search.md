# Mira / Knowledge Base Search

Use internal search as supporting context, not unquestioned fact.

Search targets:

- Existing customer profiles.
- Prior AI Notes, Lark Minutes, meeting summaries.
- Product documentation and model capability docs.
- Case studies and solution architecture references.
- Pricing and packaging notes, when accessible.
- Industry pitch materials, competitor comparisons, FAQ and objection handling docs.

Generate targeted queries from:

- Customer name.
- Customer domain.
- Attendee names and emails.
- Industry.
- Possible use case.
- Known competitor.
- BytePlus product keywords.

Example queries:

- `"Mythfactory" customer profile`
- `"mythfactory.xyz" BytePlus`
- `"AI NPC dialogue" Doubao case study`
- `"gaming" "Seed LLM" latency`
- `"OpenAI Azure" Doubao migration`
- `"EU data residency" BytePlus`

Use `Known:` only when the result is from a prior internal customer doc, AI Note, or trusted product doc.

Use `Likely:` or `To Validate:` when the result is inferred from weak search evidence.

If search returns nothing, continue generation and mark affected fields as `TBD - please confirm` or `To Validate`.
