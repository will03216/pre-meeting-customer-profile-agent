#!/usr/bin/env python3
"""Portable orchestration CLI for BytePlus pre-meeting prep.

This script runs with the current user's local Lark CLI authentication. It
keeps all optional integrations best-effort so the skill remains useful from a
fresh zip install and in dry-run mode.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import html
import time as time_module
import uuid
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    from render_prep_doc import render
except ImportError:  # pragma: no cover - defensive for unusual launch paths
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from render_prep_doc import render

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from enrichment.apollo_enrichment import enrich_with_apollo as _enrich_with_apollo
    from enrichment.apollo_enrichment import apollo_result_to_dict as _apollo_result_to_dict
    _APOLLO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _APOLLO_AVAILABLE = False


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "outputs" / "prep"
DEFAULT_PROSPECTING_PROMPT = REPO_ROOT / "config" / "prospecting_prompt.md"
INDUSTRY_PLAYBOOK_DIR = REPO_ROOT / "config" / "industry_playbooks"
DEFAULT_CALENDAR_ID = os.getenv("LARK_CALENDAR_ID", "primary")
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Europe/London")
INTERNAL_DOMAINS = {
    item.strip().lower()
    for item in os.getenv(
        "INTERNAL_EMAIL_DOMAINS",
        "bytedance.com,byteplus.com,lark.com,larksuite.com,feishu.cn",
    ).split(",")
    if item.strip()
}
PERSONAL_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "me.com",
    "proton.me",
    "protonmail.com",
    "qq.com",
    "163.com",
    "126.com",
}
INTERNAL_TITLE_PATTERNS = [
    "standup",
    "sync",
    "1:1",
    "one-on-one",
    "internal",
    "weekly",
    "daily",
    "retro",
    "retrospective",
    "planning",
    "team meeting",
    "all hands",
    "review",
    "catch up",
]


@dataclass
class PrepInput:
    mode: str
    value: str | None
    window: str | None
    contact: str | None = None
    company: str | None = None
    domain: str | None = None
    user_urls: list[str] = field(default_factory=list)


@dataclass
class CustomerIdentity:
    canonical_name: str | None
    domain: str | None
    email: str | None
    confidence: str
    evidence: list[str]
    contact_name: str | None = None
    company_name: str | None = None


@dataclass
class PrepContext:
    customer: CustomerIdentity
    event: dict[str, Any] | None
    prior_docs: list[dict[str, Any]]
    enrichment: dict[str, Any] | None
    missing_context: list[str]
    search_results: list[dict[str, Any]] = field(default_factory=list)
    docs_search_available: bool = True
    web_search_available: bool = False
    web_search_status: str = "disabled_or_not_configured"
    company_overview_status: str = "disabled_or_not_configured"
    known: dict[str, Any] = field(default_factory=dict)
    apollo_enrichment: dict[str, Any] | None = None
    user_urls: list[str] = field(default_factory=list)


@dataclass
class PrepResult:
    doc_title: str
    doc_url: str | None
    mode: str
    customer_name: str | None
    confidence: str
    missing_context: list[str]
    local_json_path: str = ""
    local_markdown_path: str = ""
    run_mode: str = ""
    lark_doc_status: str = ""


class PrepError(RuntimeError):
    """User-facing orchestration error."""


def debug_log(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[debug] {message}", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=False)
    modes.add_argument("--event-id")
    modes.add_argument("--customer")
    modes.add_argument("--email")
    modes.add_argument("--window")
    parser.add_argument("--contact", help="Contact/stakeholder person name; use with --company and/or --domain.")
    parser.add_argument("--company", help="Confirmed company name; may be used with --contact and/or --domain.")
    parser.add_argument("--domain", help="Confirmed company domain; may be used alone or with --contact/--company/--customer.")
    parser.add_argument("--url", action="append", dest="urls", default=[],
                        help="Explicit public URL(s) to use as direct enrichment sources (e.g. company website, startup profile). Can be repeated.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-json", action="store_true")
    parser.add_argument("--create-doc", action="store_true", help="Explicitly allow new doc creation; this is the default outside dry-run.")
    parser.add_argument("--no-create-doc", action="store_true", help="Generate local markdown/json only; skip Lark doc creation or update.")
    parser.add_argument("--update-existing", action="store_true")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--prospecting-prompt", help="Path to prospecting prompt guidance; defaults to config/prospecting_prompt.md.")
    parser.add_argument("--industry", help="Industry playbook name, e.g. marketing_adtech, ai_video_creative, ecommerce, gaming, enterprise_llm.")
    parser.add_argument("--workload", help="Explicit active workload, e.g. video_generation, image_generation, llm_platform, model_api.")
    parser.add_argument("--no-apollo", action="store_true", help="Disable Apollo.io enrichment for this run.")
    parser.add_argument("--apollo-refresh", action="store_true", help="Bypass Apollo cache and fetch fresh data.")
    parser.add_argument("--apollo-max-people", type=int, default=None, help="Max stakeholder candidates to fetch from Apollo (default: APOLLO_MAX_PEOPLE env or 5).")
    parser.add_argument("--apollo-debug", action="store_true", help="Print Apollo API diagnostics to stderr.")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    if not any(getattr(args, field, None) for field in ("event_id", "customer", "domain", "email", "window", "contact", "company")):
        parser.error("one input mode or --contact/--company/--domain is required")
    return args


def prep_input_from_args(args: argparse.Namespace) -> PrepInput:
    _user_urls: list[str] = list(getattr(args, "urls", None) or [])
    if args.contact or args.company:
        return PrepInput(mode="contact-company", value=args.company or args.domain or args.contact, window=None, contact=args.contact or args.customer, company=args.company, domain=args.domain, user_urls=_user_urls)
    if args.customer and args.domain:
        return PrepInput(mode="contact-company", value=args.company or args.domain, window=None, contact=args.customer, company=args.company, domain=args.domain, user_urls=_user_urls)
    if args.domain:
        return PrepInput(mode="domain", value=args.domain, window=None, domain=args.domain, user_urls=_user_urls)
    for mode in ("event_id", "customer", "email", "window"):
        value = getattr(args, mode)
        if value:
            return PrepInput(mode=mode.replace("_", "-"), value=value, window=value if mode == "window" else None, user_urls=_user_urls)
    raise PrepError("No input mode supplied.")


def industry_slug(value: str | None) -> str:
    if not value:
        return "default"
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    aliases = {
        "marketing": "marketing_adtech",
        "adtech": "marketing_adtech",
        "martech": "marketing_adtech",
        "ai_video": "ai_video_creative",
        "creative": "ai_video_creative",
        "video": "ai_video_creative",
        "llm": "enterprise_llm",
        "enterprise": "enterprise_llm",
        "default_unknown": "default",
    }
    return aliases.get(slug, slug or "default")


def load_prospecting_prompt(path_value: str | None = None, debug: bool = False) -> dict[str, str]:
    path = Path(path_value).expanduser() if path_value else DEFAULT_PROSPECTING_PROMPT
    if not path.is_absolute():
        path = REPO_ROOT / path
    try:
        try:
            display_path = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            display_path = path.as_posix()
        return {"path": display_path, "content": path.read_text(encoding="utf-8"), "available": "true"}
    except OSError:
        debug_log(debug, f"prospecting prompt missing; falling back safely: {path}")
        return {"path": path.as_posix(), "content": "", "available": "false"}


def parse_playbook_markdown(text: str, name: str, path: Path) -> dict[str, Any]:
    display_name = name.replace("_", " ").title()
    sections: dict[str, list[str]] = {}
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("vertical name:"):
            display_name = line.split(":", 1)[1].strip() or display_name
            continue
        if line.endswith(":") and not line.startswith("-"):
            current = line[:-1].strip().lower().replace(" ", "_")
            sections.setdefault(current, [])
            continue
        if line.startswith("-") and current:
            sections.setdefault(current, []).append(line[1:].strip())
    return {
        "name": name,
        "display_name": display_name,
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sections": sections,
        "raw": text,
    }


def load_industry_playbook(name: str | None = None, debug: bool = False) -> dict[str, Any]:
    requested = industry_slug(name)
    path = INDUSTRY_PLAYBOOK_DIR / f"{requested}.md"
    if not path.exists():
        debug_log(debug, f"industry playbook '{requested}' missing; falling back to default")
        requested = "default"
        path = INDUSTRY_PLAYBOOK_DIR / "default.md"
    try:
        return parse_playbook_markdown(path.read_text(encoding="utf-8"), requested, path)
    except OSError:
        return {"name": "default", "display_name": "Default / Unknown", "path": path.as_posix(), "sections": {}, "raw": ""}


KEYWORD_DISPLAY_MAP: dict[str, str] = {
    "음반": "music/record production",
    "연예": "entertainment",
    "매니지먼트": "management",
    "아티스트": "artists",
}

COUNTRY_ADJECTIVES: dict[str, str] = {
    "south korea": "Korean", "korea": "Korean",
    "japan": "Japanese",
    "china": "Chinese", "people's republic of china": "Chinese",
    "taiwan": "Taiwanese",
    "thailand": "Thai",
    "vietnam": "Vietnamese",
    "indonesia": "Indonesian",
    "malaysia": "Malaysian",
    "singapore": "Singaporean",
    "india": "Indian",
    "brazil": "Brazilian",
}


def _is_substantially_non_latin(text: str) -> bool:
    """Return True if >30% of alphabetic characters are outside the Latin script (U+0000–U+024F)."""
    if not text:
        return False
    alpha_chars = [ch for ch in text if ch.isalpha()]
    if len(alpha_chars) < 4:
        return False
    non_latin = sum(1 for ch in alpha_chars if ord(ch) > 0x024F)
    return non_latin / len(alpha_chars) > 0.30


def _build_english_apollo_description(org: dict) -> str:
    """Construct a concise English description from Apollo org metadata fields."""
    country = str(org.get("hq_country") or org.get("country") or "").strip()
    country_adj = COUNTRY_ADJECTIVES.get(country.lower(), country if country else "")
    industry = str(org.get("industry") or "").strip()
    keywords_raw = list(org.get("keywords") or [])
    desc_raw = str(org.get("short_description") or "")
    for kw, en_label in KEYWORD_DISPLAY_MAP.items():
        if kw in desc_raw and en_label not in keywords_raw:
            keywords_raw.append(en_label)
    keywords = [
        str(kw).strip() for kw in keywords_raw[:6]
        if kw and not _is_substantially_non_latin(str(kw).strip())
    ]
    name = str(org.get("name") or "").strip()
    kw_text = " and ".join(keywords[:2]) if keywords else ""
    parts = [p for p in [country_adj, industry] if p]
    prefix = " ".join(parts)
    if prefix and kw_text:
        return f"{prefix} company focused on {kw_text}."
    if prefix:
        return f"{prefix} company."
    if name and kw_text:
        return f"{name} focused on {kw_text}."
    if name and industry:
        return f"{name}: {industry} company."
    return "Company details available via Apollo — validate before the meeting."


def _summarize_description(desc: str, max_sentences: int = 2) -> str:
    """Trim a long description to the first `max_sentences` sentences for user-facing fields."""
    desc = desc.strip()
    if len(desc) <= 220:
        return desc
    parts = re.split(r"(?<=[.!?])\s+", desc)
    if len(parts) <= max_sentences:
        return desc
    summary = " ".join(parts[:max_sentences])
    if not summary.endswith((".", "!", "?")):
        summary += "."
    return summary


_CURRENCY_SYMBOLS: dict[str, str] = {"USD": "$", "EUR": "€", "GBP": "£", "CNY": "¥", "JPY": "¥", "KRW": "₩"}


def _format_apollo_revenue(value: Any, currency: str | None = None) -> str:
    """Format an Apollo revenue value into a human-readable string.

    Examples: 1065000000.0 + "USD" -> "~$1.1B annual revenue signal"
              50000000.0  + None   -> "~50M annual revenue signal (currency not confirmed)"
    """
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


VERTICAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "marketing_adtech": (
        "intent marketing",
        "customer acquisition",
        "paid media",
        "adtech",
        "martech",
        "comparison platform",
        "lead generation",
        "conversion optimization",
        "landing page",
        "performance marketing",
        "advertising",
        "marketing services",
        "agency network",
        "agency networks",
        "media buying",
        "brand marketing",
        "creative services",
        "affiliate",
        "creative testing",
        "cac",
        "conversion lift",
        "lead quality",
        "acquisition workflow",
        "digital agency",
        "digital marketing",
        "creative agency",
        "creative production",
        "content creation",
        "advertising agency",
        "marketing agency",
        "content production",
        "digital transformation",
        "marketing technology",
        "ai-powered marketing",
        "creative partner",
        "content marketing",
        "marketing automation",
        "campaign management",
        "data-driven marketing",
        "programmatic",
        "digital advertising",
        "digital-first marketing",
        "s4 capital",
        "s4capital",
        "technology services and consulting",
        "data and measurement",
        "marketing and technology services",
        "marketing technology services",
        "creative technology",
        "campaign creative",
    ),
    "ai_video_creative": (
        "ai video",
        "creative studio",
        "video generation",
        "image generation",
        "animation",
        "short drama",
        "character consistency",
        "reference image",
        "cinematic",
        "vfx",
        "creator tool",
        "batch generation",
        "generative creative",
        "creative platform",
        "ai-driven imagery",
        "ai-powered image",
        "generative image",
    ),
    "enterprise_llm": (
        "llm",
        "agent",
        "rag",
        "knowledge base",
        "enterprise ai",
        "chatbot",
        "internal assistant",
        "token usage",
        "model routing",
        "model evaluation",
        "fine-tuning",
        "private deployment",
        "vpc",
        "on-prem",
        "compliance",
        "data residency",
        "prompt caching",
        "inference cost",
    ),
    "ecommerce": (
        "ecommerce",
        "online retail",
        "marketplace",
        "product listing",
        "sku",
        "product recommendation",
        "shopping",
        "merchant",
        "product image",
        "product imagery",
        "catalog",
        "livestream commerce",
        "review analysis",
        "product search",
        "product discovery",
        "fashion brand",
        "retail brand",
        "beauty brand",
        "product photography",
        "model imagery",
        "virtual try-on",
        "visual commerce",
    ),
    "gaming": (
        "game",
        "gaming",
        "studio",
        "player",
        "npc",
        "ugc",
        "asset generation",
        "character",
        "level design",
        "live ops",
        "game marketing",
        "localization",
        "game trailer",
        "in-game content",
    ),
    "media_entertainment": (
        "media and entertainment",
        "broadcasting",
        "streaming",
        "production",
        "content distribution",
        "news",
        "format licensing",
        "studio",
        "broadcasters",
        "streamers",
        "entertainment",
        "music",
        "artist management",
        "record production",
        "talent management",
        "music label",
        "record label",
        "music production",
        "음반",
        "연예",
        "매니지먼트",
        "아티스트",
    ),
    "consumer_technology": (
        "consumer devices",
        "consumer electronics",
        "iphone",
        "mac",
        "ipad",
        "app store",
        "hardware revenue",
        "device ecosystem",
    ),
    "enterprise_software": (
        "enterprise software",
        "saas",
        "developer tools",
        "api platform",
        "cloud software",
    ),
}

VERTICAL_DISPLAY_NAMES = {
    "media_entertainment": "Media / Entertainment / Content",
    "consumer_technology": "Consumer Technology",
    "enterprise_software": "Enterprise Software / SaaS",
}


def evidence_snippets(context: PrepContext) -> list[str]:
    snippets: list[str] = []
    event = context.event or {}
    if event.get("summary"):
        snippets.append(f"Calendar title: {event['summary']}")
    for doc in context.prior_docs[:5]:
        text = doc.get("summary") or doc.get("title") or ""
        if text:
            snippets.append(f"Lark doc: {text[:180]}")
    enrichment = context.enrichment or {}
    if enrichment.get("description"):
        snippets.append(f"Enrichment: {enrichment['description'][:220]}")
    for result in context.search_results[:8]:
        text = " ".join(str(result.get(k, "")) for k in ("title", "snippet", "url"))
        if text.strip():
            snippets.append(f"Web: {text[:220]}")
    # Include raw page text from explicit user-provided URL pages so keyword matching
    # sees the full startup-profile / homepage content, not just the normalized snippet.
    for page in (enrichment.get("page_evidence") or [])[:4]:
        if page.get("source") == "explicit_user_url":
            raw_text = (page.get("text") or "").strip()
            if raw_text:
                snippets.append(f"ExplicitURL: {raw_text[:400]}")
    apollo = context.apollo_enrichment or {}
    apollo_org = apollo.get("organization") or {}
    if apollo_org.get("short_description"):
        snippets.append(f"Apollo: {str(apollo_org['short_description'])[:220]}")
    if apollo_org.get("industry"):
        snippets.append(f"Apollo industry: {apollo_org['industry']}")
    for kw in (apollo_org.get("keywords") or [])[:5]:
        snippets.append(f"Apollo keyword: {kw}")
    city = apollo_org.get("hq_city") or apollo_org.get("city")
    country = apollo_org.get("hq_country") or apollo_org.get("country")
    state = apollo_org.get("hq_state") or apollo_org.get("state")
    location_parts = [p for p in [city, state, country] if p]
    if location_parts:
        snippets.append(f"Apollo location: {', '.join(str(p) for p in location_parts)}")
    emp = apollo_org.get("num_employees") or apollo_org.get("employee_count")
    if emp:
        snippets.append(f"Apollo employees: {emp}")
    for tech in (apollo_org.get("technologies") or apollo_org.get("technology_names") or [])[:5]:
        tech_name = tech if isinstance(tech, str) else (tech.get("name") or "")
        if tech_name:
            snippets.append(f"Apollo tech: {tech_name}")
    linkedin = apollo_org.get("linkedin_url")
    if linkedin:
        snippets.append(f"Apollo linkedin: {linkedin}")
    return snippets


def infer_vertical(context: PrepContext, explicit_industry: str | None = None) -> dict[str, Any]:
    if explicit_industry:
        slug = industry_slug(explicit_industry)
        playbook = load_industry_playbook(slug)
        return {"name": playbook["name"], "display_name": playbook["display_name"], "confidence": "confirmed", "evidence": [f"Explicit CLI --industry {slug}"]}
    snippets = evidence_snippets(context)
    haystack = "\n".join(snippets).lower()
    scores: dict[str, list[str]] = {}
    for vertical, keywords in VERTICAL_KEYWORDS.items():
        for keyword in keywords:
            if keyword in haystack:
                scores.setdefault(vertical, []).append(keyword)
    if not scores:
        return {"name": "default", "display_name": "Default / Unknown", "confidence": "unknown", "evidence": []}
    best, matches = max(scores.items(), key=lambda item: len(item[1]))
    confidence = "likely" if len(set(matches)) >= 2 else "weak"
    if confidence == "weak":
        weak_label = KEYWORD_DISPLAY_MAP.get(matches[0], matches[0])
        return {"name": "default", "display_name": "Default / Unknown", "confidence": "weak", "evidence": [f"Weak signal: {weak_label}"]}
    playbook = load_industry_playbook(best)
    return {
        "name": best,
        "display_name": VERTICAL_DISPLAY_NAMES.get(best) or playbook["display_name"],
        "confidence": confidence,
        "evidence": [f"Matched signal: {KEYWORD_DISPLAY_MAP.get(item, item)}" for item in sorted(set(matches))[:5]],
    }


def first_source_label(context: PrepContext) -> str:
    enrichment = context.enrichment or {}
    candidates: list[tuple[int, str]] = []
    for doc in context.prior_docs:
        if doc.get("engagement_rows"):
            url = doc.get("url") or doc.get("title") or ""
            if url:
                candidates.append((2, url))
    company = enrichment.get("company_name") or infer_company_from_docs(context.customer.canonical_name, context.prior_docs)
    for result in context.search_results:
        url = result.get("url") or ""
        if url:
            candidates.append((source_tier(url, company)[0], url))
    for link in enrichment.get("source_links") or []:
        url = link.get("url") or link.get("label") or ""
        if url:
            candidates.append((source_tier(url, company)[0], url))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: item[0])[0][1]


def question_item(section: str, question: str, answer: str, confidence: str, ask: str, why: str, evidence: list[str] | None = None, relevance: str = "high") -> dict[str, Any]:
    return {
        "section": section,
        "question": question,
        "answer": answer,
        "confidence": confidence,
        "evidence": evidence or [],
        "ask_in_meeting": ask,
        "why_it_matters": why,
        "vertical_relevance": relevance,
    }


WORKLOAD_SPECIFIC_INDUSTRIES = {"ai_video_creative"}
BROAD_VERTICAL_INDUSTRIES = {"marketing_adtech", "ecommerce", "gaming", "enterprise_llm", "default"}

VERTICAL_SUBTYPE_TEMPLATES: dict[str, dict[str, str]] = {
    "agency_marketing_services": {
        "display_name": "Marketing / AdTech / Agency Holding Company",
        "target_users": "global brands, advertisers, enterprise marketing teams, creative teams, media buyers, agency clients, and marketing operations teams",
        "business_model": "advertising, marketing services, media planning/buying, creative services, communications, data/technology-enabled marketing, and agency network services",
    },
    "intent_marketing_comparison": {
        "display_name": "Marketing / AdTech / Intent Marketing or Comparison Platform",
        "target_users": "high-intent consumers, brand/advertiser partners, and publishers",
        "business_model": "lead generation, affiliate/referral, comparison content, performance marketing, and brand partnerships",
    },
    "media_entertainment_content": {
        "display_name": "Media / Entertainment / Content",
        "target_users": "TV/streaming audiences, broadcasters/streamers, production partners, content buyers, and media partners",
        "business_model": "broadcasting, streaming, content production, format licensing/global distribution, and media partnerships",
    },
    "consumer_technology": {
        "display_name": "Consumer Technology",
        "target_users": "consumers, developers, enterprise customers, creative professionals, and ecosystem partners",
        "business_model": "hardware sales, software/services revenue, app ecosystem, subscriptions, accessories, and support",
    },
    "creative_platform": {
        "display_name": "Creative Platform / AI Video Creative",
        "target_users": "creators, designers, marketers, agencies, enterprise creative teams, and API developers",
        "business_model": "subscriptions, credits, asset licensing, API usage, enterprise/team plans, and creative tools",
    },
}


def infer_vertical_subtype(text: str, vertical_name: str | None = None, explicit_industry: str | None = None) -> dict[str, str]:
    lowered = (text or "").lower()
    explicit = industry_slug(explicit_industry or "")
    if explicit == "ai_video_creative":
        return {"name": "creative_platform", **VERTICAL_SUBTYPE_TEMPLATES["creative_platform"], "confidence": "confirmed"}
    _agency_terms = (
        "global advertising", "marketing services", "agency network", "agency networks", "media buying",
        "brand marketing", "creative services", "communications agency", "advertising and marketing",
        "digital advertising", "digital-first marketing", "marketing and technology", "marketing technology services",
        "s4 capital", "s4capital", "technology services and consulting", "data and measurement",
        "creative technology", "campaign creative", "digital agency", "marketing agency", "advertising agency",
    )
    if explicit == "marketing_adtech" or vertical_name == "marketing_adtech":
        if any(term in lowered for term in ("intent marketing", "comparison platform", "comparison platforms", "lead generation", "affiliate", "referral", "purchase decisions", "customer acquisition platform", "performance marketing platform")):
            return {"name": "intent_marketing_comparison", **VERTICAL_SUBTYPE_TEMPLATES["intent_marketing_comparison"], "confidence": "likely"}
        if any(term in lowered for term in _agency_terms):
            return {"name": "agency_marketing_services", **VERTICAL_SUBTYPE_TEMPLATES["agency_marketing_services"], "confidence": "likely"}
        return {"name": "unknown", "display_name": "Unknown", "target_users": "", "business_model": "", "confidence": "unknown"}
    if any(term in lowered for term in ("media and entertainment", "broadcasting", "streaming service", "tv channel", "news company", "content distribution", "format licensing", "global distribution", "production arm", "content buyers", "broadcasters", "streamers")):
        return {"name": "media_entertainment_content", **VERTICAL_SUBTYPE_TEMPLATES["media_entertainment_content"], "confidence": "likely"}
    if any(term in lowered for term in ("iphone", "mac", "ipad", "apple watch", "airpods", "apple tv", "consumer devices", "app store ecosystem", "consumer electronics", "hardware revenue")):
        return {"name": "consumer_technology", **VERTICAL_SUBTYPE_TEMPLATES["consumer_technology"], "confidence": "likely"}
    if any(term in lowered for term in ("creative platform", "stock assets", "templates", "design assets", "design platform", "ai-enabled image", "ai image", "ai video", "image generation", "video generation")):
        return {"name": "creative_platform", **VERTICAL_SUBTYPE_TEMPLATES["creative_platform"], "confidence": "likely"}
    if any(term in lowered for term in _agency_terms):
        return {"name": "agency_marketing_services", **VERTICAL_SUBTYPE_TEMPLATES["agency_marketing_services"], "confidence": "likely"}
    if any(term in lowered for term in ("intent marketing", "comparison platform", "comparison platforms", "lead generation", "affiliate", "referral", "purchase decisions", "customer acquisition platform", "performance marketing platform")):
        return {"name": "intent_marketing_comparison", **VERTICAL_SUBTYPE_TEMPLATES["intent_marketing_comparison"], "confidence": "likely"}
    if vertical_name == "ai_video_creative":
        return {"name": "creative_platform", **VERTICAL_SUBTYPE_TEMPLATES["creative_platform"], "confidence": "weak"}
    return {"name": "unknown", "display_name": "Unknown", "target_users": "", "business_model": "", "confidence": "unknown"}


def incompatible_field_reason(text: str, subtype: str, weak_identity_case: bool = False) -> str | None:
    lowered = (text or "").lower()
    if not lowered:
        return None
    if weak_identity_case and any(term in lowered for term in ("consumers", "advertisers", "broadcasting", "hardware sales", "subscriptions", "comparison", "agency network")):
        return "weak_identity_company_template_blocked"
    blocked: dict[str, tuple[str, ...]] = {
        "agency_marketing_services": ("intent-marketing", "intent marketing", "comparison-platform", "comparison platform", "high-intent consumers", "consumer devices", "hardware sales", "broadcasting", "streaming", "format licensing"),
        "intent_marketing_comparison": ("consumer devices", "hardware sales", "app store", "accessories", "ecosystem partners", "developers, enterprise", "creative professionals", "agency network", "agency networks", "broadcasting", "streaming", "format licensing", "content production"),
        "media_entertainment_content": ("intent-marketing", "intent marketing", "comparison-platform", "comparison platform", "high-intent consumers", "hardware sales", "app store", "agency network", "media planning/buying"),
        "consumer_technology": ("intent-marketing", "intent marketing", "comparison-platform", "comparison platform", "high-intent consumers", "agency network", "media planning/buying", "broadcasting", "format licensing", "creative-platform packaging"),
        "creative_platform": ("hardware sales", "app store", "accessories", "intent-marketing", "intent marketing", "comparison-platform", "comparison platform", "broadcasting", "format licensing", "agency network services"),
    }
    for term in blocked.get(subtype, ()):
        if term in lowered:
            return f"incompatible_with_{subtype}"
    return None


def compatibility_fallback(field: str) -> str:
    if field == "target_users":
        return "target users/customer segments are not confirmed from compatible current-customer evidence"
    if field == "business_model":
        return "business model/revenue model is not confirmed from compatible current-customer evidence"
    if field == "what_they_do":
        return "To Validate: business description could not be confirmed from compatible current-customer evidence."
    return "To Validate"


def infer_confidence_layers(context: PrepContext, vertical: dict[str, Any], explicit_workload: str | None = None) -> dict[str, str]:
    identity = "confirmed_company" if context.customer.domain or context.customer.company_name else ("weak_person_only" if context.customer.canonical_name else "unknown")
    company_vertical = vertical.get("confidence") or "unknown"
    enrichment = context.enrichment or {}
    use_cases = [str(item).lower() for item in enrichment.get("known_use_cases") or []]
    explicit = (explicit_workload or "").strip().lower()
    workload = "unknown"
    if explicit:
        workload = "confirmed"
    elif vertical.get("name") in WORKLOAD_SPECIFIC_INDUSTRIES and vertical.get("confidence") == "confirmed":
        workload = "likely"
    elif any(
        any(signal in item for signal in ("image generation", "video generation", "voice", "audio", "model api", "inference", "api or enterprise", "llm", "chatbot", "agent", "ocr"))
        for item in use_cases
    ):
        workload = "likely"
    product_fit = "possible_after_validation"
    if workload in {"likely", "confirmed"} and (enrichment.get("possible_byteplus_fit") or vertical.get("name") in WORKLOAD_SPECIFIC_INDUSTRIES):
        product_fit = "likely"
    return {
        "identity_confidence": identity,
        "company_vertical_confidence": company_vertical if company_vertical in {"unknown", "weak", "likely", "confirmed"} else "unknown",
        "active_workload_confidence": workload,
        "product_fit_confidence": product_fit,
    }


def workload_is_active(confidence_layers: dict[str, str]) -> bool:
    return confidence_layers.get("active_workload_confidence") in {"likely", "confirmed"}


def build_question_prefill(context: PrepContext, vertical: dict[str, Any], confidence_layers: dict[str, str] | None = None, description_override: str | None = None) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    enrichment = context.enrichment or {}
    known = context.known or {}
    name = vertical.get("name") or "default"
    active_workload = workload_is_active(confidence_layers or {})
    source = first_source_label(context)
    evidence = [source] if source else []
    company_desc = description_override or enrichment.get("description") or "customer/company context"
    use_cases = enrichment.get("known_use_cases") or []
    product_fit = enrichment.get("possible_byteplus_fit") or []
    fit_text = "; ".join(f"{item.get('product')}: {item.get('reason')}" for item in product_fit[:3] if item.get("product")) or "Ark / model platform; creative models if workload confirms"

    # company_desc may come from description_override (Apollo) even when context.enrichment is empty
    _has_desc = bool(company_desc and company_desc != "customer/company context")
    _desc_confidence = "known" if (_has_desc and enrichment.get("description")) else ("likely" if _has_desc else "to_validate")
    _desc_answer = (f"Likely: {company_desc} (?)" if _desc_confidence == "likely" else f"Known: {company_desc}") if _has_desc else "To Validate: core business and target users."
    common = [
        question_item(
            "Standard Discovery Questions",
            "Core business and focus group/user introduction",
            _desc_answer,
            _desc_confidence,
            "Can you confirm the exact product line, target users, and meeting scope?",
            "Anchors the pitch, use case, stakeholders, and relevant BytePlus products.",
            evidence,
        ),
        question_item(
            "AI Usage & Current Stack",
            "Which models are you currently using?",
            "Not Found.",
            "not_found",
            "Are you currently using OpenAI, Anthropic, Gemini, Fal, Replicate, AWS Bedrock, Azure, or another provider?",
            "Determines whether BytePlus should position Ark as replacement, routing layer, or evaluation platform.",
        ),
        question_item(
            "POC Qualification",
            "What would make a POC successful?",
            "To Validate: success metric, evaluator, benchmark method, and timeline are not confirmed.",
            "to_validate",
            "What metric would make the POC worth continuing: quality, cost, latency, conversion lift, or launch readiness?",
            "Turns a broad discovery call into an actionable next step.",
        ),
    ]

    if name == "marketing_adtech" and not active_workload:
        vertical_items = [
            question_item(
                "Standard Discovery Questions",
                "Are you currently focusing more on growth, monetization, or retention?",
                "To Validate: confirm whether the meeting is about growth, monetization, retention, media optimization, workflow automation, model/API infrastructure, or another use case.",
                "to_validate",
                "Which business priority should this discussion focus on: growth, monetization, operational efficiency, customer insights, creative production, or AI infrastructure?",
                "Uses the company vertical for discovery without assuming an active AI workload.",
                evidence,
            ),
            question_item(
                "AI Usage & Current Stack",
                "Current AI adoption?",
                "To Validate: active AI or BytePlus-relevant workload is not confirmed.",
                "to_validate",
                "Are you exploring AI for creative production, media optimization, customer insights, workflow automation, model/API infrastructure, or another use case?",
                "Separates company vertical from actual workload and product fit.",
            ),
        ]
        omitted = ["Product-specific image/video, model-stack, generation-volume, and cross-sell questions collapsed until workload evidence appears."]
    elif name == "marketing_adtech":
        vertical_items = [
            question_item(
                "Standard Discovery Questions",
                "Are you currently focusing more on growth, monetization, or retention?",
                "Likely: growth and monetization are relevant because available sources point to intent marketing, customer acquisition, or comparison-platform workflows. (?)",
                "likely",
                "Is the current priority conversion lift, traffic growth, lead quality, or monetization efficiency?",
                "Maps BytePlus value to revenue-side KPIs instead of generic model quality.",
                evidence,
            ),
            question_item(
                "Business Scenarios & Use Cases",
                "What metric are they focused on?",
                "Likely: conversion lift, CAC, lead quality, content production speed, and experimentation velocity. (?)",
                "likely",
                "Which KPI matters most for this evaluation: conversion lift, CAC, lead quality, content production speed, latency, or infrastructure cost?",
                "Identifies whether the proposal should emphasize model platform, creative generation, or automation.",
                evidence,
            ),
            question_item(
                "LLM Usage",
                "LLM / image / video / voice?",
                "Likely: LLM/content optimization and image creative may be relevant; video is relevant only if paid-media creative is an active workflow. (?)",
                "likely",
                "Are your AI workloads mostly text/content optimization, image creative, video creative, ranking/recommendation, or workflow automation?",
                "Prevents over-positioning Seedance before the active workload is confirmed.",
                evidence,
            ),
            question_item(
                "Image / Video Usage",
                "Daily generations?",
                "Not Found.",
                "not_found",
                "Do you generate image or video assets for paid media, landing pages, or comparison content? If yes, what is the daily or monthly volume?",
                "Sizes Seedream/Seedance opportunity and infrastructure needs.",
            ),
            question_item(
                "Cross-Sell / Upsell Discovery",
                "What can we cross-sell?",
                f"Likely: {fit_text}. (?)",
                "likely",
                "Are your near-term priorities model platform/inference, image creative, video creative, or workflow automation?",
                "Keeps cross-sell tied to confirmed workload rather than generic product listing.",
                evidence,
            ),
        ]
        omitted = ["Gaming-only NPC / level-design questions collapsed.", "Long-form cinematic video workflow omitted unless video evidence appears.", "On-prem/VPC deployment omitted unless enterprise/security evidence appears."]
    elif name == "ai_video_creative":
        vertical_items = [
            question_item("Image / Video Usage", "Most common workflows?", "Likely: image/video creative generation, editing, or batch production may be relevant. (?)", "likely", "Which workflow is most important: image generation, video generation, character consistency, reference workflows, or editing?", "Identifies Seedance/Seedream benchmark focus.", evidence),
            question_item("Image / Video Usage", "Daily generations?", "Not Found.", "not_found", "What is the daily/monthly generation volume and peak concurrency?", "Sizes API and cost model."),
            question_item("Vendor & Competitor Understanding", "Current vendors?", "Not Found.", "not_found", "Are you using Fal, Replicate, Runway, Pika, Kling, Luma, Midjourney, Stable Diffusion, or OpenAI?", "Defines replacement or augmentation angle."),
        ]
        omitted = ["Heavy LLM token questions collapsed unless text workflow evidence appears.", "Adtech traffic questions omitted unless acquisition evidence appears."]
    elif name == "consumer_technology" and not active_workload:
        vertical_items = [
            question_item(
                "Standard Discovery Questions",
                "Which team is this discussion for?",
                "To Validate: team scope (product, developer platform, AI/ML, marketing, content, or operations) not confirmed.",
                "to_validate",
                "Which team is this discussion for: product, developer platform, AI/ML, marketing, content, or operations?",
                "Determines whether to position Ark, VLM/OCR, or Seedream/Seedance.",
                evidence,
            ),
            question_item(
                "Standard Discovery Questions",
                "What is the priority use case?",
                "To Validate: confirm whether priority is internal AI tooling, model/API infrastructure, multimodal understanding, or creative/product marketing.",
                "to_validate",
                "Is the priority internal AI tooling, model/API infrastructure, multimodal understanding, or creative/product marketing workflows?",
                "Maps the discussion to the right BytePlus product and approach.",
                evidence,
            ),
            question_item(
                "AI Usage & Current Stack",
                "Current model/vendor stack?",
                "To Validate: current model stack or internal platform not confirmed.",
                "to_validate",
                "What current model/vendor stack or internal platform is being evaluated?",
                "Identifies whether BytePlus is replacing, supplementing, or integrating with an existing stack.",
            ),
            question_item(
                "POC Qualification",
                "What success metric matters most?",
                "To Validate: success metric, evaluator, benchmark method, and timeline are not confirmed.",
                "to_validate",
                "What success metric matters most: quality, latency, privacy/compliance, cost, developer productivity, or launch readiness?",
                "Turns a broad discovery call into an actionable next step.",
            ),
        ]
        omitted = ["Product-specific deep-dive questions collapsed until team scope and active workload are confirmed."]
    elif name == "consumer_technology":
        vertical_items = [
            question_item(
                "Standard Discovery Questions",
                "Which team and use case?",
                "To Validate: confirm team scope and priority use case before deep product questions.",
                "to_validate",
                "Which team is this for and what active AI workload should we focus on?",
                "Anchors product positioning to the confirmed team scope.",
                evidence,
            ),
            question_item(
                "AI Usage & Current Stack",
                "Current model/vendor stack?",
                "Not Found.",
                "not_found",
                "What model/vendor stack or internal platform is currently in use or being evaluated?",
                "Identifies replacement, augmentation, or integration opportunity.",
            ),
            question_item(
                "POC Qualification",
                "What success metric matters most?",
                "To Validate: success metric not confirmed.",
                "to_validate",
                "What metric would make the POC worthwhile: quality, latency, privacy/compliance, cost, developer productivity, or launch readiness?",
                "Converts discovery into a scoped next step.",
            ),
        ]
        omitted = ["Deep product-specific questions require confirmed team scope and active workload."]
    elif name == "enterprise_llm":
        vertical_items = [
            question_item("AI Usage & Current Stack", "What AI capabilities are already integrated today?", "To Validate: current AI capabilities and production scope are not confirmed.", "to_validate", "Which workflows are in production: chat, RAG, agents, routing/evaluation, or fine-tuning?", "Clarifies Ark platform fit."),
            question_item("LLM Usage", "Monthly token usage / average request length / peak concurrency?", "Not Found.", "not_found", "What are monthly tokens, peak concurrency, average prompt length, and traffic regions?", "Sizes inference cost and architecture."),
            question_item("Switching Mechanism", "What would make you switch providers?", "To Validate: switching trigger is not confirmed.", "to_validate", "Would you switch for quality, latency, cost, compliance, routing, or operational control?", "Turns discovery into competitive positioning."),
        ]
        omitted = ["Image/video questions collapsed unless multimodal evidence appears.", "Gaming/adtech questions omitted."]
    elif name == "ecommerce" and not active_workload:
        vertical_items = [
            question_item("Standard Discovery Questions", "Core ecommerce/product scope?", "To Validate: confirm the product line, region, user/customer segment, and active AI workload.", "to_validate", "Which team or product line is this discussion for, and what active AI or BytePlus-relevant workload should we focus on?", "Keeps ecommerce discovery broad until workload is confirmed."),
            question_item("AI Usage & Current Stack", "Current AI adoption?", "To Validate: no confirmed recommendation, chatbot, catalog automation, creative, or model/API workload found.", "to_validate", "Are you exploring AI for catalog/content automation, search/recommendation, support, creative production, model/API infrastructure, or another use case?", "Avoids assuming ecommerce-specific AI workloads from industry alone."),
        ]
        omitted = ["Recommendation/search/ranking, product image, chatbot, and livestream questions collapsed until workload evidence appears."]
    elif name == "ecommerce":
        vertical_items = [
            question_item("Standard Discovery Questions", "Catalog / SKU scale?", "Not Found.", "not_found", "How many SKUs/listings and regions/languages need AI support?", "Sizes catalog automation opportunity."),
            question_item("Business Scenarios & Use Cases", "Recommendation/search/ranking or product content?", "Likely: ecommerce teams often evaluate listing content, product images, recommendations/search, reviews, and support. (?)", "likely", "Which workflow has the clearest ROI: listings, product images, search/recommendation, reviews, or support?", "Maps workload to Ark/Seedream/LLM fit."),
        ]
        omitted = ["Long-form video questions collapsed unless livestream evidence appears.", "Private deployment omitted unless security evidence appears."]
    elif name == "gaming" and not active_workload:
        vertical_items = [
            question_item("Business Scenarios & Use Cases", "Game/company scope?", "To Validate: genre, product line, team scope, and active AI workload are not confirmed.", "to_validate", "Which team or product line is this discussion for, and are you exploring AI for assets, NPC/agents, localization, support, marketing, infrastructure, or another use case?", "Keeps gaming discovery broad until workload is confirmed."),
        ]
        omitted = ["NPC, level-design, asset-generation, and game-video questions collapsed until workload evidence appears."]
    elif name == "gaming":
        vertical_items = [
            question_item("Business Scenarios & Use Cases", "Game genre and production stage?", "To Validate: genre, stage, and active AI workflow are not confirmed.", "to_validate", "Is the priority assets, NPC/agent, localization, support, or marketing creative?", "Determines whether Seedream, Seedance, LLM/agents, or Ark should lead."),
            question_item("Image / Video Usage", "Asset generation / character consistency?", "Likely: asset generation or marketing creative may be relevant for gaming companies. (?)", "likely", "Do you need image assets, trailers/social video, character consistency, or localization support?", "Focuses creative model demo assets."),
        ]
        omitted = ["Adtech traffic questions omitted unless performance marketing evidence appears.", "Enterprise deployment omitted unless security evidence appears."]
    else:
        vertical_items = [
            question_item("Standard Discovery Questions", "Current AI adoption?", "To Validate: active AI workload is not confirmed.", "to_validate", "Where is AI used today, if anywhere?", "Keeps discovery broad when vertical evidence is weak."),
            question_item("Commercial & Procurement Signals", "Budget and procurement?", "To Validate: budget owner, current spend, vendor commitment, and procurement path are not confirmed.", "to_validate", "Who owns budget and procurement, and are there existing vendor commitments?", "Qualifies whether the opportunity can progress."),
        ]
        omitted = ["Vertical-specific deep dives collapsed until evidence appears."]
    readiness = meeting_readiness_assets(name)
    return common + vertical_items, omitted, readiness


def meeting_readiness_assets(vertical_name: str) -> list[str]:
    base = [
        "Lark Doc / PPT link: To Prepare if AE/SA needs customer-facing overview.",
        "Benchmark: To Prepare once current model/vendor stack and success metric are confirmed.",
        "Pricing Comparison: To Prepare if cost pressure or vendor replacement is confirmed.",
    ]
    if vertical_name == "marketing_adtech":
        return base + [
            "Demo / Case Study: Recommended for marketing/adtech conversion, content experimentation, and creative workflow.",
            "Architecture Diagram: Recommended if model routing, API integration, or GenAI optimization is discussed.",
            "Vertical-Specific Examples: Recommended - use marketing/adtech examples around conversion, acquisition, and creative generation.",
            "Latency / Quality Comparison: To Prepare if workload is high-volume or API-based.",
        ]
    if vertical_name == "ai_video_creative":
        return base + ["Seedance / Seedream Demo: Recommended.", "Benchmark Assets: Prepare reference prompts/images/videos.", "Latency / Quality Comparison: Recommended."]
    if vertical_name == "enterprise_llm":
        return base + ["Architecture Diagram: Recommended.", "Security / Compliance Notes: Recommended.", "Routing / Evaluation Demo: Recommended."]
    if vertical_name == "ecommerce":
        return base + ["Product Image Demo: Recommended.", "Catalog Automation Example: Recommended.", "Recommendation/search discussion notes: To Prepare if relevant."]
    if vertical_name == "gaming":
        return base + ["Game asset generation demo: Recommended.", "Localization/support workflow: To Prepare if relevant.", "Trailer/social video examples: To Prepare if marketing use case appears."]
    return base + ["Vertical-Specific Examples: To Prepare after vertical is confirmed."]


def require_lark_cli() -> str:
    path = shutil.which("lark-cli")
    if not path:
        raise PrepError(
            "lark-cli is not installed or is not on PATH. Install/configure Lark CLI, "
            "then run `lark-cli auth login` with the required scopes."
        )
    return path


def run_lark(args: list[str], *, debug: bool = False, check: bool = False) -> dict[str, Any]:
    require_lark_cli()
    cmd = ["lark-cli", *args]
    debug_log(debug, "running: " + " ".join(safe_arg(a) for a in cmd))
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    output = proc.stdout.strip() or proc.stderr.strip()
    try:
        data = json.loads(output) if output else {}
    except json.JSONDecodeError:
        data = {"ok": proc.returncode == 0, "raw": output}
    if check and proc.returncode != 0:
        raise PrepError(format_lark_error(data, proc.returncode))
    if proc.returncode != 0 and "ok" not in data:
        data["ok"] = False
    return data


def safe_arg(arg: str) -> str:
    if "TOKEN" in arg.upper() or "SECRET" in arg.upper():
        return "<redacted>"
    return arg


def format_lark_error(data: dict[str, Any], returncode: int) -> str:
    err = data.get("error") or {}
    msg = err.get("message") or data.get("message") or data.get("raw") or f"lark-cli failed with exit {returncode}"
    hint = err.get("hint")
    if hint:
        return f"{msg}\nNext: {hint}"
    return str(msg)


def infer_missing_scope(message: str) -> str | None:
    lowered = message.lower()
    scope_map = [
        ("calendar", "calendar:calendar.event:read"),
        ("docx", "docx:document:create or docx:document:write_only"),
        ("document", "docx:document:create or docx:document:write_only"),
        ("docs", "search:docs:read or docx document scopes"),
        ("search", "search:docs:read"),
        ("im", "im:message"),
        ("message", "im:message"),
        ("permission", "permission/scope not specific in Lark response"),
        ("scope", "scope not specific in Lark response"),
    ]
    for needle, scope in scope_map:
        if needle in lowered:
            return scope
    return None


def mask_token(token: str | None) -> str:
    if not token:
        return "none"
    if len(token) <= 8:
        return "<configured>"
    return f"{token[:4]}...{token[-4:]}"


def auth_status(debug: bool = False) -> dict[str, Any] | None:
    try:
        data = run_lark(["auth", "status"], debug=debug)
    except PrepError:
        return None
    if data.get("tokenStatus") == "valid":
        return data
    return None


def parse_email(value: str) -> tuple[str, str] | None:
    match = re.match(r"^[^@\s]+@([^@\s]+\.[^@\s]+)$", value.strip().lower())
    if not match:
        return None
    return value.strip().lower(), match.group(1)


def is_personal_domain(domain: str | None) -> bool:
    return bool(domain and domain.lower() in PERSONAL_EMAIL_DOMAINS)


def is_internal_domain(domain: str | None) -> bool:
    return bool(domain and domain.lower() in INTERNAL_DOMAINS)


def domain_to_name(domain: str | None) -> str | None:
    if not domain:
        return None
    aliases = {
        "naturalint.com": "Natural Intelligence",
        "naturalintelligence.com": "Natural Intelligence",
        "freepik.es": "Freepik",
        "freepik.com": "Freepik",
    }
    normalized = normalize_domain(domain)
    if normalized in aliases:
        return aliases[normalized]
    root = domain.split(".")[0].replace("-", " ").replace("_", " ").strip()
    return root.title() if root else None


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    cleaned = re.sub(r"^https?://", "", cleaned)
    cleaned = cleaned.split("/")[0]
    cleaned = cleaned[4:] if cleaned.startswith("www.") else cleaned
    return cleaned or None


def external_attendee_domains(event: dict[str, Any] | None) -> list[tuple[str, str]]:
    if not event:
        return []
    domains: list[tuple[str, str]] = []
    for attendee in event.get("attendees") or []:
        email = attendee.get("third_party_email") or attendee.get("email") or ""
        parsed = parse_email(email)
        if not parsed:
            continue
        _, domain = parsed
        if not is_internal_domain(domain) and not is_personal_domain(domain):
            domains.append((email, domain))
    return domains


def title_customer_candidate(title: str) -> str | None:
    cleaned = title.strip()
    patterns = [
        r"^(?:byteplus|bytedance|byte)\s*<>\s*(.+?)(?:\s+(?:sync|intro|discovery|call))?$",
        r"^(.+?)\s*<>\s*(?:byteplus|bytedance|byte)(?:\s+.*)?$",
        r"^customer call:\s*(.+?)\s*(?:x|&|and|<>|/)\s*(?:byteplus|bytedance|byte).*$",
        r"^(.+?)\s*(?:x|&|and|/)\s*(?:byteplus|bytedance|byte)(?:\s+.*)?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, cleaned, re.IGNORECASE)
        if match:
            return cleanup_customer_name(match.group(1))
    return None


def cleanup_customer_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\b(sync|intro|discovery|call|meeting)\b", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:|/")
    return cleaned or None


def resolve_customer(
    *,
    explicit_customer: str | None = None,
    explicit_domain: str | None = None,
    explicit_email: str | None = None,
    explicit_contact: str | None = None,
    explicit_company: str | None = None,
    event: dict[str, Any] | None = None,
) -> CustomerIdentity:
    evidence: list[str] = []
    email: str | None = None
    domain = normalize_domain(explicit_domain)
    contact_name = cleanup_customer_name(explicit_contact)
    company_name = cleanup_customer_name(explicit_company)
    name = cleanup_customer_name(company_name or explicit_customer)
    confidence = "unknown"

    if contact_name:
        evidence.append(f"explicit contact input: {contact_name}")
    if company_name:
        evidence.append(f"explicit company input: {company_name}")
        confidence = "confirmed"
    elif name:
        evidence.append(f"explicit customer input: {name}")
        confidence = "confirmed"
    if domain:
        evidence.append(f"explicit domain input: {domain}")
        confidence = "confirmed"
        name = name or domain_to_name(domain)

    if explicit_email:
        parsed = parse_email(explicit_email)
        if parsed:
            email, email_domain = parsed
            evidence.append(f"explicit email input: {email}")
            if is_personal_domain(email_domain):
                evidence.append(f"personal email domain ignored for company inference: {email_domain}")
            else:
                domain = domain or email_domain
                name = name or domain_to_name(email_domain)
                evidence.append(f"corporate email domain: {email_domain}")
                confidence = "confirmed"

    for attendee_email, attendee_domain in external_attendee_domains(event):
        domain = domain or attendee_domain
        name = name or domain_to_name(attendee_domain)
        evidence.append(f"attendee email domain: {attendee_domain} ({attendee_email})")
        confidence = "confirmed"
        break

    if event and not name:
        candidate = title_customer_candidate(event.get("summary") or event.get("title") or "")
        if candidate:
            name = candidate
            evidence.append(f"title customer candidate: {candidate}")
            confidence = "likely" if confidence == "unknown" else confidence

    if name and confidence == "unknown":
        confidence = "likely"
    return CustomerIdentity(name, domain, email, confidence, evidence, contact_name=contact_name, company_name=company_name or (name if domain else None))


def parse_window(value: str, tz_name: str = DEFAULT_TIMEZONE, now: datetime | None = None) -> tuple[datetime, datetime, str]:
    tz = ZoneInfo(tz_name)
    current = now.astimezone(tz) if now else datetime.now(tz)
    today = current.date()
    if value == "today":
        start_day = today
        end_day = today + timedelta(days=1)
    elif value == "tomorrow":
        start_day = today + timedelta(days=1)
        end_day = today + timedelta(days=2)
    elif value == "next-7-days":
        start = current
        end = current + timedelta(days=7)
        return start, end, tz_name
    elif re.match(r"^past-\d+-hours$", value):
        hours = int(value.removeprefix("past-").removesuffix("-hours"))
        if hours <= 0:
            raise PrepError("Past-hour windows must be greater than zero.")
        start = current - timedelta(hours=hours)
        return start, current, tz_name
    elif re.match(r"^\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$", value):
        raw_start, raw_end = value.split(":", 1)
        start_day = date.fromisoformat(raw_start)
        end_day = date.fromisoformat(raw_end)
    else:
        raise PrepError("Unsupported --window value. Use today, tomorrow, next-7-days, past-N-hours, or YYYY-MM-DD:YYYY-MM-DD.")
    return datetime.combine(start_day, time.min, tz), datetime.combine(end_day, time.min, tz), tz_name


def lark_time_to_iso(value: dict[str, Any] | None, fallback_tz: str = DEFAULT_TIMEZONE) -> str:
    if not value:
        return ""
    if value.get("timestamp"):
        tz = ZoneInfo(value.get("timezone") or fallback_tz)
        return datetime.fromtimestamp(int(value["timestamp"]), tz).isoformat()
    if value.get("date"):
        return value["date"]
    return ""


def fetch_event(event_id: str, debug: bool = False) -> dict[str, Any] | None:
    params = {
        "calendar_id": DEFAULT_CALENDAR_ID,
        "event_id": event_id,
        "need_attendee": True,
        "max_attendee_num": 50,
    }
    data = run_lark(
        ["calendar", "events", "get", "--params", json.dumps(params), "--as", "user", "--format", "json"],
        debug=debug,
    )
    if data.get("code") == 0:
        return data.get("data", {}).get("event")
    raise PrepError("Could not fetch Lark event. " + format_lark_error(data, 1))


def fetch_window_events(start: datetime, end: datetime, debug: bool = False) -> list[dict[str, Any]]:
    params = {
        "calendar_id": DEFAULT_CALENDAR_ID,
        "start_time": str(int(start.timestamp())),
        "end_time": str(int(end.timestamp())),
    }
    data = run_lark(
        ["calendar", "events", "instance_view", "--params", json.dumps(params), "--page-all", "--format", "json"],
        debug=debug,
    )
    if data.get("code") == 0:
        return data.get("data", {}).get("items") or []
    raise PrepError("Could not fetch Lark calendar window. " + format_lark_error(data, 1))


def search_docs(queries: list[str], debug: bool = False) -> tuple[list[dict[str, Any]], str | None]:
    docs: list[dict[str, Any]] = []
    seen: set[str] = set()
    attempted = 0
    failed = 0
    for query in [q for q in queries if q]:
        attempted += 1
        data = run_lark(["docs", "+search", "--query", query, "--format", "json"], debug=debug)
        if data.get("ok") is False and "too many request" in format_lark_error(data, 1).lower():
            debug_log(debug, f"docs search rate limited for {query!r}; retrying once")
            time_module.sleep(1.5)
            data = run_lark(["docs", "+search", "--query", query, "--format", "json"], debug=debug)
        if data.get("ok") is False or data.get("code") not in (0, None):
            failed += 1
            debug_log(debug, f"docs search failed for {query!r}: {format_lark_error(data, 1)}")
            continue
        items = data.get("data", {}).get("items") or data.get("data", {}).get("results") or data.get("items") or data.get("results") or []
        for item in items:
            normalized = normalize_doc_result(item)
            token = str(normalized.get("token") or normalized.get("url") or normalized.get("title"))
            if token and token not in seen:
                seen.add(token)
                docs.append(normalized)
    if failed and failed == attempted:
        return [], "Docs search unavailable due to permission or missing scope. Continuing without prior docs."
    if failed:
        return docs[:10], "Docs search partially unavailable; some queries failed, but usable prior docs were found."
    return docs[:10], None


def strip_markup(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", "", value)
    return html.unescape(text).strip()


def normalize_doc_result(item: dict[str, Any]) -> dict[str, Any]:
    meta = item.get("result_meta") or {}
    title = strip_markup(item.get("title_highlighted")) or item.get("title") or item.get("name") or item.get("docs_title") or "Untitled"
    summary = strip_markup(item.get("summary_highlighted") or item.get("summary"))
    url = meta.get("url") or item.get("url") or item.get("docs_url") or item.get("app_link") or ""
    date_value = meta.get("update_time_iso") or meta.get("create_time_iso") or item.get("create_time") or item.get("update_time") or ""
    return {
        "title": title,
        "url": url,
        "date": date_value,
        "summary": summary,
        "token": meta.get("token") or item.get("token") or item.get("doc_id") or url,
        "type": item.get("entity_type") or meta.get("doc_types") or item.get("type") or "",
    }


def relevance_score(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    score = 0
    for term in [t.lower() for t in terms if t]:
        if term in lowered:
            score += 8 if " " in term else 3
        for part in term.split():
            if len(part) >= 4 and part.lower() in lowered:
                score += 1
    high_signal = [
        "founder",
        "ceo",
        "cto",
        "customer profile",
        "meeting notes",
        "ai notes",
        "prep",
        "poc",
        "opportunity",
        "seedance",
        "seedream",
        "ark",
        "maas",
        "lead",
        "pipeline",
    ]
    score += sum(2 for item in high_signal if item in lowered)
    low_signal = ["paper", "论文", "keyword highlighter", "guestlist", "newsletter", "standup"]
    score -= sum(4 for item in low_signal if item in lowered)
    return score


def rank_docs(docs: list[dict[str, Any]], terms: list[str], *, keep_existing_prep: bool = True, min_score: int = 8) -> list[dict[str, Any]]:
    ranked = []
    for doc in docs:
        text = " ".join(str(doc.get(key, "")) for key in ("title", "summary", "url"))
        score = relevance_score(text, terms)
        title = (doc.get("title") or "").lower()
        if keep_existing_prep and ("pre-meeting prep" in title or "customer profile" in title):
            score += 8
        if score >= min_score:
            enriched = dict(doc)
            enriched["relevance_score"] = score
            ranked.append(enriched)
    return sorted(ranked, key=lambda d: (d.get("relevance_score", 0), d.get("date", "")), reverse=True)


def infer_company_from_docs(customer_name: str | None, docs: list[dict[str, Any]]) -> str | None:
    if not customer_name:
        return None
    escaped = re.escape(customer_name)
    patterns = [
        rf"{escaped}\s+(?:Founder\s*&\s*CEO|Founder and CEO|CEO|Founder),\s*([A-Z][A-Za-z0-9 .&-]{{1,60}})",
        rf"{escaped}.*?\b(?:at|@)\s+([A-Z][A-Za-z0-9 .&-]{{1,60}})",
        rf"{escaped}.*?\|\s*([A-Z][A-Za-z0-9 .&-]{{1,60}})",
        rf"{escaped}\s+(?:AI Creative Technologist|Creative Technologist|Founder|CEO|CTO|CMO|Product Manager|Head of [A-Za-z ]+)\s+([A-Z][A-Za-z0-9 .&-]{{2,60}}?)\s+(?:video production|creative agencies|agency|studio|company|Country\b|[0-9]{{2,}})",
        rf"{escaped}\s+(?:Product Manager|Data Product Manager|Head of [A-Za-z ]+|Director|VP [A-Za-z ]+)\s+([A-Z][A-Za-z0-9 .&-]{{2,60}}?)\s+(?:adtec|martech|fintech|gaming|ecommerce|creative|Country\b|[0-9]{{2,}})",
    ]
    for doc in docs:
        text = " ".join(str(doc.get(key, "")) for key in ("title", "summary"))
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1).strip(" .;,-")
                candidate = re.split(r"\s{2,}|\s+Company\b|\s+creative agencies\b|\s+not on\b", candidate)[0].strip(" .;,-")
                words = candidate.split()
                if len(words) % 2 == 0 and words[: len(words) // 2] == words[len(words) // 2 :]:
                    candidate = " ".join(words[: len(words) // 2])
                if candidate and candidate.lower() not in customer_name.lower():
                    return candidate
    return None


def expand_internal_queries(identity: CustomerIdentity, company_name: str | None = None) -> list[str]:
    anchor = company_name or identity.canonical_name
    queries = [
        identity.canonical_name,
        identity.contact_name,
        identity.domain,
        f"{identity.contact_name} {anchor}" if identity.contact_name and anchor else None,
        f"{identity.canonical_name} {company_name}" if identity.canonical_name and company_name and identity.canonical_name != company_name else None,
        f"{anchor} BytePlus" if anchor else None,
        f"{anchor} meeting notes" if anchor else None,
        f"{anchor} AI notes" if anchor else None,
        f"{anchor} customer profile" if anchor else None,
        f"{anchor} prep" if anchor else None,
        f"{anchor} Seedance" if anchor else None,
        f"{anchor} Seedream" if anchor else None,
        f"{anchor} Ark" if anchor else None,
        f"{anchor} MaaS" if anchor else None,
        f"{anchor} opportunity" if anchor else None,
        f"{anchor} POC" if anchor else None,
        f"{anchor} pricing" if anchor else None,
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for query in [q for q in queries if q]:
        normalized = query.lower()
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(query)
    return deduped


def merge_docs(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for doc in group:
            key = str(doc.get("token") or doc.get("url") or doc.get("title"))
            if key and key not in seen:
                seen.add(key)
                merged.append(doc)
    return merged


def is_web_search_disabled() -> bool:
    return os.getenv("PREP_WEB_SEARCH_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def clean_duckduckgo_url(url: str) -> str:
    parsed = urlparse(html.unescape(url))
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else url
    return html.unescape(url)


def web_search(query: str, *, max_results: int = 5, debug: bool = False) -> tuple[list[dict[str, str]], str | None]:
    if is_web_search_disabled():
        return [], "web_search: disabled_or_not_configured"
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        debug_log(debug, f"web search failed for {query!r}: {exc}")
        return [], "web_search: request_failed"

    results: list[dict[str, str]] = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?(?:<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>)',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(body):
        link, raw_title, snippet_a, snippet_div = match.groups()
        title = strip_markup(raw_title)
        snippet = strip_markup(snippet_a or snippet_div)
        cleaned_url = clean_duckduckgo_url(link)
        if title and cleaned_url:
            results.append({"title": title, "url": cleaned_url, "snippet": snippet, "source": "web"})
        if len(results) >= max_results:
            break
    if not results:
        return [], "web_search: ran_but_no_results"
    return results, None


def expand_web_queries(customer: CustomerIdentity, company_name: str | None) -> list[str]:
    anchor = company_name or customer.company_name or customer.domain or customer.canonical_name
    if not anchor:
        return []
    anchor_lower = anchor.lower()
    compact_anchor = re.sub(r"[^a-z0-9]+", "", anchor_lower)
    creative_context = any(signal in anchor_lower for signal in ("imagine", "goroka", "creative", "video", "image", "art"))
    queries = [
        f"{customer.contact_name} {anchor}" if customer.contact_name and anchor else None,
        f"{customer.canonical_name} {company_name}" if customer.canonical_name and company_name and customer.canonical_name != company_name else None,
        f"{customer.contact_name} {company_name} AI Video Lead" if customer.contact_name and company_name and creative_context else None,
        f"{anchor} intent marketing" if compact_anchor == "naturalintelligence" else None,
        f"{anchor} customer acquisition comparison platforms" if compact_anchor == "naturalintelligence" else None,
        f"naturalint.com {anchor}" if compact_anchor == "naturalintelligence" else None,
        f"{anchor} company product",
        f"{anchor} official website",
        f"{anchor} Lavinia AI" if "goroka" in anchor_lower or "lavinia" in anchor_lower else None,
        f"{anchor} AI creative suite product" if creative_context else None,
        f"{anchor} founder {customer.canonical_name}" if customer.canonical_name and company_name and customer.canonical_name != company_name else None,
        f"{anchor} about company",
        f"site:{customer.domain} {anchor} about" if customer.domain else None,
        f"{anchor} users downloads funding revenue",
        f"{anchor} AI image generator video generator" if creative_context else None,
        f"{anchor} alternatives competitors",
        f"{anchor} pricing API enterprise",
        f"site:{customer.domain} {anchor} API" if customer.domain else None,
        f"site:{customer.domain} {anchor} video" if customer.domain else None,
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for query in [q for q in queries if q]:
        normalized = query.lower()
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(query)
    return deduped


def collect_web_results(queries: list[str], debug: bool = False) -> tuple[list[dict[str, str]], str | None]:
    collected: list[dict[str, str]] = []
    seen: set[str] = set()
    warnings: list[str] = []
    for query in queries[:10]:
        results, warning = web_search(query, max_results=4, debug=debug)
        if warning:
            warnings.append(warning)
        for result in results:
            key = result.get("url") or result.get("title")
            if key and key not in seen:
                seen.add(key)
                enriched = dict(result)
                enriched["query"] = query
                collected.append(enriched)
    if collected:
        return sorted(collected, key=web_relevance_score, reverse=True)[:12], None
    if any("request_failed" in warning for warning in warnings):
        return [], "web_search: request_failed"
    if any("disabled_or_not_configured" in warning for warning in warnings):
        return [], "web_search: disabled_or_not_configured"
    return [], warnings[0] if warnings else "web_search: ran_but_no_results"


def web_status_from_warning(warning: str | None, has_results: bool) -> str:
    if has_results:
        return "usable_results_found"
    if warning and "web_search:" in warning:
        return warning.split("web_search:", 1)[1].strip()
    return "ran_but_no_results"


def contextual_web_score(result: dict[str, str], customer_name: str | None, company_name: str | None) -> int:
    text = " ".join(str(result.get(key, "")) for key in ("title", "snippet", "url")).lower()
    score = web_relevance_score(result)
    host = urlparse(result.get("url", "")).netloc.lower()
    compact_text = re.sub(r"[^a-z0-9]+", "", text)
    has_company_alias = bool(company_name and any(alias in compact_text for alias in company_domain_aliases(company_name)))
    if company_name and has_company_alias:
        score += 8
    elif company_name:
        score -= 30
    if customer_name and customer_name.lower() in text:
        score += 12
    if company_name and customer_name and has_company_alias and customer_name.lower() in text:
        score += 12
    misleading_hosts = ("imagine.art", "gorokacoffee.com", "unigoroka.ac.pg", "papuanewguinea.travel", "pngyp.com", "business-yellowpages.com")
    if any(item in host for item in misleading_hosts) and not (customer_name and customer_name.lower() in text):
        score -= 20
    if company_name and any(signal in text for signal in ("academic.oup.com", "sciencedirect.com", "cell.com", "researchgate.net", "tandfonline.com", "cognitive science", "neuroscience", "natural intelligence in terms of", "neural basis of natural intelligence", "evolutionary origins of natural intelligence")):
        score -= 90
    if company_name and re.sub(r"[^a-z0-9]+", "", company_name.lower()) == "naturalintelligence":
        if any(signal in text for signal in ("intent marketing", "customer acquisition", "comparison platforms", "top-tier brands")):
            score += 18
        if "naturalintelligence.info" in host or any(signal in text for signal in ("leen gorissen", "millions of years", "nature knows")):
            score -= 35
        if "lavinia" in text or "goroka" in text:
            score -= 20
    return score


def web_relevance_score(result: dict[str, str]) -> int:
    text = " ".join(str(result.get(key, "")) for key in ("title", "snippet", "url")).lower()
    score = 0
    for signal in ["official", "company product", "founder", "ceo", "users", "downloads", "funding", "revenue", "api", "pricing", "enterprise", "competitors"]:
        if signal in text:
            score += 3
    for signal in ["active users", "downloads", "bootstrapped", "api", "enterprise", "competitors", "openai", "runway", "luma"]:
        if signal in text:
            score += 4
    host = urlparse(result.get("url", "")).netloc.lower()
    if host.endswith("imagine.art") or host.endswith("imagineart.ai"):
        score += 8
    if any(blocked in host for blocked in ("bestreview", "greenrecord", "trustpilot")):
        score -= 3
    return score


def company_domain_aliases(company_name: str | None) -> list[str]:
    if not company_name:
        return []
    compact_company = re.sub(r"[^a-z0-9]+", "", company_name.lower())
    parts = [part for part in re.split(r"[^a-z0-9]+", company_name.lower()) if part]
    aliases = [compact_company]
    if len(parts) >= 2 and len(parts[1]) >= 3:
        aliases.append(parts[0] + parts[1][:3])
    return list(dict.fromkeys(aliases))


def likely_official_web_result(result: dict[str, str], company_name: str | None) -> bool:
    if not company_name:
        return False
    host = urlparse(result.get("url", "")).netloc.lower().removeprefix("www.")
    compact_host = re.sub(r"[^a-z0-9]+", "", host.split(":")[0])
    blocked = ("linkedin.com", "crunchbase.com", "producthunt.com", "trustpilot.com", "youtube.com", "gadinsider.com", "usatoday.com", "compworth.com", "growjo.com", "pitchbook.com", "gorokacoffee.com", "naturalintelligence.info")
    return any(alias in compact_host for alias in company_domain_aliases(company_name)) and not any(item in host for item in blocked)


def verified_related_domain(host: str, company_name: str | None) -> bool:
    normalized = host.lower().removeprefix("www.")
    configured = [item.strip().lower().removeprefix("www.") for item in os.getenv("PREP_OFFICIAL_RELATED_DOMAINS", "").split(",") if item.strip()]
    return any(normalized == domain or normalized.endswith("." + domain) for domain in configured)


def confirmed_domain_match(url_or_host: str, confirmed_domain: str | None = None) -> bool:
    if not confirmed_domain:
        return False
    host = urlparse(url_or_host).netloc.lower() if "://" in url_or_host else url_or_host.lower()
    host = host.split(":")[0].removeprefix("www.")
    domain = confirmed_domain.lower().split(":")[0].removeprefix("www.")
    return bool(host and domain and (host == domain or host.endswith("." + domain)))


def official_source(url: str, company_name: str | None = None, confirmed_domain: str | None = None) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    matched = bool(
        likely_official_web_result({"url": url}, company_name)
        or verified_related_domain(host, company_name)
        or confirmed_domain_match(url, confirmed_domain)
    )
    if not matched:
        return False
    # When a confirmed domain is set and the URL does not match it, a "likely official"
    # hit based purely on the company name appearing as a substring in the host
    # (e.g. "monks" inside "sportmonks.com") is a false positive — reject it.
    if confirmed_domain and not confirmed_domain_match(url, confirmed_domain):
        compact_name = re.sub(r"[^a-z0-9]", "", (company_name or "").lower())
        compact_host = re.sub(r"[^a-z0-9]", "", host)
        if compact_name and len(compact_name) >= 3 and compact_name in compact_host:
            return False
    return True


def blocked_as_company_website(host: str) -> bool:
    blocked = (
        "linkedin.com",
        "google.com",
        "facebook.com",
        "x.com",
        "twitter.com",
        "rocketreach.co",
        "checkcompany.co.uk",
        "company-information.service.gov.uk",
        "crunchbase.com",
        "producthunt.com",
        "trustpilot.com",
        "youtube.com",
        "gadinsider.com",
        "usatoday.com",
        "everybodywiki.com",
        "greenrecord.co.uk",
        "bestreviewinsight.com",
        "purpleaitools.com",
        "compworth.com",
        "growjo.com",
        "pitchbook.com",
        "gorokacoffee.com",
        "naturalintelligence.info",
        "academic.oup.com",
        "sciencedirect.com",
        "cell.com",
        "researchgate.net",
        "tandfonline.com",
        "unigoroka.ac.pg",
        "papuanewguinea.travel",
        "pngyp.com",
        "business-yellowpages.com",
    )
    return any(item in host for item in blocked)


def product_description_score(result: dict[str, str]) -> int:
    text = " ".join(str(result.get(key, "")) for key in ("title", "snippet", "url")).lower()
    score = 0
    for signal in ["ai creative suite", "generates images", "videos", "voice", "prompt", "editing tools", "custom models"]:
        if signal in text:
            score += 3
    for low_signal in ["pricing", "faq", "frequently asked", "review", "trustpilot", "crunchbase", "competitors", "monetization", "help center", "community", "compworth", "growjo", "pitchbook", "leen gorissen", "millions of years", "nature knows", "book"]:
        if low_signal in text:
            score -= 4
    if likely_official_web_result(result, None):
        score += 2
    return score


def stable_company_website(host: str) -> str:
    normalized = host.lower().removeprefix("www.")
    for prefix in ("docs.", "help.", "support.", "community."):
        if normalized.startswith(prefix):
            return normalized.removeprefix(prefix)
    return normalized


def stable_company_description(company_name: str | None, description: str, use_cases: list[str]) -> str:
    normalized = normalize_company_overview(description, company_name)
    if normalized:
        return normalized
    lowered = description.lower()
    weak_page = any(item in lowered for item in ("monetization", "help center", "community", "pricing", "frequently asked"))
    if company_name and (weak_page or not description):
        if use_cases and any("creative" in item or "image" in item or "video" in item for item in use_cases):
            return f"{company_name} appears to be a generative AI creative platform focused on " + ", ".join(use_cases[:3]) + "."
        return ""
    if overview_quality_issue(description, company_name):
        return ""
    return description


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


def clean_source_label(label: str, url: str = "") -> str:
    if contains_placeholder(label):
        return url
    return label


def source_purpose(url: str, title: str = "", snippet: str = "") -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    text = f"{title} {snippet} {path}".lower()
    if host.startswith("developer.") or "developer" in host:
        return "developer_docs"
    if host.startswith(("support.", "help.")):
        return "support"
    if any(term in text for term in ("pricing", "billing", "plans", "subscription")):
        return "pricing"
    if any(term in text for term in ("api", "developer", "sdk", "docs", "documentation", "openapi")):
        return "developer_docs"
    if any(term in text for term in ("support", "help", "faq", "article")):
        return "support"
    if any(term in text for term in ("about", "company", "newsroom", "press", "investor", "careers")) or path in {"", "/"}:
        return "company_overview"
    if any(term in text for term in ("comparison", "alternative", "competitor", "vs ")):
        return "reference"
    return "product_or_reference"


def broad_company_overview_allowed(url: str, title: str = "", snippet: str = "", company_name: str | None = None) -> bool:
    path = urlparse(url).path.lower().strip("/")
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if host.startswith(("developer.", "support.", "help.", "docs.")):
        return False
    broad_paths = {"", "about", "company", "about-us", "newsroom"}
    if path in broad_paths or path.startswith("about-") or path.startswith("company/"):
        return True
    if "newsroom/" in path:
        return False
    purpose = source_purpose(url, title, snippet)
    if purpose in {"pricing", "developer_docs", "support", "reference"}:
        return False
    if purpose == "company_overview":
        return True
    if company_name and likely_official_web_result({"url": url}, company_name) and urlparse(url).path.strip("/") in {"", "about", "company"}:
        return True
    return False


def select_company_overview_result(results: list[dict[str, str]], company_name: str | None, domain: str | None = None) -> dict[str, str] | None:
    if not company_name:
        return None
    official_broad = [
        item for item in results
        if official_source(item.get("url", ""), company_name, domain)
        and broad_company_overview_allowed(item.get("url", ""), item.get("title", ""), item.get("snippet", ""), company_name)
    ]
    if official_broad:
        return sorted(official_broad, key=lambda item: source_tier(item.get("url", ""), company_name)[0])[0]
    trusted_business = []
    for item in results:
        url = item.get("url", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        host = urlparse(url).netloc.lower()
        text = f"{title} {snippet} {url}".lower()
        if any(blocked in host for blocked in ("linkedin.com", "pulse", "medium.com", "substack.com", "openai.com", "claude.com", "anthropic.com")):
            continue
        if any(noisy in text for noisy in ("everything you need to know", "total users", "growth rate", "statistics", "competitors and alternatives")):
            continue
        if source_purpose(url, title, snippet) in {"pricing", "developer_docs", "support", "reference"}:
            continue
        if source_tier(url, company_name, domain)[0] <= 3 and company_name.lower() in text:
            trusted_business.append(item)
    return trusted_business[0] if trusted_business else None


def source_tier(url: str, company_name: str | None = None, confirmed_domain: str | None = None) -> tuple[int, str]:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    official = official_source(url, company_name, confirmed_domain)
    verified = verified_related_domain(host, company_name)
    if host.startswith(("docs.", "help.", "support.")) and (official or verified):
        return 1, "Tier 1 - official docs/help"
    if official or verified:
        return 1, "Tier 1 - official company site"
    if any(item in host for item in ("larkoffice.com", "feishu.cn")):
        return 2, "Tier 2 - internal Lark source"
    if any(item in host for item in ("crunchbase.com", "producthunt.com", "linkedin.com",
                                     "thehub.io", "wellfound.com", "angel.co", "tracxn.com",
                                     "pitchbook.com", "f6s.com")):
        return 3, "Tier 3 - public startup/company profile"
    return 4, "Tier 4 - public web/news/review"


def fetch_page_text(url: str, debug: bool = False) -> tuple[str, str | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                return "", f"unsupported content type: {content_type}"
            html_body = response.read(400_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        debug_log(debug, f"page fetch failed for {url}: {exc}")
        return "", "page fetch failed"
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html_body)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:20000], None


def fetch_explicit_user_urls(
    urls: list[str],
    company_name: str | None,
    confirmed_domain: str | None = None,
    debug: bool = False,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Fetch user-provided URLs directly as enrichment evidence.

    Returns (results, pages) in the same shape as collect_official_domain_overview so the
    caller can use them interchangeably with the standard domain-overview path.
    """
    results: list[dict[str, str]] = []
    pages: list[dict[str, Any]] = []
    for raw_url in urls[:6]:
        url = raw_url.strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        text, warning = fetch_page_text(url, debug=debug)
        snippet = clean_overview_snippet(text, company_name) if text else ""
        tier, tier_label = source_tier(url, company_name, confirmed_domain)
        page: dict[str, Any] = {
            "title": clean_source_label(url, url),
            "url": url,
            "snippet": snippet or (text[:500] if text else ""),
            "text": text or "",
            "fetch_warning": warning or "",
            "tier": tier,
            "tier_label": tier_label,
            "source": "explicit_user_url",
        }
        pages.append(page)
        if snippet or text:
            results.append({
                "title": clean_source_label(url, url),
                "url": url,
                "snippet": snippet or text[:300],
                "source": "explicit_user_url",
            })
            debug_log(debug, f"explicit URL enrichment: fetched {url} (tier={tier_label}, snippet={bool(snippet)})")
        else:
            debug_log(debug, f"explicit URL enrichment: no content from {url} (warning={warning})")
    return results, pages


