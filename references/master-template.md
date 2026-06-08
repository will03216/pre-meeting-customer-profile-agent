# Master Template Structure

Source fetched with:

`lark-cli docs +fetch --doc https://bytedance.sg.larkoffice.com/docx/KxPkdR5m3oaFQtx0Hpsl0TQsgTc --format pretty`

Template title: `[CustName] Profile and StandardAction`.

For pre-meeting prep, preserve this structure but retitle as:

`BytePlus <> [Customer Name] - DD-MM-YYYY - Pre-Meeting Prep`

## Section 1: Background

Render a 2-column table, `Field | Value`, with these exact field labels from the master:

1. Client Name/Nation
2. AE
3. Domain/Industry
4. Stakeholders
5. Key Use Case
6. Servicing Region(s)
7. Objectives
8. Risk
9. Competitor
10. Reference

Note: The portable prep template uses the corrected spelling `Objectives`.

The master also includes three preparation sub-blocks:

- Essential background check
- Prepare Internal Hypothesis
- Meeting Readiness

In pre-meeting mode, fill these as internal prep hypotheses and readiness links when available.

## Section 2: Live Interview Script

The fetched master names this section `Standard Question Prompt`. In this skill, render it as `Live Interview Script / Standard Question Prompt`.

Add `Suggested Questions for This Meeting` above the static script. Make this block folded/collapsed by default if the Lark docx API supports folding. If folding is unavailable, use a callout or heading and continue.

Preserve these master script blocks:

1. Standard Discovery Questions
2. AI Usage & Current Stack
3. Current AI Adoption
4. Vendor & Competitor Understanding
5. Switching Mechanism
6. LLM Usage
7. Image / Video Usage
8. Business Scenarios & Use Cases
9. Core Use Cases
10. Priority & Urgency
11. Pain Point Discovery
12. Technical Pain Points
13. Commercial Pain Points
14. Compliance & Data Concerns
15. POC Qualification
16. Technical Readiness
17. Timeline
18. Success Criteria
19. Commercial & Procurement Signals
20. Budget & Commitment
21. Expansion Opportunity
22. Cross-Sell / Upsell Discovery
23. Future Opportunities
24. Organizational Expansion
25. Competitive Replacement Questions
26. Example Questions
27. Positioning Examples

The draft spec mentions 13 sub-blocks, but the fetched template contains the above nested block list. Treat the fetched template as source of truth.

## Section 3: Client Engagement

Render a 4-column table:

`Date | Stage | Key Information | Next Step`

For pre-meeting generation:

- Import prior engagement rows for the same customer, newest first.
- Add this placeholder row:
  - Date: meeting date as `DD-MM-YYYY`.
  - Stage: `Pre-Meeting`.
  - Key Information: source attribution based only on content available during the run.
  - Next Step: `Validate assumptions during the customer meeting; update after AI Notes / Minutes are available.`

Allowed stage values:

`Pre-Meeting`, `Discovery`, `POC`, `Negotiation`, `Closed-Won`, `Closed-Lost`, `Renewal`, `Expansion`.

If no prior docs exist, render `No prior BytePlus customer profile found.`

## Section 4: Meeting Output Template

The fetched master table is `Category | Notes` and contains these categories:

1. Customer Stage
2. Core Business
3. Main AI Use Cases
4. Current Models
5. Current Vendors
6. Monthly Volume
7. Paid Users
8. Pain Points
9. Budget Status
10. Contract / Commitment
11. POC Timeline
12. Expansion Opportunity
13. Competitor Risk
14. Cross-Sell Potential
15. Next Action

The draft spec compresses these into 11 rows, but the original master has 15 categories. Preserve the fetched master categories and pre-fill each note as `Known:`, `Likely:`, or `To Validate:`.

## Section 5: Risk & Support

The fetched master headings are:

- Risk&Support
- Case Study(domstic/overseas)
- Pricing Proposal
- Solution Proposal
- Others

For pre-meeting mode:

- Under `Risk&Support`, include known risks from prior docs and likely risks with `(?)`.
- Preserve manual scaffolds for Case Study, Pricing Proposal, and Solution Proposal:
  - Case Study: `What you need | For which stakeholder/use case | Domestic or overseas | By when`
  - Pricing Proposal: `Volume | Commitment term | Models | Competitor price to beat | By when`
  - Solution Proposal: `What the customer is building | BytePlus products in scope | Technical concerns | Format | By when`

## Section 6: Reference

Replace the master shared-material references with a pre-meeting reference block:

- This Upcoming Meeting: Calendar event link.
- Available Internal Context: prior customer docs, prior AI Notes/Minutes, Mira or KB results, enrichment source when permitted.
- Customer History: dated links to prior docs.

If a source is unavailable, prefer a concise line such as:

- `No prior customer profile found.`
- `No prior AI Notes found.`
- `MCP enrichment unavailable.`

Do not render the master-template link or shared-materials line unless the user explicitly asks for it.
