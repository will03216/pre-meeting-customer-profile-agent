# Meeting Qualification

Qualify a meeting only when all rules pass:

1. Event is on the SA primary calendar.
2. Event start is in the future and at least `PRE_MEETING_MIN_NOTICE_HOURS` away unless manually forced.
3. Event has at least one attendee with `type=third_party`, `is_external=true`, or an email domain outside the configured internal domains.
4. Title does not match an internal-only pattern.

Internal-only title patterns are case-insensitive:

`1:1`, `standup`, `sync`, `all hands`, `team meeting`, `onboarding`, `training`, `interview`, `OOO`, `WFH`, `holiday`, `lunch`, `coffee`, `office hours`, `review`, `retro`, `planning`, `townhall`, `focus`, `block`, `tentative`.

Edge rules:

- Do not treat free-mail domains as companies: `gmail.com`, `googlemail.com`, `yahoo.com`, `outlook.com`, `hotmail.com`, `live.com`, `icloud.com`, `me.com`, `proton.me`, `protonmail.com`, `qq.com`, `163.com`, `126.com`.
- Resolve personal-email attendees through overrides, meeting title, enrichment, or internal search.
- Internal-domain external meetings, such as other BytePlus or ByteDance regions, should be flagged for manual confirmation instead of skipped automatically.
- If attendees are unavailable, continue only for manual runs or when title/domain evidence strongly indicates a customer meeting. Mark stakeholder fields as `TBD - please confirm`.