def collect_page_evidence(results: list[dict[str, str]], company_name: str | None, confirmed_domain: str | None = None, debug: bool = False) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    selected: list[dict[str, str]] = []
    official = [item for item in results if official_source(item.get("url", ""), company_name, confirmed_domain)]
    selected.extend(official[:2])
    for item in results:
        url = item.get("url", "")
        if any(signal in url.lower() for signal in ("pricing", "docs.", "help.", "producthunt", "crunchbase")):
            selected.append(item)
        if len(selected) >= 6:
            break
    seen: set[str] = set()
    for item in selected[:6]:
        url = item.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        text, warning = fetch_page_text(url, debug=debug)
        tier, tier_label = source_tier(url, company_name)
        pages.append(
            {
                "title": item.get("title", ""),
                "url": url,
                "snippet": item.get("snippet", ""),
                "text": text,
                "fetch_warning": warning or "",
                "tier": tier,
                "tier_label": tier_label,
                "source": "web_page",
            }
        )
    return pages


def official_domain_overview_candidates(domain: str) -> list[dict[str, str]]:
    normalized = domain.lower().removeprefix("www.").strip("/")
    if not normalized:
        return []
    urls: list[str] = []
    for host in (normalized, f"www.{normalized}"):
        for path in ("", "/about", "/company", "/about-us", "/newsroom"):
            urls.append(f"https://{host}{path}")
    candidates = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        candidates.append({"title": "Company homepage/about page", "url": url, "snippet": "", "source": "web"})
    return candidates


