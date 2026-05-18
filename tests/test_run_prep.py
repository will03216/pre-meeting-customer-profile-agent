from __future__ import annotations

import argparse
import json
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_prep
import render_prep_doc
import package_skill


def event(summary: str, attendees: list[dict] | None = None) -> dict:
    return {"summary": summary, "attendees": attendees or []}


def test_email_parser_corporate_resolves_domain() -> None:
    identity = run_prep.resolve_customer(explicit_email="isaac@moburst.com")
    assert identity.domain == "moburst.com"
    assert identity.canonical_name == "Moburst"
    assert identity.confidence == "confirmed"


def test_email_parser_personal_does_not_infer_company() -> None:
    identity = run_prep.resolve_customer(explicit_email="person@gmail.com")
    assert identity.domain is None
    assert identity.canonical_name is None
    assert identity.confidence == "unknown"


def test_domain_resolver() -> None:
    identity = run_prep.resolve_customer(explicit_domain="https://www.moburst.com/about")
    assert identity.domain == "moburst.com"
    assert identity.canonical_name == "Moburst"
    assert identity.confidence == "confirmed"


def test_customer_name_resolver() -> None:
    identity = run_prep.resolve_customer(explicit_customer="Moburst")
    assert identity.canonical_name == "Moburst"
    assert identity.confidence == "confirmed"


def test_meeting_qualification_internal_standup_skipped() -> None:
    qualified, reason = run_prep.classify_event(event("MaaS standup"))
    assert not qualified
    assert "internal" in reason


def test_meeting_qualification_customer_title_accepted() -> None:
    qualified, _ = run_prep.classify_event(event("ByteDance <> Moburst Sync"))
    assert qualified


def test_meeting_qualification_generic_sync_skipped_without_customer_signal() -> None:
    qualified, _ = run_prep.classify_event(event("quick sync"))
    assert not qualified


def test_meeting_qualification_moburst_sync_accepted_with_external_domain() -> None:
    qualified, _ = run_prep.classify_event(
        event(
            "Moburst sync",
            [{"type": "third_party", "third_party_email": "isaac@moburst.com", "is_external": True}],
        )
    )
    assert qualified


def test_window_parser_today_tomorrow_next_7_days_and_explicit() -> None:
    now = datetime(2026, 5, 15, 13, 0, tzinfo=ZoneInfo("Europe/London"))
    today_start, today_end, _ = run_prep.parse_window("today", now=now)
    tomorrow_start, tomorrow_end, _ = run_prep.parse_window("tomorrow", now=now)
    next_start, next_end, _ = run_prep.parse_window("next-7-days", now=now)
    explicit_start, explicit_end, _ = run_prep.parse_window("2026-05-15:2026-05-22", now=now)
    past_start, past_end, _ = run_prep.parse_window("past-48-hours", now=now)

    assert today_start.date().isoformat() == "2026-05-15"
    assert today_end.date().isoformat() == "2026-05-16"
    assert tomorrow_start.date().isoformat() == "2026-05-16"
    assert tomorrow_end.date().isoformat() == "2026-05-17"
    assert next_start == now
    assert next_end == now.replace(day=22)
    assert explicit_start.date().isoformat() == "2026-05-15"
    assert explicit_end.date().isoformat() == "2026-05-22"
    assert past_end == now
    assert past_start == datetime(2026, 5, 13, 13, 0, tzinfo=ZoneInfo("Europe/London"))


def test_dedupe_logic_update_existing() -> None:
    docs = [
        {"title": "BytePlus <> Moburst - 15-05-2026 - Pre-Meeting Prep", "url": "https://doc"},
        {"title": "Random", "url": "https://random"},
    ]
    assert run_prep.choose_existing_doc(docs, "Moburst") == docs[0]
    assert run_prep.choose_existing_doc(docs, "Shuffll") is None


def test_dry_run_does_not_create_or_notify(tmp_path, monkeypatch) -> None:
    args = argparse.Namespace(dry_run=True, update_existing=False)
    md_path = tmp_path / "prep.md"
    md_path.write_text("# Prep\n", encoding="utf-8")
    doc_url, action = run_prep.create_or_update_doc(
        markdown_path=md_path,
        title="BytePlus <> Moburst - TBD - Pre-Meeting Prep",
        existing_doc=None,
        args=args,
    )
    assert doc_url is None
    assert action == "dry-run: no Lark write"


def test_lark_markdown_arg_uses_relative_path_inside_cwd(tmp_path, monkeypatch) -> None:
    workdir = tmp_path / "skill"
    markdown = workdir / "outputs" / "prep" / "prep.md"
    markdown.parent.mkdir(parents=True)
    markdown.write_text("# Prep\n", encoding="utf-8")
    monkeypatch.chdir(workdir)
    assert run_prep.lark_markdown_arg(markdown) == "@outputs/prep/prep.md"


