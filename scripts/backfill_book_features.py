from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Any

from services.db import transaction, utc_now


def _upsert_book(book_id: str, title: str, author: str, metadata: Dict[str, Any]) -> None:
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO books (book_id, title, author, metadata_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                title = excluded.title,
                author = excluded.author,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (book_id, title, author, json.dumps(metadata, ensure_ascii=False), utc_now()),
        )


def _insert_book_feature(book_id: str, feature_version: str, feature_payload: Dict[str, Any], source_label: str) -> None:
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO book_features (
                book_id,
                feature_version,
                feature_payload_json,
                source_label,
                generated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                book_id,
                feature_version,
                json.dumps(feature_payload, ensure_ascii=False),
                source_label,
                utc_now(),
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill books/book_features from merged corpus JSONL")
    parser.add_argument("--books-jsonl", default="data/processed/merged/books_master_merged.jsonl")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--feature-version", default="book_content_v1")
    args = parser.parse_args()

    src = Path(args.books_jsonl)
    if not src.exists():
        print(f"Source file not found: {src}")
        return 1

    count = 0
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            if args.limit > 0 and count >= args.limit:
                break
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue

            book_id = str(row.get("book_id") or row.get("id") or "").strip()
            if not book_id:
                continue
            title = str(row.get("title") or "")
            author = str(row.get("author") or "")
            genres = row.get("genres") if isinstance(row.get("genres"), list) else []
            description = str(row.get("description") or "")

            metadata = {
                "genres": genres,
                "source": row.get("source"),
                "dataset_version": row.get("dataset_version"),
            }
            _upsert_book(book_id, title, author, metadata)

            feature_payload = {
                "book_id": book_id,
                "title": title,
                "genres": genres,
                "description": description,
                "topics": row.get("topics") if isinstance(row.get("topics"), list) else [],
                "tags": row.get("tags") if isinstance(row.get("tags"), list) else [],
            }
            _insert_book_feature(book_id, args.feature_version, feature_payload, source_label="dataset_backfill")
            count += 1

    print(f"Backfilled books/book_features rows: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
