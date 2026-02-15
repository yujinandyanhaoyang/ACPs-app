"""
reading_concierge live HTTP E2E tests (requires real service process).

Example:
    set END_TO_END=1
    set READING_CONCIERGE_BASE_URL=http://localhost:8220
    venv\\Scripts\\python.exe -m pytest -q tests/test_reading_concierge_e2e.py
"""

import os
import uuid

import pytest
import requests

pytestmark = pytest.mark.skipif(
    os.getenv("END_TO_END") != "1",
    reason="Set END_TO_END=1 to run live HTTP integration tests.",
)


@pytest.fixture(autouse=True)
def patch_openai():
    yield


BASE_URL = os.getenv("READING_CONCIERGE_BASE_URL", "http://localhost:8220").rstrip("/")
USER_API = f"{BASE_URL}/user_api"


def _post_user_api(payload: dict, timeout=60):
    try:
        resp = requests.post(USER_API, json=payload, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        pytest.skip(f"Cannot connect to reading concierge at {USER_API}: {exc}")
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
    return resp.json()


def test_http_live_orchestration_flow():
    payload = {
        "session_id": f"session-{uuid.uuid4()}",
        "query": "Need personalized books for science and culture interests.",
        "user_profile": {"preferred_language": "en"},
        "history": [
            {"title": "Dune", "genres": ["science_fiction"], "rating": 5, "language": "en"},
            {"title": "Sapiens", "genres": ["history"], "rating": 4, "language": "en"},
        ],
        "reviews": [{"rating": 5, "text": "love big ideas"}],
        "candidate_ids": ["live-book-1", "live-book-2"],
        "constraints": {"top_k": 2},
    }
    res = _post_user_api(payload)
    assert res.get("state") in {"completed", "needs_input"}
    if res.get("state") == "completed":
        assert len(res.get("recommendations") or []) >= 1