def test_renderer_integration() -> None:
    context = run_prep.PrepContext(
        customer=run_prep.CustomerIdentity("Moburst", "moburst.com", None, "confirmed", ["test"]),
        event=None,
        prior_docs=[],
        enrichment=None,
        missing_context=[],
    )
    normalized = run_prep.context_to_renderer_json(context)
    rendered = run_prep.render(normalized)
    assert "BytePlus <> Moburst" in rendered
    assert "Pre-Meeting Prep" in rendered


def base_render_payload() -> dict:
    return {
        "meeting": {
            "title": "Moburst sync",
            "start": "2026-05-15T13:00:00+01:00",
            "end": "2026-05-15T13:30:00+01:00",
            "timezone": "Europe/London",
            "organizer": {"name": "AE", "email": "ae@byteplus.com"},
            "sa": {"name": "SA", "email": "sa@byteplus.com"},
            "url": "https://calendar.example/event",
        },
        "customer": {"name": "Moburst", "domain": "moburst.com", "confidence": "confirmed"},
        "attendees": [{"name": "Isaac", "email": "isaac@moburst.com", "external": True}],
        "enrichment": {"available": False},
        "prior_docs": [],
        "prior_notes": [],
        "search_results": [],
        "known": {},
        "source_status": {
            "calendar": "available",
            "attendees": "available",
            "mcp": "unavailable",
            "prior_docs": "none",
            "mira": "unavailable",
        },
    }


def test_calendar_only_source_attribution_does_not_claim_optional_sources() -> None:
    rendered = render_prep_doc.render(base_render_payload())
    assert "Prep generated from calendar data only." in rendered
    assert "Prior docs, MCP enrichment, web search, and Mira/Knowledge Base references were unavailable in this run." in rendered
    assert "Prep generated from calendar, prior docs, MCP" not in rendered


def test_mcp_available_source_attribution_may_mention_mcp() -> None:
    payload = base_render_payload()
    payload["enrichment"] = {"available": True, "known_use_cases": ["video generation"]}
    rendered = render_prep_doc.render(payload)
    assert "MCP enrichment" in rendered


def test_prior_docs_source_attribution_may_mention_prior_docs() -> None:
    payload = base_render_payload()
    payload["prior_docs"] = [{"title": "Moburst Customer Profile", "url": "https://doc.example", "date": "2026-05-01"}]
    rendered = render_prep_doc.render(payload)
    assert "Candidate prior customer docs found, but no usable prior customer profile content was extracted" in rendered


def test_web_search_source_attribution_may_mention_web_search() -> None:
    payload = base_render_payload()
    payload["customer"]["company_name"] = "ImagineArt"
    payload["customer"]["website"] = "imagine.art"
    payload["enrichment"] = {
        "available": True,
        "source": "web_search",
        "description": "AI creative platform",
        "known_use_cases": ["Likely: image generation and creative asset editing (?)"],
        "possible_byteplus_fit": [{"product": "Seedream", "reason": "Validate image generation fit"}],
    }
    payload["search_results"] = [{"title": "ImagineArt", "url": "https://www.imagine.art/", "source": "web"}]
    rendered = render_prep_doc.render(payload)
    assert "## Executive Prep Snapshot" in rendered
    assert "Likely Customer / Company:** Moburst at ImagineArt" in rendered
    assert "Seedream: Validate image generation fit" in rendered
    assert "web search references" in rendered
    assert "Web search results: https://www.imagine.art/" in rendered
    assert "MCP enrichment" not in rendered.split("| 15-05-2026 | Pre-Meeting |", 1)[1].split("|", 1)[0]


def test_docs_search_parses_lark_results(monkeypatch) -> None:
    def fake_run_lark(args, *, debug=False, check=False):
        return {
            "ok": True,
            "data": {
                "results": [
                    {
                        "entity_type": "WIKI",
                        "title_highlighted": "100 gen leads",
                        "summary_highlighted": "<h>Ahmed</h> <h>Abubakar</h> Founder &amp; CEO, ImagineArt",
                        "result_meta": {
                            "token": "abc",
                            "url": "https://bytedance.larkoffice.com/wiki/abc",
                            "update_time_iso": "2026-04-19T20:58:12+01:00",
                        },
                    }
                ]
            },
        }

    monkeypatch.setattr(run_prep, "run_lark", fake_run_lark)
    docs, warning = run_prep.search_docs(["Ahmed Abubakar"])
    assert warning is None
    assert docs[0]["title"] == "100 gen leads"
    assert "Founder & CEO, ImagineArt" in docs[0]["summary"]
    assert run_prep.infer_company_from_docs("Ahmed Abubakar", docs) == "ImagineArt"
    assert run_prep.infer_company_from_docs("Ahmed Abubakar", [{"summary": "Ahmed Abubakar Founder & CEO, ImagineArt ImagineArt creative agencies"}]) == "ImagineArt"
    assert run_prep.infer_company_from_docs("Aleix Perdigó", [{"summary": "Aleix Perdigó AI Creative Technologist Goroka video production 315 Country Spain"}]) == "Goroka"
    assert run_prep.infer_company_from_docs("David Agronov", [{"summary": "David Agronov Product Manager Natural Intelligence adtec"}]) == "Natural Intelligence"


