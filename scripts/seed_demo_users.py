from __future__ import annotations

import html
import json
import os
import random
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent

CORPUS_PATH = Path("/root/WORK/DATA/processed/books_master_merged_v2.jsonl")
CF_BOOK_INDEX_PATH = Path("/root/WORK/DATA/processed/cf_book_id_index_v2.json")
DB_FALLBACK_PATH = _PROJECT_ROOT / "data" / "recommendation_runtime.db"
SEED_TAG = "seed_demo_users_v1"
RESERVOIR_SIZE = 2500
RNG_SEED = 20260417


@dataclass(frozen=True)
class SeedPlan:
    user_id: str
    label: str
    buckets: Sequence[tuple[str, int]]
    rating_cycle: Sequence[int]


USER_PLANS: Sequence[SeedPlan] = (
    SeedPlan(
        user_id="demo_user_001",
        label="literary fiction enthusiast",
        buckets=(
            ("literary_fiction", 9),
            ("historical_fiction", 8),
            ("biography", 8),
        ),
        rating_cycle=(5, 4),
    ),
    SeedPlan(
        user_id="demo_user_002",
        label="sci-fi & fantasy reader",
        buckets=(
            ("science_fiction", 9),
            ("fantasy", 8),
            ("thriller", 8),
        ),
        rating_cycle=(5, 4),
    ),
    SeedPlan(
        user_id="demo_user_003",
        label="general reader",
        buckets=(
            ("mystery", 3),
            ("history", 3),
            ("biography", 3),
            ("science_fiction", 3),
        ),
        rating_cycle=(4,),
    ),
)


def _normalize_text(value: Any) -> str:
    return html.unescape(str(value or "")).strip().lower()


