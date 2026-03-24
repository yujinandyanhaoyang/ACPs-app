import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "user_profile_store.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_payload(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class UserProfileStore:
    """Persist user events and profile snapshots for lifecycle-based recommendations."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        configured_path = db_path or os.getenv("USER_PROFILE_STORE_DB_PATH") or str(_DEFAULT_DB_PATH)
        self.db_path = Path(configured_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS user_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_user_events_user_id_created
                        ON user_events(user_id, created_at DESC);

                    CREATE TABLE IF NOT EXISTS user_profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        profile_version TEXT NOT NULL,
                        generated_at TEXT NOT NULL,
                        source_event_window_json TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id_created
                        ON user_profiles(user_id, created_at DESC);

                    CREATE TABLE IF NOT EXISTS recommendation_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        query TEXT NOT NULL,
                        profile_version TEXT,
                        candidate_set_version_or_hash TEXT,
                        candidate_provenance_json TEXT,
                        candidate_ids_hash TEXT,
                        book_feature_version_or_hash TEXT,
                        ranking_policy_version TEXT,
                        weights_or_policy_snapshot_json TEXT,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                self._ensure_columns(
                    conn,
                    "recommendation_runs",
                    {
                        "candidate_provenance_json": "TEXT",
                        "candidate_ids_hash": "TEXT",
                    },
                )
                conn.commit()
            finally:
                conn.close()

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
        existing = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, col_type in columns.items():
            if name in existing:
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")

    def append_event(self, user_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        if not user_id:
            return
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO user_events (user_id, event_type, payload_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, event_type, json.dumps(payload, ensure_ascii=False), _utc_now()),
                )
                conn.commit()
            finally:
                conn.close()

    def _append_event_dedup(self, user_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        if not user_id or not isinstance(payload, dict) or not payload:
            return
        candidate = _canonical_payload(payload)
        recent = self.get_recent_events(user_id, limit=200, event_type=event_type)
        for row in recent:
            prior_payload = row.get("payload") if isinstance(row, dict) else None
            if not isinstance(prior_payload, dict):
                continue
            if _canonical_payload(prior_payload) == candidate:
                return
        self.append_event(user_id, event_type, payload)

    def _normalize_history_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        title = str(entry.get("title") or "").strip()
        if title:
            normalized["title"] = title
        genres = entry.get("genres") if isinstance(entry.get("genres"), list) else []
        clean_genres = []
        for genre in genres:
            label = str(genre or "").strip().lower()
            if label:
                clean_genres.append(label)
        if clean_genres:
            normalized["genres"] = clean_genres
        try:
            rating = float(entry.get("rating")) if entry.get("rating") is not None else None
        except (TypeError, ValueError):
            rating = None
        if rating is not None:
            normalized["rating"] = round(max(0.0, min(5.0, rating)), 2)
        language = str(entry.get("language") or "").strip().lower()
        if language:
            normalized["language"] = language
        for key in (
            "themes",
            "format",
            "tone",
            "mood",
            "pacing",
            "difficulty",
            "complexity",
            "page_count",
            "pages",
            "timestamp",
            "created_at",
            "book_id",
        ):
            if key in entry and entry[key] not in (None, ""):
                normalized[key] = entry[key]
        return normalized

    def _normalize_review_entry(self, review: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        text = str(review.get("text") or "").strip()
        if text:
            normalized["text"] = text
        try:
            rating = float(review.get("rating")) if review.get("rating") is not None else None
        except (TypeError, ValueError):
            rating = None
        if rating is not None:
            normalized["rating"] = round(max(0.0, min(5.0, rating)), 2)
        for key in ("book_id", "title", "timestamp", "created_at"):
            if key in review and review[key] not in (None, ""):
                normalized[key] = review[key]
        return normalized

    def ingest_user_basic_info(self, user_id: str, user_profile: Dict[str, Any]) -> None:
        if not user_id or not isinstance(user_profile, dict) or not user_profile:
            return
        payload = {k: v for k, v in user_profile.items() if k not in {"history", "reviews", "books"}}
        if not payload:
            return
        payload.setdefault("user_id", user_id)
        self._append_event_dedup(user_id, "user_basic_info", payload)

    def ingest_history_events(self, user_id: str, history: List[Dict[str, Any]]) -> None:
        if not user_id or not isinstance(history, list):
            return
        for entry in history:
            if not isinstance(entry, dict) or not entry:
                continue
            normalized = self._normalize_history_entry(entry)
            if not normalized:
                continue
            has_rating = isinstance(entry.get("rating"), (int, float))
            if has_rating:
                event_type = "rating"
            elif entry.get("event_type") == "browse" or entry.get("source") == "browse":
                event_type = "browse"
            else:
                event_type = "history_entry"
            self._append_event_dedup(user_id, event_type, normalized)

    def ingest_review_events(self, user_id: str, reviews: List[Dict[str, Any]]) -> None:
        if not user_id or not isinstance(reviews, list):
            return
        for review in reviews:
            if not isinstance(review, dict) or not review:
                continue
            normalized = self._normalize_review_entry(review)
            if not normalized:
                continue
            self._append_event_dedup(user_id, "review", normalized)

    def get_recent_events(
        self,
        user_id: str,
        *,
        limit: int = 200,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not user_id:
            return []
        conn = self._connect()
        try:
            if event_type:
                rows = conn.execute(
                    """
                    SELECT event_type, payload_json, created_at
                    FROM user_events
                    WHERE user_id = ? AND event_type = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (user_id, event_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT event_type, payload_json, created_at
                    FROM user_events
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
        finally:
            conn.close()

        events: List[Dict[str, Any]] = []
        for row in rows:
            payload_raw = row["payload_json"]
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                payload = {"raw": payload_raw}
            events.append(
                {
                    "event_type": row["event_type"],
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )
        return events

    def save_profile_snapshot(self, user_id: str, snapshot: Dict[str, Any]) -> None:
        if not user_id:
            return
        profile_version = str(snapshot.get("profile_version") or f"profile-{int(datetime.now().timestamp())}")
        generated_at = str(snapshot.get("generated_at") or _utc_now())
        source_event_window = snapshot.get("source_event_window") or {}

        with self._lock:
            conn = self._connect()
            try:
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
                        _utc_now(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_latest_profile(self, user_id: str) -> Dict[str, Any]:
        if not user_id:
            return {}
        conn = self._connect()
        try:
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
        finally:
            conn.close()

        if not row:
            return {}
        try:
            return json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return {}

    def get_user_context(self, user_id: str) -> Dict[str, Any]:
        """Build a profile/history/reviews context from persisted snapshots and events."""
        profile_snapshot = self.get_latest_profile(user_id)
        history: List[Dict[str, Any]] = []
        reviews: List[Dict[str, Any]] = []
        user_profile = profile_snapshot.get("user_profile") or {}

        for event in self.get_recent_events(user_id, limit=300):
            event_type = event.get("event_type")
            payload = event.get("payload") or {}
            if event_type in {"history_entry", "rating", "browse"}:
                if isinstance(payload, dict):
                    history.append(payload)
            elif event_type == "review":
                if isinstance(payload, dict):
                    reviews.append(payload)
            elif event_type == "user_basic_info":
                if isinstance(payload, dict):
                    for key, value in payload.items():
                        # Keep the most recent values while iterating DESC event order.
                        user_profile.setdefault(key, value)

        history.reverse()
        reviews.reverse()

        if user_id:
            user_profile.setdefault("user_id", user_id)

        return {
            "user_profile": user_profile,
            "history": history,
            "reviews": reviews,
            "profile_snapshot": profile_snapshot,
        }

    def record_recommendation_run(
        self,
        *,
        user_id: str,
        query: str,
        profile_version: Optional[str],
        candidate_set_version_or_hash: Optional[str],
        book_feature_version_or_hash: Optional[str],
        ranking_policy_version: Optional[str],
        weights_or_policy_snapshot: Optional[Dict[str, Any]],
        candidate_provenance: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not user_id or not query:
            return
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO recommendation_runs (
                        user_id,
                        query,
                        profile_version,
                        candidate_set_version_or_hash,
                        candidate_provenance_json,
                        candidate_ids_hash,
                        book_feature_version_or_hash,
                        ranking_policy_version,
                        weights_or_policy_snapshot_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        query,
                        profile_version,
                        candidate_set_version_or_hash,
                        json.dumps(candidate_provenance or {}, ensure_ascii=False),
                        str((candidate_provenance or {}).get("candidate_ids_hash") or ""),
                        book_feature_version_or_hash,
                        ranking_policy_version,
                        json.dumps(weights_or_policy_snapshot or {}, ensure_ascii=False),
                        _utc_now(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()


profile_store = UserProfileStore()