def test_docs_search_partial_failure_keeps_usable_docs(monkeypatch) -> None:
    calls = []

    def fake_run_lark(args, *, debug=False, check=False):
        calls.append(args)
        if len(calls) == 2:
            return {"ok": False, "error": {"message": "temporary docs search failure"}}
        return {
            "ok": True,
            "data": {
                "results": [
                    {
                        "title_highlighted": "100 gen leads",
                        "summary_highlighted": "Ahmed Abubakar Founder &amp; CEO, ImagineArt",
                        "result_meta": {"token": "abc", "url": "https://doc"},
                    }
                ]
            },
        }

    monkeypatch.setattr(run_prep, "run_lark", fake_run_lark)
    docs, warning = run_prep.search_docs(["Ahmed Abubakar", "Ahmed Abubakar AI notes"])
    assert docs
    assert warning and "partially unavailable" in warning


def test_docs_search_retries_rate_limit_once(monkeypatch) -> None:
    calls = []

    def fake_run_lark(args, *, debug=False, check=False):
        calls.append(args)
        if len(calls) == 1:
            return {"ok": False, "error": {"message": "API call failed: [9499] too many request"}}
        return {
            "ok": True,
            "data": {
                "results": [
                    {
                        "title_highlighted": "ImagineArt lead",
                        "summary_highlighted": "Ahmed Abubakar Founder &amp; CEO, ImagineArt",
                        "result_meta": {"token": "abc", "url": "https://doc"},
                    }
                ]
            },
        }

    monkeypatch.setattr(run_prep, "run_lark", fake_run_lark)
    monkeypatch.setattr(run_prep.time_module, "sleep", lambda _: None)
    docs, warning = run_prep.search_docs(["Ahmed Abubakar"])
    assert warning is None
    assert len(calls) == 2
    assert docs[0]["title"] == "ImagineArt lead"


def test_rank_docs_filters_low_signal_name_collisions() -> None:
    docs = [
        {"title": "100 gen leads", "summary": "Ahmed Abubakar Founder & CEO, ImagineArt creative agencies"},
        {"title": "ICLR paper list", "summary": "Ahmed Magooda and Abubakar Abid paper"},
        {"title": "BytePlus <> Ahmed Abubakar - TBD - Pre-Meeting Prep", "summary": "Existing prep"},
    ]
    ranked = run_prep.rank_docs(docs, ["Ahmed Abubakar", "ImagineArt"])
    titles = [doc["title"] for doc in ranked]
    assert "100 gen leads" in titles
    assert "BytePlus <> Ahmed Abubakar - TBD - Pre-Meeting Prep" in titles
    assert "ICLR paper list" not in titles


def test_web_enrichment_uses_public_results(monkeypatch) -> None:
    queries = []

    def fake_web_search(query, *, max_results=5, debug=False):
        queries.append(query)
        return [
            {
                "title": "ImagineArt",
                "url": "https://www.imagine.art/",
                "snippet": "ImagineArt is an AI creative platform for image and video generation.",
                "source": "web",
            }
        ], None

    monkeypatch.setattr(run_prep, "web_search", fake_web_search)
    context = run_prep.PrepContext(
        customer=run_prep.CustomerIdentity("Ahmed Abubakar", None, None, "likely", ["test"]),
        event=None,
        prior_docs=[{"summary": "Ahmed Abubakar Founder & CEO, ImagineArt"}],
        enrichment=None,
        missing_context=[],
    )
    enrichment, results, warning = run_prep.build_web_enrichment(context)
    assert warning is None
    assert enrichment and enrichment["source"] == "web_search"
    assert enrichment["company_name"] == "ImagineArt"
    assert enrichment["website"] == "imagine.art"
    assert any(item["product"] == "Seedance" for item in enrichment["possible_byteplus_fit"])
    assert any("image generation" in item for item in enrichment["known_use_cases"])
    assert results[0]["source"] == "web"
    assert "ImagineArt" in queries[0]


def test_web_results_prioritize_meeting_prep_signals() -> None:
    results = [
        {"title": "Generic review", "url": "https://greenrecord.co.uk/imagineart-review", "snippet": "review", "query": "ImagineArt company product"},
        {"title": "ImagineArt users", "url": "https://news.example/imagineart", "snippet": "over 3.5 million active users and 3.2 million downloads", "query": "ImagineArt users downloads funding revenue"},
        {"title": "ImagineArt official", "url": "https://www.imagine.art/", "snippet": "AI creative suite API", "query": "ImagineArt company product"},
    ]
    ranked = sorted(results, key=run_prep.web_relevance_score, reverse=True)
    assert ranked[0]["url"] == "https://www.imagine.art/"
    assert ranked[1]["title"] == "ImagineArt users"


