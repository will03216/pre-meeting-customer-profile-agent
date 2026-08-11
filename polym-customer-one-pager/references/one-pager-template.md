# Account Plan (一客一策) Template

> **Skeleton source:** Volcano Engine standard blank template (doc1 R7GW)
> **Style references:** Havas one-pager (W0Snd — the target style: ⭐ highlights callout, grid columns, **narrative** partnership status, ~2 tables total) + 爱诗科技/PixVerse (KXQ0, best AI-customer fit) + 广实 2024 (Ovm1d) & 广州实验室 (GUzR — the dense partnership-status callout, defend/attack framing, real account plans)
> **Synthesis inputs:** prospection (pre-meeting profile) + meeting notes (post-meeting record) + SA manual inputs

---

## 🎯 What this document IS (read before filling)

A one-pager is **not a prospection report**. Prospection is research *about* the customer; the one-pager is **our running playbook** — distilled intelligence + **our strategy + our actions + our progress over time**. Its job is to let anyone glance at it and know: where we stand, what we're doing next, and whether usage/cooperation is scaling.

**Four design principles (override the old table-heavy style):**

1. **Distill, don't dump.** Every paragraph from prospection → compress to a **bolded bullet** or a one-line judgement. If a fact doesn't change a decision or an action, cut it. The reader wants the signal, not the research.
2. **Tables are the exception, not the default.** Use prose + **bold** + nested bullets + callouts for almost everything. Reserve real tables for the **~4 genuinely tabular, trackable** things: Engagement Log, Strategy & Targets, Opportunity List, Quarterly Action Plan. Everything else is bullets. A wall of tables reads like prospection and hides the story.
3. **Lead with us, not them.** The center of gravity is Section 3 (Opportunity / **Partnership Status** narrative) and Section 9 (**our** strategy & action plan). Company background is context — keep it tight.
4. **Say it once — every fact has ONE home.** Each number/signal/pain gets stated **in full in the one section where it belongs**, then only *referenced* (not re-explained) elsewhere. A commitment figure (e.g. "400K/700K") lives in **§3 Partnership Status** + its tracking table; §6/§7/§9/§11 may *point to* it ("the 400K tier") but must not re-narrate it. A pain point (e.g. latency) is named once in **§3 Blocked** and turned into an action in **§9 Risk-defense** — it does not also fill a §1 "Challenges" bullet and a §5 line. **Self-check before finishing (mandatory):** pick your 2-3 headline facts (top number, top pain, top competitor) and count how many times each is *spelled out in full* — **target ≤2 full spell-outs each; at 3+ you're already drifting** → collapse the extras to a back-reference (e.g. "the privacy narrative (§3)"). A headline fact like a competitive narrative, a cost % (e.g. "VFX = 40% of budget"), or an ownership flag belongs in ONE home + brief pointers, never re-narrated in Highlights AND §5 AND §9. Repetition across "lenses" is the #1 way this doc drifts back into a bloated prospection report. **⚠️ Sparse accounts (first meeting, only 3-4 hard facts) are MORE prone to this, not less** — with few signals, the temptation is to restate the same VFX-cost / privacy-narrative / ownership-risk fact in every section to fill space. Don't pad. A short, tight one-pager that states each fact once beats a long one that recycles a handful of facts across §1/§3/§5/§9. If a first-meeting account only yields a thin doc, that's correct — leave it thin.

**🔄 It's a living document — updated in place, not regenerated.** After each new meeting, run the skill in **Update mode**: feed the existing one-pager + only the new meeting notes, and the skill **merges incrementally into the same doc** (`docs +update --api-version v2 --command overwrite` on the original doc_id). The Engagement Log accumulates rows over time; ratings change only on new evidence; **already-filled internal numbers are preserved, never reset to `[TBD]`**; and §8 Retrospective appears once the account spans multiple quarters with comparable wins/losses. Never re-run from scratch into a new doc — that loses history and filled numbers. See SKILL.md §8.5.

