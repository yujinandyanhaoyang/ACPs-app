from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from services.data_paths import get_processed_data_path, get_raw_data_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = get_raw_data_path("goodreads")
OUT_DIR = get_processed_data_path("goodreads")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _normalize_genre(value: str) -> str:
    token = _clean_text(value).lower().replace("-", " ").replace("/", " ")
    token = re.sub(r"\s+", "_", token)
    token = re.sub(r"[^a-z0-9_]+", "", token)
    return token.strip("_")


def _stable_bucket(user_id: str, book_id: str) -> int:
    digest = hashlib.md5(f"{user_id}:{book_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _load_tag_map(tags_path: Path) -> Dict[str, str]:
    tag_map: Dict[str, str] = {}
    with tags_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tag_id = str(row.get("tag_id") or "").strip()
            tag_name = _normalize_genre(str(row.get("tag_name") or ""))
            if tag_id and tag_name:
                tag_map[tag_id] = tag_name
    return tag_map


def _load_book_genres(book_tags_path: Path, tag_map: Dict[str, str], top_n: int = 5) -> Dict[str, List[str]]:
    weighted_tags: Dict[str, Dict[str, int]] = defaultdict(dict)

    with book_tags_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            goodreads_book_id = str(row.get("goodreads_book_id") or "").strip()
            tag_id = str(row.get("tag_id") or "").strip()
            count_value = str(row.get("count") or "0").strip()
            if not goodreads_book_id or not tag_id:
                continue
            tag_name = tag_map.get(tag_id)
            if not tag_name:
                continue
            try:
                count = int(count_value)
            except ValueError:
                count = 0
            current = weighted_tags[goodreads_book_id].get(tag_name, 0)
            if count > current:
                weighted_tags[goodreads_book_id][tag_name] = count

    book_genres: Dict[str, List[str]] = {}
    for gid, tag_counts in weighted_tags.items():
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        genres = [name for name, _ in sorted_tags[:top_n]]
        book_genres[gid] = genres
    return book_genres


def _iter_books(books_path: Path, book_genres: Dict[str, List[str]]) -> Iterable[Dict[str, object]]:
    with books_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gid = str(row.get("goodreads_book_id") or "").strip()
            if not gid:
                continue

            title = _clean_text(str(row.get("title") or row.get("original_title") or ""))
            if not title:
                continue

            author = _clean_text(str(row.get("authors") or "")) or "Unknown"
            published_year = str(row.get("original_publication_year") or "").strip()
            language_code = _clean_text(str(row.get("language_code") or ""))

            record = {
                "book_id": gid,
                "title": title,
                "author": author,
                "description": "",
                "genres": book_genres.get(gid, []),
                "publisher": "",
                "published_year": int(float(published_year)) if published_year not in {"", "nan", "None"} else None,
                "language": language_code,
                "source": "goodbooks-10k",
                "source_book_id": gid,
            }
            yield record


def _write_jsonl(path: Path, rows: Iterable[Dict[str, object]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _split_interactions(
    ratings_path: Path,
    max_interactions: int,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], List[Dict[str, object]]]:
    train: List[Dict[str, object]] = []
    valid: List[Dict[str, object]] = []
    test: List[Dict[str, object]] = []

    with ratings_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            if max_interactions > 0 and idx > max_interactions:
                break

            user_id = str(row.get("user_id") or "").strip()
            book_id = str(row.get("book_id") or "").strip()
            rating_raw = str(row.get("rating") or "").strip()
            if not user_id or not book_id or not rating_raw:
                continue

            try:
                rating = float(rating_raw)
            except ValueError:
                continue

            item = {
                "user_id": f"gr_u_{user_id}",
            "book_id": book_id,
                "rating": rating,
                "timestamp": None,
                "review_text": "",
                "source": "goodbooks-10k",
            }

            bucket = _stable_bucket(user_id, book_id)
            if bucket < 80:
                train.append(item)
            elif bucket < 90:
                valid.append(item)
            else:
                test.append(item)

    return train, valid, test


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess Goodreads goodbooks-10k into normalized JSONL files.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--max-interactions", type=int, default=300000)
    parser.add_argument("--top-tags", type=int, default=5)
    args = parser.parse_args()

    books_path = args.raw_dir / "books.csv"
    ratings_path = args.raw_dir / "ratings.csv"
    book_tags_path = args.raw_dir / "book_tags.csv"
    tags_path = args.raw_dir / "tags.csv"

    missing = [p for p in (books_path, ratings_path, book_tags_path, tags_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required raw files: {missing}")

    tag_map = _load_tag_map(tags_path)
    book_genres = _load_book_genres(book_tags_path, tag_map, top_n=args.top_tags)

    books_count = _write_jsonl(args.out_dir / "books_master.jsonl", _iter_books(books_path, book_genres))

    train, valid, test = _split_interactions(ratings_path, max_interactions=args.max_interactions)
    train_count = _write_jsonl(args.out_dir / "interactions_train.jsonl", train)
    valid_count = _write_jsonl(args.out_dir / "interactions_valid.jsonl", valid)
    test_count = _write_jsonl(args.out_dir / "interactions_test.jsonl", test)

    print("Preprocess complete")
    print(f"books_master.jsonl: {books_count}")
    print(f"interactions_train.jsonl: {train_count}")
    print(f"interactions_valid.jsonl: {valid_count}")
    print(f"interactions_test.jsonl: {test_count}")
    print(f"output_dir: {args.out_dir}")


if __name__ == "__main__":
    main()