def test_contextual_web_score_penalizes_name_collisions() -> None:
    good = {
        "title": "Aleix Perdigó - Visual l Elisava",
        "url": "https://visual.elisava.net/en/people/faculty/aleix-perdigo-goroka-lavinia-ai/",
        "snippet": "Aleix Perdigó is an AI Creative Director at Goroka and Lavinia AI.",
        "query": "Aleix Perdigó Goroka",
    }
    bad = {
        "title": "Goroka Coffee",
        "url": "https://www.gorokacoffee.com/products",
        "snippet": "Papua New Guinea coffee products",
        "query": "Goroka company product",
    }
    assert run_prep.contextual_web_score(good, "Aleix Perdigó", "Goroka") > run_prep.contextual_web_score(bad, "Aleix Perdigó", "Goroka")


def test_contextual_web_score_does_not_trust_query_text_for_relevance() -> None:
    good = {
        "title": "Natural Intelligence | Data-Powered Intent Marketing",
        "url": "https://www.naturalint.com/",
        "snippet": "Natural Intelligence is a global leader in intent marketing and customer acquisition.",
        "query": "David Agronov Natural Intelligence AI Video Lead",
    }
    bad = {
        "title": "OpenAI Statistics",
        "url": "https://example.com/openai-statistics",
        "snippet": "OpenAI downloads, revenue, and market share.",
        "query": "David Agronov Natural Intelligence AI Video Lead",
    }
    assert run_prep.contextual_web_score(good, "David Agronov", "Natural Intelligence") > 0
    assert run_prep.contextual_web_score(bad, "David Agronov", "Natural Intelligence") < 0


def test_official_web_result_chosen_over_directory_site() -> None:
    assert run_prep.likely_official_web_result(
        {"url": "https://www.imagine.art/", "title": "ImagineArt", "snippet": ""},
        "ImagineArt",
    )
    assert not run_prep.likely_official_web_result(
        {"url": "https://www.crunchbase.com/organization/imagineart", "title": "ImagineArt", "snippet": ""},
        "ImagineArt",
    )
    assert not run_prep.likely_official_web_result(
        {"url": "https://www.gorokacoffee.com/products", "title": "Goroka Coffee", "snippet": ""},
        "Goroka",
    )
    assert run_prep.likely_official_web_result(
        {"url": "https://www.naturalint.com/", "title": "Natural Intelligence", "snippet": "Intent marketing"},
        "Natural Intelligence",
    )
    assert not run_prep.likely_official_web_result(
        {"url": "https://naturalintelligence.info/", "title": "Natural Intelligence", "snippet": "Leen Gorissen"},
        "Natural Intelligence",
    )
    assert run_prep.stable_company_website("docs.imagine.art") == "imagine.art"
    assert "generative AI creative platform" in run_prep.stable_company_description("ImagineArt", "Monetization on ImagineArt Community", ["image generation"])
    assert run_prep.source_tier("https://docs.imagine.art/community/monetization", "ImagineArt")[1] == "Tier 1 - official docs/help"


def test_web_query_expansion_keeps_customer_specific_queries_scoped() -> None:
    customer = run_prep.CustomerIdentity(canonical_name="David Agronov", email=None, domain=None, confidence="explicit", evidence=[])
    queries = run_prep.expand_web_queries(customer, "Natural Intelligence")
    assert not any("Lavinia AI" in query for query in queries)
    assert not any("AI image generator video generator" in query for query in queries)
    assert any("intent marketing" in query for query in queries)
    assert any("naturalint.com" in query for query in queries)

    goroka_customer = run_prep.CustomerIdentity(canonical_name="Aleix Perdigó", email=None, domain=None, confidence="explicit", evidence=[])
    goroka_queries = run_prep.expand_web_queries(goroka_customer, "Goroka")
    assert any("Lavinia AI" in query for query in goroka_queries)


def test_intent_marketing_enrichment_uses_relevant_fit_and_questions() -> None:
    text = "Natural Intelligence is a global leader in intent marketing, customer acquisition, and comparison platforms."
    use_cases = run_prep.infer_use_cases(text)
    fit = run_prep.possible_byteplus_fit(use_cases, text)
    questions = run_prep.suggested_customer_questions(use_cases, text)
    assert "performance marketing and customer acquisition workflow" in use_cases
    assert fit[0]["product"] == "Ark / model platform"
    assert "customer-acquisition" in questions[0]


