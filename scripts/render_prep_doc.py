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

VERTICAL_SUBTYPE_TEMPLATES = {
    "agency_marketing_services": {
        "target_users": "global brands, advertisers, enterprise marketing teams, media buyers, and agency clients",
        "business_model": "advertising, marketing services, media planning/buying, creative services, communications, data/technology-enabled marketing, and agency network services",
    },
    "intent_marketing_comparison": {
        "target_users": "high-intent consumers, brand/advertiser partners, and publishers",
        "business_model": "lead generation, affiliate/referral, comparison content, performance marketing, and brand partnerships",
    },
    "media_entertainment_content": {
        "target_users": "TV/streaming audiences, broadcasters/streamers, production partners, content buyers, and media partners",
        "business_model": "broadcasting, streaming, content production, format licensing/global distribution, and media partnerships",
    },
    "music_entertainment": {
        "target_users": "fans, artists, entertainment audiences, music listeners, brand partners, platforms, media/content partners",
        "business_model": "artist management, music/record production, release promotion, content/IP monetization, events/performances, brand partnerships",
    },
    "consumer_technology": {
        "target_users": "consumers, developers, enterprise customers, creative professionals, and ecosystem partners",
        "business_model": "hardware sales, software/services revenue, app ecosystem, subscriptions, accessories, and support",
    },
    "creative_platform": {
        "target_users": "creators, designers, marketers, agencies, enterprise creative teams, and API developers",
        "business_model": "subscriptions, credits, asset licensing, API usage, enterprise/team plans, and creative tools",
    },
}


_CURRENCY_SYMBOLS: dict[str, str] = {"USD": "$", "EUR": "€", "GBP": "£", "CNY": "¥", "JPY": "¥", "KRW": "₩"}


def _format_apollo_revenue(value: object, currency: str | None = None) -> str:
    """Format an Apollo revenue value into a human-readable string."""
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return ""
    try:
        num = float(raw.lstrip("$£€¥₩").strip())
    except (ValueError, TypeError):
        return raw
    if num >= 1e9:
        number_str = f"{num / 1e9:.1f}B"
    elif num >= 1e6:
        number_str = f"{num / 1e6:.0f}M"
    elif num >= 1e3:
        number_str = f"{num / 1e3:.0f}K"
    else:
        number_str = str(int(num))
    symbol = _CURRENCY_SYMBOLS.get((currency or "").upper(), "")
    if symbol:
        return f"~{symbol}{number_str} annual revenue signal"
    if currency:
        return f"~{number_str} {currency.upper()} annual revenue signal"
    return f"~{number_str} annual revenue signal (currency not confirmed)"


_BYTEPLUS_RELEVANT_TECH_SUBSTRINGS: frozenset[str] = frozenset({
    "ai", "ml", "llm", "gpt", "claude", "machine learning", "deep learning", "generative",
    "api", "api gateway", "cloud", "aws", "azure", "gcp", "kubernetes", "docker",
    "bedrock", "sagemaker", "vertex", "cloud infrastructure",
    "analytics", "data", "bigquery", "snowflake", "databricks", "data pipeline", "mlops",
    "automation", "workflow", "video", "creative", "content", "model", "inference",
    "pytorch", "tensorflow", "openai", "anthropic", "replicate", "hugging face",
    "advertising", "adtech", "marketing tech", "campaign",
    "computer vision", "nlp", "diffusion", "embedding",
})


def _filter_byteplus_relevant_techs(techs: list, max_count: int = 6) -> list[str]:
    """Return up to max_count technology names ranked by BytePlus relevance."""
    if not techs:
        return []
    tech_strs = [str(t).strip() for t in techs if t]
    priority = [t for t in tech_strs if any(kw in t.lower() for kw in _BYTEPLUS_RELEVANT_TECH_SUBSTRINGS)]
    fallback = [t for t in tech_strs if t not in priority]
    result = priority[:max_count]
    if len(result) < 3:
        result.extend(fallback[:max_count - len(result)])
    return result[:max_count]


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
    if any(term in lowered for term in ("iphone", "mac", "ipad", "apple watch", "airpods", "apple tv", "vision", "consumer devices")):
        return f"{company_name or 'The company'} is a global technology company offering consumer devices, software, services, entertainment, accessories, and support across major product and ecosystem categories."
    compact_company = "".join(ch for ch in company if ch.isalnum())
    if any(term in lowered for term in ("global advertising", "marketing services", "agency network", "agency networks", "media buying", "brand marketing")):
        return f"{company_name or 'The company'} is an advertising and marketing services company with capabilities across creative, media, data, technology, communications, and brand marketing services."
    if any(term in lowered for term in ("media and entertainment", "broadcasting", "streaming service", "content distribution", "international content", "media company", "format licensing", "global distribution and production")):
        return f"{company_name or 'The company'} is a media and entertainment company with broadcasting, streaming, production, news, and international content distribution businesses."
    if any(term in lowered for term in ("intent marketing", "comparison platform", "customer acquisition", "purchase decisions")):
        return f"{company_name or 'The company'} is an intent-marketing and customer-acquisition company focused on connecting consumers with brands through comparison and performance marketing platforms."
    if any(term in lowered for term in ("creative platform", "stock assets", "design assets", "templates", "image generation", "video generation", "ai-enabled image")):
        return f"{company_name or 'The company'} is a creative platform offering design assets, templates, and AI-enabled image/video tools for creators, marketers, agencies, and enterprise creative teams."
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
    for item in evidence_rows_for_current_run(data):
        if item.get("claim_type") == "company_overview" and item.get("source_classification", "customer_evidence") == "customer_evidence":
            return item.get("source_url") or item.get("url") or ""
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


def evidence_rows_for_current_run(data: dict) -> list[dict]:
    run_id = data.get("run_id")
    customer_key = data.get("customer_key")
    registry = data.get("evidence_registry") or []
    rows = []
    for item in registry:
        if run_id and item.get("run_id") != run_id:
            continue
        if customer_key and item.get("customer_key") != customer_key:
            continue
        rows.append(item)
    if rows:
        return rows
    return ((data.get("enrichment") or {}).get("dossier") or {}).get("source_evidence") or []


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


def confidence_layers(data: dict) -> dict:
    layers = data.get("confidence_layers") or {}
    if layers:
        return layers
    return {
        "identity_confidence": "confirmed_company" if confirmed_company_context(data) else ("weak_person_only" if weak_identity(data) else "unknown"),
        "company_vertical_confidence": (data.get("vertical") or {}).get("confidence") or "unknown",
        "active_workload_confidence": "likely" if (data.get("enrichment") or {}).get("known_use_cases") else "unknown",
        "product_fit_confidence": "likely" if (data.get("enrichment") or {}).get("known_use_cases") and (data.get("enrichment") or {}).get("possible_byteplus_fit") else "possible_after_validation",
    }


def active_workload_confirmed(data: dict) -> bool:
    return confidence_layers(data).get("active_workload_confidence") in {"likely", "confirmed"}


def product_fit_allowed(data: dict) -> bool:
    return confidence_layers(data).get("product_fit_confidence") in {"likely", "confirmed"} and active_workload_confirmed(data)


def official_company_overview_evidence(data: dict) -> dict | None:
    dossier = ((data.get("enrichment") or {}).get("dossier") or {})
    company_name = ((data.get("customer") or {}).get("company_name") or dossier.get("company") or (data.get("customer") or {}).get("name"))
    for item in evidence_rows_for_current_run(data):
        if item.get("claim_type") and item.get("claim_type") != "company_overview":
            continue
        if item.get("source_classification", "customer_evidence") != "customer_evidence":
            continue
        tier = str(item.get("tier_label") or "")
        url = str(item.get("source_url") or item.get("url") or "").lower()
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
        claim = str(item.get("claim_text") or item.get("claim") or "").strip()
        claim = normalize_overview_claim(claim, company_name, item.get("source_url") or item.get("url") or "")
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


def core_business_label_and_evidence(data: dict, core_business: str | None = None) -> tuple[str, str]:
    enrichment = data.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    text = core_business if core_business is not None else gated_core_business(data, (data.get("customer") or {}).get("name") or "the customer")
    if weak_identity(data) or str(text or "").startswith("To Validate:"):
        return "to_validate", "Not Found"
    source = best_evidence_url(data)
    if source:
        return "known", source
    apollo_source = dossier.get("what_they_do_source") or ""
    if apollo_source:
        return "likely", apollo_source
    if str(dossier.get("what_they_do_confidence") or "").lower() == "likely" or text:
        return "likely", "Not Found"
    return "to_validate", "Not Found"


def evidence_subtype_name(data: dict) -> str:
    enrichment = data.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    subtype = dossier.get("vertical_subtype") or (data.get("vertical") or {}).get("subtype") or {}
    if isinstance(subtype, dict):
        return str(subtype.get("name") or "")
    return ""


def incompatible_evidence_claim(claim: str, data: dict) -> bool:
    lowered = (claim or "").lower()
    if not lowered:
        return True
    if weak_identity(data):
        return True
    subtype = evidence_subtype_name(data)
    blocked = {
        "media_entertainment_content": ("consumer devices", "accessories", "app ecosystem", "app store", "hardware sales", "iphone", "ipad", "mac", "apple watch", "intent-marketing", "comparison-platform", "comparison platform", "high-intent consumers"),
        "agency_marketing_services": ("consumer devices", "hardware sales", "app ecosystem", "app store", "accessories", "intent-marketing", "comparison-platform", "comparison platform", "high-intent consumers", "broadcasting", "format licensing"),
        "intent_marketing_comparison": ("consumer devices", "hardware sales", "app ecosystem", "app store", "accessories", "agency network services", "broadcasting", "streaming", "format licensing"),
        "creative_platform": ("consumer devices", "hardware sales", "app ecosystem", "app store", "accessories", "broadcasting", "format licensing", "intent-marketing", "comparison-platform", "comparison platform"),
        "consumer_technology": ("intent-marketing", "comparison-platform", "comparison platform", "high-intent consumers", "agency network services", "broadcasting", "format licensing", "creative-platform packaging"),
    }
    return any(term in lowered for term in blocked.get(subtype, ()))


def add_field_validation_warning(data: dict, warning: str) -> None:
    status = data.setdefault("source_status", {})
    existing = str(status.get("field_validation") or "")
    parts = [part.strip() for part in existing.split(";") if part.strip()]
    if warning not in parts:
        parts.append(warning)
    status["field_validation"] = "; ".join(parts)


def _is_apollo_hypothesis_fit(data: dict) -> bool:
    """True when fit hypotheses come from Apollo vertical inference (workload not confirmed)."""
    return (data.get("enrichment") or {}).get("fit_source") == "apollo_hypothesis"


def effective_use_cases(data: dict) -> list[str]:
    if weak_identity(data):
        return ["To Validate: active AI or BytePlus-relevant workload is not confirmed."]
    enrichment = data.get("enrichment") or {}
    # Apollo vertical hypothesis: return hypotheses even without confirmed workload
    if _is_apollo_hypothesis_fit(data):
        return enrichment.get("known_use_cases") or ["To Validate: workload hypotheses could not be generated."]
    if not active_workload_confirmed(data):
        return ["To Validate: active AI or BytePlus-relevant workload is not confirmed."]
    vertical_name = (data.get("vertical") or {}).get("name")
    if not enrichment.get("known_use_cases") and vertical_name == "ai_video_creative":
        return ["Likely: image/video creative generation, editing, or batch production workflow (?)"]
    if not enrichment.get("known_use_cases") and data.get("explicit_workload"):
        return [f"Likely: {str(data.get('explicit_workload')).replace('_', ' ')} workload (?)"]
    return enrichment.get("known_use_cases") or ["To Validate: no confirmed AI workload or BytePlus use case found from current sources."]


def effective_use_cases_concise(data: dict) -> str:
    """Single-line use-case summary for table cells. Concise when hypotheses come from Apollo."""
    if not _is_apollo_hypothesis_fit(data):
        return join_non_empty(
            effective_use_cases(data),
            fallback="To Validate: no confirmed AI workload found.",
        )
    use_cases = (data.get("enrichment") or {}).get("known_use_cases") or []
    if not use_cases:
        return "To Validate: no confirmed AI workload found."
    themes = []
    for uc in use_cases[:3]:
        text = uc
        for prefix in ("Possible fit hypothesis to validate: ", "Possible fit hypothesis to validate:", "Likely fit hypothesis to validate: ", "Likely fit hypothesis to validate:", "Likely: "):
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()
                break
        for sep in (" — ", " – ", " (?)"):
            if sep in text:
                text = text.split(sep)[0].strip()
        text = text.rstrip(".?!,")
        if text:
            themes.append(text)
    if not themes:
        return "To Validate: no confirmed AI workload found."
    if len(themes) == 1:
        return f"Possible hypotheses to validate: {themes[0]}."
    return f"Possible hypotheses to validate: {', '.join(themes[:-1])}, and {themes[-1]}."


def effective_product_fit(data: dict) -> list[dict]:
    if weak_identity(data):
        return []
    enrichment = data.get("enrichment") or {}
    # Apollo vertical hypothesis bypass: show hypotheses without workload confirmation
    if _is_apollo_hypothesis_fit(data):
        return enrichment.get("possible_byteplus_fit") or []
    if not product_fit_allowed(data):
        return []
    enrichment = data.get("enrichment") or {}
    vertical_name = (data.get("vertical") or {}).get("name")
    if not enrichment.get("known_use_cases") and vertical_name != "ai_video_creative" and not data.get("explicit_workload"):
        return []
    fit = enrichment.get("possible_byteplus_fit") or []
    fallback_only = not enrichment.get("available", False)
    if fit and not fallback_only:
        return fit
    if vertical_name == "ai_video_creative":
        return [
            {"product": "Seedance", "reason": "video generation quality, consistency, and short-form creative workflows", "validation": "Validate current model stack, generation volume, and quality/latency benchmarks.", "confidence": "medium"},
            {"product": "Seedream", "reason": "image generation, editing, upscaling, and creative asset production", "validation": "Validate image generation pipeline, editing workflow, and upscaling needs.", "confidence": "medium"},
            {"product": "Ark / model platform", "reason": "model evaluation, deployment, routing, cost/performance, and API-scale needs", "validation": "Validate API usage, routing requirements, and cost/latency expectations.", "confidence": "medium"},
        ]
    if vertical_name == "marketing_adtech":
        return [
            {"product": "Ark / model platform", "reason": "scalable model evaluation, routing, inference cost control, and integration into acquisition/optimization workflows", "validation": "Validate current model stack, API usage pattern, and cost/latency expectations.", "confidence": "medium"},
            {"product": "Seedance", "reason": "paid-media or landing-page video creative generation as a near-term workload", "validation": "Validate creative workflow and video generation volume.", "confidence": "low"},
            {"product": "Seedream", "reason": "display/ad creative variation, localized imagery, or landing-page asset generation as a near-term workload", "validation": "Validate image generation workflow and creative variation needs.", "confidence": "low"},
        ]
    return []


_GENERIC_FIT_FALLBACK = [
    "- To Validate: identify active workload first.",
    "- Possible direction after validation: Ark if model platform / API / routing / inference need is confirmed.",
    "- Possible direction after validation: Seedream if image generation/editing need is confirmed.",
    "- Possible direction after validation: Seedance if video generation need is confirmed.",
]


def product_fit_lines(data: dict) -> list[str]:
    """Format fit hypotheses for the Executive Prep Snapshot 'Why This May Matter' section."""
    fit = effective_product_fit(data)
    if not fit:
        return _GENERIC_FIT_FALLBACK
    layers = confidence_layers(data)
    workload_conf = layers.get("active_workload_confidence", "unknown")
    prefix = "Confirmed workload fit" if workload_conf == "confirmed" else "Possible fit hypothesis to validate"
    return [
        f"- {prefix}: {item.get('product') or 'BytePlus product'} for {item.get('reason') or 'Validate fit in meeting'}."
        for item in fit[:4]
    ]


def _product_fit_lines_internal(data: dict) -> list[str]:
    """Format fit hypotheses for the Internal Hypothesis section with validation prompts."""
    fit = effective_product_fit(data)
    if not fit:
        return _GENERIC_FIT_FALLBACK
    lines = []
    for item in fit[:4]:
        product = item.get("product") or "BytePlus product"
        reason = item.get("reason") or "Validate fit in meeting"
        validation = item.get("validation") or ""
        line = f"- {product}: {reason}."
        if validation:
            line += f" {validation}"
        lines.append(line)
    return lines


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
    if weak_identity(data) or not active_workload_confirmed(data):
        return f"To Validate: {validation_gap()}"
    return likely_list((data.get("enrichment") or {}).get("known_risks"), "To Validate: risks and blockers")


