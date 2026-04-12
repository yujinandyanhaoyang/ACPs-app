from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.enrich_utils import (
    clean_text,
    iter_amazon_records,
    iter_goodreads_records,
    load_config,
    resolve_input_paths,
)


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def _normalize_genres(value: Any) -> List[str]:
    if isinstance(value, list):
        items = value
    elif value is None:
        items = []
    else:
        items = [value]
    genres: List[str] = []
    seen = set()
    for item in items:
        token = clean_text(item)
        if token and token not in seen:
            genres.append(token)
            seen.add(token)
    return genres


def _normalize_rating(value: Any) -> Optional[float]:
    text = clean_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _base_record(
    *,
    source: str,
    book_id: str,
    title: str,
    author: str,
    genres: List[str],
    description: str,
    rating: Optional[float],
    rating_source: Optional[str],
    description_source: str,
) -> Dict[str, Any]:
    return {
        "source": source,
        "book_id": book_id,
        "title": title,
        "author": author,
        "genres": genres,
        "description": description,
        "rating": rating,
        "rating_source": rating_source,
        "description_source": description_source,
    }


def _normalize_enriched_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return _base_record(
        source=clean_text(row.get("source")) or "",
        book_id=clean_text(row.get("book_id")),
        title=clean_text(row.get("title")),
        author=clean_text(row.get("author")),
        genres=_normalize_genres(row.get("genres")),
        description=clean_text(row.get("description")),
        rating=_normalize_rating(row.get("rating")),
        rating_source=clean_text(row.get("rating_source")) or None,
        description_source="llm_generated",
    )


def _normalize_amazon_record(record: Any) -> Dict[str, Any]:
    return _base_record(
        source="amazon",
        book_id=clean_text(record.book_id),
        title=clean_text(record.title),
        author=clean_text(record.author),
        genres=_normalize_genres(record.genres),
        description=clean_text(record.description),
        rating=None,
        rating_source=None,
        description_source="original",
    )


def _normalize_goodreads_record(record: Any) -> Dict[str, Any]:
    rating = _normalize_rating(record.rating)
    return _base_record(
        source="goodreads",
        book_id=clean_text(record.book_id),
        title=clean_text(record.title),
        author=clean_text(record.author),
        genres=[],
        description="",
        rating=rating,
        rating_source="goodreads" if rating is not None else None,
        description_source="original",
    )


def _keep_amazon(record: Dict[str, Any]) -> bool:
    description = clean_text(record.get("description"))
    return bool(clean_text(record.get("title"))) and bool(clean_text(record.get("author"))) and bool(_normalize_genres(record.get("genres"))) and len(description) >= 50


def _goodreads_rating_from_row(row: Any) -> Optional[float]:
    return _normalize_rating(row.rating)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the final merged master book dataset.")
    parser.add_argument("--limit", type=int, default=None, help="Limit raw records scanned from each source for validation.")
    args = parser.parse_args()

    config = load_config()
    goodreads_path, amazon_paths = resolve_input_paths(config.raw_root)
    enriched_path = config.output_path
    master_path = config.output_path.parent / "books_master_merged.jsonl"

    enriched_index: Dict[str, Dict[str, Any]] = {}
    for row in _iter_jsonl(enriched_path):
        normalized = _normalize_enriched_row(row)
        book_id = normalized["book_id"]
        if book_id and book_id not in enriched_index:
            enriched_index[book_id] = normalized

    output_index: Dict[str, Dict[str, Any]] = {book_id: dict(row) for book_id, row in enriched_index.items()}

    enriched_records_merged = len(enriched_index)
    amazon_raw_kept = 0
    goodreads_raw_kept = 0
    amazon_dropped = 0
    goodreads_dropped = 0
    goodreads_rating_patches = 0

    # Amazon raw: usable records can enter output if not already superseded by enriched records.
    amazon_seen = 0
    for path in amazon_paths:
        for record in iter_amazon_records(path):
            if args.limit is not None and amazon_seen >= args.limit:
                break
            amazon_seen += 1
            normalized = _normalize_amazon_record(record)
            book_id = normalized["book_id"]
            if not book_id:
                amazon_dropped += 1
                continue
            if not _keep_amazon(normalized):
                amazon_dropped += 1
                continue
            if book_id not in output_index:
                output_index[book_id] = normalized
            amazon_raw_kept += 1

    # Goodreads raw: used primarily to patch ratings on enriched records.
    goodreads_seen = 0
    for record in iter_goodreads_records(goodreads_path):
        if args.limit is not None and goodreads_seen >= args.limit:
            break
        goodreads_seen += 1
        normalized = _normalize_goodreads_record(record)
        book_id = normalized["book_id"]
        if not book_id:
            goodreads_dropped += 1
            continue

        if book_id in output_index:
            if normalized["rating"] is not None:
                current = output_index[book_id]
                current["rating"] = normalized["rating"]
                current["rating_source"] = "goodreads"
                goodreads_rating_patches += 1
            continue

        # Goodreads raw has no genres/description, so under the requested KEEP rules it is dropped.
        goodreads_dropped += 1

    final_rows = sorted(output_index.values(), key=lambda row: (row["book_id"], row["source"], row["title"]))
    master_path.parent.mkdir(parents=True, exist_ok=True)
    with master_path.open("w", encoding="utf-8") as f:
        for row in final_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("=== Master Dataset Build Complete ===")
    print(f"Enriched records merged       : {enriched_records_merged}")
    print(f"Amazon raw records kept       : {amazon_raw_kept}")
    print(f"Goodreads raw records kept    : {goodreads_raw_kept}")
    print(f"Goodreads rating patches      : {goodreads_rating_patches}")
    print(f"Amazon raw records dropped    : {amazon_dropped}")
    print(f"Goodreads raw records dropped : {goodreads_dropped}")
    print(f"Total records in output       : {len(final_rows)}")
    print(f"Output path                   : {master_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
