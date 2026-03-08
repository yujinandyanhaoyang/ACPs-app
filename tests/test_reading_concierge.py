import json
import asyncio

import pytest
import reading_concierge.reading_concierge as concierge
from services.book_retrieval import load_books


def _post_user_api(client, payload):
    resp = client.post("/user_api", json=payload)
    assert resp.status_code == 200
    return resp.json()


def _print_flow_response(body):
    print("\n[reading_concierge integration] response:")
    print(json.dumps(body, ensure_ascii=False, indent=2))


def _demo_payload_with_query(query: str) -> dict:
    return {
        "query": query,
        "user_profile": {"age": 29, "preferred_language": "en"},
        "history": [
            {
                "title": "Dune",
                "genres": ["science_fiction"],
                "themes": ["politics", "ecology"],
                "rating": 5,
                "language": "en",
            }
        ],
        "reviews": [{"rating": 5, "text": "I enjoy nuanced worldbuilding and ideas."}],
        "books": [
            {
                "book_id": "sci-1",
                "title": "Foundation",
                "description": "A science fiction saga about psychohistory and galactic empires.",
                "genres": ["science_fiction"],
            },
            {
                "book_id": "hist-1",
                "title": "The Silk Roads",
                "description": "A global history narrative connecting trade, diplomacy, and empires.",
                "genres": ["history"],
            },
            {
                "book_id": "soc-1",
                "title": "Sapiens",
                "description": "An accessible history of humankind and social evolution.",
                "genres": ["history", "society"],
            },
        ],
        "constraints": {
            "scenario": "warm",
            "top_k": 2,
            "ground_truth_ids": ["sci-1"],
            "ablation": True,
        },
    }


def test_demo_page_route_available(client_reading_concierge):
    resp = client_reading_concierge.get("/demo")
    assert resp.status_code == 200
    assert "Reading Concierge" in resp.text
    assert "Top K Results" in resp.text


def test_demo_status_route_available(client_reading_concierge):
    resp = client_reading_concierge.get("/demo/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service"] == "reading_concierge"
    assert "demo_page_available" in payload
    assert "benchmark_summary_available" in payload
    assert "retrieval_corpus" in payload
    assert "path" in payload["retrieval_corpus"]


def test_demo_retrieval_corpus_route_available(client_reading_concierge):
    resp = client_reading_concierge.get("/demo/retrieval-corpus")
    assert resp.status_code == 200
    payload = resp.json()
    assert "path" in payload
    assert "selection_source" in payload


def test_demo_benchmark_summary_route_available(client_reading_concierge):
    resp = client_reading_concierge.get("/demo/benchmark-summary")
    assert resp.status_code == 200
    payload = resp.json()
    assert "available" in payload
    if payload["available"]:
        assert "summary" in payload
    else:
        assert "message" in payload