def clean_overview_snippet(text: str, company_name: str | None) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return ""
    normalized = normalize_company_overview(clean, company_name)
    if normalized:
        return normalized
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    selected: list[str] = []
    company_lower = (company_name or "").lower()
    for sentence in sentences:
        lowered = sentence.lower()
        if len(sentence) < 40:
            continue
        if company_lower and company_lower.split()[0] not in lowered and not any(term in lowered for term in ("company", "platform", "studio", "media", "creates", "designs", "operates", "provides")):
            continue
        selected.append(sentence.strip())
        if len(" ".join(selected)) > 260:
            break
    return " ".join(selected)[:500].strip(" -")


def overview_quality_issue(text: str, company_name: str | None = None) -> bool:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return True
    lowered = clean.lower()
    company = (company_name or "").lower()
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+.-]*", lowered)
    if len(tokens) < 8:
        return True
    if company:
        company_count = sum(1 for token in tokens if token == company)
        if company_count >= 3:
            return True
    nav_terms = ["learn more", "buy", "support", "accessories", "store", "entertainment", "tv & home"]
    if sum(1 for term in nav_terms if term in lowered) >= 3:
        return True
    if len(set(tokens)) / max(len(tokens), 1) < 0.55:
        return True
    return False


def normalize_company_overview(text: str, company_name: str | None = None) -> str:
    lowered = (text or "").lower()
    compact = re.sub(r"\s+", " ", text or "").strip()
    company = company_name or "The company"
    if contains_placeholder(compact):
        return ""
    if any(term in lowered for term in ("iphone", "mac", "ipad", "apple watch", "airpods", "apple tv")):
        if overview_quality_issue(compact, company_name):
            return f"{company} is a global technology company offering consumer devices, software, services, entertainment, accessories, and support across major product and ecosystem categories."
        return compact
    compact_company = re.sub(r"[^a-z0-9]+", "", company.lower())
    if any(term in lowered for term in ("global advertising", "marketing services", "agency networks", "agency network", "media buying", "brand marketing")):
        return f"{company} is an advertising and marketing services company with capabilities across creative, media, data, technology, communications, and brand marketing services."
    if any(term in lowered for term in ("media and entertainment", "broadcasting", "streaming service", "content distribution", "international content", "media company", "format licensing", "global distribution and production")):
        return f"{company} is a media and entertainment company with broadcasting, streaming, production, news, and international content distribution businesses."
    if any(term in lowered for term in ("intent marketing", "comparison platform", "customer acquisition")):
        return f"{company} is an intent-marketing and customer-acquisition company focused on connecting consumers with brands through comparison and performance marketing platforms."
    if any(term in lowered for term in ("creative platform", "stock assets", "templates", "image generation", "video generation", "design platform")):
        return f"{company} is a creative platform offering design assets, templates, and AI-enabled image/video tools for creators, marketers, agencies, and enterprise creative teams."
    if overview_quality_issue(compact, company_name):
        return ""
    return ""


