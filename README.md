# Pre-Meeting Customer Profile Skill

Portable meeting-prep skill for generating BytePlus Customer Profile / Standard Action prep docs from Lark calendar events, customer names, domains, or email addresses.

For local mode, this packaged skill is portable. Each user installs the zip, completes Lark CLI authentication with their own account, and the skill runs using that user's Calendar/Docs/Folder permissions.

## Install From Zip

1. Unzip the skill package.
2. Open a terminal in the unpacked skill folder.
3. Confirm Lark CLI is available:

```bash
lark-cli auth status
```

4. Authenticate with the scopes you need:

```bash
lark-cli auth login --scope "calendar:calendar.event:read search:docs:read docx:document:create docx:document:write_only im:message"
```

Depending on your Lark app configuration, some scope names may differ. The script degrades gracefully when optional scopes are missing.

## Usage

```bash
python scripts/run_prep.py --event-id "<lark_event_id>"
python scripts/run_prep.py --customer "Moburst"
python scripts/run_prep.py --domain "moburst.com"
python scripts/run_prep.py --email "isaac@moburst.com"
python scripts/run_prep.py --window today
python scripts/run_prep.py --window tomorrow
python scripts/run_prep.py --window next-7-days
python scripts/run_prep.py --window past-48-hours
python scripts/run_prep.py --window "2026-05-15:2026-05-22"
python scripts/run_prep.py --domain naturalint.com --industry marketing_adtech
python scripts/run_prep.py --domain naturalint.com --prospecting-prompt config/prospecting_prompt.md
```

Useful options:

```bash
--dry-run          Do not create/update docs or send IM notifications
--output-json      Print machine-readable normalized JSON and result data
--create-doc       Explicitly allow new doc creation
--update-existing  Update the best matching existing prep/profile doc
--no-notify        Do not send the internal bot IM summary
--industry         Force an industry playbook such as marketing_adtech, ai_video_creative, ecommerce, gaming, or enterprise_llm
--prospecting-prompt <path>
                  Load prospecting guidance from a custom markdown file
--no-apollo        Disable Apollo.io enrichment for this run
--apollo-refresh   Bypass Apollo cache and fetch fresh data
--apollo-max-people <n>
                  Max stakeholder candidates from Apollo (default: APOLLO_MAX_PEOPLE env or 5)
--apollo-debug     Print Apollo API diagnostics to stderr
--debug            Print diagnostics without secrets
```

Dry-run examples:

```bash
python3 scripts/run_prep.py --customer "Moburst" --dry-run --debug
python3 scripts/run_prep.py --domain "moburst.com" --dry-run --output-json
python3 scripts/run_prep.py --email "isaac@moburst.com" --dry-run
python3 scripts/run_prep.py --window tomorrow --dry-run
python3 scripts/run_prep.py --domain naturalint.com --industry marketing_adtech --dry-run --debug
```

Apollo enrichment live test (isolates Apollo signal, skips web search):

```bash
# Test Apollo enrichment and domain guard — jelly-fish.co.kr is a Korean company;
# Apollo may match the US company jellyfish.co which should be rejected.
PREP_WEB_SEARCH_DISABLED=1 python3 scripts/run_prep.py \
  --customer "Jellyfish" --domain "jelly-fish.co.kr" \
  --apollo-refresh --apollo-debug --no-notify --dry-run

# Full live run (creates doc, runs web enrichment too):
python3 scripts/run_prep.py \
  --customer "Jellyfish" --domain "jelly-fish.co.kr" \
  --apollo-refresh --apollo-debug --create-doc --no-notify
```

## Configuration

Optional environment variables:

