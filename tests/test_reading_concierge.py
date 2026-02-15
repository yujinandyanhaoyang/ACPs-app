import json

import pytest


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

    assert res["metric_snapshot"]
    assert res["explanations"]


@pytest.mark.usefixtures("patch_openai")
def test_orchestration_needs_input_when_profile_missing(client_reading_concierge):
    payload = {
        "query": "Recommend me books",
        "user_profile": {},
        "history": [],
        "reviews": [],
        "books": [],
    }
    res = _post_user_api(client_reading_concierge, payload)

    assert res["state"] == "needs_input"
    assert res["partner_tasks"]["reader_profile_agent_001"]["state"] == "awaiting-input"
    assert "book_content_agent_001" not in res["partner_tasks"]
    assert "rec_ranking_agent_001" not in res["partner_tasks"]