**Visual style (Lark rich elements — use them):**
- Open with a `<callout emoji="⭐" background-color="light-blue">` **Highlights** block (blue background is the default for the summary), heavy **bold** on the numbers that matter (rating, headcount, revenue, committed volume, # users live). Note: the markdown layer only supports the `light-<hue>` color tier (`light-blue`, `light-green`, `light-red`, `light-purple`, …); `medium-blue`/`dark-blue`/other tokens are silently dropped, so always use `light-blue`.
- Use `> ` **blockquote callouts** to make key state "blue/boxed" — partnership status, dense analysis, internal-sensitive warnings.
- Use `<grid><column width-ratio="0.5">…</column><column width-ratio="0.5">…</column></grid>` for side-by-side strategic initiatives or land/expand pairs.
- **Bold** the lead phrase of every bullet (the category / the verdict), then explain.
- Bracketed category tags for challenges/levers: **【Market】**, **【Cost】**, **【Compliance】**.

---

## ⚠️ Template Compliance Rules (do not violate)

1. **Section names follow the template exactly** — do not add/remove/rename/invent. (One sanctioned exception: **§8 Retrospective is optional** — omit it entirely for single-snapshot accounts and renumber §9–12 → §8–11, per the §8 note.)
2. **Only the four core tables stay as tables** (Engagement Log, Strategy & Targets, Opportunity List, Quarterly Action Plan). Other historically-tabular sections are now **bullets/callouts** — do not re-tableize them. (One small metadata strip + optional financials table are allowed.)
3. **Every field must be filled**: source available → content; no source → `[TBD]`; never leave blank, never fabricate.
4. **Internal-sensitive numbers** (revenue targets, wallet share, budget, discounts, individual scores) with no explicit SA input → `[TBD]`, never inferred.
   - **🔵 Every `[TBD]` MUST render in blue text:** write it as `<text color="blue">[TBD]</text>` (bracketed notes too, e.g. `<text color="blue">[TBD — SA to break down]</text>`). This makes every manual-fill gap jump out the instant someone opens the doc, so they instantly see what's missing and who must fill it. **Never emit a bare, uncolored `[TBD]`** anywhere in the generated doc. (Syntax note: only `<text color="…">` survives the Lark markdown layer — `<font color>` is silently dropped. Verified working colors: `blue`, `green`, `red`.)
5. **Whiteboards / architecture diagrams / embedded sheets**: keep the `> 📌` placeholder note, do NOT substitute a table.
6. **🔒 OUTPUT LANGUAGE IS ALWAYS ENGLISH — PERMANENT RULE.** Regardless of the language of the prospection, the meeting notes, or ANY reference/example provided (which are frequently Chinese), the final one-pager is **always written in English**. The only exception: keep customer/product/brand names in their original form (e.g. Seedance, ModelArk, Seedream, Runway, Veo, 火山引擎→"Volcano Engine"/"BytePlus"). Section headings, table headers, descriptions, and all prose are English. Do not switch to the example's language.
7. **Conflicts: meeting notes win**, keep the old value as a note: `(prospection had X, meeting updated to Y)`. **⚠️ ASR exception:** when the conflict is a *clean prospection figure* vs. a *garbled ASR figure* (country/office counts, user counts, cost %, cycle times spoken in a raw transcript), "meeting wins" does **not** apply — ASR numbers are low-confidence. Keep the prospection value, or keep it and tag the meeting value `<text color="blue">[confirm]</text>`. Never let transcript noise overwrite a verified fact. "Meeting wins" is for **judgement/attitude updates** (decision chain, opportunities, blockers), not for overturning established factual numbers.
8. **To Do & action items are traceable: absolute date + source, always.** No relative dates ("this week", "July", "before the rollout") — convert to a concrete `YYYY-MM-DD`/`YYYY-MM` anchored to the meeting date, or blue the unknown (`<text color="blue">[TBD date — <trigger>]</text>`). Every action ends with `src: <YYYY-MM-DD> mtg, <who raised/agreed>` so a colleague can trace which meeting and which person each commitment came from. The §12 Reference Materials whole-doc URL is **not** sufficient provenance for individual actions. Same applies to the **Milestone** column of the Quarterly Action Plan — use absolute dates, not "end-June".
9. **Keep total under 50,000 characters.** Distilling helps here — if you're near the limit, you're dumping, not distilling.

---

## Template Body (copy and fill)

```markdown
**Account Plan · <COMPANY_NAME>** ｜ Team: <e.g. Byte+ EUI Global-500> ｜ AE: <name or <text color="blue">[TBD]</text>> ｜ SA: <name> ｜ CSM: <name or <text color="blue">[TBD]</text>> ｜ Updated: <YYYY-MM-DD> ｜ Status: Draft / Maintained

<callout emoji="⭐" background-color="light-blue">
- **Who:** <one line — industry, scale, what they do; e.g. "Top-3 European media group, 23,000+ staff, €2.9B revenue, AI-transformation at the core">
- **Partnership rating:** Text **[H/M/L]** · Image **[H/M/L]** · Video **[H/M/L]**
- **Where we stand:** <one line — e.g. "Seedance pilot live with ~60 users in France; full rollout to ~23k targeted by end-June">
- **The prize:** <core opportunity in one line + est. value or <text color="blue">[TBD]</text>>
- **Main threat:** <incumbent competitor & lock-in, one line>
- **Next move:** <the single most important next action + owner + date>
</callout>

---

# 1. Customer Overview

> _**HARD CAP: 8 bullets for this ENTIRE section** — Company Profile + Business Model & Products + Business Challenges **combined**, not 8 each. This is context, not the story. Compress prospection paragraphs into bold-led bullets, **collapse brand/product lists into ONE bullet** (don't give each subsidiary its own line), and drop anything §3/§5/§9 already carries. **Self-check before moving on: count the bullets in §1 — if >8, you're writing a prospection, cut back.** A first-meeting account should leave §1 thin; that's correct, not incomplete._

## Company Profile

- **Company:** <name>, <industry>, <type (public/SOE/foreign/unicorn)>, founded <year>, HQ <city/country>
- **Scale:** <headcount>, revenue <amount>, present in <# markets>
- **Core business:** <one sentence>
- **AI maturity:** Level <1-5> — <one sentence, e.g. "10+ in-house AI products in production, millions of daily LLM calls">
- **Parent / group:** <if any, and its pull on purchasing decisions>
- **Recent signals:** <YYYY-MM> <event> · <YYYY-MM> <event> _(source)_

> _Optional financials table — include ONLY if revenue/profit trend actually informs strategy; otherwise drop it and keep the one-line "Scale" bullet above. **Put the table flush-left, NOT inside this `>` blockquote** — a markdown table nested in a blockquote (or a callout) silently collapses into one run-on paragraph (e.g. "Financials(€)2024TrendRevenue~€1.2B…"). The intro note can be a blockquote; the table that follows must start at the left margin._

| Financials | <Y-2> | <Y-1> | This yr (est.) | Target yr |
|---|---|---|---|---|
| Revenue | | | | |
| Net profit | | | | |

## Business Model & Products

> _Merged on purpose — one tight block. Lead with how they make money, then list **only the 2-3 products/brands that matter to OUR opportunity**. Collapse the rest into a single "Other brands:" line — do NOT give every subsidiary its own bullet._

- **How they make money:** <1-2 sentences — core segments + revenue model; add revenue mix inline if known, else <text color="blue">[TBD]</text>>
- **<Product/brand that matters to us, e.g. Vermeer.ai>** — <type> · <key metric, e.g. "100+ countries, -50% TV ad cost"> · models: <e.g. Runway Gen-4, Veo>
- **Other brands:** <one line, e.g. "Fresco Film (service prod.), Cimarrón (LatAm) — context only">

## Business Challenges

> _**Optional — include ONLY if it adds a pain not already covered by §3 Blocked / §5 Competitive / §9 Risk-defense.** The pains we're actively solving live in §3/§9; this bullet is for *structural / business-level* challenges that frame why they buy AI at all (e.g. shareholder growth pressure, brand-consistency at scale). If everything here would just repeat a downstream section → **drop this subsection entirely.** Max 2-3 bullets._

- **【<tag, e.g. Growth pressure>】** <structural challenge, e.g. "post-spinoff shareholder pressure → AI is the differentiation thesis">
- **【<tag>】** <description>

---

# 2. Strategic Goals & Direction (<YYYY>-<YYYY>)

> <strategy core in one sentence — e.g. "AI transformation at the core, full platformization">

> _Each direction is its own **full-width blue callout** (`background-color="light-blue"`), stacked top to bottom. Under the bold title, list the concrete targets/initiatives as a **numbered 1/2/3 list with a blank line between items** — that blank line keeps them flat 1/2/3 (inside a `<grid>` the blank lines collapse and the list nests, so do **not** wrap these in a grid)._

<callout emoji="🎯" background-color="light-blue">
**1. <Direction, e.g. AI-driven org transformation>**

1. <target/initiative, e.g. "AVA LLM portal live to 22,000+ staff">

2. <target, e.g. "Converged.AI OS as group platform">

3. <target>
</callout>

<callout emoji="🎯" background-color="light-blue">
**2. <Direction, e.g. AI content industrialization>**

1. <target, e.g. "Vermeer multi-model wrapper">

2. <target, e.g. "-50% TV ad production cost">
</callout>

<callout emoji="🎯" background-color="light-blue">
**3. <Direction, e.g. globalization / M&A>**

1. <target>

2. <target>
</callout>

---

# 3. BytePlus <> <COMPANY_NAME> Opportunity

> ⭐ **This is the core of the document.** Spend your best effort here. **Order matters: lead with where we stand (Partnership Status), then the rating + directions.**

## Partnership Status (合作情况)

> _Put this **first** — it's the one thing a reader needs. Keep it **short and pointed**: state, not prose. One line each, only what moved. New customer → "New customer, no engagement yet; first opportunities below." Update every time something moves._

- **Background:** <how we got in — one line>
- **Live now:** <what's in production, e.g. "Seedance pilot, ~60 users in France creative team">
- **In motion:** <what's progressing + timeline, e.g. "rollout to ~23k staff targeted end-June; 400K/700K commitment under decision">
- **Blocked / at risk:** <e.g. "US legal team has an unresolved internal dispute slowing group sign-off">
- **Recap (so far):** <one-line "how we got to today" judgement — the folded §8 retrospective. e.g. "From a warm eval to live France production in weeks; relationship solid (2 champions); only blockers are latency + the commitment decision." Omit on a brand-new account with no history yet.>

## Partnership Rating & Directions

> _Rating + where we play, together. Each rating line carries its rationale; directions are the concrete plays that follow._
>
> ⚠️ **Ratings start from prospection; meeting silence is NOT a downgrade.** A rating reflects the *structural* opportunity (scale, use-case fit), not what a single meeting happened to dwell on. Do **not** drop a prospection rating just because the meeting focused elsewhere — a video-heavy first meeting doesn't make Image "M" if the localized-asset demand is still there. **Only change a rating on positive evidence** (the customer said image isn't relevant / a competitor owns it / a real blocker emerged). **If you do change one, annotate the conflict:** `Image — M (prospection had H; meeting centered on video, image not yet probed)`.

- **Text / LLM — [H/M/L]:** <one-line rationale, e.g. "AVA runs GPT-5/Claude on a multi-model arch; BytePlus LLM plugs in directly">
- **Image — [H/M/L]:** <rationale>
- **Video — [H/M/L]:** <rationale, e.g. "Vermeer is Runway-led; Seedance is the APAC/compliance alternative">
- **Estimated annual revenue:** <amount or <text color="blue">[TBD]</text>>

**Primary directions:**
1. **<Direction, e.g. Video Gen (Seedance)>** — <entry point & scenario, e.g. "plug into Vermeer as APAC-exclusive video gen; Cannes Lions joint campaign">
2. **<Direction, e.g. LLM / ModelArk>** — <entry point>
3. **<Direction>** — <entry point>

## Engagement Log

> _One row per touchpoint, most recent last. No meetings yet → "No engagements logged yet."_

| Date | Format | Customer attendees | BytePlus attendees | Key topics & signals | Outcome / next step |
|---|---|---|---|---|---|
| <YYYY-MM-DD> | <onsite/VC/call> | <names + titles> | <names or <text color="blue">[TBD]</text>> | <what was discussed; quantified signals here too> | <decision / action / blocker> |

## Strategy & Targets

| Metric | Current status | Current scale | Target | Notes |
|---|---|---|---|---|
| <e.g. Video usage/mo> | <pilot / not started> | <number or <text color="blue">[TBD]</text>> | <target> | |
| <e.g. # onboarded users> | | | | |
| <e.g. Revenue/yr> | | <<text color="blue">[TBD]</text>> | <<text color="blue">[TBD]</text>> | |

---

# 4. Core Decision Team

## Org Chart

> 📌 **Needs manual add: decision-chain whiteboard**

- **Decision chain:** <one line if known, e.g. "Technical eval (CTO) → strategic rec (CSO) → economic approval (CEO) → group sign-off">

## Key Decision Makers

| Name | Title | Role | Attitude | Notes (KPI / pain / leaning) |
|---|---|---|---|---|
| <name> | <title> | Final / Primary / Influencer / Executor | Champion / Optimistic / Neutral / Detractor | <e.g. "owns AI budget; cares about cost-per-render; source: meeting"> |

_No meeting notes → attitude defaults to Neutral. For a Detractor, note the leaning in the Notes column (e.g. "leans Alibaba Cloud"). Update post-meeting._

> _**Decision-makers by product line** — include ONLY for enterprises with formal, separate product-line procurement (cloud infra / security / data / etc.). For media/agency/AI-native customers this rarely fits → **skip it** and instead add a bullet per key person noting their **specific** evaluation criterion (KPI / pain / eval standard, e.g. "cost-per-render", "compliance/provenance", "latency vs. incumbent"). Never write "quality & price."_

## IT Procurement Process

- **<step, e.g. technical evaluation>** → <goal> · lead: <role>
- **<step, e.g. budget approval>** → <goal> · lead: <role>
- _No info → <text color="blue">[TBD]</text>_

---

# 5. IT Architecture & Competitive Landscape

## IT System Architecture

> 📌 **Needs manual add: IT system architecture diagram**

- **Primary cloud(s):** <vendor & use, e.g. "Google Cloud — core AI infra, Pencil Pro lock-in">
- **AI models:** <e.g. "GPT-4o / Claude / Gemini / Llama — multi-model API calls daily">
- **Ad/content & data stack:** <e.g. "TikTok Ads, DV360, BigQuery, Tableau">
- **In-house AI products:** <e.g. "Share of Model™ / Vermeer / AVA">

## Competitive Situation

> _Bullets, not a vendor matrix. One bullet per incumbent: who they are, lock-in level, and our entry angle. Real share/discount numbers go in the dense callout above; here give the judgement._

- **<vendor> (<product>) — lock-in [H/M/L]:** <e.g. "Pencil Pro locks GCP at group level — not a replacement target; entry via APAC coverage gap">
- **<vendor> (<product>) — lock-in [H/M/L]:** <e.g. "OpenAI + Anthropic consumed as APIs; multi-model arch is open to adding a vendor">
- **Real on-account share:** <<text color="blue">[TBD]</text> — pull from meeting notes>

---

# 6. Budget Distribution & Opportunities

## IT Wallet Depth

- **Total IT wallet (/yr):** <amount + trend, source meeting-notes-first; pure inference → <text color="blue">[TBD]</text> with basis noted>

> 📌 **Needs manual add: business architecture diagram (business-line tree; mark BytePlus-engaged parts green)**

## Opportunity List

| Opportunity | Budget est. | Solution owner | Current blocker | Status |
|---|---|---|---|---|
| <opp, e.g. Seedance into Vermeer> | <amount or <text color="blue">[TBD]</text>> | <name> | <blocker> | Pilot / POC / Not started / Delivered |

---

# 7. Revenue Target & Wallet Share

> ⚠️ **Internal-sensitive — filled by SA/AE manually. No source → <text color="blue">[TBD]</text>, never inferred.** Keep this short; it's a few numbers, not tables.

- **Revenue target:** <text color="blue">[TBD]</text>
- **Wallet share:** <text color="blue">[TBD]</text>
- **H1/H2 growth target:** <text color="blue">[TBD]</text>
- **Winback / migration target:** <text color="blue">[TBD]</text>
- **By product line / by quarter:** <text color="blue">[TBD — SA to break down]</text>

---

# 8. Retrospective  ← OPTIONAL SECTION

> _**Default: OMIT this section entirely — no heading, no placeholder text — and renumber the following sections up by one** (Follow-up Strategy becomes §8, Resource Requests §9, To Do §10, Reference Materials §11). A single-snapshot account has no separate retrospective worth keeping: the wins/losses already live in §3's Live now / In motion / Blocked + the §3 **Recap (so far)** line, and the relationship in §3 Background + §4 Notes._
>
> _**Include this section (as `# 8. Retrospective`, keeping the original 8–12 numbering) ONLY when** the account has run across multiple quarters with comparable, cross-period wins/losses (e.g. "Q1 onboarded 3 teams, Q2 lost the LLM slot to AVA, net usage +40% QoQ") that a single §3 snapshot cannot carry. When you do include it:_

- **Performance:** <under 120 words, quantify cross-period wins/losses/growth/cross-sell>
- **Key relationships:** <how key-person relationships shifted over time>

---

# 9. Follow-up Strategy

> ⭐ **The other core section — this is OUR plan.** What we do, who owns it, when it lands.

## Commercial Strategy (Sales: <AE name or <text color="blue">[TBD]</text>>)

> _6 levers as a checklist — fill what applies, mark the rest <text color="blue">[TBD]</text>/"n/a". Each lever is a distinct play, not one flat paragraph._

- **1. Pricing & commercials:** <e.g. "stay market-competitive; commit-tier discount on volume">
- **2. Account care / cadence:** <e.g. "weekly online sync; monthly review">
- **3. Land (opportunity plays):** <core entry, e.g. "Seedance pilot → full rollout; ModelArk as 5th LLM into AVA">
- **4. Expand (cross-sell):** <how one win pulls the next, e.g. "video win → upsell LLM in same workflow; replicate France rollout to other regions">
- **5. Strategic / ecosystem:** <e.g. "Cannes Lions co-marketing; ByteDance strategic-investment intro">
- **6. Risk & defense:** <what loses the account + countermove, e.g. "lock Seedance into production before Runway renewal window">

## Product / Solution (SA: <SA name>)

- **<Lead product, e.g. Seedance>** → enter via <dept> · pain: <e.g. "J+ suite has no video gen"> · edge: <e.g. "ByteDance owns TikTok — strongest provenance story"; **include reference customers / proof points WE cited in the meeting** — e.g. "already powering Babelsberg & Globo"> · play: <e.g. "pilot one brand client">
- **<Product, e.g. ModelArk>** → enter via <dept> · pain: <…> · edge: <…>

> 🏅 **Reference cases WE cited belong here.** When BytePlus name-drops a flagship customer, same-industry case, partner, or live demo to build credibility, capture it in the relevant product's `edge:` (and, if it reveals what the customer responds to, echo one line in §3 Directions + the §3 Engagement Log topic column). **If the meeting was ASR and the reference name is garbled, still surface the FACT that we cited an industry flagship** (restore per the ASR rule / mark blue) — do **not** let it survive only as a garbled name in the §11 source caveat.

## Quarterly Action Plan & Milestones

| Direction | Need | Action — Sales | Action — SA | Action — Product | Milestone / progress |
|---|---|---|---|---|---|
| <e.g. Video / Seedance> | <need> | <action> | <action> | <<text color="blue">[TBD]</text>> | <absolute dates, e.g. "pilot done 2026-06-15; full launch 2026-06-30"> |

## Brand Marketing / Ecosystem

- <joint PR, industry-event sponsorship, ecosystem partners; none → <text color="blue">[TBD]</text>>

---

# 10. Resource Requests

> _Customer's asks of BytePlus (from notes) + internal support we need. First-time file may list expected asks._

1. <ask, e.g. "airport ad resources — customer's urgent exposure need">
2. <ask, e.g. "GPU elastic scaling on demand at competitive price">
3. <<text color="blue">[TBD]</text> — confirm at next meeting>

---

# 11. To Do

> _**Every action carries (a) an absolute target date and (b) a source.** This section is a live tracker that someone else may pick up — it must stand on its own with no tribal knowledge._
> - **No relative dates.** Convert "this week" / "next month" / "by July" / "before the rollout" into a concrete `YYYY-MM-DD` anchored to the meeting date (use the meeting date in §3 Engagement Log as the anchor — e.g. a meeting on 2026-06-16 + "this week" → `2026-06-20`, that week's Friday). If only a month is known, write `YYYY-MM`. If the date depends on a milestone whose date isn't set yet, write `<text color="blue">[TBD date — before the 23k rollout]</text>` (keep the trigger, blue the unknown).
> - **No source-less actions.** Each item ends with the meeting it came from + who raised / agreed it. If the source is genuinely unknown, mark `source: <text color="blue">[TBD]</text>` — never drop the slot._

## <current quarter, e.g. 2026 Q2>

1. **[<Owner>]** <specific action> — _target: <YYYY-MM-DD>_ · _src: <YYYY-MM-DD> mtg, raised by <name> / agreed with <name>_
2. **[<Owner>]** <action> — _target: <YYYY-MM-DD>_ · _src: <YYYY-MM-DD> mtg, <who said/owns it>_

## <next quarter>

1. <text color="blue">[TBD — set after this quarter's milestones land]</text>

---

# 12. Reference Materials

| Material | Link |
|---|---|
| Prospection doc | <prospection_url> |
| Meeting notes | <meeting_notes_url or "none"> |

**Data freshness:** Synthesized <DATE>. Prospection as of <DATE>; meeting notes as of <DATE>. Update directly in this doc going forward.

> _**Source caveat — include this callout ONLY when the meeting notes were a raw ASR transcript** (broken sentences, `Speaker 1/2/3`, misspelled proper nouns). Omit it when notes were clean/AI-summarized._
>
> ⚠️ **Source caveat:** the meeting notes are a **raw auto-transcript (ASR)** — speaker names, attendee names, and some figures (cost %, cycle times) are approximate and need verification before being quoted externally.

**Open items <text color="blue">[TBD]</text>:** <list every <text color="blue">[TBD]</text>, especially revenue target / wallet share / key-person attitudes / opportunity budgets.>
```

---

## Lark Formatting Notes

1. `<callout emoji="⭐">…</callout>` → renders as a Feishu Callout box. Use it for the Highlights header block. (A leading `> ⭐ **…**` blockquote also renders as a callout if the explicit tag fails.)
2. `> 📌 **Needs manual add: …**` → placeholder for a whiteboard/architecture diagram; renders as a callout. Never substitute a table.
3. `<grid><column width-ratio="0.5">…</column><column width-ratio="0.5">…</column></grid>` → two-column side-by-side layout. Use for short paired items. ⚠️ **Do NOT put a numbered list inside a grid column** — the grid collapses the blank lines and the list nests (1 → 1.1 → 1.2). For numbered lists use a stacked full-width callout instead (note 8).
4. `<callout background-color="light-blue">**Title**` + blank line + `1.` / blank line / `2.` …`</callout>` → **blue area with a clean 1/2/3 list**. Stack these full-width (no grid). The **blank line between each numbered item is required** — without it Lark nests the items. Used for Section 2 strategic directions. Only the `light-<hue>` color tier survives (`light-blue`, `light-green`, …).
5. `> ` blockquote → boxed/"blue" emphasis for partnership status, dense analysis, internal-sensitive warnings.
6. **Bold** the lead phrase of every bullet — it's the scan layer.
7. **🔵 Blue text marks every manual-fill gap.** Wrap each `[TBD]` as `<text color="blue">[TBD]</text>` so unfilled fields are unmistakable at a glance. Use `<text color="…">` only (`<font color>` is dropped by the markdown layer). On round-trip Lark may split the tag (e.g. `<text color="blue">[</text><text color="blue">TBD]</text>`) — that's cosmetic; the color is preserved and it renders blue.
8. Only the four core tables render as markdown tables: Engagement Log, Strategy & Targets, Opportunity List, Quarterly Action Plan (plus the small metadata strip + optional financials). Everything else is bullets.
9. Whiteboards / embedded Sheets / images cannot be created via markdown → placeholder note only; SA adds manually.
10. **🚫 Never nest a markdown table inside a `>` blockquote or a `<callout>`.** The pipe-table syntax only parses at the top (flush-left) level. Indented under a blockquote/callout it collapses into a single run-on paragraph with all cells concatenated. This catches the **optional financials table** most often (its intro note is a blockquote — keep the note as `>`, but drop the table to the left margin). If you want a "boxed" look, put the `>` note *above* the table, never around it. Same rule for the 4 core tables: always flush-left.

## Section Priority (when content is sparse)

Fill order — front-load the parts that read as "our playbook," not "research":
1. ⭐ Highlights callout (rating + where we stand + next move)
2. Section 3 Opportunity — **Partnership Status narrative + Strategy & Targets** (most important)
3. Section 9 Follow-up Strategy — **our** 6-lever plan + Quarterly Action Plan
4. Section 1 Customer Overview (tight context)
5. Section 4 Decision Team
6. Section 6 Budget & Opportunities
7. Section 5 IT Architecture & Competition
8. Section 7 Revenue Target
9. Section 8 Retrospective (OPTIONAL — omitted entirely by default + renumber; included only for multi-quarter accounts)
10. Sections 10/11/12 Resource Requests / To Do / References

## Source Annotation Rules

Keep annotations light — inline `_(source)_` only where provenance matters (a disputed number, a key attitude). Don't tag every bullet; over-annotation reads like a research report.
- `(prospection)` — pre-meeting profile
- `(meeting)` — meeting notes
- `(SA)` — SA manual input
- `[TBD]` — no source, needs manual fill
