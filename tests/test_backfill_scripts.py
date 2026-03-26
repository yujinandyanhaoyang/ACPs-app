from __future__ import annotations

import sqlite3
from pathlib import Path

from services.db import run_migrations


def _runtime_db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'runtime_backfill.db'}"


def _create_legacy_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE user_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                event_type TEXT,
                payload_json TEXT,
                created_at TEXT
            );
            CREATE TABLE user_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                profile_version TEXT,
                generated_at TEXT,
                source_event_window_json TEXT,
                payload_json TEXT,
                created_at TEXT
            );
            CREATE TABLE recommendation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                query TEXT,
                profile_version TEXT,
                candidate_set_version_or_hash TEXT,
                candidate_provenance_json TEXT,
                book_feature_version_or_hash TEXT,
                ranking_policy_version TEXT,
                weights_or_policy_snapshot_json TEXT,
                created_at TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO user_events (user_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            ("u-backfill", "review", '{"text":"nice"}', "2026-03-25T00:00:00+00:00"),
        )
        conn.execute(
            """
            INSERT INTO user_profiles (
                user_id, profile_version, generated_at, source_event_window_json, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "u-backfill",
                "u-backfill-v1",
                "2026-03-25T00:00:00+00:00",
                '{"review_count":1}',
                '{"profile_version":"u-backfill-v1","generated_at":"2026-03-25T00:00:00+00:00"}',
                "2026-03-25T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO recommendation_runs (
                user_id, query, profile_version, candidate_set_version_or_hash,
                candidate_provenance_json, book_feature_version_or_hash,
                ranking_policy_version, weights_or_policy_snapshot_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "u-backfill",
                "query",
                "u-backfill-v1",
                "cand-v1",
                '{"retrieval_rule":"legacy"}',
                "bf-v1",
                "rank-v1",
                '{"semantic":0.4}',
                "2026-03-25T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_backfill_user_events_script(monkeypatch, tmp_path):
    from scripts import backfill_user_events

    db_url = _runtime_db_url(tmp_path)
    run_migrations(db_url=db_url)

    legacy_db = tmp_path / "legacy.db"
    _create_legacy_db(legacy_db)

    monkeypatch.setenv("RECSYS_DB_URL", db_url)
    monkeypatch.setattr(
        "sys.argv",
        ["backfill_user_events.py", "--legacy-db", str(legacy_db)],
    )

    rc = backfill_user_events.main()
    assert rc == 0

    conn = sqlite3.connect(str(tmp_path / "runtime_backfill.db"))
    try:
        events = conn.execute("SELECT COUNT(*) FROM user_events").fetchone()[0]
        profiles = conn.execute("SELECT COUNT(*) FROM user_profiles").fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM recommendation_runs").fetchone()[0]
    finally:
        conn.close()

    assert events >= 1
    assert profiles >= 1
    assert runs >= 1


def test_backfill_book_features_script(monkeypatch, tmp_path):
    from scripts import backfill_book_features

    db_url = _runtime_db_url(tmp_path)
    run_migrations(db_url=db_url)

    books_jsonl = tmp_path / "books.jsonl"
    books_jsonl.write_text(
        '{"book_id":"bk-1","title":"Book One","author":"A","genres":["fiction"],"description":"desc","source":"test","dataset_version":"v1"}\n',
        encoding="utf-8",
    )

    monkeypatch.setenv("RECSYS_DB_URL", db_url)
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_book_features.py",
            "--books-jsonl",
            str(books_jsonl),
            "--limit",
            "1",
            "--feature-version",
            "book_content_v1",
        ],
    )

    rc = backfill_book_features.main()
    assert rc == 0

    conn = sqlite3.connect(str(tmp_path / "runtime_backfill.db"))
    try:
        books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        features = conn.execute("SELECT COUNT(*) FROM book_features").fetchone()[0]
    finally:
        conn.close()

    assert books == 1
    assert features == 1