@pytest.mark.usefixtures("patch_openai")
def test_unified_orchestration_flow_completed(client_reading_concierge):
    payload = {
        "query": "I want personalized sci-fi recommendations with diverse themes.",
        "user_profile": {"age": 27, "preferred_language": "en"},
        "history": [
            {
                "title": "Dune",
                "genres": ["science_fiction", "classic"],
                "themes": ["politics", "ecology"],
                "rating": 5,
                "format": "ebook",
                "language": "en",
            },
            {
                "title": "The Left Hand of Darkness",
                "genres": ["science_fiction"],
                "themes": ["identity", "culture"],
                "rating": 4,
                "format": "print",
                "language": "en",
            },
        ],
        "reviews": [
            {"rating": 5, "text": "Loved political depth and worldbuilding."},
            {"rating": 4, "text": "Great balance of ideas and character arcs."},
        ],
        "books": [
            {
                "book_id": "b1",
                "title": "Foundation",
                "description": "A science fiction saga about civilization cycles.",
                "genres": ["science", "fiction"],
                "kg_node_id": "kg:foundation",
            },
            {
                "book_id": "b2",
                "title": "Hyperion",
                "description": "A layered story with diverse voices and themes.",
                "genres": ["science", "fiction"],
                "kg_node_id": "kg:hyperion",
            },
        ],
        "constraints": {
            "top_k": 2,
            "novelty_threshold": 0.4,
            "min_new_items": 1,
            "ground_truth_ids": ["b1"],
            "ablation": True,
        },
    }
    res = _post_user_api(client_reading_concierge, payload)
    _print_flow_response(res)

    assert res["state"] == "completed"
    assert len(res["recommendations"]) >= 1
    assert any(r.get("title") in {"Foundation", "Hyperion"} for r in res["recommendations"])

    partner_tasks = res["partner_tasks"]
    assert partner_tasks["reader_profile_agent_001"]["state"] == "completed"
    assert partner_tasks["book_content_agent_001"]["state"] == "completed"
    assert partner_tasks["rec_ranking_agent_001"]["state"] == "completed"
    assert partner_tasks["reader_profile_agent_001"]["route_outcome"] in {"local_only", "remote_success", "remote_failed_local_fallback"}
    assert "remote_attempted" in partner_tasks["reader_profile_agent_001"]
    assert partner_tasks["reader_profile_agent_001"]["acceptance"]["passed"] is True
    assert partner_tasks["book_content_agent_001"]["acceptance"]["passed"] is True
    assert partner_tasks["rec_ranking_agent_001"]["acceptance"]["passed"] is True

    assert res["metric_snapshot"]
    assert res["explanations"]
    assert res["evaluation"]["metrics"]["precision_at_k"] is not None
    assert "ablation" in res["evaluation"]


@pytest.mark.usefixtures("patch_openai")
def test_orchestration_needs_input_in_warm_mode_when_profile_missing(client_reading_concierge):
    payload = {
        "query": "Recommend me books",
        "user_profile": {},
        "history": [],
        "reviews": [],
        "books": [],
        "constraints": {"scenario": "warm"},
    }
    res = _post_user_api(client_reading_concierge, payload)

    assert res["state"] == "needs_input"
    assert res["partner_tasks"]["reader_profile_agent_001"]["state"] == "awaiting-input"
    assert res["partner_tasks"]["book_content_agent_001"]["state"] == "completed"
    assert res["partner_tasks"]["book_content_agent_001"]["acceptance"]["passed"] is True
    assert "rec_ranking_agent_001" not in res["partner_tasks"]


@pytest.mark.usefixtures("patch_openai")
def test_orchestration_cold_start_auto_mode_completes(client_reading_concierge):
    available_books = load_books()
    assert len(available_books) >= 2

    payload = {
        "query": "Need starter recommendations for reading science and culture.",
        "user_profile": {},
        "history": [],
        "reviews": [],
        "candidate_ids": [
            str(available_books[0].get("book_id")),
            str(available_books[1].get("book_id")),
        ],
    }
    res = _post_user_api(client_reading_concierge, payload)
    assert res["scenario"] == "cold"
    assert res["state"] == "completed"
    assert len(res["recommendations"]) >= 1


@pytest.mark.usefixtures("patch_openai")
def test_orchestration_explore_mode_applies_policy(client_reading_concierge):
    payload = {
        "query": "Explore novel and diverse books.",
        "user_profile": {"preferred_language": "en"},
        "history": [
            {
                "title": "Book A",
                "genres": ["fiction"],
                "rating": 4,
                "language": "en",
            }
        ],
        "books": [
            {
                "book_id": "ex-1",
                "title": "Exploration One",
                "description": "global multicultural story",
                "genres": ["fiction"],
            },
            {
                "book_id": "ex-2",
                "title": "Exploration Two",
                "description": "innovative narrative",
                "genres": ["fiction"],
            },
        ],
        "constraints": {"scenario": "explore", "top_k": 2},
    }
    res = _post_user_api(client_reading_concierge, payload)
    assert res["scenario"] == "explore"
    ranking_result = res["partner_results"]["rec_ranking_agent_001"]["result"]
    constraints = ranking_result["outputs"]["constraints"]
    weights = ranking_result["outputs"]["scoring_weights"]
    assert constraints["min_new_items"] >= 1
    assert constraints["novelty_threshold"] >= 0.5
    assert weights["diversity"] >= 0.35


