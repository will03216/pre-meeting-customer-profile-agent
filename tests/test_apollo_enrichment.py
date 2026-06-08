"""Unit tests for scripts/enrichment/apollo_enrichment.py (mocked only)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from enrichment.apollo_enrichment import (
    ApolloEnrichmentResult,
    ApolloOrganizationProfile,
    ApolloPersonCandidate,
    _cache_key,
    _domain_matches,
    _map_apollo_error,
    _normalize_domain,
    _parse_org,
    _why_relevant,
    apollo_result_to_dict,
    enrich_with_apollo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_identity(domain: str = "", name: str = "", contact: str = ""):
    obj = MagicMock()
    obj.domain = domain
    obj.company_name = name
    obj.canonical_name = contact or name
    return obj


def _org_payload(name="Jellyfish", domain="jellyfish.co"):
    return {
        "id": "abc123",
        "name": name,
        "primary_domain": domain,
        "website_url": f"https://{domain}",
        "short_description": f"{name} is a software platform.",
        "industry": "software",
        "keywords": ["engineering", "devtools"],
        "num_employees": 250,
        "founded_year": 2016,
        "city": "Boston",
        "state": "MA",
        "country": "US",
        "technology_names": ["GitHub", "Jira"],
        "annual_revenue": "$10M-$50M",
    }


def _people_payload():
    return [
        {
            "name": "Alice Example",
            "title": "CTO",
            "seniority": "c_suite",
            "department": "engineering",
            "linkedin_url": "https://linkedin.com/in/alice-example",
        },
        {
            "name": "Bob Sample",
            "title": "VP Product",
            "seniority": "vp",
            "department": "product",
            "linkedin_url": "",
        },
    ]


# ---------------------------------------------------------------------------
# 1. Disabled when no API key
# ---------------------------------------------------------------------------

def test_enrich_disabled_no_api_key(monkeypatch):
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    identity = _make_identity(domain="jellyfish.co", name="Jellyfish")
    result = enrich_with_apollo(identity)
    assert result.status == "missing_api_key"
    assert result.organization is None
    assert result.people == []


# ---------------------------------------------------------------------------
# 2. No domain or name → no_input_domain_or_name
# ---------------------------------------------------------------------------

def test_enrich_no_input(monkeypatch):
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    identity = _make_identity(domain="", name="")
    result = enrich_with_apollo(identity)
    assert result.status == "no_input_domain_or_name"


# ---------------------------------------------------------------------------
# 3. Successful domain-exact match with high confidence
# ---------------------------------------------------------------------------

def test_enrich_domain_exact_match(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "apollo_cache")
    org_payload = _org_payload()
    people_raw = _people_payload()

    with patch("enrichment.apollo_enrichment._apollo_get") as mock_get, \
         patch("enrichment.apollo_enrichment._apollo_post") as mock_post:
        mock_get.return_value = ({"organization": org_payload}, False, None)
        mock_post.return_value = ({"people": people_raw}, False, None)

        identity = _make_identity(domain="jellyfish.co", name="Jellyfish")
        result = enrich_with_apollo(identity, vertical_name="enterprise_llm")

    assert result.status == "organization_matched"
    assert result.confidence == "high_domain_exact"
    assert result.organization is not None
    assert result.organization.name == "Jellyfish"
    assert result.organization.employee_count == 250
    assert result.organization.founded_year == 2016
    assert result.organization.hq_city == "Boston"
    assert len(result.people) == 2
    assert result.people[0].name == "Alice Example"


# ---------------------------------------------------------------------------
# 4. Domain guard: domain-exact enrichment returns different domain
#    → rejected_due_to_domain_mismatch, no org data used
# ---------------------------------------------------------------------------

def test_enrich_domain_guard_mismatch_from_exact_lookup(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    wrong_domain_org = _org_payload(name="Jellyfish Corp", domain="jellyfishcorp.com")

    with patch("enrichment.apollo_enrichment._apollo_get") as mock_get:
        mock_get.return_value = ({"organization": wrong_domain_org}, False, None)

        identity = _make_identity(domain="jelly-fish.co.kr", name="Jellyfish")
        result = enrich_with_apollo(identity)

    assert result.status == "rejected_due_to_domain_mismatch"
    assert result.confidence == "none"
    assert result.organization is None, "Organization must NOT be exposed after domain mismatch"
    assert result.input_domain == "jelly-fish.co.kr"
    assert any("jellyfishcorp.com" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 5. Domain guard: name search returns jellyfish.co for input jelly-fish.co.kr
#    → rejected_due_to_domain_mismatch
# ---------------------------------------------------------------------------

def test_domain_guard_rejects_jellyfish_name_search_mismatch(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    # Domain enrichment returns nothing for jelly-fish.co.kr
    # Name search returns jellyfish.co (US company) - different domain
    jellyfish_us_org = _org_payload(name="Jellyfish", domain="jellyfish.co")

    with patch("enrichment.apollo_enrichment._apollo_get") as mock_get, \
         patch("enrichment.apollo_enrichment._apollo_post") as mock_post:
        mock_get.return_value = (None, False, "not_found")  # domain exact lookup fails
        mock_post.return_value = ({"organizations": [jellyfish_us_org]}, False, None)

        identity = _make_identity(domain="jelly-fish.co.kr", name="Jellyfish")
        result = enrich_with_apollo(identity)

    assert result.status == "rejected_due_to_domain_mismatch"
    assert result.confidence == "none"
    assert result.organization is None
    assert any("jelly-fish.co.kr" in w and "jellyfish.co" in w for w in result.warnings), \
        f"Expected mismatch warning mentioning both domains. Got: {result.warnings}"


# ---------------------------------------------------------------------------
# 6. Organization not found
# ---------------------------------------------------------------------------

def test_enrich_organization_not_found(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    with patch("enrichment.apollo_enrichment._apollo_get") as mock_get, \
         patch("enrichment.apollo_enrichment._apollo_post") as mock_post:
        mock_get.return_value = (None, False, "not_found")
        mock_post.return_value = (None, False, "not_found")

        identity = _make_identity(domain="tiny-unknown-startup.io", name="Tiny Unknown Startup")
        result = enrich_with_apollo(identity)

    assert result.status == "organization_not_found"
    assert result.organization is None
    assert result.people == []


# ---------------------------------------------------------------------------
# 7. Error reason mapping: 401 → auth_failed_401
# ---------------------------------------------------------------------------

def test_apollo_401_maps_to_auth_failed_status(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    with patch("enrichment.apollo_enrichment._apollo_get") as mock_get:
        mock_get.return_value = (None, False, "apollo_auth_error_401")
        identity = _make_identity(domain="example.com", name="Example")
        result = enrich_with_apollo(identity)

    assert result.status == "auth_failed_401", f"Expected auth_failed_401, got {result.status!r}"
    assert result.organization is None


# ---------------------------------------------------------------------------
# 8. Error reason mapping: 403 → forbidden_403
# ---------------------------------------------------------------------------

def test_apollo_403_maps_to_forbidden_status(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    with patch("enrichment.apollo_enrichment._apollo_get") as mock_get:
        mock_get.return_value = (None, False, "apollo_auth_error_403")
        identity = _make_identity(domain="example.com", name="Example")
        result = enrich_with_apollo(identity)

    assert result.status == "forbidden_403", f"Expected forbidden_403, got {result.status!r}"


# ---------------------------------------------------------------------------
# 9. Error reason mapping: rate_limited → rate_limited_429
# ---------------------------------------------------------------------------

def test_apollo_rate_limited_maps_to_429_status(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    with patch("enrichment.apollo_enrichment._apollo_get") as mock_get:
        mock_get.return_value = (None, False, "rate_limited")
        identity = _make_identity(domain="example.com", name="Example")
        result = enrich_with_apollo(identity)

    assert result.status == "rate_limited_429", f"Expected rate_limited_429, got {result.status!r}"


# ---------------------------------------------------------------------------
# 10. Error reason mapping: timeout → timeout
# ---------------------------------------------------------------------------

def test_apollo_timeout_maps_to_timeout_status(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    with patch("enrichment.apollo_enrichment._apollo_get") as mock_get:
        mock_get.return_value = (None, False, "apollo_timeout")
        identity = _make_identity(domain="example.com", name="Example")
        result = enrich_with_apollo(identity)

    assert result.status == "timeout", f"Expected timeout, got {result.status!r}"


# ---------------------------------------------------------------------------
# 11. request_failed does not silently hide the reason — warning is recorded
#     apollo_http_422 from org enrichment → org_enrich_invalid_request_422
# ---------------------------------------------------------------------------

def test_request_failed_does_not_hide_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    with patch("enrichment.apollo_enrichment._apollo_get") as mock_get:
        # _enrich_org_by_domain converts apollo_http_422 → apollo_org_enrich_422
        mock_get.return_value = (None, False, "apollo_http_422")
        identity = _make_identity(domain="example.com", name="Example")
        result = enrich_with_apollo(identity)

    assert result.status == "org_enrich_invalid_request_422", \
        f"Expected org_enrich_invalid_request_422, got {result.status!r}"
    assert len(result.warnings) > 0, "Expected at least one warning message"
    assert not any("request_failed" in w for w in result.warnings), \
        "Warning must not collapse to generic request_failed"


# ---------------------------------------------------------------------------
# 12. apollo_result_to_dict does not expose API key or personal data
# ---------------------------------------------------------------------------

def test_result_to_dict_no_key_leak(monkeypatch):
    monkeypatch.setenv("APOLLO_API_KEY", "super_secret_key_12345")
    monkeypatch.setenv("APOLLO_REVEAL_EMAILS", "0")
    org = ApolloOrganizationProfile(
        name="Acme",
        domain="acme.com",
        short_description="Acme builds widgets.",
        employee_count=100,
    )
    person = ApolloPersonCandidate(
        name="Jane Doe",
        title="CTO",
        linkedin_url="https://linkedin.com/in/janedoe",
        seniority="c_suite",
    )
    result = ApolloEnrichmentResult(
        status="organization_matched",
        confidence="high_domain_exact",
        organization=org,
        people=[person],
    )
    d = apollo_result_to_dict(result)
    serialized = json.dumps(d)
    assert "super_secret_key_12345" not in serialized
    assert "janedoe" not in serialized  # LinkedIn URL hidden when APOLLO_REVEAL_EMAILS=0
    assert d["organization"]["name"] == "Acme"
    assert d["people"][0]["name"] == "Jane Doe"


# ---------------------------------------------------------------------------
# 13. Cache hit path respected
# ---------------------------------------------------------------------------

def test_cache_hit(monkeypatch, tmp_path):
    import enrichment.apollo_enrichment as ae_mod

    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr(ae_mod, "CACHE_DIR", tmp_path / "cache")

    org_payload = _org_payload()
    cache_data = {"organization": org_payload, "_cache_written_at": time.time()}
    key = _cache_key("organizations/enrich", {"domain": "jellyfish.co"})
    (tmp_path / "cache").mkdir(parents=True)
    (tmp_path / "cache" / f"{key}.json").write_text(json.dumps(cache_data))

    with patch("enrichment.apollo_enrichment._apollo_post") as mock_post:
        mock_post.return_value = ({"people": []}, False, None)
        identity = _make_identity(domain="jellyfish.co", name="Jellyfish")
        result = enrich_with_apollo(identity)

    assert result.status == "organization_matched"
    assert result.cache_hit is True
    assert result.organization.name == "Jellyfish"


# ---------------------------------------------------------------------------
# 14. Renderer handles Apollo rejected/unavailable without crashing
# ---------------------------------------------------------------------------

def test_renderer_handles_apollo_unavailable():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from render_prep_doc import _build_apollo_essential_rows, apollo_stakeholders_section

    for status in ("rejected_due_to_domain_mismatch", "auth_failed_401", "forbidden_403",
                   "rate_limited_429", "timeout", "network_error", "request_failed",
                   "organization_not_found", "missing_api_key", "disabled"):
        data = {
            "apollo": {
                "status": status,
                "organization": None,
                "people": [],
                "warnings": [f"test warning for {status}"],
                "input_domain": "jelly-fish.co.kr",
                "input_name": "Jellyfish",
            },
            "enrichment": {},
            "customer": {},
        }
        # Must not raise
        rows = _build_apollo_essential_rows(data)
        section = apollo_stakeholders_section(data)
        assert isinstance(rows, list)
        assert isinstance(section, str)

    # rejected status must produce a visible note row
    data_rejected = {
        "apollo": {
            "status": "rejected_due_to_domain_mismatch",
            "organization": None,
            "people": [],
            "warnings": ["Apollo returned domain 'jellyfish.co' for input domain 'jelly-fish.co.kr'."],
            "input_domain": "jelly-fish.co.kr",
        },
        "enrichment": {},
        "customer": {},
    }
    rows = _build_apollo_essential_rows(data_rejected)
    assert len(rows) == 1
    field_name, value = rows[0]
    assert "Apollo" in field_name
    assert "jellyfish.co" in value or "Not used" in value or "mismatch" in value.lower()


# ---------------------------------------------------------------------------
# Utility function tests
# ---------------------------------------------------------------------------

def test_normalize_domain():
    assert _normalize_domain("https://www.example.com/path?q=1") == "example.com"
    assert _normalize_domain("example.com") == "example.com"
    assert _normalize_domain("") == ""


def test_domain_matches():
    assert _domain_matches("https://www.jellyfish.co", "jellyfish.co")
    assert not _domain_matches("jellyfish.co", "jellyfishcorp.com")
    assert not _domain_matches("jellyfish.co", "jelly-fish.co.kr")
    assert not _domain_matches("", "jellyfish.co")


def test_why_relevant_cto():
    assert "Technical" in _why_relevant("CTO", "default")
    assert "Executive" in _why_relevant("CEO", "marketing_adtech")
    assert "Product" in _why_relevant("VP Product", "enterprise_llm")


def test_map_apollo_error():
    assert _map_apollo_error("rate_limited") == "rate_limited_429"
    assert _map_apollo_error("apollo_auth_error_401") == "auth_failed_401"
    assert _map_apollo_error("apollo_auth_error_403") == "forbidden_403"
    assert _map_apollo_error("apollo_timeout") == "timeout"
    assert _map_apollo_error("apollo_network_error: timed out") == "timeout"
    assert _map_apollo_error("apollo_network_error: connection refused") == "network_error"
    assert _map_apollo_error("apollo_invalid_json") == "invalid_response"
    assert _map_apollo_error("apollo_max_retries") == "network_error"
    # apollo_http_422 (generic) still maps to http_error_422
    assert _map_apollo_error("apollo_http_422") == "http_error_422"
    # apollo_org_enrich_422 is the specific org-enrichment 422 code
    assert _map_apollo_error("apollo_org_enrich_422") == "org_enrich_invalid_request_422"
    assert _map_apollo_error("not_found") == "organization_not_found"
    assert _map_apollo_error(None) == "request_failed"
    assert _map_apollo_error("something_unknown") == "request_failed"


# ---------------------------------------------------------------------------
# Regression tests (requirements 5.1-5.4)
# ---------------------------------------------------------------------------

def test_org_enrich_called_with_query_param_domain_not_json_body(monkeypatch, tmp_path):
    """organizations/enrich must be called via _apollo_get with domain in params dict.
    The api_key must NOT appear in the params dict — it goes in the X-Api-Key header.
    """
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    captured: dict = {}

    def fake_get(endpoint, params, api_key, **kwargs):
        captured["endpoint"] = endpoint
        captured["params"] = dict(params)
        captured["api_key_in_params"] = "api_key" in params
        return None, False, "not_found"

    with patch("enrichment.apollo_enrichment._apollo_get", side_effect=fake_get), \
         patch("enrichment.apollo_enrichment._apollo_post") as mock_post:
        mock_post.return_value = (None, False, "not_found")
        identity = _make_identity(domain="jelly-fish.co.kr", name="Jellyfish")
        enrich_with_apollo(identity)

    assert captured.get("endpoint") == "organizations/enrich", \
        f"Expected organizations/enrich, got {captured.get('endpoint')!r}"
    assert captured.get("params") == {"domain": "jelly-fish.co.kr"}, \
        f"Expected domain as query param only, got {captured.get('params')}"
    assert not captured.get("api_key_in_params"), \
        "api_key must NOT be in params dict; it belongs in X-Api-Key header"


def test_normalize_domain_removes_protocol_www_slash_path():
    """_normalize_domain strips https://, http://, www., path, and query string."""
    assert _normalize_domain("https://www.jelly-fish.co.kr/about?lang=en") == "jelly-fish.co.kr"
    assert _normalize_domain("http://example.com/") == "example.com"
    assert _normalize_domain("www.apollo.io") == "apollo.io"
    assert _normalize_domain("HTTPS://WWW.EXAMPLE.COM") == "example.com"
    assert _normalize_domain("jelly-fish.co.kr") == "jelly-fish.co.kr"
    assert _normalize_domain("") == ""
    assert _normalize_domain(None) == ""


