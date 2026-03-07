from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOOK_INPUTS = [
    PROJECT_ROOT / "data" / "processed" / "goodreads" / "books_master.jsonl",
    PROJECT_ROOT / "data" / "processed" / "amazon_kindle" / "books_master.jsonl",
    PROJECT_ROOT / "data" / "processed" / "amazon_books" / "books_master.jsonl",
]
DEFAULT_INTERACTION_INPUTS = [
    PROJECT_ROOT / "data" / "processed" / "goodreads" / "interactions_train.jsonl",
    PROJECT_ROOT / "data" / "processed" / "goodreads" / "interactions_valid.jsonl",
    PROJECT_ROOT / "data" / "processed" / "goodreads" / "interactions_test.jsonl",
    PROJECT_ROOT / "data" / "processed" / "amazon_kindle" / "interactions_train.jsonl",
    PROJECT_ROOT / "data" / "processed" / "amazon_kindle" / "interactions_valid.jsonl",
    PROJECT_ROOT / "data" / "processed" / "amazon_kindle" / "interactions_test.jsonl",
    PROJECT_ROOT / "data" / "processed" / "amazon_books" / "interactions_train.jsonl",
    PROJECT_ROOT / "data" / "processed" / "amazon_books" / "interactions_valid.jsonl",
    PROJECT_ROOT / "data" / "processed" / "amazon_books" / "interactions_test.jsonl",
]
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "merged"


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_title(value: str) -> str:
    token = _clean_text(value).lower()
    token = re.sub(r"[^\w\s]", "", token, flags=re.UNICODE)
    return re.sub(r"\s+", " ", token).strip()


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                yield row


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _merge_list_values(left: Any, right: Any) -> List[str]:
    items: List[str] = []
    seen = set()
    for source in [left, right]:
        if not isinstance(source, list):
            continue
        for item in source:
            token = _clean_text(item)
            if token and token not in seen:
                items.append(token)
                seen.add(token)
    return items


def _book_merge_key(row: Dict[str, Any]) -> str:
    title = _normalize_title(str(row.get("title") or ""))
    author = _normalize_title(str(row.get("author") or ""))
    return f"{title}::{author}"


def merge_books(book_paths: List[Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    merged_by_key: Dict[str, Dict[str, Any]] = {}
    stats = {"inputs": [], "merged_books": 0, "deduped_books": 0}

    for path in book_paths:
        if not path.exists():
            continue
        stats["inputs"].append(str(path))
        for row in _iter_jsonl(path):
            title = _clean_text(row.get("title"))
            if not title:
                continue
            key = _book_merge_key(row)
            current = merged_by_key.get(key)
            if current is None:
                merged_by_key[key] = {
                    "book_id": _clean_text(row.get("book_id")) or key,
                    "title": title,
                    "author": _clean_text(row.get("author")) or "Unknown",
                    "description": _clean_text(row.get("description")),
                    "genres": _merge_list_values(row.get("genres"), []),
                    "publisher": _clean_text(row.get("publisher")),
                    "published_year": row.get("published_year"),
                    "source": _clean_text(row.get("source")) or "unknown",
                    "source_ids": [_clean_text(row.get("book_id"))] if _clean_text(row.get("book_id")) else [],
                }
                continue

            stats["deduped_books"] += 1
            current["genres"] = _merge_list_values(current.get("genres"), row.get("genres"))
            if len(_clean_text(row.get("description"))) > len(_clean_text(current.get("description"))):
                current["description"] = _clean_text(row.get("description"))
            if not _clean_text(current.get("publisher")):
                current["publisher"] = _clean_text(row.get("publisher"))
            if not current.get("published_year") and row.get("published_year"):
                current["published_year"] = row.get("published_year")
            source = _clean_text(row.get("source"))
            if source:
                merged_sources = _merge_list_values(str(current.get("source") or "").split("+"), [source])
                current["source"] = "+".join(merged_sources)
            source_book_id = _clean_text(row.get("book_id"))
            if source_book_id and source_book_id not in current["source_ids"]:
                current["source_ids"].append(source_book_id)

    merged_books = list(merged_by_key.values())
    stats["merged_books"] = len(merged_books)
    return merged_books, stats


def merge_interactions(interaction_paths: List[Path], valid_book_ids: set[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    stats = {"inputs": [], "kept": 0, "dropped_missing_book": 0, "deduped": 0}

    for path in interaction_paths:
        if not path.exists():
            continue
        stats["inputs"].append(str(path))
        for row in _iter_jsonl(path):
            user_id = _clean_text(row.get("user_id"))
            book_id = _clean_text(row.get("book_id"))
            rating = row.get("rating")
            if not user_id or not book_id:
                continue
            if book_id not in valid_book_ids:
                stats["dropped_missing_book"] += 1
                continue
            key = (user_id, book_id, rating, row.get("timestamp"))
            if key in seen:
                stats["deduped"] += 1
                continue
            seen.add(key)
            merged.append(row)
            stats["kept"] += 1
    return merged, stats


def write_merged_interactions(path: Path, interaction_paths: List[Path], valid_book_ids: set[str]) -> Tuple[int, Dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    stats = {"inputs": [], "kept": 0, "dropped_missing_book": 0, "deduped": 0, "mode": "streaming-no-global-dedupe"}

    with path.open("w", encoding="utf-8") as f:
        for input_path in interaction_paths:
            if not input_path.exists():
                continue
            stats["inputs"].append(str(input_path))
            for row in _iter_jsonl(input_path):
                user_id = _clean_text(row.get("user_id"))
                book_id = _clean_text(row.get("book_id"))
                if not user_id or not book_id:
                    continue
                if book_id not in valid_book_ids:
                    stats["dropped_missing_book"] += 1
                    continue
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                stats["kept"] += 1

    return stats["kept"], stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge normalized Goodreads and Amazon book corpora into a unified retrieval/training corpus.")
    parser.add_argument("--book-input", action="append", type=Path, dest="book_inputs")
    parser.add_argument("--interaction-input", action="append", type=Path, dest="interaction_inputs")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--merge-interactions", action="store_true")
    args = parser.parse_args()

    book_paths = args.book_inputs or DEFAULT_BOOK_INPUTS
    merged_books, book_stats = merge_books(book_paths)
    books_out = args.out_dir / "books_master_merged.jsonl"
    book_count = _write_jsonl(books_out, merged_books)

    print(f"merged_books: {book_count}")
    print(f"books_out: {books_out}")
    print(json.dumps(book_stats, ensure_ascii=False))

    if args.merge_interactions:
        interaction_paths = args.interaction_inputs or DEFAULT_INTERACTION_INPUTS
        interactions_out = args.out_dir / "interactions_merged.jsonl"
        interaction_count, interaction_stats = write_merged_interactions(
            interactions_out,
            interaction_paths,
            valid_book_ids={str(row["book_id"]) for row in merged_books},
        )
        print(f"merged_interactions: {interaction_count}")
        print(f"interactions_out: {interactions_out}")
        print(json.dumps(interaction_stats, ensure_ascii=False))


if __name__ == "__main__":
    main()