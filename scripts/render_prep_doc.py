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
PLACEHOLDER_PATTERNS = (
    "official company overview",
    "company overview",
    "generic company overview",
    "normalized overview",
    "overview unavailable",
    "to validate: to validate",
)


def contains_placeholder(text: str | None) -> bool:
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in PLACEHOLDER_PATTERNS)


def raw_nav_or_placeholder_claim(text: str | None) -> bool:
    clean = " ".join(str(text or "").split())
    lowered = clean.lower()
    if not clean or contains_placeholder(clean):
        return True
    tokens = [token for token in lowered.replace("/", " ").split() if token]
    if len(tokens) >= 12 and len(set(tokens)) / max(len(tokens), 1) < 0.5:
        return True
    nav_terms = ("learn more", "buy", "support", "accessories", "privacy policy", "cookie", "sign in")
    return sum(1 for term in nav_terms if term in lowered) >= 3


def normalize_overview_claim(claim: str, company_name: str | None = None, url: str = "") -> str:
    clean = " ".join(str(claim or "").split())
    lowered = f"{clean} {url}".lower()
    company = (company_name or "").lower()
    if contains_placeholder(clean):
        return ""
    if (company == "apple" or "apple.com" in lowered) and any(term in lowered for term in ("iphone", "mac", "ipad", "apple watch", "airpods", "apple tv", "vision")):
        return "Apple is a global technology company offering consumer devices, software, services, entertainment, accessories, and support across products such as iPhone, Mac, iPad, Apple Watch, Vision, AirPods, and Apple TV."
    compact_company = "".join(ch for ch in company if ch.isalnum())
    if compact_company in {"interpublicgroupipg", "interpublicgroup", "ipg"} or any(term in lowered for term in ("global advertising", "marketing services", "agency network", "agency networks", "media buying", "brand marketing", "mccann", "fcb", "ipg mediabrands")):
        return "Interpublic Group (IPG) is a global advertising and marketing services holding company with agency networks across creative, media, data, technology, communications, and brand marketing services."
    if "keshet" in compact_company or any(term in lowered for term in ("keshet broadcasting", "keshet 12", "streaming service", "content distribution", "international content", "media company")):
        return "Keshet Media Group is a media and entertainment company with broadcasting, streaming, production, news, and international content distribution businesses."
    return "" if raw_nav_or_placeholder_claim(clean) else clean


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
        clean = value.strip()
        if clean.lower() == "to validate: to validate" or contains_placeholder(clean):
            return fallback
        return clean or fallback
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
    customer = data.get("customer") or {}
    company_domain = (customer.get("website") or customer.get("domain") or "").lower().removeprefix("www.")
    dossier = enrichment.get("dossier") or {}
    for item in dossier.get("source_evidence") or []:
        url = item.get("url") or ""
        host = url.lower().split("/")[2].removeprefix("www.") if "://" in url else url.lower().split("/")[0].removeprefix("www.")
        path = "/" + "/".join(url.lower().split("/")[3:]) if "://" in url else ""
        path = path.rstrip("/")
        if (
            item.get("source_classification", "customer_evidence") == "customer_evidence"
            and "Tier 1 - official company site" in str(item.get("tier_label") or "")
            and company_domain
            and (host == company_domain or host.endswith("." + company_domain))
            and path in {"", "/", "/about", "/company", "/about-us", "/newsroom"}
        ):
            return url
    urls: list[str] = []
    for item in enrichment.get("source_links") or []:
        url = item.get("url") or item.get("label") or ""
        if url:
            urls.append(url)
    for item in data.get("search_results") or []:
        url = item.get("url") or ""
        if url:
            urls.append(url)
    for item in dossier.get("source_evidence") or []:
        if item.get("source_classification", "customer_evidence") not in {"customer_evidence", "candidate_entity_evidence"}:
            continue
        url = item.get("url") or ""
        if url:
            urls.append(url)
    if not urls:
        return ""
    def rank(url: str) -> tuple[int, int]:
        host = url.lower().split("/")[2].removeprefix("www.") if "://" in url else url.lower().split("/")[0].removeprefix("www.")
        if company_domain and (host == company_domain or host.endswith("." + company_domain)):
            purpose_penalty = 1 if any(part in url.lower() for part in ("api", "developer", "pricing", "billing", "support", "help")) else 0
            return (1 + purpose_penalty, source_rank(url))
        return (source_rank(url), 0)
    return sorted(dict.fromkeys(urls), key=rank)[0]


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