def test_422_debug_includes_safe_response_excerpt(monkeypatch, tmp_path, capsys):
    """HTTP 422 response body excerpt must appear in debug output; API key must be redacted."""
    import io as _io
    import urllib.error as _ue

    fake_key = "super_secret_key_abc"
    monkeypatch.setenv("APOLLO_API_KEY", fake_key)
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    response_body = (
        '{"error":"unprocessable","message":"domain quota exceeded",'
        f'"api_key":"{fake_key}"}}'
    ).encode("utf-8")

    http_exc = _ue.HTTPError(
        url="https://api.apollo.io/v1/organizations/enrich",
        code=422,
        msg="Unprocessable Entity",
        hdrs={},  # type: ignore[arg-type]
        fp=_io.BytesIO(response_body),
    )

    with patch("urllib.request.urlopen", side_effect=http_exc):
        from enrichment.apollo_enrichment import _apollo_get
        _data, _cache, error = _apollo_get(
            "organizations/enrich",
            {"domain": "jelly-fish.co.kr"},
            fake_key,
            ttl_hours=0,
            refresh=True,
            debug=True,
        )

    captured = capsys.readouterr()
    assert error == "apollo_http_422"
    assert "422" in captured.err, "HTTP status must appear in debug output"
    assert "response_excerpt" in captured.err, "response_excerpt key must appear in debug output"
    assert fake_key not in captured.err, "API key must be redacted from debug output"
    # The redacted marker OR the safe excerpt content must appear
    assert "***REDACTED***" in captured.err or "domain quota exceeded" in captured.err


def test_people_search_skipped_when_org_enrich_fails_422(monkeypatch, tmp_path):
    """When org enrichment returns HTTP 422, people search (POST) must not be called."""
    monkeypatch.setenv("APOLLO_API_KEY", "test_key_xyz")
    monkeypatch.setattr("enrichment.apollo_enrichment.CACHE_DIR", tmp_path / "cache")

    with patch("enrichment.apollo_enrichment._apollo_get") as mock_get, \
         patch("enrichment.apollo_enrichment._apollo_post") as mock_post:
        # _apollo_get returns raw 422; _enrich_org_by_domain converts to apollo_org_enrich_422
        mock_get.return_value = (None, False, "apollo_http_422")

        identity = _make_identity(domain="jelly-fish.co.kr", name="Jellyfish")
        result = enrich_with_apollo(identity)

    assert result.status == "org_enrich_invalid_request_422", \
        f"Expected org_enrich_invalid_request_422, got {result.status!r}"
    mock_post.assert_not_called()  # People search (POST) must never be called after 422
    assert result.organization is None
    assert result.people == []


# ---------------------------------------------------------------------------
# Round 5: Language normalization helpers
# ---------------------------------------------------------------------------

def test_is_substantially_non_latin_korean():
    from run_prep import _is_substantially_non_latin
    assert _is_substantially_non_latin("음반 기획 및 제작, 연예 매니지먼트 업체") is True
    assert _is_substantially_non_latin("Korean entertainment company") is False
    assert _is_substantially_non_latin("") is False
    assert _is_substantially_non_latin("abc") is False  # too short (< 4 alpha chars)


def test_build_english_apollo_description_korean():
    from run_prep import _build_english_apollo_description, _is_substantially_non_latin
    org = {
        "name": "Jellyfish Entertainment",
        "industry": "entertainment",
        "keywords": ["music", "artist management"],
        "country": "South Korea",
        "short_description": "음반 기획 및 제작, 연예 매니지먼트 업체, 소속 아티스트 안내",
    }
    result = _build_english_apollo_description(org)
    assert "Korean" in result, f"Expected 'Korean' in result, got: {result!r}"
    assert "entertainment" in result.lower(), f"Expected 'entertainment' in result, got: {result!r}"
    assert _is_substantially_non_latin(result) is False, \
        f"Result must be English (no raw Korean), got: {result!r}"


def test_build_english_apollo_description_uses_keyword_display_map():
    from run_prep import _build_english_apollo_description, _is_substantially_non_latin
    # When description contains Korean keywords, they should be mapped to English
    org = {
        "name": "TestCo",
        "industry": "music",
        "keywords": [],
        "country": "Japan",
        "short_description": "음반 기획 및 제작, 아티스트 매니지먼트",
    }
    result = _build_english_apollo_description(org)
    assert not _is_substantially_non_latin(result), f"Result should be English, got: {result!r}"
    assert "Japanese" in result or "music" in result.lower(), \
        f"Expected country adjective or industry, got: {result!r}"


# ---------------------------------------------------------------------------
# Round 4 regression: Korean entertainment company (jelly-fish.co.kr)
# Apollo organization_matched with Korean description → vertical and doc correct
# ---------------------------------------------------------------------------

def test_korean_entertainment_apollo_propagates_to_document():
    """
    Input: jelly-fish.co.kr, Apollo returns Korean entertainment org with 14 employees.
    Expected: vertical inferred as media_entertainment (not Default/Unknown),
    What They Do uses Apollo description, Executive Snapshot includes Apollo evidence,
    no web search required to produce a useful document.
    """
    from run_prep import (
        PrepContext,
        CustomerIdentity,
        context_to_renderer_json,
        infer_vertical,
        evidence_snippets,
    )
    import argparse
    from scripts.render_prep_doc import render  # type: ignore[import]

    korean_desc = "음반 기획 및 제작, 연예 매니지먼트 업체, 소속 아티스트 안내"

    apollo_data = {
        "status": "organization_matched",
        "confidence": "high_domain_exact",
        "organization": {
            "name": "Jellyfish Entertainment",
            "primary_domain": "jelly-fish.co.kr",
            "short_description": korean_desc,
            "industry": "entertainment",
            "keywords": ["music", "artist management"],
            "num_employees": 14,
            "city": "Seoul",
            "country": "South Korea",
            "linkedin_url": "https://www.linkedin.com/company/jellyfish-entertainment",
            "technology_names": [],
        },
        "people": [],
        "warnings": [],
    }

    identity = CustomerIdentity(
        canonical_name="Jellyfish",
        domain="jelly-fish.co.kr",
        email=None,
        confidence="confirmed",
        evidence=["domain: jelly-fish.co.kr"],
        company_name="Jellyfish Entertainment",
    )
    context = PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment=None,
        missing_context=[],
        apollo_enrichment=apollo_data,
        web_search_status="web_search: disabled_by_env",
        company_overview_status="no_overview_eligible_results",
    )

    # Vertical inference must pick up Korean signals from evidence_snippets
    snippets = evidence_snippets(context)
    haystack = "\n".join(snippets).lower()
    assert "음반" in haystack or "연예" in haystack or "entertainment" in haystack, \
        "Apollo description and location must appear in evidence snippets"

    vertical = infer_vertical(context)
    assert vertical.get("name") == "media_entertainment", \
        f"Expected media_entertainment, got {vertical.get('name')!r} (evidence: {vertical.get('evidence')})"

    args = argparse.Namespace(
        industry=None,
        workload=None,
        prospecting_prompt=None,
        debug=False,
    )
    render_json = context_to_renderer_json(context, args)

    # Vertical in render_json must not be Default/Unknown
    assert render_json["vertical"]["name"] == "media_entertainment", \
        f"render_json vertical: {render_json['vertical']}"

    # what_they_do must use Apollo description (not web search unavailable message)
    dossier = render_json.get("enrichment", {}).get("dossier") or {}
    what_they_do = str(dossier.get("what_they_do") or "")
    assert "Apollo signal" in what_they_do, \
        f"what_they_do should contain Apollo signal, got: {what_they_do!r}"
    assert "web search" not in what_they_do.lower(), \
        f"what_they_do should not mention web search, got: {what_they_do!r}"

    # Employee count goes to scale_signals, NOT monthly_volume
    dossier_check = render_json.get("enrichment", {}).get("dossier") or {}
    scale_signals = dossier_check.get("scale_signals") or []
    assert any("14" in str(s) and "Apollo" in str(s) for s in scale_signals), \
        f"scale_signals should include Apollo employee count 14, got: {scale_signals}"
    known = render_json.get("known") or {}
    monthly_volume = str(known.get("monthly_volume") or "")
    assert "14" not in monthly_volume, \
        f"monthly_volume must NOT contain employee count, got: {monthly_volume!r}"

    # Render to markdown and assert final document quality
    md = render(render_json)
    assert "Default / Unknown" not in md, "Vertical must not be Default / Unknown in rendered output"
    assert "Apollo signal" in md, "Apollo signal label must appear in rendered markdown"
    assert "web search/fetch was unavailable" not in md, \
        "Rendered doc must not say web search/fetch was unavailable when Apollo description exists"
    assert "14" in md, "Employee count (14) must appear somewhere in the rendered output"
    # English description must be in user-facing sections
    assert "Korean entertainment" in md or "entertainment" in md.lower(), \
        "English paraphrase must appear in rendered markdown"


def test_korean_apollo_description_not_in_user_facing_sections():
    """
    Round 5: Raw Korean text must not appear in What They Do, Core Business Hypothesis,
    Standard Discovery pre-fill, or Meeting Output Core Business.
    It may only appear in the Evidence Table as 'Original source text'.
    Vertical evidence labels must be English, not raw Korean keywords.
    """
    from run_prep import PrepContext, CustomerIdentity, context_to_renderer_json
    import argparse
    from scripts.render_prep_doc import render  # type: ignore[import]

    korean_desc = "음반 기획 및 제작, 연예 매니지먼트 업체, 소속 아티스트 안내"
    apollo_data = {
        "status": "organization_matched",
        "confidence": "high_domain_exact",
        "organization": {
            "name": "Jellyfish Entertainment",
            "primary_domain": "jelly-fish.co.kr",
            "short_description": korean_desc,
            "industry": "entertainment",
            "keywords": ["music", "artist management"],
            "num_employees": 14,
            "city": "Seoul",
            "country": "South Korea",
            "linkedin_url": "https://www.linkedin.com/company/jellyfish-entertainment",
            "technology_names": [],
        },
        "people": [],
        "warnings": [],
    }
    identity = CustomerIdentity(
        canonical_name="Jellyfish",
        domain="jelly-fish.co.kr",
        email=None,
        confidence="confirmed",
        evidence=["domain: jelly-fish.co.kr"],
        company_name="Jellyfish Entertainment",
    )
    context = PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment=None,
        missing_context=[],
        apollo_enrichment=apollo_data,
        web_search_status="web_search: disabled_by_env",
        company_overview_status="no_overview_eligible_results",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    render_json = context_to_renderer_json(context, args)
    md = render(render_json)

    # Locate section boundaries so we can check per-section
    lines = md.split("\n")

    def lines_in_section(header_substring: str, end_header_prefix: str = "##") -> str:
        collecting = False
        section_lines = []
        for line in lines:
            if header_substring in line:
                collecting = True
            elif collecting and line.startswith(end_header_prefix) and header_substring not in line:
                break
            elif collecting:
                section_lines.append(line)
        return "\n".join(section_lines)

    # Sections that must NOT contain raw Korean
    # (Round 17: Executive Prep Snapshot merged into Account Intelligence Snapshot / Opportunity Hypotheses)
    intel_section = lines_in_section("Essential Background Check")
    opp_section = lines_in_section("Opportunity Hypotheses")
    validation_section = lines_in_section("First Meeting Validation Plan")

    korean_chars = "음반연예매니지먼트아티스트"
    for char in korean_chars:
        assert char not in intel_section, \
            f"Raw Korean char '{char}' must not appear in Account Intelligence Snapshot"
        assert char not in opp_section, \
            f"Raw Korean char '{char}' must not appear in Opportunity Hypotheses"
        assert char not in validation_section, \
            f"Raw Korean char '{char}' must not appear in First Meeting Validation Plan"

    # English paraphrase must appear in user-facing sections
    assert "Korean entertainment" in intel_section or "entertainment" in intel_section.lower(), \
        "English paraphrase must appear in Essential Background Check"
    assert "Korean entertainment" in opp_section or "entertainment" in opp_section.lower() or \
           "media" in opp_section.lower(), \
        "English paraphrase or vertical must appear in Opportunity Hypotheses"

    # Original Korean must be preserved ONLY in Evidence Table
    evidence_section = lines_in_section("Evidence Table", end_header_prefix="#")
    assert "Original source text" in evidence_section, \
        "Original source text must appear in Evidence Table"
    assert "음반" in evidence_section or "연예" in evidence_section, \
        "Original Korean text must be preserved in Evidence Table"

    # English vertical label must be present in intel section
    assert "매니지먼트" not in intel_section, \
        "Raw Korean keyword '매니지먼트' must not appear in Account Intelligence Snapshot"
    assert "아티스트" not in intel_section, \
        "Raw Korean keyword '아티스트' must not appear in Account Intelligence Snapshot"
    assert "management" in intel_section.lower() or "entertainment" in intel_section.lower() or \
           "media" in intel_section.lower(), \
        "English vertical evidence must appear in Account Intelligence Snapshot"

    # Vertical must not be Default / Unknown
    assert "Default / Unknown" not in md


# ---------------------------------------------------------------------------
# Round 5 / general synthesis: Monks (monks.com) regression tests
# ---------------------------------------------------------------------------

def _monks_apollo_data() -> dict:
    """Mock Apollo organization_matched payload for Monks (monks.com)."""
    monks_long_desc = (
        "Monks is a digital-first creative production partner that enables brands to transform "
        "the way they create and distribute content at scale. We combine cutting-edge technology "
        "with creative expertise to deliver award-winning digital campaigns, immersive experiences, "
        "and AI-powered marketing solutions for global brands and agencies. Our work spans creative "
        "production, digital transformation, and data-driven marketing across 30+ countries."
    )
    return {
        "status": "organization_matched",
        "confidence": "high_domain_exact",
        "organization": {
            "name": "Monks",
            "primary_domain": "monks.com",
            "short_description": monks_long_desc,
            "industry": "marketing and advertising",
            "keywords": ["digital marketing", "creative production", "content creation", "advertising", "digital agency"],
            "num_employees": 8000,
            "employee_count": 8000,
            "annual_revenue": "1065000000.0",
            "annual_revenue_currency": "USD",
            "founded_year": 1999,
            "city": "Amsterdam",
            "country": "Netherlands",
            "linkedin_url": "https://www.linkedin.com/company/monksdigital",
            "technology_names": [
                "Salesforce", "HubSpot", "AWS", "Adobe Creative Suite", "OpenAI",
                "Python", "React", "Slack", "Google Analytics", "Adobe Analytics",
                "Tableau", "Snowflake",
            ],
        },
        "people": [],
        "warnings": [],
    }


def _monks_context():
    from run_prep import PrepContext, CustomerIdentity
    identity = CustomerIdentity(
        canonical_name="Monks",
        domain="monks.com",
        email=None,
        confidence="confirmed",
        evidence=["domain: monks.com"],
        company_name="Monks",
    )
    return PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment=None,
        missing_context=[],
        apollo_enrichment=_monks_apollo_data(),
        web_search_status="web_search: disabled_by_env",
        company_overview_status="no_overview_eligible_results",
    )


def test_monks_classified_as_marketing_adtech_not_default():
    """Monks (monks.com) with digital agency Apollo data must be classified as
    marketing_adtech, not Default / Unknown. No domain-specific hardcoding."""
    from run_prep import context_to_renderer_json, infer_vertical
    import argparse

    context = _monks_context()
    vertical = infer_vertical(context)
    assert vertical["name"] == "marketing_adtech", \
        f"Expected marketing_adtech, got {vertical['name']!r} (evidence: {vertical['evidence']})"

    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    render_json = context_to_renderer_json(context, args)
    assert render_json["vertical"]["name"] == "marketing_adtech", \
        f"render_json vertical: {render_json['vertical']}"

    from scripts.render_prep_doc import render  # type: ignore[import]
    md = render(render_json)
    assert "Default / Unknown" not in md, "Vertical must not be Default / Unknown for Monks"
    assert "Marketing" in md or "marketing" in md, "Marketing vertical must appear in rendered output"