```bash
LARK_CALENDAR_ID=primary
DEFAULT_TIMEZONE=Europe/London
INTERNAL_EMAIL_DOMAINS=bytedance.com,byteplus.com
CUSTOMER_PROFILE_FOLDER_TOKEN=<folder_token>
PREP_DOC_FOLDER_TOKEN=<folder_token>
PREP_NOTIFY_USER_ID=<open_id>
MCP_CUSTOMER_ENRICHMENT_URL=https://...
MCP_CUSTOMER_ENRICHMENT_TOKEN=<token>

# Apollo.io enrichment (optional — leave blank to disable)
APOLLO_API_KEY=<your_apollo_api_key>
APOLLO_MAX_PEOPLE=5
APOLLO_CACHE_TTL_HOURS=24
APOLLO_WATERFALL_ENABLED=0
APOLLO_REVEAL_EMAILS=0
APOLLO_REVEAL_PHONE_NUMBERS=0
```

If the user does not have access to the configured Customer Profiles folder, the skill will either create the doc in the user's default space or write a local markdown fallback.

Local markdown and JSON fallbacks are written under:

```bash
outputs/prep/
```

## Behavior

- Event ID mode fetches one Lark event and uses its title, time, attendees, organizer, description, and meeting link.
- Customer mode searches for prior docs using the customer name and generates a draft even when meeting context is missing.
- Domain mode treats corporate domain evidence as strong identity evidence.
- Email mode uses corporate email domains, but does not infer company identity from personal providers such as Gmail, Outlook, Hotmail, Yahoo, iCloud, QQ, or 163.
- Window mode scans calendar events, skips obvious internal meetings, and generates prep for qualified customer-facing events.
- Docs search is used for prior context and dedupe when `search:docs:read` is available.
- MCP enrichment is optional. If not configured or failing, the run continues and marks enrichment unavailable.
- The skill infers a vertical when `--industry` is not provided, then uses `config/industry_playbooks/` to retain relevant master-template questions and omit or collapse irrelevant deep dives.
- The skill renders pre-filled answers inline under existing template sections. It does not render a giant `Question Coverage Matrix`.
- Confidence labels are `Known`, `Likely`, `To Validate`, and `Not Found`. `Known` requires evidence; `Likely` is inference and must include `(?)`.
- The Meeting Output Template keeps the original categories and fills notes with `Known`, `Likely`, `To Validate`, `Not Found`, `Evidence`, and `Follow-up` language.
- Notifications are internal only. The script sends bot IM summaries to `PREP_NOTIFY_USER_ID` or the authenticated user when available. It never sends anything to customers.

## Prospecting Prompt and Industry Playbooks

Default prospecting guidance:

```text
config/prospecting_prompt.md
```

Initial playbooks:

```text
config/industry_playbooks/default.md
config/industry_playbooks/marketing_adtech.md
config/industry_playbooks/ai_video_creative.md
config/industry_playbooks/ecommerce.md
config/industry_playbooks/gaming.md
config/industry_playbooks/enterprise_llm.md
```

If `--industry` is provided, that playbook is used. If it is missing, the script warns in debug mode and falls back to `default.md`. If `--industry` is omitted, vertical inference uses customer name, domain, event title, prior docs, docs search snippets, web search results, official website snippets, product modules, and enrichment context.

The original BytePlus master template remains the source of truth. Playbooks only guide which questions are useful for the detected vertical and how to pre-fill them inside the existing sections.

## Troubleshooting

- `lark-cli is not installed`: install Lark CLI and ensure it is on `PATH`.
- `keychain not initialized` or auth errors: run `lark-cli auth login` again in the same user profile.
- Calendar permission missing: add calendar event read permission to the Lark app and re-authenticate.
- Docs search unavailable: add `search:docs:read` and re-authenticate.
- Folder write permission missing: grant access to the configured folder, unset the folder token to use default space, or use the local markdown fallback.
- No qualified meetings found: use an explicit `--event-id`, `--customer`, `--domain`, or `--email` to force a customer anchor.

## Packaging

Build a clean zip under `dist/`:

```bash
python scripts/package_skill.py
```

The package includes these files:

```text
SKILL.md
README.md
config/
references/
scripts/render_prep_doc.py
scripts/run_prep.py
tests/
```

Do not include secrets, local `.env`, personal auth files, local cache, or generated private outputs.
