from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Tuple

from services.data_paths import get_processed_data_path, get_raw_data_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = get_raw_data_path("amazon_books")
OUT_DIR = get_processed_data_path("amazon_kindle")


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_token(value: str) -> str:
    token = _clean_text(value).lower().replace("-", " ").replace("/", " ")
    token = re.sub(r"\s+", "_", token)
    token = re.sub(r"[^a-z0-9_]+", "", token)
    return token.strip("_")


def _stable_bucket(user_id: str, book_id: str) -> int:
    digest = hashlib.md5(f"{user_id}:{book_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _iter_json_records(path: Path) -> Iterator[Dict[str, Any]]:
    with _open_text(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def _extract_author(row: Dict[str, Any]) -> str:
    author = row.get("author")
    if isinstance(author, str) and _clean_text(author):
        return _clean_text(author)

    brand = row.get("brand")
    if isinstance(brand, str) and _clean_text(brand):
        return _clean_text(brand)

    by_line = row.get("by")
    if isinstance(by_line, str) and _clean_text(by_line):
        return _clean_text(by_line)

    details = row.get("details")
    if isinstance(details, dict):
        for key in ["Author", "Authors", "Publisher"]:
            value = details.get(key)
            if isinstance(value, str) and _clean_text(value):
                return _clean_text(value)

    return "Unknown"


def _extract_description(row: Dict[str, Any]) -> str:
    description = row.get("description")
    if isinstance(description, list):
        joined = " ".join(_clean_text(item) for item in description if _clean_text(item))
        if joined:
            return joined
    if isinstance(description, str) and _clean_text(description):
        return _clean_text(description)

    feature = row.get("feature")
    if isinstance(feature, list):
        joined = " ".join(_clean_text(item) for item in feature if _clean_text(item))
        if joined:
            return joined

    return ""


def _extract_genres(row: Dict[str, Any], max_genres: int = 8) -> List[str]:
    categories = row.get("categories") or []
    genre_candidates: List[str] = []
    if isinstance(categories, list):
        for group in categories:
            if isinstance(group, list):
                genre_candidates.extend(str(item) for item in group)
            elif isinstance(group, str):
                genre_candidates.append(group)

    deduped: List[str] = []
    seen = set()
    for raw in genre_candidates:
        token = _normalize_token(raw)
        if not token:
            continue
        if token in {"books", "kindle_store", "kindle_books", "subjects"}:
            continue
        if token not in seen:
            deduped.append(token)
            seen.add(token)
        if len(deduped) >= max_genres:
            break
    return deduped


def _iter_books(metadata_path: Path, source_name: str, max_books: int) -> Iterable[Dict[str, Any]]:
    count = 0
    for row in _iter_json_records(metadata_path):
        asin = _clean_text(row.get("asin"))
        title = _clean_text(row.get("title"))
        if not asin or not title:
            continue

        year = None
        year_raw = _clean_text(row.get("date") or row.get("publishedDate") or "")
        if year_raw:
            match = re.search(r"(19|20)\d{2}", year_raw)
            if match:
                year = int(match.group(0))

        yield {
            "book_id": f"amz_{asin}",
            "title": title,
            "author": _extract_author(row),
            "description": _extract_description(row),
            "genres": _extract_genres(row),
            "publisher": _clean_text(row.get("publisher")),
            "published_year": year,
            "source": source_name,
            "source_book_id": asin,
        }

        count += 1
        if max_books > 0 and count >= max_books:
            break


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _split_interactions(
    reviews_path: Path,
    valid_book_ids: set[str],
    source_name: str,
    max_reviews: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    train: List[Dict[str, Any]] = []
    valid: List[Dict[str, Any]] = []
    test: List[Dict[str, Any]] = []
    count = 0

    for row in _iter_json_records(reviews_path):
        user_id = _clean_text(row.get("reviewerID") or row.get("user_id"))
        asin = _clean_text(row.get("asin") or row.get("parent_asin"))
        if not user_id or not asin:
            continue

        book_id = f"amz_{asin}"
        if book_id not in valid_book_ids:
            continue

        try:
            rating = float(row.get("overall") if row.get("overall") is not None else row.get("rating"))
        except (TypeError, ValueError):
            continue

        summary = _clean_text(row.get("summary"))
        review_text = _clean_text(row.get("reviewText") or row.get("text"))
        merged_review = ". ".join(part for part in [summary, review_text] if part)

        item = {
            "user_id": f"amz_u_{user_id}",
            "book_id": book_id,
            "rating": rating,
            "timestamp": row.get("unixReviewTime") or row.get("sort_timestamp"),
            "review_text": merged_review,
            "source": source_name,
        }

        bucket = _stable_bucket(user_id, asin)
        if bucket < 80:
            train.append(item)
        elif bucket < 90:
            valid.append(item)
        else:
            test.append(item)

        count += 1
        if max_reviews > 0 and count >= max_reviews:
            break

    return train, valid, test


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess Amazon Books/Kindle Store review dumps into normalized JSONL files. Kindle Store is the default starting point for initial testing.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--metadata-file", default="meta_Kindle_Store.json.gz")
    parser.add_argument("--reviews-file", default="Kindle_Store_5.json.gz")
    parser.add_argument("--source", default="amazon-kindle-2018")
    parser.add_argument("--max-books", type=int, default=500000)
    parser.add_argument("--max-reviews", type=int, default=2000000)
    args = parser.parse_args()

    metadata_path = args.raw_dir / args.metadata_file
    reviews_path = args.raw_dir / args.reviews_file
    missing = [p for p in (metadata_path, reviews_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required raw files: {missing}")

    books = list(_iter_books(metadata_path, source_name=args.source, max_books=args.max_books))
    valid_book_ids = {str(row["book_id"]) for row in books}
    books_count = _write_jsonl(args.out_dir / "books_master.jsonl", books)

    train, valid, test = _split_interactions(
        reviews_path,
        valid_book_ids=valid_book_ids,
        source_name=args.source,
        max_reviews=args.max_reviews,
    )
    train_count = _write_jsonl(args.out_dir / "interactions_train.jsonl", train)
    valid_count = _write_jsonl(args.out_dir / "interactions_valid.jsonl", valid)
    test_count = _write_jsonl(args.out_dir / "interactions_test.jsonl", test)

    print("Amazon preprocessing complete")
    print(f"books_master.jsonl: {books_count}")
    print(f"interactions_train.jsonl: {train_count}")
    print(f"interactions_valid.jsonl: {valid_count}")
    print(f"interactions_test.jsonl: {test_count}")
    print(f"output_dir: {args.out_dir}")


if __name__ == "__main__":
    main()