def test_intent_marketing_dossier_does_not_infer_video_from_generic_video_word() -> None:
    dossier = run_prep.extract_company_dossier(
        "Natural Intelligence",
        "Natural Intelligence is a global leader in intent marketing and customer acquisition.",
        ["performance marketing and customer acquisition workflow"],
        [
            {
                "title": "Natural Intelligence",
                "url": "https://www.naturalint.com/",
                "snippet": "Comparison platforms and customer acquisition. A marketing video appears on the page.",
            }
        ],
        [],
    )
    assert "Intent marketing platform" in dossier["product_modules"]
    assert "Comparison platforms" in dossier["product_modules"]
    assert "AI video generation" not in dossier["product_modules"]


def test_prospecting_prompt_loading_default_custom_and_missing(tmp_path) -> None:
    default_prompt = run_prep.load_prospecting_prompt()
    assert default_prompt["available"] == "true"
    assert "Do not render a giant question coverage matrix" in default_prompt["content"]

    custom = tmp_path / "custom_prompt.md"
    custom.write_text("custom prospecting guidance", encoding="utf-8")
    loaded = run_prep.load_prospecting_prompt(str(custom))
    assert loaded["available"] == "true"
    assert loaded["content"] == "custom prospecting guidance"

    missing = run_prep.load_prospecting_prompt(str(tmp_path / "missing.md"))
    assert missing["available"] == "false"
    assert missing["content"] == ""


def test_industry_playbook_loading_and_fallback() -> None:
    for name in ["default", "marketing_adtech", "ai_video_creative", "ecommerce", "gaming", "enterprise_llm"]:
        playbook = run_prep.load_industry_playbook(name)
        assert playbook["name"] == name
        assert playbook["display_name"]
        assert playbook["sections"]
    fallback = run_prep.load_industry_playbook("unknown_vertical")
    assert fallback["name"] == "default"


def context_for_vertical(text: str) -> run_prep.PrepContext:
    return run_prep.PrepContext(
        customer=run_prep.CustomerIdentity(canonical_name="Customer", domain=None, email=None, confidence="confirmed", evidence=[]),
        event={"summary": text},
        prior_docs=[{"title": "doc", "summary": text}],
        enrichment={"available": True, "source": "web_search", "description": text, "known_use_cases": [], "source_links": [{"url": "https://example.com"}]},
        missing_context=[],
        search_results=[{"title": text, "snippet": text, "url": "https://example.com", "source": "web"}],
        docs_search_available=True,
        web_search_available=True,
    )


def test_vertical_inference_maps_initial_playbooks() -> None:
    assert run_prep.infer_vertical(context_for_vertical("intent marketing customer acquisition comparison platform"))["name"] == "marketing_adtech"
    assert run_prep.infer_vertical(context_for_vertical("AI video creative studio video generation character consistency"))["name"] == "ai_video_creative"
    assert run_prep.infer_vertical(context_for_vertical("enterprise LLM token usage model routing compliance"))["name"] == "enterprise_llm"
    assert run_prep.infer_vertical(context_for_vertical("ecommerce marketplace SKU product catalog recommendation"))["name"] == "ecommerce"
    assert run_prep.infer_vertical(context_for_vertical("gaming studio player NPC asset generation localization"))["name"] == "gaming"
    assert run_prep.infer_vertical(context_for_vertical("single vague signal"))["name"] == "default"
    assert run_prep.infer_vertical(context_for_vertical("single vague signal"), "marketing_adtech")["confidence"] == "confirmed"


def test_question_filtering_by_vertical() -> None:
    marketing_questions, marketing_omitted, _ = run_prep.build_question_prefill(
        context_for_vertical("intent marketing customer acquisition comparison platform"),
        {"name": "marketing_adtech"},
    )
    marketing_text = "\n".join(item["question"] + " " + item["section"] for item in marketing_questions)
    assert "What metric are they focused on?" in marketing_text
    assert "Current Stack" in marketing_text
    assert any("Gaming-only" in item for item in marketing_omitted)

    video_questions, _, _ = run_prep.build_question_prefill(context_for_vertical("AI video creative studio video generation"), {"name": "ai_video_creative"})
    assert any(item["section"] == "Image / Video Usage" for item in video_questions)

    llm_questions, _, _ = run_prep.build_question_prefill(context_for_vertical("LLM token usage model routing"), {"name": "enterprise_llm"})
    assert any("Monthly token usage" in item["question"] for item in llm_questions)

    ecommerce_questions, _, _ = run_prep.build_question_prefill(context_for_vertical("ecommerce SKU catalog product recommendation"), {"name": "ecommerce"})
    assert any("SKU" in item["question"] or "Catalog" in item["question"] for item in ecommerce_questions)

    gaming_questions, _, _ = run_prep.build_question_prefill(context_for_vertical("gaming NPC asset generation"), {"name": "gaming"})
    assert any("Game genre" in item["question"] for item in gaming_questions)

    default_questions, _, _ = run_prep.build_question_prefill(context_for_vertical("unknown"), {"name": "default"})
    assert any("Current AI adoption" in item["question"] for item in default_questions)