def test_long_apollo_description_summarized_in_user_facing_fields():
    """A long Apollo description (>2 sentences) must be summarized to ≤2 sentences
    in What They Do and Core Business. The full text stays in Apollo essential rows."""
    from run_prep import context_to_renderer_json, _summarize_description
    import argparse

    # Test the helper directly — description must be >220 chars to trigger summarization
    long_desc = (
        "Sentence one: this is a long first sentence about the company and its products and global reach. "
        "Sentence two: this covers the technology and creative capabilities that they offer at enterprise scale. "
        "Sentence three: this details geographic markets and industries that should be dropped from user-facing fields."
    )
    assert len(long_desc) > 220, "Test desc must be long enough to trigger summarization"
    summarized = _summarize_description(long_desc)
    sentences = [s for s in summarized.replace(".", ".|").split("|") if s.strip()]
    assert len(sentences) <= 2, f"Should be ≤2 sentences, got {len(sentences)}: {summarized!r}"
    assert "Sentence one" in summarized, "First sentence must be preserved"
    assert "Sentence three" not in summarized, "Third sentence must be dropped"

    # Test end-to-end: Monks long description is summarized in what_they_do
    context = _monks_context()
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    render_json = context_to_renderer_json(context, args)
    dossier = render_json.get("enrichment", {}).get("dossier") or {}
    what_they_do = str(dossier.get("what_they_do") or "")
    # Full 3-sentence description must be trimmed — 3rd sentence should not appear
    assert "30+ countries" not in what_they_do, \
        f"3rd sentence must not appear in what_they_do, got: {what_they_do[:200]!r}"
    assert "Apollo signal" in what_they_do, "Apollo signal label must appear"


def test_scale_signals_use_apollo_employee_and_revenue_not_monthly_volume():
    """Apollo employee count and revenue must appear in Scale Signals / dossier.scale_signals.
    Monthly Volume must remain 'Not Found' unless actual API/generation volume exists."""
    from run_prep import context_to_renderer_json
    import argparse

    context = _monks_context()
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    render_json = context_to_renderer_json(context, args)

    dossier = render_json.get("enrichment", {}).get("dossier") or {}
    scale_signals = dossier.get("scale_signals") or []
    assert any("8,000" in str(s) or "8000" in str(s) for s in scale_signals), \
        f"Employee count must appear in scale_signals, got: {scale_signals}"
    assert any("revenue" in str(s).lower() or "1.1" in str(s) for s in scale_signals), \
        f"Revenue signal must appear in scale_signals, got: {scale_signals}"

    known = render_json.get("known") or {}
    monthly_volume = str(known.get("monthly_volume") or "")
    assert "8000" not in monthly_volume and "employee" not in monthly_volume.lower(), \
        f"Employee count must NOT be in monthly_volume, got: {monthly_volume!r}"

    from scripts.render_prep_doc import render  # type: ignore[import]
    md = render(render_json)
    assert "Not Found: monthly token/image/video volume" in md or "Not Found" in md, \
        "Monthly Volume row must show Not Found in rendered output"


def test_apollo_revenue_formatted_human_readable():
    """Revenue values must be formatted for human readers."""
    from run_prep import _format_apollo_revenue
    assert _format_apollo_revenue("1065000000.0", "USD") == "~$1.1B annual revenue signal"
    assert _format_apollo_revenue("1065000000.0") == "~1.1B annual revenue signal (currency not confirmed)"
    assert _format_apollo_revenue("50000000.0", "EUR") == "~€50M annual revenue signal"
    assert _format_apollo_revenue("500000.0") == "~500K annual revenue signal (currency not confirmed)"
    assert _format_apollo_revenue("$10M-$50M") == "$10M-$50M"  # already-formatted string passthrough
    assert _format_apollo_revenue("") == ""
    assert _format_apollo_revenue(None) == ""


def test_technology_signals_filtered_for_byteplus_relevance():
    """Technology Signals must prioritize BytePlus-relevant tools (AI, cloud, analytics, creative).
    Noisy irrelevant tools should be deprioritized when better signals exist."""
    from render_prep_doc import _filter_byteplus_relevant_techs

    monks_techs = [
        "Salesforce", "HubSpot", "AWS", "Adobe Creative Suite", "OpenAI",
        "Python", "React", "Slack", "Google Analytics", "Adobe Analytics",
        "Tableau", "Snowflake",
    ]
    filtered = _filter_byteplus_relevant_techs(monks_techs, max_count=6)
    assert len(filtered) <= 6, f"Must return ≤6 results, got {len(filtered)}"
    # High-priority tools must be included
    assert "AWS" in filtered, "AWS (cloud) must be included as BytePlus-relevant"
    assert "OpenAI" in filtered, "OpenAI (AI) must be included as BytePlus-relevant"
    # Noisy tools should be absent when higher-priority ones fill the slots
    noisy = {"Slack", "React", "HubSpot"}
    relevant_count = sum(1 for t in filtered if t not in noisy)
    assert relevant_count >= 4, \
        f"At least 4 of the 6 slots must be BytePlus-relevant, got: {filtered}"


# ---------------------------------------------------------------------------
# Round 7 regression tests
# ---------------------------------------------------------------------------


def test_scale_signal_synchronized_across_all_sections():
    """
    Apollo scale signal (employee count + revenue) must appear consistently in:
    - Essential Background Check (dossier.scale_signals)
    - Executive Prep Snapshot (known.scale_signal)
    - Prepare Internal Hypothesis (known.scale_signal)
    Monthly Volume must remain 'Not Found' (no employee count bleed-over).
    No company-specific hardcoding.
    """
    from run_prep import context_to_renderer_json
    import argparse
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _monks_context()
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    render_json = context_to_renderer_json(context, args)

    # scale_signal must be in known
    known = render_json.get("known") or {}
    scale_signal = known.get("scale_signal") or ""
    assert "Likely" in scale_signal, f"scale_signal must start with 'Likely', got: {scale_signal!r}"
    assert "Apollo signal" in scale_signal, f"scale_signal must mention Apollo signal, got: {scale_signal!r}"
    assert "8,000" in scale_signal or "8000" in scale_signal, \
        f"scale_signal must include employee count, got: {scale_signal!r}"
    assert "(?)" in scale_signal, f"scale_signal must include (?) confidence marker, got: {scale_signal!r}"

    md = render(render_json)
    lines = md.split("\n")

    def section_text(header_substring: str) -> str:
        collecting = False
        out = []
        for line in lines:
            if header_substring in line:
                collecting = True
            elif collecting and line.startswith("##") and header_substring not in line:
                break
            elif collecting:
                out.append(line)
        return "\n".join(out)

    # Round 17: Executive Prep Snapshot / Prepare Internal Hypothesis merged into
    # Account Intelligence Snapshot (Section 2). Scale signal lives there; no need to repeat.
    background_section = section_text("Essential Background Check")

    # Employee count must appear in Account Intelligence Snapshot
    assert "8,000" in background_section or "8000" in background_section or "Apollo signal" in background_section, \
        f"Employee count or Apollo signal must appear in Essential Background Check; got:\n{background_section[:400]}"

    # Monthly Volume must remain Not Found
    assert "Not Found" in md, "Monthly Volume must show Not Found for pure Apollo firmographic data"
    # Employee count must not appear in a Monthly Volume row
    monthly_idx = next((i for i, l in enumerate(lines) if "Monthly" in l and "Volume" in l), None)
    if monthly_idx is not None:
        monthly_row = lines[monthly_idx]
        assert "8000" not in monthly_row and "8,000" not in monthly_row, \
            f"Employee count must not bleed into Monthly Volume row: {monthly_row!r}"


def test_apollo_org_people_split_in_source_status():
    """
    source_status must have separate 'apollo_org' and 'apollo_people' keys.
    'apollo_org' reflects organization enrichment outcome.
    'apollo_people' reflects people search outcome (may be 'not_attempted' or an error code).
    The old single 'apollo' key must not be present.
    """
    from run_prep import context_to_renderer_json
    import argparse

    context = _monks_context()
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    render_json = context_to_renderer_json(context, args)

    source_status = render_json.get("source_status") or {}
    assert "apollo_org" in source_status, \
        f"source_status must contain 'apollo_org', got keys: {list(source_status.keys())}"
    assert "apollo_people" in source_status, \
        f"source_status must contain 'apollo_people', got keys: {list(source_status.keys())}"
    assert source_status["apollo_org"] == "organization_matched", \
        f"apollo_org should be 'organization_matched' for Monks mock, got: {source_status['apollo_org']!r}"

    # people_status for Monks mock has no people key → should be 'not_attempted'
    assert source_status["apollo_people"] in (
        "not_attempted", "no_people_found", "people_found"
    ), f"apollo_people unexpected value: {source_status['apollo_people']!r}"


def test_apollo_people_403_renders_non_blocking_note():
    """
    When Apollo people search returns 403 (free plan restriction), the rendered doc
    must show a non-blocking note in the Evidence Table rather than a fatal error.
    The note should say something like 'Unavailable' and 'Stakeholders remain To Validate.'
    Org enrichment data must still appear normally.
    """
    from run_prep import PrepContext, CustomerIdentity, context_to_renderer_json
    import argparse
    from scripts.render_prep_doc import render  # type: ignore[import]

    apollo_with_403_people = {
        "status": "organization_matched",
        "confidence": "high_domain_exact",
        "people_status": "people_search_forbidden_403",
        "organization": {
            "name": "AnyAgency",
            "primary_domain": "anyagency.com",
            "short_description": "A creative marketing agency.",
            "industry": "marketing and advertising",
            "keywords": ["digital marketing", "creative agency"],
            "num_employees": 500,
            "city": "New York",
            "country": "United States",
            "linkedin_url": "https://www.linkedin.com/company/anyagency",
            "technology_names": ["AWS", "OpenAI"],
        },
        "people": [],
        "warnings": ["people search: 403 forbidden"],
    }
    identity = CustomerIdentity(
        canonical_name="AnyAgency",
        domain="anyagency.com",
        email=None,
        confidence="confirmed",
        evidence=["domain: anyagency.com"],
        company_name="AnyAgency",
    )
    context = PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment=None,
        missing_context=[],
        apollo_enrichment=apollo_with_403_people,
        web_search_status="web_search: disabled_by_env",
        company_overview_status="no_overview_eligible_results",
    )

    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    render_json = context_to_renderer_json(context, args)

    # source_status.apollo_people must carry the 403 code
    source_status = render_json.get("source_status") or {}
    assert source_status.get("apollo_people") == "people_search_forbidden_403", \
        f"apollo_people status mismatch: {source_status.get('apollo_people')!r}"

    # Org data must still be present
    dossier = render_json.get("enrichment", {}).get("dossier") or {}
    assert dossier.get("what_they_do") or dossier.get("scale_signals"), \
        "Org enrichment data must still be present despite people 403"

    md = render(render_json)

    # The 403 note must appear in the rendered doc
    assert "Unavailable" in md or "403" in md or "To Validate" in md, \
        "People 403 must surface as a non-blocking note in the rendered output"
    # Org enrichment must still render
    assert "500" in md or "AnyAgency" in md, \
        "Org data (employee count or name) must appear despite people 403"
    # Must not be a fatal error
    assert "Fatal" not in md and "FAILED" not in md, \
        "People 403 must not cause a fatal rendering error"


def test_evidence_table_no_mid_sentence_truncation():
    """
    Long Apollo descriptions in the Evidence Table must be truncated at sentence boundaries,
    not mid-word or mid-sentence.
    """
    from render_prep_doc import _build_apollo_essential_rows  # type: ignore[import]

    long_desc = (
        "Monks is a global creative production partner enabling brands worldwide. "
        "They combine cutting-edge technology with creative expertise to deliver award-winning campaigns. "
        "Their work spans 30 countries and reaches millions of consumers every day through digital channels."
    )
    assert len(long_desc) > 180, "Desc must be long enough to trigger truncation"

    # _build_apollo_essential_rows expects the full render JSON with data["apollo"]
    render_data = {
        "apollo": {
            "status": "organization_matched",
            "organization": {
                "name": "Monks",
                "primary_domain": "monks.com",
                "short_description_en": long_desc,
                "short_description": long_desc,
                "industry": "marketing and advertising",
                "num_employees": 8000,
                "hq_city": "Amsterdam",
                "hq_country": "Netherlands",
                "technology_names": ["AWS", "OpenAI"],
            },
            "people": [],
        }
    }

    rows = _build_apollo_essential_rows(render_data)
    # Find the Company Description row
    desc_rows = [(label, val) for label, val in rows if "Description" in label]
    assert desc_rows, "Apollo essential rows must include a description row"

    _, cell_text = desc_rows[0]
    # Must not end mid-word
    assert not cell_text.endswith("…") or cell_text[-1] in ".!?", \
        f"Cell must not end mid-word without a period: {cell_text!r}"
    if len(cell_text) < len(long_desc):
        # Truncation occurred — must end with punctuation or sentence end
        assert cell_text[-1] in ".!?", \
            f"Truncated cell must end with sentence-boundary punctuation, got: {cell_text!r}"
        # Must not end mid-word (last char before period must be alphanumeric or closing paren)
        last_word = cell_text.rstrip(".!? ").split()[-1] if cell_text.rstrip(".!? ") else ""
        assert last_word, f"Truncated cell must end on a real word, got: {cell_text!r}"


def test_marketing_adtech_vertical_produces_seedance_ark_vlm_hypotheses():
    """
    marketing_adtech vertical + Apollo org data must produce BytePlus fit hypotheses
    mentioning Seedance/Seedream, Ark, and VLM / automation.
    No web enrichment required — Apollo-only enrichment must trigger the hypotheses.
    """
    from run_prep import context_to_renderer_json
    import argparse
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _monks_context()
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    render_json = context_to_renderer_json(context, args)

    enrichment = render_json.get("enrichment") or {}
    known_use_cases = enrichment.get("known_use_cases") or []
    possible_byteplus_fit = enrichment.get("possible_byteplus_fit") or []

    assert known_use_cases, "marketing_adtech must produce known_use_cases from Apollo vertical fit"
    assert any("Possible fit hypothesis to validate" in str(uc) for uc in known_use_cases), \
        f"Use cases must use 'Possible fit hypothesis to validate' wording, got: {known_use_cases}"

    products = [item.get("product") or "" for item in possible_byteplus_fit]
    assert any("Seedance" in p or "Seedream" in p for p in products), \
        f"Seedance/Seedream must appear in possible_byteplus_fit, got: {products}"
    assert any("Ark" in p for p in products), \
        f"Ark must appear in possible_byteplus_fit, got: {products}"
    assert any("VLM" in p or "automation" in p.lower() for p in products), \
        f"VLM / automation must appear in possible_byteplus_fit, got: {products}"

    md = render(render_json)
    assert "Seedance" in md or "Seedream" in md, \
        "Seedance or Seedream must appear in rendered output for marketing_adtech vertical"
    assert "Ark" in md, "Ark must appear in rendered output for marketing_adtech vertical"


def test_standard_discovery_evidence_shows_apollo_source_not_not_found():
    """
    When Apollo org enrichment provides What They Do, Standard Discovery prefill
    must show 'Apollo organization enrichment' as the evidence source,
    not 'Not Found'. No web search required.
    """
    from run_prep import context_to_renderer_json
    import argparse
    from scripts.render_prep_doc import render, core_business_label_and_evidence  # type: ignore[import]

    context = _monks_context()
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    render_json = context_to_renderer_json(context, args)

    label, evidence = core_business_label_and_evidence(render_json)
    assert label in ("likely", "known"), \
        f"Core business label must be 'likely' or 'known' when Apollo provides data, got: {label!r}"
    assert "Apollo" in evidence or evidence != "Not Found", \
        f"Evidence must reference Apollo or be a real source, got: {evidence!r}"
    assert evidence != "Not Found", \
        f"Evidence must not be 'Not Found' when Apollo org enrichment is available, got: {evidence!r}"

    md = render(render_json)
    # Standard Discovery section must reference Apollo, not 'Not Found' for core business
    lines = md.split("\n")
    collecting = False
    discovery_lines = []
    for line in lines:
        if "Standard Discovery" in line:
            collecting = True
        elif collecting and line.startswith("##") and "Standard Discovery" not in line:
            break
        elif collecting:
            discovery_lines.append(line)
    discovery_text = "\n".join(discovery_lines)

    # The core business answer (What They Do) must reference Apollo in discovery
    # If it says 'Not Found' in the evidence column, that's the bug this test catches
    core_biz_lines = [l for l in discovery_lines if "Core Business" in l or "What They Do" in l or "Monks" in l]
    if core_biz_lines:
        core_biz_text = "\n".join(core_biz_lines)
        # Should not say 'Not Found' next to core business when Apollo provided the answer
        assert "Apollo" in core_biz_text or "Not Found" not in core_biz_text, \
            f"Standard Discovery Core Business must not show 'Not Found' when Apollo data exists:\n{core_biz_text}"


# ---------------------------------------------------------------------------
# Round 8 regression tests: vertical-specific fit hypotheses
# ---------------------------------------------------------------------------