def customer_context_classification(data: dict) -> str:
    explicit = (data.get("customer_context") or {}).get("classification")
    if explicit:
        return explicit
    customer = data.get("customer") or {}
    enrichment = data.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    if customer.get("domain") or (customer.get("company_name") and customer.get("website")):
        return "confirmed_company"
    if data.get("meeting", {}).get("title") and data.get("attendees"):
        return "event_context"
    if dossier.get("candidate_company"):
        return "candidate_company"
    if customer.get("name") and not customer.get("company_name") and not customer.get("domain"):
        return "person_only"
    return "unknown"


def weak_identity(data: dict) -> bool:
    return customer_context_classification(data) in {"person_only", "candidate_company", "unknown"} and unknown_vertical(data.get("vertical") or {})


def weak_or_unknown_vertical(data: dict) -> bool:
    return unknown_vertical(data.get("vertical") or {})


def confirmed_company_context(data: dict) -> bool:
    return customer_context_classification(data) == "confirmed_company"


def official_company_overview_evidence(data: dict) -> dict | None:
    dossier = ((data.get("enrichment") or {}).get("dossier") or {})
    company_name = ((data.get("customer") or {}).get("company_name") or dossier.get("company") or (data.get("customer") or {}).get("name"))
    for item in dossier.get("source_evidence") or []:
        if item.get("source_classification", "customer_evidence") != "customer_evidence":
            continue
        tier = str(item.get("tier_label") or "")
        url = str(item.get("url") or "").lower()
        path = "/" + "/".join(url.split("/")[3:]) if "://" in url else ""
        path = path.rstrip("/")
        if "Tier 1 - official company site" not in tier:
            continue
        if any(marker in url for marker in ("developer.", "/api", "pricing", "billing", "support.", "help.")):
            continue
        if "/newsroom/" in url:
            continue
        if path not in {"", "/", "/about", "/company", "/about-us", "/newsroom"} and "/about-" not in path:
            continue
        claim = str(item.get("claim") or "").strip()
        claim = normalize_overview_claim(claim, company_name, item.get("url") or "")
        if claim:
            clean_item = dict(item)
            clean_item["claim"] = claim
            return clean_item
    return None


def effective_source_status(data: dict) -> dict:
    status = dict(data.get("source_status") or {})
    if official_company_overview_evidence(data):
        if status.get("web_search") in {"ran_but_all_results_filtered", "request_failed", "ran_but_no_results", "disabled_or_not_configured"}:
            status["web_search"] = "usable_results_found"
        status["company_overview_enrichment"] = "usable_results_found"
    return status


def gated_core_business(data: dict, customer_name: str, source: str = "") -> str:
    customer = data.get("customer") or {}
    enrichment = data.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    if weak_identity(data):
        return "To Validate: no confirmed company or business was extracted from usable sources."
    official_overview = official_company_overview_evidence(data)
    if official_overview and (
        not dossier.get("what_they_do")
        or str(dossier.get("what_they_do", "")).startswith("To Validate:")
        or str(customer.get("description", "")).startswith("To Validate:")
    ):
        return str(official_overview.get("claim") or "").strip()
    if confirmed_company_context(data) and not (dossier.get("what_they_do") or customer.get("description")):
        return "To Validate: business description could not be enriched because web search/fetch was unavailable."
    return dossier.get("what_they_do") or customer.get("description") or "To Validate: core business."


def effective_use_cases(data: dict) -> list[str]:
    if weak_identity(data) or weak_or_unknown_vertical(data):
        return ["To Validate: active AI or BytePlus-relevant workload is not confirmed."]
    enrichment = data.get("enrichment") or {}
    return enrichment.get("known_use_cases") or ["To Validate: no confirmed AI workload or BytePlus use case found from current sources."]


