from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from services.repositories import ProfileRepository, RecommendationRepository


def _iter_rows(conn: sqlite3.Connection, sql: str, params: tuple = ()):  # noqa: ANN001
    conn.row_factory = sqlite3.Row
    for row in conn.execute(sql, params):
        yield row


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill user events/profile snapshots from legacy store DB")
    parser.add_argument("--legacy-db", default="data/user_profile_store.db")
    args = parser.parse_args()

    legacy_path = Path(args.legacy_db)
    if not legacy_path.exists():
        print(f"Legacy DB not found: {legacy_path}")
        return 1

    profile_repo = ProfileRepository()
    rec_repo = RecommendationRepository()

    conn = sqlite3.connect(str(legacy_path))
    try:
        users = set()

        for row in _iter_rows(conn, "SELECT user_id, event_type, payload_json, created_at FROM user_events ORDER BY id ASC"):
            user_id = str(row["user_id"] or "").strip()
            if not user_id:
                continue
            users.add(user_id)
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {}
            profile_repo.append_event(user_id, str(row["event_type"] or "unknown"), payload, created_at=row["created_at"])

        for row in _iter_rows(
            conn,
            """
            SELECT user_id, profile_version, generated_at, source_event_window_json, payload_json, created_at
            FROM user_profiles
            ORDER BY id ASC
            """,
        ):
            user_id = str(row["user_id"] or "").strip()
            if not user_id:
                continue
            users.add(user_id)
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {}
            payload.setdefault("profile_version", row["profile_version"])
            payload.setdefault("generated_at", row["generated_at"])
            profile_repo.save_profile_snapshot(user_id, payload)

        for row in _iter_rows(
            conn,
            """
            SELECT
                user_id,
                query,
                profile_version,
                candidate_set_version_or_hash,
                candidate_provenance_json,
                book_feature_version_or_hash,
                ranking_policy_version,
                weights_or_policy_snapshot_json,
                created_at,
                id
            FROM recommendation_runs
            ORDER BY id ASC
            """,
        ):
            user_id = str(row["user_id"] or "").strip()
            if not user_id:
                continue
            users.add(user_id)
            try:
                candidate_provenance = json.loads(row["candidate_provenance_json"] or "{}")
            except Exception:
                candidate_provenance = {}
            try:
                weights = json.loads(row["weights_or_policy_snapshot_json"] or "{}")
            except Exception:
                weights = {}

            run_id = f"legacy-run-{row['id']}"
            rec_repo.create_recommendation_run(
                run_id=run_id,
                user_id=user_id,
                query=str(row["query"] or ""),
                profile_version=str(row["profile_version"] or ""),
                candidate_set_version_or_hash=str(row["candidate_set_version_or_hash"] or ""),
                candidate_provenance=candidate_provenance,
                book_feature_version_or_hash=str(row["book_feature_version_or_hash"] or ""),
                ranking_policy_version=str(row["ranking_policy_version"] or ""),
                weights_or_policy_snapshot=weights,
                run_timestamp=str(row["created_at"] or ""),
            )

        print(f"Backfill complete. Users touched: {len(users)}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