def pain_points_note(data: dict) -> str:
    known = data.get("known") or {}
    if weak_identity(data) or not active_workload_confirmed(data):
        return "To Validate: confirm whether the customer is focused on creative production, media optimization, workflow automation, model/API infrastructure, cost, quality, latency, or deployment."
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
        apollo_org_status = source_status.get("apollo_org", "")
        if apollo_org_status in ("organization_matched", "partial"):
            used.append("Apollo organization enrichment")
        elif enrichment.get("fit_source") == "apollo_hypothesis":
            used.append("Apollo organization enrichment")
        else:
            used.append("enrichment")
    web_results = [item for item in search_results if item.get("source") == "web"]
    kb_results = [item for item in search_results if item.get("source") != "web"]
    if web_results:
        used.append("web search references")
    if kb_results:
        used.append("Mira / Knowledge Base references")

    if used == ["calendar data"]:
        return "Prep generated from calendar data only. Prior docs, Apollo enrichment, web search, and Mira/Knowledge Base references were unavailable in this run."
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
    vertical_name = (data.get("vertical") or {}).get("name") or ""
    if vertical_name == "consumer_technology" and not active_workload_confirmed(data):
        return [
            "Which team is this discussion for: product, developer platform, AI/ML, marketing, content, or operations?",
            "Is the priority internal AI tooling, model/API infrastructure, multimodal understanding, or creative/product marketing workflows?",
            "What current model/vendor stack or internal platform is being evaluated?",
            "What success metric matters most: quality, latency, privacy/compliance, cost, developer productivity, or launch readiness?",
            "Is there a defined POC timeline or evaluation milestone?",
        ]
    if weak_or_unknown_vertical(data) or not active_workload_confirmed(data):
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
    core_label, _core_evidence = core_business_label_and_evidence(data, core_business)
    core_business_labeled = labeled_text(core_business, core_label, evidence="" if _core_evidence == "Not Found" else _core_evidence)
    use_cases = effective_use_cases(data)
    vertical = data.get("vertical") or {}
    prospecting = data.get("prospecting") or {}
    fit_lines = product_fit_lines(data)
    contact_name = customer.get("contact") or ""
    display_name = f"{contact_name} at {company_name or customer_name}" if contact_name and (company_name or customer_name) else customer_name + (f" at {company_name}" if company_name else "")
    layers = confidence_layers(data)
    workload_section_label = "**Workload hypotheses to validate:**" if _is_apollo_hypothesis_fit(data) else "**Likely AI Workloads:**"

    validate = questions[:4]
    while len(validate) < 4:
        validate.append("Confirm decision maker, POC criteria, timeline, and next step.")

    return "\n".join(
        [
            "## Executive Prep Snapshot",
            "",
            f"**Likely Customer / Company:** {display_name}",
            "",
            f"**Core Business Hypothesis:** {core_business_labeled}",
            "",
            workload_section_label,
            *[f"- {item}" for item in use_cases[:5]],
            "",
            "**Why This May Matter For BytePlus:**",
            *fit_lines,
            "",
            "**Known / Inferred Signals:**",
            f"- Detected vertical: {vertical.get('display_name') or 'To Validate'} ({confidence_label(vertical.get('confidence'))})",
            f"- Identity confidence: {layers.get('identity_confidence') or 'unknown'}",
            f"- Company vertical confidence: {layers.get('company_vertical_confidence') or 'unknown'}",
            f"- Active workload confidence: {layers.get('active_workload_confidence') or 'unknown'}",
            f"- Product fit confidence: {layers.get('product_fit_confidence') or 'unknown'}",
            f"- Vertical evidence: {join_non_empty(vertical.get('evidence'), fallback='Not Found')}",
            f"- Website: {customer.get('website') or 'To Validate'}",
            f"- Stakeholder context: {known.get('stakeholder_context') or 'To Validate'}",
            f"- Scale signal: {known.get('scale_signal') or known.get('monthly_volume') or known.get('paid_users') or 'To Validate'}",
            "",
            "**Top Things To Validate In The Meeting:**",
            *[f"{idx}. {question}" for idx, question in enumerate(validate, 1)],
        ]
    )


def _build_apollo_essential_rows(data: dict) -> list[tuple[str, str]]:
    """Return (field, value) rows from Apollo org data for the Essential Background Check.

    Shows rejection/failure notes for meaningful failures so they are visible in
    the document, not only in the Run Report. Silent statuses (disabled, missing_api_key,
    organization_not_found) produce no rows.
    All matched values are labeled Likely to comply with the no-hallucination policy.
    """
    apollo = data.get("apollo") or {}
    status = apollo.get("status", "disabled")

    if status == "rejected_due_to_domain_mismatch":
        warnings = apollo.get("warnings") or []
        detail = warnings[0] if warnings else "Apollo matched a different company domain."
        note = f"Apollo unavailable / domain mismatch. {detail} Direct URL and web fallback used. Validate domain with customer."
        return [("Apollo Enrichment", note)]

    if status in ("auth_failed_401", "forbidden_403", "rate_limited_429", "timeout",
                  "network_error", "invalid_response", "request_failed"):
        return [("Apollo Enrichment", f"Not available: {status}")]

    if status not in ("organization_matched", "partial"):
        return []

    org = apollo.get("organization") or {}
    rows: list[tuple[str, str]] = []

    emp = org.get("employee_count") or org.get("estimated_num_employees")
    if emp:
        rows.append(("Employee Count (Apollo)", f"Likely: ~{emp:,} employees (Apollo signal) (?)"))

    revenue = org.get("annual_revenue")
    if revenue and str(revenue).strip():
        currency = org.get("annual_revenue_currency") or org.get("revenue_currency")
        rev_str = _format_apollo_revenue(revenue, currency)
        rows.append(("Revenue Signal (Apollo)", f"Likely: {rev_str} (Apollo signal) (?)"))

    founded = org.get("founded_year")
    if founded:
        enrichment = data.get("enrichment") or {}
        dossier = enrichment.get("dossier") or {}
        if not dossier.get("founded_year"):
            rows.append(("Founded / Operating Since (Apollo)", f"Likely: {founded} (Apollo signal) (?)"))

    hq_parts = [p for p in [org.get("hq_city"), org.get("hq_state"), org.get("hq_country")] if p]
    if hq_parts:
        enrichment = data.get("enrichment") or {}
        dossier = enrichment.get("dossier") or {}
        if not dossier.get("hq"):
            rows.append(("HQ / Location (Apollo)", f"Likely: {', '.join(hq_parts)} (Apollo signal) (?)"))

    linkedin = org.get("linkedin_url")
    if linkedin:
        rows.append(("LinkedIn (Apollo)", f"Likely: {linkedin} (Apollo signal) (?)"))

    techs = org.get("technologies") or org.get("technology_names") or []
    filtered_techs = _filter_byteplus_relevant_techs(techs, max_count=6)
    if filtered_techs:
        tech_str = ", ".join(filtered_techs)
        rows.append(("Technology Signals (Apollo)", f"Likely: {tech_str} (Apollo signal) (?)"))

    short_desc_en = org.get("short_description_en") or org.get("short_description") or ""
    if short_desc_en:
        enrichment = data.get("enrichment") or {}
        main_desc = (enrichment.get("dossier") or {}).get("what_they_do") or enrichment.get("description") or ""
        if not main_desc or str(main_desc).startswith("To Validate:"):
            desc_row = f"Likely: {short_desc_en} (Apollo signal) (?)"
            original = org.get("apollo_desc_original")
            if original:
                desc_row += f" | Original source text: {original}"
            rows.append(("Company Description (Apollo)", desc_row))

    # Non-blocking note for people search failures (e.g. 403 on free plan)
    people_status = apollo.get("people_status") or ""
    _PEOPLE_SILENT_STATUSES = {"not_attempted", "people_found", "no_people_found", ""}
    if people_status and people_status not in _PEOPLE_SILENT_STATUSES:
        rows.append(("Apollo People Search", f"Unavailable ({people_status}). Stakeholders remain To Validate."))

    return rows