def collect_official_domain_overview(domain: str | None, company_name: str | None, debug: bool = False) -> tuple[list[dict[str, str]], list[dict[str, Any]], str | None]:
    if not domain:
        return [], [], "web_search: disabled_or_not_configured"
    results: list[dict[str, str]] = []
    pages: list[dict[str, Any]] = []
    failures = 0
    for candidate in official_domain_overview_candidates(domain):
        text, warning = fetch_page_text(candidate["url"], debug=debug)
        snippet = clean_overview_snippet(text, company_name)
        page = {
            "title": clean_source_label(candidate["title"], candidate["url"]),
            "url": candidate["url"],
            "snippet": snippet,
            "text": text,
            "fetch_warning": warning or "",
            "tier": source_tier(candidate["url"], company_name, domain)[0],
            "tier_label": source_tier(candidate["url"], company_name, domain)[1],
            "source": "web_page",
        }
        if snippet:
            result = dict(candidate)
            result["snippet"] = snippet
            results.append(result)
            pages.append(page)
            break
        failures += 1
        if len(pages) < 2:
            pages.append(page)
    if results:
        return results, pages, None
    return [], pages, "web_search: request_failed" if failures else "web_search: ran_but_no_results"


def official_company_overview_evidence(dossier: dict[str, Any], company_name: str | None = None) -> dict[str, Any] | None:
    for item in dossier.get("source_evidence") or []:
        if item.get("source_classification") != "customer_evidence":
            continue
        if "Tier 1 - official company site" not in str(item.get("tier_label", "")):
            continue
        claim = str(item.get("claim") or "").strip()
        if contains_placeholder(claim) or overview_quality_issue(claim, company_name):
            continue
        if broad_company_overview_allowed(item.get("url", ""), "", claim, company_name):
            return item
    return None


def extract_pricing_tiers(text: str) -> list[str]:
    tiers = []
    for tier in ["Free", "Basic", "Standard", "Ultimate", "Creator", "Enterprise", "Pro", "Team", "Business"]:
        if re.search(rf"\b{re.escape(tier)}\b", text, re.IGNORECASE):
            tiers.append(tier)
    return tiers[:8]


def customer_related_pricing_text(company_name: str | None, enrichment_description: str, web_results: list[dict[str, str]], pages: list[dict[str, Any]], confirmed_domain: str | None = None) -> str:
    if not company_name:
        return ""
    blocked_hosts = ("openai.com", "claude.com", "anthropic.com")
    parts: list[str] = []
    for item in web_results:
        url = item.get("url", "")
        host = urlparse(url).netloc.lower()
        if any(blocked in host for blocked in blocked_hosts):
            continue
        if source_purpose(url, item.get("title", ""), item.get("snippet", "")) != "pricing":
            continue
        haystack = f"{item.get('title', '')} {item.get('snippet', '')} {url}".lower()
        if company_name and not official_source(url, company_name, confirmed_domain) and company_name.lower() not in haystack:
            continue
        if company_name and not is_canonical_entity_compatible(url, item.get("title", ""), item.get("snippet", ""), company_name, confirmed_domain):
            continue
        parts.append(f"{item.get('title', '')} {item.get('snippet', '')}")
    for page in pages:
        url = page.get("url", "")
        host = urlparse(url).netloc.lower()
        if any(blocked in host for blocked in blocked_hosts):
            continue
        if source_purpose(url, page.get("title", ""), page.get("snippet", "")) != "pricing":
            continue
        haystack = f"{page.get('title', '')} {page.get('snippet', '')} {url}".lower()
        if company_name and not official_source(url, company_name, confirmed_domain) and company_name.lower() not in haystack:
            continue
        if company_name and not is_canonical_entity_compatible(url, page.get("title", ""), page.get("snippet", ""), company_name, confirmed_domain):
            continue
        parts.append(page.get("text", ""))
    return " ".join(parts)


def contact_company_noise(url: str, title: str, snippet: str, company_name: str | None, contact_name: str | None) -> bool:
    if not company_name or not contact_name:
        return False
    text = f"{title} {snippet} {url}".lower()
    host = urlparse(url).netloc.lower()
    contact_parts = [part for part in re.split(r"\s+", contact_name.lower()) if len(part) > 2]
    if not contact_parts or company_name.lower() not in text:
        return False
    if any(part in text for part in contact_parts) and any(noisy in host for noisy in ("link.me", "linkedin.com")):
        return True
    if len(contact_parts) >= 2 and contact_parts[-1] in text and company_name.lower() in text and not official_source(url, company_name):
        return True
    return False


def is_canonical_entity_compatible(url: str, title: str, snippet: str, company_name: str | None, confirmed_domain: str | None) -> bool:
    """Return False when a result references a same-name-but-different-entity source.

    When confirmed_domain is set, a URL host that *contains* the compact company
    name as a substring (e.g. sportmonks.com ⊃ "monks") but does NOT match the
    confirmed domain is a different entity and should be rejected.

    Financial instrument contamination (investment trust, stock ticker) is rejected
    even on neutral news domains, because "Monks Investment Trust (MNKS:LSE)" is a
    legally distinct entity from Monks / monks.com.
    """
    if not company_name:
        return True
    if confirmed_domain_match(url, confirmed_domain):
        return True

    combined_text = f"{title} {snippet}".lower()

    # Reject financial-instrument contamination: investment trust, ticker symbols, NAV/fund pages.
    # These are legally distinct entities that share a similar name with the operating company.
    _FINANCIAL_ENTITY_MARKERS = (
        "investment trust", "investment fund", "net asset value", " nav ",
        "fund manager", " aum ", "portfolio companies", "listed investment",
    )
    _TICKER_EXCHANGE_RE = re.compile(r'\b[A-Z]{2,6}:(LSE|NYSE|NASDAQ|HKEX|SGX|TSX|ASX)\b')
    if confirmed_domain:
        compact_name_fin = re.sub(r"[^a-z0-9]", "", company_name.lower())
        if compact_name_fin and len(compact_name_fin) >= 3 and compact_name_fin in combined_text:
            if any(marker in combined_text for marker in _FINANCIAL_ENTITY_MARKERS):
                return False
            if _TICKER_EXCHANGE_RE.search(f"{title} {snippet}"):
                return False

    neutral_hosts = (
        "wikipedia.org", "linkedin.com", "crunchbase.com", "bloomberg.com",
        "reuters.com", "techcrunch.com", "forbes.com", "ft.com", "wsj.com",
        "businessinsider.com", "wired.com", "theregister.com", "venturebeat.com",
        "nytimes.com", "bbc.com", "theguardian.com", "apnews.com",
        "pitchbook.com", "cbinsights.com", "glassdoor.com", "g2.com",
    )
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if any(nh in host for nh in neutral_hosts):
        return True
    compact_name = re.sub(r"[^a-z0-9]", "", company_name.lower())
    compact_host = re.sub(r"[^a-z0-9]", "", host)
    if not compact_name or len(compact_name) < 3:
        return True
    # Common rejection helper — used for both host and path matches
    def _reject_unless_canonical_cited() -> bool:
        canonical_bare = (confirmed_domain or "").lower().split(":")[0].removeprefix("www.").split("/")[0]
        if canonical_bare and canonical_bare in combined_text:
            return False  # allow: snippet cites the canonical domain
        return True  # reject

    # Reject if the company name appears embedded in a different host name
    # but that host does not match the confirmed domain.  For example:
    #   company="Monks", confirmed_domain="monks.com", url host="sportmonks.com"
    #   → compact_name="monks" in compact_host="sportmonks" → reject
    if compact_name in compact_host and confirmed_domain and not confirmed_domain_match(url, confirmed_domain):
        if _reject_unless_canonical_cited():
            return False

    # Also reject if the company name appears as a path segment on a different host.
    # For example: https://sportsapi.com/monks — "monks" is a path segment on sportsapi.com.
    if confirmed_domain and not confirmed_domain_match(url, confirmed_domain):
        compact_path = re.sub(r"[^a-z0-9/]", "", (parsed.path or "").lower())
        path_segments = [seg for seg in compact_path.split("/") if seg]
        if compact_name in path_segments:
            if _reject_unless_canonical_cited():
                return False

    return True


def classify_source(url: str, title: str = "", snippet: str = "", company_name: str | None = None, customer_name: str | None = None, candidate_company: str | None = None, confirmed_domain: str | None = None, contact_name: str | None = None) -> str:
    text = f"{title} {snippet} {url}".lower()
    host = urlparse(url).netloc.lower()
    if contains_placeholder(text):
        return "generic_market_reference"
    if any(item in host for item in ("openai.com", "claude.com", "anthropic.com")):
        return "competitor_reference"
    if company_name and official_source(url, company_name, confirmed_domain):
        return "customer_evidence"
    if contact_company_noise(url, title, snippet, company_name, contact_name):
        return "generic_market_reference"
    if not official_source(url, company_name, confirmed_domain) and any(item in text for item in ("statistics", "stats", "projected", "market share", "downloads are expected", "total users")):
        return "generic_market_reference"
    if host.removeprefix("www.").startswith(("docs.", "help.", "support.")) and not official_source(url, company_name, confirmed_domain):
        return "generic_market_reference"
    if any(item in text for item in ("competitor", "alternative", "alternatives")):
        return "generic_market_reference"
    if "pricing" in text and not official_source(url, company_name, confirmed_domain):
        return "generic_market_reference"
    if company_name and company_name.lower() in text:
        # Guard: reject same-name-different-entity sources when a confirmed domain is set
        if confirmed_domain and not is_canonical_entity_compatible(url, title, snippet, company_name, confirmed_domain):
            return "generic_market_reference"
        return "customer_evidence"
    candidate_terms = [term.lower() for term in [candidate_company or "", customer_name or ""] if term]
    if any(term and term in text for term in candidate_terms):
        return "candidate_entity_evidence"
    if any(item in host for item in ("linkedin.com", "pappers.fr", "societe.com")) and customer_name and customer_name.lower() in text:
        return "candidate_entity_evidence"
    return "generic_market_reference"


