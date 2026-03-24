from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services.db import transaction, utc_now


class ProfileRepository:
    def __init__(self, db_url: Optional[str] = None) -> None:
        self.db_url = db_url

    def upsert_user(self, user_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        if not str(user_id or "").strip():
            return
        now = utc_now()
        with transaction(self.db_url) as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    metadata_json = excluded.metadata_json
                """,
                (user_id, now, now, json.dumps(metadata or {}, ensure_ascii=False)),
            )

    def append_event(self, user_id: str, event_type: str, payload: Dict[str, Any], created_at: Optional[str] = None) -> None:
        if not str(user_id or "").strip() or not str(event_type or "").strip():
            return
        self.upsert_user(user_id)
        with transaction(self.db_url) as conn:
            conn.execute(
                """
                INSERT INTO user_events (user_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_id,
                    event_type,
                    json.dumps(payload or {}, ensure_ascii=False),
                    created_at or utc_now(),
                ),
            )

    def save_profile_snapshot(self, user_id: str, snapshot: Dict[str, Any]) -> None:
        if not str(user_id or "").strip():
            return
        self.upsert_user(user_id)
        profile_version = str(snapshot.get("profile_version") or "profile-v1")
        generated_at = str(snapshot.get("generated_at") or utc_now())
        source_event_window = snapshot.get("source_event_window") or {}
        with transaction(self.db_url) as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (
                    user_id,
                    profile_version,
                    generated_at,
                    source_event_window_json,
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    profile_version,
                    generated_at,
                    json.dumps(source_event_window, ensure_ascii=False),
                    json.dumps(snapshot, ensure_ascii=False),
                    utc_now(),
                ),
            )

    def get_latest_profile(self, user_id: str) -> Dict[str, Any]:
        if not str(user_id or "").strip():
            return {}
        with transaction(self.db_url) as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM user_profiles
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["payload_json"])
        except Exception:
            return {}

    def get_recent_events(self, user_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        if not str(user_id or "").strip():
            return []
        with transaction(self.db_url) as conn:
            rows = conn.execute(
                """
                SELECT event_type, payload_json, created_at
                FROM user_events
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, max(1, int(limit))),
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {}
            result.append(
                {
                    "event_type": row["event_type"],
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )
        return result
