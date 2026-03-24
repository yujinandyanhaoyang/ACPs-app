from __future__ import annotations

import argparse
import json
import sqlite3
from typing import Any, Dict

import requests

from services.db import get_sqlite_path, resolve_database_url


def build_demo_payload(debug: bool = False) -> Dict[str, Any]:
    base = {
        "user_id": "demo_user_001",
        "query": "Recommend personalized science fiction and history books with diversity.",
        "constraints": {
            "scenario": "warm",
            "top_k": 3,
        },
    }
    if not debug:
        return base

    base.update(
        {
            "user_profile": {"age": 25, "preferred_language": "en"},
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
                    "title": "Sapiens",
                    "genres": ["history", "nonfiction"],
                    "themes": ["culture", "society"],
                    "rating": 4,
                    "format": "print",
                    "language": "en",
                },
            ],
            "reviews": [
                {"rating": 5, "text": "Love books with deep worldbuilding and social themes."},
                {"rating": 4, "text": "Prefer insightful writing and broad perspectives."},
            ],
            "books": [
                {
                    "book_id": "demo-001",
                    "title": "Foundation",
                    "description": "Classic sci-fi with civilizational cycles and big ideas.",
                    "genres": ["science_fiction"],
                },
                {
                    "book_id": "demo-002",
                    "title": "Guns, Germs, and Steel",
                    "description": "Historical synthesis of human societies and development.",
                    "genres": ["history", "nonfiction"],
                },
                {
                    "book_id": "demo-003",
                    "title": "The Left Hand of Darkness",
                    "description": "Speculative fiction exploring culture and identity.",
                    "genres": ["science_fiction"],
                },
            ],
            "constraints": {
                "scenario": "explore",
                "top_k": 3,
                "novelty_threshold": 0.5,
                "min_new_items": 1,
                "debug_payload_override": True,
                "ablation": True,
                "ground_truth_ids": ["demo-001", "demo-003"],
            },
        }
    )
    return base


def _print_db_snapshot() -> None:
    db_url = resolve_database_url()
    sqlite_path = get_sqlite_path(db_url)
    print(f"runtime_db_url={db_url}")
    print(f"runtime_db_path={sqlite_path}")
    if not sqlite_path.exists():
        print("runtime_db_exists=false")
        return

    conn = sqlite3.connect(str(sqlite_path))
    try:
        runs = conn.execute("SELECT COUNT(*) FROM recommendation_runs").fetchone()[0]
        recs = conn.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
        logs = conn.execute("SELECT COUNT(*) FROM agent_task_logs").fetchone()[0]
    finally:
        conn.close()

    print("runtime_db_exists=true")
    print(f"recommendation_runs={runs}")
    print(f"recommendations={recs}")
    print(f"agent_task_logs={logs}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reading concierge workflow demo request")
    parser.add_argument("--base-url", default="http://127.0.0.1:8100", help="Reading concierge service base URL")
    parser.add_argument("--debug", action="store_true", help="Use debug payload and call /user_api_debug")
    parser.add_argument("--path", default=None, help="Override API path")
    parser.add_argument("--timeout", type=float, default=30.0, help="Request timeout in seconds")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON response")
    parser.add_argument("--check-db", action="store_true", help="Print runtime DB table counts after request")
    args = parser.parse_args()

    payload = build_demo_payload(debug=args.debug)
    path = args.path or ("/user_api_debug" if args.debug else "/user_api")

    response = requests.post(
        args.base_url.rstrip("/") + path,
        json=payload,
        timeout=args.timeout,
    )
    response.raise_for_status()

    body = response.json()
    summary = {
        "state": body.get("state"),
        "scenario": body.get("scenario"),
        "recommendation_count": len(body.get("recommendations") or []),
        "contract_validation": body.get("contract_validation"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None))

    if args.pretty:
        print(json.dumps(body, ensure_ascii=False, indent=2))

    if args.check_db:
        _print_db_snapshot()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