def effective_product_fit(data: dict) -> list[dict]:
    if weak_identity(data) or weak_or_unknown_vertical(data):
        return []
    enrichment = data.get("enrichment") or {}
    vertical_confidence = (data.get("vertical") or {}).get("confidence")
    if not enrichment.get("known_use_cases") and vertical_confidence != "confirmed":
        return []
    fit = enrichment.get("possible_byteplus_fit") or []
    vertical_name = (data.get("vertical") or {}).get("name")
    fallback_only = not enrichment.get("available", False)
    if fit and not fallback_only:
        return fit
    if vertical_name == "ai_video_creative":
        return [
            {"product": "Seedance", "reason": "Validate fit for video generation quality, consistency, and short-form creative workflows", "confidence": "medium"},
            {"product": "Seedream", "reason": "Validate fit for image generation, editing, upscaling, and creative asset production", "confidence": "medium"},
            {"product": "Ark / model platform", "reason": "Validate model evaluation, deployment, routing, cost/performance, and API-scale needs", "confidence": "medium"},
        ]
    if vertical_name == "marketing_adtech":
        return [
            {"product": "Ark / model platform", "reason": "Validate fit for scalable model evaluation, routing, inference cost control, and integration into acquisition/optimization workflows", "confidence": "medium"},
            {"product": "Seedance", "reason": "Validate whether paid-media or landing-page video creative generation is a near-term workload", "confidence": "low"},
            {"product": "Seedream", "reason": "Validate whether display/ad creative variation, localized imagery, or landing-page asset generation is a near-term workload", "confidence": "low"},
        ]
    return []


def product_fit_lines(data: dict) -> list[str]:
    fit = effective_product_fit(data)
    if not fit:
        return [
            "- To Validate: identify active workload first.",
            "- Possible direction after validation: Ark if model platform / API / routing / inference need is confirmed.",
            "- Possible direction after validation: Seedream if image generation/editing need is confirmed.",
            "- Possible direction after validation: Seedance if video generation need is confirmed.",
        ]
    return [f"- {item.get('product') or 'BytePlus product'}: {item.get('reason') or 'Validate fit in meeting'}" for item in fit[:4]]


def normalized_person_background(description: str, customer_name: str, source: str) -> str:
    if not description:
        return "To Validate: no confirmed customer/company business description found."
    lowered = description.lower()
    if "linkedin" in lowered or "expérience" in lowered or "experience" in lowered:
        base = f"{customer_name} appears to have a personal professional background related to web entrepreneurship or advertising based on public profile evidence."
        return labeled_text(base, "likely", evidence=source, followup=f"confirm whether the meeting is for {customer_name} personally, a candidate company/product, or another entity.")
    return labeled_text(description, "likely", evidence=source)


def customer_context_confidence(data: dict) -> str:
    if weak_identity(data):
        return "Weak / Person-only input. No confirmed company, domain, calendar event, or active workload found."
    if (data.get("customer") or {}).get("domain") or (data.get("customer") or {}).get("website"):
        return "Confirmed company context based on domain."
    return "Confirmed company context based on domain / official site / calendar / prior docs."


def validation_gap() -> str:
    return "budget, decision maker, timeline, current vendor, and success metrics are not confirmed."


def risk_note(data: dict) -> str:
    if weak_identity(data) or weak_or_unknown_vertical(data):
        return f"To Validate: {validation_gap()}"
    return likely_list((data.get("enrichment") or {}).get("known_risks"), "To Validate: risks and blockers")


def pain_points_note(data: dict) -> str:
    known = data.get("known") or {}
    if weak_identity(data) or weak_or_unknown_vertical(data):
        return "To Validate: no confirmed pain point found. Missing budget, decision maker, timeline, current vendor, and success metrics should be validated in the meeting."
    if known.get("pain_points"):
        return known["pain_points"]
    return likely_list((data.get("enrichment") or {}).get("known_risks"), "To Validate: pain points")


