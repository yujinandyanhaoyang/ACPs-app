from __future__ import annotations

import sqlite3
from pathlib import Path

from services.db import run_migrations
from services.repositories import ProfileRepository, RecommendationRepository, TaskLogRepository
from services.user_profile_store import UserProfileStore


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'runtime_test.db'}"


def test_run_migrations_creates_core_tables(tmp_path):
    db_url = _db_url(tmp_path)
    applied = run_migrations(db_url=db_url)
    assert applied

    conn = sqlite3.connect(str(tmp_path / "runtime_test.db"))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    expected = {
        "schema_migrations",
        "users",
        "user_events",
        "user_profiles",
        "books",
        "book_features",
        "recommendation_runs",
        "recommendations",
        "agent_task_logs",
    }
    assert expected.issubset(tables)


def test_repositories_write_run_recommendations_and_task_logs(tmp_path):
    db_url = _db_url(tmp_path)
    run_migrations(db_url=db_url)

    profile_repo = ProfileRepository(db_url=db_url)
    rec_repo = RecommendationRepository(db_url=db_url)
    task_repo = TaskLogRepository(db_url=db_url)

    profile_repo.upsert_user("u1", {"segment": "warm"})
    profile_repo.append_event("u1", "rating", {"book_id": "b1", "rating": 5})
    profile_repo.save_profile_snapshot(
        "u1",
        {
            "profile_version": "u1-v1",
            "generated_at": "2026-03-24T00:00:00+00:00",
            "source_event_window": {"history_count": 1},
            "cold_start_flag": False,
        },
    )

    rec_repo.create_recommendation_run(
        run_id="run-001",
        user_id="u1",
        query="science fiction",
        profile_version="u1-v1",
        candidate_set_version_or_hash="cand-001",
        candidate_provenance={"retrieval_rule": "unit-test"},
        book_feature_version_or_hash="bf-001",
        ranking_policy_version="policy-001",
        weights_or_policy_snapshot={"semantic": 0.4},
    )
    rec_repo.save_recommendations(
        run_id="run-001",
        recommendations=[
            {
                "book_id": "b1",
                "rank_position": 1,
                "score_total": 0.91,
                "score_cf": 0.4,
                "score_content": 0.3,
                "score_kg": 0.1,
                "score_diversity": 0.11,
                "scenario_policy": "warm",
                "explanation": "good fit",
                "explanation_evidence_refs": ["score_parts.semantic"],
            }
        ],
    )

    task_repo.append(
        task_id="task-001",
        session_id="sess-1",
        sender_id="reading_concierge_001",
        receiver_id="reader_profile_agent_001",
        state_transition="completed",
        payload={"route": "local"},
    )

    conn = sqlite3.connect(str(tmp_path / "runtime_test.db"))
    try:
        runs = conn.execute("SELECT COUNT(*) FROM recommendation_runs").fetchone()[0]
        recs = conn.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
        logs = conn.execute("SELECT COUNT(*) FROM agent_task_logs").fetchone()[0]
        profiles = conn.execute("SELECT COUNT(*) FROM user_profiles").fetchone()[0]
    finally:
        conn.close()

    assert runs == 1
    assert recs == 1
    assert logs == 1
    assert profiles == 1


def test_recovery_after_restart_reuses_persisted_profile_events(tmp_path):
    store_path = tmp_path / "legacy_store.db"
    first = UserProfileStore(db_path=str(store_path))
    first.append_event("restart-user", "review", {"text": "great read", "rating": 5})
    first.save_profile_snapshot(
        "restart-user",
        {
            "profile_version": "restart-user-v1",
            "generated_at": "2026-03-25T00:00:00+00:00",
            "source_event_window": {"review_count": 1},
            "feature_vector": [0.1, 0.2],
        },
    )

    second = UserProfileStore(db_path=str(store_path))
    context = second.get_user_context("restart-user")
    snapshot = second.get_latest_profile("restart-user")

    assert len(context.get("reviews") or []) >= 1
    assert snapshot.get("profile_version") == "restart-user-v1"


def test_retention_hooks_prune_old_runs_and_task_logs(tmp_path):
    db_url = _db_url(tmp_path)
    run_migrations(db_url=db_url)
    rec_repo = RecommendationRepository(db_url=db_url)
    task_repo = TaskLogRepository(db_url=db_url)

    for idx in range(1, 4):
        run_id = f"run-prune-{idx}"
        rec_repo.create_recommendation_run(
            run_id=run_id,
            user_id="u-prune",
            query=f"query-{idx}",
            profile_version=f"v{idx}",
            candidate_set_version_or_hash=f"cand-{idx}",
            candidate_provenance={"retrieval_rule": "test"},
            book_feature_version_or_hash=f"bf-{idx}",
            ranking_policy_version="policy-v1",
            weights_or_policy_snapshot={"semantic": 0.4},
            run_timestamp=f"2026-03-25T00:00:0{idx}+00:00",
        )
        task_repo.append(
            task_id="task-prune-1",
            session_id="session-prune",
            sender_id="leader",
            receiver_id="partner",
            state_transition="completed",
            payload={"seq": idx},
            timestamp=f"2026-03-25T00:00:0{idx}+00:00",
        )

    pruned_runs = rec_repo.prune_old_runs(keep_latest_per_user=1)
    pruned_logs = task_repo.prune_old_logs(keep_latest_per_task=1)

    conn = sqlite3.connect(str(tmp_path / "runtime_test.db"))
    try:
        remaining_runs = conn.execute(
            "SELECT COUNT(*) FROM recommendation_runs WHERE user_id = 'u-prune'"
        ).fetchone()[0]
        remaining_logs = conn.execute(
            "SELECT COUNT(*) FROM agent_task_logs WHERE task_id = 'task-prune-1'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert pruned_runs == 2
    assert pruned_logs == 2
    assert remaining_runs == 1
    assert remaining_logs == 1