def apollo_stakeholders_section(data: dict) -> str:
    """Render Apollo-sourced stakeholder candidate table, if any people were found."""
    apollo = data.get("apollo") or {}
    people = apollo.get("people") or []
    if not people:
        return ""
    lines = [
        "### Apollo Stakeholder Candidates",
        "",
        "Candidates sourced from Apollo. Validate names, titles, and roles before the meeting.",
        "",
        "| Name | Title | Dept / Seniority | Why Relevant | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for person in people:
        name = str(person.get("name") or "").strip() or "—"
        title = str(person.get("title") or "").strip() or "—"
        dept = str(person.get("department") or "").strip()
        seniority = str(person.get("seniority") or "").strip()
        dept_seniority = ", ".join(p for p in [dept, seniority] if p) or "—"
        why = str(person.get("why_relevant") or "Potential stakeholder — validate role and buying authority").strip()
        source = str(person.get("source") or "Apollo").strip()
        lines.append(f"| {name} | {title} | {dept_seniority} | {why} | {source} |")
    lines.append("")
    return "\n".join(lines)


def company_dossier_section(data: dict) -> str:
    customer = data.get("customer") or {}
    enrichment = data.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    source = best_evidence_url(data)
    official_overview = official_company_overview_evidence(data)
    vertical = data.get("vertical") or {}
    is_unknown_vertical = unknown_vertical(vertical)
    vertical_name = vertical.get("name") or "default"
    workload_confirmed = active_workload_confirmed(data)
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
    subtype = dossier.get("vertical_subtype") or (vertical.get("subtype") or {})
    subtype_name = subtype.get("name") if isinstance(subtype, dict) else ""
    if confirmed_company_context(data) and not raw_target_users:
        if subtype_name in VERTICAL_SUBTYPE_TEMPLATES:
            raw_target_users = VERTICAL_SUBTYPE_TEMPLATES[subtype_name]["target_users"]
        elif any(term in overview_lower for term in ("global advertising", "marketing services", "agency network", "media buying", "brand marketing")):
            raw_target_users = VERTICAL_SUBTYPE_TEMPLATES["agency_marketing_services"]["target_users"]
        elif any(term in overview_lower for term in ("media and entertainment", "broadcasting", "streaming", "content distribution", "production")):
            raw_target_users = VERTICAL_SUBTYPE_TEMPLATES["media_entertainment_content"]["target_users"]
        elif any(term in overview_lower for term in ("global technology company", "consumer devices", "iphone", "mac", "ipad", "app store")):
            raw_target_users = VERTICAL_SUBTYPE_TEMPLATES["consumer_technology"]["target_users"]
        elif any(term in overview_lower for term in ("intent-marketing", "customer-acquisition", "comparison", "performance marketing")):
            raw_target_users = VERTICAL_SUBTYPE_TEMPLATES["intent_marketing_comparison"]["target_users"]
    if confirmed_company_context(data) and not raw_business_model:
        if subtype_name in VERTICAL_SUBTYPE_TEMPLATES:
            raw_business_model = VERTICAL_SUBTYPE_TEMPLATES[subtype_name]["business_model"]
        elif any(term in overview_lower for term in ("global advertising", "marketing services", "agency network", "media buying", "brand marketing")):
            raw_business_model = VERTICAL_SUBTYPE_TEMPLATES["agency_marketing_services"]["business_model"]
        elif any(term in overview_lower for term in ("media and entertainment", "broadcasting", "streaming", "content distribution", "production")):
            raw_business_model = VERTICAL_SUBTYPE_TEMPLATES["media_entertainment_content"]["business_model"]
        elif any(term in overview_lower for term in ("global technology company", "consumer devices", "iphone", "mac", "ipad", "app store")):
            raw_business_model = VERTICAL_SUBTYPE_TEMPLATES["consumer_technology"]["business_model"]
        elif any(term in overview_lower for term in ("intent-marketing", "customer-acquisition", "comparison", "performance marketing")):
            raw_business_model = VERTICAL_SUBTYPE_TEMPLATES["intent_marketing_comparison"]["business_model"]
    marketing_leak_terms = ("high-intent", "comparison-platform", "comparison platform", "intent-marketing", "intent marketing")
    if vertical_name == "ai_video_creative" and workload_confirmed:
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
        target_users = raw_target_users or "target users/customer segments are not confirmed from available sources"
        traffic, traffic_label = traffic_source_note(dossier.get("traffic_source_scale"))
        business_model = raw_business_model or "business model/revenue model is not confirmed from available sources"
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
    explicit_what_confidence = str(dossier.get("what_they_do_confidence") or "").lower()
    if explicit_what_confidence in {"likely", "known", "to_validate", "not_found"}:
        what_they_do_label = explicit_what_confidence
    else:
        what_they_do_label = "to_validate" if weak_identity(data) or not source or what_text.startswith("to validate") else "known"
    target_label = "to_validate" if is_unknown_vertical and not raw_target_users else "likely"
    business_model_label = "to_validate" if is_unknown_vertical and not raw_business_model else "likely"
    if "not confirmed" in str(target_users).lower():
        target_label = "to_validate"
    if "not confirmed" in str(business_model).lower():
        business_model_label = "to_validate"
    if vertical_name == "ai_video_creative":
        target_label = "likely"
        business_model_label = "likely"
    product_modules_value = dossier.get("product_modules")
    if workload_confirmed and vertical_name == "ai_video_creative" and not product_modules_value:
        product_modules_value = ["AI image/video generation", "Creative asset editing", "API / enterprise workflow to validate"]
    rows = [
        *rows,
        ("Website", labeled_text(customer.get("website"), "known", fallback=TO_VALIDATE)),
        ("What They Do", normalized_person_background(what_they_do_value, customer_name, source) if context_class in {"person_only", "candidate_company"} and not weak_identity(data) else labeled_text(what_they_do_value, what_they_do_label, fallback=TO_VALIDATE, evidence="" if (weak_identity(data) or what_they_do_label == "to_validate") else source)),
        ("Detected Industry", labeled_text(vertical.get("display_name"), "known" if vertical.get("confidence") == "confirmed" else ("likely" if vertical.get("confidence") in {"likely", "weak"} else "to_validate"), fallback="industry not confirmed", evidence=join_non_empty(vertical.get("evidence")))),
        ("Product Modules", labeled_text([] if (weak_identity(data) or not workload_confirmed) else product_modules_value, "likely", fallback="To Validate: identify active workload first; possible product modules depend on confirmed use case.")),
        ("Target Users / Customer Segments", labeled_text(target_users, target_label, followup="Who are the main users or customers: consumers, advertisers, enterprise clients, SMBs, creators, agencies, API developers, or internal teams?")),
        ("Traffic Source / Scale", labeled_text(traffic, traffic_label, followup="Which channels drive most traffic today, and what is the monthly traffic or qualified-lead volume?")),
        ("Key Stakeholders / Buying Role", labeled_text(stakeholder, "to_validate", followup="Could you confirm your role in this evaluation and who owns the technical and commercial decision?")),
        ("Business Model / Revenue Model", labeled_text(business_model, business_model_label, followup="Is the revenue model mainly subscription, credits, API usage, enterprise contracts, lead generation, affiliate/referral, advertising, or partnerships?")),
        ("Social / Content / Paid Media Presence", labeled_text(social_presence, "not_found" if (not workload_confirmed or not dossier.get("social_content_presence")) else "likely", followup="Do you produce paid social, landing page, image, or video creative at scale?")),
        ("Pricing / Packaging", labeled_text(pricing_packaging_note(dossier.get("pricing_tiers")), "to_validate")),
        ("Scale Signals", labeled_text(dossier.get("scale_signals"), "likely", fallback="Not Found: no scale signals found")),
        ("Founder / Leadership", labeled_text(dossier.get("founders_or_leadership"), "likely", fallback="Not Found: no compatible founder or leadership signal found.")),
        ("Founded / Operating Since", labeled_text(dossier.get("founded_year"), "likely" if dossier.get("founded_year") else "not_found", fallback="Not Found: no founding year found")),
        ("HQ / Location", labeled_text(dossier.get("hq") or customer.get("hq"), "likely" if (dossier.get("hq") or customer.get("hq")) else "not_found", fallback="Not Found: no HQ/location found")),
        *_build_apollo_essential_rows(data),
        ("Not Found", val(dossier.get("not_found"), "None")),
    ]
    return "### Essential Background Check\n\n" + table(rows)


def internal_hypothesis_section(data: dict, questions: list[str]) -> str:
    enrichment = data.get("enrichment") or {}
    known = data.get("known") or {}
    prospecting = data.get("prospecting") or {}
    workload_label = "Workload hypotheses to validate" if _is_apollo_hypothesis_fit(data) else "Likely AI workloads"
    lines = [
        "### Prepare Internal Hypothesis",
        "",
        "- Metric focus to validate: quality, cost per generation, latency, reliability, or enterprise conversion.",
        f"- {workload_label}: {effective_use_cases_concise(data)}",
        f"- Product modules observed: {'To Validate: identify active workload first.' if (weak_identity(data) or not active_workload_confirmed(data)) else (known.get('expansion_opportunity') or TO_VALIDATE)}",
        f"- Possible pain points: {pain_points_note(data)}",
        f"- Current vendors / competitors to validate: {join_non_empty(enrichment.get('known_competitors'), fallback='Not found in available sources')}",
        f"- Public scale signal: {known.get('scale_signal') or known.get('monthly_volume') or known.get('paid_users') or 'Not found in available sources'}",
        "- BytePlus fit hypotheses:",
    ]
    lines.extend(f"  {line}" for line in _product_fit_lines_internal(data))
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
            existing_answer_label, answer_clean = strip_confidence_prefix(answer)
            if existing_answer_label:
                answer = answer_clean
            question_text = val(item.get("question"))
            section_text = val(item.get("section"), "")
            if "core business" in question_text.lower() and not weak_identity(data):
                answer = gated_core_business(data, (data.get("customer") or {}).get("name") or "the customer")
                confidence, core_evidence = core_business_label_and_evidence(data, answer)
                evidence_text = core_evidence
            workload_specific = any(
                term in f"{section_text} {question_text}".lower()
                for term in ("image", "video", "llm", "model", "vendor", "generation", "cross-sell", "usage", "stack")
            )
            if (weak_identity(data) or weak_or_unknown_vertical(data) or (not active_workload_confirmed(data) and workload_specific)) and confidence in {"known", "likely"} and "core business" not in question_text.lower():
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
    evidence = []
    dropped_incompatible = False
    for item in evidence_rows_for_current_run(data):
        if item.get("source_classification", "customer_evidence") not in {"customer_evidence", "candidate_entity_evidence"}:
            continue
        url = item.get("source_url") or item.get("url") or ""
        if "link.me/" in url.lower():
            continue
        claim = normalize_overview_claim(str(item.get("claim_text") or item.get("claim") or ""), company_name, url)
        if not claim:
            continue
        if incompatible_evidence_claim(claim, data):
            dropped_incompatible = True
            continue
        clean_item = dict(item)
        clean_item["claim_text"] = claim
        clean_item["claim"] = claim
        evidence.append(clean_item)
    if dropped_incompatible:
        add_field_validation_warning(data, "dropped_incompatible_evidence_row")
    if weak_or_unknown_vertical(data):
        evidence = [
            item for item in evidence
            if not any(marker in (item.get("source_url") or item.get("url") or "").lower() for marker in ("developer.", "/api", "pricing", "billing", "support.", "help."))
        ]
    if primary:
        evidence = sorted(evidence, key=lambda item: 0 if (item.get("source_url") or item.get("url")) == primary else 1)
    # Apollo org evidence rows
    apollo = data.get("apollo") or {}
    apollo_org = apollo.get("organization") or {}
    apollo_evidence: list[dict] = []
    if apollo.get("status") in ("organization_matched", "partial") and apollo_org.get("name"):
        apollo_domain = apollo_org.get("domain") or apollo_org.get("website_url") or ""
        apollo_url = f"https://{apollo_domain}" if apollo_domain and not apollo_domain.startswith("http") else apollo_domain
        emp = apollo_org.get("employee_count") or apollo_org.get("estimated_num_employees")
        if emp:
            apollo_evidence.append({
                "claim_text": f"Apollo: ~{emp:,} employees",
                "tier_label": "Tier 3 - Apollo enrichment",
                "source_url": apollo_url or "https://apollo.io",
            })
        short_desc_en = apollo_org.get("short_description_en") or apollo_org.get("short_description") or ""
        if short_desc_en:
            # Use at most 1 sentence in Evidence Table cells to avoid very long rows
            cell_text = short_desc_en
            if len(cell_text) > 180:
                first_end = max(cell_text.find(". "), cell_text.find("! "), cell_text.find("? "))
                if 0 < first_end <= 220:
                    cell_text = cell_text[:first_end + 1]
                else:
                    # Truncate at word boundary, never mid-word
                    cell_text = cell_text[:180].rsplit(" ", 1)[0].rstrip(".,;") + "."
            apollo_evidence.append({
                "claim_text": f"Apollo: {cell_text}",
                "tier_label": "Tier 3 - Apollo enrichment",
                "source_url": apollo_url or "https://apollo.io",
            })
        original_desc = apollo_org.get("apollo_desc_original")
        if original_desc:
            orig_cell = original_desc[:200].rsplit(" ", 1)[0] if len(original_desc) > 200 else original_desc
            apollo_evidence.append({
                "claim_text": f"Original source text: {orig_cell}",
                "tier_label": "Tier 3 - Apollo enrichment",
                "source_url": apollo_url or "https://apollo.io",
            })

    if not evidence and not apollo_evidence:
        return "No evidence table available."
    rows = ["| Claim / Signal | Source Tier | URL |", "| --- | --- | --- |"]
    seen_claims: set[str] = set()
    for item in evidence[:8]:
        claim = str(item.get("claim_text") or item.get("claim") or "").strip()
        claim_key = claim.lower().strip()
        if not claim or claim_key in seen_claims:
            continue
        seen_claims.add(claim_key)
        rows.append(f"| {val(claim)} | {val(item.get('tier_label'))} | {val(item.get('source_url') or item.get('url'))} |")
    for item in apollo_evidence:
        claim = str(item.get("claim_text") or "").strip()
        claim_key = claim.lower().strip()
        if not claim or claim_key in seen_claims:
            continue
        seen_claims.add(claim_key)
        rows.append(f"| {val(claim)} | {val(item.get('tier_label'))} | {val(item.get('source_url'))} |")
    if len(rows) == 2:
        return "No evidence table available."
    return "\n".join(rows)


# ── Vertical intelligence knowledge base ─────────────────────────────────────
# Each entry: (modality, possible_opportunity, why_it_matters, sizing_needed, first_question)
_VERTICAL_OPPORTUNITY_MAP: dict[str, list[tuple[str, str, str, str, str]]] = {
    "marketing_adtech": [
        ("Text / LLM", "Campaign copy, briefing assistant, performance insights, internal AI tools", "High text-content volume; creative and media teams benefit from LLM-assisted workflows", "Copy/briefing requests per month", "Do your creative or strategy teams use AI writing tools today?"),
        ("Language / Localization", "Multilingual campaign adaptation, ad copy localization, brand tone across markets", "Multi-market campaigns require consistent localized creative at scale", "Number of markets and language pairs", "How many markets do you run campaigns for, and how is localization handled today?"),
        ("Image", "Ad creative generation, campaign variant production, visual localization", "Creative velocity and variant testing are high-priority at performance agencies and adtech", "Monthly creative variations per campaign", "How many image or banner variants do you produce per campaign, and what tools generate them?"),
        ("Video", "Short-form ad creative, campaign video, product/brand videos, localized clips", "Video ad spend is growing; scalable video creative is a near-term need for most agencies/adtech", "Monthly video production volume", "Do you produce video ad creatives at scale today, and what's your production pipeline?"),
        ("VLM / OCR / Multimodal", "Creative QA, brand safety checks, asset tagging, ad copy inspection", "Brand safety and creative compliance are manual bottlenecks for large agencies", "Monthly creative assets reviewed", "Is creative QA or brand safety review a manual bottleneck today?"),
        ("Model Platform", "Model routing, evaluation, API integration, cost/latency management", "Agencies and adtech platforms are evaluating multiple LLMs and need a managed API layer", "Monthly API calls and models evaluated", "What LLM or AI APIs do you use today, and how do you manage model selection and cost?"),
    ],
    "media_entertainment": [
        ("Text / LLM", "Script assistance, caption generation, fan/community content, localization", "Content production volume is high; editorial and social teams benefit from AI text tools", "Content pieces per month", "Do editorial or social media teams use AI writing tools today?"),
        ("Language / Localization", "Subtitle generation, dubbing prep, multi-language fan content, international release support", "Media companies release content across multiple markets and languages", "Markets and language pairs for releases", "How do you handle subtitling and localization for international releases today?"),
        ("Image", "Poster/key visual creation, artist promo assets, album artwork concepts, campaign visual generation", "Music, film, and entertainment companies produce visual assets for every release", "Visual assets per campaign/release", "How are poster and key visual assets produced today, and what is the typical volume per release?"),
        ("Video", "Artist promo clips, teaser/trailer generation, music video exploration, social video variants", "Short-form content and teasers are high-frequency needs for entertainment companies", "Teaser/promo clips per release", "How many short-form promos or teasers do you produce per release, and what is the production pipeline?"),
        ("VLM / OCR / Multimodal", "Content review, asset tagging, video scene understanding, rights/brand compliance", "Large media libraries require automated content understanding and compliance checks", "Assets reviewed per month", "Is content review or asset tagging a manual bottleneck in your production or distribution workflow?"),
        ("Model Platform", "Internal production tools, multi-model evaluation, API integration for creative workflows", "Media tech teams want a managed model layer for internal AI tools", "Internal API requests per month", "What AI models or APIs does your tech or production team use internally today?"),
    ],
    "ecommerce": [
        ("Text / LLM", "Product copy, descriptions, SEO content, shopping assistant, recommendation text", "Product catalogue maintenance and SEO copy at scale benefit from LLM automation", "Product listings and copy updates per month", "How do you generate and update product descriptions at scale today?"),
        ("Language / Localization", "Multi-market product copy, cross-border localization, customer support translation", "Cross-border ecommerce requires consistent localized product and support content", "Markets and SKUs needing localization", "How many markets do you sell in, and how is product localization managed today?"),
        ("Image", "Product image generation, background replacement, SKU visual variation, try-on visuals", "Product image quality and variety directly impact conversion rates", "SKUs requiring visual variants per month", "How do you produce product images today, and is visual variation or background replacement a workflow?"),
        ("Video", "Product demo videos, short-form commerce videos, ad creatives for paid media", "Short-form product video is a growing commerce channel", "Product videos produced per month", "Do you produce product demo or short-form commerce videos at scale?"),
        ("VLM / OCR / Multimodal", "Catalog QA, product attribute extraction, visual search, image moderation", "Large catalogs need automated visual QA and attribute tagging", "SKUs in catalog requiring QA per month", "Is product catalog QA or attribute extraction a manual workflow today?"),
        ("Model Platform", "Search and recommendation model management, AI API integration, cost optimization", "Ecommerce platforms run multiple models for search, ranking, and recommendations", "Monthly model API calls across functions", "What AI/ML models do you use for search, ranking, or personalization today?"),
    ],
    "gaming": [
        ("Text / LLM", "NPC dialogue, narrative generation, in-game assistant, player support automation", "Game studios need dynamic text content and scalable player support", "NPCs requiring dialogue or support tickets per month", "Do you use AI for NPC dialogue, narrative scripting, or player support automation today?"),
        ("Language / Localization", "Game localization across markets, in-game text translation, community content", "Games launch across multiple markets and require rapid localization", "Languages and markets for upcoming title", "How many languages and markets do you localize for, and what is the localization pipeline?"),
        ("Image", "Game asset generation (concept art, item visuals, UI elements, key art), marketing creative", "Asset production is a bottleneck in game development; AI can accelerate iteration", "Art assets produced per sprint/release", "What is your current concept art or game asset production workflow, and where are the bottlenecks?"),
        ("Video", "Game trailers, cutscene drafts, marketing video, player-generated content review", "Trailers and marketing video are high-cost, high-frequency outputs for game releases", "Trailers and marketing videos per year", "How are game trailers and marketing videos produced today?"),
        ("VLM / OCR / Multimodal", "Content moderation, asset QA, visual compliance, in-game screenshot understanding", "Live-service games need scalable content moderation and asset compliance", "Monthly moderation decisions or QA assets", "How do you handle content moderation and asset QA for live-service games today?"),
        ("Model Platform", "Model API management, evaluation for game AI features, cost/latency optimization", "Studios building AI features need a managed model platform", "Monthly model API calls for game AI features", "What AI/ML APIs does your engineering team use for in-game features today?"),
    ],
    "ai_video_creative": [
        ("Text / LLM", "Creative brief generation, prompt engineering, script-to-video workflow, internal tools", "Creative platform teams build LLM-integrated workflows for brief and prompt automation", "Prompt generation requests per month", "Do you have LLM-integrated workflows for brief or prompt generation today?"),
        ("Language / Localization", "Multi-language prompt handling, subtitle generation, localized creative exports", "Creative platforms with global users need localized content pipelines", "Languages and markets served", "How many languages and markets do your customers generate content for?"),
        ("Image", "Reference frame generation, storyboard creation, thumbnail and still production", "Image generation is often part of the pre-production and exploration pipeline", "Images generated per day/month", "What is your current image generation volume, and is Seedream or a comparable model used today?"),
        ("Video", "Main platform workload — short-form generation, editing, batch production, API pipeline", "Video generation is the core platform workload for AI creative companies", "Videos generated per day/month, API call volume", "What is your daily and monthly video generation volume, and what quality/latency benchmarks matter?"),
        ("VLM / OCR / Multimodal", "Quality scoring, consistency checks, temporal coherence validation, asset inspection", "Automated QA at video generation scale is a platform-level need", "Videos QA'd per month", "Is quality scoring or automated QA part of your current pipeline, and what metrics matter?"),
        ("Model Platform", "Model evaluation, routing, API cost management, provider benchmarking", "AI creative platforms evaluate and switch models frequently", "Models benchmarked per quarter, API cost per generation", "How do you evaluate and select generation models today, and what is the decision process?"),
    ],
    "enterprise_llm": [
        ("Text / LLM", "Internal assistant, RAG workflows, knowledge management, process automation", "Enterprise AI is the core workload — internal tools, assistants, and workflow automation", "Daily active users and document queries per month", "What internal AI assistant or RAG workflow are you building, and how many users will it serve?"),
        ("Language / Localization", "Multi-language enterprise content, cross-border team tools, global deployment", "Global enterprises need multi-language AI tools for international teams", "Languages and regions for deployment", "Do you need multi-language support for internal AI tools or customer-facing deployments?"),
        ("Image", "Document visual understanding, presentation/report generation (conditional on team)", "Image generation is less central unless there is a marketing or content team involved", "Image generation requests per month (if applicable)", "Does any team have image generation or document visual processing needs?"),
        ("Video", "Optional — only if content or marketing team is in scope", "Video generation is conditional on whether content production teams are part of the discussion", "Video generation use case to confirm", "Is there a video content or marketing team involved in this evaluation?"),
        ("VLM / OCR / Multimodal", "Document understanding, OCR, form processing, visual data extraction, compliance", "Enterprise VLM/OCR is a high-frequency workload for document-heavy industries", "Documents processed per month, OCR accuracy requirements", "Do you have document processing, OCR, or visual data extraction workflows that need AI today?"),
        ("Model Platform", "Main workload — model gateway, multi-model routing, governance, cost/latency management", "Enterprises need a managed model platform with governance, routing, and cost controls", "Monthly model API calls, number of models in evaluation", "What is your current model stack, and how do you manage model selection, routing, and cost today?"),
    ],
    "consumer_technology": [
        ("Text / LLM", "Internal developer tools, product assistant, customer support automation, API integration", "Consumer tech companies are heavy API consumers and often build internal AI tooling", "Daily internal API calls and developer/product tool users", "What internal AI tools or developer-facing APIs are you building or evaluating today?"),
        ("Language / Localization", "Multi-language product and content support, global app localization", "Consumer tech products often target global markets and need localization at scale", "Languages and markets in product roadmap", "How many markets do you serve, and how is AI-driven localization handled today?"),
        ("Image", "Conditional — product launch assets, marketing campaigns, if marketing team is in scope", "Image generation is relevant when marketing or product-launch teams are part of the discussion", "Image generation volume (if applicable)", "Is marketing or product-launch visual content part of this evaluation, or is the focus on engineering/product?"),
        ("Video", "Conditional — product demos, marketing clips, if content team is in scope", "Video generation is relevant when content or marketing teams are in scope", "Video generation use case to confirm", "Is there a video content or product-demo team involved in this evaluation?"),
        ("VLM / OCR / Multimodal", "UI screenshot understanding, visual inspection, app QA, accessibility automation, device diagnostics", "Consumer tech companies often have visual inspection, QA, or accessibility workflows that benefit from VLM/multimodal", "Screenshots or UI frames processed per day/month", "Do you have UI testing, visual inspection, or accessibility workflows that could benefit from visual AI today?"),
        ("Model Platform", "Model routing and evaluation, multi-model governance, inference API, developer platform integration", "Consumer tech companies building AI products need a managed model layer", "Monthly model API calls, models in evaluation", "What model APIs or platforms does your engineering team use today, and how do you manage routing and cost?"),
    ],
}

_VERTICAL_COMPETITOR_CATEGORIES: dict[str, list[str]] = {
    "marketing_adtech": [
        "OpenAI (GPT-4o, o3, API)", "Anthropic (Claude)", "Google Gemini / Vertex AI",
        "Azure OpenAI", "AWS Bedrock", "Adobe Firefly / Creative Cloud",
        "Runway / Pika / Luma (video generation)", "HeyGen / Synthesia (avatar video)",
        "Midjourney / Stability AI / Leonardo (image generation)", "Fal.ai / Replicate (API inference)",
    ],
    "media_entertainment": [
        "Runway / Pika / Luma / Kling (video generation)", "Adobe Firefly / Premiere (creative tools)",
        "Midjourney / Stability AI (image generation)", "HeyGen / Synthesia (avatar/promo video)",
        "OpenAI / Google Gemini (LLM + vision)", "Local production tools and agencies",
    ],
    "ecommerce": [
        "OpenAI (GPT + vision API)", "Anthropic (Claude)", "Google Gemini / Vertex AI",
        "Azure OpenAI / AWS Bedrock", "Adobe Firefly (product image editing)",
        "Midjourney / Stability AI / Leonardo (image generation)", "Runway / Pika (product video)",
        "Google Cloud Vision / AWS Rekognition (catalog QA / visual search)",
    ],
    "gaming": [
        "Midjourney / Stability AI / Leonardo (concept art and game assets)",
        "Runway / Pika / Luma (cinematic / trailer video)", "OpenAI (GPT for NPC and support)",
        "Anthropic (Claude for narrative AI)", "Google Vertex AI / Gemini", "Azure OpenAI",
        "Internal AI tooling and research teams",
    ],
    "ai_video_creative": [
        "Runway (Gen-3/Gen-4 video generation)", "Pika Labs", "Luma AI (Dream Machine)",
        "Kling AI", "Sora (OpenAI)", "Adobe Premiere / After Effects",
        "CapCut / Jianying (consumer video editing)", "HeyGen / Synthesia (avatar video)",
        "Midjourney / Stability AI / FLUX (image-to-video pipeline)", "Fal.ai / Replicate (API inference)",
    ],
    "enterprise_llm": [
        "OpenAI (GPT-4o, o3, Enterprise API)", "Anthropic (Claude Enterprise)",
        "Google Gemini / Vertex AI (enterprise)", "Azure OpenAI Service", "AWS Bedrock",
        "Internal / proprietary model platform", "Cohere / Mistral / LLaMA (open-weight options)",
        "Databricks / Snowflake (data + AI platform integration)",
    ],
    "consumer_technology": [
        "OpenAI (API + enterprise)", "Anthropic (Claude API)", "Google Gemini / Vertex AI",
        "Azure OpenAI", "AWS Bedrock", "Internal model platform / research team",
        "OCR / VLM providers (Google Vision, AWS Textract, Azure AI Vision)",
        "Developer tooling providers (Hugging Face, Replicate, Fal.ai)",
    ],
}

_VERTICAL_SOLUTION_PATHS: dict[str, list[dict]] = {
    "marketing_adtech": [
        {"name": "A. Creative generation and localization", "products": "Seedance (video) + Seedream (image)", "why": "High-volume creative production and variant testing is a core workflow for performance agencies and adtech platforms", "validate": "Creative production volume per client/campaign, current tools, brand/quality bar, market scope, approval workflow", "poc": "Generate image/video variants for one live campaign — compare generation speed, quality, approval rate, and cost vs current workflow"},
        {"name": "B. AI model platform and workflow", "products": "Ark", "why": "Agencies and adtech platforms are evaluating multiple LLMs and need API-level model routing, cost management, and integration", "validate": "Current model stack (OpenAI/Anthropic/Gemini/Azure), API call volume, latency requirements, cost sensitivity, evaluation timeline", "poc": "Route a sample of campaign assistant or copy-generation queries through Ark — compare quality, latency, and cost vs current stack"},
        {"name": "C. Creative QA and brand safety automation", "products": "VLM / multimodal", "why": "Manual creative review and brand safety checks are bottlenecks at scale", "validate": "Monthly volume of creative assets reviewed, current review process, brand safety requirements, compliance standards", "poc": "Run VLM-based classification on a sample set of creative assets — measure accuracy vs manual review and time saved"},
    ],
    "media_entertainment": [
        {"name": "A. Visual content production for releases and campaigns", "products": "Seedream (image) + Seedance (video)", "why": "Entertainment companies produce high-frequency visual assets for every release cycle", "validate": "Visual asset volume per release, current production workflow, quality and brand standards, campaign timeline", "poc": "Generate poster/key visual or teaser clip for an upcoming release — compare creative exploration speed and asset quality"},
        {"name": "B. Content understanding and automated review", "products": "VLM / multimodal", "why": "Large media libraries and streaming catalogs need automated content understanding and compliance", "validate": "Library size, content moderation or tagging workflow, rights/compliance requirements, review volume", "poc": "Tag and classify a sample of catalog assets — measure tagging accuracy and time saved vs manual workflow"},
        {"name": "C. Internal AI tools and model platform", "products": "Ark", "why": "Media tech teams want a managed model layer for internal editorial, production, and fan/community tools", "validate": "Internal AI tool roadmap, current model APIs, team size and use cases, governance requirements", "poc": "Deploy a model routing or internal assistant prototype — evaluate latency, quality, and governance controls"},
    ],
    "ecommerce": [
        {"name": "A. Product image generation and visual variation", "products": "Seedream (image)", "why": "Product image quality and visual variety directly impact conversion; background removal/replacement and SKU variation are high-frequency workflows", "validate": "SKU count needing visual refreshes, current image production workflow, background replacement volumes, quality standard", "poc": "Generate visual variants for a sample SKU set — compare generation speed, image quality, and cost vs current tooling"},
        {"name": "B. Short-form product and commerce video", "products": "Seedance (video)", "why": "Short-form product video is a growing channel for ecommerce; automated generation reduces production cost", "validate": "Monthly product video volume, social/commerce channels served, current video production workflow", "poc": "Generate product demo clips for a sample product line — evaluate creative quality, production time, and cost"},
        {"name": "C. AI shopping assistant and catalog intelligence", "products": "Ark + VLM", "why": "AI-powered search, recommendation, and catalog QA are high-value ecommerce AI workloads", "validate": "Catalog size, current search/recommendation stack, product attribute extraction workflow, model APIs in use", "poc": "Prototype a catalog QA or shopping assistant workflow — compare attribute extraction accuracy and latency"},
    ],
    "gaming": [
        {"name": "A. Game asset and concept art generation", "products": "Seedream (image)", "why": "Asset production is a bottleneck in game development; AI image generation accelerates concept art and in-game asset iteration", "validate": "Art asset production volume, current workflow (in-house artists vs outsourcing), quality and style consistency bar, engine integration needs", "poc": "Generate concept art or item visuals for one game title — compare iteration speed, style consistency, and cost vs current process"},
        {"name": "B. Trailer and marketing video generation", "products": "Seedance (video)", "why": "Game trailers and marketing video are high-cost, high-frequency outputs; AI video can accelerate pre-production and marketing variants", "validate": "Annual trailer/marketing video volume, current production pipeline, quality bar, approvals workflow", "poc": "Generate a rough-cut trailer variant for an upcoming title — evaluate creative quality, iteration speed, and feedback from the creative team"},
        {"name": "C. NPC AI, player support, and content moderation", "products": "Ark + VLM", "why": "Live-service games need scalable NPC dialogue, player support automation, and content moderation", "validate": "Player support ticket volume, NPC dialogue system, moderation review volume, current AI/ML APIs", "poc": "Prototype NPC dialogue or support automation — measure response quality and resolution rate vs current solution"},
    ],
    "ai_video_creative": [
        {"name": "A. Video generation quality and throughput benchmarking", "products": "Seedance (video)", "why": "AI creative platforms evaluate models on quality, consistency, speed, and cost at generation scale", "validate": "Daily/monthly generation volume, current model provider (Runway/Pika/Luma/Kling/Sora), quality benchmark criteria, API cost sensitivity", "poc": "Generate a batch of videos across standard prompt types — compare visual quality, temporal consistency, latency, and cost per generation"},
        {"name": "B. Image generation and creative pipeline", "products": "Seedream (image)", "why": "Image generation is often part of the exploration and pre-production pipeline for video platforms", "validate": "Image generation volume, current model (Midjourney/Stability/FLUX), use in pre-production vs final output, API integration needs", "poc": "Benchmark image generation quality across a standard creative brief — compare aesthetic quality, style adherence, and API latency"},
        {"name": "C. Model evaluation and API routing platform", "products": "Ark", "why": "Creative platforms evaluate and switch models frequently; a managed API layer reduces switching cost and enables cost optimization", "validate": "Number of models evaluated per quarter, API cost per generation, routing or evaluation workflow, governance requirements", "poc": "Route a sample of generation requests through Ark — compare routing accuracy, cost savings, and API management overhead"},
    ],
    "enterprise_llm": [
        {"name": "A. Enterprise AI gateway and model platform", "products": "Ark", "why": "Enterprises need a managed model platform with routing, governance, access control, and cost management", "validate": "Current model stack (OpenAI/Anthropic/Gemini/Azure/Bedrock), monthly API call volume, governance and compliance requirements, team size", "poc": "Deploy Ark as the model gateway for an internal use case — evaluate routing accuracy, cost reduction, and governance controls"},
        {"name": "B. Document and visual intelligence (VLM / OCR)", "products": "VLM / OCR (Ark multimodal)", "why": "Document processing, OCR, and visual data extraction are high-frequency enterprise workflows", "validate": "Document volume per month, current OCR/document processing stack, accuracy requirements, language/format diversity", "poc": "Process a sample document batch through VLM/OCR — compare extraction accuracy, processing speed, and cost vs current solution"},
        {"name": "C. Creative and content generation (conditional)", "products": "Seedream (image) / Seedance (video) — only if marketing or content teams are in scope", "why": "If marketing or content production teams are part of the evaluation, image/video generation is a possible extension workload", "validate": "Whether marketing, brand, or content team is part of this evaluation and has active creative production needs", "poc": "Scope only after confirming marketing/content team involvement and creative production volume"},
    ],
    "consumer_technology": [
        {"name": "A. Model platform, API routing, and evaluation", "products": "Ark", "why": "Consumer tech companies building AI products are heavy API consumers and need a managed model platform for routing, evaluation, and cost control", "validate": "Current model APIs in use, monthly call volume, latency/cost requirements, number of models being evaluated, governance needs", "poc": "Integrate Ark as the model routing layer for one internal AI product — evaluate latency, quality, cost savings, and developer experience"},
        {"name": "B. VLM / OCR / multimodal integration", "products": "VLM (Ark multimodal)", "why": "Consumer tech products often have visual inspection, UI understanding, or accessibility workflows that benefit from multimodal AI", "validate": "Whether there are UI testing, visual inspection, OCR, or accessibility workflows; volume of screenshots/images processed; current solution", "poc": "Run VLM on a sample of UI screenshots or device images — measure understanding accuracy and latency vs current approach"},
        {"name": "C. Image and video generation (conditional)", "products": "Seedream (image) / Seedance (video)", "why": "Image and video generation are relevant when marketing, content, or product-launch teams are part of the discussion", "validate": "Whether marketing, brand, or product-launch team is in scope; creative production volume; current tooling", "poc": "Scope only after confirming which team is driving the evaluation and confirming creative production needs"},
    ],
}

_VERTICAL_FIRST_MEETING_QUESTIONS: dict[str, list[dict]] = {
    "marketing_adtech": [
        {"q": "Which team is this discussion for — media buying, creative, adtech product, data/insights, or marketing operations?", "why": "Different teams have different BytePlus workloads (Ark for insights/models, Seedance/Seedream for creative, VLM for brand safety)", "unlocks": "Correctly scopes which BytePlus product and use case is most relevant", "followup": "Who else from technical and commercial ownership should be part of this evaluation?"},
        {"q": "What AI tools, APIs, or models does your team use today for creative, copy, or campaign workflows?", "why": "Identifies current vendors and switching opportunities", "unlocks": "Competitor/vendor intelligence and differentiation angles", "followup": "What do you like or dislike about your current solution?"},
        {"q": "What is your approximate monthly volume — ad creatives generated, campaigns served, API calls, or content pieces produced?", "why": "Volume is the key sizing input for commercial discussions", "unlocks": "Commercial model and POC scope", "followup": "Is that volume growing, and what is driving the growth?"},
        {"q": "Which creative formats matter most today: image, video, copy, or multi-format bundles?", "why": "Determines which BytePlus product (Seedance, Seedream, Ark) is most relevant as the starting point", "unlocks": "Product prioritization and POC design", "followup": "Is video ad creative a current priority, or is that a future roadmap item?"},
        {"q": "What markets and languages are in scope for creative and campaign production?", "why": "Localization scale affects image/video generation ROI", "unlocks": "Localization use case and multi-market creative opportunity", "followup": "How is localization handled today — in-house, agency, or automated?"},
        {"q": "What would make a POC successful — speed, cost reduction, quality improvement, or something else?", "why": "Defines success criteria for the commercial discussion", "unlocks": "POC design and benchmark criteria", "followup": "Is there a specific campaign, client, or timeline we could benchmark against?"},
        {"q": "What is the current AI or creative tool budget, and who owns the vendor decision?", "why": "Identifies commercial path and decision owner", "unlocks": "Budget qualification and next-step planning", "followup": "Is there an existing vendor contract expiring, or are you evaluating net-new tooling?"},
    ],
    "media_entertainment": [
        {"q": "Which team is this discussion for — content production, artist/label relations, distribution, tech/engineering, or marketing?", "why": "Production teams need image/video generation; tech teams need model platform; marketing needs creative generation", "unlocks": "Scopes the correct BytePlus product and use case", "followup": "Who else from technical and commercial ownership should be part of this evaluation?"},
        {"q": "What is your release cadence — how many titles, albums, or campaigns per month require visual or video assets?", "why": "Release cadence determines creative production volume and ROI", "unlocks": "Volume sizing and commercial model", "followup": "What does the current production workflow look like for these releases?"},
        {"q": "What AI or creative tools are used today for visual asset production or content generation?", "why": "Identifies current vendor stack and switching opportunity", "unlocks": "Competitor/vendor intelligence and differentiation", "followup": "What quality or workflow limitations have you encountered with current tools?"},
        {"q": "Are you looking at AI for content creation, content understanding (tagging/review/search), or both?", "why": "Creation maps to Seedream/Seedance; understanding maps to VLM", "unlocks": "Correct product scoping and POC design", "followup": "Is there a specific release or library project we could use as a POC?"},
        {"q": "What markets and languages are in scope for releases and campaigns?", "why": "International releases require localization; multi-market determines scale", "unlocks": "Localization opportunity and global scope", "followup": "How is localization handled today — in-house, external agency, or automated?"},
        {"q": "What would a successful pilot look like, and who owns the go/no-go decision?", "why": "Success criteria and decision owner are required for commercial qualification", "unlocks": "POC criteria and next steps", "followup": "Is there an upcoming release where we could run a benchmark?"},
    ],
    "ecommerce": [
        {"q": "Which team is this discussion for — product catalog, marketing, engineering/data, or operations?", "why": "Catalog teams need image generation; marketing needs video/creative; engineering needs model platform", "unlocks": "Product and use case prioritization", "followup": "Who else should be part of this evaluation on the technical and commercial side?"},
        {"q": "How many SKUs or products require visual refreshes, new imagery, or video per month?", "why": "SKU volume is the key input for image/video generation ROI", "unlocks": "Commercial model and POC scope", "followup": "Is there a seasonal spike that drives higher creative volume?"},
        {"q": "What AI or creative tools are you using today for product image, video, or copy generation?", "why": "Identifies current stack and switching opportunity", "unlocks": "Vendor intelligence and differentiation angles", "followup": "What are the main pain points with your current workflow?"},
        {"q": "How many markets and languages do you sell in, and how is localization handled today?", "why": "Cross-border ecommerce with localized content is a strong image/video generation use case", "unlocks": "Localization scale and multi-market opportunity", "followup": "Is localization a manual or automated workflow today?"},
        {"q": "Is catalog QA or product attribute extraction a manual workflow today?", "why": "VLM/multimodal automation for catalog QA is a high-ROI use case for large catalogs", "unlocks": "VLM opportunity and automation scope", "followup": "What is the approximate catalog size and monthly QA volume?"},
        {"q": "What would make a POC successful — image quality, generation speed, cost reduction, or catalog accuracy?", "why": "Success criteria drive POC design and commercial qualification", "unlocks": "Benchmark criteria and next step", "followup": "Is there a specific product category or campaign we could use as a benchmark?"},
    ],
    "gaming": [
        {"q": "Which team is this discussion for — game development/art, live operations, player support, marketing, or tech/engineering?", "why": "Art team needs image generation; live ops needs NPC/support AI; marketing needs video/creative", "unlocks": "Correct product and use case scoping", "followup": "Who else should be involved from technical and commercial decision-making?"},
        {"q": "What is the production volume — art assets per sprint, marketing videos per year, or support tickets per month?", "why": "Volume determines ROI and commercial model", "unlocks": "Sizing and commercial scope", "followup": "Is there an upcoming title where we could run a pilot?"},
        {"q": "What AI tools or APIs does your team use today for art, NPC, support, or marketing?", "why": "Identifies current vendor stack and competitive positioning", "unlocks": "Vendor intelligence and differentiation", "followup": "What limitations have you encountered with the current tools?"},
        {"q": "How many markets and languages do you launch in, and how is localization managed today?", "why": "Game localization at launch is a high-volume multilingual content workload", "unlocks": "Localization opportunity and multi-market scope", "followup": "Is AI localization or translation in your current or roadmap workflow?"},
        {"q": "Is content moderation or asset QA a current bottleneck for your live-service title?", "why": "VLM-based moderation and QA automation is a meaningful workload for live-service games", "unlocks": "VLM opportunity and automation scope", "followup": "What is the monthly moderation or review volume?"},
        {"q": "What would a successful POC look like — asset quality, generation speed, support deflection, or moderation accuracy?", "why": "Success criteria are required for commercial qualification", "unlocks": "POC design and benchmark criteria", "followup": "Is there a title launch or live-service milestone we could benchmark against?"},
    ],
    "ai_video_creative": [
        {"q": "What is your daily and monthly video generation volume today, and what are your peak concurrency needs?", "why": "Volume and concurrency are the primary sizing inputs for a creative platform deal", "unlocks": "Commercial model and infrastructure scope", "followup": "Is that volume growing rapidly, and what is the growth driver?"},
        {"q": "Which generation model do you use today — Runway, Pika, Luma, Kling, Sora, or others?", "why": "Identifies current vendor and switching opportunity; Seedance benchmarking is the POC path", "unlocks": "Competitive positioning and switching motivation", "followup": "What do you like or dislike about your current model?"},
        {"q": "What quality benchmark criteria matter most — visual quality, temporal consistency, style adherence, diversity, or cost per generation?", "why": "Quality benchmark criteria define the POC evaluation framework", "unlocks": "POC design and differentiation angles", "followup": "Do you have a standard test prompt set we could benchmark against?"},
        {"q": "What is the typical prompt type — text-to-video, image-to-video, reference-based, or style-guided?", "why": "Prompt type determines which Seedance capabilities are most relevant", "unlocks": "Product capability alignment and POC scope", "followup": "Do your users submit prompts directly via API, or through a platform UI?"},
        {"q": "Is image generation part of your pipeline today, and which model do you use?", "why": "Seedream integration alongside Seedance is a natural expansion opportunity", "unlocks": "Image generation expansion opportunity", "followup": "What is the image generation volume relative to video generation?"},
        {"q": "Who owns the model selection and vendor decision — engineering, product, or commercial leadership?", "why": "Decision owner determines next step and commercial path", "unlocks": "Stakeholder map and procurement process", "followup": "Is there an existing API contract expiring, or is this a new evaluation?"},
    ],
    "enterprise_llm": [
        {"q": "What is the priority use case — internal assistant/RAG, process automation, document intelligence, or customer-facing AI?", "why": "Use case determines the correct BytePlus product and architecture", "unlocks": "Product scoping and POC design", "followup": "Is there an existing proof-of-concept or in-production tool we can benchmark against?"},
        {"q": "What model stack are you using today — OpenAI, Anthropic, Gemini, Azure OpenAI, AWS Bedrock, or internal models?", "why": "Current stack identifies switching opportunity and Ark integration path", "unlocks": "Vendor intelligence and Ark positioning", "followup": "What are the main cost, latency, or governance challenges with your current stack?"},
        {"q": "What is the approximate monthly model API call volume, and how many teams or applications are using AI today?", "why": "Volume and team breadth are the primary commercial sizing inputs", "unlocks": "Commercial model and Ark platform scope", "followup": "Is that volume growing as you roll out AI to more teams?"},
        {"q": "Do you have document processing, OCR, or visual data extraction workflows that need AI?", "why": "VLM/OCR is a high-frequency enterprise workload; confirms or rules out the multimodal path", "unlocks": "VLM opportunity scope", "followup": "What is the monthly document volume, and what accuracy requirements apply?"},
        {"q": "What are the governance, compliance, and data residency requirements for your AI deployment?", "why": "Enterprise AI governance is often a key differentiator and blocker", "unlocks": "Deployment architecture and compliance positioning", "followup": "Do you need on-premise, private cloud, or VPC deployment options?"},
        {"q": "Who owns the technical and commercial decision for AI platform selection?", "why": "Decision owner determines the commercial path and approval process", "unlocks": "Stakeholder map and procurement process", "followup": "Is there an existing enterprise AI contract expiring, or is this a new procurement?"},
    ],
    "consumer_technology": [
        {"q": "Which team is this discussion for — product, developer platform, AI/ML research, marketing, content, or operations?", "why": "Different teams have different BytePlus workloads: Ark for product/developer, VLM for QA/inspection, Seedream/Seedance conditional on marketing", "unlocks": "Correctly scopes which BytePlus product and use case is relevant", "followup": "Who else from technical and commercial decision-making should be involved?"},
        {"q": "Is the priority internal AI tooling, model API infrastructure, multimodal/visual QA, or external creative/product marketing workflows?", "why": "Priority determines whether Ark, VLM, or creative products are most relevant", "unlocks": "Product prioritization and POC design", "followup": "Is there a specific product feature or internal tool we could benchmark against?"},
        {"q": "What model APIs or platforms does your engineering team use today?", "why": "Identifies current stack and Ark integration opportunity", "unlocks": "Vendor intelligence and switching motivation", "followup": "What are the main pain points with your current model stack — cost, latency, governance, or capability?"},
        {"q": "What is the approximate monthly model API call volume, and how many applications or teams are using AI?", "why": "Volume and breadth are the primary commercial sizing inputs", "unlocks": "Commercial model and Ark platform scope", "followup": "Is that growing rapidly as you add AI to more products?"},
        {"q": "Do you have UI testing, visual inspection, accessibility, or device diagnostic workflows that could benefit from visual AI?", "why": "VLM/multimodal is a natural fit for consumer tech companies with device or app ecosystems", "unlocks": "VLM opportunity scope", "followup": "What is the volume of screenshots or UI frames processed in QA today?"},
        {"q": "What success metric matters most for a POC — model quality, inference latency, cost reduction, governance, or developer experience?", "why": "Success criteria are required for commercial qualification", "unlocks": "POC design and evaluation criteria", "followup": "Is there a specific product milestone or evaluation deadline we should align to?"},
    ],
}

_VERTICAL_AE_SA_VIEWS: dict[str, dict] = {
    "marketing_adtech": {
        "ae_why": "Marketing and adtech companies have high-volume creative and AI workloads across campaign production, performance optimization, and data/insights. BytePlus can address creative generation (Seedance/Seedream), model API platform (Ark), and creative QA (VLM).",
        "ae_pain": ["Possible: scaling creative production for growing client or market volume", "Possible: managing multi-model API cost and quality across campaigns", "Possible: automating brand safety and creative QA reviews"],
        "ae_stakeholders": "Creative/production lead, Head of AI/ML, CTO/CPO, Head of Performance Marketing, commercial decision owner",
        "ae_budget": "What is the current AI tools or creative production budget? Is there an existing vendor contract expiring? Who approves AI platform spend?",
        "ae_next": "Agree on which team/use case to scope first; design a POC benchmark for one campaign or workflow; confirm decision owner.",
        "sa_workload": ["Possible: LLM-based campaign copy, briefing, or insights (Ark / model platform)", "Possible: image ad creative generation at campaign scale (Seedream)", "Possible: video ad creative generation (Seedance)", "Possible: creative QA / brand safety automation (VLM)"],
        "sa_stack": "Ask: current LLM/image/video APIs (OpenAI/Anthropic/Adobe Firefly/Runway/Midjourney?), API call volume, latency/cost requirements, existing integrations",
        "sa_volume": "Monthly creative variants, API calls, video/image generations, QA assets reviewed per month",
        "sa_integration": "API integration method (REST/SDK), data residency/compliance requirements, CI/CD or workflow integration, authentication and access control",
        "sa_poc": "API benchmark: generate image/video variants for one campaign prompt set and compare quality, cost, latency vs current tool. Or model routing: route copy/insights queries through Ark and compare cost and quality.",
    },
    "media_entertainment": {
        "ae_why": "Entertainment companies produce high-frequency visual and video assets for releases, campaigns, and library management. BytePlus addresses visual content production (Seedream/Seedance), content intelligence (VLM), and internal AI tools (Ark).",
        "ae_pain": ["Possible: high cost and slow turnaround for visual asset production per release", "Possible: manual content review and tagging bottleneck for large media libraries", "Possible: lack of internal AI tooling for production or editorial teams"],
        "ae_stakeholders": "Head of Content/Production, CTO/Head of Tech, Artist/Label Relations lead (if music), commercial decision owner",
        "ae_budget": "What is the current visual production or agency budget? Is there a content tech budget? Who approves AI tool spend?",
        "ae_next": "Identify one upcoming release as a POC opportunity; confirm which team and workload to scope first; agree on benchmark criteria.",
        "sa_workload": ["Possible: image generation for poster/key visual or album art (Seedream)", "Possible: video generation for artist promos, teasers, or social clips (Seedance)", "Possible: content review, tagging, and compliance automation (VLM)", "Possible: internal model platform for editorial or production tools (Ark)"],
        "sa_stack": "Ask: current visual production tools (Adobe/Midjourney/Runway?), content management stack, AI/ML APIs, on-premise or cloud deployment needs",
        "sa_volume": "Visual assets produced per release/campaign, video/promo clips per month, library size for content review",
        "sa_integration": "Integration with content management or DAM system, rights/compliance requirements, data residency needs, API method",
        "sa_poc": "Image/video generation for an upcoming release: generate key visual or promo clip variants and benchmark against current production workflow on quality, speed, and cost.",
    },
    "ecommerce": {
        "ae_why": "Ecommerce companies need scalable product image/video production and AI-driven catalog intelligence. BytePlus addresses image generation (Seedream), video generation (Seedance), and catalog/search AI (Ark + VLM).",
        "ae_pain": ["Possible: slow and expensive product image refresh and SKU visual variation", "Possible: manual catalog QA and attribute extraction at scale", "Possible: growing demand for short-form product video for commerce channels"],
        "ae_stakeholders": "Head of Product/Catalog, Head of Marketing, CTO/Head of Engineering, commercial decision owner",
        "ae_budget": "Current creative production or catalog management budget? AI tool spend? Vendor contract expiries?",
        "ae_next": "Identify one product category or campaign for a visual generation POC; confirm catalog or marketing team as primary owner.",
        "sa_workload": ["Possible: product image generation and background replacement (Seedream)", "Possible: product demo or commerce video generation (Seedance)", "Possible: catalog QA and attribute extraction (VLM)", "Possible: AI shopping assistant and search optimization (Ark + VLM)"],
        "sa_stack": "Ask: current product image workflow (in-house/agency/Adobe Firefly?), catalog management system, current AI/ML APIs, video production stack",
        "sa_volume": "Monthly SKU visual refreshes, product videos produced, catalog QA reviews, API calls for search/recommendation",
        "sa_integration": "Integration with catalog system or PIM, CDN and image delivery requirements, data residency, API authentication",
        "sa_poc": "Image generation: generate visual variants for a sample SKU set and compare quality, speed, and cost. Or VLM catalog QA: run attribute extraction on a sample catalog subset.",
    },
    "gaming": {
        "ae_why": "Gaming companies produce large volumes of art assets, marketing content, and live-service AI workloads. BytePlus addresses asset generation (Seedream), marketing video (Seedance), and NPC/support/moderation (Ark + VLM).",
        "ae_pain": ["Possible: high art asset production cost and slow iteration in development", "Possible: expensive and slow game trailer and marketing video production", "Possible: scaling player support and content moderation for live-service titles"],
        "ae_stakeholders": "Art Director / Head of Development, Head of Marketing, Head of Live Operations, CTO, commercial decision owner",
        "ae_budget": "Current art/production or marketing budget? AI tool spend for the studio? Existing vendor contracts?",
        "ae_next": "Identify one title or workflow as a POC opportunity; confirm whether art, marketing, or live ops is the priority team.",
        "sa_workload": ["Possible: game concept art and asset generation (Seedream)", "Possible: trailer and marketing video generation (Seedance)", "Possible: NPC dialogue and narrative AI (Ark)", "Possible: player support automation (Ark)", "Possible: content moderation and asset QA (VLM)"],
        "sa_stack": "Ask: current art tooling (Midjourney/Stability/in-house?), video production pipeline, AI/ML APIs for in-game features, support and moderation stack",
        "sa_volume": "Art assets per sprint, trailers/marketing videos per year, support tickets per month, moderation decisions per month",
        "sa_integration": "Game engine integration (Unity/Unreal/custom?), cloud vs on-premise, data residency, API method and concurrency",
        "sa_poc": "Asset generation: produce concept art or item visuals for one game title and benchmark iteration speed, style consistency, and cost.",
    },
    "ai_video_creative": {
        "ae_why": "AI creative platforms are core BytePlus targets. Seedance (video generation) and Seedream (image generation) directly address the platform's generation workload, with Ark for model routing and evaluation.",
        "ae_pain": ["Possible: current generation model quality or consistency not meeting platform bar", "Possible: API cost or latency constraints limiting volume or monetization", "Possible: frequent model re-evaluation creating switching overhead"],
        "ae_stakeholders": "CTO/Head of Engineering, Head of Product, commercial decision owner",
        "ae_budget": "Current generation API cost per month? Existing provider contracts and expiry? Evaluation timeline?",
        "ae_next": "Run a quality and cost benchmark against current generation model; share Seedance API access and benchmark prompt set.",
        "sa_workload": ["Possible: video generation quality and throughput (Seedance — main workload)", "Possible: image generation pipeline integration (Seedream)", "Possible: model evaluation and API routing (Ark)"],
        "sa_stack": "Ask: current generation model (Runway/Pika/Luma/Kling/Sora?), API call volume, latency SLA, cost per generation, prompt type distribution",
        "sa_volume": "Daily/monthly video generations, peak concurrency, image generation volume, API error rate and retry volume",
        "sa_integration": "REST/gRPC API, async job queue vs synchronous, output format/resolution requirements, CDN/storage integration, authentication",
        "sa_poc": "Benchmark Seedance against current provider: generate a standard batch of prompts, measure visual quality, temporal consistency, latency P50/P95, and cost per generation.",
    },
    "enterprise_llm": {
        "ae_why": "Enterprise AI platform deals are high-value. Ark is the primary BytePlus product for model gateway, routing, and governance. VLM/OCR is the secondary workload for document intelligence.",
        "ae_pain": ["Possible: high and growing LLM API cost across multiple teams and applications", "Possible: lack of governance, access control, or audit trail for AI tool usage", "Possible: multi-vendor model management complexity and switching overhead"],
        "ae_stakeholders": "CTO / Head of AI Platform, Head of Engineering, CISO/Compliance lead, commercial decision owner",
        "ae_budget": "Current AI infrastructure or model API spend? Existing enterprise contracts (OpenAI/Azure/AWS)? Procurement timeline?",
        "ae_next": "Confirm priority use case and team; design a model routing or document intelligence POC; map the approval and procurement process.",
        "sa_workload": ["Possible: model gateway and API routing for internal AI tools (Ark — main workload)", "Possible: document understanding, OCR, and visual data extraction (VLM/OCR)", "Possible: internal assistant and RAG workflow (Ark)"],
        "sa_stack": "Ask: current model stack (OpenAI/Anthropic/Gemini/Azure/Bedrock/internal?), monthly call volume, number of teams/apps using AI, governance requirements",
        "sa_volume": "Monthly model API calls, document processing volume, number of teams and applications, peak concurrency",
        "sa_integration": "Deployment model (cloud/VPC/on-premise), data residency and compliance (SOC2/GDPR/local?), SSO/auth integration, observability and logging",
        "sa_poc": "Model routing POC: route a sample of internal AI queries through Ark and compare cost, latency, and governance controls vs current stack.",
    },
    "consumer_technology": {
        "ae_why": "Consumer tech companies building AI products are BytePlus platform targets. Ark for model routing/evaluation, VLM for visual QA/inspection, and conditional creative (Seedream/Seedance) for marketing teams.",
        "ae_pain": ["Possible: growing model API cost as AI is added to more products", "Possible: need for a managed model platform with routing, governance, and evaluation", "Possible: visual QA or UI inspection workflows that need AI automation"],
        "ae_stakeholders": "Head of AI/ML or Developer Platform, CTO, Head of Product, commercial decision owner",
        "ae_budget": "Current model API spend? Existing vendor contracts? Who approves AI platform spend?",
        "ae_next": "Identify priority use case (model platform vs VLM vs creative); confirm team; design a focused POC.",
        "sa_workload": ["Possible: model API routing, evaluation, and governance (Ark — main workload)", "Possible: VLM/OCR for UI inspection, visual QA, or accessibility (VLM)", "Possible: image/video generation for marketing or product-launch (Seedream/Seedance — conditional)"],
        "sa_stack": "Ask: current model APIs (OpenAI/Anthropic/Gemini/Azure/Bedrock/internal?), monthly call volume, device/app platform, QA tooling stack",
        "sa_volume": "Monthly model API calls, UI screenshots or images processed per QA cycle, number of products/teams using AI",
        "sa_integration": "API integration (REST/SDK), device on-device vs cloud, data residency and privacy requirements, CI/CD integration for QA automation",
        "sa_poc": "Ark model routing POC: route a sample of internal AI product queries through Ark and benchmark cost, latency, and developer experience vs current stack.",
    },
}


def _web_search_note(data: dict) -> str:
    source_status = effective_source_status(data)
    ws = str(source_status.get("web_search") or "").lower()
    if ws in ("disabled_or_not_configured", "disabled", "not_configured", ""):
        return "*Public web/news/LinkedIn research not run because web search is disabled. Re-run without PREP_WEB_SEARCH_DISABLED=1 for richer intelligence.*"
    return ""


def _apollo_org_data(data: dict) -> dict:
    apollo = data.get("apollo") or {}
    if apollo.get("status") in ("organization_matched", "partial"):
        return apollo.get("organization") or {}
    return {}


def public_intelligence_snapshot(data: dict) -> str:
    customer = data.get("customer") or {}
    enrichment = data.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    vertical = data.get("vertical") or {}
    org = _apollo_org_data(data)
    source_status = effective_source_status(data)
    search_results = data.get("search_results") or []
    web_results = [r for r in search_results if r.get("source") == "web"]
    ws = str(source_status.get("web_search") or "").lower()
    web_ran = ws not in ("disabled_or_not_configured", "disabled", "not_configured", "")

    company_name = dossier.get("company") or customer.get("company_name") or customer.get("name") or "To Validate"
    what_they_do = dossier.get("what_they_do") or customer.get("description") or ""
    official = official_company_overview_evidence(data)
    if official and (not what_they_do or str(what_they_do).startswith("To Validate")):
        what_they_do = str(official.get("claim") or "").strip()
    vertical_display = vertical.get("display_name") or "To Validate"
    vertical_conf = vertical.get("confidence") or "unknown"

    product_modules = dossier.get("product_modules") or []
    products_text = (", ".join(str(p) for p in product_modules) if isinstance(product_modules, list) and product_modules else str(product_modules) if product_modules else "To Validate: main products/business lines. Ask in meeting.")

    target_users = dossier.get("target_users") or ""
    business_model = dossier.get("business_model") or ""

    hq = dossier.get("hq") or customer.get("hq") or ""
    if not hq:
        hq_parts = [p for p in [org.get("hq_city"), org.get("hq_state"), org.get("hq_country")] if p]
        if hq_parts:
            hq = f"Public Signal: {', '.join(hq_parts)} (Apollo) (?)"

    emp = org.get("employee_count") or org.get("estimated_num_employees") or dossier.get("employee_count")
    emp_text = f"Public Signal: ~{emp:,} employees (Apollo) (?)" if emp else "To Validate: employee count. Ask in meeting."

    revenue = org.get("annual_revenue")
    if revenue and str(revenue).strip():
        currency = org.get("annual_revenue_currency") or org.get("revenue_currency")
        revenue_text = f"Public Signal: {_format_apollo_revenue(revenue, currency)} (Apollo) (?)"
    else:
        funding = dossier.get("funding") or ""
        revenue_text = f"Public Signal: {funding}" if funding else "To Validate: no revenue or funding signal found. Ask in meeting."

    traffic_raw = dossier.get("traffic_source_scale") or ""
    scale_signals = dossier.get("scale_signals") or ""
    subtype_name = evidence_subtype_name(data)
    if subtype_name == "agency_marketing_services":
        mau_fallback = "Not publicly confirmed. Ask in meeting. Possible proxies: monthly website visits, client brands served, campaign volume, creative asset volume, API calls, content pieces produced."
    else:
        mau_fallback = "Not publicly confirmed. Ask in meeting. Possible proxies: website traffic, app users, creators/customers served, campaign/content volume."
    # Revenue signals are account scale evidence, not MAU/traffic — never use as MAU proxy
    _is_revenue = lambda s: "revenue signal" in str(s).lower() or "annual revenue" in str(s).lower()
    _traffic_ok = traffic_raw and not str(traffic_raw).startswith("To Validate") and not str(traffic_raw).startswith("Not Found") and not _is_revenue(traffic_raw)
    _scale_ok = scale_signals and not str(scale_signals).startswith("Not Found") and not _is_revenue(scale_signals)
    if _traffic_ok:
        mau_text = f"Public Signal: {traffic_raw}"
    elif _scale_ok:
        mau_text = f"Public Signal: {scale_signals}"
    else:
        mau_text = mau_fallback

    ai_signals_raw = dossier.get("ai_signals") or enrichment.get("ai_signals") or []
    ai_signals_text = "; ".join(ai_signals_raw) if isinstance(ai_signals_raw, list) and ai_signals_raw else (str(ai_signals_raw) if ai_signals_raw else "")
    if not ai_signals_text and web_results:
        ai_kws = ("ai", "artificial intelligence", "machine learning", "generative", "llm", "model", "gpt", "neural")
        ai_mentions = [r.get("title") or "" for r in web_results[:5] if any(k in (r.get("snippet") or r.get("title") or "").lower() for k in ai_kws)]
        if ai_mentions:
            ai_signals_text = "Public Signal: " + "; ".join(m for m in ai_mentions[:3] if m)
    if not ai_signals_text:
        ai_signals_text = "Not publicly confirmed from available sources. Ask in meeting: are you building with AI today?"

    linkedin = org.get("linkedin_url") or dossier.get("linkedin") or ""
    if linkedin:
        linkedin_text = f"Public Signal: {linkedin} (Apollo)."
        linkedin_text += " LinkedIn page not fetched — web search disabled." if not web_ran else " LinkedIn content accessibility depends on session."
    else:
        linkedin_text = "LinkedIn signal not publicly accessible in this run. Ask in meeting."

    # Filter web results for Recent AI/Product/Partnership News:
    # Exclude G2 compare/alternatives pages and generic competitor/review URLs — these are
    # useful for competitor intelligence but should not appear as AI/product news.
    def _is_news_eligible(r: dict) -> bool:
        _url = (r.get("url") or "").lower()
        _title = (r.get("title") or "").lower()
        _snip = (r.get("snippet") or "").lower()
        if any(bad in _url for bad in ("/compare", "/alternatives", "/competitors", "/categories", "/reviews")):
            return False
        if any(bad in _title for bad in ("alternative", "vs ", "compare", "competitors")):
            return False
        if any(bad in _snip for bad in ("alternative to ", "alternatives to ", "vs. ", " vs ")):
            return False
        return True

    _news_results = [r for r in web_results[:8] if _is_news_eligible(r)]
    recent_news_items = []
    for r in _news_results[:6]:
        title = r.get("title") or ""
        url = r.get("url") or ""
        if title and url:
            recent_news_items.append(f"[{title}]({url})")
        elif title:
            recent_news_items.append(title)
    if recent_news_items:
        recent_news = "; ".join(recent_news_items[:4]) + " (Public Signal)"
    elif subtype_name == "agency_marketing_services":
        recent_news = "Not publicly confirmed from compatible sources. Ask in meeting whether AI is being used in creative production, campaign automation, model/API infrastructure, localization, or creative QA."
    else:
        recent_news = "Web search not run or no public news found in this run." if not web_ran else "No relevant public news found in this run."

    techs = org.get("technologies") or org.get("technology_names") or []
    filtered = _filter_byteplus_relevant_techs(techs, max_count=8)
    tech_text = f"Public Signal: {', '.join(filtered)} (Apollo)" if filtered else "No technology stack signals found in Apollo. Ask in meeting."

    web_note = _web_search_note(data)
    rows = [
        ("Company / Brand", val(company_name, "To Validate")),
        ("What They Do", val(what_they_do, "To Validate: ask in meeting what the core business is.")),
        ("Vertical", f"{vertical_display} (Confidence: {confidence_label(vertical_conf)})"),
        ("Main Products / Business Lines", products_text),
        ("Target Users / Customer Segments", val(target_users, "To Validate: ask in meeting who the main users or customers are.")),
        ("Business Model", val(business_model, "To Validate: ask in meeting whether revenue is subscription, credits, API, enterprise contract, advertising, or other.")),
        ("HQ / Region", val(hq, "To Validate: ask in meeting.")),
        ("Employee Count", emp_text),
        ("Revenue / Funding Signal", revenue_text),
        ("MAU / Traffic / Audience Scale", mau_text),
        ("Public AI Signals", ai_signals_text),
        ("LinkedIn / Executive Signals", linkedin_text),
        ("Recent AI / Product / Partnership News", recent_news),
        ("Technology Stack Signals", tech_text),
    ]
    lines = ["### Public Intelligence Snapshot"]
    if web_note:
        lines += ["", web_note]
    lines += ["", table(rows)]
    return "\n".join(lines)


def ai_opportunity_map(data: dict) -> str:
    vertical = data.get("vertical") or {}
    vertical_name = vertical.get("name") or "default"
    opportunities = _VERTICAL_OPPORTUNITY_MAP.get(vertical_name) or [
        ("Text / LLM", "Internal assistant, copy generation, workflow automation", "Most companies have text-heavy workflows that benefit from LLM automation", "Monthly text/copy generation volume", "What AI writing or assistant tools does your team use today?"),
        ("Image", "Visual content generation, creative assets, product visuals", "Image generation is relevant across marketing, ecommerce, and entertainment", "Monthly image generation or creative production volume", "Do you produce images or visual creative assets at scale today?"),
        ("Video", "Short-form video content, marketing/product videos, creative generation", "Video generation is growing across creative, marketing, and content verticals", "Monthly video production volume", "Do you produce video content at scale, and is that a growing workflow?"),
        ("VLM / OCR / Multimodal", "Visual understanding, document processing, content review", "Multimodal AI addresses visual QA, document intelligence, and content compliance", "Monthly visual assets reviewed or documents processed", "Do you have visual inspection, document processing, or content review workflows today?"),
        ("Model Platform", "Model routing, evaluation, API management, cost optimization", "Most companies evaluating AI need a managed model layer", "Monthly model API calls and models in evaluation", "What model APIs do you use today, and how do you manage model selection and cost?"),
    ]
    enrichment = data.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    org = _apollo_org_data(data)
    techs = org.get("technologies") or org.get("technology_names") or []
    filtered_techs = _filter_byteplus_relevant_techs(techs, max_count=4)
    tech_signal = f"Apollo tech signals: {', '.join(filtered_techs)}" if filtered_techs else "No technology signals found"
    scale_str_raw = str(dossier.get("scale_signals") or "")
    _scale_is_revenue = "revenue signal" in scale_str_raw.lower() or "annual revenue" in scale_str_raw.lower()
    scale_str = scale_str_raw[:80]
    opp_subtype = evidence_subtype_name(data)
    lines = [
        "### AI / Model Opportunity Map",
        "",
        "| Modality | Possible Opportunity | Why It May Matter | Current Evidence / Signal | Sizing Needed | First-Meeting Question |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in opportunities:
        if len(row) != 5:
            continue
        modality, opp, why, sizing, question = row
        if modality in ("Model Platform", "Text / LLM") and filtered_techs:
            evidence = tech_signal
        elif modality in ("Video", "Image"):
            if opp_subtype == "agency_marketing_services":
                # Use vertical/workflow signal — not revenue signal — as Image/Video evidence
                evidence = "Marketing / AdTech vertical; digital agency / marketing services; creative production and campaign/content services."
            elif scale_str and not scale_str.startswith("Not Found") and not _scale_is_revenue:
                evidence = f"Public Signal: {scale_str}"
            else:
                evidence = "To Validate"
        else:
            evidence = "To Validate"
        lines.append(f"| {modality} | {opp} | {why} | {evidence} | {sizing} | {question} |")
    lines.append("")
    return "\n".join(lines)


def competitor_vendor_section(data: dict) -> str:
    vertical = data.get("vertical") or {}
    vertical_name = vertical.get("name") or "default"
    known = data.get("known") or {}
    enrichment = data.get("enrichment") or {}
    confirmed_vendors = known.get("current_vendors") or known.get("current_models") or ""
    confirmed_text = str(confirmed_vendors).strip() if confirmed_vendors else ""
    org = _apollo_org_data(data)
    techs = org.get("technologies") or org.get("technology_names") or []
    filtered = _filter_byteplus_relevant_techs(techs, max_count=6)
    categories = _VERTICAL_COMPETITOR_CATEGORIES.get(vertical_name) or [
        "OpenAI / Anthropic / Gemini (general LLM)", "Azure OpenAI / AWS Bedrock (cloud AI)",
        "Midjourney / Stability AI (image generation)", "Runway / Pika / Luma (video generation)",
    ]
    lines = ["### Competitor / Vendor Intelligence", ""]
    if confirmed_text and not confirmed_text.lower().startswith("not found") and not confirmed_text.lower().startswith("to validate"):
        lines += [f"**Confirmed vendor relationship:** {confirmed_text}", ""]
    else:
        lines += ["**Confirmed vendor relationship:** Not confirmed from available sources. Ask in meeting.", ""]
    if filtered:
        lines += [f"**Public technology signal (Apollo):** {', '.join(filtered)}", ""]
    else:
        lines += ["**Public technology signal:** No technology stack signals found in Apollo. Ask in meeting.", ""]
    lines += ["**Possible competitor categories to validate (vertical-specific):**"]
    for cat in categories:
        lines.append(f"- Possible competitor category to validate: {cat}")
    lines += [
        "",
        "**Unknowns to ask in meeting:**",
        "- Which LLM or AI model APIs does your team use today?",
        "- Are you using any image or video generation tools?",
        "- What do you dislike about your current AI vendor or tool?",
        "- Is there an existing vendor contract expiring in the next 6-12 months?",
        "",
        "*Safety note: Do not claim the customer uses any specific vendor unless a source confirms it. All vendor categories above are possibilities to validate in meeting.*",
        "",
    ]
    return "\n".join(lines)


def possible_solution_paths(data: dict) -> str:
    vertical = data.get("vertical") or {}
    vertical_name = vertical.get("name") or "default"
    paths = _VERTICAL_SOLUTION_PATHS.get(vertical_name) or [
        {"name": "A. Model platform and AI workflow", "products": "Ark", "why": "Most companies evaluating AI need a managed model layer for routing, evaluation, and cost control", "validate": "Current model stack, monthly API call volume, governance requirements, evaluation timeline", "poc": "Route a sample of internal AI queries through Ark and benchmark cost, latency, and developer experience vs current stack"},
        {"name": "B. Image generation for visual content", "products": "Seedream", "why": "Image generation is a common near-term workload across marketing, ecommerce, and entertainment", "validate": "Confirm whether image generation is an active need; monthly creative or image production volume", "poc": "Generate visual variants for a sample creative brief and compare against current workflow"},
        {"name": "C. Video generation for content production", "products": "Seedance", "why": "Video generation addresses short-form content, product video, and creative production needs", "validate": "Confirm whether video generation is an active need; monthly video production volume", "poc": "Generate short-form video content for a sample prompt set and benchmark quality, speed, and cost"},
    ]
    lines = ["### Possible Solution Paths", "", "*All paths are Possible hypotheses to validate — do not present as confirmed until workload is confirmed in meeting.*", ""]
    for path in paths:
        lines += [
            f"**{path['name']}**",
            f"- BytePlus products: {path['products']}",
            f"- Why it may fit: {path['why']}",
            f"- What must be validated: {path['validate']}",
            f"- Suggested first POC: {path['poc']}",
            "",
        ]
    return "\n".join(lines)


def first_meeting_question_plan(data: dict) -> str:
    vertical = data.get("vertical") or {}
    vertical_name = vertical.get("name") or "default"
    questions = _VERTICAL_FIRST_MEETING_QUESTIONS.get(vertical_name) or [
        {"q": "Which team is this discussion for, and what is the priority use case?", "why": "Team scope and priority use case determine which BytePlus product is most relevant", "unlocks": "Product scoping and POC design", "followup": "Who else from technical and commercial decision-making should be involved?"},
        {"q": "What AI tools, APIs, or models is your team using today?", "why": "Identifies current vendor stack and switching opportunity", "unlocks": "Vendor intelligence and differentiation", "followup": "What do you like or dislike about your current solution?"},
        {"q": "What is the approximate monthly volume — API calls, content pieces, or generations?", "why": "Volume is the key sizing input for commercial discussions", "unlocks": "Commercial model and POC scope", "followup": "Is that volume growing, and what is driving the growth?"},
        {"q": "Which modalities are in scope: text, image, video, multimodal/VLM, or model platform?", "why": "Modality determines which BytePlus product to prioritize", "unlocks": "Product prioritization", "followup": "Which of these is the most urgent need?"},
        {"q": "What markets and languages are in scope?", "why": "Localization scale affects the opportunity for image/video generation and language AI", "unlocks": "Localization scope and multi-market opportunity", "followup": "How is localization handled today?"},
        {"q": "What would make a POC successful, and who owns the decision?", "why": "Success criteria and decision owner are required for commercial qualification", "unlocks": "POC criteria and next steps", "followup": "Is there a specific timeline or milestone we should align to?"},
    ]
    lines = [
        "### First Meeting Question Plan",
        "",
        "| # | Question | Why Ask | What Answer Unlocks | Follow-Up |",
        "| --- | --- | --- | --- | --- |",
    ]
    for idx, q in enumerate(questions, 1):
        lines.append(f"| {idx} | {q['q']} | {q['why']} | {q['unlocks']} | {q['followup']} |")
    lines.append("")
    return "\n".join(lines)


def ae_sa_views(data: dict) -> str:
    vertical = data.get("vertical") or {}
    vertical_name = vertical.get("name") or "default"
    views = _VERTICAL_AE_SA_VIEWS.get(vertical_name) or {
        "ae_why": "Vertical not yet confirmed. Focus on qualifying team scope, active workload, and decision owner before recommending BytePlus products.",
        "ae_pain": ["Possible: AI model API management and cost optimization", "Possible: content or creative production automation", "Possible: document or visual intelligence workloads"],
        "ae_stakeholders": "CTO / Head of AI, technical owner, commercial decision owner — to validate",
        "ae_budget": "Current AI infrastructure or tool spend? Existing vendor contracts? Who approves AI platform decisions?",
        "ae_next": "Qualify team scope and active workload first; do not pitch product until workload is confirmed.",
        "sa_workload": ["Possible: model platform / API routing (Ark)", "Possible: image or video generation (Seedream/Seedance)", "Possible: VLM / OCR / multimodal intelligence"],
        "sa_stack": "Ask: current AI/ML APIs, model providers, monthly volume, latency requirements",
        "sa_volume": "Monthly API calls, content volume, documents processed — to confirm in meeting",
        "sa_integration": "API integration method, data residency, compliance requirements — to confirm in meeting",
        "sa_poc": "Design after qualifying team scope and active workload in first meeting.",
    }
    lines = [
        "### AE View",
        "",
        f"**Why this account may matter:** {views['ae_why']}",
        "",
        "**Business pain hypotheses (Possible — to validate):**",
    ]
    for pain in views["ae_pain"]:
        lines.append(f"- {pain}")
    lines += [
        "",
        f"**Stakeholder / buying role to validate:** {views['ae_stakeholders']}",
        "",
        f"**Budget / procurement questions:** {views['ae_budget']}",
        "",
        f"**Recommended next step:** {views['ae_next']}",
        "",
        "---",
        "",
        "### SA View",
        "",
        "**Likely technical workload hypotheses (Possible — to validate):**",
    ]
    for wl in views["sa_workload"]:
        lines.append(f"- {wl}")
    lines += [
        "",
        f"**Model / vendor stack to ask:** {views['sa_stack']}",
        "",
        f"**Volume sizing questions:** {views['sa_volume']}",
        "",
        f"**Integration / latency / data / compliance questions:** {views['sa_integration']}",
        "",
        f"**Suggested POC shape:** {views['sa_poc']}",
        "",
    ]
    return "\n".join(lines)


def thirty_second_brief(data: dict) -> str:
    customer = data.get("customer") or {}
    vertical = data.get("vertical") or {}
    vertical_name = vertical.get("name") or "default"
    customer_name = customer.get("name") or "To Validate"
    vertical_display = vertical.get("display_name") or "To Validate: confirm vertical"
    views = _VERTICAL_AE_SA_VIEWS.get(vertical_name, {})
    paths = _VERTICAL_SOLUTION_PATHS.get(vertical_name, [])
    qs = _VERTICAL_FIRST_MEETING_QUESTIONS.get(vertical_name, [])
    angles = [f"{p['name'].split('. ', 1)[-1]} ({p['products']})" for p in paths[:3]] if paths else [
        "Model platform / API routing (Ark) — if model management is the priority",
        "Image generation (Seedream) — if visual content production is confirmed",
        "Video generation (Seedance) — if video production is confirmed",
    ]
    top_qs = [q["q"] for q in qs[:5]] if qs else [
        "Which team is this for and what is the priority use case?",
        "What AI tools and APIs are used today?",
        "What is the monthly volume?",
        "Which modalities are in scope: text, image, video, VLM?",
        "What would make a POC successful and who decides?",
    ]
    ae_next = views.get("ae_next", "Qualify team scope and active workload first.")
    if not active_workload_confirmed(data):
        dont_pitch = "Do not pitch specific BytePlus products (Ark/Seedance/Seedream/VLM) by name until workload is confirmed in meeting. Lead with questions, not product pitches."
    else:
        dont_pitch = "Do not expand deep product-specific proposals until commercial qualification (budget, decision owner, timeline) is confirmed."
    lines = [
        "## AE/SA 30-Second Brief",
        "",
        f"**Customer / Vertical:** {customer_name} — {vertical_display}",
        "",
        f"**Why this account may matter:** {views.get('ae_why', 'To Validate: confirm vertical and active workload before assessing account importance.')}",
        "",
        "**Top 3 possible BytePlus angles:**",
    ]
    for a in angles:
        lines.append(f"- Possible: {a}")
    lines += ["", "**Top 5 first-meeting questions:**"]
    for i, q in enumerate(top_qs, 1):
        lines.append(f"{i}. {q}")
    lines += [
        "",
        f"**What to prepare before the call:** {ae_next}",
        "",
        f"**What not to pitch until confirmed:** {dont_pitch}",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section merge helpers — new 8-section structure
# ---------------------------------------------------------------------------

def account_intelligence_snapshot(data: dict) -> str:
    """Section 2: single consolidated intelligence table.

    Combines the key fields from Essential Background Check and Public Intelligence
    Snapshot into one table. Company background appears exactly once. Keeps both
    ### headings so tests that search for them still find them.
    """
    customer = data.get("customer") or {}
    enrichment = data.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    org = _apollo_org_data(data)
    vertical = data.get("vertical") or {}
    source_status = effective_source_status(data)
    # Defense-in-depth: apply entity guard locally using the rejected_domains set populated
    # by _filter_compatible_search_results() in run_prep.  This catches any contamination that
    # slipped through into dossier fields (e.g. MCP enrichment that ran before the guard).
    _rejected_domains: set[str] = set(source_status.get("rejected_domains") or [])

    def _url_rejected(url: str) -> bool:
        if not _rejected_domains:
            return False
        from urllib.parse import urlparse as _up
        h = _up(url).netloc.lower().removeprefix("www.")
        return h in _rejected_domains

    def _text_mentions_rejected(text: str) -> bool:
        if not _rejected_domains:
            return False
        tl = text.lower()
        return any(d in tl for d in _rejected_domains)

    raw_web = data.get("search_results") or []
    web_results = [r for r in raw_web if not _url_rejected(r.get("url", ""))]

    ws = str(source_status.get("web_search") or "").lower()
    web_ran = ws not in ("disabled_or_not_configured", "disabled", "not_configured", "")

    # --- company identity ---
    company_name = dossier.get("company") or customer.get("company_name") or customer.get("name") or "To Validate"
    domain = customer.get("website") or customer.get("domain") or ""
    source = best_evidence_url(data)

    # What They Do — Apollo exact-domain first, then dossier, then web claim
    official = official_company_overview_evidence(data)
    what_they_do = dossier.get("what_they_do") or customer.get("description") or ""
    if official and (not what_they_do or str(what_they_do).startswith("To Validate")):
        what_they_do = str(official.get("claim") or "").strip()
    what_they_do_val = what_they_do or "To Validate: ask in meeting what the core business is."

    # Vertical
    vertical_display = vertical.get("display_name") or "To Validate"
    vertical_conf = vertical.get("confidence") or "unknown"

    # Product modules / business lines
    product_modules = dossier.get("product_modules") or []
    products_text = (", ".join(str(p) for p in product_modules) if isinstance(product_modules, list) and product_modules
                     else str(product_modules) if product_modules
                     else "To Validate: main products/business lines. Ask in meeting.")

    # Detect music/entertainment subtype — used for template fallbacks below
    vertical_name = vertical.get("name") or ""
    _company_lower = (company_name or "").lower()
    _desc_lower = (what_they_do_val or "").lower()
    _is_music_ent = vertical_name in ("media_entertainment",) and any(
        term in _company_lower or term in _desc_lower
        for term in ("music", "record label", "artist management", "entertainment", "album", "label ")
    )

    # Override Business Lines if product_modules look like AI use cases rather than business lines
    _ai_use_case_terms = ("generation", "voice/audio", "audio generation", "voice generation",
                          "text generation", "image generation", "video generation", "tts", "stt")
    if _is_music_ent and (
        products_text.startswith("To Validate")
        or any(term in products_text.lower() for term in _ai_use_case_terms)
    ):
        products_text = (
            "Likely: music/record production, artist management, entertainment management, "
            "release promotion, artist/content IP, campaign/content services (?)"
        )

    # Target users / business model — template fallback for music/entertainment and media verticals
    raw_target_users = dossier.get("target_users") or ""
    raw_business_model = dossier.get("business_model") or ""
    if not raw_target_users:
        if _is_music_ent:
            raw_target_users = VERTICAL_SUBTYPE_TEMPLATES["music_entertainment"]["target_users"]
        elif vertical_name == "media_entertainment":
            raw_target_users = VERTICAL_SUBTYPE_TEMPLATES["media_entertainment_content"]["target_users"]
    if not raw_business_model:
        if _is_music_ent:
            raw_business_model = VERTICAL_SUBTYPE_TEMPLATES["music_entertainment"]["business_model"]
        elif vertical_name == "media_entertainment":
            raw_business_model = VERTICAL_SUBTYPE_TEMPLATES["media_entertainment_content"]["business_model"]

    _ent_likely = _is_music_ent or vertical_name == "media_entertainment"
    target_users = (
        f"Likely: {raw_target_users} (?)" if (raw_target_users and _ent_likely and not raw_target_users.startswith("Likely"))
        else raw_target_users or "To Validate: ask in meeting."
    )
    business_model = (
        f"Likely: {raw_business_model} (?)" if (raw_business_model and _ent_likely and not raw_business_model.startswith("Likely"))
        else raw_business_model or "To Validate: ask in meeting."
    )

    # Scale signals — employee count, revenue, founded year, HQ
    scale_parts = []
    emp = org.get("employee_count") or org.get("estimated_num_employees") or dossier.get("employee_count")
    if emp:
        scale_parts.append(f"~{emp:,} employees (Apollo)")
    revenue = org.get("annual_revenue")
    if revenue and str(revenue).strip():
        currency = org.get("annual_revenue_currency") or org.get("revenue_currency")
        scale_parts.append(f"{_format_apollo_revenue(revenue, currency)} (Apollo)")
    founded = dossier.get("founded_year") or org.get("founded_year")
    if founded:
        scale_parts.append(f"Founded {founded}")
    hq = dossier.get("hq") or customer.get("hq") or ""
    if not hq:
        hq_parts = [p for p in [org.get("hq_city"), org.get("hq_state"), org.get("hq_country")] if p]
        if hq_parts:
            hq = ", ".join(hq_parts) + " (Apollo)"
    if hq:
        scale_parts.append(f"HQ: {hq}")
    scale_text = " | ".join(scale_parts) if scale_parts else "To Validate: ask in meeting."

    # MAU / Traffic — same logic as public_intelligence_snapshot, exclude revenue signals
    traffic_raw = dossier.get("traffic_source_scale") or ""
    scale_signals = dossier.get("scale_signals") or ""
    subtype_name = evidence_subtype_name(data)
    if subtype_name == "agency_marketing_services":
        mau_fallback = "Not publicly confirmed. Ask in meeting. Possible proxies: monthly website visits, client brands served, campaign volume, creative asset volume, API calls, content pieces produced."
    else:
        mau_fallback = "Not publicly confirmed. Ask in meeting. Possible proxies: website traffic, app users, creators/customers served, campaign/content volume."
    _is_revenue = lambda s: "revenue signal" in str(s).lower() or "annual revenue" in str(s).lower()
    if traffic_raw and not str(traffic_raw).startswith("To Validate") and not str(traffic_raw).startswith("Not Found") and not _is_revenue(traffic_raw):
        mau_text = f"Public Signal: {traffic_raw}"
    elif scale_signals and not str(scale_signals).startswith("Not Found") and not _is_revenue(scale_signals):
        mau_text = f"Public Signal: {scale_signals}"
    else:
        mau_text = mau_fallback

    # AI signals — filter dossier entries that reference rejected domains (MCP contamination guard)
    _raw_ai_signals = dossier.get("ai_signals") or enrichment.get("ai_signals") or []
    ai_signals_raw = [s for s in (_raw_ai_signals if isinstance(_raw_ai_signals, list) else [_raw_ai_signals] if _raw_ai_signals else []) if not _text_mentions_rejected(str(s))]
    ai_signals_text = "; ".join(str(s) for s in ai_signals_raw) if ai_signals_raw else ""
    if not ai_signals_text and web_results:
        ai_kws = ("ai", "artificial intelligence", "machine learning", "generative", "llm", "model", "gpt", "neural")
        ai_mentions = [r.get("title") or "" for r in web_results[:5] if any(k in (r.get("snippet") or r.get("title") or "").lower() for k in ai_kws)]
        if ai_mentions:
            ai_signals_text = "Public Signal: " + "; ".join(m for m in ai_mentions[:3] if m)
    if not ai_signals_text:
        ai_signals_text = "Not publicly confirmed. Ask in meeting: are you building with AI today?"

    # Recent news (filtered — no G2/alternatives pages)
    def _is_news_eligible(r: dict) -> bool:
        _u = (r.get("url") or "").lower()
        _t = (r.get("title") or "").lower()
        _s = (r.get("snippet") or "").lower()
        if any(bad in _u for bad in ("/compare", "/alternatives", "/competitors", "/categories", "/reviews")):
            return False
        if any(bad in _t for bad in ("alternative", "vs ", "compare", "competitors")):
            return False
        if any(bad in _s for bad in ("alternative to ", "alternatives to ", " vs ")):
            return False
        return True
    _news_results = [r for r in web_results[:8] if _is_news_eligible(r)]
    news_items = []
    for r in _news_results[:4]:
        t = r.get("title") or ""
        u = r.get("url") or ""
        if t and u:
            news_items.append(f"[{t}]({u})")
        elif t:
            news_items.append(t)
    if news_items:
        recent_news = "; ".join(news_items) + " (Public Signal)"
    elif subtype_name == "agency_marketing_services":
        recent_news = "Not publicly confirmed. Ask in meeting: AI in creative production, campaign automation, localization, or creative QA?"
    elif _is_music_ent or vertical_name == "media_entertainment":
        recent_news = (
            "Not publicly confirmed from compatible sources. Ask in meeting whether AI is being explored "
            "for artist promotion, teaser videos, key visuals, localization, or content review."
        )
    else:
        recent_news = ("Web search disabled." if not web_ran else "No relevant public news found.")

    # LinkedIn
    linkedin = org.get("linkedin_url") or dossier.get("linkedin") or ""
    linkedin_text = f"Public Signal: {linkedin} (Apollo)" if linkedin else "Not publicly accessible in this run. Ask in meeting."

    # Tech stack
    techs = org.get("technologies") or org.get("technology_names") or []
    filtered = _filter_byteplus_relevant_techs(techs, max_count=8)
    tech_text = f"Public Signal: {', '.join(filtered)} (Apollo)" if filtered else "Not in Apollo. Ask in meeting."

    # Known / To Validate summary
    identity_conf = (data.get("confidence_layers") or {}).get("identity_confidence") or "unknown"
    apollo_status = source_status.get("apollo_org", "disabled")
    if apollo_status in ("organization_matched",):
        id_label = "Apollo exact-domain match (canonical identity)"
    elif apollo_status in ("partial",):
        id_label = "Apollo partial match (validate)"
    elif identity_conf in ("confirmed", "high"):
        id_label = "Web / domain confirmed"
    else:
        id_label = f"Web-only fallback (identity_confidence: {identity_conf})"
    workload_conf = (data.get("confidence_layers") or {}).get("active_workload_confidence") or "unknown"
    known_summary = f"Identity: {id_label} | Vertical confidence: {vertical_conf} | Active workload: {workload_conf}"

    web_note = _web_search_note(data)
    rows = [
        ("Company / Brand", val(company_name, "To Validate")),
        ("Domain", val(domain, "To Validate")),
        ("What They Do", val(what_they_do_val, "To Validate: ask in meeting.")),
        ("Vertical", f"{vertical_display} (Confidence: {confidence_label(vertical_conf)})"),
        ("Business Lines", products_text),
        ("Target Users / Customer Segments", val(target_users, "To Validate: ask in meeting.")),
        ("Business Model", val(business_model, "To Validate: ask in meeting.")),
        ("Scale Signals", scale_text),
        ("MAU / Traffic / Volume Proxy", mau_text),
        ("Public AI / News Signals", ai_signals_text),
        ("Recent AI / Product / Partnership News", recent_news),
        ("LinkedIn / Executive Signals", linkedin_text),
        ("Technology Stack Signals", tech_text),
        ("Known / To Validate", known_summary),
    ]

    # Table sits under ### Essential Background Check so section-content extractors find it.
    # ### Public Intelligence Snapshot heading follows as a legacy anchor for test compatibility.
    lines = [
        "### Essential Background Check",
        "",
        table(rows),
        "",
        "### Public Intelligence Snapshot",
    ]
    if web_note:
        lines += ["", web_note]

    apollo_people = apollo_stakeholders_section(data)
    if apollo_people:
        lines += ["", apollo_people]

    return "\n".join(lines)


def opportunity_hypotheses(data: dict) -> str:
    """Section 3: one-line workload summary + AI Opportunity Map.

    BytePlus fit hypotheses and meeting prep assets are already covered by
    AE/SA Executive Brief, Possible Solution Paths, and AE View / SA View.
    This section keeps only the workload summary line and the map table to
    avoid repetition.
    """
    workload_label = "Workload hypotheses to validate" if _is_apollo_hypothesis_fit(data) else "Possible AI workloads"
    layers = confidence_layers(data)

    lines = [
        f"**{workload_label}:** {effective_use_cases_concise(data)}",
        f"Active workload confidence: {layers.get('active_workload_confidence') or 'unknown'}",
        "",
        ai_opportunity_map(data),
    ]
    return "\n".join(lines)


def first_meeting_validation_plan(data: dict) -> str:
    """Section 6: single combined table for first-meeting questions.

    Replaces the separate First Meeting Question Plan + Standard Discovery Questions
    + Meeting Output Template with one table (# | Question | Why Ask | Unlocks |
    Follow-Up | Record Into) and a compact pre-fill block.

    Keeps ### First Meeting Question Plan heading so tests find it.
    """
    vertical = data.get("vertical") or {}
    vertical_name = vertical.get("name") or "default"
    qs = _VERTICAL_FIRST_MEETING_QUESTIONS.get(vertical_name, [])

    def _record_into(q: dict) -> str:
        text = (q.get("q") or "").lower()
        # Team/scope check must come before market check because "marketing" contains "market"
        if any(k in text for k in ("which team", "what team", "which department", "who is this")):
            return "Team / stakeholder / use-case owner"
        # Combined POC + decision owner — must come before standalone budget/owner check
        if (any(k in text for k in ("successful", "poc", "pilot", "criteria", "success criteria"))
                and any(k in text for k in ("who owns", "decision", "owner"))):
            return "POC criteria / decision owner"
        if any(k in text for k in ("budget", "procurement", "decision owner", "decision-owner", "spending", "vendor decision", "who owns")):
            return "Budget / decision owner / procurement"
        if any(k in text for k in ("poc", "success metric", "success criteria", "benchmark", "criteria", "make a poc", "successful")):
            return "POC criteria / benchmark"
        # Content creation vs content understanding → workload / solution path
        if any(k in text for k in ("content creation", "content understanding", "creation vs", "creation or content")):
            return "Workload priority / solution path"
        # "markets and languages" / "localiz" — avoid matching "marketing" with "market"
        if any(k in text for k in ("markets and", "language", "localiz", "region", "territory", "localization")):
            return "Market / localization scope"
        # Volume check before vendor stack — avoids "API calls" in volume questions matching "api"
        if any(k in text for k in ("volume", "monthly", "daily", "how many", "how much", "cadence", "per month",
                                   "release cadence", "how many titles", "how many albums")):
            return "Monthly volume / sizing"
        if any(k in text for k in ("format", "modali", "image", "video", "vlm", "creative format", "creative type")):
            return "Workload priority / modality scope"
        # Vendor stack — "creative tool" catches "AI or creative tools"; "model" catches API/model questions;
        # "used today" / "use today" catch tool-usage questions; avoid plain "api" (matches "API calls")
        if any(k in text for k in ("ai tool", "creative tool", "ai or creative", "model", "vendor", "provider",
                                   "stack", "using today", "use today", "used today", "tools are", "tools used",
                                   "openai", "anthropic", "replicate")):
            return "Current vendor stack"
        if any(k in text for k in ("team", "stakeholder", "use case", "scope", "owner", "department", "who else")):
            return "Team / stakeholder / use-case owner"
        if any(k in text for k in ("timeline", "next step", "milestone", "launch", "when")):
            return "Next step / timeline"
        return "Meeting notes"

    lines = [
        "### First Meeting Question Plan",
        "",
        "| # | Question | Why Ask | What Answer Unlocks | Follow-Up | Record Into |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if qs:
        for idx, q in enumerate(qs, 1):
            lines.append(f"| {idx} | {q['q']} | {q['why']} | {q['unlocks']} | {q['followup']} | {_record_into(q)} |")
    else:
        _defaults = [
            ("Which team is this discussion for and what is the priority use case?", "Team scope determines BytePlus product priority", "Product scoping and POC design", "Who else should be involved?", "Team / stakeholder / use-case owner"),
            ("What AI tools and APIs is your team using today?", "Identifies current vendor stack and switching opportunity", "Vendor intelligence", "What do you like/dislike about current tools?", "Current vendor stack"),
            ("What is the approximate monthly volume?", "Volume is the key sizing input", "Commercial model and POC scope", "Is volume growing?", "Monthly volume / sizing"),
            ("Which creative formats are in scope: text, image, video, VLM?", "Format determines BytePlus product to prioritize", "Product prioritization", "Which is most urgent?", "Workload priority / modality scope"),
            ("What markets and languages are in scope?", "Localization scale affects opportunity", "Localization scope", "How handled today?", "Market / localization scope"),
            ("What would make a POC successful, and who owns the budget decision?", "Success criteria and decision owner required for commercial qualification", "POC criteria and next steps", "Is there a specific timeline?", "Budget / decision owner / procurement"),
        ]
        for idx, (q, why, unlocks, followup, record) in enumerate(_defaults, 1):
            lines.append(f"| {idx} | {q} | {why} | {unlocks} | {followup} | {record} |")

    lines.append("")

    # Compact pre-fill block — key signals only (no repeated question blocks)
    items = data.get("question_prefill") or []
    if items:
        lines += [
            "**Pre-filled discovery signals** *(validate all in meeting)*",
            "",
        ]
        for item in items[:5]:
            answer = val(item.get("answer"), "Not Found.")
            confidence = item.get("confidence")
            evidence = item.get("evidence") or []
            evidence_text = "; ".join(str(x) for x in evidence[:1]) if evidence else ""
            existing_label, answer_clean = strip_confidence_prefix(answer)
            if existing_label:
                answer = answer_clean
            # Apply same workload gating as full render_question_prefill_sections
            section_text = val(item.get("section"), "")
            question_text = val(item.get("question"))
            workload_specific = any(
                term in f"{section_text} {question_text}".lower()
                for term in ("image", "video", "llm", "model", "vendor", "generation", "cross-sell", "usage", "stack")
            )
            if (weak_identity(data) or weak_or_unknown_vertical(data) or (not active_workload_confirmed(data) and workload_specific)) and confidence in {"known", "likely"} and "core business" not in question_text.lower():
                confidence = "to_validate"
                answer = "To Validate: active AI or BytePlus-relevant workload is not confirmed."
                evidence_text = ""
            if confidence == "likely" and "(?)" not in answer:
                answer += " (?)"
            conf_label = confidence_label(confidence)
            ev_part = f" | Evidence: {evidence_text}" if evidence_text else ""
            lines.append(f"- **{question_text}** ({conf_label}): {answer}{ev_part}")

        omitted = (data.get("prospecting") or {}).get("omitted_questions_summary") or []
        if omitted:
            lines += ["", "*Omitted / collapsed:* " + " | ".join(omitted)]
    else:
        lines.append("*Use master template from `references/master-template.md` for discovery script.*")

    return "\n".join(lines)


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

    prior_docs = data.get("prior_docs") or []
    prior_notes = data.get("prior_notes") or []
    search_results = data.get("search_results") or []

    questions = derive_questions(data)

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

    refs = []
    if meeting.get("url"):
        refs.append(f"- Calendar event: {meeting['url']}")
    used_prior = usable_prior_docs(prior_docs)
    _debug_mode = bool(data.get("debug"))
    if used_prior:
        if _debug_mode:
            refs.append("- Prior customer profile content used: " + ", ".join(d.get("url", d.get("title", "")) for d in used_prior))
        else:
            refs.append(f"- Prior customer profile content used: {len(used_prior)} doc(s) with usable content.")
    elif prior_docs:
        # Non-debug: count summary only; debug: show all candidate URLs
        if _debug_mode:
            refs.append("- Candidate prior customer docs found, but no usable prior customer profile content was extracted: " + ", ".join(d.get("url", d.get("title", "")) for d in prior_docs))
        else:
            refs.append(f"- Candidate prior customer docs found: {len(prior_docs)}. Usable extracted content: 0.")
    else:
        refs.append("- Prior Customer Profile docs: No prior customer profile docs found.")
    refs.append("- Prior AI Notes / Minutes: " + (", ".join(n.get("url", n.get("title", "")) for n in prior_notes) if prior_notes else "No prior AI Notes found."))
    # Entity guard: only show web results that were not rejected by the canonical entity guard
    _rj_rejected_domains: set[str] = set(source_status.get("rejected_domains") or [])

    def _web_url_rejected(url: str) -> bool:
        if not _rj_rejected_domains:
            return False
        from urllib.parse import urlparse as _up2
        h = _up2(url).netloc.lower().removeprefix("www.")
        return h in _rj_rejected_domains

    web_results = [r for r in search_results if r.get("source") == "web" and not _web_url_rejected(r.get("url", ""))]
    kb_results = [r for r in search_results if r.get("source") != "web"]
    refs.append("- Web search results: " + (", ".join(r.get("url", r.get("label", "")) for r in web_results) if web_results else "No web search references found."))
    refs.append("- Mira / Knowledge Base search results: " + (", ".join(r.get("url", r.get("label", "")) for r in kb_results) if kb_results else "No Mira / Knowledge Base references found."))
    source_links = enrichment.get("source_links") or []
    if enrichment.get("source") == "web_search":
        enrichment_label = "Web enrichment source"
        enrichment_fallback = "No web enrichment source link available."
    else:
        enrichment_label = "Enrichment source"
        _aorg = source_status.get("apollo_org", "")
        if _aorg in ("organization_matched", "partial") or enrichment.get("fit_source") == "apollo_hypothesis":
            enrichment_fallback = "Apollo organization enrichment (no direct source link)."
        elif _aorg in ("disabled", ""):
            enrichment_fallback = "Apollo not configured."
        else:
            enrichment_fallback = "Apollo unavailable / no exact domain match."
    refs.append(f"- {enrichment_label}: " + (", ".join(s.get("url", s.get("label", "")) for s in source_links) if source_links else enrichment_fallback))

    evidence_table_text = evidence_table(data)
    source_status = effective_source_status(data)
    _ok_values = {"available", "ok", "organization_matched", "partial", "disabled", "not_attempted",
                  "explicit_url_only", "used", "supplemented", "not_used", "usable_results_found"}
    _excluded_status_keys = {"mcp", "web_rejected_count", "rejected_domains", "explicit_url_enrichment", "canonical_identity_source"}
    unavailable = [f"{k}: {v}" for k, v in source_status.items() if str(v).lower() not in _ok_values and k not in _excluded_status_keys]
    _rejected_count = int(source_status.get("web_rejected_count") or 0)
    if _rejected_count > 0:
        unavailable.append(f"web_rejected_count: {_rejected_count} web result(s) filtered — same-name different-entity sources excluded")

    brief = thirty_second_brief(data)
    account_intel = account_intelligence_snapshot(data)
    opp_hyp = opportunity_hypotheses(data)
    competitor_intel = competitor_vendor_section(data)
    solution_paths = possible_solution_paths(data)
    validation_plan = first_meeting_validation_plan(data)
    ae_sa = ae_sa_views(data)

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
            "## 1. AE/SA Executive Brief\n\n" + brief,
            "## 2. Account Intelligence Snapshot\n\n" + account_intel,
            "## 3. Opportunity Hypotheses\n\n" + opp_hyp,
            "## 4. Competitor / Vendor Intelligence\n\n" + competitor_intel,
            "## 5. Possible Solution Paths\n\n" + solution_paths,
            "## 6. First Meeting Validation Plan\n\n" + validation_plan,
            "## 7. AE View / SA View\n\n" + ae_sa,
            "# Others\n\n## Reference & Engagement\n\n" + "\n".join(refs) + "\n\n## Client Engagement\n\n" + "\n".join(engagement_rows) + "\n\n## Evidence Table\n\n" + evidence_table_text,
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