def evidence_claim(title: str, snippet: str, url: str, company_name: str | None = None) -> str:
    normalized = normalize_company_overview(snippet or title or "", company_name)
    if normalized:
        return normalized
    for value in (snippet, title, url):
        clean = re.sub(r"\s+", " ", value or "").strip()
        if clean and not contains_placeholder(clean):
            return clean
    return ""


def usable_evidence_row(item: dict[str, Any], company_name: str | None = None) -> bool:
    claim = str(item.get("claim") or "").strip()
    url = str(item.get("url") or "").lower()
    if not claim or contains_placeholder(claim):
        return False
    if "link.me/" in url:
        return False
    if item.get("source_classification") not in {"customer_evidence", "candidate_entity_evidence"}:
        return False
    if broad_company_overview_allowed(url, "", claim, company_name) and overview_quality_issue(claim, company_name):
        return False
    return True


def extract_company_dossier(
    company_name: str | None,
    enrichment_description: str,
    use_cases: list[str],
    web_results: list[dict[str, str]],
    pages: list[dict[str, Any]],
    customer_name: str | None = None,
    confirmed_domain: str | None = None,
    contact_name: str | None = None,
) -> dict[str, Any]:
    compatible_web_results = [
        item for item in web_results
        if is_canonical_entity_compatible(item.get("url", ""), item.get("title", ""), item.get("snippet", ""), company_name, confirmed_domain)
    ]
    compatible_pages = [
        page for page in pages
        if is_canonical_entity_compatible(
            page.get("url", ""), page.get("title", ""), page.get("snippet", ""),
            company_name, confirmed_domain
        )
    ]
    combined = " ".join(
        [enrichment_description]
        + [f"{item.get('title', '')} {item.get('snippet', '')}" for item in compatible_web_results]
        + [page.get("text", "") for page in compatible_pages]
    )
    rejected_web_count = (len(web_results) - len(compatible_web_results)) + (len(pages) - len(compatible_pages))
    modules = []
    module_signals = [
        ("Intent marketing platform", ("intent marketing", "customer acquisition")),
        ("Comparison platforms", ("comparison platform", "comparison platforms")),
        ("xMatch / GenAI optimization", ("xmatch", "genai")),
        ("AI image generation", ("image", "text-to-image", "ai art")),
        ("AI video generation", ("text-to-video", "ai video", "video generation")),
        ("Voice/audio generation", ("voice", "audio", "music")),
        ("Background remover", ("background remover", "bg remover")),
        ("Upscaler", ("upscaler", "upscale")),
        ("Custom models", ("custom model", "custom models")),
        ("API / enterprise plans", ("model api", "inference api", "creative api", "api deployment", "api integration", "enterprise plan", "enterprise plans")),
    ]
    lowered = combined.lower()
    for label, needles in module_signals:
        if any(needle in lowered for needle in needles):
            modules.append(label)

    pricing_tiers = extract_pricing_tiers(customer_related_pricing_text(company_name, enrichment_description, web_results, pages, confirmed_domain))
    candidate_company = ""
    if not company_name:
        if "la methode papier" in lowered or "la méthode papier" in lowered:
            candidate_company = "La Methode Papier"
        elif "siderakis fabien" in lowered:
            candidate_company = "Siderakis Fabien"

    trusted_scale_parts: list[str] = []
    if company_name:
        trusted_scale_parts.append(enrichment_description)
    for item in web_results:
        classification = classify_source(
            item.get("url", ""),
            item.get("title", ""),
            item.get("snippet", ""),
            company_name,
            customer_name,
            candidate_company,
            confirmed_domain,
            contact_name,
        )
        if classification in {"customer_evidence", "candidate_entity_evidence"}:
            trusted_scale_parts.append(f"{item.get('title', '')} {item.get('snippet', '')}")
    for page in compatible_pages:
        classification = classify_source(
            page.get("url", ""),
            page.get("title", ""),
            page.get("snippet", ""),
            company_name,
            customer_name,
            candidate_company,
            confirmed_domain,
            contact_name,
        )
        if classification in {"customer_evidence", "candidate_entity_evidence"}:
            trusted_scale_parts.append(page.get("text", "") or f"{page.get('title', '')} {page.get('snippet', '')}")
    trusted_scale_text = " ".join(trusted_scale_parts)
    scale_signals = []
    for pattern in [
        r"over\s+[\d.]+\s*(?:million|m|k)\s+active users",
        r"over\s+[\d.]+\s*(?:million|m|k)\s+purchase decisions",
        r"[\d.]+\s*(?:million|m|k)\s+downloads",
        r"\$[\d.]+\s*(?:m|million|b|billion)\s+(?:arr|annual recurring revenue|revenue)",
        r"[\d.]+\s*(?:b|billion|m|million)\s+(?:in\s+)?(?:annual\s+)?revenue",
        r"over\s+[\d,]+\s+employees",
        r"[\d,]+\s+employees",
        r"[\d.]+\s*(?:million|m|k)\s+paid subscribers",
        r"(?:one|two|three|four|five|six|seven|eight|nine|ten)\s+million\s+paid subscribers",
        r"[\d,]+\s+enterprise (?:clients|customers)",
        r"[\d.]+\s*(?:million|m|k)\s+(?:monthly users|monthly active users|users)",
        r"[\d.]+\s*(?:million|m|k)\s+(?:api calls|generations)",
        r"[\d,]+\s+(?:api calls|generations)",
        r"used by millions",
        r"millions worldwide",
    ]:
        for match in re.finditer(pattern, trusted_scale_text, re.IGNORECASE):
            signal = match.group(0)
            if signal not in scale_signals:
                scale_signals.append(signal)

    _FOUNDER_FRAGMENT_WORDS = {"the", "an", "a", "its", "our", "their", "all", "this", "that", "with", "for", "by", "at", "of", "global", "sport", "api", "data"}

    founders = []
    for pattern in [r"founder(?: and CEO)?\s+([A-Z][A-Za-z .'-]{2,60})", r"led by\s+([A-Z][A-Za-z .'-]{2,60})"]:
        for match in re.finditer(pattern, combined):
            value = match.group(1).strip(" .")
            # Require at least two words (first + last name) and no fragment word
            words = value.split()
            if (
                value
                and value not in founders
                and len(words) >= 2
                and not any(w.lower() in _FOUNDER_FRAGMENT_WORDS for w in words)
                and all(len(w) >= 2 for w in words)
            ):
                founders.append(value)

    hq = ""
    hq_match = re.search(r"(?:located in|based in|location in)\s+([A-Z][A-Za-z ,.-]{2,80})", combined)
    if hq_match:
        hq = re.split(
            r"\bwith\b|\band\b|\bestimated\b|\brevenue\b|\bWho\b|\bWhat\b|\bWhen\b|\bFrequently\b|[.;]",
            hq_match.group(1),
        )[0].strip(" .,-")
        hq = re.sub(r"\s*-\s*", " ", hq).strip()
    founded_year = ""
    founded_match = re.search(r"(?:est\.?|founded|operating since)\s*(?:in)?\s*(20\d{2}|19\d{2})", combined, re.IGNORECASE)
    if founded_match:
        founded_year = founded_match.group(1)
    vertical_subtype = infer_vertical_subtype(combined, None, None)
    subtype_name = vertical_subtype.get("name", "unknown")
    creative_signal = subtype_name == "creative_platform" or any(term in lowered for term in ("image generation", "video generation", "generative ai", "creative platform", "creator", "designers", "ai image", "ai video"))
    intent_marketing_signal = subtype_name == "intent_marketing_comparison"
    agency_signal = subtype_name == "agency_marketing_services"
    media_signal = subtype_name == "media_entertainment_content"
    consumer_tech_signal = subtype_name == "consumer_technology"
    target_users = ""
    if subtype_name in VERTICAL_SUBTYPE_TEMPLATES:
        target_users = VERTICAL_SUBTYPE_TEMPLATES[subtype_name]["target_users"]
    traffic_source_scale = ""
    traffic_terms = []
    for term in ("seo", "sem", "affiliate", "paid social", "partner traffic", "high-intent audiences", "purchase decisions"):
        if len(term) <= 3:
            if re.search(r'\b' + re.escape(term) + r'\b', lowered):
                traffic_terms.append(term)
        else:
            if term in lowered:
                traffic_terms.append(term)
    if traffic_terms:
        traffic_source_scale = "; ".join(dict.fromkeys(traffic_terms))
    business_model = ""
    if subtype_name in VERTICAL_SUBTYPE_TEMPLATES:
        business_model = VERTICAL_SUBTYPE_TEMPLATES[subtype_name]["business_model"]
    social_content_presence = ""
    if any(term in lowered for term in ("paid media", "ad creative", "landing page", "creative testing", "paid social")):
        social_content_presence = "paid media / landing-page creative workflow signal found"
    source_evidence = []
    for item in sorted(web_results[:8], key=lambda x: source_tier(x.get("url", ""), company_name, confirmed_domain)[0]):
        tier, tier_label = source_tier(item.get("url", ""), company_name, confirmed_domain)
        classification = classify_source(
            item.get("url", ""),
            item.get("title", ""),
            item.get("snippet", ""),
            company_name,
            customer_name,
            candidate_company,
            confirmed_domain,
            contact_name,
        )
        source_evidence.append(
            {
                "claim": evidence_claim(item.get("title", ""), item.get("snippet", ""), item.get("url", ""), company_name),
                "url": item.get("url", ""),
                "tier": tier,
                "tier_label": tier_label,
                "source_classification": classification,
            }
        )
    for page in sorted(compatible_pages[:6], key=lambda x: source_tier(x.get("url", ""), company_name, confirmed_domain)[0]):
        classification = classify_source(
            page.get("url", ""),
            page.get("title", ""),
            page.get("snippet", ""),
            company_name,
            customer_name,
            candidate_company,
            confirmed_domain,
            contact_name,
        )
        source_evidence.append(
            {
                "claim": evidence_claim(page.get("title", ""), page.get("snippet", ""), page.get("url", ""), company_name),
                "url": page.get("url", ""),
                "tier": source_tier(page.get("url", ""), company_name, confirmed_domain)[0],
                "tier_label": source_tier(page.get("url", ""), company_name, confirmed_domain)[1],
                "source_classification": classification,
            }
        )

    return {
        "company": company_name or "",
        "what_they_do": stable_company_description(company_name, enrichment_description, use_cases),
        "product_modules": modules,
        "pricing_tiers": pricing_tiers,
        "scale_signals": scale_signals[:5],
        "founders_or_leadership": founders[:5],
        "hq": hq,
        "founded_year": founded_year,
        "target_users": target_users,
        "traffic_source_scale": traffic_source_scale,
        "business_model": business_model,
        "vertical_subtype": vertical_subtype,
        "social_content_presence": social_content_presence,
        "candidate_company": candidate_company,
        "source_evidence": sorted(
            [item for item in source_evidence if usable_evidence_row(item, company_name)],
            key=lambda item: (
                0 if broad_company_overview_allowed(item.get("url", ""), "", item.get("claim", ""), company_name) else 1,
                item.get("tier", 9),
                1 if any(marker in (item.get("url") or "").lower() for marker in ("developer.", "/api", "pricing", "billing", "support.", "help.")) else 0,
            ),
        )[:8],
        "not_found": [
            item
            for item, present in [
                ("Funding", "funding" in lowered or "bootstrapped" in lowered),
                ("Current model vendors", any(vendor in lowered for vendor in ("openai", "runway", "luma", "midjourney"))),
                ("Enterprise customer count", "enterprise customer" in lowered),
                ("API volume / monthly generation volume", bool(scale_signals)),
            ]
            if not present
        ],
        "rejected_web_count": rejected_web_count,
    }


def infer_use_cases(text: str) -> list[str]:
    lowered = text.lower()
    use_cases: list[str] = []
    signals = [
        (("intent marketing", "customer acquisition", "performance marketing"), "performance marketing and customer acquisition workflow"),
        (("comparison platform", "comparison platforms", "compare products", "top brands"), "consumer comparison platform content and ranking workflow"),
        (("image", "ai art", "text-to-image", "background remover", "upscaler"), "image generation and creative asset editing"),
        (("video", "shorts", "text-to-video", "ai video"), "video generation / short-form creative workflow"),
        (("voice", "audio", "tts", "text to speech"), "voice or audio generation workflow"),
        (("model api", "inference api", "creative api", "api deployment", "api integration", "custom model", "enterprise integration"), "API or enterprise integration requirements"),
    ]
    for needles, label in signals:
        if any(needle in lowered for needle in needles) and label not in use_cases:
            use_cases.append(label)
    return use_cases


def infer_competitors(text: str) -> list[str]:
    competitors = []
    if any(signal in text.lower() for signal in ("intent marketing", "customer acquisition", "comparison platform")):
        competitors.append("Other intent-marketing / comparison-platform acquisition vendors")
    for name in ["OpenAI", "Runway", "Midjourney", "Stability AI", "Adobe Firefly", "Pika", "Kling", "Luma"]:
        if name.lower() in text.lower():
            competitors.append(f"{name} or adjacent creative AI tools")
    return competitors[:5]


def infer_metrics(text: str) -> dict[str, str]:
    metrics: dict[str, str] = {}
    active_users = re.search(r"over\s+([\d.]+\s*(?:million|m|k))\s+active users", text, re.IGNORECASE)
    downloads = re.search(r"([\d.]+\s*(?:million|m|k))\s+downloads", text, re.IGNORECASE)
    if active_users:
        metrics["paid_users"] = f"Likely scale signal: over {active_users.group(1)} active users (?)"
    if downloads:
        metrics["monthly_volume"] = f"Likely adoption signal: {downloads.group(1)} downloads mentioned publicly (?)"
    return metrics


def possible_byteplus_fit(use_cases: list[str], combined_text: str) -> list[dict[str, str]]:
    lowered = combined_text.lower()
    if any(signal in lowered for signal in ("intent marketing", "customer acquisition", "comparison platform")):
        return [
            {"product": "Ark / model platform", "reason": "Validate fit for scalable model evaluation, routing, inference cost control, and integration into acquisition/optimization workflows", "confidence": "medium"},
            {"product": "Seedance", "reason": "Validate whether paid-media or landing-page video creative generation is a near-term workload", "confidence": "low"},
            {"product": "Seedream", "reason": "Validate whether display/ad creative variation, localized imagery, or landing-page asset generation is a near-term workload", "confidence": "low"},
        ]
    return [
        {"product": "Seedance", "reason": "Validate fit for video generation quality, consistency, and short-form creative workflows", "confidence": "medium"},
        {"product": "Seedream", "reason": "Validate fit for image generation, editing, upscaling, and creative asset production", "confidence": "medium"},
        {"product": "Ark / model platform", "reason": "Validate model evaluation, deployment, routing, cost/performance, and API-scale needs", "confidence": "medium"},
    ]


def suggested_customer_questions(use_cases: list[str], combined_text: str) -> list[str]:
    lowered = combined_text.lower()
    if any(signal in lowered for signal in ("intent marketing", "customer acquisition", "comparison platform")):
        return [
            "Can you confirm whether this discussion is for Natural Intelligence's intent-marketing / customer-acquisition platform?",
            "Where are AI models used today: traffic qualification, landing-page generation, ranking/recommendation, ad creative, sales assistance, or internal operations?",
            "Which KPI matters most for a model evaluation: conversion lift, cost per qualified lead, content production speed, compliance risk, latency, or infra cost?",
            "What is the current experimentation workflow for comparison pages, ads, and localized content?",
            "Do you already use third-party LLM/image/video models, and where are quality, cost, or governance becoming limiting factors?",
            "What would make a POC successful: measurable conversion uplift, lower creative cost, faster launch cycles, better personalization, or safer automated content?",
        ]
    return [
        "Can you confirm whether this discussion is for the company/product identified in the prep?",
        "Are you evaluating BytePlus for model quality, API/inference scale, cost/performance, or enterprise deployment?",
        "Which image/video generation capabilities are most important: quality, controllability, consistency, speed, safety, or cost?",
        "What is your current generation stack, and which vendors/models are you benchmarking against?",
        "What monthly generation volume, peak concurrency, and latency targets should we size for?",
        "Would a POC be judged by creative quality, conversion lift, production cost, or developer integration effort?",
    ]


def synthesize_known_fields(enrichment: dict[str, Any] | None, docs: list[dict[str, Any]], web_results: list[dict[str, str]], apollo_enrichment: dict[str, Any] | None = None) -> dict[str, Any]:
    if not enrichment:
        return {}
    text = " ".join(
        [enrichment.get("description", "")]
        + [str(doc.get("summary", "")) for doc in docs[:5]]
        + [f"{item.get('title', '')} {item.get('snippet', '')}" for item in web_results[:8]]
    )
    known: dict[str, Any] = {}
    company = enrichment.get("company_name")
    if company:
        known["stakeholder_context"] = f"Likely: {company} stakeholder; validate role, buying authority, and meeting objective."
    if enrichment.get("description"):
        known["objectives"] = "To Validate: confirm whether the customer is evaluating model quality, API/inference scale, cost, or enterprise deployment."
        if any(signal in text.lower() for signal in ("intent marketing", "customer acquisition", "comparison platform")):
            known["pain_points"] = "Likely: intent-marketing platforms care about qualified traffic conversion, landing-page/content experimentation speed, acquisition cost, lead quality, and brand/compliance controls (?)"
        else:
            known["pain_points"] = "Likely: creative AI teams often care about output quality, controllability, latency, generation cost, and safety/commercial rights (?)"
    metrics = infer_metrics(text)
    known.update(metrics)
    if "api" in text.lower() or "enterprise" in text.lower():
        known["current_models"] = "To Validate: whether they use in-house models, open-source models, or third-party APIs."
        known["current_vendors"] = "To Validate: current AI/model providers and fallback stack."
    dossier = enrichment.get("dossier") or {}
    if dossier.get("scale_signals"):
        known["monthly_volume"] = "Public scale signal: " + "; ".join(dossier["scale_signals"][:2]) + " (?)"
        known["paid_users"] = "To Validate: paid/free split; public sources mention usage scale but not paid user count."
    if dossier.get("pricing_tiers"):
        known["budget_status"] = "To Validate: public customer packaging terms were found, but actual AI infra spend, vendor commitments, budget owner, and BytePlus-relevant commitment are not confirmed."
    if dossier.get("product_modules"):
        known["expansion_opportunity"] = "Possible product modules: " + ", ".join(dossier["product_modules"][:6])
    return known


