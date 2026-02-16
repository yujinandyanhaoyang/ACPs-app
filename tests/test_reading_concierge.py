import json

import pytest
import reading_concierge.reading_concierge as concierge


def _post_user_api(client, payload):
    resp = client.post("/user_api", json=payload)
    assert resp.status_code == 200
    return resp.json()


def _print_flow_response(body):
    print("\n[reading_concierge integration] response:")
    print(json.dumps(body, ensure_ascii=False, indent=2))


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

    partner_tasks = res["partner_tasks"]
    assert partner_tasks["reader_profile_agent_001"]["state"] == "completed"
    assert partner_tasks["book_content_agent_001"]["state"] == "completed"
    assert partner_tasks["rec_ranking_agent_001"]["state"] == "completed"
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
    payload = {
        "query": "Need starter recommendations for reading science and culture.",
        "user_profile": {},
        "history": [],
        "reviews": [],
        "candidate_ids": ["cold-1", "cold-2"],
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
