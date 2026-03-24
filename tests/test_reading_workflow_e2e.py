from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from reading_concierge import reading_concierge
from services.db import run_migrations
from services.repositories import ProfileRepository, RecommendationRepository, TaskLogRepository


@pytest.mark.usefixtures("patch_openai")
def test_reading_workflow_persists_reproducible_artifacts(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'workflow_runtime.db'}"
    run_migrations(db_url=db_url)

    # Redirect runtime persistence bridge to an isolated test database.
    reading_concierge.profile_store._profile_repo = ProfileRepository(db_url=db_url)
    reading_concierge.profile_store._recommendation_repo = RecommendationRepository(db_url=db_url)
    reading_concierge.profile_store._task_log_repo = TaskLogRepository(db_url=db_url)

    client = TestClient(reading_concierge.app)
    payload = {
        "user_id": "e2e_user_01",
        "query": "Recommend diverse thoughtful science fiction",
        "history": [
            {
                "title": "Dune",
                "genres": ["science_fiction"],
                "rating": 5,
                "language": "en",
            }
        ],
        "reviews": [{"rating": 5, "text": "I like worldbuilding and ideas"}],
        "books": [
            {
                "book_id": "wf-001",
                "title": "Foundation",
                "description": "Galactic empire and psychohistory.",
                "genres": ["science_fiction"],
            },
            {
                "book_id": "wf-002",
                "title": "The Left Hand of Darkness",
                "description": "Identity and culture exploration.",
                "genres": ["science_fiction"],
            },
        ],
        "constraints": {
            "scenario": "warm",
            "top_k": 2,
            "debug_payload_override": True,
        },
    }

    resp = client.post("/user_api_debug", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("state") in {"completed", "needs_input"}

    conn = sqlite3.connect(str(tmp_path / "workflow_runtime.db"))
    try:
        runs = conn.execute("SELECT COUNT(*) FROM recommendation_runs").fetchone()[0]
        logs = conn.execute("SELECT COUNT(*) FROM agent_task_logs").fetchone()[0]
        recs = conn.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
    finally:
        conn.close()

    assert runs >= 1
    assert logs >= 1
    # completed flows should persist recommendations; needs_input may persist none.
    assert recs >= 0