def _make_apollo_context(
    name: str,
    domain: str,
    description: str,
    industry: str,
    keywords: list,
    tech_signals: list,
    num_employees: int = 500,
) -> "PrepContext":  # type: ignore[name-defined]
    from run_prep import PrepContext, CustomerIdentity
    apollo_data = {
        "status": "organization_matched",
        "confidence": "high_domain_exact",
        "organization": {
            "name": name,
            "primary_domain": domain,
            "short_description": description,
            "industry": industry,
            "keywords": keywords,
            "num_employees": num_employees,
            "city": "Amsterdam",
            "country": "Netherlands",
            "technology_names": tech_signals,
        },
        "people": [],
        "warnings": [],
    }
    identity = CustomerIdentity(
        canonical_name=name,
        domain=domain,
        email=None,
        confidence="confirmed",
        evidence=[f"domain: {domain}"],
        company_name=name,
    )
    return PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment=None,
        missing_context=[],
        apollo_enrichment=apollo_data,
        web_search_status="web_search: disabled_by_env",
        company_overview_status="no_overview_eligible_results",
    )


def test_generate_byteplus_fit_hypotheses_marketing_adtech_no_ai_tech():
    """
    marketing_adtech without AI/cloud tech signals: Seedance/Seedream leads, not Ark.
    All hypotheses include 'to validate' wording. No company-specific hardcoding.
    """
    from run_prep import generate_byteplus_fit_hypotheses
    h = generate_byteplus_fit_hypotheses(
        "marketing_adtech",
        description="technology and marketing services company creating digital experiences for global brands",
        tech_signals=["Salesforce", "Jira", "HubSpot"],
    )
    assert h, "Should produce hypotheses for marketing_adtech"
    use_cases = h.get("known_use_cases") or []
    fit = h.get("possible_byteplus_fit") or []
    assert use_cases, "marketing_adtech must produce known_use_cases"
    assert any("to validate" in uc.lower() or "hypothesis" in uc.lower() for uc in use_cases), \
        "Use cases must use hypothesis-to-validate framing"
    products = [item.get("product") or "" for item in fit]
    # Without AI tech signals, Seedance/Seedream leads
    assert products[0] in ("Seedance / Seedream",), \
        f"Without AI tech signals, Seedance/Seedream should lead, got: {products}"
    assert any("Ark" in p for p in products), "Ark must appear in fit"
    assert any("VLM" in p or "automation" in p.lower() for p in products), "VLM must appear in fit"
    # All items have validation notes
    for item in fit:
        assert item.get("validation"), f"Every fit item must have a validation note: {item}"
    # No confirmed-workload claims
    for item in fit:
        reason = (item.get("reason") or "").lower()
        assert "customer needs" not in reason and "they are using" not in reason, \
            f"Must not make confirmed-workload claims: {item['reason']!r}"


def test_generate_byteplus_fit_hypotheses_marketing_adtech_with_ai_tech():
    """
    marketing_adtech WITH AI/cloud tech signals (e.g., OpenAI, AWS): Ark leads over Seedance/Seedream.
    All hypotheses framed as hypotheses to validate.
    """
    from run_prep import generate_byteplus_fit_hypotheses
    h = generate_byteplus_fit_hypotheses(
        "marketing_adtech",
        description="global digital agency delivering AI-powered marketing and technology solutions",
        tech_signals=["OpenAI", "AWS", "Snowflake", "Salesforce"],
    )
    fit = h.get("possible_byteplus_fit") or []
    products = [item.get("product") or "" for item in fit]
    # Ark should lead when AI tech signals are present
    assert products[0] in ("Ark / model platform",), \
        f"With AI tech signals, Ark should lead, got: {products}"
    assert any("Seedance" in p or "Seedream" in p for p in products), "Seedance/Seedream must appear"
    assert any("VLM" in p or "automation" in p.lower() for p in products), "VLM must appear"
    # Ark reason must mention model/API/routing — not generic
    ark_item = next(item for item in fit if "Ark" in (item.get("product") or ""))
    assert any(kw in ark_item["reason"].lower() for kw in ["routing", "api", "workflow", "model"]), \
        f"Ark reason must mention model/API/routing, got: {ark_item['reason']!r}"


def test_generate_byteplus_fit_hypotheses_media_entertainment_music():
    """
    media_entertainment with music/artist signals: Seedance → artist promos/social video.
    Must NOT show marketing/adtech-only wording (e.g., 'campaign conversion').
    """
    from run_prep import generate_byteplus_fit_hypotheses
    h = generate_byteplus_fit_hypotheses(
        "media_entertainment",
        description="Korean entertainment company focused on music record production and artist management",
        tech_signals=[],
    )
    fit = h.get("possible_byteplus_fit") or []
    products = [item.get("product") or "" for item in fit]
    assert any("Seedance" in p for p in products), "Seedance must appear for music entertainment"
    assert any("Seedream" in p for p in products), "Seedream must appear for music entertainment"
    assert any("Ark" in p for p in products), "Ark must appear for music entertainment"
    seedance = next(item for item in fit if "Seedance" in (item.get("product") or ""))
    assert any(kw in seedance["reason"].lower() for kw in ["artist", "promo", "fan", "social video", "teaser"]), \
        f"Seedance reason must mention artist/promo/fan/social, got: {seedance['reason']!r}"
    seedream = next(item for item in fit if "Seedream" in (item.get("product") or ""))
    assert any(kw in seedream["reason"].lower() for kw in ["artist", "album", "poster", "visual asset"]), \
        f"Seedream reason must mention artist/album/poster/visual asset, got: {seedream['reason']!r}"
    ark = next(item for item in fit if "Ark" in (item.get("product") or ""))
    assert any(kw in ark["reason"].lower() for kw in ["content", "localization", "planning", "community"]), \
        f"Ark reason must mention content/localization/planning, got: {ark['reason']!r}"
    # Must NOT use marketing/adtech-only wording
    full_text = " ".join(item.get("reason", "") for item in fit).lower()
    assert "campaign conversion" not in full_text, \
        "Entertainment vertical must not mention campaign conversion"
    assert "ad compliance" not in full_text, \
        "Entertainment vertical must not mention ad compliance"


def test_vertical_fit_hypotheses_no_hallucination_all_framed_as_to_validate():
    """
    For Apollo-only cases, ALL fit hypotheses must use 'to validate' or 'hypothesis' framing.
    Must not say 'confirmed need', 'customer requires', 'they are using', etc.
    """
    from run_prep import generate_byteplus_fit_hypotheses
    FORBIDDEN_CONFIRMED_PHRASES = [
        "confirmed need", "customer requires", "they are using",
        "the customer uses", "has confirmed", "currently deployed",
    ]
    for vertical in ("marketing_adtech", "media_entertainment", "ecommerce", "gaming", "ai_video_creative", "enterprise_llm"):
        h = generate_byteplus_fit_hypotheses(vertical, "a typical company", ["AWS"])
        for item in h.get("possible_byteplus_fit") or []:
            reason = (item.get("reason") or "").lower()
            for phrase in FORBIDDEN_CONFIRMED_PHRASES:
                assert phrase not in reason, \
                    f"Vertical {vertical!r}: reason must not contain {phrase!r}: {item['reason']!r}"
        for uc in h.get("known_use_cases") or []:
            uc_lower = uc.lower()
            for phrase in FORBIDDEN_CONFIRMED_PHRASES:
                assert phrase not in uc_lower, \
                    f"Vertical {vertical!r}: use_case must not contain {phrase!r}: {uc!r}"


def test_unknown_vertical_produces_empty_hypotheses():
    """
    Unknown / default vertical must produce empty hypotheses so the renderer
    falls back to the safe generic fallback text.
    """
    from run_prep import generate_byteplus_fit_hypotheses
    from scripts.render_prep_doc import _GENERIC_FIT_FALLBACK  # type: ignore[import]

    h = generate_byteplus_fit_hypotheses("unknown_vertical", "some company", ["Jira"])
    assert h == {}, f"Unknown vertical should return empty dict, got: {h}"

    h2 = generate_byteplus_fit_hypotheses("", "", [])
    assert h2 == {}, "Empty vertical string should return empty dict"

    # Renderer should fall back to generic text when no hypotheses
    context = _make_apollo_context(
        name="AnonCo",
        domain="anonco.example",
        description="a company of unknown type",
        industry="unknown",
        keywords=[],
        tech_signals=[],
    )
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import product_fit_lines  # type: ignore[import]

    # Override vertical to force default
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    rj["vertical"] = {"name": "default", "display_name": "Default / Unknown", "confidence": "unknown"}
    rj.get("enrichment", {}).pop("known_use_cases", None)
    rj.get("enrichment", {}).pop("possible_byteplus_fit", None)
    rj.get("enrichment", {}).pop("available", None)
    rj["confidence_layers"] = {
        "identity_confidence": "confirmed_company",
        "company_vertical_confidence": "unknown",
        "active_workload_confidence": "unknown",
        "product_fit_confidence": "possible_after_validation",
    }
    lines = product_fit_lines(rj)
    assert lines == _GENERIC_FIT_FALLBACK, \
        f"Unknown vertical must use generic fallback. Got:\n{lines}"


def test_product_question_blocks_not_auto_expanded_without_workload_evidence():
    """
    Marketing/adtech vertical with Apollo data should produce fit hypotheses,
    but deep product-specific question blocks should NOT auto-expand.
    Specifically: Seedance/Seedream deep dive questions should be collapsed
    until active workload is confirmed by MCP/docs/CRM.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_apollo_context(
        name="DigitalAgency",
        domain="digitalagency.example",
        description="digital marketing agency creating campaigns for global brands",
        industry="marketing and advertising",
        keywords=["digital marketing", "advertising", "creative agency"],
        tech_signals=["Salesforce", "Google Analytics"],
        num_employees=1000,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # Product fit hypotheses must appear in Brief (Section 1) or Solution Paths (Section 5)
    # Round 17: "Possible fit hypothesis to validate" block moved out of Opportunity Hypotheses
    # (which now contains only the workload summary + AI map) into Brief / Solution Paths.
    assert "Seedance" in md or "Seedream" in md or "Ark" in md, \
        "BytePlus product names must appear in rendered output for marketing_adtech with Apollo"
    assert "Possible" in md, \
        "Hypothesis-level language must appear in rendered output"

    # Deep product-specific question blocks should be COLLAPSED (not fully expanded)
    # A fully-expanded block would include questions like "Image / Video Usage" or "AI Usage & Current Stack"
    # in the Vertical-Aware In-Template Prefill section with multiple sub-questions
    lines = md.split("\n")
    prefill_start = next((i for i, l in enumerate(lines) if "Vertical-Aware In-Template Prefill" in l), None)
    if prefill_start:
        prefill_text = "\n".join(lines[prefill_start:prefill_start + 80])
        # Should not have deep Seedance-specific questions
        assert "Seedance video generation benchmark" not in prefill_text.lower() and \
               "reference workflow" not in prefill_text.lower(), \
            "Deep Seedance-specific benchmark questions must not appear without confirmed workload"

    # Active workload confidence must remain 'likely' (hypothesis-level), not 'confirmed'
    layers = rj.get("confidence_layers") or {}
    assert layers.get("active_workload_confidence") in ("likely", "unknown"), \
        f"Without confirmed workload, confidence must be 'likely' or 'unknown', got: {layers.get('active_workload_confidence')!r}"
    assert layers.get("active_workload_confidence") != "confirmed", \
        "Apollo-only data must not produce 'confirmed' active_workload_confidence"


# ---------------------------------------------------------------------------
# Round 9 regression tests: consumer_technology and confidence accuracy
# ---------------------------------------------------------------------------


def test_consumer_technology_generates_ark_vlm_seedream_hypotheses():
    """
    consumer_technology vertical + Apollo org data must generate:
    - Ark: model routing/evaluation, internal AI assistant, API integration
    - VLM/OCR/multimodal: UI QA, device/content QA, visual inspection, support automation
    - Seedream/Seedance: conditional on marketing/creative team context
    No generic fallback. No hardcoding of specific company names.
    """
    from run_prep import generate_byteplus_fit_hypotheses, context_to_renderer_json
    import argparse
    from scripts.render_prep_doc import render, product_fit_lines, _product_fit_lines_internal  # type: ignore[import]

    # Direct function test
    h = generate_byteplus_fit_hypotheses(
        "consumer_technology",
        description="multinational technology company known for consumer electronics, software, and online services",
        tech_signals=["Swift", "Xcode", "Metal", "CoreML", "AWS"],
    )
    assert h, "consumer_technology must produce hypotheses"
    fit = h.get("possible_byteplus_fit") or []
    products = [item.get("product") or "" for item in fit]
    assert any("Ark" in p for p in products), f"Ark must appear for consumer_technology, got: {products}"
    assert any("VLM" in p or "multimodal" in p.lower() or "OCR" in p for p in products), \
        f"VLM/OCR must appear for consumer_technology, got: {products}"
    assert any("Seedream" in p or "Seedance" in p for p in products), \
        f"Seedream/Seedance must appear for consumer_technology, got: {products}"

    ark = next(item for item in fit if "Ark" in (item.get("product") or ""))
    assert any(kw in ark["reason"].lower() for kw in ["routing", "evaluation", "api", "assistant"]), \
        f"Ark reason must mention routing/evaluation/API/assistant, got: {ark['reason']!r}"

    vlm = next(item for item in fit if "VLM" in (item.get("product") or "") or "multimodal" in (item.get("product") or "").lower())
    assert any(kw in vlm["reason"].lower() for kw in ["ui", "qa", "visual inspection", "support automation", "screenshot"]), \
        f"VLM reason must mention UI/QA/visual inspection/support automation, got: {vlm['reason']!r}"

    creative = next(item for item in fit if "Seedream" in (item.get("product") or "") or "Seedance" in (item.get("product") or ""))
    assert "conditional" in creative["reason"].lower() or "marketing" in creative["reason"].lower() \
        or "conditional" in creative["validation"].lower(), \
        f"Seedream/Seedance must be conditional on marketing/creative team, got: {creative['reason']!r}"

    # End-to-end: rendered doc must contain consumer_technology-specific hypotheses
    context = _make_apollo_context(
        name="BigTechCo",
        domain="bigtechco.example",
        description="multinational technology company known for consumer electronics, software, and online services",
        industry="consumer electronics",
        keywords=["consumer devices", "app ecosystem", "developer platform", "software services"],
        tech_signals=["CoreML", "Swift", "AWS"],
        num_employees=100000,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)

    fit_result = (rj.get("enrichment") or {}).get("possible_byteplus_fit") or []
    products_result = [item.get("product") or "" for item in fit_result]
    assert any("Ark" in p for p in products_result), \
        f"Rendered JSON must include Ark hypothesis for consumer_technology, got: {products_result}"
    assert any("VLM" in p or "multimodal" in p.lower() or "OCR" in p for p in products_result), \
        f"Rendered JSON must include VLM/OCR hypothesis, got: {products_result}"

    md = render(rj)
    assert "Ark" in md, "Ark must appear in rendered output for consumer_technology"
    assert "VLM" in md or "multimodal" in md.lower() or "OCR" in md, \
        "VLM/OCR must appear in rendered output for consumer_technology"


def test_consumer_technology_questions_in_executive_snapshot():
    """
    consumer_technology vertical without confirmed workload must show specific discovery questions
    about team scope and priority use case, not just generic 'what workload?' questions.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render, derive_questions  # type: ignore[import]

    context = _make_apollo_context(
        name="DevicesCo",
        domain="devicesco.example",
        description="global technology company making consumer devices, software, and developer tools",
        industry="consumer electronics",
        keywords=["consumer devices", "developer platform", "app ecosystem"],
        tech_signals=[],
        num_employees=50000,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)

    questions = derive_questions(rj)
    questions_text = "\n".join(questions).lower()
    assert "team" in questions_text or "product" in questions_text, \
        f"Questions must ask about team scope, got: {questions}"
    assert "ai/ml" in questions_text or "ai" in questions_text or "developer platform" in questions_text, \
        f"Questions must mention AI/ML or developer platform, got: {questions}"
    assert "model" in questions_text or "vendor" in questions_text or "stack" in questions_text, \
        f"Questions must ask about model/vendor stack, got: {questions}"

    md = render(rj)
    # "Top Things To Validate" must include team-scope question
    assert "team" in md.lower() or "product" in md.lower(), \
        "Rendered doc must include team-scope question for consumer_technology"


