import argparse
import json
from typing import Any, Dict

import requests


def build_demo_payload() -> Dict[str, Any]:
    return {
        "user_id": "demo_user_001",
        "query": "Recommend personalized science fiction and history books with diversity.",
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
                "kg_node_id": "kg:foundation",
            },
            {
                "book_id": "demo-002",
                "title": "Guns, Germs, and Steel",
                "description": "Historical synthesis of human societies and development.",
                "genres": ["history", "nonfiction"],
                "kg_node_id": "kg:ggs",
            },
            {
                "book_id": "demo-003",
                "title": "The Left Hand of Darkness",
                "description": "Speculative fiction exploring culture and identity.",
                "genres": ["science_fiction"],
                "kg_node_id": "kg:lhd",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the reading concierge end-to-end demo request")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Reading concierge service base URL")
    parser.add_argument("--path", default="/user_api", help="API path")
    parser.add_argument("--timeout", type=float, default=30.0, help="Request timeout in seconds")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON response")
    args = parser.parse_args()

    payload = build_demo_payload()
    response = requests.post(
        args.base_url.rstrip("/") + args.path,
        json=payload,
        timeout=args.timeout,
    )
    response.raise_for_status()

    body = response.json()
    if args.pretty:
        print(json.dumps(body, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(body, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