@pytest.mark.usefixtures("patch_openai")
def test_remote_discovery_fallback_to_local(monkeypatch, client_reading_concierge):
    monkeypatch.setattr(concierge, "PARTNER_MODE", "auto")

    async def fake_discovery(partner_key: str):
        return "http://127.0.0.1:9999/unreachable-rpc"

    async def fake_remote_call(rpc_url, payload, task_id=None):
        raise RuntimeError("simulated remote failure")

    monkeypatch.setattr(concierge, "_discover_partner_endpoint", fake_discovery)
    monkeypatch.setattr(concierge, "_invoke_remote_rpc", fake_remote_call)

    payload = {
        "query": "Recommend me books for history and technology.",
        "user_profile": {"preferred_language": "en"},
        "history": [
            {
                "title": "Sapiens",
                "genres": ["history"],
                "rating": 4,
                "language": "en",
            }
        ],
        "books": [
            {
                "book_id": "fb-1",
                "title": "Fallback Book",
                "description": "history and technology overview",
                "genres": ["history", "technology"],
            }
        ],
    }
    res = _post_user_api(client_reading_concierge, payload)
    assert res["state"] == "completed"
    tasks = res["partner_tasks"]
    assert tasks["reader_profile_agent_001"]["route"] == "local"
    assert tasks["book_content_agent_001"]["route"] == "local"
    assert tasks["rec_ranking_agent_001"]["route"] == "local"
    assert tasks["reader_profile_agent_001"]["fallback"] is True
    assert tasks["reader_profile_agent_001"]["remote_attempted"] is True
    assert tasks["reader_profile_agent_001"]["route_outcome"] == "remote_failed_local_fallback"


@pytest.mark.usefixtures("patch_openai")
def test_remote_strict_mode_disables_local_fallback(monkeypatch, client_reading_concierge):
    monkeypatch.setattr(concierge, "PARTNER_MODE", "auto")

    async def fake_discovery(partner_key: str):
        return "http://127.0.0.1:9999/unreachable-rpc"

    async def fake_remote_call(rpc_url, payload, task_id=None):
        raise RuntimeError("simulated remote failure")

    monkeypatch.setattr(concierge, "_discover_partner_endpoint", fake_discovery)
    monkeypatch.setattr(concierge, "_invoke_remote_rpc", fake_remote_call)

    payload = {
        "query": "Recommend architecture books with strict remote validation.",
        "user_profile": {"preferred_language": "en"},
        "history": [
            {
                "title": "Clean Architecture",
                "genres": ["technology"],
                "rating": 5,
                "language": "en",
            }
        ],
        "books": [
            {
                "book_id": "strict-1",
                "title": "Building Microservices",
                "description": "service architecture and reliability",
                "genres": ["technology"],
            }
        ],
        "constraints": {"strict_remote_validation": True},
    }
    res = _post_user_api(client_reading_concierge, payload)

    assert res["state"] == "needs_input"
    tasks = res["partner_tasks"]
    assert tasks["reader_profile_agent_001"]["state"] == "failed"
    assert tasks["reader_profile_agent_001"]["fallback"] is False
    assert tasks["reader_profile_agent_001"]["remote_attempted"] is True
    assert tasks["reader_profile_agent_001"]["route_outcome"] == "remote_failed_strict"
    assert "rec_ranking_agent_001" not in tasks


@pytest.mark.usefixtures("patch_openai")
def test_demo_e2e_different_queries_should_change_recommendation_order(client_reading_concierge):
    science_query = "Recommend science fiction books focused on future civilizations and technology."
    history_query = "Recommend history books focused on trade routes and empires."

    sci_res = _post_user_api(client_reading_concierge, _demo_payload_with_query(science_query))
    hist_res = _post_user_api(client_reading_concierge, _demo_payload_with_query(history_query))

    assert sci_res["state"] == "completed"
    assert hist_res["state"] == "completed"

    sci_top_ids = [row.get("book_id") for row in (sci_res.get("recommendations") or [])]
    hist_top_ids = [row.get("book_id") for row in (hist_res.get("recommendations") or [])]

    assert sci_top_ids and hist_top_ids
    assert sci_top_ids != hist_top_ids