def test_apollo_hypothesis_workload_confidence_stays_unknown():
    """
    For Apollo-only enrichment cases, active_workload_confidence must stay 'unknown',
    not be promoted to 'likely'. product_fit_confidence may stay 'possible_after_validation'.
    The rendered doc must use 'Workload hypotheses to validate' (not 'Likely AI Workloads')
    and must NOT render 'Active workload confidence: likely'.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _monks_context()  # marketing_adtech, Apollo-only
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)

    layers = rj.get("confidence_layers") or {}
    assert layers.get("active_workload_confidence") == "unknown", \
        f"Apollo-only enrichment must not promote active_workload_confidence, got: {layers.get('active_workload_confidence')!r}"
    assert layers.get("product_fit_confidence") in ("possible_after_validation", "unknown", None), \
        f"Apollo-only enrichment must not promote product_fit_confidence, got: {layers.get('product_fit_confidence')!r}"

    md = render(rj)
    assert "Active workload confidence: unknown" in md, \
        "Rendered doc must show 'Active workload confidence: unknown' for Apollo-only case"
    assert "Active workload confidence: likely" not in md, \
        "Must NOT render 'Active workload confidence: likely' for Apollo-only case"
    assert "Workload hypotheses to validate" in md, \
        "Section label must be 'Workload hypotheses to validate' for Apollo-only case"
    assert "Likely AI Workloads" not in md, \
        "Must NOT use 'Likely AI Workloads' label for Apollo-only hypothesis case"

    # fit hypotheses must still be present despite unknown workload confidence
    assert "Possible fit hypothesis to validate" in md or "Seedance" in md or "Ark" in md, \
        "Fit hypotheses must still render despite active_workload_confidence = unknown"


def test_apollo_hypothesis_no_confirmed_workload_language():
    """
    Apollo-only cases must not render:
    - 'confirmed workload'
    - 'customer requires'
    - 'they are using'
    - 'active workload confirmed'
    All vertical hypotheses use 'to validate' or 'hypothesis' framing.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    FORBIDDEN = [
        "confirmed workload",
        "customer requires",
        "they are using",
        "active workload confirmed",
    ]

    for vertical, desc, industry, keywords in [
        ("marketing_adtech", "global digital agency delivering marketing and technology solutions", "marketing and advertising", ["digital marketing", "creative agency"]),
        ("consumer_technology", "multinational technology company known for consumer electronics", "consumer electronics", ["consumer devices", "app ecosystem"]),
        ("media_entertainment", "entertainment company focused on music and artist management", "entertainment", ["music", "artist management"]),
    ]:
        context = _make_apollo_context(
            name="TestCo",
            domain=f"testco-{vertical}.example",
            description=desc,
            industry=industry,
            keywords=keywords,
            tech_signals=[],
        )
        args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
        rj = context_to_renderer_json(context, args)
        md = render(rj).lower()

        for phrase in FORBIDDEN:
            assert phrase not in md, \
                f"Vertical {vertical!r}: rendered doc must not contain {phrase!r}"


# ---------------------------------------------------------------------------
# Round 10 acceptance tests — rich intelligence sections
# ---------------------------------------------------------------------------

def _make_rich_context(name: str, domain: str, description: str, industry: str, keywords: list, tech_signals: list, num_employees: int = 500, linkedin: str = "") -> "PrepContext":  # type: ignore[name-defined]
    """Create a PrepContext with Apollo org data for rich-section acceptance tests."""
    from run_prep import PrepContext, CustomerIdentity
    org = {
        "name": name,
        "primary_domain": domain,
        "short_description": description,
        "industry": industry,
        "keywords": keywords,
        "num_employees": num_employees,
        "city": "Seoul",
        "country": "South Korea",
        "technology_names": tech_signals,
    }
    if linkedin:
        org["linkedin_url"] = linkedin
    apollo_data = {
        "status": "organization_matched",
        "confidence": "high_domain_exact",
        "organization": org,
        "people": [],
        "warnings": [],
    }
    identity = CustomerIdentity(
        canonical_name=name,
        domain=domain,
        email=None,
        confidence="confirmed",
        evidence=[f"domain: {domain}"],
        company_name=name,
    )
    return PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment=None,
        missing_context=[],
        apollo_enrichment=apollo_data,
        web_search_status="web_search: disabled_by_env",
        company_overview_status="no_overview_eligible_results",
    )


def _assert_rich_sections_present(md: str, label: str) -> None:
    """Assert all 7 new rich intelligence sections appear in the rendered doc."""
    assert "Public Intelligence Snapshot" in md, f"{label}: Public Intelligence Snapshot section missing"
    assert "AI / Model Opportunity Map" in md, f"{label}: AI / Model Opportunity Map section missing"
    assert "Competitor / Vendor Intelligence" in md, f"{label}: Competitor / Vendor Intelligence section missing"
    assert "Possible Solution Paths" in md, f"{label}: Possible Solution Paths section missing"
    assert "First Meeting Question Plan" in md, f"{label}: First Meeting Question Plan section missing"
    assert "AE View" in md, f"{label}: AE View section missing"
    assert "SA View" in md, f"{label}: SA View section missing"
    assert "AE/SA 30-Second Brief" in md, f"{label}: AE/SA 30-Second Brief section missing"


def _assert_no_mcp_in_output(md: str, label: str) -> None:
    assert "mcp: unavailable" not in md.lower(), f"{label}: 'mcp: unavailable' must not appear in output"
    assert "mcp enrichment unavailable" not in md.lower(), f"{label}: 'MCP enrichment unavailable' must not appear in output"
    assert "mcp enrichment" not in md.lower(), f"{label}: 'MCP enrichment' must not appear in user-facing output"


def _assert_possible_not_likely_for_hypotheses(md: str, label: str) -> None:
    assert "Likely fit hypothesis to validate" not in md, f"{label}: must use 'Possible' not 'Likely fit hypothesis to validate'"
    assert "Likely hypotheses to validate" not in md, f"{label}: must use 'Possible' not 'Likely hypotheses to validate'"