def generate_byteplus_fit_hypotheses(
    vertical: str,
    description: str = "",
    tech_signals: list[str] | None = None,
) -> dict[str, list]:
    """
    Return vertical-aware BytePlus fit hypotheses.
    All items are framed as hypotheses to validate; no confirmed-workload claims.
    Returns {"known_use_cases": [...], "possible_byteplus_fit": [...]} or {} for default/unknown.
    Each possible_byteplus_fit entry has: product, reason, validation, confidence.
    """
    desc_lower = (description or "").lower()
    techs = [t.lower() for t in (tech_signals or [])]

    def _desc(*kw: str) -> bool:
        return any(k in desc_lower for k in kw)

    def _tech(*kw: str) -> bool:
        return any(any(k in t for k in kw) for t in techs)

    if vertical == "marketing_adtech":
        ark_priority = _tech("ai", "openai", "bedrock", "api", "ml") or _tech("aws", "azure", "gcp")
        fit = [
            {
                "product": "Seedance / Seedream",
                "reason": "campaign creative generation, image/video ad asset production, content localization and variation, and creative testing at scale",
                "validation": "Validate actual creative workflow, asset volume, production toolchain, and success metric.",
                "confidence": "medium",
            },
            {
                "product": "Ark / model platform",
                "reason": "internal AI workflow, campaign assistant, model routing/evaluation, API integration, and cost/latency control for creative production pipelines",
                "validation": "Validate current model stack, API usage pattern, ownership, and cost/latency expectations.",
                "confidence": "medium",
            },
            {
                "product": "VLM / automation",
                "reason": "creative QA, brand safety review, asset inspection, ad compliance checking, and content moderation workflow",
                "validation": "Validate whether visual QA or compliance is a pain point and what the current review process looks like.",
                "confidence": "low",
            },
        ]
        if ark_priority:
            fit = [fit[1], fit[0], fit[2]]
        return {
            "known_use_cases": [
                "Possible fit hypothesis to validate: campaign creative generation — image/video ad assets, creative variations, and localization at scale (?)",
                "Possible fit hypothesis to validate: AI-powered content production pipeline — automated asset creation, brand templates, and creative testing (?)",
                "Possible fit hypothesis to validate: AI workflow automation — internal creative review, brand safety QA, and asset inspection (?)",
            ],
            "possible_byteplus_fit": fit,
        }

    if vertical == "media_entertainment":
        has_music = _desc("music", "record", "artist", "album", "음반", "연예")
        has_film = _desc("film", "movie", "streaming", "cinema", "broadcast")
        if has_music:
            seedance_reason = "artist promo videos, teaser content, short-form fan engagement clips, MV/storyboard exploration, and social video production"
            seedream_reason = "poster/key visual generation, concept art, artist visual assets, album/campaign creatives, and image editing"
        elif has_film:
            seedance_reason = "promo trailers, teaser content, short-form social video production, and scene/storyboard exploration"
            seedream_reason = "poster/key visual generation, concept art, promotional creatives, and image editing"
        else:
            seedance_reason = "promo video generation, teaser content, short-form social video production, and visual storytelling"
            seedream_reason = "poster/key visual generation, concept art, campaign creatives, and image editing"
        return {
            "known_use_cases": [
                "Possible fit hypothesis to validate: AI-generated visual content for promotional content, visuals, and social media assets (?)",
                "Possible fit hypothesis to validate: AI workflow automation for content review, asset management, and localization (?)",
            ],
            "possible_byteplus_fit": [
                {
                    "product": "Seedance",
                    "reason": seedance_reason,
                    "validation": "Validate content production volume, social video workflow, and creative toolchain.",
                    "confidence": "medium",
                },
                {
                    "product": "Seedream",
                    "reason": seedream_reason,
                    "validation": "Validate image/visual asset production workflow and design team tooling.",
                    "confidence": "medium",
                },
                {
                    "product": "Ark / model platform",
                    "reason": "content planning assistant, script/caption generation, localization, fan/community content workflows, and model API integration",
                    "validation": "Validate current AI stack, content planning tools, and API integration needs.",
                    "confidence": "medium",
                },
                {
                    "product": "VLM / automation",
                    "reason": "content review, visual asset tagging, video understanding, brand/safety checks, and catalog/search automation",
                    "validation": "Validate whether content QA or catalog automation is a pain point.",
                    "confidence": "low",
                },
            ],
        }

    if vertical == "ecommerce":
        return {
            "known_use_cases": [
                "Possible fit hypothesis to validate: product image generation/editing, background replacement, and SKU visual variation at scale (?)",
                "Possible fit hypothesis to validate: AI-powered shopping assistant, product copy generation, and recommendation/search automation (?)",
            ],
            "possible_byteplus_fit": [
                {
                    "product": "Seedream",
                    "reason": "product image generation/editing, background replacement, SKU visual variation, and localized product creatives",
                    "validation": "Validate product catalog size, image production volume, and current creative toolchain.",
                    "confidence": "medium",
                },
                {
                    "product": "Seedance",
                    "reason": "short product videos, ad creatives, livestream/product demo clips, and social commerce video assets",
                    "validation": "Validate whether video ads or livestream content production is a current workflow.",
                    "confidence": "medium",
                },
                {
                    "product": "Ark / model platform",
                    "reason": "shopping assistant, product copy generation, recommendation/search assistant, and customer service automation",
                    "validation": "Validate current AI stack, recommendation/search ownership, and conversational AI plans.",
                    "confidence": "medium",
                },
                {
                    "product": "VLM / automation",
                    "reason": "catalog QA, product image understanding, OCR from product pages, moderation, and duplicate detection",
                    "validation": "Validate whether catalog QA or image moderation is a current pain point.",
                    "confidence": "low",
                },
            ],
        }

    if vertical == "gaming":
        return {
            "known_use_cases": [
                "Possible fit hypothesis to validate: game asset generation — character/item creatives, key visuals, and store assets (?)",
                "Possible fit hypothesis to validate: marketing creative generation — game trailer variations, promo clips, and ad creatives (?)",
            ],
            "possible_byteplus_fit": [
                {
                    "product": "Seedance",
                    "reason": "game trailer variations, character/action promo clips, UGC-style short video ads, and cinematic previsualization",
                    "validation": "Validate game genre, trailer production workflow, and marketing creative volume.",
                    "confidence": "medium",
                },
                {
                    "product": "Seedream",
                    "reason": "character concept art, item/skin creatives, key visual generation, and store assets",
                    "validation": "Validate game art pipeline, in-house vs. outsourced art production, and asset generation volume.",
                    "confidence": "medium",
                },
                {
                    "product": "Ark / model platform",
                    "reason": "NPC/dialogue assistant, player support, localization, community moderation, and model routing",
                    "validation": "Validate current AI usage in-game or live-ops, support automation needs, and model stack.",
                    "confidence": "medium",
                },
                {
                    "product": "VLM / automation",
                    "reason": "gameplay video understanding, content moderation, ad creative QA, and bug/visual issue triage",
                    "validation": "Validate whether content moderation or QA automation is a current pain point.",
                    "confidence": "low",
                },
            ],
        }

    if vertical == "ai_video_creative":
        ark_priority = _tech("api", "openai", "bedrock", "ml", "aws", "azure", "gcp") or _desc("platform", "developer", "api")
        fit = [
            {
                "product": "Seedance",
                "reason": "model comparison, video generation capacity, reference-based generation, creative API integration, and quality/latency benchmarking",
                "validation": "Validate current model stack, generation volume, API integration needs, and benchmark criteria.",
                "confidence": "medium",
            },
            {
                "product": "Seedream",
                "reason": "image-to-video pipeline assets, image editing, reference image generation, and visual consistency workflows",
                "validation": "Validate image generation workflow, pipeline architecture, and quality benchmarks.",
                "confidence": "medium",
            },
            {
                "product": "Ark / model platform",
                "reason": "multi-model routing, evaluation platform, model API orchestration, and cost/latency optimization",
                "validation": "Validate model evaluation needs, routing requirements, and API scale.",
                "confidence": "medium",
            },
            {
                "product": "VLM / automation",
                "reason": "video QA, generated-content evaluation, prompt/result inspection, and safety/quality scoring",
                "validation": "Validate whether automated QA or safety scoring is a current workflow.",
                "confidence": "low",
            },
        ]
        if ark_priority:
            fit = [fit[2], fit[0], fit[1], fit[3]]
        return {
            "known_use_cases": [
                "Possible fit hypothesis to validate: video generation, editing, or batch production workflow (?)",
                "Possible fit hypothesis to validate: API integration for multi-model routing, evaluation, or content production pipeline (?)",
            ],
            "possible_byteplus_fit": fit,
        }

    if vertical == "enterprise_llm":
        has_creative_signal = _desc("creative", "content", "media", "image", "video")
        fit: list[dict[str, Any]] = [
            {
                "product": "Ark / model platform",
                "reason": "model gateway, routing, evaluation, observability, enterprise API integration, cost/latency optimization, and internal assistant workflows",
                "validation": "Validate current model stack, API integration needs, evaluation requirements, and cost/latency expectations.",
                "confidence": "medium",
            },
            {
                "product": "VLM / OCR",
                "reason": "document understanding, image/video understanding, workflow automation, and support/ops automation",
                "validation": "Validate document processing volume, understanding requirements, and automation use cases.",
                "confidence": "medium",
            },
        ]
        if has_creative_signal:
            fit += [
                {
                    "product": "Seedream",
                    "reason": "content/image generation, visual asset production, and creative workflow automation",
                    "validation": "Validate whether creative/image generation is a near-term workload.",
                    "confidence": "low",
                },
                {
                    "product": "Seedance",
                    "reason": "video generation, content production, and media workflow automation",
                    "validation": "Validate whether video generation is a near-term workload.",
                    "confidence": "low",
                },
            ]
        return {
            "known_use_cases": [
                "Possible fit hypothesis to validate: enterprise AI workflow automation, model API integration, and internal assistant use cases (?)",
                "Possible fit hypothesis to validate: document/image understanding, ops automation, and workflow intelligence (?)",
            ],
            "possible_byteplus_fit": fit,
        }

    if vertical == "consumer_technology":
        has_developer = _desc("developer", "platform", "ecosystem", "sdk", "api")
        has_creative = _desc("creative", "media", "content", "advertising", "marketing", "campaign")
        creative_note = (
            "campaign creative generation, product visual assets, localization, short-form video, launch content, and creative variation testing"
            " — conditional on whether the meeting is with marketing/creative/content teams"
        )
        fit: list[dict[str, Any]] = [
            {
                "product": "Ark / model platform",
                "reason": "model routing/evaluation, internal AI assistant workflows, developer/product team API integration, inference quality/latency/cost benchmarking, and enterprise model governance",
                "validation": "Validate which team this discussion is for (product, AI/ML, developer platform, marketing, or ops) and what the priority use case is.",
                "confidence": "medium",
            },
            {
                "product": "VLM / OCR / multimodal automation",
                "reason": "UI screenshot understanding, device/content QA, visual inspection, accessibility/documentation workflows, support automation, and image/video understanding for product or app workflows",
                "validation": "Validate whether UI/content QA, visual inspection, accessibility, or support automation is a current pain point.",
                "confidence": "medium",
            },
            {
                "product": "Seedream / Seedance",
                "reason": creative_note,
                "validation": "Confirm whether the meeting involves marketing, creative, or content teams before positioning Seedream/Seedance.",
                "confidence": "low",
            },
        ]
        return {
            "known_use_cases": [
                "Possible fit hypothesis to validate: model routing/evaluation, internal AI assistant, developer/product API integration, and inference benchmarking (?)",
                "Possible fit hypothesis to validate: UI/content QA, visual inspection, accessibility automation, and multimodal understanding for product or app workflows (?)",
                "Possible fit hypothesis to validate: creative/product-marketing assets — conditional on whether discussion is with marketing/creative teams (?)",
            ],
            "possible_byteplus_fit": fit,
        }

    return {}  # default/unknown — renderer uses generic fallback


def _add_vertical_fit_from_apollo(render_json: dict[str, Any]) -> None:
    """Add BytePlus fit hypotheses for known verticals when Apollo org enrichment is available.

    Sets enrichment.available=True and enrichment.fit_source='apollo_hypothesis' so
    the renderer bypasses the workload-confirmation gate via _is_apollo_hypothesis_fit().
    Does NOT promote active_workload_confidence — workload remains unconfirmed.
    """
    vertical = render_json.get("vertical") or {}
    vertical_name = vertical.get("name") or ""
    apollo = render_json.get("apollo") or {}
    if apollo.get("status") not in ("organization_matched", "partial"):
        return
    enrichment = render_json.get("enrichment") or {}
    existing_use_cases = [
        item for item in (enrichment.get("known_use_cases") or [])
        if item and not str(item).startswith("To Validate") and not str(item).startswith("Likely fit hypothesis") and not str(item).startswith("Possible fit hypothesis")
    ]
    if existing_use_cases:
        return  # web enrichment already has confirmed use cases — do not override
    org = apollo.get("organization") or {}
    description = org.get("short_description_en") or org.get("short_description") or ""
    tech_signals = list(org.get("technology_names") or org.get("technologies") or [])
    hypotheses = generate_byteplus_fit_hypotheses(vertical_name, description, tech_signals)
    if not hypotheses:
        return
    enrichment["known_use_cases"] = hypotheses["known_use_cases"]
    enrichment["possible_byteplus_fit"] = hypotheses["possible_byteplus_fit"]
    enrichment["available"] = True
    enrichment["fit_source"] = "apollo_hypothesis"
    render_json["enrichment"] = enrichment


def _build_enrichment_from_pages(
    results: list[dict[str, str]],
    pages: list[dict[str, Any]],
    inferred_company: str | None,
    customer: "CustomerIdentity",
    source_label: str,
    debug: bool = False,
) -> tuple[dict[str, Any], list[dict[str, str]], None]:
    """Build a minimal enrichment dict from already-fetched pages (no web search)."""
    combined = " ".join((item.get("title", "") + " " + item.get("snippet", "")).lower() for item in results)
    use_cases = infer_use_cases(combined)
    description = (results[0].get("snippet") or "").strip() if results else ""
    description = stable_company_description(inferred_company, description, use_cases) if description else ""
    website = customer.domain or ""
    if not website:
        for item in results:
            h = urlparse(item.get("url", "")).netloc.lower().removeprefix("www.")
            if h and not blocked_as_company_website(h):
                website = stable_company_website(h)
                break
    dossier = extract_company_dossier(inferred_company, description, use_cases, results, pages, customer.canonical_name, customer.domain, customer.contact_name)
    if not dossier.get("what_they_do") or str(dossier.get("what_they_do", "")).startswith("To Validate:"):
        if description:
            dossier["what_they_do"] = description
    enrichment: dict[str, Any] = {
        "available": True,
        "confidence": "medium",
        "website": website,
        "company_name": inferred_company or "",
        "description": dossier.get("what_they_do") or description,
        "dossier": dossier,
        "page_evidence": pages,
        "industry": "To Validate: inferred from explicit URL sources",
        "known_use_cases": use_cases,
        "known_competitors": infer_competitors(combined),
        "known_risks": ["Direct URL enrichment only; validate customer requirements, budget, timeline, and decision process"],
        "possible_byteplus_fit": possible_byteplus_fit(use_cases, combined),
        "suggested_questions": suggested_customer_questions(use_cases, combined),
        "source_links": [{"label": item.get("title") or item.get("url", ""), "url": item.get("url", "")} for item in results[:3]],
        "source": source_label,
        "web_search_status": "explicit_url_only",
        "company_overview_status": "usable_results_found",
    }
    return enrichment, results, None


def build_web_enrichment(context: PrepContext, debug: bool = False) -> tuple[dict[str, Any] | None, list[dict[str, str]], str | None]:
    if os.getenv("PREP_WEB_SEARCH_DISABLED", "0").strip() == "1":
        debug_log(debug, "web search disabled by PREP_WEB_SEARCH_DISABLED=1")
        # Even when web search is disabled, explicit user URLs can still be fetched.
        if context.user_urls:
            customer = context.customer
            inferred_company = customer.company_name or (domain_to_name(customer.domain) if customer.domain else None) or infer_company_from_docs(customer.canonical_name, context.prior_docs)
            eu_results, eu_pages = fetch_explicit_user_urls(context.user_urls, inferred_company, customer.domain, debug=debug)
            if eu_results:
                return _build_enrichment_from_pages(eu_results, eu_pages, inferred_company, customer, "explicit_user_url", debug=debug)
        return None, [], "web_search: disabled_by_env"
    customer = context.customer
    inferred_company = customer.company_name or (domain_to_name(customer.domain) if customer.domain else None) or infer_company_from_docs(customer.canonical_name, context.prior_docs)
    direct_overview_results: list[dict[str, str]] = []
    direct_overview_pages: list[dict[str, Any]] = []
    direct_overview_warning: str | None = None
    if customer.domain and inferred_company:
        direct_overview_results, direct_overview_pages, direct_overview_warning = collect_official_domain_overview(customer.domain, inferred_company, debug=debug)
    company_overview_status = "usable_results_found" if direct_overview_results else "no_overview_eligible_results"

    # Pre-fetch explicit user-provided URLs (runs regardless of web search outcome).
    user_url_results: list[dict[str, str]] = []
    user_url_pages: list[dict[str, Any]] = []
    if context.user_urls:
        user_url_results, user_url_pages = fetch_explicit_user_urls(context.user_urls, inferred_company, customer.domain, debug=debug)
        if user_url_results and not direct_overview_results:
            company_overview_status = "usable_results_found"

    queries = expand_web_queries(customer, inferred_company)
    if not queries:
        return None, [], "web_search: disabled_or_not_configured"
    results, warning = collect_web_results(queries, debug=debug)
    if not results:
        if direct_overview_results:
            results = direct_overview_results
            page_evidence = direct_overview_pages
            warning = None
        elif user_url_results:
            # Explicit user URLs are the only available source — treat like direct domain overview.
            results = user_url_results
            page_evidence = user_url_pages
            warning = None
            company_overview_status = "usable_results_found"
        elif customer.domain and inferred_company:
            all_pages = direct_overview_pages + user_url_pages
            dossier = extract_company_dossier(inferred_company, "", [], [], all_pages, customer.canonical_name, customer.domain, customer.contact_name)
            description = "To Validate: business description could not be enriched because web search/fetch was unavailable."
            dossier["what_they_do"] = description
            enrichment = {
                "available": True,
                "confidence": "low",
                "website": customer.domain,
                "company_name": inferred_company,
                "description": description,
                "dossier": dossier,
                "page_evidence": all_pages,
                "industry": "To Validate: industry could not be enriched from available sources",
                "known_use_cases": [],
                "known_competitors": [],
                "known_risks": ["Public company overview unavailable; validate customer requirements, budget, timeline, and decision process"],
                "possible_byteplus_fit": [],
                "suggested_questions": [],
                "source_links": [],
                "source": "web_search",
                "web_search_status": web_status_from_warning(warning, False),
                "company_overview_status": company_overview_status,
            }
            return enrichment, [], warning
        else:
            return None, [], warning
    else:
        page_evidence = direct_overview_pages + user_url_pages + collect_page_evidence(results, inferred_company, confirmed_domain=customer.domain, debug=debug)
        if direct_overview_results:
            seen_result_urls = {item.get("url") for item in direct_overview_results}
            results = direct_overview_results + [item for item in results if item.get("url") not in seen_result_urls]
        if user_url_results:
            seen_result_urls = {item.get("url") for item in results}
            results = results + [item for item in user_url_results if item.get("url") not in seen_result_urls]
    scored_results = sorted(
        ((contextual_web_score(item, customer.canonical_name, inferred_company), item) for item in results),
        key=lambda pair: pair[0],
        reverse=True,
    )
    filtered_results = [item for score, item in scored_results if score > 0]
    if filtered_results:
        results = filtered_results[:12]
    elif customer.domain and inferred_company:
        if direct_overview_results:
            results = direct_overview_results
            page_evidence = direct_overview_pages
            warning = None
        else:
            results = [item for _, item in scored_results][:12]
            warning = warning or None
    else:
        results = [item for _, item in scored_results][:12]
        warning = warning or None

    preferred = results[0]
    for item in results:
        haystack = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        if customer.canonical_name and inferred_company and customer.canonical_name.lower() in haystack and inferred_company.lower() in haystack:
            preferred = item
            break
    else:
        preferred = max(results, key=product_description_score)
    for item in results:
        if official_source(item.get("url", ""), inferred_company, customer.domain):
            preferred = item
            break
    if inferred_company:
        for item in results:
            haystack = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
            if inferred_company.lower() in haystack and preferred == results[0]:
                preferred = item
                break
    overview = select_company_overview_result(results, inferred_company, customer.domain)
    description = (overview or {}).get("snippet") or ""
    website = customer.domain or ""
    if not website:
        for item in results:
            parsed = urlparse(item["url"])
            host = parsed.netloc.lower().removeprefix("www.")
            if host and official_source(item.get("url", ""), inferred_company, customer.domain) and not blocked_as_company_website(host):
                website = stable_company_website(host)
                break
    combined = " ".join((item.get("title", "") + " " + item.get("snippet", "")).lower() for item in results)
    use_cases = infer_use_cases(combined)
    if any(term in combined for term in ("creative platform", "generative creative", "image generation", "video generation", "text-to-image", "text-to-video")) and not use_cases:
        use_cases.append("creative AI / generative media workflow")
    description = stable_company_description(inferred_company, description, use_cases)
    dossier = extract_company_dossier(inferred_company, description, use_cases, results, page_evidence, customer.canonical_name, customer.domain, customer.contact_name)
    web_search_status = web_status_from_warning(warning, bool(results))
    official_overview = official_company_overview_evidence(dossier, inferred_company)
    if official_overview:
        company_overview_status = "usable_results_found"
    if official_overview and (
        not dossier.get("what_they_do")
        or str(dossier.get("what_they_do", "")).startswith("To Validate:")
        or not description
        or str(description).startswith("To Validate:")
    ):
        description = str(official_overview.get("claim") or "").strip()
        dossier["what_they_do"] = description
        company_overview_status = "usable_results_found"
    elif inferred_company and customer.domain and not (dossier.get("what_they_do") or description):
        description = "To Validate: business description could not be enriched because web search/fetch was unavailable."
        dossier["what_they_do"] = description
        company_overview_status = "no_overview_eligible_results"
    trusted_source_results = [
        item for item in results
        if classify_source(
            item.get("url", ""),
            item.get("title", ""),
            item.get("snippet", ""),
            inferred_company,
            customer.canonical_name,
            dossier.get("candidate_company"),
            customer.domain,
            customer.contact_name,
        ) in {"customer_evidence", "candidate_entity_evidence"}
    ]
    trusted_page_links = [
        {"label": item.get("title") or item.get("url", ""), "url": item.get("url", "")}
        for item in page_evidence
        if classify_source(item.get("url", ""), item.get("title", ""), item.get("snippet", ""), inferred_company, customer.canonical_name, dossier.get("candidate_company"), customer.domain, customer.contact_name) in {"customer_evidence", "candidate_entity_evidence"}
    ]
    source_links = (trusted_page_links + [{"label": item["title"], "url": item["url"]} for item in trusted_source_results])[:5]
    if dossier.get("what_they_do"):
        description = dossier["what_they_do"]
    competitors = infer_competitors(combined)
    fit = possible_byteplus_fit(use_cases, combined)
    questions = suggested_customer_questions(use_cases, combined)
    enrichment = {
        "available": True,
        "confidence": "medium",
        "website": website,
        "company_name": inferred_company or "",
        "description": description,
        "dossier": dossier,
        "page_evidence": page_evidence,
        "industry": "To Validate: inferred from public web results",
        "known_use_cases": use_cases,
        "known_competitors": competitors,
        "known_risks": ["Public web context only; validate customer requirements, budget, timeline, and decision process"],
        "possible_byteplus_fit": fit,
        "suggested_questions": questions,
        "source_links": source_links,
        "source": "web_search",
        "web_search_status": web_search_status,
        "company_overview_status": company_overview_status,
    }
    return enrichment, results, None


def is_likely_prep_doc(doc: dict[str, Any], customer_name: str | None) -> bool:
    title = (doc.get("title") or "").lower()
    if customer_name and customer_name.lower() not in title:
        return False
    return "pre-meeting prep" in title or "customer profile" in title or "prep" in title


def choose_existing_doc(docs: list[dict[str, Any]], customer_name: str | None) -> dict[str, Any] | None:
    for doc in docs:
        if is_likely_prep_doc(doc, customer_name):
            return doc
    return None


def classify_event(event: dict[str, Any], explicit_identity: CustomerIdentity | None = None) -> tuple[bool, str]:
    title = (event.get("summary") or "").lower()
    has_external_domain = bool(external_attendee_domains(event))
    has_customer_signal = has_external_domain or bool(title_customer_candidate(event.get("summary") or ""))
    if explicit_identity and explicit_identity.canonical_name:
        lowered = explicit_identity.canonical_name.lower()
        has_customer_signal = has_customer_signal or lowered in title
    if any(pattern in title for pattern in INTERNAL_TITLE_PATTERNS) and not has_customer_signal:
        return False, "internal/generic title without customer signal"
    if has_customer_signal:
        return True, "customer signal found"
    return False, "no external corporate attendee or customer signal"


def call_mcp_enrichment(context: PrepContext, debug: bool = False) -> dict[str, Any] | None:
    url = os.getenv("MCP_CUSTOMER_ENRICHMENT_URL")
    token = os.getenv("MCP_CUSTOMER_ENRICHMENT_TOKEN")
    if not url:
        debug_log(debug, "MCP_CUSTOMER_ENRICHMENT_URL not configured; skipping enrichment")
        return None
    payload = {
        "customer_name": context.customer.canonical_name,
        "domain": context.customer.domain,
        "email": context.customer.email,
        "event": context.event or {},
        "prior_docs_summary": context.prior_docs[:5],
    }
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        debug_log(debug, f"MCP enrichment failed: {exc}")
        context.missing_context.append("MCP enrichment configured but request failed")
        return None