def test_renderer_in_template_prefill_and_no_matrix() -> None:
    payload = base_render_payload()
    payload["vertical"] = {"name": "marketing_adtech", "display_name": "Marketing / AdTech", "confidence": "likely", "evidence": ["official site mentions intent marketing"]}
    payload["prospecting"] = {
        "prompt_path": "config/prospecting_prompt.md",
        "playbook_path": "config/industry_playbooks/marketing_adtech.md",
        "retained_questions_count": 1,
        "omitted_questions_summary": ["Gaming-only questions collapsed."],
        "meeting_readiness_assets": ["Demo / Case Study: Recommended for marketing/adtech."],
    }
    payload["question_prefill"] = [
        {
            "section": "AI Usage & Current Stack",
            "question": "Which models are you currently using?",
            "answer": "Not Found.",
            "confidence": "not_found",
            "evidence": [],
            "ask_in_meeting": "Which model providers are in production or evaluation today?",
            "why_it_matters": "Determines replacement/routing/evaluation positioning.",
            "vertical_relevance": "high",
        }
    ]
    rendered = render_prep_doc.render(payload)
    assert "Question Coverage Matrix" not in rendered
    assert "all-question table" in rendered
    assert "### AI Usage & Current Stack" in rendered
    assert "#### 1. Which models are you currently using?" in rendered
    assert "- **Pre-filled answer (Not Found)**: Not Found." in rendered
    assert "- **Ask in meeting**: Which model providers" in rendered
    assert "Detected Vertical" in rendered
    assert "Demo / Case Study: Recommended for marketing/adtech." in rendered


def test_meeting_output_template_notes_are_enhanced() -> None:
    rendered = render_prep_doc.render(base_render_payload())
    section = rendered.split("# Meeting Output Template", 1)[1].split("# Risk&Support", 1)[0]
    assert "Follow-up:" in section
    assert "Not Found:" in section
    assert "To Validate:" in section


def test_polished_output_has_no_invalid_confidence_combinations() -> None:
    payload = base_render_payload()
    payload["customer"]["industry"] = "To Validate: inferred from public web results"
    payload["vertical"] = {"name": "marketing_adtech", "display_name": "Marketing / AdTech", "confidence": "likely", "evidence": ["comparison platform", "customer acquisition", "intent marketing"]}
    rendered = render_prep_doc.render(payload)
    for bad in ["Known: To Validate", "Known: Not Found", "Known: Known", "Likely: Not Found"]:
        assert bad not in rendered


def test_polished_output_joins_lists_cleanly_and_limits_questions() -> None:
    payload = base_render_payload()
    payload["vertical"] = {"name": "marketing_adtech", "display_name": "Marketing / AdTech", "confidence": "likely", "evidence": ["comparison platform", "customer acquisition", "intent marketing"]}
    payload["enrichment"] = {
        "available": True,
        "known_use_cases": ["performance marketing and customer acquisition workflow", "consumer comparison platform content and ranking workflow"],
        "suggested_questions": [f"Question {idx}?" for idx in range(1, 9)],
    }
    rendered = render_prep_doc.render(payload)
    assert "comparison platform; customer acquisition; intent marketing" in rendered
    assert "workflowconsumer" not in rendered
    suggested = rendered.split("### Suggested Questions for This Meeting", 1)[1].split("###", 1)[0]
    assert len([line for line in suggested.splitlines() if line.strip().startswith(tuple(str(i) + "." for i in range(1, 10)))]) == 5
    assert "6. Question" not in suggested
    top_validate = rendered.split("**Top Things To Validate In The Meeting:**", 1)[1].split("###", 1)[0]
    assert "6. " not in top_validate


def test_official_evidence_preferred_over_linkedin_for_known_description() -> None:
    payload = base_render_payload()
    payload["customer"]["description"] = "Natural Intelligence is a global leader in intent marketing."
    payload["customer"]["website"] = "naturalint.com"
    payload["enrichment"] = {
        "available": True,
        "source": "web_search",
        "source_links": [{"url": "https://www.linkedin.com/company/naturalintelligence2"}],
        "dossier": {
            "source_evidence": [
                {"url": "https://www.linkedin.com/company/naturalintelligence2", "claim": "LinkedIn profile"},
                {"url": "https://www.naturalint.com/", "claim": "Official site"},
            ]
        },
    }
    payload["search_results"] = [{"source": "web", "url": "https://www.naturalint.com/", "title": "Natural Intelligence"}]
    rendered = render_prep_doc.render(payload)
    assert "Evidence: https://www.naturalint.com/." in rendered