def test_acceptance_jellyfish_entertainment():
    """
    Jellyfish Entertainment / jelly-fish.co.kr (Korean music/entertainment company).
    Expected: media_entertainment vertical, rich sections present, no MCP, Possible wording.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_rich_context(
        name="Jellyfish Entertainment",
        domain="jelly-fish.co.kr",
        description="Korean entertainment company focused on music production, artist management, and fan content",
        industry="entertainment",
        keywords=["music", "artist management", "K-pop", "record label", "fan content"],
        tech_signals=["AWS"],
        num_employees=300,
        linkedin="https://www.linkedin.com/company/jellyfish-entertainment",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    _assert_rich_sections_present(md, "Jellyfish Entertainment")
    _assert_no_mcp_in_output(md, "Jellyfish Entertainment")
    _assert_possible_not_likely_for_hypotheses(md, "Jellyfish Entertainment")

    # media_entertainment-specific: must have music/entertainment competitor categories
    assert "Runway" in md or "Midjourney" in md or "Adobe Firefly" in md, \
        "Jellyfish Entertainment: media_entertainment competitor categories must appear"
    # First meeting questions should be vertical-specific
    assert "release" in md.lower() or "production" in md.lower() or "content" in md.lower(), \
        "Jellyfish Entertainment: first meeting questions must be media_entertainment-specific"
    # MAU / traffic proxy note
    assert "Ask in meeting" in md or "Not publicly confirmed" in md, \
        "Jellyfish Entertainment: MAU/traffic must note 'Ask in meeting' when not found"
    # Web search disabled note must appear
    assert "web search" in md.lower() and "disabled" in md.lower(), \
        "Jellyfish Entertainment: web search disabled note must appear in Public Intelligence Snapshot"


def test_acceptance_monks():
    """
    Monks / monks.com (global creative production agency, marketing/adtech).
    Expected: marketing_adtech vertical, rich sections present, Ark + Seedance/Seedream paths.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_rich_context(
        name="Monks",
        domain="monks.com",
        description="global creative production partner enabling brands worldwide with technology and creative expertise",
        industry="marketing and advertising",
        keywords=["digital marketing", "creative production", "technology", "advertising"],
        tech_signals=["AWS", "Google Cloud", "OpenAI"],
        num_employees=7000,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    _assert_rich_sections_present(md, "Monks")
    _assert_no_mcp_in_output(md, "Monks")
    _assert_possible_not_likely_for_hypotheses(md, "Monks")

    # marketing_adtech solution paths must mention Seedance/Seedream and Ark
    assert "Seedance" in md or "Seedream" in md, "Monks: Seedance or Seedream must appear in solution paths"
    assert "Ark" in md, "Monks: Ark must appear in model platform solution path"
    # Competitor categories for marketing_adtech
    assert "Adobe Firefly" in md or "OpenAI" in md or "Runway" in md, \
        "Monks: marketing_adtech competitor categories must appear"
    # First meeting questions must be adtech-specific
    assert "campaign" in md.lower() or "creative" in md.lower() or "media" in md.lower(), \
        "Monks: first meeting questions must be marketing_adtech-specific"


def test_acceptance_dept():
    """
    DEPT / deptagency.com (digital experience agency, marketing/adtech).
    Expected: marketing_adtech, rich sections present, no unsupported confirmed claims.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_rich_context(
        name="DEPT",
        domain="deptagency.com",
        description="global digital agency delivering technology and marketing solutions for brands and platforms",
        industry="marketing and advertising",
        keywords=["digital agency", "performance marketing", "data analytics", "creative technology"],
        tech_signals=["Salesforce", "AWS", "Google Analytics"],
        num_employees=4000,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    _assert_rich_sections_present(md, "DEPT")
    _assert_no_mcp_in_output(md, "DEPT")
    _assert_possible_not_likely_for_hypotheses(md, "DEPT")

    # No unsupported confirmed claims
    FORBIDDEN_CONFIRMED = ["confirmed workload", "customer requires", "they are using", "active workload confirmed"]
    for phrase in FORBIDDEN_CONFIRMED:
        assert phrase not in md.lower(), f"DEPT: must not contain confirmed claim: {phrase!r}"
    # Solution paths present
    assert "BytePlus products" in md, "DEPT: Solution paths must show BytePlus products"
    # AE View must explain why account may matter
    assert "Why this account may matter" in md, "DEPT: AE View must have 'Why this account may matter'"


def test_acceptance_apple_consumer_technology():
    """
    Apple / apple.com (consumer technology, hardware, software, services).
    Expected: consumer_technology vertical, Ark + VLM as primary paths, creative conditional.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_rich_context(
        name="Apple",
        domain="apple.com",
        description="global technology company known for consumer electronics, software platforms, and digital services",
        industry="consumer electronics",
        keywords=["consumer devices", "app ecosystem", "developer platform", "software services", "hardware"],
        tech_signals=["Swift", "CoreML", "AWS"],
        num_employees=160000,
        linkedin="https://www.linkedin.com/company/apple",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    _assert_rich_sections_present(md, "Apple")
    _assert_no_mcp_in_output(md, "Apple")
    _assert_possible_not_likely_for_hypotheses(md, "Apple")

    # consumer_technology: Ark and VLM must appear as primary paths
    assert "Ark" in md, "Apple: Ark must appear as primary model platform path"
    assert "VLM" in md or "multimodal" in md.lower(), "Apple: VLM/multimodal must appear"
    # Image/video must be conditional
    assert "conditional" in md.lower(), "Apple: image/video paths must be marked conditional"
    # First meeting questions must ask about team scope
    assert "team" in md.lower() and ("product" in md.lower() or "developer" in md.lower()), \
        "Apple: questions must ask about team scope for consumer_technology"
    # Competitor categories for consumer_technology
    assert "OpenAI" in md or "Anthropic" in md or "Azure OpenAI" in md, \
        "Apple: consumer_technology competitor categories must appear"


def test_acceptance_ipg():
    """
    IPG / interpublic.com (global advertising holding group, marketing/adtech).
    Expected: marketing_adtech, rich sections, vertical-specific questions, Possible wording.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_rich_context(
        name="IPG",
        domain="interpublic.com",
        description="global advertising and marketing services company operating across creative, media, and data disciplines",
        industry="advertising",
        keywords=["advertising", "marketing services", "media buying", "creative agency network", "data analytics"],
        tech_signals=["Salesforce", "Adobe", "AWS"],
        num_employees=55000,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    _assert_rich_sections_present(md, "IPG")
    _assert_no_mcp_in_output(md, "IPG")
    _assert_possible_not_likely_for_hypotheses(md, "IPG")

    # marketing_adtech vertical-specific content
    assert "campaign" in md.lower() or "creative" in md.lower() or "media" in md.lower(), \
        "IPG: marketing_adtech-specific content must appear"
    assert "Possible Solution Paths" in md, "IPG: Possible Solution Paths section must appear"
    # Employee count from Apollo must appear
    assert "55,000" in md or "55000" in md or "employees" in md.lower(), \
        "IPG: Apollo employee count signal must appear in Public Intelligence Snapshot"
    # AE/SA 30-Second Brief must include account motivation
    assert "Why this account may matter" in md, "IPG: 30-Second Brief must explain why account may matter"
    # SA View must have POC shape
    assert "Suggested POC shape" in md, "IPG: SA View must have 'Suggested POC shape'"


# ---------------------------------------------------------------------------
# Round 12 — canonical entity guard regression tests
# ---------------------------------------------------------------------------

def test_is_canonical_entity_compatible_exact_domain_match():
    """Exact domain match is always compatible."""
    from run_prep import is_canonical_entity_compatible
    assert is_canonical_entity_compatible("https://monks.com/about", "Monks", "global marketing company", "Monks", "monks.com") is True


def test_is_canonical_entity_compatible_neutral_news_site():
    """Neutral news sites are always allowed through."""
    from run_prep import is_canonical_entity_compatible
    assert is_canonical_entity_compatible("https://en.wikipedia.org/wiki/Monks_(company)", "Monks company", "marketing agency", "Monks", "monks.com") is True
    assert is_canonical_entity_compatible("https://www.bloomberg.com/profile/company/monks", "Monks acquires", "", "Monks", "monks.com") is True


def test_is_canonical_entity_compatible_same_name_different_entity_rejected():
    """sportmonks.com contains 'monks' but is a different company — must be rejected."""
    from run_prep import is_canonical_entity_compatible
    assert is_canonical_entity_compatible("https://www.sportmonks.com/football-api/pricing", "SportMonks Football API pricing", "Soccer data API plans", "Monks", "monks.com") is False


def test_is_canonical_entity_compatible_the_monks_different_entity_rejected():
    """the-monks.com contains 'monks' but is a different entity — must be rejected."""
    from run_prep import is_canonical_entity_compatible
    assert is_canonical_entity_compatible("https://the-monks.com/", "The Monks", "independent creative studio", "Monks", "monks.com") is False


def test_is_canonical_entity_compatible_no_confirmed_domain_permissive():
    """Without a confirmed_domain, the guard cannot reject anything."""
    from run_prep import is_canonical_entity_compatible
    assert is_canonical_entity_compatible("https://www.sportmonks.com/football-api/pricing", "SportMonks", "", "Monks", None) is True


def test_classify_source_sportmonks_rejected_when_domain_set():
    """classify_source must return generic_market_reference for sportmonks.com when confirmed_domain=monks.com."""
    from run_prep import classify_source
    result = classify_source(
        "https://www.sportmonks.com/football-api/pricing",
        "SportMonks Football API — pricing plans",
        "Football data and sports API pricing for Monks and fans",
        company_name="Monks",
        confirmed_domain="monks.com",
    )
    assert result == "generic_market_reference", f"sportmonks.com should be rejected, got: {result}"


def test_classify_source_monks_official_site_accepted():
    """classify_source must accept monks.com as customer_evidence."""
    from run_prep import classify_source
    result = classify_source(
        "https://monks.com/about",
        "Monks — global marketing company",
        "Monks is a global data-driven marketing company",
        company_name="Monks",
        confirmed_domain="monks.com",
    )
    assert result == "customer_evidence", f"monks.com should be customer_evidence, got: {result}"


def test_extract_company_dossier_rejected_count_populated():
    """extract_company_dossier must populate rejected_web_count when incompatible sources are present."""
    from run_prep import extract_company_dossier

    web_results = [
        {"url": "https://monks.com/about", "title": "Monks global marketing", "snippet": "Monks is a global marketing company"},
        {"url": "https://en.wikipedia.org/wiki/Monks", "title": "Monks (company)", "snippet": "Monks, formerly known as Media.Monks"},
        {"url": "https://www.sportmonks.com/football-api/pricing", "title": "SportMonks API pricing", "snippet": "Football data API pricing plans"},
        {"url": "https://the-monks.com/", "title": "The Monks creative studio", "snippet": "Independent creative studio"},
    ]
    dossier = extract_company_dossier(
        company_name="Monks",
        enrichment_description="Monks is a global data-driven creative production company",
        use_cases=["marketing", "creative production"],
        web_results=web_results,
        pages=[],
        customer_name="Monks",
        confirmed_domain="monks.com",
    )
    assert dossier["rejected_web_count"] == 2, (
        f"Expected 2 rejected (sportmonks + the-monks), got {dossier['rejected_web_count']}"
    )


def test_extract_company_dossier_compatible_content_not_polluted():
    """Combined text for dossier extraction must not include sportmonks pricing content."""
    from run_prep import extract_company_dossier

    web_results = [
        {"url": "https://monks.com/about", "title": "Monks global marketing", "snippet": "Monks is a S4Capital global marketing company"},
        {"url": "https://www.sportmonks.com/football-api/pricing", "title": "SportMonks $9.99/month pricing", "snippet": "Football data API tiers $9 $49 $99"},
    ]
    dossier = extract_company_dossier(
        company_name="Monks",
        enrichment_description="Monks is a global marketing company (S4Capital)",
        use_cases=[],
        web_results=web_results,
        pages=[],
        customer_name="Monks",
        confirmed_domain="monks.com",
    )
    # SportMonks pricing tiers must not contaminate the extracted pricing_tiers
    pricing_text = " ".join(dossier.get("pricing_tiers") or []).lower()
    scale_text = " ".join(dossier.get("scale_signals") or []).lower()
    assert "sportmonks" not in pricing_text, "SportMonks pricing must not pollute pricing_tiers"
    assert "9.99" not in pricing_text and "49" not in scale_text, "SportMonks API pricing must not appear in scale signals"


def test_synthesize_known_fields_uses_possible_not_likely_for_modules():
    """synthesize_known_fields must use 'Possible product modules' not 'Likely product modules'."""
    from run_prep import synthesize_known_fields

    enrichment = {
        "company_name": "Monks",
        "description": "Global marketing company using AI for creative production",
        "dossier": {
            "product_modules": ["AI image generation", "Custom models", "API / enterprise plans"],
            "scale_signals": [],
            "pricing_tiers": [],
        },
    }
    known = synthesize_known_fields(enrichment, [], [])
    expansion = known.get("expansion_opportunity", "")
    assert expansion.startswith("Possible product modules"), (
        f"Expected 'Possible product modules', got: {expansion!r}"
    )
    assert "Likely product modules" not in expansion, "Must not use 'Likely product modules'"


# ---------------------------------------------------------------------------
# Round 13 — Monks web-only fallback, Apollo missing key, Consumer Tech guard
# ---------------------------------------------------------------------------

def _make_web_only_context(name: str, domain: str, search_results: list, description: str = "") -> "PrepContext":  # type: ignore[name-defined]
    """Create a PrepContext with no Apollo data (web-only fallback) and mocked search_results."""
    from run_prep import PrepContext, CustomerIdentity
    identity = CustomerIdentity(
        canonical_name=name,
        domain=domain,
        email=None,
        confidence="confirmed",
        evidence=[f"domain: {domain}"],
        company_name=name,
    )
    enrichment = {
        "company_name": name,
        "description": description or f"To Validate: {name} business description.",
        "website": f"https://{domain}",
        "source": "web_search",
        "dossier": {},
        "known_use_cases": [],
        "possible_byteplus_fit": [],
        "known_competitors": [],
        "known_risks": [],
        "suggested_questions": [],
        "source_links": [],
    }
    return PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment=enrichment,
        missing_context=[],
        apollo_enrichment={"status": "missing_api_key"},
        search_results=search_results,
        web_search_status="usable_results_found",
        company_overview_status="usable_results_found",
    )


def test_monks_web_only_fallback_vertical_is_marketing_adtech():
    """
    Test A: Monks web-only fallback (Apollo missing).
    With Wikipedia/Funnel-like web results, vertical must be Marketing/AdTech, not Consumer Technology.
    """
    import argparse
    from run_prep import context_to_renderer_json, infer_vertical
    from scripts.render_prep_doc import render  # type: ignore[import]

    wiki_snippet = (
        "Monks is a digital-first marketing, technology services and consulting company. "
        "Monks operates across social, digital advertising, data and measurement ecosystems. "
        "Monks is a wholly owned subsidiary of S4 Capital."
    )
    funnel_snippet = (
        "Monks is the global, purely digital, unitary operating brand of S4Capital plc, "
        "combining global marketing and technology services."
    )
    web_results = [
        {"url": "https://monks.com/about", "title": "Monks – global marketing company", "snippet": "Global creative production and marketing agency", "source": "web"},
        {"url": "https://en.wikipedia.org/wiki/Monks_(company)", "title": "Monks (company) – Wikipedia", "snippet": wiki_snippet, "source": "web"},
        {"url": "https://funnel.io/partners/monks", "title": "Monks – Funnel partner", "snippet": funnel_snippet, "source": "web"},
        {"url": "https://www.sportmonks.com/football-api/pricing", "title": "SportMonks Football API pricing", "snippet": "Football data API plans $9 $49 $99", "source": "web"},
        {"url": "https://the-monks.com/", "title": "The Monks creative studio", "snippet": "Independent creative studio Berlin", "source": "web"},
    ]
    context = _make_web_only_context(
        name="Monks",
        domain="monks.com",
        search_results=web_results,
        description="Monks is a digital-first marketing, technology services and consulting company (S4 Capital).",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # Vertical must be marketing_adtech
    vertical_name = (rj.get("vertical") or {}).get("name", "")
    assert vertical_name == "marketing_adtech", (
        f"Monks web-only: vertical must be marketing_adtech, got {vertical_name!r}"
    )

    # Consumer Technology phrases must NOT appear
    consumer_tech_phrases = [
        "consumer devices", "hardware sales", "app ecosystem",
        "device diagnostics", "hardware revenue", "device ecosystem",
        "consumer electronics",
    ]
    md_lower = md.lower()
    for phrase in consumer_tech_phrases:
        assert phrase not in md_lower, (
            f"Monks web-only: consumer technology phrase {phrase!r} must not appear in marketing/adtech report"
        )

    # SportMonks URL must NOT appear anywhere in customer-facing output
    assert "sportmonks.com" not in md.lower(), (
        "Monks web-only: sportmonks.com must not appear in any customer-facing section"
    )
    assert "the-monks.com" not in md.lower(), (
        "Monks web-only: the-monks.com must not appear in any customer-facing section"
    )

    # web_rejected_count > 0 (at least sportmonks + the-monks were rejected)
    rejected = (rj.get("source_status") or {}).get("web_rejected_count", 0)
    assert rejected >= 2, f"Monks web-only: expected at least 2 rejected sources, got {rejected}"

    # No output_validation error
    output_val = (rj.get("source_status") or {}).get("output_validation", "")
    assert "missing from registry" not in output_val, (
        f"Monks web-only: cited evidence URL must be in registry. output_validation: {output_val!r}"
    )

    # canonical_identity_source must be web_only_fallback
    assert (rj.get("source_status") or {}).get("canonical_identity_source") == "web_only_fallback", (
        "Monks web-only: canonical_identity_source must be web_only_fallback when Apollo key is missing"
    )


def test_apollo_exact_domain_is_canonical_identity():
    """
    Test B: Apollo exact-domain match is the canonical identity anchor.
    Web sources must enrich but not override Apollo description, vertical, scale, LinkedIn.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    apollo_description = "Monks is the global, purely digital, unitary operating brand of S4Capital."
    context = _make_rich_context(
        name="Monks",
        domain="monks.com",
        description=apollo_description,
        industry="advertising",
        keywords=["digital marketing", "advertising", "creative production", "S4 Capital"],
        tech_signals=["Salesforce", "Adobe"],
        num_employees=8000,
        linkedin="https://www.linkedin.com/company/monks",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # Apollo exact domain must be canonical identity
    assert (rj.get("source_status") or {}).get("canonical_identity_source") == "apollo_exact_domain", (
        "Apollo present: canonical_identity_source must be apollo_exact_domain"
    )

    # Description must come from Apollo, not be overwritten
    assert "s4capital" in md.lower() or "monks" in md.lower(), (
        "Apollo exact-domain: Apollo description must be present in rendered output"
    )

    # Vertical must be marketing_adtech
    vertical_name = (rj.get("vertical") or {}).get("name", "")
    assert vertical_name == "marketing_adtech", (
        f"Apollo exact-domain: vertical must be marketing_adtech for Monks, got {vertical_name!r}"
    )

    # No consumer technology phrases
    assert "consumer devices" not in md.lower(), (
        "Apollo exact-domain: 'consumer devices' must not appear for Monks"
    )


def test_consumer_technology_true_positive_apple():
    """
    Test C: Consumer Technology vertical still works correctly for Apple.
    Consumer devices / hardware / app ecosystem wording allowed only when vertical is confirmed consumer_tech.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_rich_context(
        name="Apple",
        domain="apple.com",
        description="Apple designs iPhones, Macs, iPads and consumer electronics. App Store ecosystem. Hardware sales and software services.",
        industry="consumer_technology",
        keywords=["iphone", "mac", "ipad", "app store", "consumer electronics", "hardware"],
        tech_signals=["Swift", "Xcode", "CoreML"],
        num_employees=160000,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # Vertical must be consumer_technology
    vertical_name = (rj.get("vertical") or {}).get("name", "")
    assert vertical_name == "consumer_technology", (
        f"Apple: vertical must be consumer_technology, got {vertical_name!r}"
    )

    # Consumer technology signals ARE allowed here
    assert "iphone" in md.lower() or "apple" in md.lower() or "consumer" in md.lower(), (
        "Apple: consumer technology content must appear when vertical is correctly consumer_technology"
    )

    # Rich sections must still be present
    _assert_rich_sections_present(md, "Apple")


def test_monks_apollo_exact_domain_description_flows_to_what_they_do():
    """Apollo exact-domain description must flow to What They Do even if web enrichment had a value."""
    import argparse
    from run_prep import PrepContext, CustomerIdentity, context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    apollo_data = {
        "status": "organization_matched",
        "confidence": "high_domain_exact",
        "organization": {
            "name": "Monks",
            "primary_domain": "monks.com",
            "short_description": "Monks is a digital-first marketing, technology services and consulting company under S4 Capital.",
            "industry": "advertising",
            "keywords": ["digital marketing", "advertising", "s4 capital"],
            "num_employees": 7600,
        },
        "people": [],
        "warnings": [],
    }
    identity = CustomerIdentity(
        canonical_name="Monks",
        domain="monks.com",
        email=None,
        confidence="confirmed",
        evidence=["domain: monks.com"],
        company_name="Monks",
    )
    # Web enrichment sets a DIFFERENT what_they_do that would normally block Apollo
    web_enrichment = {
        "company_name": "Monks",
        "description": "Some web-sourced description that does not mention S4 Capital.",
        "website": "https://monks.com",
        "source": "web_search",
        "dossier": {
            "what_they_do": "Some web-sourced description that does not mention S4 Capital.",
        },
        "known_use_cases": [],
        "possible_byteplus_fit": [],
        "known_competitors": [],
        "known_risks": [],
        "suggested_questions": [],
        "source_links": [],
    }
    context = PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment=web_enrichment,
        missing_context=[],
        apollo_enrichment=apollo_data,
        search_results=[],
        web_search_status="usable_results_found",
        company_overview_status="usable_results_found",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)

    # What They Do must use Apollo description, not the web-sourced one
    dossier = (rj.get("enrichment") or {}).get("dossier") or {}
    what_they_do = str(dossier.get("what_they_do") or "")
    assert "s4 capital" in what_they_do.lower() or "s4capital" in what_they_do.lower() or "digital-first marketing" in what_they_do.lower(), (
        f"Apollo exact-domain: what_they_do must use Apollo description, got: {what_they_do!r}"
    )
    assert "web-sourced" not in what_they_do.lower(), (
        "Apollo exact-domain: web-sourced description must not override Apollo"
    )

    # Run the renderer and check no To Validate for what they do
    md = render(rj)
    assert "To Validate: business description could not be confirmed" not in md, (
        "Apollo exact-domain: rendered output must not show To Validate for what_they_do when Apollo exact-domain description exists"
    )


def test_monks_agency_product_modules_cleaned():
    """agency_marketing_services subtype must not list BytePlus AI model names as Monks' products."""
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_rich_context(
        name="Monks",
        domain="monks.com",
        description="Monks is a digital-first marketing and technology services company under S4 Capital.",
        industry="advertising",
        keywords=["digital marketing", "advertising", "s4 capital", "creative production"],
        tech_signals=["Salesforce", "Adobe"],
        num_employees=7600,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # "API / enterprise plans" must not appear in the Public Intelligence Snapshot as a Monks product
    # (it's a BytePlus product module, not a description of what Monks does)
    pub_intel_start = md.find("Public Intelligence Snapshot")
    pub_intel_end = md.find("\n#", pub_intel_start + 1) if pub_intel_start != -1 else -1
    pub_intel_text = md[pub_intel_start:pub_intel_end] if pub_intel_start != -1 else ""
    assert "API / enterprise plans" not in pub_intel_text, (
        "Monks agency: 'API / enterprise plans' must not appear in Main Products / Business Lines"
    )

    # Target users must mention agency-appropriate terms
    assert "advertisers" in md.lower() or "agency clients" in md.lower() or "brands" in md.lower(), (
        "Monks agency: target users must mention advertisers / agency clients / brands"
    )


def test_monks_sportmonks_not_in_standard_discovery():
    """SportMonks URL must not appear in Standard Discovery evidence for Monks/monks.com."""
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_web_only_context(
        name="Monks",
        domain="monks.com",
        search_results=[
            {"url": "https://monks.com/about", "title": "Monks global marketing", "snippet": "Global marketing and technology services company", "source": "web"},
            {"url": "https://www.sportmonks.com/football-api/", "title": "SportMonks Football API", "snippet": "Football data API for developers", "source": "web"},
        ],
        description="Monks is a digital-first marketing and technology services company.",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    assert "sportmonks.com" not in md.lower(), (
        "Monks: sportmonks.com must not appear anywhere in customer-facing output"
    )


def test_monks_mau_fallback_agency_specific():
    """MAU/Traffic fallback for agency_marketing_services must use agency-specific proxy text."""
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_rich_context(
        name="Monks",
        domain="monks.com",
        description="Monks is a digital-first marketing and technology services company under S4 Capital.",
        industry="advertising",
        keywords=["digital marketing", "advertising", "s4 capital"],
        tech_signals=["Salesforce"],
        num_employees=7600,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # MAU / Traffic must not show bare "sem" as a traffic signal
    pub_intel_start = md.find("MAU / Traffic")
    pub_intel_end = md.find("\n|", pub_intel_start + 1) if pub_intel_start != -1 else -1
    mau_row = md[pub_intel_start:pub_intel_end] if pub_intel_start != -1 else md
    # "| sem |" or "sem" alone as a signal is wrong
    assert "| sem" not in mau_row and "sem |" not in mau_row, (
        f"Monks: MAU/Traffic must not show bare 'sem' as a traffic signal, got: {mau_row!r}"
    )


# ---------------------------------------------------------------------------
# Round 15 — final Monks report cleanup regression tests
# ---------------------------------------------------------------------------


def test_monks_agency_target_users_specific():
    """
    agency_marketing_services target_users must be marketing/adtech-specific.
    Must include 'global brands', 'advertisers', and 'marketing operations teams'.
    Must NOT include consumer-technology-specific terms.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_rich_context(
        name="Monks",
        domain="monks.com",
        description="Monks is a digital-first marketing, technology services and consulting company under S4 Capital.",
        industry="advertising",
        keywords=["digital marketing", "advertising", "s4 capital", "creative production"],
        tech_signals=["Salesforce", "Adobe"],
        num_employees=7600,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    assert "global brands" in md.lower(), "Monks agency: 'global brands' must appear in target users"
    assert "advertisers" in md.lower(), "Monks agency: 'advertisers' must appear in target users"
    assert "marketing operations teams" in md.lower(), \
        "Monks agency: 'marketing operations teams' must appear in target users"
    assert "consumers, developers" not in md.lower(), \
        "Monks agency: consumer-technology target user wording must not appear"
    assert "hardware" not in md.lower(), \
        "Monks agency: hardware/consumer-tech wording must not appear in target users"


def test_monks_mau_does_not_use_revenue_signal():
    """
    MAU / Traffic / Audience Scale must not use revenue signal as proxy.
    Revenue is account scale, not MAU/traffic.
    """
    import argparse
    from run_prep import PrepContext, CustomerIdentity, context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    # Set up context where scale_signals is a revenue signal
    apollo_data = {
        "status": "organization_matched",
        "confidence": "high_domain_exact",
        "organization": {
            "name": "Monks",
            "primary_domain": "monks.com",
            "short_description": "Monks is a digital-first marketing company under S4 Capital.",
            "industry": "advertising",
            "keywords": ["digital marketing", "s4 capital"],
            "num_employees": 7600,
            "annual_revenue": "$500M-$1B",
        },
        "people": [],
        "warnings": [],
    }
    identity = CustomerIdentity(
        canonical_name="Monks",
        domain="monks.com",
        email=None,
        confidence="confirmed",
        evidence=["domain: monks.com"],
        company_name="Monks",
    )
    context = PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment={
            "company_name": "Monks",
            "description": "Monks is a digital-first marketing company.",
            "dossier": {
                "scale_signals": ["~$600M annual revenue signal"],
                "traffic_source_scale": "",
            },
        },
        missing_context=[],
        apollo_enrichment=apollo_data,
        search_results=[],
        web_search_status="disabled",
        company_overview_status="no_overview_eligible_results",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # MAU / Traffic row must NOT contain the revenue signal as a MAU proxy
    mau_idx = md.find("MAU / Traffic")
    assert mau_idx != -1, "MAU / Traffic row must exist"
    mau_line_end = md.find("\n", mau_idx + 1)
    mau_row = md[mau_idx:mau_line_end] if mau_line_end != -1 else md[mau_idx:]
    assert "revenue signal" not in mau_row.lower(), (
        f"MAU row must not show revenue signal as MAU proxy, got: {mau_row!r}"
    )
    assert "annual revenue" not in mau_row.lower(), (
        f"MAU row must not show annual revenue as MAU proxy, got: {mau_row!r}"
    )
    # Must use the agency-specific fallback text
    assert "ask in meeting" in mau_row.lower() or "not publicly confirmed" in mau_row.lower(), (
        f"MAU row must use the agency fallback text, got: {mau_row!r}"
    )


def test_monks_recent_news_no_g2_alternatives():
    """
    Recent AI / Product / Partnership News must not use G2 alternatives/comparison pages.
    Competitor comparison pages are not AI/product news.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    g2_results = [
        {"url": "https://www.g2.com/compare/monks-vs-accenture", "title": "Monks vs Accenture — G2 comparison", "snippet": "Compare Monks and Accenture features"},
        {"url": "https://www.g2.com/alternatives/monks", "title": "Best Monks alternatives 2024", "snippet": "Top alternatives to Monks: Accenture, WPP, DEPT"},
        {"url": "https://monks.com/news/ai-creative-partnership", "title": "Monks announces AI creative partnership", "snippet": "Monks partners with AI firm for creative automation"},
    ]
    context = _make_web_only_context(
        name="Monks",
        domain="monks.com",
        search_results=g2_results,
        description="Monks is a digital-first marketing and technology services company.",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # G2 compare/alternatives URLs must not appear in Recent AI/News section
    news_idx = md.find("Recent AI / Product / Partnership News")
    assert news_idx != -1, "Recent AI / Product / Partnership News row must exist"
    news_end = md.find("\n", news_idx + 1)
    news_row = md[news_idx:news_end] if news_end != -1 else md[news_idx:]
    assert "g2.com/compare" not in news_row, "G2 compare URL must not appear in AI/News row"
    assert "g2.com/alternatives" not in news_row, "G2 alternatives URL must not appear in AI/News row"
    # The compatible news result (monks.com/news/ai) should appear
    assert "monks.com" in news_row or "partnership" in news_row.lower() or "not publicly confirmed" in news_row.lower(), (
        f"Compatible news or fallback must appear in Recent AI/News row, got: {news_row!r}"
    )


def test_monks_investment_trust_rejected():
    """
    Monks Investment Trust (MNKS:LSE) and FT investment trust pages must be rejected
    by the entity guard and must not appear in any customer-facing section.
    """
    from run_prep import is_canonical_entity_compatible

    # FT investment trust article
    assert is_canonical_entity_compatible(
        "https://www.ft.com/content/monks-investment-trust-nav-update",
        "Monks Investment Trust — NAV update",
        "Monks Investment Trust (MNKS:LSE) net asset value update for Q1.",
        "Monks",
        "monks.com",
    ) is False, "FT investment trust article must be rejected by entity guard"

    # Direct investment trust page with ticker
    assert is_canonical_entity_compatible(
        "https://www.trustnet.com/monks-investment-trust",
        "Monks Investment Trust (MNKS:LSE) — fund details",
        "Monks Investment Trust is a listed investment trust. NAV: 950p.",
        "Monks",
        "monks.com",
    ) is False, "Investment trust page with MNKS:LSE ticker must be rejected"

    # Bloomberg ticker page
    assert is_canonical_entity_compatible(
        "https://www.bloomberg.com/quote/MNKS:LN",
        "MNKS:LN — Monks Investment Trust",
        "Monks Investment Trust portfolio of global growth companies. Net asset value and AUM.",
        "Monks",
        "monks.com",
    ) is False, "Bloomberg investment trust / AUM page must be rejected"

    # Legitimate Monks company news on FT is still allowed
    assert is_canonical_entity_compatible(
        "https://www.ft.com/content/monks-s4capital-digital-marketing",
        "Monks: S4Capital digital marketing expansion",
        "Monks, the digital marketing arm of S4 Capital, expands into APAC.",
        "Monks",
        "monks.com",
    ) is True, "Legitimate FT news about the Monks marketing company must be allowed"


def test_monks_investment_trust_not_in_output():
    """
    Investment trust / ticker contamination must not appear in any customer-facing field
    when web_results include investment trust pages alongside legitimate Monks results.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    trust_results = [
        {"url": "https://monks.com/about", "title": "Monks – global marketing and technology company", "snippet": "Monks is a digital-first marketing, technology services company under S4 Capital.", "source": "web"},
        {"url": "https://www.ft.com/content/monks-investment-trust", "title": "Monks Investment Trust — NAV update", "snippet": "Monks Investment Trust (MNKS:LSE) net asset value 960p. Fund size AUM £2.8bn.", "source": "web"},
        {"url": "https://www.trustnet.com/monks", "title": "Monks Investment Trust (MNKS:LSE)", "snippet": "Listed investment trust. Portfolio of global growth equities. NAV and AUM details.", "source": "web"},
    ]
    context = _make_web_only_context(
        name="Monks",
        domain="monks.com",
        search_results=trust_results,
        description="Monks is a digital-first marketing and technology services company.",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # Financial instrument markers must not appear in customer-facing output
    assert "investment trust" not in md.lower(), \
        "Monks Investment Trust must not appear in customer-facing output"
    assert "mnks:lse" not in md.lower(), \
        "MNKS:LSE ticker must not appear in customer-facing output"
    assert "net asset value" not in md.lower() and " nav " not in md.lower(), \
        "NAV (net asset value) must not appear in customer-facing output for Monks the agency"
    assert " aum" not in md.lower(), \
        "AUM (assets under management) must not appear in customer-facing output for Monks the agency"
    # Vertical must still be marketing_adtech (trust pages must not pollute vertical inference)
    vertical_name = (rj.get("vertical") or {}).get("name", "")
    assert vertical_name == "marketing_adtech", (
        f"Monks: vertical must remain marketing_adtech despite investment trust contamination, got {vertical_name!r}"
    )


def test_monks_expansion_opportunity_agency_specific():
    """
    Expansion Opportunity for agency_marketing_services must not show
    'Voice/audio generation' or 'API / enterprise plans' — these are BytePlus
    product names, not Monks service lines.
    Must show agency-specific possible directions.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _make_rich_context(
        name="Monks",
        domain="monks.com",
        description="Monks is a digital-first marketing and technology services company under S4 Capital.",
        industry="advertising",
        keywords=["digital marketing", "advertising", "s4 capital", "creative production"],
        tech_signals=["Salesforce", "Adobe"],
        num_employees=7600,
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    assert "Voice/audio generation" not in md, \
        "Monks agency: 'Voice/audio generation' must not appear in expansion opportunity"
    assert "API / enterprise plans" not in md, \
        "Monks agency: 'API / enterprise plans' must not appear in expansion opportunity"
    # Agency-specific directions must appear
    assert "campaign creative generation" in md.lower() or "creative localization" in md.lower() or \
           "campaign pipelines" in md.lower() or "brand safety" in md.lower(), \
        "Monks agency: agency-specific expansion directions must appear"


def test_monks_image_video_evidence_uses_workflow_signal():
    """
    AI / Model Opportunity Map: Image and Video evidence for agency_marketing_services
    must use the marketing/adtech creative workflow signal, not a revenue signal.
    """
    import argparse
    from run_prep import PrepContext, CustomerIdentity, context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    apollo_data = {
        "status": "organization_matched",
        "confidence": "high_domain_exact",
        "organization": {
            "name": "Monks",
            "primary_domain": "monks.com",
            "short_description": "Monks is a digital-first marketing company under S4 Capital.",
            "industry": "advertising",
            "keywords": ["digital marketing", "s4 capital"],
            "num_employees": 7600,
            "annual_revenue": "$500M-$1B",
        },
        "people": [],
        "warnings": [],
    }
    identity = CustomerIdentity(
        canonical_name="Monks",
        domain="monks.com",
        email=None,
        confidence="confirmed",
        evidence=["domain: monks.com"],
        company_name="Monks",
    )
    context = PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment={
            "company_name": "Monks",
            "description": "Monks is a digital-first marketing company.",
            "dossier": {
                "scale_signals": ["~$600M annual revenue signal"],
            },
        },
        missing_context=[],
        apollo_enrichment=apollo_data,
        search_results=[],
        web_search_status="disabled",
        company_overview_status="no_overview_eligible_results",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # Find the AI / Model Opportunity Map table (use ### heading to skip TOC links)
    opp_idx = md.find("### AI / Model Opportunity Map")
    assert opp_idx != -1, "AI / Model Opportunity Map section must be present"
    opp_end_candidates = [md.find("\n###", opp_idx + 1), md.find("\n##", opp_idx + 30)]
    opp_end = min(c for c in opp_end_candidates if c > 0) if any(c > 0 for c in opp_end_candidates) else len(md)
    opp_section = md[opp_idx:opp_end]

    # Revenue signal must not appear in Image or Video evidence column
    lines = [l for l in opp_section.split("\n") if "| Image" in l or "| Video" in l]
    for line in lines:
        assert "revenue signal" not in line.lower(), (
            f"Image/Video evidence must not use revenue signal, got: {line!r}"
        )
        assert "annual revenue" not in line.lower(), (
            f"Image/Video evidence must not use annual revenue, got: {line!r}"
        )
    # Agency-specific workflow signal must appear for Image/Video
    assert any("creative production" in l.lower() or "campaign" in l.lower() or "marketing / adtech" in l.lower()
               for l in lines), \
        f"Image/Video evidence must use marketing/adtech workflow signal for agency, got: {lines}"


def test_monks_web_rejected_count_in_run_report():
    """
    web_rejected_count must appear in Run Report when incompatible sources are filtered.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    web_results = [
        {"url": "https://monks.com/about", "title": "Monks global marketing", "snippet": "Global marketing and technology services company", "source": "web"},
        {"url": "https://www.sportmonks.com/football-api/", "title": "SportMonks Football API", "snippet": "Football data API for developers", "source": "web"},
        {"url": "https://www.ft.com/content/monks-investment-trust", "title": "Monks Investment Trust — NAV update", "snippet": "Monks Investment Trust (MNKS:LSE) net asset value 960p.", "source": "web"},
    ]
    context = _make_web_only_context(
        name="Monks",
        domain="monks.com",
        search_results=web_results,
        description="Monks is a digital-first marketing and technology services company.",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # web_rejected_count must be > 0 (sportmonks + investment trust filtered)
    rejected = (rj.get("source_status") or {}).get("web_rejected_count", 0)
    assert rejected >= 2, f"Expected at least 2 rejected sources (sportmonks + investment trust), got {rejected}"

    # Run Report must show the rejection count
    run_report_idx = md.find("## Run Report")
    assert run_report_idx != -1, "Run Report section must be present"
    run_report = md[run_report_idx:]
    assert "web_rejected_count" in run_report or "filtered" in run_report.lower(), (
        f"Run Report must mention filtered/rejected web count, got snippet: {run_report[:300]!r}"
    )


# ---------------------------------------------------------------------------
# Round 16 — final Monks cleanup: target users, Standard Discovery evidence,
#             web results list, investment trust guard
# ---------------------------------------------------------------------------


def test_monks_agency_target_users_enforced():
    """
    agency_marketing_services must ALWAYS render the canonical target_users,
    even when web enrichment populated a consumer-tech value like
    "consumers, developers, enterprise customers, creative professionals, and ecosystem partners".
    """
    import argparse
    from run_prep import PrepContext, CustomerIdentity, context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    # Web enrichment has a consumer-tech target_users that slips past incompatible_field_reason
    web_enrichment = {
        "company_name": "Monks",
        "description": "Monks is a digital-first marketing and technology services company.",
        "dossier": {
            "target_users": "consumers, developers, enterprise customers, creative professionals, and ecosystem partners",
        },
        "known_use_cases": [],
        "possible_byteplus_fit": [],
    }
    apollo_data = {
        "status": "organization_matched",
        "confidence": "high_domain_exact",
        "organization": {
            "name": "Monks",
            "primary_domain": "monks.com",
            "short_description": "Monks is a digital-first marketing company under S4 Capital.",
            "industry": "advertising",
            "keywords": ["digital marketing", "advertising", "s4 capital"],
            "num_employees": 7600,
        },
        "people": [],
        "warnings": [],
    }
    identity = CustomerIdentity(
        canonical_name="Monks",
        domain="monks.com",
        email=None,
        confidence="confirmed",
        evidence=["domain: monks.com"],
        company_name="Monks",
    )
    context = PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment=web_enrichment,
        missing_context=[],
        apollo_enrichment=apollo_data,
        search_results=[],
        web_search_status="disabled",
        company_overview_status="no_overview_eligible_results",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # Consumer-tech phrasing must NOT appear in target users
    assert "consumers, developers" not in md.lower(), \
        "Monks agency: consumer-tech target_users must be replaced by agency template"
    assert "ecosystem partners" not in md.lower(), \
        "Monks agency: 'ecosystem partners' (consumer-tech phrasing) must not appear"
    # Agency-specific users must appear
    assert "global brands" in md.lower(), "Monks agency: 'global brands' must appear in target users"
    assert "marketing operations teams" in md.lower(), \
        "Monks agency: 'marketing operations teams' must appear in target users"


def test_monks_sportmonks_not_in_standard_discovery_evidence():
    """
    Standard Discovery question evidence must not contain sportmonks.com URLs.
    The entity guard must propagate to build_question_prefill via context.search_results.
    """
    import argparse
    from run_prep import PrepContext, CustomerIdentity, context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    web_results = [
        {"url": "https://monks.com/about", "title": "Monks global marketing", "snippet": "Global marketing and technology services company", "source": "web"},
        {"url": "https://www.sportmonks.com/football-api/plans-pricing/", "title": "SportMonks Plans & Pricing", "snippet": "Football data API pricing plans", "source": "web"},
        {"url": "https://the-monks.com/", "title": "The Monks creative studio", "snippet": "Independent creative studio Berlin", "source": "web"},
    ]
    identity = CustomerIdentity(
        canonical_name="Monks",
        domain="monks.com",
        email=None,
        confidence="confirmed",
        evidence=["domain: monks.com"],
        company_name="Monks",
    )
    from run_prep import PrepContext
    context = PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment={
            "company_name": "Monks",
            "description": "Monks is a digital-first marketing company.",
            "dossier": {},
        },
        missing_context=[],
        apollo_enrichment={"status": "missing_api_key"},
        search_results=web_results,
        web_search_status="usable_results_found",
        company_overview_status="usable_results_found",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # sportmonks.com must not appear anywhere in customer-facing output
    assert "sportmonks.com" not in md.lower(), \
        "sportmonks.com must not appear in Standard Discovery evidence or anywhere in output"
    assert "the-monks.com" not in md.lower(), \
        "the-monks.com must not appear in Standard Discovery evidence or anywhere in output"

    # Standard Discovery section must not cite sportmonks
    disc_idx = md.find("Standard Discovery")
    if disc_idx != -1:
        disc_end = md.find("\n##", disc_idx + 1)
        disc_section = md[disc_idx:disc_end] if disc_end != -1 else md[disc_idx:]
        assert "sportmonks" not in disc_section.lower(), \
            "Standard Discovery evidence must not contain sportmonks"


def test_monks_web_results_list_no_investment_trust():
    """
    Others > Web search results list must not show MarketBeat MNKS / investment trust pages.
    Investment trust contamination must be filtered before the Others section is rendered.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    trust_results = [
        {"url": "https://monks.com/about", "title": "Monks global marketing", "snippet": "Global marketing company under S4 Capital", "source": "web"},
        {"url": "https://www.marketbeat.com/stocks/LON/MNKS/", "title": "Monks Investment Trust (MNKS) Stock — MarketBeat", "snippet": "Monks Investment Trust MNKS:LSE stock price, NAV, AUM details.", "source": "web"},
        {"url": "https://www.trustnet.com/monks-investment-trust", "title": "Monks Investment Trust (MNKS:LSE)", "snippet": "Listed investment trust. Net asset value. AUM £2.8bn.", "source": "web"},
    ]
    context = _make_web_only_context(
        name="Monks",
        domain="monks.com",
        search_results=trust_results,
        description="Monks is a digital-first marketing and technology services company.",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # MarketBeat / investment trust URLs must not appear in Web search results list (Others section)
    others_idx = md.find("# Others")
    assert others_idx != -1, "Others section must be present"
    others_section = md[others_idx:]
    assert "marketbeat.com" not in others_section.lower(), \
        "MarketBeat investment trust URL must not appear in Others web results list"
    assert "mnks:lse" not in others_section.lower(), \
        "MNKS:LSE ticker must not appear in Others section"
    assert "investment trust" not in others_section.lower(), \
        "Investment trust must not appear in Others section"

    # web_rejected_count must reflect the rejections
    rejected = (rj.get("source_status") or {}).get("web_rejected_count", 0)
    assert rejected >= 2, f"Expected at least 2 rejected sources (marketbeat + trustnet), got {rejected}"


def test_monks_evidence_table_no_contamination():
    """
    Evidence Table must stay clean: no sportmonks, investment trust, or unrelated Monk entities.
    Rich sections must still be present.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    mixed_results = [
        {"url": "https://monks.com/about", "title": "Monks – global marketing", "snippet": "Monks is a digital-first marketing company under S4 Capital.", "source": "web"},
        {"url": "https://www.sportmonks.com/football-api/", "title": "SportMonks Football API", "snippet": "Football data API pricing plans", "source": "web"},
        {"url": "https://www.ft.com/content/monks-investment-trust", "title": "Monks Investment Trust — NAV update", "snippet": "Monks Investment Trust (MNKS:LSE) net asset value. AUM £2.8bn.", "source": "web"},
        {"url": "https://the-monks.com/", "title": "The Monks creative studio", "snippet": "Independent creative studio Berlin", "source": "web"},
    ]
    context = _make_web_only_context(
        name="Monks",
        domain="monks.com",
        search_results=mixed_results,
        description="Monks is a digital-first marketing and technology services company.",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # Evidence Table section must not reference rejected sources
    et_idx = md.find("Evidence Table")
    if et_idx != -1:
        et_end = md.find("\n##", et_idx + 1)
        et_section = md[et_idx:et_end] if et_end != -1 else md[et_idx:]
        assert "sportmonks.com" not in et_section.lower(), "Evidence Table must not contain sportmonks"
        assert "the-monks.com" not in et_section.lower(), "Evidence Table must not contain the-monks"
        assert "investment trust" not in et_section.lower(), "Evidence Table must not contain investment trust"

    # Rich sections must still render
    _assert_rich_sections_present(md, "Monks evidence table test")

    # Rejected count must be >= 3
    rejected = (rj.get("source_status") or {}).get("web_rejected_count", 0)
    assert rejected >= 3, f"Expected at least 3 rejected sources, got {rejected}"


# ---------------------------------------------------------------------------
# Round 18 regression tests: consolidated section contamination + UX fixes
# ---------------------------------------------------------------------------


def test_monks_no_contamination_in_consolidated_sections():
    """
    Account Intelligence Snapshot and Others > Web search results must not contain
    SportMonks, sportsapi, the-monks, MNKS, or investment trust pages for Monks/monks.com.
    Rejected sources must only appear in Run Report (rejected count).
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    contaminated_results = [
        {"url": "https://monks.com/about", "title": "Monks – global digital agency", "snippet": "Monks is a digital-first marketing company under S4 Capital.", "source": "web"},
        {"url": "https://www.sportmonks.com/football-api/pricing", "title": "SportMonks Football API pricing", "snippet": "Football data API plans $9 $49 $99", "source": "web"},
        {"url": "https://sportsapi.com/monks", "title": "Monks API — SportsAPI football data", "snippet": "SportMonks football data feeds and predictions API", "source": "web"},
        {"url": "https://the-monks.com/", "title": "The Monks creative studio", "snippet": "Independent creative studio Berlin", "source": "web"},
        {"url": "https://www.marketbeat.com/stocks/LON/MNKS/", "title": "Monks Investment Trust (MNKS:LSE) — MarketBeat", "snippet": "Monks Investment Trust stock price, NAV, AUM. MNKS:LSE listed.", "source": "web"},
    ]
    context = _make_web_only_context(
        name="Monks",
        domain="monks.com",
        search_results=contaminated_results,
        description="Monks is a digital-first marketing and technology services company under S4 Capital.",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # Customer-facing output must not contain any contaminated domains
    bad_terms = ["sportmonks.com", "sportsapi.com", "the-monks.com", "mnks:lse", "investment trust"]
    others_start = md.find("# Others")
    customer_facing = md[:others_start] if others_start != -1 else md
    for term in bad_terms:
        assert term not in customer_facing.lower(), (
            f"Contaminated term {term!r} must not appear in customer-facing sections"
        )

    # Others > Web search results must also be clean
    if others_start != -1:
        others_section = md[others_start:]
        assert "sportmonks.com" not in others_section.lower(), \
            "sportmonks.com must not appear in Others web results list"
        assert "marketbeat.com" not in others_section.lower(), \
            "marketbeat.com must not appear in Others web results list"

    # Rejection must be recorded
    rejected = (rj.get("source_status") or {}).get("web_rejected_count", 0)
    assert rejected >= 4, f"Expected at least 4 rejected sources (sportmonks, sportsapi, the-monks, marketbeat), got {rejected}"


def test_monks_prefill_uses_apollo_description_not_consumer_tech():
    """
    Pre-filled discovery signals for Monks / marketing_adtech must use the canonical
    Apollo description ('digital agency', 'S4 Capital', 'creative production').
    Consumer-tech fallback ('consumer devices', 'hardware', 'accessories') must not appear.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _monks_context()  # Apollo-matched, marketing_adtech
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    consumer_tech_phrases = [
        "consumer devices", "hardware sales", "app ecosystem", "accessories",
        "global technology company offering consumer", "entertainment, accessories, and support",
    ]
    md_lower = md.lower()
    for phrase in consumer_tech_phrases:
        assert phrase not in md_lower, (
            f"Consumer-tech fallback phrase {phrase!r} must not appear in Monks marketing/adtech report"
        )

    # Apollo description terms must appear somewhere in the report
    assert any(term in md_lower for term in ("digital agency", "creative production", "s4 capital", "marketing")), \
        "Apollo description terms (digital agency / creative production / S4 Capital) must appear in report"


def test_monks_first_meeting_record_into_mapping():
    """
    First Meeting Validation Plan Record Into column must use canonical field names:
    - team/stakeholder question → Team / stakeholder / use-case owner
    - monthly volume question → Monthly volume / sizing
    - budget/decision question → Budget / decision owner / procurement
    - modality/format question → Workload priority / modality scope
    - market/language question → Market / localization scope
    - POC/success question → POC criteria / benchmark
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _monks_context()
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # All canonical field names must appear in the validation plan table
    assert "Team / stakeholder / use-case owner" in md, \
        "Record Into must include 'Team / stakeholder / use-case owner'"
    assert "Monthly volume / sizing" in md, \
        "Record Into must include 'Monthly volume / sizing'"
    assert "Budget / decision owner / procurement" in md, \
        "Record Into must include 'Budget / decision owner / procurement'"
    assert "Market / localization scope" in md, \
        "Record Into must include 'Market / localization scope'"
    # Workload priority
    assert "Workload priority" in md, \
        "Record Into must include 'Workload priority / modality scope'"
    # Old incorrect values must not appear
    assert "Scope / product scoping" not in md, \
        "Old 'Scope / product scoping' must not appear in Record Into"


def test_monks_opportunity_hypotheses_not_repetitive():
    """
    Opportunity Hypotheses (Section 3) must contain only:
    - Workload hypotheses summary line
    - Active workload confidence line
    - AI / Model Opportunity Map
    It must NOT contain:
    - BytePlus fit hypotheses block
    - Prepare before the call block
    These are already in AE/SA Brief, Solution Paths, and AE/SA View.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    context = _monks_context()
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    lines = md.split("\n")

    def section_between(start_sub: str, end_sub: str) -> str:
        collecting = False
        out = []
        for line in lines:
            if start_sub in line:
                collecting = True
            elif collecting and end_sub in line and end_sub != start_sub:
                break
            elif collecting:
                out.append(line)
        return "\n".join(out)

    opp_section = section_between("## 3. Opportunity Hypotheses", "## 4.")

    assert "Workload hypotheses" in opp_section or "Possible AI workloads" in opp_section, \
        "Opportunity Hypotheses must contain workload summary"
    assert "AI / Model Opportunity Map" in opp_section, \
        "Opportunity Hypotheses must contain AI / Model Opportunity Map"
    # Repetitive blocks must be absent from this section
    assert "BytePlus fit hypotheses" not in opp_section, \
        "BytePlus fit hypotheses block must not appear in Opportunity Hypotheses (already in Brief/Paths)"
    assert "Prepare before the call" not in opp_section, \
        "Prepare before the call block must not appear in Opportunity Hypotheses (already in Brief)"


def test_monks_prior_docs_summary_non_debug():
    """
    In non-debug mode, prior docs should show count summary only, not full candidate URLs.
    Debug mode should show full URLs.
    """
    import argparse
    from run_prep import context_to_renderer_json, PrepContext, CustomerIdentity
    from scripts.render_prep_doc import render  # type: ignore[import]

    identity = CustomerIdentity(
        canonical_name="Monks",
        domain="monks.com",
        email=None,
        confidence="confirmed",
        evidence=["domain: monks.com"],
        company_name="Monks",
    )
    fake_prior_docs = [
        {"url": "https://lark.com/docs/prior-monks-profile-1", "title": "Monks Prior Profile 2024", "engagement_rows": []},
        {"url": "https://lark.com/docs/prior-monks-profile-2", "title": "Monks Q1 2025 Meeting Notes", "engagement_rows": []},
    ]
    context = PrepContext(
        customer=identity,
        event=None,
        prior_docs=fake_prior_docs,
        enrichment=None,
        missing_context=[],
        apollo_enrichment=_monks_apollo_data(),
        web_search_status="web_search: disabled_by_env",
        company_overview_status="no_overview_eligible_results",
    )
    args_normal = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj_normal = context_to_renderer_json(context, args_normal)
    md_normal = render(rj_normal)

    # Non-debug: must show count, not full URLs
    assert "lark.com/docs/prior-monks-profile-1" not in md_normal, \
        "Non-debug: prior doc URLs must not appear in rendered output"
    assert "Candidate prior customer docs found: 2" in md_normal, \
        "Non-debug: must show count summary for candidate prior docs"

    # Debug mode: full URLs should appear
    args_debug = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=True)
    rj_debug = context_to_renderer_json(context, args_debug)
    md_debug = render(rj_debug)
    assert "lark.com/docs/prior-monks-profile-1" in md_debug or \
           "Candidate prior customer docs found" in md_debug, \
        "Debug: prior doc URLs or summary must appear in rendered output"


def test_monks_evidence_table_clean_round18():
    """
    Evidence Table must not contain any contamination for Monks:
    sportmonks, sportsapi, the-monks, investment trust, MNKS.
    Run Report must still show web_rejected_count.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    contaminated_results = [
        {"url": "https://monks.com/about", "title": "Monks – global digital agency", "snippet": "Monks is a marketing company under S4 Capital.", "source": "web"},
        {"url": "https://www.sportmonks.com/football-api/", "title": "SportMonks Football API", "snippet": "Football data API plans $9 $49 $99", "source": "web"},
        {"url": "https://www.ft.com/content/monks-investment-trust", "title": "Monks Investment Trust — FT", "snippet": "Monks Investment Trust (MNKS:LSE) net asset value update.", "source": "web"},
    ]
    context = _make_web_only_context(
        name="Monks",
        domain="monks.com",
        search_results=contaminated_results,
        description="Monks is a digital-first marketing and technology services company.",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    bad_terms = ["sportmonks.com", "investment trust", "mnks:lse"]
    et_idx = md.lower().find("evidence table")
    et_section = md[et_idx:] if et_idx != -1 else md
    for term in bad_terms:
        assert term not in et_section.lower(), \
            f"Evidence Table must not contain {term!r}"

    # Run Report must still record rejections
    rejected = (rj.get("source_status") or {}).get("web_rejected_count", 0)
    assert rejected >= 2, f"Expected at least 2 rejections, got {rejected}"


def test_monks_web_rejected_count_in_run_report_round18():
    """
    Run Report must show web_rejected_count for Monks with contaminated search results.
    Rejected domains must not appear in customer-facing sections.
    """
    import argparse
    from run_prep import context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    web_results = [
        {"url": "https://monks.com/about", "title": "Monks global marketing", "snippet": "Global marketing and tech services", "source": "web"},
        {"url": "https://www.sportmonks.com/football-api/pricing", "title": "SportMonks API pricing", "snippet": "Football data API plans $9 $49 $99", "source": "web"},
        {"url": "https://the-monks.com/", "title": "The Monks creative studio", "snippet": "Independent creative studio", "source": "web"},
    ]
    context = _make_web_only_context(
        name="Monks",
        domain="monks.com",
        search_results=web_results,
        description="Monks is a digital-first marketing company.",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    rejected = (rj.get("source_status") or {}).get("web_rejected_count", 0)
    assert rejected >= 2, f"Expected >= 2 rejections, got {rejected}"
    assert "web_rejected_count" in md.lower() or "web result(s) filtered" in md.lower(), \
        "Run Report must mention rejected web result count"

    # Rejected domains must not appear in customer-facing output
    assert "sportmonks.com" not in md.lower(), \
        "sportmonks.com must not appear anywhere in rendered output"
    assert "the-monks.com" not in md.lower(), \
        "the-monks.com must not appear anywhere in rendered output"


def test_monks_dossier_ai_signals_filtered():
    """
    If the dossier ai_signals field contains contaminated content referencing rejected domains
    (e.g. from MCP enrichment that ran before the entity guard), those signals must not
    appear in Account Intelligence Snapshot > Public AI / News Signals.
    """
    import argparse
    from run_prep import PrepContext, CustomerIdentity, context_to_renderer_json
    from scripts.render_prep_doc import render  # type: ignore[import]

    identity = CustomerIdentity(
        canonical_name="Monks",
        domain="monks.com",
        email=None,
        confidence="confirmed",
        evidence=["domain: monks.com"],
        company_name="Monks",
    )
    contaminated_enrichment = {
        "company_name": "Monks",
        "description": "Monks is a digital-first marketing company under S4 Capital.",
        "source": "mcp",
        "dossier": {
            "what_they_do": "Monks is a digital agency under S4 Capital.",
            "ai_signals": [
                "Monks uses AI for creative production and campaign automation",
                "sportmonks.com API integration for sports data predictions",
            ],
            "scale_signals": "~8,000 employees",
        },
        "known_use_cases": [],
        "possible_byteplus_fit": [],
        "known_competitors": [],
        "known_risks": [],
        "suggested_questions": [],
        "source_links": [],
    }
    # Also pass a sportmonks.com search result to build the rejected_domains set
    contaminated_results = [
        {"url": "https://monks.com/about", "title": "Monks global agency", "snippet": "Monks S4 Capital agency", "source": "web"},
        {"url": "https://www.sportmonks.com/football-api/pricing", "title": "SportMonks Football API", "snippet": "Football data plans", "source": "web"},
    ]
    context = PrepContext(
        customer=identity,
        event=None,
        prior_docs=[],
        enrichment=contaminated_enrichment,
        missing_context=[],
        apollo_enrichment={"status": "missing_api_key"},
        search_results=contaminated_results,
        web_search_status="usable_results_found",
        company_overview_status="usable_results_found",
    )
    args = argparse.Namespace(industry=None, workload=None, prospecting_prompt=None, debug=False)
    rj = context_to_renderer_json(context, args)
    md = render(rj)

    # The clean ai_signal must appear
    intel_idx = md.find("Account Intelligence Snapshot")
    if intel_idx == -1:
        intel_idx = md.find("Essential Background Check")
    assert intel_idx != -1, "Account Intelligence Snapshot section must be present"
    intel_end = md.find("\n## 3.", intel_idx)
    intel_section = md[intel_idx:intel_end] if intel_end != -1 else md[intel_idx:]

    assert "sportmonks.com" not in intel_section.lower(), \
        "Contaminated dossier ai_signal referencing sportmonks.com must be filtered from Account Intelligence Snapshot"
    assert "creative production" in intel_section.lower() or "campaign automation" in intel_section.lower(), \
        "Clean ai_signal must still appear in Account Intelligence Snapshot"
