---
name: pre-meeting-customer-profile
description: Auto-generate BytePlus pre-meeting Customer Profile and Standard Action documents from calendar events, attendees, customer enrichment, Mira or knowledge-base search, prior customer docs, AI Notes, and product references. Use when preparing an AE or SA for upcoming qualified customer-facing meetings, scanning calendars for customer prep, creating or updating Lark/Feishu customer profile docs, resolving customer names from attendees/domains, or drafting pre-meeting hypotheses, questions, risks, product-fit angles, and To Validate fields.
---

# Pre-Meeting Customer Profile

Use this skill to create or update a BytePlus Customer Profile & Standard Action draft before a qualified customer meeting. Preserve the original master template structure and mark pre-meeting content as confirmed, likely, or to validate.

## Core Rules

- Generate a useful draft whenever a calendar event is available. Optional source failures must degrade to `TBD - please confirm` or `To Validate`, never block the document.
- Use the master template from `https://bytedance.sg.larkoffice.com/docx/KxPkdR5m3oaFQtx0Hpsl0TQsgTc` as the structure. Read `references/master-template.md` for the fetched section layout and static script blocks.
- Use vertical-aware prospecting prefill when possible: infer the customer vertical, select an industry playbook, retain relevant master-template questions, and pre-fill answers inline inside the existing template sections.
- Do not render a giant `Question Coverage Matrix`; irrelevant vertical-specific questions should be omitted or collapsed.
- Title documents as `BytePlus <> [Customer Name] - DD-MM-YYYY - Pre-Meeting Prep`, using Europe/London for the meeting date.
- Default storage folder: Customer Profiles, folder token `FFrAfB8t6lrZTvdpx8Zc4HEenub`, unless the user asks for Customer Prep Briefs or another folder.
- Prefer true Lark mentions when the docx API supports them. Otherwise use plain text `Name (email)`.
- Do not write inferred requirements as confirmed customer requirements. Use `Likely: ... (?)`, italic Markdown, or `To Validate: ...`.
- Use the confidence labels `Known`, `Likely`, `To Validate`, and `Not Found`. `Known` requires evidence; `Likely` must include `(?)`.
- Use ASCII punctuation in generated docs unless copying exact template text from Lark.

## Workflow

1. Gather calendar events for the configured window.
   - Defaults: `PRE_MEETING_LOOKAHEAD_HOURS=24`, `PRE_MEETING_MIN_NOTICE_HOURS=1`, `DEFAULT_TIMEZONE=Europe/London`.
   - Manual alternatives: event id, customer name, or "tomorrow".
2. Qualify meetings.
   - Include only primary-calendar future events with at least one external attendee.
   - Exclude titles matching internal-only patterns in `references/qualification.md`.
   - Flag internal-domain externals for manual confirmation instead of auto-skipping them.
3. Extract event facts.
   - Title, start/end, organizer, attendees, event link, attendee emails/domains.
4. Resolve the canonical customer name.
   - Follow the ordered resolver in `references/customer-resolution.md`.
   - Do not group personal-email domains by domain; use overrides, title, enrichment, or internal search.
5. Query optional sources in priority order.
   - Prior customer docs and prior AI Notes/minutes.
   - Enriched Customer Profile MCP, if available.
   - Mira or knowledge-base search.
   - Product, solution, case study, pricing, and competitor references.
6. Merge facts by confidence.
   - Calendar facts are authoritative for meeting details.
   - Prior docs/AI Notes are authoritative for confirmed engagement history.
   - High-confidence MCP values can be plain text; medium/low confidence values get `(?)`.
   - Search results support hypotheses unless they are trusted prior customer docs or trusted product docs.
7. Render the document.
   - Use the six-section structure in `references/master-template.md`.
   - Put `Pre-Meeting Prep - to validate in customer meeting` in the title/status block.
   - Add "Suggested Questions for This Meeting" above the static interview script, then keep the master script blocks.
   - Add retained question prefill directly under the relevant original template section headings such as Standard Discovery Questions, AI Usage & Current Stack, Image / Video Usage, POC Qualification, and Commercial & Procurement Signals.
   - For each retained question include pre-filled answer, confidence, evidence/source when available, why it matters, and ask-in-meeting follow-up.
   - For Section 3, import prior engagement-log rows newest first and add a Pre-Meeting placeholder row.
   - For Section 4, preserve the fetched master output categories and prefix values with `Known:`, `Likely:`, `To Validate:`, `Not Found:`, and `Follow-up:`.
8. Create or update the Lark document.
   - Idempotency recommendation: match by customer + meeting date + calendar event id. Update an existing prep doc by default.
   - Use the docx API or `lark-cli docs` when available. If only a Markdown draft can be produced locally, produce it and state what is missing.
9. DM the SA.
   - Include doc link, key prep points, top questions, missing fields, and unavailable source notes.

## Portable CLI Entrypoint

Use `scripts/run_prep.py` as the main user-facing orchestration command. It is portable for packaged zip installs and runs under each user's own Lark CLI authentication and permissions.