def test_essential_background_backfills_leadership_fields() -> None:
    payload = base_render_payload()
    payload["vertical"] = {"name": "marketing_adtech", "display_name": "Marketing / AdTech", "confidence": "likely", "evidence": ["intent marketing"]}
    payload["customer"]["website"] = "naturalint.com"
    payload["enrichment"] = {
        "available": True,
        "dossier": {
            "company": "Natural Intelligence",
            "what_they_do": "Natural Intelligence connects consumers with brands.",
            "hq": "Tel Aviv, Israel",
            "target_users": "high-intent consumers, brand/advertiser partners, and publishers",
            "traffic_source_scale": "high-intent audiences; purchase decisions",
            "business_model": "intent-marketing / comparison-platform model",
            "social_content_presence": "",
        },
    }
    rendered = render_prep_doc.render(payload)
    for field in [
        "Target Users / Customer Segments",
        "Traffic Source / Scale",
        "Key Stakeholders / Buying Role",
        "Business Model / Revenue Model",
        "Social / Content / Paid Media Presence",
    ]:
        assert field in rendered
    assert "Likely: Tel Aviv, Israel (?)" in rendered
    assert "Do you produce paid social, landing page, image, or video creative at scale?" in rendered


def test_scale_signals_backfill_purchase_decisions_from_evidence() -> None:
    dossier = run_prep.extract_company_dossier(
        "Natural Intelligence",
        "Natural Intelligence is a leader in intent marketing.",
        [],
        [{"title": "Scale", "url": "https://example.com", "snippet": "over 60 million purchase decisions facilitated annually"}],
        [],
    )
    assert "over 60 million purchase decisions" in dossier["scale_signals"]


def test_traffic_source_scale_is_human_readable_with_volume_followup() -> None:
    note, label = render_prep_doc.traffic_source_note("affiliate; purchase decisions")
    assert label == "likely"
    assert "affiliate; purchase decisions" not in note
    assert "high-intent acquisition traffic" in note

    payload = base_render_payload()
    payload["enrichment"] = {"available": True, "dossier": {"traffic_source_scale": "affiliate; purchase decisions"}}
    rendered = render_prep_doc.render(payload)
    assert "monthly traffic or qualified-lead volume" in rendered


def test_pricing_packaging_is_cautious_for_public_packaging() -> None:
    payload = base_render_payload()
    payload["enrichment"] = {"available": True, "dossier": {"pricing_tiers": ["Team", "Business"]}}
    rendered = render_prep_doc.render(payload)
    assert "Pricing / Packaging | To Validate: public packaging/pricing terms were found" in rendered
    assert "Likely: Team; Business" not in rendered


def test_weak_identity_output_does_not_leak_previous_customer_name() -> None:
    payload = base_render_payload()
    payload["customer"]["name"] = "Fabien Siderakis"
    payload["vertical"] = {"name": "default", "display_name": "Default / Unknown", "confidence": "unknown", "evidence": []}
    rendered = render_prep_doc.render(payload)
    assert "Fabien Siderakis" in rendered
    assert "David Agronov" not in rendered


def test_unknown_vertical_uses_neutral_leadership_fields() -> None:
    payload = base_render_payload()
    payload["customer"]["name"] = "Fabien Siderakis"
    payload["vertical"] = {"name": "default", "display_name": "Default / Unknown", "confidence": "unknown", "evidence": []}
    payload["enrichment"] = {"available": True, "dossier": {}}
    rendered = render_prep_doc.render(payload)
    assert "high-intent consumers" not in rendered
    assert "brand/advertiser partners" not in rendered
    assert "intent-marketing / comparison-platform model" not in rendered
    assert "Target Users / Customer Segments | To Validate: target users/customer segments are not confirmed" in rendered
    assert "Business Model / Revenue Model | To Validate: business model/revenue model is not confirmed" in rendered


def test_competitor_pricing_pages_do_not_populate_customer_pricing() -> None:
    dossier = run_prep.extract_company_dossier(
        None,
        "Fabien Siderakis public profile",
        [],
        [
            {"title": "Plans & Pricing | Claude by Anthropic", "url": "https://claude.com/pricing", "snippet": "Free, Pro, Team, and Enterprise tiers"},
            {"title": "API Pricing - OpenAI", "url": "https://openai.com/api/pricing/", "snippet": "Compare token costs and service tiers"},
            {"title": "Anthropic enterprise analytics", "url": "https://www.finout.io/blog/anthropics-enterprise-analytics", "snippet": "Enterprise and Business pricing analysis"},
        ],
        [],
    )
    assert dossier["pricing_tiers"] == []


def test_person_only_candidate_company_is_likely_and_to_validate() -> None:
    dossier = run_prep.extract_company_dossier(
        None,
        "Fabien Siderakis is associated with LA METHODE PAPIER.",
        [],
        [{"title": "Mentions legales", "url": "https://lamethodepapier.com", "snippet": "Siderakis Fabien LA METHODE PAPIER"}],
        [],
    )
    assert dossier["candidate_company"] == "La Methode Papier"

    payload = base_render_payload()
    payload["customer"]["name"] = "Fabien Siderakis"
    payload["enrichment"] = {"available": True, "dossier": dossier}
    rendered = render_prep_doc.render(payload)
    assert "Candidate Company / Product | Likely: La Methode Papier (?)" in rendered
    assert "Confirm whether the meeting is for Fabien Siderakis personally, La Methode Papier, or another company/product" in rendered


