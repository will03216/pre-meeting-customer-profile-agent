# Customer Name Resolution

Resolve the canonical customer name in this order. First confident match wins.

1. Email override map
   - Example: `taylorsiratt@gmail.com -> Rap.AI`.
   - Best storage: user-maintained JSON, Lark Sheet, or Bitable.
2. Canonical domain map
   - Example: `rdandx.com -> RD&X`, `realtimeuk.com -> RealtimeUK`.
3. Meeting title parsing
   - `^(.*?) <> (?:byte|byteplus|bytedance)` -> group 1.
   - `^(?:byte|byteplus|bytedance) <> (.*)` -> group 1.
   - `^(.*?) & ByteDance` -> group 1.
4. Enriched Customer Profile MCP exact match
   - Confirm canonical customer name.
   - Resolve personal-email attendees to companies.
   - Validate domain mappings.
5. Mira or internal document search
   - Search customer name candidates, domain, attendee emails, company aliases.
   - Use only high-confidence matches for canonical naming.
   - Flag fuzzy matches as low-confidence.
6. Domain-root fallback
   - Example: `studiopro.llc -> StudioPro`.
   - Strip common suffixes and title-case cautiously.
7. Manual fallback
   - Render `<unknown> (please confirm)` and surface a run-report flag.

AE handling:

- If calendar organizer is not the SA, use the organizer as AE/Owner.
- If calendar organizer is the SA, look up the AE from prior docs, prior external-organizer meetings, CRM/MCP account owner, or internal docs.
- If no AE match is found, render `TBD - please confirm`.