def _normalize_genres(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        token = _normalize_text(item)
        if token:
            out.append(token)
    return out


def _resolve_sqlite_path() -> Path:
    return DB_FALLBACK_PATH


def _iter_books_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                yield row


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS user_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_user_events_user_time
            ON user_events(user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            profile_version TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            source_event_window_json TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_user_profiles_user_time
            ON user_profiles(user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS user_behavior_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            book_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            weight REAL NOT NULL,
            rating SMALLINT,
            duration_sec INTEGER,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        CREATE INDEX IF NOT EXISTS idx_user_behavior_events_user_time
            ON user_behavior_events(user_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_user_behavior_events_book
            ON user_behavior_events(book_id);
        """
    )


def _book_matches_bucket(book: Dict[str, Any], bucket: str) -> bool:
    genres = _normalize_genres(book.get("genres"))
    title = _normalize_text(book.get("title"))
    description = _normalize_text(book.get("description"))
    blob = " ".join([title, description, " ".join(genres)])

    if bucket == "literary_fiction":
        return any(
            phrase in blob
            for phrase in (
                "literary fiction",
                "literature & fiction",
                "literature &amp; fiction",
                "literary",
            )
        )
    if bucket == "historical_fiction":
        return "historical fiction" in blob or ("historical" in blob and "fiction" in blob)
    if bucket == "biography":
        return any(phrase in blob for phrase in ("biography", "biographies & memoirs", "memoir"))
    if bucket == "science_fiction":
        return any(phrase in blob for phrase in ("science fiction", "science fiction & fantasy", "sci-fi"))
    if bucket == "fantasy":
        return "fantasy" in blob
    if bucket == "thriller":
        return any(phrase in blob for phrase in ("thriller", "suspense"))
    if bucket == "mystery":
        return any(phrase in blob for phrase in ("mystery", "crime", "detective"))
    if bucket == "history":
        return "history" in blob or "historical" in blob
    return False


def _load_indexed_book_ids(index_path: Path) -> set[str]:
    with index_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid CF index format: expected object at {index_path}")
    return {str(book_id).strip() for book_id in data.keys() if str(book_id).strip()}


def _stream_candidate_pools(indexed_ids: set[str]) -> tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    reservoir: List[Dict[str, Any]] = []
    seen = 0
    rng = random.Random(RNG_SEED)

    for book in _iter_books_jsonl(CORPUS_PATH):
        if not isinstance(book, dict):
            continue
        book_id = str(book.get("book_id") or "").strip()
        if not book_id or book_id not in indexed_ids:
            continue

        record = {
            "book_id": book_id,
            "title": str(book.get("title") or book_id),
            "genres": _normalize_genres(book.get("genres")),
            "description": str(book.get("description") or book.get("blurb") or ""),
        }

        for bucket_name in ("literary_fiction", "historical_fiction", "biography", "science_fiction", "fantasy", "thriller", "mystery", "history"):
            if _book_matches_bucket(record, bucket_name):
                buckets[bucket_name].append(record)

        seen += 1
        if len(reservoir) < RESERVOIR_SIZE:
            reservoir.append(record)
        else:
            j = rng.randrange(seen)
            if j < RESERVOIR_SIZE:
                reservoir[j] = record

    return buckets, reservoir


def _unique_ordered(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in records:
        book_id = str(row.get("book_id") or "").strip()
        if not book_id or book_id in seen:
            continue
        seen.add(book_id)
        out.append(row)
    return out


def _pick_books_for_plan(
    plan: SeedPlan,
    buckets: Dict[str, List[Dict[str, Any]]],
    fallback_pool: List[Dict[str, Any]],
    rng: random.Random,
) -> List[Dict[str, Any]]:
    used_ids: set[str] = set()
    picked: List[Dict[str, Any]] = []

    for bucket_name, needed in plan.buckets:
        pool = list(buckets.get(bucket_name) or [])
        rng.shuffle(pool)
        chosen = 0
        for row in pool:
            book_id = str(row.get("book_id") or "").strip()
            if not book_id or book_id in used_ids:
                continue
            picked.append({**row, "_bucket": bucket_name})
            used_ids.add(book_id)
            chosen += 1
            if chosen >= needed:
                break

        if chosen >= needed:
            continue

        shortfall = needed - chosen
        fallback = list(fallback_pool)
        rng.shuffle(fallback)
        for row in fallback:
            book_id = str(row.get("book_id") or "").strip()
            if not book_id or book_id in used_ids:
                continue
            picked.append({**row, "_bucket": bucket_name})
            used_ids.add(book_id)
            shortfall -= 1
            if shortfall <= 0:
                break

        if shortfall > 0:
            raise RuntimeError(
                f"Insufficient indexed books for {plan.user_id} bucket={bucket_name}; "
                f"missing {shortfall} items."
            )

    return _unique_ordered(picked)


def _timestamps(count: int, rng: random.Random) -> List[str]:
    now = datetime.now(timezone.utc)
    offsets = sorted((rng.uniform(0, 90 * 24 * 3600) for _ in range(count)), reverse=True)
    return [
        (now - timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")
        for offset in offsets
    ]


def _rating_for_index(plan: SeedPlan, idx: int) -> int:
    cycle = list(plan.rating_cycle) or [4]
    return int(cycle[idx % len(cycle)])


def _build_behavior_row(plan: SeedPlan, book: Dict[str, Any], rating: int, created_at: str) -> Dict[str, Any]:
    weight = 1.0 if rating >= 5 else 0.85
    duration_base = 1800 if rating >= 5 else 1200
    duration_sec = duration_base + (rating * 137)
    event_type = str(book.get("_bucket") or "rating").strip().lower()
    return {
        "user_id": plan.user_id,
        "book_id": str(book.get("book_id") or "").strip(),
        "event_type": event_type,
        "weight": float(weight),
        "rating": int(rating),
        "duration_sec": int(duration_sec),
        "created_at": created_at,
    }


def _build_legacy_event_row(plan: SeedPlan, book: Dict[str, Any], rating: int, created_at: str) -> Dict[str, Any]:
    event_type = str(book.get("_bucket") or "rating").strip().lower()
    return {
        "user_id": plan.user_id,
        "event_type": event_type,
        "payload_json": json.dumps(
            {
                "book_id": str(book.get("book_id") or "").strip(),
                "title": str(book.get("title") or ""),
                "genres": book.get("genres") if isinstance(book.get("genres"), list) else [],
                "rating": int(rating),
                "weight": 1.0 if rating >= 5 else 0.85,
                "duration_sec": 1800 + (rating * 137),
                "verified": True,
                "seed_tag": SEED_TAG,
                "source": "seed_demo_users.py",
                "bucket": book.get("_bucket"),
            },
            ensure_ascii=False,
        ),
        "created_at": created_at,
    }


def _ensure_users(conn: sqlite3.Connection, user_ids: Sequence[str]) -> None:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for user_id in user_ids:
        conn.execute(
            """
            INSERT INTO users (user_id, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                updated_at = excluded.updated_at,
                metadata_json = excluded.metadata_json
            """,
            (
                user_id,
                now,
                now,
                json.dumps({"seeded_demo_user": True, "seed_tag": SEED_TAG}, ensure_ascii=False),
            ),
        )


def _delete_existing_demo_rows(conn: sqlite3.Connection, user_ids: Sequence[str]) -> None:
    if not user_ids:
        return
    placeholders = ",".join("?" for _ in user_ids)
    conn.execute(f"DELETE FROM user_behavior_events WHERE user_id IN ({placeholders})", tuple(user_ids))
    conn.execute(f"DELETE FROM user_events WHERE user_id IN ({placeholders})", tuple(user_ids))
    conn.execute(f"DELETE FROM user_profiles WHERE user_id IN ({placeholders})", tuple(user_ids))


def main() -> int:
    sqlite_path = _resolve_sqlite_path()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    if not CF_BOOK_INDEX_PATH.exists():
        print(f"Missing CF index: {CF_BOOK_INDEX_PATH}")
        return 1
    if not CORPUS_PATH.exists():
        print(f"Missing corpus: {CORPUS_PATH}")
        return 1

    indexed_ids = _load_indexed_book_ids(CF_BOOK_INDEX_PATH)
    buckets, fallback_pool = _stream_candidate_pools(indexed_ids)

    rng = random.Random(RNG_SEED)
    behavior_rows_by_user: Dict[str, List[Dict[str, Any]]] = {}
    legacy_rows_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for plan in USER_PLANS:
        selected_books = _pick_books_for_plan(plan, buckets, fallback_pool, rng)
        timestamps = _timestamps(len(selected_books), rng)
        behavior_rows: List[Dict[str, Any]] = []
        legacy_rows: List[Dict[str, Any]] = []

        for idx, (book, created_at) in enumerate(zip(selected_books, timestamps)):
            rating = _rating_for_index(plan, idx)
            behavior_rows.append(_build_behavior_row(plan, book, rating, created_at))
            legacy_rows.append(_build_legacy_event_row(plan, book, rating, created_at))

        behavior_rows_by_user[plan.user_id] = behavior_rows
        legacy_rows_by_user[plan.user_id] = legacy_rows

    with sqlite3.connect(str(sqlite_path)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_schema(conn)
        _delete_existing_demo_rows(conn, [plan.user_id for plan in USER_PLANS])
        _ensure_users(conn, [plan.user_id for plan in USER_PLANS])

        for plan in USER_PLANS:
            selected_behavior_rows = behavior_rows_by_user.get(plan.user_id) or []
            selected_legacy_rows = legacy_rows_by_user.get(plan.user_id) or []
            if not selected_behavior_rows:
                continue

            conn.executemany(
                """
                INSERT INTO user_behavior_events (
                    user_id, book_id, event_type, weight, rating, duration_sec, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["user_id"],
                        row["book_id"],
                        row["event_type"],
                        row["weight"],
                        row["rating"],
                        row["duration_sec"],
                        row["created_at"],
                    )
                    for row in selected_behavior_rows
                ],
            )
            conn.executemany(
                """
                INSERT INTO user_events (
                    user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        row["user_id"],
                        row["event_type"],
                        row["payload_json"],
                        row["created_at"],
                    )
                    for row in selected_legacy_rows
                ],
            )

    for plan in USER_PLANS:
        print(f"Seeded {plan.user_id}: {len(behavior_rows_by_user.get(plan.user_id) or [])} events")

    print("demo_user_004: skipped (cold start left unchanged)")
    print(f"Runtime DB: {sqlite_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