@pytest.mark.usefixtures("patch_openai")
def test_demo_e2e_explanations_follow_human_readable_language(client_reading_concierge):
    res = _post_user_api(
        client_reading_concierge,
        _demo_payload_with_query("Recommend science fiction with social and philosophical depth."),
    )

    assert res["state"] == "completed"
    explanations = res.get("explanations") or []
    assert explanations

    for item in explanations:
        text = str(item.get("justification") or "").strip()
        assert text
        assert "_" not in text
        assert len(text.split()) >= 5


@pytest.mark.usefixtures("patch_openai")
def test_demo_e2e_recommendation_output_has_no_logic_inconsistency(client_reading_concierge):
    res = _post_user_api(
        client_reading_concierge,
        _demo_payload_with_query("Recommend books about big historical transitions and societal change."),
    )

    assert res["state"] == "completed"
    rows = res.get("recommendations") or []
    assert rows

    top_k = (_demo_payload_with_query("tmp")["constraints"]["top_k"])
    assert len(rows) <= top_k

    ranks = [row.get("rank") for row in rows]
    assert ranks == list(range(1, len(rows) + 1))

    ids = [row.get("book_id") for row in rows]
    assert all(ids)
    assert len(ids) == len(set(ids))

    for row in rows:
        assert row.get("title")
        assert isinstance(row.get("score_parts"), dict)
        assert row.get("composite_score") is not None


# ---------------------------------------------------------------------------
# Phase 1c — LRU session eviction (D8)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("patch_openai")
def test_session_lru_eviction(monkeypatch, client_reading_concierge):
    """Verify that sessions are evicted when the cap is exceeded."""
    # Lower the cap so we can trigger eviction cheaply
    monkeypatch.setattr(concierge, "MAX_SESSIONS", 3)
    concierge.sessions.clear()

    base_payload = {
        "query": "test eviction",
        "user_profile": {"preferred_language": "en"},
        "history": [{"title": "A", "genres": ["fiction"], "rating": 4, "language": "en"}],
        "books": [{"book_id": "ev-1", "title": "Evict Book", "description": "d", "genres": ["fiction"]}],
    }

    # Fill 3 sessions
    for i in range(3):
        resp = client_reading_concierge.post(
            "/user_api", json={**base_payload, "session_id": f"s-{i}"}
        )
        assert resp.status_code == 200

    assert len(concierge.sessions) == 3
    assert "s-0" in concierge.sessions

    # 4th session should evict s-0 (oldest)
    resp = client_reading_concierge.post(
        "/user_api", json={**base_payload, "session_id": "s-new"}
    )
    assert resp.status_code == 200
    assert len(concierge.sessions) == 3
    assert "s-0" not in concierge.sessions
    assert "s-new" in concierge.sessions

    # Accessing s-1 again should refresh it (move to end), so s-2 becomes oldest
    resp = client_reading_concierge.post(
        "/user_api", json={**base_payload, "session_id": "s-1"}
    )
    assert resp.status_code == 200
    assert "s-1" in concierge.sessions

    # Adding another session should now evict s-2 (the oldest)
    resp = client_reading_concierge.post(
        "/user_api", json={**base_payload, "session_id": "s-final"}
    )
    assert resp.status_code == 200
    assert "s-2" not in concierge.sessions
    assert "s-1" in concierge.sessions
    assert "s-final" in concierge.sessions

    concierge.sessions.clear()


def test_derive_books_does_not_fabricate_candidates_when_no_match():
    rows = asyncio.run(
        concierge._derive_books_from_query(
            query="zzzz_unmatched_query_token_987654321",
            candidate_ids=["not-a-real-book-id"],
        )
    )
    assert rows == []
