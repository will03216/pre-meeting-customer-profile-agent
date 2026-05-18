#!/usr/bin/env python3
"""Render a BytePlus pre-meeting customer profile draft from normalized JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TBD = "TBD - please confirm"
TO_VALIDATE = "To Validate"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_dt(value: str, tz_name: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    tz = ZoneInfo(tz_name or "Europe/London")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def val(value, fallback: str = TBD) -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, list):
        return "\n".join(str(v).strip() for v in value if str(v).strip()) or fallback
    return str(value)


def join_non_empty(items, sep: str = "; ", fallback: str = "") -> str:
    if items is None:
        return fallback
    if isinstance(items, str):
        return items.strip() or fallback
    values = [str(item).strip() for item in items if str(item).strip()]
    return sep.join(values) if values else fallback


def strip_confidence_prefix(text: str) -> tuple[str | None, str]:
    clean = (text or "").strip()
    for prefix, key in [
        ("Known:", "known"),
        ("Likely:", "likely"),
        ("To Validate:", "to_validate"),
        ("Not Found:", "not_found"),
    ]:
        if clean.lower().startswith(prefix.lower()):
            return key, clean[len(prefix):].strip()
    return None, clean


def labeled_text(value: str | list | None, label: str, fallback: str = TO_VALIDATE, evidence: str = "", followup: str = "") -> str:
    text = join_non_empty(value, fallback=fallback)
    existing_label, clean = strip_confidence_prefix(text)
    label = existing_label or label
    if label == "known" and clean.lower().startswith(("to validate", "not found")):
        label = "to_validate" if clean.lower().startswith("to validate") else "not_found"
    prefix = confidence_label(label)
    suffix = " (?)" if label == "likely" and "(?)" not in clean else ""
    result = f"{prefix}: {clean}{suffix}"
    if evidence:
        result += f" Evidence: {evidence}."
    if followup:
        result += f" Follow-up: {followup}"
    return result


def person_text(person: dict | None) -> str:
    if not person:
        return TBD
    name = person.get("name") or person.get("email")
    email = person.get("email")
    if name and email and name != email:
        return f"{name} ({email})"
    return val(name or email)


def likely_list(items, fallback: str = TO_VALIDATE) -> str:
    if not items:
        return fallback
    return "; ".join(f"Likely: {item} (?)" for item in items)


def known_or_likely(value: str | list | None, confidence: str | None, fallback: str = TO_VALIDATE) -> str:
    if not value:
        return fallback
    return labeled_text(value, "known" if confidence == "high" else "likely", fallback=fallback)


def table(rows: list[tuple[str, str]]) -> str:
    out = ["| Field | Value |", "| --- | --- |"]
    for k, v in rows:
        cell = val(v).replace("\n", "<br>")
        out.append(f"| {k} | {cell} |")
    return "\n".join(out)


def output_table(rows: list[tuple[str, str]]) -> str:
    out = ["| Category | Notes |", "| --- | --- |"]
    for k, v in rows:
        out.append(f"| {k} | {val(v, TO_VALIDATE).replace(chr(10), '<br>')} |")
    return "\n".join(out)


def confidence_label(value: str | None) -> str:
    mapping = {
        "known": "Known",
        "likely": "Likely",
        "to_validate": "To Validate",
        "not_found": "Not Found",
        "confirmed": "Known",
    }
    return mapping.get((value or "").lower(), val(value, "To Validate"))


def ensure_note(text: str, fallback: str) -> str:
    clean = val(text, fallback)
    if any(label in clean for label in ("Known:", "Likely:", "To Validate:", "Not Found:", "Follow-up:", "Evidence:")):
        return clean
    return fallback


def append_followup(text: str, followup: str) -> str:
    clean = val(text, TO_VALIDATE)
    if "Follow-up:" in clean:
        return clean
    return f"{clean} Follow-up: {followup}"


def source_rank(url: str) -> int:
    host = url.lower()
    if "larkoffice.com" in host or "feishu.cn" in host:
        return 1
    if "naturalint.com" in host or "imagine.art" in host or "goroka.tv" in host:
        return 2
    if "linkedin.com" in host or "crunchbase.com" in host or "pitchbook.com" in host:
        return 3
    return 4


def best_evidence_url(data: dict) -> str:
    enrichment = data.get("enrichment") or {}
    urls: list[str] = []
    for item in enrichment.get("source_links") or []:
        url = item.get("url") or item.get("label") or ""
        if url:
            urls.append(url)
    for item in data.get("search_results") or []:
        url = item.get("url") or ""
        if url:
            urls.append(url)
    dossier = enrichment.get("dossier") or {}
    for item in dossier.get("source_evidence") or []:
        url = item.get("url") or ""
        if url:
            urls.append(url)
    if not urls:
        return ""
    return sorted(dict.fromkeys(urls), key=source_rank)[0]


def usable_prior_docs(prior_docs: list[dict]) -> list[dict]:
    usable = []
    for doc in prior_docs:
        title = (doc.get("title") or "").lower()
        summary = (doc.get("summary") or "").lower()
        if doc.get("engagement_rows") or ("customer profile" in title and "web search results:" not in summary):
            usable.append(doc)
    return usable


def traffic_source_note(raw: str | None) -> tuple[str, str]:
    if not raw:
        return "traffic source and scale are not confirmed from available sources", "to_validate"
    text = raw.strip()
    lowered = text.lower()
    if "purchase decisions" in lowered or "high-intent" in lowered or "affiliate" in lowered:
        return (
            "public evidence suggests high-intent acquisition traffic and purchase-decision workflows may be relevant; exact channel mix and volume are unconfirmed",
            "likely",
        )
    return text, "likely"


def pricing_packaging_note(pricing_tiers: list | None) -> str:
    if pricing_tiers:
        return "public packaging/pricing terms were found, but actual AI infrastructure spend, budget owner, and BytePlus-relevant commitment are unknown"
    return "pricing or packaging was not found; actual AI infrastructure spend, budget owner, and BytePlus-relevant commitment are unknown"


def unknown_vertical(vertical: dict) -> bool:
    return (vertical.get("name") in {None, "", "default"}) and (vertical.get("confidence") in {None, "", "unknown", "weak"})


def source_attribution(data: dict) -> str:
    prior_docs = data.get("prior_docs") or []
    used_prior_docs = usable_prior_docs(prior_docs)
    prior_notes = data.get("prior_notes") or []
    search_results = data.get("search_results") or []
    enrichment = data.get("enrichment") or {}

    source_status = data.get("source_status") or {}
    used = ["calendar data"] if source_status.get("calendar") == "available" else ["user-provided customer identity"]
    if used_prior_docs:
        used.append("usable prior customer profile docs")
    if prior_notes:
        used.append("prior AI Notes / Minutes")
    enrichment_source = enrichment.get("source")
    if enrichment.get("available") and enrichment_source != "web_search":
        used.append("MCP enrichment")
    web_results = [item for item in search_results if item.get("source") == "web"]
    kb_results = [item for item in search_results if item.get("source") != "web"]
    if web_results:
        used.append("web search references")
    if kb_results:
        used.append("Mira / Knowledge Base references")

    if used == ["calendar data"]:
        return "Prep generated from calendar data only. Prior docs, MCP enrichment, web search, and Mira/Knowledge Base references were unavailable in this run."
    sentence = "Prep generated from " + ", ".join(used) + "."
    if prior_docs and not used_prior_docs:
        sentence += " Candidate prior docs were found but no usable prior customer profile content was extracted."
    return sentence


def derive_questions(data: dict) -> list[str]:
    enrichment = data.get("enrichment") or {}
    questions = list(enrichment.get("suggested_questions") or [])
    defaults = [
        "Can you confirm the main AI workload you are evaluating BytePlus for?",
        "What is your current model / vendor stack?",
        "What are your latency, compliance, or data residency requirements?",
        "Who owns the technical and commercial decision?",
        "Is there a defined POC timeline or success metric?",
        "What would make the POC successful from your perspective?",
    ]
    for q in defaults:
        if q not in questions:
            questions.append(q)
    return questions[:5]


def executive_snapshot(data: dict, customer_name: str, company_name: str | None, questions: list[str]) -> str:
    customer = data.get("customer") or {}
    enrichment = data.get("enrichment") or {}
    known = data.get("known") or {}
    vertical = data.get("vertical") or {}
    company = company_name or customer_name
    core_business = customer.get("description") or customer.get("industry") or "To Validate: company/product context"
    use_cases = enrichment.get("known_use_cases") or ["To Validate: primary AI workload"]
    product_fit = enrichment.get("possible_byteplus_fit") or []
    vertical = data.get("vertical") or {}
    prospecting = data.get("prospecting") or {}
    fit_lines = []
    for item in product_fit[:4]:
        product = item.get("product") or "BytePlus product"
        reason = item.get("reason") or "Validate fit in meeting"
        fit_lines.append(f"- {product}: {reason}")
    if not fit_lines:
        fit_lines.append("- To Validate: BytePlus product fit")

    validate = questions[:4]
    while len(validate) < 4:
        validate.append("Confirm decision maker, POC criteria, timeline, and next step.")

    return "\n".join(
        [
            "## Executive Prep Snapshot",
            "",
            f"**Likely Customer / Company:** {customer_name}" + (f" at {company_name}" if company_name else ""),
            "",
            f"**Core Business Hypothesis:** {core_business}",
            "",
            "**Likely AI Workloads:**",
            *[f"- {item}" for item in use_cases[:5]],
            "",
            "**Why This May Matter For BytePlus:**",
            *fit_lines,
            "",
            "**Known / Inferred Signals:**",
            f"- Detected vertical: {vertical.get('display_name') or 'To Validate'} ({confidence_label(vertical.get('confidence'))})",
            f"- Vertical evidence: {join_non_empty(vertical.get('evidence'), fallback='Not Found')}",
            f"- Website: {customer.get('website') or 'To Validate'}",
            f"- Stakeholder context: {known.get('stakeholder_context') or 'To Validate'}",
            f"- Scale signal: {known.get('monthly_volume') or known.get('paid_users') or 'To Validate'}",
            "",
            "**Top Things To Validate In The Meeting:**",
            *[f"{idx}. {question}" for idx, question in enumerate(validate, 1)],
        ]
    )


def company_dossier_section(data: dict) -> str:
    customer = data.get("customer") or {}
    enrichment = data.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    source = best_evidence_url(data)
    vertical = data.get("vertical") or {}
    is_unknown_vertical = unknown_vertical(vertical)
    target_users = dossier.get("target_users") or ("target users/customer segments are not confirmed from available sources" if is_unknown_vertical else "high-intent consumers and brand/advertiser partners are relevant based on intent-marketing and comparison-platform positioning")
    traffic, traffic_label = traffic_source_note(dossier.get("traffic_source_scale"))
    business_model = dossier.get("business_model") or ("business model/revenue model is not confirmed from available sources" if is_unknown_vertical else "intent-marketing / comparison-platform model connecting consumers with brands")
    social_presence = dossier.get("social_content_presence") or "no confirmed social or paid-media creative workflow from current sources"
    customer_name = customer.get("name") or "the customer"
    stakeholder = f"{customer_name}'s role, buying authority, and technical/commercial ownership are not confirmed"
    rows = [
        ("Company / Brand", dossier.get("company") or customer.get("company_name") or customer.get("name")),
        ("Candidate Company / Product", labeled_text(dossier.get("candidate_company"), "likely", fallback="To Validate: confirm whether this meeting is for the person, a company, or a product.", followup=f"Confirm whether the meeting is for {customer_name} personally, {dossier.get('candidate_company') or 'a candidate company/product'}, or another company/product.")),
        ("Website", labeled_text(customer.get("website"), "known", fallback=TO_VALIDATE)),
        ("What They Do", labeled_text(dossier.get("what_they_do") or customer.get("description"), "known" if source else "to_validate", fallback=TO_VALIDATE, evidence=source)),
        ("Detected Industry", labeled_text(vertical.get("display_name"), "known" if vertical.get("confidence") == "confirmed" else ("likely" if vertical.get("confidence") in {"likely", "weak"} else "to_validate"), fallback=TO_VALIDATE, evidence=join_non_empty(vertical.get("evidence")))),
        ("Product Modules", labeled_text(dossier.get("product_modules"), "likely", fallback="Not Found: no product modules found")),
        ("Target Users / Customer Segments", labeled_text(target_users, "to_validate" if is_unknown_vertical and not dossier.get("target_users") else "likely", followup="Who are the main users or customers: consumers, advertisers, enterprise clients, SMBs, or internal teams?")),
        ("Traffic Source / Scale", labeled_text(traffic, traffic_label, followup="Which channels drive most traffic today, and what is the monthly traffic or qualified-lead volume?")),
        ("Key Stakeholders / Buying Role", labeled_text(stakeholder, "to_validate", followup="Could you confirm your role in this evaluation and who owns the technical and commercial decision?")),
        ("Business Model / Revenue Model", labeled_text(business_model, "to_validate" if is_unknown_vertical and not dossier.get("business_model") else "likely", followup="Is the revenue model mainly lead generation, affiliate/referral, advertising, subscription, or enterprise partnerships?")),
        ("Social / Content / Paid Media Presence", labeled_text(social_presence, "not_found" if not dossier.get("social_content_presence") else "likely", followup="Do you produce paid social, landing page, image, or video creative at scale?")),
        ("Pricing / Packaging", labeled_text(pricing_packaging_note(dossier.get("pricing_tiers")), "to_validate")),
        ("Scale Signals", labeled_text(dossier.get("scale_signals"), "likely", fallback="Not Found: no scale signals found")),
        ("Founder / Leadership", labeled_text(dossier.get("founders_or_leadership"), "likely", fallback="Not Found: no founder or leadership signal found")),
        ("Founded / Operating Since", labeled_text(dossier.get("founded_year"), "likely" if dossier.get("founded_year") else "not_found", fallback="Not Found: no founding year found")),
        ("HQ / Location", labeled_text(dossier.get("hq") or customer.get("hq"), "likely" if (dossier.get("hq") or customer.get("hq")) else "not_found", fallback="Not Found: no HQ/location found")),
        ("Not Found", val(dossier.get("not_found"), "None")),
    ]
    return "### Essential Background Check\n\n" + table(rows)


def internal_hypothesis_section(data: dict, questions: list[str]) -> str:
    enrichment = data.get("enrichment") or {}
    known = data.get("known") or {}
    product_fit = enrichment.get("possible_byteplus_fit") or []
    prospecting = data.get("prospecting") or {}
    lines = [
        "### Prepare Internal Hypothesis",
        "",
        "- Metric focus to validate: quality, cost per generation, latency, reliability, or enterprise conversion.",
        f"- Likely AI workloads: {join_non_empty(enrichment.get('known_use_cases'), fallback=TO_VALIDATE)}",
        f"- Product modules observed: {known.get('expansion_opportunity') or TO_VALIDATE}",
        f"- Possible pain points: {known.get('pain_points') or val(enrichment.get('known_risks'), TO_VALIDATE)}",
        f"- Current vendors / competitors to validate: {join_non_empty(enrichment.get('known_competitors'), fallback='Not found in available sources')}",
        f"- Public scale signal: {known.get('monthly_volume') or known.get('paid_users') or 'Not found in available sources'}",
        "- BytePlus fit hypotheses:",
    ]
    lines.extend(f"  - {item.get('product')}: {item.get('reason')}" for item in product_fit[:5])
    lines.extend(["", "### Meeting Readiness", ""])
    assets = prospecting.get("meeting_readiness_assets") or []
    if assets:
        lines.extend(f"- {asset}" for asset in assets)
    else:
        lines.extend(f"- {question}" for question in questions[:6])
    return "\n".join(lines)


def render_question_prefill_sections(data: dict) -> str:
    items = data.get("question_prefill") or []
    if not items:
        return "### Static Master Script\n\nUse the master template blocks from `references/master-template.md`: Standard Discovery, AI Usage & Current Stack, Business Scenarios & Use Cases, Pain Point Discovery, POC Qualification, Commercial & Procurement Signals, Cross-Sell / Upsell Discovery, and Competitive Replacement Questions."
    grouped: dict[str, list[dict]] = {}
    for item in items:
        grouped.setdefault(item.get("section") or "Standard Discovery Questions", []).append(item)
    lines = [
        "### Vertical-Aware In-Template Prefill",
        "",
        "Relevant master-template questions are pre-filled below. Irrelevant vertical-specific questions are omitted or collapsed; no separate all-question table is rendered.",
    ]
    for section, section_items in grouped.items():
        lines.extend(["", f"### {section}", ""])
        for idx, item in enumerate(section_items, 1):
            evidence = item.get("evidence") or []
            evidence_text = "Not Found" if not evidence else "; ".join(str(x) for x in evidence[:2])
            answer = val(item.get("answer"), "Not Found.")
            if item.get("confidence") == "likely" and "(?)" not in answer:
                answer += " (?)"
            question = val(item.get("question"))
            lines.extend(
                [
                    f"#### {idx}. {question}",
                    "",
                    f"- **Pre-filled answer ({confidence_label(item.get('confidence'))})**: {answer}",
                    f"- **Evidence**: {evidence_text}",
                    f"- **Why it matters**: {val(item.get('why_it_matters'), 'Clarifies BytePlus positioning and next step.')}",
                    f"- **Ask in meeting**: {val(item.get('ask_in_meeting'), 'Validate this directly with the customer.')}",
                    "",
                ]
            )
    omitted = (data.get("prospecting") or {}).get("omitted_questions_summary") or []
    if omitted:
        lines.extend(["### Omitted / Collapsed Questions", ""])
        lines.extend(f"- {item}" for item in omitted)
    lines.extend(["", "### Static Master Script", "", "Use the master template blocks from `references/master-template.md`: Standard Discovery, AI Usage & Current Stack, Business Scenarios & Use Cases, Pain Point Discovery, POC Qualification, Commercial & Procurement Signals, Cross-Sell / Upsell Discovery, and Competitive Replacement Questions."])
    return "\n".join(lines).strip()


def evidence_table(data: dict) -> str:
    enrichment = data.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    evidence = dossier.get("source_evidence") or []
    if not evidence:
        return "No evidence table available."
    rows = ["| Claim / Signal | Source Tier | URL |", "| --- | --- | --- |"]
    for item in evidence[:8]:
        rows.append(f"| {val(item.get('claim'))} | {val(item.get('tier_label'))} | {val(item.get('url'))} |")
    return "\n".join(rows)


def render(data: dict) -> str:
    meeting = data.get("meeting") or {}
    customer = data.get("customer") or {}
    enrichment = data.get("enrichment") or {}
    known = data.get("known") or {}
    source_status = data.get("source_status") or {}
    tz_name = meeting.get("timezone") or "Europe/London"
    start = parse_dt(meeting.get("start", ""), tz_name)
    end = parse_dt(meeting.get("end", ""), tz_name)
    date_label = start.strftime("%d-%m-%Y") if start else TBD
    time_label = (
        f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}, {tz_name}"
        if start and end
        else TBD
    )
    customer_name = val(customer.get("name"), "<unknown> (please confirm)")
    company_name = customer.get("company_name")
    title = f"BytePlus <> {customer_name} - {date_label} - Pre-Meeting Prep"
    confidence = customer.get("confidence") or enrichment.get("confidence")

    attendees = data.get("attendees") or []
    stakeholders = []
    for attendee in attendees:
        if not attendee.get("external", True):
            continue
        text = person_text(attendee)
        if attendee.get("title"):
            text = f"{text} - {attendee['title']}"
        stakeholders.append(text)

    prior_docs = data.get("prior_docs") or []
    prior_notes = data.get("prior_notes") or []
    search_results = data.get("search_results") or []
    product_fit = enrichment.get("possible_byteplus_fit") or []
    vertical = data.get("vertical") or {}
    prospecting = data.get("prospecting") or {}
    product_fit_text = []
    for item in product_fit:
        product = item.get("product") or "BytePlus product"
        reason = item.get("reason")
        fit_conf = item.get("confidence")
        prefix = "Known" if fit_conf == "high" else "Likely"
        suffix = "" if fit_conf == "high" else " (?)"
        product_fit_text.append(f"{prefix}: {product}{suffix}" + (f" - {reason}" if reason else ""))

    background_rows = [
        ("Client Name/Nation", f"{customer_name}" + (f"\nLikely company: {company_name} (?)" if company_name else "") + f"\n{val(customer.get('hq'), TO_VALIDATE)}"),
        ("Detected Vertical", f"{val(vertical.get('display_name'), TO_VALIDATE)}\nVertical Confidence: {confidence_label(vertical.get('confidence'))}\nEvidence: {join_non_empty(vertical.get('evidence'), fallback='Not Found')}"),
        ("AE", person_text(meeting.get("organizer"))),
        ("SA", person_text(meeting.get("sa"))),
        ("Domain", labeled_text(customer.get("website") or customer.get("domain"), "known", fallback=TO_VALIDATE)),
        ("Industry", labeled_text(vertical.get("display_name") or customer.get("industry"), "likely" if vertical.get("display_name") else "to_validate", fallback=TO_VALIDATE, evidence=join_non_empty(vertical.get("evidence")))),
        ("Stakeholders", "\n".join(stakeholders) or TBD),
        ("Key Use Case", known_or_likely(enrichment.get("known_use_cases"), None)),
        ("Servicing Region(s)", known_or_likely(customer.get("hq"), confidence)),
        ("Objectives", val(known.get("objectives"), "To Validate: customer objectives")),
        ("Risk", likely_list(enrichment.get("known_risks"), "To Validate: risks and blockers")),
        ("Competitor", likely_list(enrichment.get("known_competitors"), "To Validate: current vendors / competitors")),
        ("Reference", val(meeting.get("url") or customer.get("website"), "Calendar event link unavailable")),
    ]

    questions = derive_questions(data)
    snapshot = executive_snapshot(data, customer_name, company_name, questions)
    dossier = company_dossier_section(data)
    hypotheses = internal_hypothesis_section(data, questions)
    engagement_rows = ["| Date | Stage | Key Information | Next Step |", "| --- | --- | --- | --- |"]
    imported = False
    for doc in sorted(prior_docs, key=lambda d: d.get("date", ""), reverse=True):
        for row in doc.get("engagement_rows") or []:
            engagement_rows.append(
                f"| {val(row.get('date'), val(doc.get('date')))} | {val(row.get('stage'))} | {val(row.get('key_information'))} | {val(row.get('next_step'))} |"
            )
            imported = True
    if not imported:
        if prior_docs:
            engagement_rows.append("| - | - | Candidate prior customer docs found, but no usable prior customer profile content was extracted. | Validate assumptions during the customer meeting. |")
        else:
            engagement_rows.append("| - | - | No prior customer profile docs found. | - |")
    engagement_rows.append(
        f"| {date_label} | Pre-Meeting | {source_attribution(data)} | Validate assumptions during the customer meeting; update after AI Notes / Minutes are available. |"
    )

    source_hint = first_source = best_evidence_url(data)
    if first_source:
        source_hint = f" Evidence: {first_source}."
    output_rows = [
        ("Customer Stage", "Known: Pre-Meeting. Follow-up: confirm meeting objective and decision owners."),
        ("Core Business", labeled_text(customer.get("description") or customer.get("industry"), "known" if first_source else "to_validate", fallback="To Validate: core business.", evidence=first_source, followup="confirm exact meeting scope and product line.")),
        ("Main AI Use Cases", append_followup(known_or_likely(enrichment.get("known_use_cases"), None), "confirm active workload and priority use case.")),
        ("Current Models", append_followup(val(known.get("current_models"), "Not Found: current models."), "ask whether they use OpenAI, Anthropic, Gemini, Fal, Replicate, Bedrock, Azure, or others.")),
        ("Current Vendors", append_followup(val(known.get("current_vendors"), "Not Found: current vendors."), "ask current LLM/image/video/cloud providers and what they dislike.")),
        ("Monthly Volume", append_followup(val(known.get("monthly_volume"), "Not Found: monthly token/image/video volume."), "ask daily/monthly volume, peak concurrency, and traffic regions.")),
        ("Paid Users", append_followup(val(known.get("paid_users"), "To Validate: paid/free/enterprise split."), "confirm user/customer tiers and commercial model.")),
        ("Pain Points", append_followup(val(known.get("pain_points"), likely_list(enrichment.get("known_risks"), "To Validate: pain points")), "confirm biggest blocker and success metric.")),
        ("Budget Status", append_followup(val(known.get("budget_status"), "To Validate: budget status."), "ask current AI infra spend, vendor commitments, and budget owner.")),
        ("Contract / Commitment", append_followup(val(known.get("contract_commitment"), "To Validate: contract / commitment."), "ask minimum commitments, renewals, and expiry dates.")),
        ("POC Timeline", append_followup(val(known.get("poc_timeline"), "To Validate: POC timeline."), "ask evaluator, benchmark method, timeline, and launch deadline.")),
        ("Expansion Opportunity", append_followup(val(known.get("expansion_opportunity"), "\n".join(product_fit_text) or "To Validate: expansion opportunity."), "identify primary workload first.")),
        ("Competitor Risk", append_followup(likely_list(enrichment.get("known_competitors"), "To Validate: competitor risk."), "ask current providers and whether alternatives have approached recently.")),
        ("Cross-Sell Potential", append_followup(join_non_empty(product_fit_text, fallback="Likely: model platform + creative generation + automation if workload confirms. (?)"), "confirm active workload before pitching product bundle.")),
        ("Next Action", "To Validate: stakeholder role, active workload, vendor stack, volume/cost, POC success criteria, and required meeting assets. Follow-up: agree owner and next milestone."),
    ]

    refs = []
    if meeting.get("url"):
        refs.append(f"- Calendar event: {meeting['url']}")
    used_prior = usable_prior_docs(prior_docs)
    if used_prior:
        refs.append("- Prior customer profile content used: " + ", ".join(d.get("url", d.get("title", "")) for d in used_prior))
    elif prior_docs:
        refs.append("- Candidate prior customer docs found, but no usable prior customer profile content was extracted: " + ", ".join(d.get("url", d.get("title", "")) for d in prior_docs))
    else:
        refs.append("- Prior Customer Profile docs: No prior customer profile docs found.")
    refs.append("- Prior AI Notes / Minutes: " + (", ".join(n.get("url", n.get("title", "")) for n in prior_notes) if prior_notes else "No prior AI Notes found."))
    web_results = [r for r in search_results if r.get("source") == "web"]
    kb_results = [r for r in search_results if r.get("source") != "web"]
    refs.append("- Web search results: " + (", ".join(r.get("url", r.get("label", "")) for r in web_results) if web_results else "No web search references found."))
    refs.append("- Mira / Knowledge Base search results: " + (", ".join(r.get("url", r.get("label", "")) for r in kb_results) if kb_results else "No Mira / Knowledge Base references found."))
    source_links = enrichment.get("source_links") or []
    enrichment_label = "Web enrichment source" if enrichment.get("source") == "web_search" else "Enriched profile source"
    refs.append(f"- {enrichment_label}: " + (", ".join(s.get("url", s.get("label", "")) for s in source_links) if source_links else "MCP enrichment unavailable or no source link allowed."))

    unavailable = [f"{k}: {v}" for k, v in source_status.items() if str(v).lower() not in {"available", "ok"}]
    if not unavailable and not enrichment.get("available", False):
        unavailable.append("mcp: unavailable")

    return "\n\n".join(
        [
            f"# {title}",
            table(
                [
                    ("Customer", customer_name),
                    ("Meeting Date", date_label),
                    ("Time", time_label),
                    ("AE / Owner", person_text(meeting.get("organizer"))),
                    ("SA", person_text(meeting.get("sa"))),
                    ("Status", "Pre-Meeting Prep - to validate in customer meeting"),
                ]
            ),
            "# Background\n\n" + table(background_rows) + "\n\n" + dossier + "\n\n" + snapshot + "\n\n" + hypotheses,
            "# Client Engagement\n\n" + "\n".join(engagement_rows),
            "# Standard Question Prompt\n\n"
            + "### Suggested Questions for This Meeting\n\n"
            + "\n".join(f"{idx}. {q}" for idx, q in enumerate(questions, 1))
            + "\n\n"
            + render_question_prefill_sections(data),
            "# Meeting Output Template\n\n" + output_table(output_rows),
            "# Risk&Support\n\n"
            + "### Risks\n\n"
            + (("\n".join(f"- {risk} (?) - validate in meeting." for risk in enrichment.get("known_risks", []))) or "- To Validate: budget owner, decision process, technical owner, timeline, and blockers.")
            + "\n\n### Case Study (domestic / overseas)\n\n*What you need | For which stakeholder / use case | Domestic or overseas | By when*"
            + "\n\n### Pricing Proposal\n\n*Volume | Commitment term | Models | Competitor price to beat | By when*"
            + "\n\n### Solution Proposal\n\n*What the customer is building | BytePlus products in scope | Technical concerns | Format | By when*",
            "# Others\n\n## Reference doc\n\n" + "\n".join(refs) + "\n\n## Evidence Table\n\n" + evidence_table(data),
            "## Run Report\n\n"
            + ("Unavailable or incomplete sources:\n" + "\n".join(f"- {item}" for item in unavailable) if unavailable else "All declared sources available."),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Normalized event context JSON")
    parser.add_argument("--output", type=Path, help="Markdown output path; stdout when omitted")
    args = parser.parse_args()

    data = load_json(args.input)
    rendered = render(data)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