def build_context(
    prep_input: PrepInput,
    *,
    event: dict[str, Any] | None,
    debug: bool = False,
    no_apollo: bool = False,
    apollo_refresh: bool = False,
    apollo_debug: bool = False,
    apollo_max_people: int | None = None,
) -> PrepContext:
    explicit_customer = prep_input.value if prep_input.mode == "customer" else None
    explicit_domain = prep_input.domain or (prep_input.value if prep_input.mode == "domain" else None)
    explicit_email = prep_input.value if prep_input.mode == "email" else None
    identity = resolve_customer(
        explicit_customer=explicit_customer,
        explicit_domain=explicit_domain,
        explicit_email=explicit_email,
        explicit_contact=prep_input.contact,
        explicit_company=prep_input.company,
        event=event,
    )
    missing: list[str] = []
    if not event:
        missing.append("meeting context")
    if identity.confidence in {"weak", "unknown"}:
        missing.append("confirmed customer identity")

    search_terms = expand_internal_queries(identity)
    initial_docs, search_warning = search_docs(search_terms[:6], debug=debug)
    inferred_company = identity.company_name or (domain_to_name(identity.domain) if identity.domain else None) or infer_company_from_docs(identity.canonical_name, initial_docs)
    expanded_docs: list[dict[str, Any]] = []
    expanded_warning: str | None = None
    if inferred_company:
        expanded_docs, expanded_warning = search_docs(expand_internal_queries(identity, inferred_company), debug=debug)
    prior_docs = rank_docs(merge_docs(initial_docs, expanded_docs), [identity.canonical_name or "", identity.domain or "", inferred_company or ""])[:10]
    if search_warning:
        missing.append(search_warning)
    if expanded_warning and expanded_warning != search_warning:
        missing.append(expanded_warning)

    context = PrepContext(identity, event, prior_docs, None, missing, docs_search_available=bool(prior_docs) or search_warning is None)
    context.user_urls = list(prep_input.user_urls or [])
    mcp_enrichment = call_mcp_enrichment(context, debug=debug)

    # Apollo enrichment: after MCP, before web search (optional, additive)
    if _APOLLO_AVAILABLE and not no_apollo:
        try:
            apollo_result = _enrich_with_apollo(
                identity,
                prep_input=prep_input,
                event=event,
                vertical_name=None,  # vertical not yet inferred at this stage
                apollo_max_people=apollo_max_people,
                apollo_refresh=apollo_refresh,
                debug=apollo_debug or debug,
            )
            context.apollo_enrichment = _apollo_result_to_dict(apollo_result)
            if apollo_result.warnings:
                for w in apollo_result.warnings:
                    debug_log(debug, f"Apollo warning: {w}")
        except Exception as exc:  # pragma: no cover - defensive
            debug_log(debug, f"Apollo enrichment failed: {exc}")
            context.apollo_enrichment = {"status": "request_failed", "confidence": "none"}

    web_enrichment, web_results, web_warning = build_web_enrichment(context, debug=debug)
    context.search_results = web_results
    context.web_search_available = bool(web_results)
    if web_enrichment and web_enrichment.get("web_search_status"):
        context.web_search_status = str(web_enrichment["web_search_status"])
    elif web_results:
        context.web_search_status = "usable_results_found"
    elif web_warning and "web_search:" in web_warning:
        context.web_search_status = web_warning.split("web_search:", 1)[1].strip()
    else:
        context.web_search_status = "ran_but_no_results"
    if web_enrichment and web_enrichment.get("company_overview_status"):
        context.company_overview_status = str(web_enrichment["company_overview_status"])
    elif customer := context.customer:
        context.company_overview_status = "no_overview_eligible_results" if customer.domain else "disabled_or_not_configured"
    context.enrichment = mcp_enrichment or web_enrichment
    context.known = synthesize_known_fields(context.enrichment, context.prior_docs, context.search_results, context.apollo_enrichment)
    dossier = (context.enrichment or {}).get("dossier") or {}
    if any(
        item.get("source_classification") == "customer_evidence"
        and "Tier 1 - official company site" in str(item.get("tier_label") or "")
        and str(item.get("claim") or "").strip()
        and not contains_placeholder(str(item.get("claim") or ""))
        and broad_company_overview_allowed(item.get("url", ""), "", str(item.get("claim") or ""), context.customer.company_name or context.customer.canonical_name)
        for item in dossier.get("source_evidence") or []
    ):
        context.web_search_status = "usable_results_found"
        context.company_overview_status = "usable_results_found"
    if web_warning and context.web_search_status != "usable_results_found":
        context.missing_context.append(f"web_search: {context.web_search_status}")
    if context.company_overview_status not in {"usable_results_found", "available"}:
        context.missing_context.append(f"company_overview_enrichment: {context.company_overview_status}")
    if mcp_enrichment is None:
        context.missing_context.append("MCP enrichment unavailable")
    return context


def _augment_render_json_from_apollo(render_json: dict[str, Any], apollo: dict[str, Any]) -> None:
    """Merge Apollo org data into dossier/enrichment fields when web enrichment is unavailable.

    Non-Latin descriptions are normalized to a concise English paraphrase (stored as
    short_description_en). Long English descriptions are summarized to ≤2 sentences.
    The original text is preserved in apollo_desc_original so the Evidence Table can
    show it; user-facing fields always receive the concise English version.
    Apollo firmographic signals (employee count, revenue) go into dossier.scale_signals,
    NOT monthly_volume (which is reserved for API/generation volume).
    """
    if not apollo or apollo.get("status") not in ("organization_matched", "partial"):
        return
    org_orig = apollo.get("organization") or {}
    desc = str(org_orig.get("short_description") or org_orig.get("description") or "").strip()

    # Normalize non-Latin descriptions to English; preserve original for evidence
    if desc and _is_substantially_non_latin(desc):
        english_desc = _build_english_apollo_description(org_orig)
        original_desc: str | None = desc
    else:
        english_desc = desc
        original_desc = None

    # Summarize long English descriptions to 1-2 sentences for user-facing fields
    user_facing_desc = _summarize_description(english_desc) if english_desc else ""

    # Shallow-copy the org dict to annotate without mutating the original context
    org = dict(org_orig)
    if user_facing_desc:
        org["short_description_en"] = user_facing_desc
    if original_desc:
        org["apollo_desc_original"] = original_desc
    apollo_copy = dict(apollo)
    apollo_copy["organization"] = org
    render_json["apollo"] = apollo_copy

    # Populate user-facing description fields only when no better source exists
    if user_facing_desc:
        apollo_desc_text = f"{user_facing_desc} (Apollo signal)"
        apollo_likely_desc = f"Likely: {user_facing_desc} (Apollo signal) (?)"

        enrichment = render_json.get("enrichment") or {}
        dossier = enrichment.get("dossier") or {}
        current_what = str(dossier.get("what_they_do") or "").strip()
        is_exact_domain_match = apollo.get("status") == "organization_matched"
        if is_exact_domain_match or not current_what or current_what.startswith("To Validate:"):
            dossier["what_they_do"] = apollo_desc_text
            dossier["what_they_do_confidence"] = "likely"
            if is_exact_domain_match:
                dossier["what_they_do_source"] = "apollo_exact_domain"
            enrichment["dossier"] = dossier
            render_json["enrichment"] = enrichment

        current_edesc = str(enrichment.get("description") or "").strip()
        if not current_edesc or current_edesc.startswith("To Validate:"):
            enrichment["description"] = apollo_likely_desc
            render_json["enrichment"] = enrichment

        customer = render_json.get("customer") or {}
        current_cdesc = str(customer.get("description") or "").strip()
        if not current_cdesc or current_cdesc.startswith("To Validate:"):
            customer["description"] = apollo_likely_desc
            render_json["customer"] = customer

        source_status = render_json.get("source_status") or {}
        if source_status.get("company_overview_enrichment") != "usable_results_found":
            source_status["company_overview_enrichment"] = "usable_results_found"
            render_json["source_status"] = source_status

    # Populate dossier.scale_signals AND known["scale_signal"] from Apollo firmographics.
    # Monthly Volume is reserved for API/generation usage volume — do NOT set it here.
    enrichment = render_json.get("enrichment") or {}
    dossier = enrichment.get("dossier") or {}
    scale_signals: list[str] = list(dossier.get("scale_signals") or [])
    emp = org.get("num_employees") or org.get("employee_count")
    if emp and not any("employee" in str(s).lower() for s in scale_signals):
        scale_signals.append(f"~{emp:,} employees (Apollo signal)")
    revenue = org.get("annual_revenue")
    currency = org.get("annual_revenue_currency") or org.get("revenue_currency")
    rev_str = ""
    if revenue and str(revenue).strip() and not any("revenue" in str(s).lower() for s in scale_signals):
        rev_str = _format_apollo_revenue(revenue, currency)
        if rev_str:
            scale_signals.append(f"{rev_str} (Apollo signal)")
    if scale_signals != list(dossier.get("scale_signals") or []):
        dossier["scale_signals"] = scale_signals
        enrichment["dossier"] = dossier
        render_json["enrichment"] = enrichment

    # Build a single composite scale signal string for the Executive Snapshot and Hypothesis sections.
    # Format: "Likely: ~8,000 employees; ~$1.1B annual revenue signal; founded 1999; HQ Amsterdam, Netherlands. (Apollo signal) (?)"
    sig_parts: list[str] = []
    if emp:
        sig_parts.append(f"~{emp:,} employees")
    if rev_str:
        sig_parts.append(rev_str)
    founded = org.get("founded_year")
    if founded:
        sig_parts.append(f"founded {founded}")
    hq_parts = [p for p in [org.get("hq_city") or org.get("city"), org.get("hq_state") or org.get("state"), org.get("hq_country") or org.get("country")] if p]
    if hq_parts:
        sig_parts.append(f"HQ {', '.join(str(p) for p in hq_parts)}")
    if sig_parts:
        known = render_json.get("known") or {}
        if not known.get("scale_signal"):
            known["scale_signal"] = "Likely: " + "; ".join(sig_parts) + ". (Apollo signal) (?)"
            render_json["known"] = known

    # Store the Apollo evidence source string for evidence propagation into question prefill blocks.
    if user_facing_desc:
        input_domain = apollo.get("input_domain") or org.get("primary_domain") or org.get("domain") or ""
        evidence_src = f"Apollo organization enrichment, exact domain match: {input_domain}" if input_domain else "Apollo organization enrichment"
        dossier = (render_json.get("enrichment") or {}).get("dossier") or {}
        if not dossier.get("what_they_do_source"):
            dossier["what_they_do_source"] = evidence_src
            enrichment = render_json.get("enrichment") or {}
            enrichment["dossier"] = dossier
            render_json["enrichment"] = enrichment


def _filter_compatible_search_results(
    search_results: list[dict[str, Any]],
    enrichment: dict[str, Any],
    customer: "CustomerIdentity",
) -> list[dict[str, Any]]:
    """Remove same-name-different-entity web results from the list stored in render_json.

    This ensures that rejected sources (e.g. sportmonks.com when company=Monks/monks.com)
    do not appear in Standard Discovery evidence, Public Intelligence Snapshot, or any
    other section that reads from render_json["search_results"].
    """
    company_name = customer.company_name or enrichment.get("company_name") or customer.canonical_name
    confirmed_domain = customer.domain
    if not company_name or not confirmed_domain:
        return search_results
    return [
        r for r in search_results
        if is_canonical_entity_compatible(
            r.get("url", ""), r.get("title", ""), r.get("snippet", ""),
            company_name, confirmed_domain,
        )
    ]


def context_to_renderer_json(context: PrepContext, args: argparse.Namespace | None = None) -> dict[str, Any]:
    event = context.event or {}
    customer = context.customer
    enrichment = normalize_enrichment(context.enrichment, context)
    run_id = uuid.uuid4().hex
    customer_key = re.sub(r"[^a-z0-9]+", "-", (customer.company_name or enrichment.get("company_name") or customer.canonical_name or customer.domain or "unknown").lower()).strip("-")
    attendees = []
    for attendee in event.get("attendees") or []:
        email = attendee.get("third_party_email") or attendee.get("email") or ""
        attendees.append(
            {
                "name": attendee.get("display_name") or email,
                "email": email,
                "external": bool(attendee.get("is_external") or attendee.get("type") == "third_party"),
            }
        )
    if customer.email and not attendees:
        attendees.append({"name": customer.email, "email": customer.email, "external": True})
    if customer.contact_name and not any(customer.contact_name == attendee.get("name") for attendee in attendees):
        attendees.append({"name": customer.contact_name, "email": "", "external": True, "title": "Contact / stakeholder to validate"})

    meeting = {
        "title": event.get("summary") or "Customer prep",
        "start": lark_time_to_iso(event.get("start_time")),
        "end": lark_time_to_iso(event.get("end_time")),
        "timezone": (event.get("start_time") or {}).get("timezone") or DEFAULT_TIMEZONE,
        "organizer": {"name": (event.get("event_organizer") or {}).get("display_name", ""), "email": ""},
        "sa": {"name": "", "email": ""},
        "url": event.get("app_link") or (event.get("vchat") or {}).get("meeting_url") or "",
    }
    render_json = {
        "meeting": meeting,
        "customer": {
            "name": customer.canonical_name or "<unknown> (please confirm)",
            "contact": customer.contact_name or "",
            "domain": customer.domain or "",
            "website": enrichment.get("website", "") or customer.domain or "",
            "company_name": enrichment.get("company_name", ""),
            "industry": enrichment.get("industry", ""),
            "hq": enrichment.get("hq", ""),
            "company_size": enrichment.get("company_size", ""),
            "description": enrichment.get("description", ""),
            "confidence": "high" if customer.confidence == "confirmed" else customer.confidence,
        },
        "attendees": attendees,
        "enrichment": enrichment,
        "prior_docs": context.prior_docs,
        "prior_notes": [],
        "known": context.known,
        "apollo": context.apollo_enrichment or {},
        "source_status": {
            "calendar": "available" if event else "missing",
            "attendees": "available" if attendees else "missing",
            "mcp": "available" if context.enrichment and context.enrichment.get("source") != "web_search" else "unavailable",
            "prior_docs": "available" if context.prior_docs else "none",
            "docs_search": "available" if context.docs_search_available else "unavailable",
            "web_search": context.web_search_status,
            "company_overview_enrichment": context.company_overview_status,
            "apollo_org": (context.apollo_enrichment or {}).get("status", "disabled"),
            "apollo_people": (context.apollo_enrichment or {}).get("people_status", "not_attempted"),
            "web_rejected_count": (enrichment.get("dossier") or {}).get("rejected_web_count", 0),
            "canonical_identity_source": "apollo_exact_domain" if (context.apollo_enrichment or {}).get("status") in ("organization_matched",) else (
                "explicit_user_url" if context.user_urls and (enrichment or {}).get("source") in ("explicit_user_url",) else (
                    "explicit_url_supplemented" if context.user_urls and context.web_search_status not in ("disabled_by_env", "ran_but_no_results") else (
                        "web_only_fallback" if (context.apollo_enrichment or {}).get("status") == "missing_api_key" else "web_search"
                    )
                )
            ),
            "explicit_url_enrichment": "used" if context.user_urls and (enrichment or {}).get("source") == "explicit_user_url" else ("supplemented" if context.user_urls else "not_used"),
        },
        "run_id": run_id,
        "customer_key": customer_key,
    }
    # Filter search_results to entity-compatible sources only and track rejection count.
    # This prevents rejected same-name-different-entity URLs (e.g. sportmonks.com for Monks)
    # from appearing in Standard Discovery evidence, Public Intelligence, or any renderer section.
    # context.search_results is also updated so that build_question_prefill (called later) uses only
    # compatible sources — preventing rejected URLs from leaking into question evidence fields.
    _original_search_results = list(context.search_results)
    _original_search_count = len(_original_search_results)
    _compatible_results = _filter_compatible_search_results(_original_search_results, enrichment, customer)
    render_json["search_results"] = _compatible_results
    context.search_results = _compatible_results
    _filter_rejected = _original_search_count - len(_compatible_results)
    if _filter_rejected > 0:
        _prior = int(render_json["source_status"].get("web_rejected_count") or 0)
        render_json["source_status"]["web_rejected_count"] = _prior + _filter_rejected
    # Expose rejected domain set so the render layer can do defense-in-depth filtering
    # on dossier fields and any other signal that might reference a rejected entity.
    _compatible_url_set = {r.get("url", "") for r in _compatible_results}
    _rejected_domains: set[str] = set()
    for _r in _original_search_results:
        _u = _r.get("url", "")
        if _u and _u not in _compatible_url_set:
            _h = urlparse(_u).netloc.lower().removeprefix("www.")
            if _h:
                _rejected_domains.add(_h)
    render_json["source_status"]["rejected_domains"] = sorted(_rejected_domains)

    dossier = enrichment.get("dossier") or {}
    registry = build_evidence_registry(dossier, run_id, customer_key, customer.company_name or enrichment.get("company_name") or customer.canonical_name, customer.domain)
    if not registry and dossier.get("what_they_do") and not str(dossier.get("what_they_do")).startswith("To Validate:"):
        source_url = ""
        for item in enrichment.get("source_links") or []:
            source_url = item.get("url") or item.get("label") or ""
            if source_url:
                break
        source_url = source_url or (f"https://{customer.domain}" if customer.domain else "")
        if source_url:
            registry = build_evidence_registry(
                {
                    "source_evidence": [
                        {
                            "claim": dossier["what_they_do"],
                            "url": source_url,
                            "tier": source_tier(source_url, customer.company_name or enrichment.get("company_name") or customer.canonical_name, customer.domain)[0],
                            "tier_label": source_tier(source_url, customer.company_name or enrichment.get("company_name") or customer.canonical_name, customer.domain)[1],
                            "source_classification": "customer_evidence",
                        }
                    ]
                },
                run_id,
                customer_key,
                customer.company_name or enrichment.get("company_name") or customer.canonical_name,
                customer.domain,
            )
    render_json["evidence_registry"] = registry
    if registry:
        dossier["source_evidence"] = registry
        render_json["enrichment"]["dossier"] = dossier
    has_official_overview_claim = any(
        item.get("source_classification") == "customer_evidence"
        and "Tier 1 - official company site" in str(item.get("tier_label") or "")
        and str(item.get("claim") or "").strip()
        and not contains_placeholder(str(item.get("claim") or ""))
        and broad_company_overview_allowed(item.get("url", ""), "", str(item.get("claim") or ""), customer.company_name or customer.canonical_name)
        for item in dossier.get("source_evidence") or []
    )
    if has_official_overview_claim:
        render_json["source_status"]["web_search"] = "usable_results_found"
        render_json["source_status"]["company_overview_enrichment"] = "usable_results_found"
    if customer.domain or (enrichment.get("company_name") and enrichment.get("website")):
        render_json["customer_context"] = {"classification": "confirmed_company"}
    elif event:
        render_json["customer_context"] = {"classification": "event_context"}
    elif dossier.get("candidate_company"):
        render_json["customer_context"] = {"classification": "candidate_company"}
    elif customer.canonical_name:
        render_json["customer_context"] = {"classification": "person_only"}
    else:
        render_json["customer_context"] = {"classification": "unknown"}
    _augment_render_json_from_apollo(render_json, context.apollo_enrichment or {})
    # Pass debug flag through render_json so the render layer can suppress noisy fallbacks
    render_json["debug"] = bool(getattr(args, "debug", False)) if args else False
    if args:
        prompt = load_prospecting_prompt(getattr(args, "prospecting_prompt", None), debug=getattr(args, "debug", False))
        vertical = infer_vertical(context, getattr(args, "industry", None))
        playbook = load_industry_playbook(vertical.get("name"), debug=getattr(args, "debug", False))
        confidence_layers = infer_confidence_layers(context, vertical, getattr(args, "workload", None))
        render_json["vertical"] = vertical
        render_json["confidence_layers"] = confidence_layers
        apply_production_field_guards(render_json, getattr(args, "industry", None) if not getattr(args, "workload", None) else getattr(args, "workload", None))
        _add_vertical_fit_from_apollo(render_json)
        # Use Apollo description for prefill when it's an exact domain match, stripping Likely/signal markers
        _prefill_desc = ""
        if (context.apollo_enrichment or {}).get("status") == "organization_matched":
            _aug_enrichment = render_json.get("enrichment") or {}
            _aug_desc = str(_aug_enrichment.get("description") or "").strip()
            # Strip "Likely: " prefix and " (Apollo signal) (?)" / " (?)" suffix
            _aug_desc = re.sub(r'^Likely:\s*', '', _aug_desc)
            _aug_desc = re.sub(r'\s*\(Apollo signal\)\s*\(\?\)\s*$', '', _aug_desc)
            _aug_desc = re.sub(r'\s*\(\?\)\s*$', '', _aug_desc).strip()
            _prefill_desc = _aug_desc
        questions, omitted, readiness = build_question_prefill(context, vertical, confidence_layers, description_override=_prefill_desc or None)
        if getattr(args, "workload", None):
            render_json["explicit_workload"] = args.workload
        render_json["prospecting"] = {
            "prompt_path": prompt.get("path", ""),
            "prompt_available": prompt.get("available") == "true",
            "playbook_path": playbook.get("path", ""),
            "retained_questions_count": len(questions),
            "omitted_questions_summary": omitted,
            "meeting_readiness_assets": readiness,
        }
        render_json["question_prefill"] = questions
    else:
        vertical = infer_vertical(context, None)
        render_json["vertical"] = vertical
        render_json["confidence_layers"] = infer_confidence_layers(context, vertical, None)
        apply_production_field_guards(render_json, None)
        _add_vertical_fit_from_apollo(render_json)
    return render_json


def claim_type_for_source(item: dict[str, Any]) -> str:
    claim = str(item.get("claim") or "").lower()
    url = str(item.get("url") or "")
    purpose = source_purpose(url, "", claim)
    if purpose == "pricing":
        return "pricing_packaging"
    if purpose in {"developer_docs", "support"}:
        return "active_workload"
    if any(term in claim for term in ("revenue", "employees", "users", "downloads", "paid subscribers", "enterprise customers", "purchase decisions")):
        return "scale_signal"
    if any(term in claim for term in ("founded", "based in", "headquartered", "located in")):
        return "hq_location"
    return "company_overview"