Examples:

```bash
python scripts/run_prep.py --event-id "<lark_event_id>"
python scripts/run_prep.py --customer "Moburst"
python scripts/run_prep.py --domain "moburst.com"
python scripts/run_prep.py --email "isaac@moburst.com"
python scripts/run_prep.py --window today
python scripts/run_prep.py --window tomorrow
python scripts/run_prep.py --window next-7-days
python scripts/run_prep.py --window "2026-05-15:2026-05-22"
```

Supported flags:

```bash
--dry-run
--output-json
--create-doc
--update-existing
--no-notify
--prospecting-prompt <path>
--industry <name>
--debug
```

Industry playbooks:

```bash
python scripts/run_prep.py --domain naturalint.com --industry marketing_adtech
python scripts/run_prep.py --customer "David Agronov" --industry marketing_adtech
python scripts/run_prep.py --domain example.com --industry enterprise_llm
python scripts/run_prep.py --domain naturalint.com --prospecting-prompt config/prospecting_prompt.md
```

If `--industry` is omitted, the skill infers a vertical from event context, prior docs, docs search, web search results, official website text, product modules, and enrichment snippets. If confidence is weak, it uses the default playbook. If a requested playbook is missing, it warns and falls back to `config/industry_playbooks/default.md`.

Default prospecting guidance is stored in `config/prospecting_prompt.md`. Initial playbooks live under `config/industry_playbooks/`: `default`, `marketing_adtech`, `ai_video_creative`, `ecommerce`, `gaming`, and `enterprise_llm`.

For local mode, this packaged skill is portable. Each user installs the zip, completes Lark CLI authentication with their own account, and the skill runs using that user's Calendar/Docs/Folder permissions.

If the user does not have access to the configured Customer Profiles folder, the skill will either create the doc in the user's default space or write a local markdown fallback.

Optional configuration:

```bash
LARK_CALENDAR_ID=primary
DEFAULT_TIMEZONE=Europe/London
INTERNAL_EMAIL_DOMAINS=bytedance.com,byteplus.com
CUSTOMER_PROFILE_FOLDER_TOKEN=<folder_token>
PREP_DOC_FOLDER_TOKEN=<folder_token>
PREP_NOTIFY_USER_ID=<open_id>
MCP_CUSTOMER_ENRICHMENT_URL=https://...
MCP_CUSTOMER_ENRICHMENT_TOKEN=<token>
```

Required or useful Lark scopes depend on selected features:

- Calendar fetch: `calendar:calendar.event:read`
- Docs search/dedupe: `search:docs:read`
- Doc creation/update: `docx:document:create`, `docx:document:write_only`
- Bot notification: `im:message`

Troubleshooting:

- If Lark CLI is missing, install it and authenticate.
- If auth or keychain fails, rerun `lark-cli auth login` in the same profile.
- If docs search is unavailable, the run continues without prior docs.
- If folder writes fail, unset the folder token or grant folder access; local markdown output is retained under `outputs/prep/`.

## Rendering Helper

Use `scripts/render_prep_doc.py` to produce a Markdown/Lark-compatible draft from normalized JSON when live APIs are unavailable or when testing merge logic.

```bash
python3 /Users/bytedance/.codex/skills/pre-meeting-customer-profile/scripts/render_prep_doc.py \
  --input event_context.json \
  --output prep-draft.md
```

Input shape is documented in `references/input-schema.md`. The script is intentionally conservative: it fills known fields, marks weak or missing fields, and emits a source availability report.

## Lark/Mira/MCP Integration Notes

- Calendar and attendees are the only required sources for meeting-specific generation.
- Enriched Customer Profile MCP input and output contracts are in `references/enrichment.md`.
- Mira search query guidance and source-use rules are in `references/search.md`.
- Vertical playbooks guide question filtering and inline prefill style only; they do not override source attribution rules or convert inferred content into confirmed facts.
- If the master template needs to be refreshed, run:

```bash
lark-cli docs +fetch --doc https://bytedance.sg.larkoffice.com/docx/KxPkdR5m3oaFQtx0Hpsl0TQsgTc --format pretty
```

Keep fetched master-template changes in `references/master-template.md` so future runs preserve the original structure.

## Output Checklist

- Qualified customer meeting only.
- Customer name resolved or clearly marked `<unknown> (please confirm)`.
- Meeting date formatted `DD-MM-YYYY` in Europe/London.
- Six sections present: Background, Live Interview Script, Client Engagement Log, Meeting Output Template, Risk & Support, Reference.
- Suggested questions cover missing fields, unconfirmed enrichment, unresolved next steps, risks, competitors, and product-fit hypotheses.
- Vertical-aware retained questions are answered inline inside existing template sections, not in a separate full matrix.
- Meeting Output Template rows contain actionable `Known`, `Likely`, `To Validate`, `Not Found`, `Evidence`, or `Follow-up` notes.
- Missing optional sources listed in the run report and SA DM.
- No duplicate prep document created when an existing customer/date/event doc exists.
