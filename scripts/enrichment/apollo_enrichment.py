#!/usr/bin/env python3
"""Apollo.io enrichment for BytePlus pre-meeting customer profile.

Provides company firmographic and stakeholder data for small, niche, or
ambiguous companies that are underserved by generic web search.

Security rules (non-negotiable):
- API key is never logged, printed, or stored in generated docs.
- Personal emails and phone numbers are not revealed by default.
- Apollo results are never promoted to Known; confidence stays Likely.
- Domain guard: if Apollo returns a different domain, result is immediately
  rejected with status=rejected_due_to_domain_mismatch and NOT used.
- Waterfall enrichment is disabled by default.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


APOLLO_API_BASE = "https://api.apollo.io/v1"
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "prep_apollo"

# Title buckets for vertical-aware stakeholder search
_TITLE_BUCKETS: dict[str, list[str]] = {
    "marketing_adtech": [
        "CTO", "VP Engineering", "Head of Engineering", "Chief Technology Officer",
        "VP Product", "Head of Product", "CPO",
        "VP Marketing", "CMO", "Head of Growth",
        "CEO", "Co-founder", "Founder",
    ],
    "ai_video_creative": [
        "CTO", "VP Engineering", "Head of AI", "ML Engineer",
        "Head of Product", "VP Product",
        "CEO", "Co-founder", "Founder",
    ],
    "enterprise_llm": [
        "CTO", "VP Engineering", "Head of AI", "Head of ML",
        "Enterprise Architect", "VP Infrastructure",
        "CEO", "Co-founder",
    ],
    "ecommerce": [
        "CTO", "VP Engineering", "Head of Technology",
        "VP Product", "Head of Product",
        "CEO", "Co-founder",
    ],
    "gaming": [
        "CTO", "VP Engineering", "Technical Director",
        "Head of Product", "VP Product",
        "CEO", "Studio Head",
    ],
    "default": [
        "CTO", "VP Engineering", "Head of Engineering",
        "VP Product", "Head of Product",
        "CEO", "Co-founder", "Founder",
    ],
}


@dataclass
class ApolloOrganizationProfile:
    name: str = ""
    domain: str = ""
    linkedin_url: str = ""
    website_url: str = ""
    short_description: str = ""
    industry: str = ""
    keywords: list[str] = field(default_factory=list)
    employee_count: int | None = None
    estimated_num_employees: int | None = None
    annual_revenue: str = ""
    founded_year: int | None = None
    hq_city: str = ""
    hq_state: str = ""
    hq_country: str = ""
    technologies: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApolloPersonCandidate:
    name: str = ""
    title: str = ""
    linkedin_url: str = ""
    seniority: str = ""
    department: str = ""
    why_relevant: str = ""
    source: str = "Apollo"


@dataclass
class ApolloEnrichmentResult:
    status: str = "disabled"
    confidence: str = "none"
    organization: ApolloOrganizationProfile | None = None
    people: list[ApolloPersonCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cache_hit: bool = False
    input_domain: str = ""
    input_name: str = ""
    people_status: str = "not_attempted"


def _mask_key(text: str, key: str | None) -> str:
    if not key or not text:
        return text
    return text.replace(key, "***REDACTED***")


def _map_apollo_error(error: str | None) -> str:
    """Map internal Apollo error strings to safe, user-facing status codes."""
    if not error:
        return "request_failed"
    if error == "rate_limited":
        return "rate_limited_429"
    if error == "apollo_auth_error_401":
        return "auth_failed_401"
    if error == "apollo_auth_error_403":
        return "forbidden_403"
    if error == "apollo_timeout":
        return "timeout"
    if error == "apollo_org_enrich_422":
        return "org_enrich_invalid_request_422"
    if error.startswith("apollo_network_error"):
        msg = error.lower()
        if "timeout" in msg or "timed out" in msg:
            return "timeout"
        return "network_error"
    if error == "apollo_invalid_json":
        return "invalid_response"
    if error == "apollo_max_retries":
        return "network_error"
    if error.startswith("apollo_http_"):
        code = error.removeprefix("apollo_http_")
        return f"http_error_{code}"
    if error == "not_found":
        return "organization_not_found"
    return "request_failed"


def _cache_key(endpoint: str, params: dict[str, Any]) -> str:
    clean = {k: v for k, v in params.items() if k != "api_key"}
    payload = json.dumps({"endpoint": endpoint, "params": clean}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def _read_cache(key: str, ttl_hours: float) -> dict[str, Any] | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        written_at = data.get("_cache_written_at", 0)
        if time.time() - written_at > ttl_hours * 3600:
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(key: str, data: dict[str, Any]) -> None:
    path = _cache_path(key)
    try:
        to_store = dict(data)
        to_store["_cache_written_at"] = time.time()
        path.write_text(json.dumps(to_store, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _safe_response_excerpt(exc: urllib.error.HTTPError, api_key: str) -> str:
    """Read up to 400 chars of a 4xx response body, redacting the API key."""
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        return _mask_key(raw[:400], api_key)
    except Exception:
        return "(body unreadable)"


def _apollo_get(
    endpoint: str,
    params: dict[str, Any],
    api_key: str,
    ttl_hours: float = 24.0,
    refresh: bool = False,
    debug: bool = False,
) -> tuple[dict[str, Any] | None, bool, str | None]:
    """GET /v1/<endpoint> with api_key in X-Api-Key header, domain as query param.

    Returns (data, cache_hit, error_code).
    The api_key is never printed in debug output or error messages.
    Content-Type is intentionally omitted — GET has no body.
    """
    cache_key = _cache_key(endpoint, params)
    if not refresh:
        cached = _read_cache(cache_key, ttl_hours)
        if cached is not None:
            if debug:
                print(f"[apollo] cache hit: endpoint={endpoint} method=GET", file=sys.stderr)
            return cached, True, None

    # api_key goes in header, not in URL — keeps key out of server logs
    query_string = urllib.parse.urlencode(params)
    url = f"{APOLLO_API_BASE}/{endpoint}?{query_string}"
    param_keys = list(params.keys())

    if debug:
        print(
            f"[apollo] request: endpoint={endpoint} method=GET "
            f"param_keys={param_keys} domain={params.get('domain', 'N/A')}",
            file=sys.stderr,
        )

    req = urllib.request.Request(
        url,
        headers={"X-Api-Key": api_key, "Cache-Control": "no-cache"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                _write_cache(cache_key, data)
                if debug:
                    print(f"[apollo] success: endpoint={endpoint} method=GET status=200", file=sys.stderr)
                return data, False, None
        except urllib.error.HTTPError as exc:
            excerpt = _safe_response_excerpt(exc, api_key)
            if debug:
                print(
                    f"[apollo] http error: endpoint={endpoint} method=GET "
                    f"status={exc.code} attempt={attempt+1} "
                    f"response_excerpt={excerpt!r}",
                    file=sys.stderr,
                )
            if exc.code == 429:
                retry_after = int(exc.headers.get("Retry-After", "5"))
                if attempt < 2:
                    time.sleep(min(retry_after, 30))
                    continue
                return None, False, "rate_limited"
            if exc.code in (401, 403):
                return None, False, f"apollo_auth_error_{exc.code}"
            if exc.code >= 500 and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            return None, False, f"apollo_http_{exc.code}"
        except (urllib.error.URLError, TimeoutError) as exc:
            safe_msg = _mask_key(str(exc), api_key)
            is_timeout = isinstance(exc, TimeoutError) or "timed out" in safe_msg.lower()
            if debug:
                err_type = "timeout" if is_timeout else "network_error"
                print(f"[apollo] {err_type}: endpoint={endpoint} method=GET attempt={attempt+1}", file=sys.stderr)
            if attempt < 2:
                time.sleep(1)
                continue
            return None, False, "apollo_timeout" if is_timeout else f"apollo_network_error: {safe_msg}"
        except json.JSONDecodeError:
            if debug:
                print(f"[apollo] invalid json: endpoint={endpoint} method=GET", file=sys.stderr)
            return None, False, "apollo_invalid_json"
    return None, False, "apollo_max_retries"


def _apollo_post(
    endpoint: str,
    payload: dict[str, Any],
    api_key: str,
    ttl_hours: float = 24.0,
    refresh: bool = False,
    debug: bool = False,
) -> tuple[dict[str, Any] | None, bool, str | None]:
    """POST /v1/<endpoint> with api_key in X-Api-Key header, payload as JSON body.

    The api_key is never printed in error messages or debug output.
    """
    cache_key = _cache_key(endpoint, payload)
    if not refresh:
        cached = _read_cache(cache_key, ttl_hours)
        if cached is not None:
            if debug:
                print(f"[apollo] cache hit: endpoint={endpoint} method=POST", file=sys.stderr)
            return cached, True, None

    # api_key goes in header, not in body — keeps key out of JSON payload
    body_payload = {k: v for k, v in payload.items() if k != "api_key"}
    body_keys = list(body_payload.keys())
    body_bytes = json.dumps(body_payload).encode("utf-8")
    url = f"{APOLLO_API_BASE}/{endpoint}"

    if debug:
        print(
            f"[apollo] request: endpoint={endpoint} method=POST body_keys={body_keys}",
            file=sys.stderr,
        )

    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
        method="POST",
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                _write_cache(cache_key, data)
                if debug:
                    print(f"[apollo] success: endpoint={endpoint} method=POST status=200", file=sys.stderr)
                return data, False, None
        except urllib.error.HTTPError as exc:
            excerpt = _safe_response_excerpt(exc, api_key)
            if debug:
                print(
                    f"[apollo] http error: endpoint={endpoint} method=POST "
                    f"status={exc.code} attempt={attempt+1} "
                    f"response_excerpt={excerpt!r}",
                    file=sys.stderr,
                )
            if exc.code == 429:
                retry_after = int(exc.headers.get("Retry-After", "5"))
                if attempt < 2:
                    time.sleep(min(retry_after, 30))
                    continue
                return None, False, "rate_limited"
            if exc.code in (401, 403):
                return None, False, f"apollo_auth_error_{exc.code}"
            if exc.code >= 500 and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            return None, False, f"apollo_http_{exc.code}"
        except (urllib.error.URLError, TimeoutError) as exc:
            safe_msg = _mask_key(str(exc), api_key)
            is_timeout = isinstance(exc, TimeoutError) or "timed out" in safe_msg.lower()
            if debug:
                err_type = "timeout" if is_timeout else "network_error"
                print(f"[apollo] {err_type} (POST): endpoint={endpoint} attempt={attempt+1}", file=sys.stderr)
            if attempt < 2:
                time.sleep(1)
                continue
            return None, False, "apollo_timeout" if is_timeout else f"apollo_network_error: {safe_msg}"
        except json.JSONDecodeError:
            if debug:
                print(f"[apollo] invalid json (POST): endpoint={endpoint}", file=sys.stderr)
            return None, False, "apollo_invalid_json"
    return None, False, "apollo_max_retries"


def _normalize_domain(domain: str | None) -> str:
    if not domain:
        return ""
    d = domain.lower().strip().removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return d.split("/")[0].split("?")[0]


def _domain_matches(d1: str | None, d2: str | None) -> bool:
    return bool(d1 and d2 and _normalize_domain(d1) == _normalize_domain(d2))


def _parse_org(raw_org: dict[str, Any]) -> ApolloOrganizationProfile:
    technologies = [t for t in (raw_org.get("technology_names") or []) if isinstance(t, str)]
    keywords = [k for k in (raw_org.get("keywords") or []) if isinstance(k, str)]
    hq_city = str(raw_org.get("city") or "")
    hq_state = str(raw_org.get("state") or "")
    hq_country = str(raw_org.get("country") or "")
    employee_count: int | None = None
    if isinstance(raw_org.get("num_employees"), int):
        employee_count = raw_org["num_employees"]
    estimated: int | None = None
    if isinstance(raw_org.get("estimated_num_employees"), int):
        estimated = raw_org["estimated_num_employees"]
    revenue = str(raw_org.get("annual_revenue") or raw_org.get("annual_revenue_printed") or "")
    founded: int | None = None
    if isinstance(raw_org.get("founded_year"), int):
        founded = raw_org["founded_year"]
    return ApolloOrganizationProfile(
        name=str(raw_org.get("name") or ""),
        domain=_normalize_domain(raw_org.get("primary_domain") or raw_org.get("website_url") or ""),
        linkedin_url=str(raw_org.get("linkedin_url") or ""),
        website_url=str(raw_org.get("website_url") or ""),
        short_description=str(raw_org.get("short_description") or ""),
        industry=str(raw_org.get("industry") or ""),
        keywords=keywords[:10],
        employee_count=employee_count,
        estimated_num_employees=estimated,
        annual_revenue=revenue,
        founded_year=founded,
        hq_city=hq_city,
        hq_state=hq_state,
        hq_country=hq_country,
        technologies=technologies[:15],
        raw=raw_org,
    )


def _enrich_org_by_domain(
    domain: str,
    api_key: str,
    ttl_hours: float,
    refresh: bool,
    debug: bool,
) -> tuple[ApolloOrganizationProfile | None, bool, str | None]:
    data, cache_hit, error = _apollo_get(
        "organizations/enrich",
        {"domain": domain},
        api_key,
        ttl_hours=ttl_hours,
        refresh=refresh,
        debug=debug,
    )
    if error:
        # 422 from org enrichment gets a distinct status so people search is
        # explicitly skipped and the Run Report shows a clear reason.
        if error == "apollo_http_422":
            return None, cache_hit, "apollo_org_enrich_422"
        return None, cache_hit, error
    org_raw = (data or {}).get("organization") or {}
    if not org_raw:
        return None, cache_hit, "not_found"
    return _parse_org(org_raw), cache_hit, None


def _search_org_by_name(
    name: str,
    domain_hint: str | None,
    api_key: str,
    ttl_hours: float,
    refresh: bool,
    debug: bool,
) -> tuple[ApolloOrganizationProfile | None, bool, str | None]:
    payload: dict[str, Any] = {
        "q_organization_name": name,
        "page": 1,
        "per_page": 5,
    }
    if domain_hint:
        payload["q_organization_domains"] = [domain_hint]
    data, cache_hit, error = _apollo_post(
        "mixed_companies/search",
        payload,
        api_key,
        ttl_hours=ttl_hours,
        refresh=refresh,
        debug=debug,
    )
    if error:
        return None, cache_hit, error
    organizations = (data or {}).get("organizations") or []
    if not organizations:
        return None, cache_hit, "not_found"
    return _parse_org(organizations[0]), cache_hit, None


def _search_people(
    org_id: str | None,
    domain: str | None,
    vertical: str | None,
    max_people: int,
    api_key: str,
    ttl_hours: float,
    refresh: bool,
    debug: bool,
) -> tuple[list[ApolloPersonCandidate], str]:
    if not org_id and not domain:
        return [], "not_attempted"
    bucket_key = vertical if vertical in _TITLE_BUCKETS else "default"
    titles = _TITLE_BUCKETS[bucket_key]
    payload: dict[str, Any] = {
        "person_titles": titles[:8],
        "page": 1,
        "per_page": min(max_people, 10),
    }
    if org_id:
        payload["organization_ids"] = [org_id]
    elif domain:
        payload["q_organization_domains"] = [domain]

    data, _cache_hit, error = _apollo_post(
        "mixed_people/search",
        payload,
        api_key,
        ttl_hours=ttl_hours,
        refresh=refresh,
        debug=debug,
    )
    if error or not data:
        mapped = _map_apollo_error(error) if error else "no_data"
        return [], mapped
    reveal_emails = os.getenv("APOLLO_REVEAL_EMAILS", "0").strip() == "1"
    results: list[ApolloPersonCandidate] = []
    for person in (data.get("people") or [])[:max_people]:
        name = str(person.get("name") or "").strip()
        if not name:
            continue
        title = str(person.get("title") or "").strip()
        linkedin = str(person.get("linkedin_url") or "") if reveal_emails else ""
        results.append(ApolloPersonCandidate(
            name=name,
            title=title,
            linkedin_url=linkedin,
            seniority=str(person.get("seniority") or ""),
            department=str(person.get("department") or ""),
            why_relevant=_why_relevant(title, bucket_key),
            source="Apollo",
        ))
    status = "people_found" if results else "no_people_found"
    return results, status


def _why_relevant(title: str, vertical: str) -> str:
    title_lower = title.lower()
    if any(t in title_lower for t in ("cto", "chief technology", "vp engineering", "head of engineering")):
        return "Technical decision maker — evaluate model quality, API integration, and infrastructure"
    if any(t in title_lower for t in ("ceo", "chief executive", "founder", "co-founder")):
        return "Executive sponsor — budget authority and strategic direction"
    if any(t in title_lower for t in ("cpo", "vp product", "head of product", "chief product")):
        return "Product owner — defines use case requirements and success criteria"
    if any(t in title_lower for t in ("cmo", "vp marketing", "head of marketing", "head of growth")):
        return "Marketing/growth owner — conversion, acquisition, and creative workloads"
    if any(t in title_lower for t in ("head of ai", "head of ml", "ai engineer", "ml engineer")):
        return "AI/ML technical owner — model evaluation and integration"
    return "Potential stakeholder — validate role and buying authority"


def enrich_with_apollo(
    customer_identity: Any,
    prep_input: Any = None,
    event: dict[str, Any] | None = None,
    vertical_name: str | None = None,
    apollo_max_people: int | None = None,
    *,
    apollo_refresh: bool = False,
    debug: bool = False,
) -> ApolloEnrichmentResult:
    """Main Apollo enrichment entry point.

    Source priority: domain-exact first, name search fallback.
    Domain guard: if Apollo returns a different domain, result is rejected
    immediately with status=rejected_due_to_domain_mismatch.
    Never raises; returns degraded result on any error.
    """
    api_key = os.getenv("APOLLO_API_KEY", "").strip()
    if not api_key:
        return ApolloEnrichmentResult(status="missing_api_key")

    ttl_hours = float(os.getenv("APOLLO_CACHE_TTL_HOURS", "24"))
    max_people = apollo_max_people if apollo_max_people is not None else int(os.getenv("APOLLO_MAX_PEOPLE", "5"))

    input_domain = _normalize_domain(getattr(customer_identity, "domain", None) or "")
    input_name = (
        getattr(customer_identity, "company_name", None)
        or getattr(customer_identity, "canonical_name", None)
        or ""
    )

    if not input_domain and not input_name:
        return ApolloEnrichmentResult(
            status="no_input_domain_or_name",
            input_domain=input_domain,
            input_name=input_name,
        )

    result = ApolloEnrichmentResult(input_domain=input_domain, input_name=input_name)
    org: ApolloOrganizationProfile | None = None
    cache_hit = False

    # Step 1: domain-exact enrichment (highest confidence)
    if input_domain:
        if debug:
            print(f"[apollo] step1 domain enrichment: endpoint=organizations/enrich domain={input_domain}", file=sys.stderr)
        org, cache_hit, error = _enrich_org_by_domain(input_domain, api_key, ttl_hours, apollo_refresh, debug)
        if error and error != "not_found":
            mapped = _map_apollo_error(error)
            if debug:
                print(f"[apollo] step1 failed: endpoint=organizations/enrich reason={mapped}", file=sys.stderr)
            result.status = mapped
            result.warnings.append(f"Apollo domain enrichment: {mapped}")
            return result
        if org:
            apollo_domain = org.domain
            if apollo_domain and not _domain_matches(apollo_domain, input_domain):
                if debug:
                    print(
                        f"[apollo] domain guard: input_domain={input_domain} "
                        f"apollo_returned_domain={apollo_domain} "
                        f"reason=rejected_due_to_domain_mismatch",
                        file=sys.stderr,
                    )
                result.status = "rejected_due_to_domain_mismatch"
                result.confidence = "none"
                result.warnings.append(
                    f"Apollo returned domain '{apollo_domain}' for input domain '{input_domain}'. "
                    "Organization rejected to protect customer identity."
                )
                return result
            if debug:
                print(
                    f"[apollo] domain matched: input_domain={input_domain} "
                    f"apollo_domain={apollo_domain or 'N/A'} confidence=high_domain_exact",
                    file=sys.stderr,
                )
            result.confidence = "high_domain_exact"
            result.cache_hit = cache_hit

    # Step 2: name search fallback (only when domain lookup returned nothing)
    if org is None and input_name:
        if debug:
            print(
                f"[apollo] step2 name search: endpoint=mixed_companies/search "
                f"name={input_name!r} domain_hint={input_domain or 'none'}",
                file=sys.stderr,
            )
        org, cache_hit, error = _search_org_by_name(
            input_name, input_domain or None, api_key, ttl_hours, apollo_refresh, debug
        )
        if error and error != "not_found":
            mapped = _map_apollo_error(error)
            if debug:
                print(f"[apollo] step2 failed: endpoint=mixed_companies/search reason={mapped}", file=sys.stderr)
            result.status = mapped
            result.warnings.append(f"Apollo name search: {mapped}")
            return result
        if org:
            apollo_domain = org.domain
            if input_domain and apollo_domain and not _domain_matches(apollo_domain, input_domain):
                if debug:
                    print(
                        f"[apollo] domain guard (name search): input_domain={input_domain} "
                        f"apollo_returned_domain={apollo_domain} "
                        f"reason=rejected_due_to_domain_mismatch",
                        file=sys.stderr,
                    )
                result.status = "rejected_due_to_domain_mismatch"
                result.confidence = "none"
                result.warnings.append(
                    f"Apollo name search returned domain '{apollo_domain}' which differs from "
                    f"input domain '{input_domain}'. Organization rejected to protect customer identity."
                )
                return result
            result.confidence = "medium_name_and_domain_match" if input_domain else "low_name_only"
            result.cache_hit = cache_hit
            if debug:
                print(
                    f"[apollo] name search matched: name={org.name!r} "
                    f"apollo_domain={apollo_domain or 'N/A'} confidence={result.confidence}",
                    file=sys.stderr,
                )

    if org is None:
        result.status = "organization_not_found"
        if debug:
            print(f"[apollo] not found: domain={input_domain!r} name={input_name!r}", file=sys.stderr)
        return result

    result.organization = org
    result.status = "organization_matched"
    if debug:
        print(
            f"[apollo] organization matched: name={org.name!r} domain={org.domain!r} "
            f"employees={org.employee_count} confidence={result.confidence}",
            file=sys.stderr,
        )

    # People search (only for sufficiently confident matches)
    if result.confidence in ("high_domain_exact", "medium_name_and_domain_match") and max_people > 0:
        org_id = str(org.raw.get("id") or org.raw.get("organization_id") or "")
        result.people, result.people_status = _search_people(
            org_id=org_id or None,
            domain=input_domain or org.domain or None,
            vertical=vertical_name,
            max_people=max_people,
            api_key=api_key,
            ttl_hours=ttl_hours,
            refresh=apollo_refresh,
            debug=debug,
        )

    return result


def apollo_result_to_dict(result: ApolloEnrichmentResult) -> dict[str, Any]:
    """Serialize ApolloEnrichmentResult to a plain dict safe for JSON.

    Strips the raw Apollo response (may contain sensitive data) and
    never exposes personal contact data unless explicitly enabled.
    """
    reveal_emails = os.getenv("APOLLO_REVEAL_EMAILS", "0").strip() == "1"

    org_dict: dict[str, Any] | None = None
    if result.organization:
        org = result.organization
        org_dict = {
            "name": org.name,
            "domain": org.domain,
            "linkedin_url": org.linkedin_url,
            "website_url": org.website_url,
            "short_description": org.short_description,
            "industry": org.industry,
            "keywords": org.keywords,
            "employee_count": org.employee_count,
            "estimated_num_employees": org.estimated_num_employees,
            "annual_revenue": org.annual_revenue,
            "founded_year": org.founded_year,
            "hq_city": org.hq_city,
            "hq_state": org.hq_state,
            "hq_country": org.hq_country,
            "technologies": org.technologies,
        }

    people_list: list[dict[str, Any]] = []
    for person in result.people:
        entry: dict[str, Any] = {
            "name": person.name,
            "title": person.title,
            "seniority": person.seniority,
            "department": person.department,
            "why_relevant": person.why_relevant,
            "source": person.source,
        }
        if reveal_emails and person.linkedin_url:
            entry["linkedin_url"] = person.linkedin_url
        people_list.append(entry)

    return {
        "status": result.status,
        "confidence": result.confidence,
        "people_status": result.people_status,
        "organization": org_dict,
        "people": people_list,
        "warnings": result.warnings,
        "cache_hit": result.cache_hit,
        "input_domain": result.input_domain,
        "input_name": result.input_name,
    }