def build_evidence_registry(dossier: dict[str, Any], run_id: str, customer_key: str, company_name: str | None, domain: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in dossier.get("source_evidence") or []:
        claim = normalize_company_overview(str(item.get("claim") or ""), company_name) or str(item.get("claim") or "").strip()
        if not claim or contains_placeholder(claim):
            continue
        claim_type = claim_type_for_source(item)
        key = (claim_type, re.sub(r"\s+", " ", claim).lower())
        if key in seen:
            continue
        seen.add(key)
        url = str(item.get("url") or "")
        tier = item.get("tier")
        tier_label = item.get("tier_label") or source_tier(url, company_name, domain)[1]
        source_purpose_value = source_purpose(url, "", claim)
        row = {
            **item,
            "claim_id": f"{customer_key}-{len(rows)+1:03d}",
            "claim_type": claim_type,
            "claim_text": claim,
            "claim": claim,
            "source_url": url,
            "source_tier": tier if tier is not None else source_tier(url, company_name, domain)[0],
            "source_purpose": source_purpose_value,
            "confidence": "known" if "Tier 1" in str(tier_label) and claim_type == "company_overview" else "likely",
            "run_id": run_id,
            "customer_key": customer_key,
        }
        rows.append(row)
    rows.sort(key=lambda item: (0 if item.get("claim_type") == "company_overview" else 1, item.get("source_tier", 9)))
    return rows[:8]


def field_starts_unavailable(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return not text or text.startswith(("to validate", "not found"))


def apply_production_field_guards(render_json: dict[str, Any], explicit_industry: str | None = None) -> list[str]:
    warnings: list[str] = []
    customer = render_json.get("customer") or {}
    enrichment = render_json.get("enrichment") or {}
    dossier = enrichment.setdefault("dossier", {})
    vertical = render_json.get("vertical") or {}
    context_class = (render_json.get("customer_context") or {}).get("classification")
    weak_identity_case = context_class in {"person_only", "unknown"} and not customer.get("domain")
    current_text = " ".join(
        str(part or "")
        for part in [
            dossier.get("what_they_do"),
            dossier.get("target_users"),
            dossier.get("business_model"),
            customer.get("description"),
            " ".join(str(item) for item in enrichment.get("known_use_cases") or []),
            " ".join(vertical.get("evidence") or []),
        ]
    )
    subtype = dossier.get("vertical_subtype") or infer_vertical_subtype(current_text, vertical.get("name"), explicit_industry)
    allowed_by_vertical = {
        "marketing_adtech": {"agency_marketing_services", "intent_marketing_comparison", "unknown"},
        "ai_video_creative": {"creative_platform", "unknown"},
    }
    allowed_subtypes = allowed_by_vertical.get(vertical.get("name"))
    if allowed_subtypes and subtype.get("name") not in allowed_subtypes:
        subtype = infer_vertical_subtype(current_text, vertical.get("name"), explicit_industry)
    if subtype.get("name") == "unknown" and vertical.get("name") == "ai_video_creative":
        subtype = infer_vertical_subtype("", vertical.get("name"), "ai_video_creative")
    dossier["vertical_subtype"] = subtype
    vertical["subtype"] = subtype
    render_json["vertical"] = vertical

    if weak_identity_case:
        for field in ("target_users", "business_model"):
            if dossier.get(field):
                dossier[field] = compatibility_fallback(field)
                warnings.append(f"downgraded_{field}_weak_identity")
        if dossier.get("what_they_do") and not str(dossier.get("what_they_do")).lower().startswith("to validate"):
            dossier["what_they_do"] = compatibility_fallback("what_they_do")
            warnings.append("downgraded_company_overview_weak_identity")
    else:
        subtype_name = subtype.get("name", "unknown")
        for field in ("what_they_do", "target_users", "business_model"):
            # Skip what_they_do when it comes from an Apollo exact-domain match — it is authoritative
            if field == "what_they_do" and dossier.get("what_they_do_source") == "apollo_exact_domain":
                continue
            field_text = str(dossier.get(field) or "")
            reason = incompatible_field_reason(field_text, subtype_name, False)
            if not reason and vertical.get("name") == "marketing_adtech" and any(term in field_text.lower() for term in ("consumer devices", "hardware sales", "app store", "accessories", "broadcasting", "streaming", "format licensing")):
                reason = "incompatible_with_marketing_adtech"
            if not reason and vertical.get("name") == "ai_video_creative" and any(term in field_text.lower() for term in ("hardware sales", "app store", "intent-marketing", "comparison-platform", "broadcasting", "format licensing")):
                reason = "incompatible_with_ai_video_creative"
            if reason:
                dossier[field] = compatibility_fallback(field)
                warnings.append(f"downgraded_incompatible_{field}")

        if (
            vertical.get("name") == "ai_video_creative"
            and customer.get("domain")
            and field_starts_unavailable(dossier.get("what_they_do"))
        ):
            company = customer.get("company_name") or dossier.get("company") or customer.get("name") or "The company"
            dossier["what_they_do"] = f"{company} appears to be a creative platform for design assets and AI-enabled image/video workflows."
            dossier["what_they_do_confidence"] = "likely"
            subtype = infer_vertical_subtype("", vertical.get("name"), "ai_video_creative")
            dossier["vertical_subtype"] = subtype
            vertical["subtype"] = subtype
            render_json["vertical"] = vertical
            warnings.append("used_explicit_workload_vertical_overview_fallback")

        subtype_name = (dossier.get("vertical_subtype") or {}).get("name", "unknown")
        if subtype_name in VERTICAL_SUBTYPE_TEMPLATES:
            template = VERTICAL_SUBTYPE_TEMPLATES[subtype_name]
            if not dossier.get("target_users") or str(dossier.get("target_users")).startswith("target users/customer segments are not confirmed") or incompatible_field_reason(str(dossier.get("target_users")), subtype_name):
                dossier["target_users"] = template["target_users"]
                warnings.append("filled_target_users_from_current_subtype")
            if not dossier.get("business_model") or str(dossier.get("business_model")).startswith("business model/revenue model is not confirmed") or incompatible_field_reason(str(dossier.get("business_model")), subtype_name):
                dossier["business_model"] = template["business_model"]
                warnings.append("filled_business_model_from_current_subtype")

        if subtype_name == "agency_marketing_services":
            # Always apply canonical agency target_users — the generic condition above only replaces when
            # explicitly incompatible, but "consumers, developers, ecosystem partners" (consumer-tech
            # phrasing) slips through. For confirmed agency subtype, always use the canonical value.
            dossier["target_users"] = VERTICAL_SUBTYPE_TEMPLATES["agency_marketing_services"]["target_users"]
            warnings.append("enforced_target_users_agency")

            modules = list(dossier.get("product_modules") or [])
            # Remove BytePlus AI model product names — these describe BytePlus offerings, not agency service lines
            byteplus_ai_modules = {"API / enterprise plans", "Custom models", "xMatch / GenAI optimization",
                                   "AI image generation", "AI video generation", "Voice/audio generation",
                                   "Background remover", "Upscaler", "Intent marketing platform", "Comparison platforms"}
            modules = [m for m in modules if m not in byteplus_ai_modules]
            if not modules:
                modules = ["marketing services", "creative production", "technology services",
                           "digital media", "data/measurement", "consulting", "campaign/content services"]
            dossier["product_modules"] = modules
            warnings.append("normalized_product_modules_agency")
            # Replace expansion_opportunity with agency-specific directions
            _known = render_json.get("known") or {}
            _known["expansion_opportunity"] = (
                "Possible directions after validation: campaign creative generation, "
                "creative localization, model/API workflow for campaign pipelines, "
                "creative QA / brand safety automation."
            )
            render_json["known"] = _known
            warnings.append("normalized_expansion_opportunity_agency")

    filtered_registry: list[dict[str, Any]] = []
    subtype_name = (dossier.get("vertical_subtype") or {}).get("name", "unknown")
    for row in render_json.get("evidence_registry") or []:
        claim = str(row.get("claim_text") or row.get("claim") or "")
        if row.get("claim_type") == "company_overview" and incompatible_field_reason(claim, subtype_name, weak_identity_case):
            warnings.append("removed_incompatible_evidence_row")
            continue
        filtered_registry.append(row)
    render_json["evidence_registry"] = filtered_registry
    if filtered_registry:
        dossier["source_evidence"] = filtered_registry
    elif dossier.get("source_evidence"):
        dossier["source_evidence"] = []
    enrichment["dossier"] = dossier
    render_json["enrichment"] = enrichment
    if warnings:
        existing = str((render_json.get("source_status") or {}).get("field_validation") or "")
        all_warnings = [existing] if existing else []
        all_warnings.extend(warnings)
        render_json.setdefault("source_status", {})["field_validation"] = "; ".join(dict.fromkeys(all_warnings))
    return warnings


def normalize_enrichment(enrichment: dict[str, Any] | None, context: PrepContext) -> dict[str, Any]:
    if not enrichment:
        return {
            "available": False,
            "confidence": context.customer.confidence,
            "known_use_cases": ["To Validate: customer use case"],
            "known_competitors": [],
            "known_risks": ["Missing confirmed budget, decision maker, timeline, current vendor, and success metrics"],
            "possible_byteplus_fit": [
                {"product": "Seed / Doubao LLM", "reason": "Validate AI workload and model requirements", "confidence": "medium"},
                {"product": "Ark / model platform", "reason": "Validate model evaluation, deployment, and routing needs", "confidence": "medium"},
            ],
            "suggested_questions": [],
            "source_links": [],
        }
    return {
        "available": True,
        "confidence": enrichment.get("confidence") or context.customer.confidence,
        "known_use_cases": enrichment.get("known_use_cases") or enrichment.get("use_cases") or [],
        "known_competitors": enrichment.get("known_competitors") or enrichment.get("competitors") or [],
        "known_risks": enrichment.get("known_risks") or enrichment.get("risks") or [],
        "possible_byteplus_fit": enrichment.get("possible_byteplus_fit") or enrichment.get("recommended_products") or [],
        "suggested_questions": enrichment.get("suggested_questions") or enrichment.get("questions_to_ask") or [],
        "source_links": enrichment.get("source_links") or [],
        "source": enrichment.get("source", ""),
        "company_name": enrichment.get("company_name", ""),
        "dossier": enrichment.get("dossier") or {},
        "page_evidence": enrichment.get("page_evidence") or [],
        "website": enrichment.get("website", ""),
        "industry": enrichment.get("industry", ""),
        "hq": enrichment.get("hq", ""),
        "company_size": enrichment.get("company_size", ""),
        "description": enrichment.get("description", ""),
    }


def doc_title(render_json: dict[str, Any]) -> str:
    customer = render_json.get("customer", {}).get("name") or "<unknown> (please confirm)"
    start = render_json.get("meeting", {}).get("start")
    label = "TBD"
    if start:
        try:
            label = datetime.fromisoformat(start).strftime("%d-%m-%Y")
        except ValueError:
            pass
    return f"BytePlus <> {customer} - {label} - Pre-Meeting Prep"


def write_local_outputs(render_json: dict[str, Any], markdown: str, title: str) -> tuple[Path, Path]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "prep"
    json_path = OUTPUT_ROOT / f"{slug}.json"
    md_path = OUTPUT_ROOT / f"{slug}.md"
    json_path.write_text(json.dumps(render_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown + "\n", encoding="utf-8")
    return json_path, md_path


def validate_rendered_output(render_json: dict[str, Any], markdown: str) -> list[str]:
    warnings: list[str] = []
    forbidden = ["Official company overview", "Generic company overview", "Normalized overview", "Overview unavailable", "To Validate: To Validate", "Known: Known:"]
    for item in forbidden:
        if item in markdown:
            warnings.append(f"output_validation: forbidden text found: {item}")
    layers = render_json.get("confidence_layers") or {}
    if layers.get("active_workload_confidence") in {"unknown", "weak"}:
        if re.search(r"Likely: (Seedance|Seedream|Ark|AI image|AI video|API / enterprise)", markdown):
            warnings.append("output_validation: likely product/workload text found while active workload is not confirmed")
    subtype = ((render_json.get("enrichment") or {}).get("dossier") or {}).get("vertical_subtype") or (render_json.get("vertical") or {}).get("subtype") or {}
    subtype_name = subtype.get("name") if isinstance(subtype, dict) else ""
    context_class = (render_json.get("customer_context") or {}).get("classification")
    weak_identity_case = context_class in {"person_only", "unknown"} and not (render_json.get("customer") or {}).get("domain")
    if subtype_name:
        for label in ("Target Users / Customer Segments", "Business Model / Revenue Model", "What They Do"):
            for match in re.findall(rf"\| {re.escape(label)} \| ([^\n]+)", markdown):
                field_value = match.split(" Follow-up:", 1)[0]
                if incompatible_field_reason(field_value, subtype_name, weak_identity_case):
                    warnings.append(f"field_validation: downgraded_incompatible_{label.lower().replace(' / ', '_').replace(' ', '_')}")
                    break
    def normalize_url_for_validation(value: str) -> str:
        return value.strip().rstrip(".,;)")

    registry_urls = {
        normalize_url_for_validation(str(item.get("source_url") or item.get("url") or ""))
        for item in render_json.get("evidence_registry") or []
    }
    cited_urls = {
        normalize_url_for_validation(url)
        for url in re.findall(r"Evidence: (https?://[^\s|,]+)", markdown)
    }
    confirmed_domain_for_validation = ((render_json.get("customer") or {}).get("domain") or "").lower().removeprefix("www.")
    missing = set()
    for url in cited_urls:
        if not url or url in registry_urls:
            continue
        # Confirmed-domain URLs are inherently valid identity anchors; no registry entry required.
        if confirmed_domain_for_validation:
            url_host = url.lower().split("/")[2].removeprefix("www.") if "://" in url else url.lower().removeprefix("www.").split("/")[0]
            if url_host == confirmed_domain_for_validation or url_host.endswith("." + confirmed_domain_for_validation):
                continue
        missing.add(url)
    if missing:
        warnings.append("output_validation: cited evidence URL missing from registry: " + ", ".join(sorted(missing)[:3]))
    return warnings


def lark_markdown_arg(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
        return f"@{relative.as_posix()}"
    except ValueError:
        return f"@{path}"


def create_or_update_doc(
    *,
    markdown_path: Path,
    title: str,
    existing_doc: dict[str, Any] | None,
    args: argparse.Namespace,
    debug: bool = False,
) -> tuple[str | None, str]:
    if args.dry_run:
        return None, "Lark doc creation skipped because --dry-run was used"
    if getattr(args, "no_create_doc", False):
        return None, "Lark doc creation skipped because --no-create-doc was used"
    fallback_written = markdown_path.exists() and markdown_path.stat().st_size > 0
    markdown_arg = lark_markdown_arg(markdown_path)
    if args.update_existing and existing_doc and existing_doc.get("url"):
        data = run_lark(
            [
                "docs",
                "+update",
                "--doc",
                existing_doc["url"],
                "--markdown",
                markdown_arg,
                "--mode",
                "overwrite",
                "--new-title",
                title,
                "--as",
                "user",
            ],
            debug=debug,
        )
        if data.get("ok"):
            return existing_doc.get("url"), "updated existing doc"
        message = format_lark_error(data, 1)
        status = auth_status(debug=debug)
        diagnostic = [
            "Could not update existing Lark doc; local markdown output created instead.",
            f"Lark CLI auth exists: {'yes' if status else 'no'}",
            f"Likely missing scope: {infer_missing_scope(message) or 'unknown'}",
            "Folder token attempted: none (existing document update)",
            f"Fallback markdown written successfully: {'yes' if fallback_written else 'no'}",
        ]
        return None, "\n".join(diagnostic)

    folder = os.getenv("PREP_DOC_FOLDER_TOKEN") or os.getenv("CUSTOMER_PROFILE_FOLDER_TOKEN")
    cmd = ["docs", "+create", "--title", title, "--markdown", markdown_arg, "--as", "user"]
    if folder:
        cmd[2:2] = ["--folder-token", folder]
    data = run_lark(cmd, debug=debug)
    if data.get("ok"):
        return data.get("data", {}).get("doc_url"), "created Lark doc"
    first_error = format_lark_error(data, 1)
    if folder:
        fallback = run_lark(["docs", "+create", "--title", title, "--markdown", markdown_arg, "--as", "user"], debug=debug)
        if fallback.get("ok"):
            return fallback.get("data", {}).get("doc_url"), "created Lark doc in default space after folder fallback"
        first_error = first_error + " | default-space fallback: " + format_lark_error(fallback, 1)
    status = auth_status(debug=debug)
    diagnostic = [
        "Could not create Lark doc due to missing permission or auth. Local markdown output created instead.",
        f"Lark CLI auth exists: {'yes' if status else 'no'}",
        f"Likely missing scope: {infer_missing_scope(first_error) or 'unknown'}",
        f"Folder token attempted: {mask_token(folder)}",
        f"Fallback markdown written successfully: {'yes' if fallback_written else 'no'}",
    ]
    return None, "\n".join(diagnostic)


def run_mode_label(args: argparse.Namespace) -> str:
    if args.dry_run:
        return "dry_run"
    if getattr(args, "no_create_doc", False):
        return "local_only"
    if args.update_existing:
        return "update_existing"
    return "create_doc"


def lark_doc_creation_status(action: str, doc_url: str | None, args: argparse.Namespace) -> str:
    if args.dry_run:
        return "skipped_dry_run"
    if getattr(args, "no_create_doc", False):
        return "skipped_no_create_doc"
    if doc_url:
        return "updated" if args.update_existing and action.startswith("updated") else "created"
    return "failed"


def valid_lark_open_id(value: str | None) -> bool:
    return bool(value and re.match(r"^ou_[A-Za-z0-9_-]{8,}$", value))


def build_notification_markdown(result: PrepResult) -> str:
    return (
        f"Meeting prep generated.\n\n"
        f"Customer: {result.customer_name or 'Unknown'}\n"
        f"Confidence: {result.confidence}\n"
        f"Doc: {result.doc_url or 'Local markdown fallback'}\n"
        f"Missing context: {', '.join(result.missing_context) if result.missing_context else 'None'}\n"
        f"Next action: Review the prep doc before the meeting."
    )


def notification_command(result: PrepResult, recipient: str) -> tuple[list[str] | None, str | None]:
    if not valid_lark_open_id(recipient):
        return None, "notification skipped: PREP_NOTIFY_USER_ID/authenticated user id must be a Lark open_id like ou_xxx"
    markdown = build_notification_markdown(result).strip()
    if not markdown:
        return None, "notification skipped: message content is empty"
    idempotency_key = f"prep-{re.sub(r'[^a-z0-9]+', '-', result.doc_title.lower())[:80]}"
    return (
        [
            "im",
            "+messages-send",
            "--as",
            "bot",
            "--user-id",
            recipient,
            "--markdown",
            markdown,
            "--idempotency-key",
            idempotency_key,
        ],
        None,
    )


def send_notification(result: PrepResult, context: PrepContext, args: argparse.Namespace, debug: bool = False) -> str:
    if args.dry_run or args.no_notify:
        return "notification skipped"
    recipient = os.getenv("PREP_NOTIFY_USER_ID")
    if not recipient:
        status = auth_status(debug=debug)
        recipient = (status or {}).get("userOpenId")
    if not recipient:
        return "notification skipped: no PREP_NOTIFY_USER_ID and no authenticated user id"
    cmd, warning = notification_command(result, recipient)
    if warning or cmd is None:
        return warning or "notification skipped: invalid payload"
    data = run_lark(cmd, debug=debug)
    if data.get("ok"):
        return "bot IM sent to configured/authenticated user"
    return "notification failed: " + format_lark_error(data, 1)


def process_single(prep_input: PrepInput, args: argparse.Namespace, *, event: dict[str, Any] | None = None) -> PrepResult:
    if prep_input.mode == "event-id" and event is None:
        event = fetch_event(prep_input.value or "", debug=args.debug)
    context = build_context(
        prep_input,
        event=event,
        debug=args.debug,
        no_apollo=getattr(args, "no_apollo", False),
        apollo_refresh=getattr(args, "apollo_refresh", False),
        apollo_debug=getattr(args, "apollo_debug", False),
        apollo_max_people=getattr(args, "apollo_max_people", None),
    )
    _apollo_status = (context.apollo_enrichment or {}).get("status", "disabled")
    if _apollo_status == "missing_api_key" and not getattr(args, "no_apollo", False):
        print(
            "Warning: Apollo API key missing; running web-only fallback. "
            "Identity confidence may be lower. Set APOLLO_API_KEY to enable enrichment.",
            file=sys.stderr,
        )
    render_json = context_to_renderer_json(context, args)
    markdown = render(render_json)
    validation_warnings = validate_rendered_output(render_json, markdown)
    if validation_warnings:
        render_json.setdefault("source_status", {})["output_validation"] = "; ".join(validation_warnings)
        markdown = render(render_json)
    title = doc_title(render_json)
    json_path, md_path = write_local_outputs(render_json, markdown, title)
    debug_log(args.debug, f"wrote local JSON: {json_path}")
    debug_log(args.debug, f"wrote local Markdown: {md_path}")

    existing = choose_existing_doc(context.prior_docs, context.customer.canonical_name)
    doc_url, action = create_or_update_doc(markdown_path=md_path, title=title, existing_doc=existing, args=args, debug=args.debug)
    lark_status = lark_doc_creation_status(action, doc_url, args)
    render_json.setdefault("source_status", {})["lark_doc_creation"] = lark_status
    if doc_url:
        render_json.setdefault("lark_doc", {})["url"] = doc_url
    markdown = render(render_json)
    validation_warnings = validate_rendered_output(render_json, markdown)
    if validation_warnings:
        render_json.setdefault("source_status", {})["output_validation"] = "; ".join(validation_warnings)
        markdown = render(render_json)
    json_path, md_path = write_local_outputs(render_json, markdown, title)
    if doc_url:
        parity = run_lark(["docs", "+update", "--doc", doc_url, "--markdown", lark_markdown_arg(md_path), "--mode", "overwrite", "--new-title", title, "--as", "user"], debug=args.debug)
        if not parity.get("ok"):
            render_json.setdefault("source_status", {})["lark_doc_parity_update"] = "failed"
            markdown = render(render_json)
            json_path, md_path = write_local_outputs(render_json, markdown, title)
    debug_log(args.debug, f"updated local JSON with Lark status: {json_path}")
    debug_log(args.debug, f"updated local Markdown with Lark status: {md_path}")
    missing_context = list(context.missing_context)
    if lark_status == "failed":
        missing_context.append("lark_doc_creation: failed")
    summary_confidence = (
        render_json.get("confidence_layers", {}).get("identity_confidence")
        or context.customer.confidence
    )
    result = PrepResult(
        title,
        doc_url,
        prep_input.mode,
        context.customer.canonical_name,
        summary_confidence,
        missing_context,
        local_json_path=str(json_path),
        local_markdown_path=str(md_path),
        run_mode=run_mode_label(args),
        lark_doc_status=lark_status,
    )
    notify_status = send_notification(result, context, args, debug=args.debug)
    if args.output_json:
        print(json.dumps({"normalized": render_json, "result": asdict(result), "action": action, "notification": notify_status}, indent=2))
    else:
        print_summary(result, action, notify_status, context)
    return result


def print_summary(result: PrepResult, action: str, notify_status: str, context: PrepContext) -> None:
    print("Prep generation completed.")
    print()
    print(f"Customer: {result.customer_name or 'Unknown'}")
    print(f"Confidence: {result.confidence}")
    print(f"Mode: {result.mode}")
    print(f"Lark Doc: {result.doc_url or action}")
    print(f"Local Markdown: {result.local_markdown_path or 'unavailable'}")
    print(f"Local JSON: {result.local_json_path or 'unavailable'}")
    print(f"Run Mode: {result.run_mode or 'unknown'}")
    print(f"Doc action: {action}")
    print(f"Prior docs found: {len(context.prior_docs)}")
    print(f"Notification: {notify_status}")
    if result.lark_doc_status == "failed":
        print("Local fallback was generated successfully")
    if result.missing_context:
        print("Missing context:")
        for item in result.missing_context:
            print(f"- {item}")
    print("Next action:")
    print("- Review the prep doc before the meeting.")


def process_window(prep_input: PrepInput, args: argparse.Namespace) -> list[PrepResult]:
    start, end, tz_name = parse_window(prep_input.window or "")
    debug_log(args.debug, f"window timezone: {tz_name}; start={start.isoformat()} end={end.isoformat()}")
    events = fetch_window_events(start, end, debug=args.debug)
    results: list[PrepResult] = []
    skipped: list[tuple[str, str]] = []
    for event in events:
        qualified, reason = classify_event(event)
        if not qualified:
            skipped.append((event.get("summary") or "Untitled", reason))
            continue
        child_input = PrepInput(mode="window", value=event.get("event_id"), window=prep_input.window)
        results.append(process_single(child_input, args, event=event))
    if not args.output_json:
        print()
        print("Window summary")
        print("| Event | Customer | Confidence | Doc |")
        print("| --- | --- | --- | --- |")
        for result in results:
            print(f"| {result.doc_title} | {result.customer_name or 'Unknown'} | {result.confidence} | {result.doc_url or 'local'} |")
        if skipped:
            print()
            print("Skipped events")
            for title, reason in skipped:
                print(f"- {title}: {reason}")
        if not results:
            print("No qualified customer meetings found.")
    return results


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    prep_input = prep_input_from_args(args)
    try:
        if prep_input.mode == "window":
            process_window(prep_input, args)
        else:
            process_single(prep_input, args)
        return 0
    except PrepError as exc:
        if args.output_json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"Prep run failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
