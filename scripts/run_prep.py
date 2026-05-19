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
    known: dict[str, Any] = field(default_factory=dict)


@dataclass
class PrepResult:
    doc_title: str
    doc_url: str | None
    mode: str
    customer_name: str | None
    confidence: str
    missing_context: list[str]


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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-json", action="store_true")
    parser.add_argument("--create-doc", action="store_true", help="Explicitly allow new doc creation; this is the default outside dry-run.")
    parser.add_argument("--update-existing", action="store_true")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--prospecting-prompt", help="Path to prospecting prompt guidance; defaults to config/prospecting_prompt.md.")
    parser.add_argument("--industry", help="Industry playbook name, e.g. marketing_adtech, ai_video_creative, ecommerce, gaming, enterprise_llm.")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    if not any(getattr(args, field, None) for field in ("event_id", "customer", "domain", "email", "window", "contact", "company")):
        parser.error("one input mode or --contact/--company/--domain is required")
    return args


def prep_input_from_args(args: argparse.Namespace) -> PrepInput:
    if args.contact or args.company:
        return PrepInput(mode="contact-company", value=args.company or args.domain or args.contact, window=None, contact=args.contact or args.customer, company=args.company, domain=args.domain)
    if args.customer and args.domain:
        return PrepInput(mode="contact-company", value=args.company or args.domain, window=None, contact=args.customer, company=args.company, domain=args.domain)
    if args.domain:
        return PrepInput(mode="domain", value=args.domain, window=None, domain=args.domain)
    for mode in ("event_id", "customer", "email", "window"):
        value = getattr(args, mode)
        if value:
            return PrepInput(mode=mode.replace("_", "-"), value=value, window=value if mode == "window" else None)
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
        "affiliate",
        "creative testing",
        "cac",
        "conversion lift",
        "lead quality",
        "acquisition workflow",
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
        "catalog",
        "livestream commerce",
        "review analysis",
        "product search",
        "product discovery",
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
        return {"name": "default", "display_name": "Default / Unknown", "confidence": "weak", "evidence": [f"Weak signal: {matches[0]}"]}
    playbook = load_industry_playbook(best)
    return {
        "name": best,
        "display_name": playbook["display_name"],
        "confidence": confidence,
        "evidence": [f"Matched signal: {item}" for item in sorted(set(matches))[:5]],
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


def build_question_prefill(context: PrepContext, vertical: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    enrichment = context.enrichment or {}
    known = context.known or {}
    name = vertical.get("name") or "default"
    source = first_source_label(context)
    evidence = [source] if source else []
    company_desc = enrichment.get("description") or "customer/company context"
    use_cases = enrichment.get("known_use_cases") or []
    product_fit = enrichment.get("possible_byteplus_fit") or []
    fit_text = "; ".join(f"{item.get('product')}: {item.get('reason')}" for item in product_fit[:3] if item.get("product")) or "Ark / model platform; creative models if workload confirms"

    common = [
        question_item(
            "Standard Discovery Questions",
            "Core business and focus group/user introduction",
            f"Known: {company_desc}" if evidence and enrichment.get("description") else "To Validate: core business and target users.",
            "known" if evidence and enrichment.get("description") else "to_validate",
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

    if name == "marketing_adtech":
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
    elif name == "enterprise_llm":
        vertical_items = [
            question_item("AI Usage & Current Stack", "What AI capabilities are already integrated today?", "To Validate: current AI capabilities and production scope are not confirmed.", "to_validate", "Which workflows are in production: chat, RAG, agents, routing/evaluation, or fine-tuning?", "Clarifies Ark platform fit."),
            question_item("LLM Usage", "Monthly token usage / average request length / peak concurrency?", "Not Found.", "not_found", "What are monthly tokens, peak concurrency, average prompt length, and traffic regions?", "Sizes inference cost and architecture."),
            question_item("Switching Mechanism", "What would make you switch providers?", "To Validate: switching trigger is not confirmed.", "to_validate", "Would you switch for quality, latency, cost, compliance, routing, or operational control?", "Turns discovery into competitive positioning."),
        ]
        omitted = ["Image/video questions collapsed unless multimodal evidence appears.", "Gaming/adtech questions omitted."]
    elif name == "ecommerce":
        vertical_items = [
            question_item("Standard Discovery Questions", "Catalog / SKU scale?", "Not Found.", "not_found", "How many SKUs/listings and regions/languages need AI support?", "Sizes catalog automation opportunity."),
            question_item("Business Scenarios & Use Cases", "Recommendation/search/ranking or product content?", "Likely: ecommerce teams often evaluate listing content, product images, recommendations/search, reviews, and support. (?)", "likely", "Which workflow has the clearest ROI: listings, product images, search/recommendation, reviews, or support?", "Maps workload to Ark/Seedream/LLM fit."),
        ]
        omitted = ["Long-form video questions collapsed unless livestream evidence appears.", "Private deployment omitted unless security evidence appears."]
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
        return [], "Web search disabled by PREP_WEB_SEARCH_DISABLED."
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        debug_log(debug, f"web search failed for {query!r}: {exc}")
        return [], "Web search unavailable in this run."

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
        return [], "Web search returned no usable results."
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
    return [], warnings[0] if warnings else "Web search returned no usable results."


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
    aliases = [compact_company]
    if compact_company == "naturalintelligence":
        aliases.append("naturalint")
    return aliases


def likely_official_web_result(result: dict[str, str], company_name: str | None) -> bool:
    if not company_name:
        return False
    host = urlparse(result.get("url", "")).netloc.lower().removeprefix("www.")
    compact_host = re.sub(r"[^a-z0-9]+", "", host.split(":")[0])
    blocked = ("linkedin.com", "crunchbase.com", "producthunt.com", "trustpilot.com", "youtube.com", "gadinsider.com", "usatoday.com", "compworth.com", "growjo.com", "pitchbook.com", "gorokacoffee.com", "naturalintelligence.info")
    return any(alias in compact_host for alias in company_domain_aliases(company_name)) and not any(item in host for item in blocked)


def verified_related_domain(host: str, company_name: str | None) -> bool:
    normalized = host.lower().removeprefix("www.")
    compact_company = re.sub(r"[^a-z0-9]+", "", (company_name or "").lower())
    if compact_company == "freepik":
        allowed = ("freepik.es", "freepik.com", "support.freepik.com", "magnific.com")
        return normalized == allowed or any(normalized.endswith("." + domain) or normalized == domain for domain in allowed)
    return False


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
    lowered = description.lower()
    weak_page = any(item in lowered for item in ("monetization", "help center", "community", "pricing", "frequently asked"))
    if company_name and (weak_page or not description):
        if use_cases and any("creative" in item or "image" in item or "video" in item for item in use_cases):
            return f"{company_name} appears to be a generative AI creative platform focused on " + ", ".join(use_cases[:3]) + "."
        return ""
    return description


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
    purpose = source_purpose(url, title, snippet)
    if purpose == "company_overview":
        return True
    host = urlparse(url).netloc.lower()
    if company_name and likely_official_web_result({"url": url}, company_name) and urlparse(url).path.strip("/") in {"", "about", "company"}:
        return True
    return False


def select_company_overview_result(results: list[dict[str, str]], company_name: str | None, domain: str | None = None) -> dict[str, str] | None:
    if not company_name:
        return None
    official_broad = [
        item for item in results
        if likely_official_web_result(item, company_name)
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
        if source_tier(url, company_name)[0] <= 3 and company_name.lower() in text:
            trusted_business.append(item)
    return trusted_business[0] if trusted_business else None


def source_tier(url: str, company_name: str | None = None) -> tuple[int, str]:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    official = company_name and likely_official_web_result({"url": url}, company_name)
    verified = verified_related_domain(host, company_name)
    if host.startswith(("docs.", "help.", "support.")) and (official or verified):
        return 1, "Tier 1 - official docs/help"
    if official or verified:
        return 1, "Tier 1 - official company site"
    if any(item in host for item in ("larkoffice.com", "feishu.cn")):
        return 2, "Tier 2 - internal Lark source"
    if any(item in host for item in ("crunchbase.com", "producthunt.com", "linkedin.com")):
        return 3, "Tier 3 - business directory/social profile"
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


def collect_page_evidence(results: list[dict[str, str]], company_name: str | None, debug: bool = False) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    selected: list[dict[str, str]] = []
    official = [item for item in results if likely_official_web_result(item, company_name)]
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


def extract_pricing_tiers(text: str) -> list[str]:
    tiers = []
    for tier in ["Free", "Basic", "Standard", "Ultimate", "Creator", "Enterprise", "Pro", "Team", "Business"]:
        if re.search(rf"\b{re.escape(tier)}\b", text, re.IGNORECASE):
            tiers.append(tier)
    return tiers[:8]


def customer_related_pricing_text(company_name: str | None, enrichment_description: str, web_results: list[dict[str, str]], pages: list[dict[str, Any]]) -> str:
    if not company_name:
        return ""
    blocked_hosts = ("openai.com", "claude.com", "anthropic.com")
    person_company_terms = ("fabien", "siderakis", "lamethodepapier", "la methode papier", "la méthode papier")
    parts = [enrichment_description]
    for item in web_results:
        url = item.get("url", "")
        host = urlparse(url).netloc.lower()
        if any(blocked in host for blocked in blocked_hosts):
            continue
        haystack = f"{item.get('title', '')} {item.get('snippet', '')} {url}".lower()
        if company_name and not likely_official_web_result(item, company_name) and company_name.lower() not in haystack:
            continue
        parts.append(f"{item.get('title', '')} {item.get('snippet', '')}")
    for page in pages:
        url = page.get("url", "")
        host = urlparse(url).netloc.lower()
        if any(blocked in host for blocked in blocked_hosts):
            continue
        haystack = f"{page.get('title', '')} {page.get('snippet', '')} {url}".lower()
        if company_name and not likely_official_web_result({"url": url}, company_name) and company_name.lower() not in haystack and not verified_related_domain(host, company_name):
            continue
        parts.append(page.get("text", ""))
    return " ".join(parts)


def classify_source(url: str, title: str = "", snippet: str = "", company_name: str | None = None, customer_name: str | None = None, candidate_company: str | None = None) -> str:
    text = f"{title} {snippet} {url}".lower()
    host = urlparse(url).netloc.lower()
    if any(item in host for item in ("openai.com", "claude.com", "anthropic.com")):
        return "competitor_reference"
    if company_name and verified_related_domain(host, company_name):
        return "customer_evidence"
    if host.removeprefix("www.").startswith(("docs.", "help.", "support.")) and not (company_name and likely_official_web_result({"url": url}, company_name)):
        return "generic_market_reference"
    if any(item in text for item in ("competitor", "alternative", "alternatives")):
        return "generic_market_reference"
    if "pricing" in text and not (company_name and (likely_official_web_result({"url": url}, company_name) or verified_related_domain(host, company_name))):
        return "generic_market_reference"
    if company_name and (likely_official_web_result({"url": url}, company_name) or company_name.lower() in text):
        return "customer_evidence"
    candidate_terms = [term.lower() for term in [candidate_company or "", customer_name or ""] if term]
    if any(term and term in text for term in candidate_terms):
        return "candidate_entity_evidence"
    if any(item in host for item in ("linkedin.com", "pappers.fr", "societe.com")) and customer_name and customer_name.lower() in text:
        return "candidate_entity_evidence"
    return "generic_market_reference"


def extract_company_dossier(
    company_name: str | None,
    enrichment_description: str,
    use_cases: list[str],
    web_results: list[dict[str, str]],
    pages: list[dict[str, Any]],
    customer_name: str | None = None,
) -> dict[str, Any]:
    combined = " ".join(
        [enrichment_description]
        + [f"{item.get('title', '')} {item.get('snippet', '')}" for item in web_results]
        + [page.get("text", "") for page in pages]
    )
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
        ("API / enterprise plans", ("api", "enterprise")),
    ]
    lowered = combined.lower()
    for label, needles in module_signals:
        if any(needle in lowered for needle in needles):
            modules.append(label)

    pricing_tiers = extract_pricing_tiers(customer_related_pricing_text(company_name, enrichment_description, web_results, pages))
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
        )
        if classification in {"customer_evidence", "candidate_entity_evidence"}:
            trusted_scale_parts.append(f"{item.get('title', '')} {item.get('snippet', '')}")
    for page in pages:
        classification = classify_source(
            page.get("url", ""),
            page.get("title", ""),
            page.get("snippet", ""),
            company_name,
            customer_name,
            candidate_company,
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

    founders = []
    for pattern in [r"founder(?: and CEO)?\s+([A-Z][A-Za-z .'-]{2,60})", r"led by\s+([A-Z][A-Za-z .'-]{2,60})"]:
        for match in re.finditer(pattern, combined):
            value = match.group(1).strip(" .")
            if value and value not in founders:
                founders.append(value)

    hq = ""
    hq_match = re.search(r"(?:located in|based in|location in)\s+([A-Z][A-Za-z ,.-]{2,80})", combined)
    if hq_match:
        hq = re.split(r"\bWho\b|\bWhat\b|\bWhen\b|\bFrequently\b", hq_match.group(1))[0].strip(" .")
    founded_year = ""
    founded_match = re.search(r"(?:est\.?|founded|operating since)\s*(?:in)?\s*(20\d{2}|19\d{2})", combined, re.IGNORECASE)
    if founded_match:
        founded_year = founded_match.group(1)
    creative_signal = any(term in lowered for term in ("image generation", "video generation", "generative ai", "creative platform", "creator", "designers", "ai image", "ai video"))
    marketing_signal = any(term in lowered for term in ("intent marketing", "customer acquisition", "comparison platform", "high-intent consumers"))
    target_users = ""
    if creative_signal:
        target_users = "creators, designers, marketers, agencies, enterprise creative teams, and API developers"
    elif any(term in lowered for term in ("high-intent consumers", "top-tier brands", "advertisers", "publishers")):
        target_users = "high-intent consumers, brand/advertiser partners, and publishers"
    traffic_source_scale = ""
    traffic_terms = []
    for term in ("seo", "sem", "affiliate", "paid social", "partner traffic", "high-intent audiences", "purchase decisions"):
        if term in lowered:
            traffic_terms.append(term)
    if traffic_terms:
        traffic_source_scale = "; ".join(dict.fromkeys(traffic_terms))
    business_model = ""
    if creative_signal and any(term in lowered for term in ("subscription", "credits", "api", "enterprise", "paid subscribers", "pricing")):
        business_model = "subscription, credit, API, and enterprise creative-platform packaging"
    elif marketing_signal or any(term in lowered for term in ("publishers monetize",)):
        business_model = "intent-marketing / comparison-platform model connecting consumers, publishers, and brands"
    social_content_presence = ""
    if any(term in lowered for term in ("paid media", "ad creative", "landing page", "creative testing", "paid social")):
        social_content_presence = "paid media / landing-page creative workflow signal found"
    source_evidence = []
    for item in sorted(web_results[:8], key=lambda x: source_tier(x.get("url", ""), company_name)[0]):
        tier, tier_label = source_tier(item.get("url", ""), company_name)
        classification = classify_source(
            item.get("url", ""),
            item.get("title", ""),
            item.get("snippet", ""),
            company_name,
            customer_name,
            candidate_company,
        )
        source_evidence.append(
            {
                "claim": item.get("snippet") or item.get("title") or item.get("url"),
                "url": item.get("url", ""),
                "tier": tier,
                "tier_label": tier_label,
                "source_classification": classification,
            }
        )
    for page in sorted(pages[:6], key=lambda x: source_tier(x.get("url", ""), company_name)[0]):
        classification = classify_source(
            page.get("url", ""),
            page.get("title", ""),
            page.get("snippet", ""),
            company_name,
            customer_name,
            candidate_company,
        )
        source_evidence.append(
            {
                "claim": page.get("snippet") or page.get("title") or page.get("url"),
                "url": page.get("url", ""),
                "tier": source_tier(page.get("url", ""), company_name)[0],
                "tier_label": source_tier(page.get("url", ""), company_name)[1],
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
        "social_content_presence": social_content_presence,
        "candidate_company": candidate_company,
        "source_evidence": sorted(
            [item for item in source_evidence if item["source_classification"] in {"customer_evidence", "candidate_entity_evidence"}],
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
        (("api", "enterprise", "custom model"), "API or enterprise integration requirements"),
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


def synthesize_known_fields(enrichment: dict[str, Any] | None, docs: list[dict[str, Any]], web_results: list[dict[str, str]]) -> dict[str, Any]:
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
        known["budget_status"] = "Public pricing/packaging found: " + ", ".join(dossier["pricing_tiers"]) + ". Validate current AI infra spend."
    if dossier.get("product_modules"):
        known["expansion_opportunity"] = "Likely product modules: " + ", ".join(dossier["product_modules"][:6])
    return known


def build_web_enrichment(context: PrepContext, debug: bool = False) -> tuple[dict[str, Any] | None, list[dict[str, str]], str | None]:
    customer = context.customer
    inferred_company = customer.company_name or (domain_to_name(customer.domain) if customer.domain else None) or infer_company_from_docs(customer.canonical_name, context.prior_docs)
    queries = expand_web_queries(customer, inferred_company)
    if not queries:
        return None, [], "Web search skipped because customer identity is unknown."
    results, warning = collect_web_results(queries, debug=debug)
    if not results:
        return None, [], warning
    scored_results = sorted(
        ((contextual_web_score(item, customer.canonical_name, inferred_company), item) for item in results),
        key=lambda pair: pair[0],
        reverse=True,
    )
    filtered_results = [item for score, item in scored_results if score > 0]
    results = (filtered_results or [item for _, item in scored_results])[:12]
    page_evidence = collect_page_evidence(results, inferred_company, debug=debug)

    preferred = results[0]
    for item in results:
        haystack = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        if customer.canonical_name and inferred_company and customer.canonical_name.lower() in haystack and inferred_company.lower() in haystack:
            preferred = item
            break
    else:
        preferred = max(results, key=product_description_score)
    for item in results:
        if likely_official_web_result(item, inferred_company):
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
            if host and likely_official_web_result(item, inferred_company) and not blocked_as_company_website(host):
                website = stable_company_website(host)
                break
    combined = " ".join((item.get("title", "") + " " + item.get("snippet", "")).lower() for item in results)
    use_cases = infer_use_cases(combined)
    if any(term in combined for term in ("creative", "generation", "artificial intelligence")) and not use_cases:
        use_cases.append("creative AI / generative media workflow")
    description = stable_company_description(inferred_company, description, use_cases)
    dossier = extract_company_dossier(inferred_company, description, use_cases, results, page_evidence, customer.canonical_name)
    trusted_source_results = [
        item for item in results
        if classify_source(
            item.get("url", ""),
            item.get("title", ""),
            item.get("snippet", ""),
            inferred_company,
            customer.canonical_name,
            dossier.get("candidate_company"),
        ) in {"customer_evidence", "candidate_entity_evidence"}
    ]
    trusted_page_links = [
        {"label": item.get("title") or item.get("url", ""), "url": item.get("url", "")}
        for item in page_evidence
        if classify_source(item.get("url", ""), item.get("title", ""), item.get("snippet", ""), inferred_company, customer.canonical_name, dossier.get("candidate_company")) in {"customer_evidence", "candidate_entity_evidence"}
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
    mcp_enrichment = call_mcp_enrichment(context, debug=debug)
    web_enrichment, web_results, web_warning = build_web_enrichment(context, debug=debug)
    context.search_results = web_results
    context.web_search_available = bool(web_results)
    context.enrichment = mcp_enrichment or web_enrichment
    context.known = synthesize_known_fields(context.enrichment, context.prior_docs, context.search_results)
    if web_warning:
        context.missing_context.append(web_warning)
    if mcp_enrichment is None:
        context.missing_context.append("MCP enrichment unavailable")
    return context


def context_to_renderer_json(context: PrepContext, args: argparse.Namespace | None = None) -> dict[str, Any]:
    event = context.event or {}
    customer = context.customer
    enrichment = normalize_enrichment(context.enrichment, context)
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
        "search_results": context.search_results,
        "known": context.known,
        "source_status": {
            "calendar": "available" if event else "missing",
            "attendees": "available" if attendees else "missing",
            "mcp": "available" if context.enrichment and context.enrichment.get("source") != "web_search" else "unavailable",
            "prior_docs": "available" if context.prior_docs else "none",
            "docs_search": "available" if context.docs_search_available else "unavailable",
            "web_search": "available" if context.web_search_available else "unavailable",
        },
    }
    dossier = enrichment.get("dossier") or {}
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
    if args:
        prompt = load_prospecting_prompt(getattr(args, "prospecting_prompt", None), debug=getattr(args, "debug", False))
        vertical = infer_vertical(context, getattr(args, "industry", None))
        playbook = load_industry_playbook(vertical.get("name"), debug=getattr(args, "debug", False))
        questions, omitted, readiness = build_question_prefill(context, vertical)
        render_json["vertical"] = vertical
        render_json["prospecting"] = {
            "prompt_path": prompt.get("path", ""),
            "prompt_available": prompt.get("available") == "true",
            "playbook_path": playbook.get("path", ""),
            "retained_questions_count": len(questions),
            "omitted_questions_summary": omitted,
            "meeting_readiness_assets": readiness,
        }
        render_json["question_prefill"] = questions
    return render_json


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
        return None, "dry-run: no Lark write"
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
    context = build_context(prep_input, event=event, debug=args.debug)
    render_json = context_to_renderer_json(context, args)
    markdown = render(render_json)
    title = doc_title(render_json)
    json_path, md_path = write_local_outputs(render_json, markdown, title)
    debug_log(args.debug, f"wrote local JSON: {json_path}")
    debug_log(args.debug, f"wrote local Markdown: {md_path}")

    existing = choose_existing_doc(context.prior_docs, context.customer.canonical_name)
    doc_url, action = create_or_update_doc(markdown_path=md_path, title=title, existing_doc=existing, args=args, debug=args.debug)
    result = PrepResult(title, doc_url, prep_input.mode, context.customer.canonical_name, context.customer.confidence, context.missing_context)
    notify_status = send_notification(result, context, args, debug=args.debug)
    if args.output_json:
        print(json.dumps({"normalized": render_json, "result": asdict(result), "action": action, "notification": notify_status}, indent=2))
    else:
        print_summary(result, action, notify_status, context)
    return result


def print_summary(result: PrepResult, action: str, notify_status: str, context: PrepContext) -> None:
    print("Meeting prep generated.")
    print()
    print(f"Customer: {result.customer_name or 'Unknown'}")
    print(f"Confidence: {result.confidence}")
    print(f"Mode: {result.mode}")
    print(f"Doc: {result.doc_url or 'Local markdown fallback'}")
    print(f"Doc action: {action}")
    print(f"Prior docs found: {len(context.prior_docs)}")
    print(f"Notification: {notify_status}")
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