def test_prior_docs_attribution_distinguishes_candidate_from_usable() -> None:
    payload = base_render_payload()
    payload["prior_docs"] = [{"title": "BytePlus <> David - Pre-Meeting Prep", "url": "https://doc.example", "summary": "Web search results: https://example.com"}]
    rendered = render_prep_doc.render(payload)
    assert "Candidate prior customer docs found, but no usable prior customer profile content was extracted" in rendered
    assert "No prior BytePlus customer profile found" not in rendered

    payload["prior_docs"] = [{"title": "Natural Intelligence Customer Profile", "url": "https://profile.example", "summary": "Confirmed engagement history", "engagement_rows": [{"stage": "Discovery", "key_information": "Used", "next_step": "Next"}]}]
    rendered = render_prep_doc.render(payload)
    assert "usable prior customer profile docs" in rendered
    assert "Prior customer profile content used: https://profile.example" in rendered


def test_company_dossier_extracts_fields_from_evidence() -> None:
    dossier = run_prep.extract_company_dossier(
        "ImagineArt",
        "ImagineArt AI creative suite",
        ["image generation"],
        [
            {
                "title": "ImagineArt",
                "url": "https://www.imagine.art/",
                "snippet": "generates images, videos, shorts, and voice from text prompt. BG remover, upscaler, and custom models.",
            },
            {
                "title": "Scale",
                "url": "https://news.example/imagineart",
                "snippet": "over 3.5 million active users and 3.2 million downloads. ImagineArt is located in San Francisco, California, United States. Who are competitors?",
            },
        ],
        [],
    )
    assert "AI image generation" in dossier["product_modules"]
    assert "over 3.5 million active users" in dossier["scale_signals"]
    assert dossier["hq"] == "San Francisco, California, United States"


def test_template_uses_objectives_spelling() -> None:
    rendered = render_prep_doc.render(base_render_payload())
    assert "Objectives" in rendered
    assert "Obectives" not in rendered


def test_notification_payload_rejects_invalid_recipient() -> None:
    result = run_prep.PrepResult("BytePlus <> Moburst - 15-05-2026 - Pre-Meeting Prep", None, "window", "Moburst", "likely", [])
    cmd, warning = run_prep.notification_command(result, "bad-id")
    assert cmd is None
    assert warning
    assert "open_id" in warning


def test_notification_payload_for_open_id_uses_markdown_user_id() -> None:
    result = run_prep.PrepResult("BytePlus <> Moburst - 15-05-2026 - Pre-Meeting Prep", None, "window", "Moburst", "likely", ["MCP enrichment unavailable"])
    cmd, warning = run_prep.notification_command(result, "ou_3b4e6414910946deea7529b7c8dd4cd8")
    assert warning is None
    assert cmd is not None
    assert "--user-id" in cmd
    assert "ou_3b4e6414910946deea7529b7c8dd4cd8" in cmd
    assert "--markdown" in cmd
    assert "Meeting prep generated." in cmd[cmd.index("--markdown") + 1]


def test_package_excludes_secrets_outputs_and_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(package_skill, "DIST", tmp_path)
    zip_path = package_skill.build_zip()
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "scripts/run_prep.py" in names
    assert "scripts/render_prep_doc.py" in names
    assert "README.md" in names
    assert "SKILL.md" in names
    assert "config/prep.env.example" in names
    assert "config/prospecting_prompt.md" in names
    assert "config/industry_playbooks/default.md" in names
    assert "config/industry_playbooks/marketing_adtech.md" in names
    assert "config/industry_playbooks/ai_video_creative.md" in names
    assert "config/industry_playbooks/ecommerce.md" in names
    assert "config/industry_playbooks/gaming.md" in names
    assert "config/industry_playbooks/enterprise_llm.md" in names
    assert not any(name.startswith("outputs/prep/") for name in names)
    assert not any("__pycache__" in name or ".pytest_cache" in name for name in names)
    assert ".env" not in names
    assert not any("token" in name.lower() for name in names)


def test_output_json_shape_for_normalized_context() -> None:
    context = run_prep.PrepContext(
        customer=run_prep.CustomerIdentity("Moburst", "moburst.com", None, "confirmed", ["test"]),
        event=None,
        prior_docs=[],
        enrichment=None,
        missing_context=["meeting context"],
    )
    payload = {"normalized": run_prep.context_to_renderer_json(context)}
    assert json.loads(json.dumps(payload))["normalized"]["customer"]["name"] == "Moburst"