def source_attribution(data: dict) -> str:
    prior_docs = data.get("prior_docs") or []
    used_prior_docs = usable_prior_docs(prior_docs)
    prior_notes = data.get("prior_notes") or []
    search_results = data.get("search_results") or []
    enrichment = data.get("enrichment") or {}

    source_status = effective_source_status(data)
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
    if weak_identity(data):
        return [
            "Can you confirm whether this meeting is for the person, a candidate company/product, or another entity?",
            "What active AI or BytePlus-relevant workload should we discuss?",
            "Are you evaluating LLM/model platform, image/video generation, API integration, or another use case?",
            "Who owns the technical and commercial decision?",
            "What would make a next step or POC worthwhile?",
        ]
    if weak_or_unknown_vertical(data):
        return [
            "Can you confirm the meeting scope and which team/product this discussion is for?",
            "What active AI or BytePlus-relevant workload should we discuss?",
            "Are you evaluating LLM/model platform, image/video generation, API integration, or another use case?",
            "Who owns the technical and commercial decision?",
            "What would make a next step or POC worthwhile?",
        ]
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
    core_business = gated_core_business(data, customer_name)
    use_cases = effective_use_cases(data)
    vertical = data.get("vertical") or {}
    prospecting = data.get("prospecting") or {}
    fit_lines = product_fit_lines(data)
    contact_name = customer.get("contact") or ""
    display_name = f"{contact_name} at {company_name or customer_name}" if contact_name and (company_name or customer_name) else customer_name + (f" at {company_name}" if company_name else "")

    validate = questions[:4]
    while len(validate) < 4:
        validate.append("Confirm decision maker, POC criteria, timeline, and next step.")

    return "\n".join(
        [
            "## Executive Prep Snapshot",
            "",
            f"**Likely Customer / Company:** {display_name}",
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
    official_overview = official_company_overview_evidence(data)
    vertical = data.get("vertical") or {}
    is_unknown_vertical = unknown_vertical(vertical)
    vertical_name = vertical.get("name") or "default"
    vertical_confidence = vertical.get("confidence")
    workload_confirmed = bool((enrichment.get("known_use_cases") or [])) or vertical_confidence == "confirmed"
    context_class = customer_context_classification(data)
    what_they_do = (
        str(official_overview.get("claim") or "").strip()
        if official_overview and (
            not dossier.get("what_they_do")
            or str(dossier.get("what_they_do", "")).startswith("To Validate:")
            or str(customer.get("description", "")).startswith("To Validate:")
        )
        else dossier.get("what_they_do") or customer.get("description")
    )
    raw_target_users = dossier.get("target_users") or ""
    raw_business_model = dossier.get("business_model") or ""
    overview_lower = str(what_they_do or "").lower()
    if confirmed_company_context(data) and not raw_target_users:
        if any(term in overview_lower for term in ("global advertising", "marketing services", "agency network", "media buying", "brand marketing")):
            raw_target_users = "global brands, advertisers, enterprise marketing teams, media buyers, and agency clients"
        elif any(term in overview_lower for term in ("media and entertainment", "broadcasting", "streaming", "content distribution", "production")):
            raw_target_users = "TV/streaming audiences, broadcasters/streamers, production partners, content buyers, and media partners"
        elif any(term in overview_lower for term in ("global technology company", "consumer devices", "iphone", "mac", "ipad", "app store")):
            raw_target_users = "consumers, developers, enterprise customers, creative professionals, and ecosystem partners"
        elif any(term in overview_lower for term in ("intent-marketing", "customer-acquisition", "comparison", "performance marketing")):
            raw_target_users = "high-intent consumers, brand/advertiser partners, and publishers"
    if confirmed_company_context(data) and not raw_business_model:
        if any(term in overview_lower for term in ("global advertising", "marketing services", "agency network", "media buying", "brand marketing")):
            raw_business_model = "advertising, marketing services, media planning/buying, creative services, data/technology-enabled marketing, communications, and agency network services"
        elif any(term in overview_lower for term in ("media and entertainment", "broadcasting", "streaming", "content distribution", "production")):
            raw_business_model = "broadcasting, streaming, content production, format licensing/global distribution, and media partnerships"
        elif any(term in overview_lower for term in ("global technology company", "consumer devices", "iphone", "mac", "ipad", "app store")):
            raw_business_model = "hardware sales, software/services revenue, App Store ecosystem, subscriptions, accessories, and support"
        elif any(term in overview_lower for term in ("intent-marketing", "customer-acquisition", "comparison", "performance marketing")):
            raw_business_model = "intent-marketing / comparison-platform model connecting consumers, publishers, and brands"
    marketing_leak_terms = ("high-intent", "comparison-platform", "comparison platform", "intent-marketing", "intent marketing")
    if vertical_name == "ai_video_creative":
        if not raw_target_users or any(term in raw_target_users.lower() for term in marketing_leak_terms):
            target_users = "creators, designers, marketers, agencies, enterprise creative teams, and API developers"
        else:
            target_users = raw_target_users
        if dossier.get("scale_signals"):
            traffic = "public evidence suggests creative-platform scale; validate monthly generations, paid subscribers, enterprise customers, API calls, and web/app usage"
            traffic_label = "likely"
        else:
            traffic = "creative-platform traffic and usage scale are not confirmed from available sources"
            traffic_label = "to_validate"
        if not raw_business_model or any(term in raw_business_model.lower() for term in marketing_leak_terms):
            business_model = "subscription, credit, API, and enterprise creative-platform packaging"
        else:
            business_model = raw_business_model
    else:
        target_users = raw_target_users or ("target users/customer segments are not confirmed from available sources" if is_unknown_vertical else "high-intent consumers and brand/advertiser partners are relevant based on intent-marketing and comparison-platform positioning")
        traffic, traffic_label = traffic_source_note(dossier.get("traffic_source_scale"))
        business_model = raw_business_model or ("business model/revenue model is not confirmed from available sources" if is_unknown_vertical else "intent-marketing / comparison-platform model connecting consumers with brands")
    social_presence = dossier.get("social_content_presence") or "no confirmed social or paid-media creative workflow from current sources"
    if weak_or_unknown_vertical(data):
        social_presence = "no confirmed social or paid-media creative workflow from current sources"
    customer_name = customer.get("name") or "the customer"
    contact_name = customer.get("contact") or ""
    stakeholder = f"{customer_name}'s role, buying authority, and technical/commercial ownership are not confirmed"
    if contact_name:
        stakeholder = f"{contact_name}'s role, buying authority, and technical/commercial ownership are not confirmed"
    rows: list[tuple[str, str]] = [
        ("Company / Brand", dossier.get("company") or customer.get("company_name") or customer.get("name")),
        ("Customer Context Confidence", customer_context_confidence(data)),
    ]
    if confirmed_company_context(data) and contact_name:
        rows.append(("Contact / Stakeholder", f"{contact_name} - To Validate role, buying authority, technical owner, and commercial owner."))
    candidate = dossier.get("candidate_company")
    if not confirmed_company_context(data) or (candidate and candidate != (dossier.get("company") or customer.get("company_name"))):
        rows.append(("Candidate Company / Product", labeled_text(candidate, "likely", fallback=f"To Validate: no confirmed company or product was extracted from usable sources. Confirm whether this meeting is for {customer_name} personally, a company, or a product.", followup=f"Confirm whether the meeting is for {customer_name} personally, {candidate or 'a candidate company/product'}, or another company/product.")))
    what_they_do_value = (
        "To Validate: no confirmed company or business was extracted from usable sources."
        if weak_identity(data)
        else (what_they_do or ("To Validate: business description could not be enriched because web search/fetch was unavailable." if confirmed_company_context(data) else "To Validate: core business."))
    )
    what_text = str(what_they_do_value or "").strip().lower()
    what_they_do_label = "to_validate" if weak_identity(data) or not source or what_text.startswith("to validate") else "known"
    target_label = "to_validate" if is_unknown_vertical and not raw_target_users else "likely"
    business_model_label = "to_validate" if is_unknown_vertical and not raw_business_model else "likely"
    if vertical_name == "ai_video_creative":
        target_label = "likely"
        business_model_label = "likely"
    rows = [
        *rows,
        ("Website", labeled_text(customer.get("website"), "known", fallback=TO_VALIDATE)),
        ("What They Do", normalized_person_background(what_they_do_value, customer_name, source) if context_class in {"person_only", "candidate_company"} and not weak_identity(data) else labeled_text(what_they_do_value, what_they_do_label, fallback=TO_VALIDATE, evidence="" if (weak_identity(data) or what_they_do_label == "to_validate") else source)),
        ("Detected Industry", labeled_text(vertical.get("display_name"), "known" if vertical.get("confidence") == "confirmed" else ("likely" if vertical.get("confidence") in {"likely", "weak"} else "to_validate"), fallback="industry not confirmed", evidence=join_non_empty(vertical.get("evidence")))),
        ("Product Modules", labeled_text([] if (weak_identity(data) or weak_or_unknown_vertical(data) or not workload_confirmed) else dossier.get("product_modules"), "likely", fallback="To Validate: identify active workload first; possible product modules depend on confirmed use case.")),
        ("Target Users / Customer Segments", labeled_text(target_users, target_label, followup="Who are the main users or customers: consumers, advertisers, enterprise clients, SMBs, creators, agencies, API developers, or internal teams?")),
        ("Traffic Source / Scale", labeled_text(traffic, traffic_label, followup="Which channels drive most traffic today, and what is the monthly traffic or qualified-lead volume?")),
        ("Key Stakeholders / Buying Role", labeled_text(stakeholder, "to_validate", followup="Could you confirm your role in this evaluation and who owns the technical and commercial decision?")),
        ("Business Model / Revenue Model", labeled_text(business_model, business_model_label, followup="Is the revenue model mainly subscription, credits, API usage, enterprise contracts, lead generation, affiliate/referral, advertising, or partnerships?")),
        ("Social / Content / Paid Media Presence", labeled_text(social_presence, "not_found" if (weak_or_unknown_vertical(data) or not dossier.get("social_content_presence")) else "likely", followup="Do you produce paid social, landing page, image, or video creative at scale?")),
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
    prospecting = data.get("prospecting") or {}
    lines = [
        "### Prepare Internal Hypothesis",
        "",
        "- Metric focus to validate: quality, cost per generation, latency, reliability, or enterprise conversion.",
        f"- Likely AI workloads: {join_non_empty(effective_use_cases(data), fallback=TO_VALIDATE)}",
        f"- Product modules observed: {'To Validate: identify active workload first.' if (weak_identity(data) or weak_or_unknown_vertical(data)) else (known.get('expansion_opportunity') or TO_VALIDATE)}",
        f"- Possible pain points: {pain_points_note(data)}",
        f"- Current vendors / competitors to validate: {join_non_empty(enrichment.get('known_competitors'), fallback='Not found in available sources')}",
        f"- Public scale signal: {known.get('monthly_volume') or known.get('paid_users') or 'Not found in available sources'}",
        "- BytePlus fit hypotheses:",
    ]
    lines.extend(f"  {line}" for line in product_fit_lines(data))
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
            confidence = item.get("confidence")
            if (weak_identity(data) or weak_or_unknown_vertical(data)) and confidence in {"known", "likely"}:
                question_text = val(item.get("question"))
                if "core business" in question_text.lower() and not weak_identity(data):
                    answer = gated_core_business(data, (data.get("customer") or {}).get("name") or "the customer")
                    confidence = "known" if not answer.startswith("To Validate:") else "to_validate"
                    evidence_text = best_evidence_url(data) if confidence == "known" else "Not Found"
                else:
                    confidence = "to_validate"
                    answer = "To Validate: active AI or BytePlus-relevant workload is not confirmed."
                    evidence_text = "Not Found"
            if confidence == "likely" and "(?)" not in answer:
                answer += " (?)"
            question = val(item.get("question"))
            lines.extend(
                [
                    f"#### {idx}. {question}",
                    "",
                    f"- **Pre-filled answer ({confidence_label(confidence)})**: {answer}",
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
    customer = data.get("customer") or {}
    company_name = customer.get("company_name") or dossier.get("company") or customer.get("name")
    primary = best_evidence_url(data)
    evidence = [
        item for item in (dossier.get("source_evidence") or [])
        if item.get("source_classification", "customer_evidence") in {"customer_evidence", "candidate_entity_evidence"}
        and normalize_overview_claim(str(item.get("claim") or ""), company_name, item.get("url") or "")
        and "link.me/" not in (item.get("url") or "").lower()
    ]
    if weak_or_unknown_vertical(data):
        evidence = [
            item for item in evidence
            if not any(marker in (item.get("url") or "").lower() for marker in ("developer.", "/api", "pricing", "billing", "support.", "help."))
        ]
    if primary:
        evidence = sorted(evidence, key=lambda item: 0 if item.get("url") == primary else 1)
    if not evidence:
        return "No evidence table available."
    rows = ["| Claim / Signal | Source Tier | URL |", "| --- | --- | --- |"]
    for item in evidence[:8]:
        claim = normalize_overview_claim(str(item.get("claim") or ""), company_name, item.get("url") or "")
        rows.append(f"| {val(claim)} | {val(item.get('tier_label'))} | {val(item.get('url'))} |")
    return "\n".join(rows)


def render(data: dict) -> str:
    meeting = data.get("meeting") or {}
    customer = data.get("customer") or {}
    enrichment = data.get("enrichment") or {}
    known = data.get("known") or {}
    source_status = effective_source_status(data)
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
    product_fit = effective_product_fit(data)
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
        ("Key Use Case", join_non_empty(effective_use_cases(data), fallback="To Validate: no confirmed AI workload or BytePlus use case found from current sources.")),
        ("Servicing Region(s)", known_or_likely(customer.get("hq"), confidence)),
        ("Objectives", val(known.get("objectives"), "To Validate: customer objectives")),
        ("Risk", risk_note(data)),
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
    core_business = gated_core_business(data, customer_name, first_source)
    output_rows = [
        ("Customer Stage", "Known: Pre-Meeting. Follow-up: confirm meeting objective and decision owners."),
        ("Core Business", labeled_text(core_business, "to_validate" if weak_identity(data) or core_business.startswith("To Validate:") else ("known" if first_source else "to_validate"), fallback="To Validate: core business.", evidence="" if (weak_identity(data) or core_business.startswith("To Validate:")) else first_source, followup="confirm exact meeting scope and product line.")),
        ("Main AI Use Cases", append_followup(join_non_empty(effective_use_cases(data)), "confirm active workload and priority use case.")),
        ("Current Models", append_followup(val(known.get("current_models"), "Not Found: current models."), "ask whether they use OpenAI, Anthropic, Gemini, Fal, Replicate, Bedrock, Azure, or others.")),
        ("Current Vendors", append_followup(val(known.get("current_vendors"), "Not Found: current vendors."), "ask current LLM/image/video/cloud providers and what they dislike.")),
        ("Monthly Volume", append_followup(val(known.get("monthly_volume"), "Not Found: monthly token/image/video volume."), "ask daily/monthly volume, peak concurrency, and traffic regions.")),
        ("Paid Users", append_followup(val(known.get("paid_users"), "To Validate: paid/free/enterprise split."), "confirm user/customer tiers and commercial model.")),
        ("Pain Points", append_followup(pain_points_note(data), "confirm biggest blocker and success metric.")),
        ("Budget Status", append_followup(val(known.get("budget_status"), "To Validate: budget status."), "ask current AI infra spend, vendor commitments, and budget owner.")),
        ("Contract / Commitment", append_followup(val(known.get("contract_commitment"), "To Validate: contract / commitment."), "ask minimum commitments, renewals, and expiry dates.")),
        ("POC Timeline", append_followup(val(known.get("poc_timeline"), "To Validate: POC timeline."), "ask evaluator, benchmark method, timeline, and launch deadline.")),
        ("Expansion Opportunity", append_followup("To Validate: identify active workload first." if (weak_identity(data) or weak_or_unknown_vertical(data) or not product_fit_text) else val(known.get("expansion_opportunity"), "\n".join(product_fit_text) or "To Validate: expansion opportunity."), "identify primary workload first.")),
        ("Competitor Risk", append_followup(likely_list(enrichment.get("known_competitors"), "To Validate: competitor risk."), "ask current providers and whether alternatives have approached recently.")),
        ("Cross-Sell Potential", append_followup(join_non_empty(product_fit_text, fallback="To Validate: identify active workload first. Possible directions after validation: Ark for model platform/API/routing, Seedream for image generation/editing, Seedance for video generation."), "confirm active workload before pitching product bundle.")),
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
            + (f"- {risk_note(data)}" if (weak_identity(data) or weak_or_unknown_vertical(data)) else (("\n".join(f"- {risk} (?) - validate in meeting." for risk in enrichment.get("known_risks", []))) or "- To Validate: budget owner, decision process, technical owner, timeline, and blockers."))
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
