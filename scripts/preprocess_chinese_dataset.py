from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_BOOKS_PATH = PROJECT_ROOT / "data" / "raw" / "chinese" / "books_raw.jsonl"
RAW_INTERACTIONS_PATH = PROJECT_ROOT / "data" / "raw" / "chinese" / "interactions_raw.jsonl"
OUT_DIR = PROJECT_ROOT / "data" / "processed"


def _enforce_compliance_in_ci() -> None:
    if os.getenv("CI", "").lower() != "true":
        return
    if os.getenv("SKIP_DATA_COMPLIANCE_CHECK", "").lower() in {"1", "true", "yes"}:
        return

    checker = PROJECT_ROOT / "scripts" / "check_data_compliance.py"
    result = subprocess.run(
        [sys.executable, str(checker)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Data compliance check failed in CI before Chinese ingestion.\n"
            + (result.stdout or "")
            + (result.stderr or "")
        )


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_language(value: Any) -> str:
    token = _clean_text(value).lower()
    if token in {"zh", "zh-cn", "zh-hans", "zh-hant", "cn", "chinese", "中文"}:
        return "zh"
    if token in {"en", "en-us", "en-gb", "english"}:
        return "en"
    if token:
        return "mixed"
    return "zh"


def _normalize_script(value: Any, language: str) -> str:
    token = _clean_text(value).lower()
    if token in {"hans", "simplified", "简体"}:
        return "hans"
    if token in {"hant", "traditional", "繁體", "繁体"}:
        return "hant"
    if token in {"latin", "latn"}:
        return "latin"
    if language == "zh":
        return "hans"
    if language == "en":
        return "latin"
    return "latin"


def _normalize_genres(value: Any) -> List[str]:
    if isinstance(value, list):
        source = value
    elif isinstance(value, str):
        source = re.split(r"[,;/|、]", value)
    else:
        source = []

    genres: List[str] = []
    seen: set[str] = set()
    for item in source:
        token = _clean_text(item).lower().replace(" ", "_")
        token = re.sub(r"_+", "_", token).strip("_")
        if not token or token in seen:
            continue
        seen.add(token)
        genres.append(token)
    return genres


def _normalize_isbn(value: Any) -> str:
    token = re.sub(r"[^0-9Xx]", "", _clean_text(value)).upper()
    if len(token) in {10, 13}:
        return token
    return ""


def _safe_int(value: Any) -> int | None:
    raw = _clean_text(value)
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                yield row


def _stable_bucket(user_id: str, book_id: str) -> int:
    digest = hashlib.md5(f"{user_id}:{book_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _normalize_book_row(row: Dict[str, Any], fallback_index: int) -> Dict[str, Any] | None:
    title = _clean_text(row.get("title") or row.get("name"))
    if not title:
        return None

    book_id = _clean_text(row.get("book_id") or row.get("id") or row.get("source_book_id") or f"zh_{fallback_index}")
    if not book_id:
        return None

    language = _normalize_language(row.get("language"))
    source = _clean_text(row.get("source")) or "unknown"
    canonical = _clean_text(row.get("canonical_work_id") or row.get("work_id") or f"cw_{book_id}")

    normalized: Dict[str, Any] = {
        "book_id": book_id,
        "canonical_work_id": canonical,
        "title": title,
        "language": language,
        "source": source,
        "author": _clean_text(row.get("author")) or "Unknown",
        "description": _clean_text(row.get("description")),
        "genres": _normalize_genres(row.get("genres") or row.get("tags") or row.get("subjects")),
        "original_title": _clean_text(row.get("original_title")) or title,
        "translated_titles": row.get("translated_titles") if isinstance(row.get("translated_titles"), list) else [],
        "aliases": row.get("aliases") if isinstance(row.get("aliases"), list) else [],
        "publisher": _clean_text(row.get("publisher")),
        "published_year": _safe_int(row.get("published_year") or row.get("year")),
        "isbn10": _normalize_isbn(row.get("isbn10")),
        "isbn13": _normalize_isbn(row.get("isbn13")),
        "script": _normalize_script(row.get("script"), language),
        "source_book_id": _clean_text(row.get("source_book_id") or row.get("id") or book_id),
    }
    return normalized


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _normalize_interaction_row(row: Dict[str, Any], known_book_ids: set[str]) -> Dict[str, Any] | None:
    user_id = _clean_text(row.get("user_id") or row.get("uid"))
    book_id = _clean_text(row.get("book_id") or row.get("item_id"))
    if not user_id or not book_id:
        return None
    if book_id not in known_book_ids:
        return None

    rating_raw = row.get("rating", row.get("score", 0.0))
    try:
        rating = float(rating_raw)
    except (TypeError, ValueError):
        return None

    return {
        "user_id": user_id,
        "book_id": book_id,
        "rating": max(0.0, min(5.0, rating)),
        "timestamp": row.get("timestamp") if row.get("timestamp") is not None else None,
        "review_text": _clean_text(row.get("review_text") or row.get("review") or ""),
        "source": _clean_text(row.get("source")) or "unknown",
    }


def build_chinese_datasets(
    raw_books_path: Path = RAW_BOOKS_PATH,
    raw_interactions_path: Path = RAW_INTERACTIONS_PATH,
    out_dir: Path = OUT_DIR,
    max_interactions: int = 0,
) -> Dict[str, Any]:
    if not raw_books_path.exists():
        raise FileNotFoundError(f"books raw file not found: {raw_books_path}")
    if not raw_interactions_path.exists():
        raise FileNotFoundError(f"interactions raw file not found: {raw_interactions_path}")

    normalized_books: List[Dict[str, Any]] = []
    seen_book_ids: set[str] = set()
    for index, row in enumerate(_iter_jsonl(raw_books_path), start=1):
        normalized = _normalize_book_row(row, index)
        if not normalized:
            continue
        book_id = str(normalized["book_id"])
        if book_id in seen_book_ids:
            continue
        seen_book_ids.add(book_id)
        normalized_books.append(normalized)

    train: List[Dict[str, Any]] = []
    valid: List[Dict[str, Any]] = []
    test: List[Dict[str, Any]] = []

    for idx, row in enumerate(_iter_jsonl(raw_interactions_path), start=1):
        if max_interactions > 0 and idx > max_interactions:
            break
        normalized = _normalize_interaction_row(row, seen_book_ids)
        if not normalized:
            continue

        bucket = _stable_bucket(str(normalized["user_id"]), str(normalized["book_id"]))
        if bucket < 80:
            train.append(normalized)
        elif bucket < 90:
            valid.append(normalized)
        else:
            test.append(normalized)

    books_path = out_dir / "books_master_zh.jsonl"
    train_path = out_dir / "interactions_train_zh.jsonl"
    valid_path = out_dir / "interactions_valid_zh.jsonl"
    test_path = out_dir / "interactions_test_zh.jsonl"

    books_count = _write_jsonl(books_path, normalized_books)
    train_count = _write_jsonl(train_path, train)
    valid_count = _write_jsonl(valid_path, valid)
    test_count = _write_jsonl(test_path, test)

    return {
        "books_count": books_count,
        "train_count": train_count,
        "valid_count": valid_count,
        "test_count": test_count,
        "outputs": {
            "books_master_zh": str(books_path),
            "interactions_train_zh": str(train_path),
            "interactions_valid_zh": str(valid_path),
            "interactions_test_zh": str(test_path),
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preprocess Chinese books and interactions into normalized JSONL artifacts.")
    parser.add_argument("--raw-books", type=Path, default=RAW_BOOKS_PATH)
    parser.add_argument("--raw-interactions", type=Path, default=RAW_INTERACTIONS_PATH)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--max-interactions", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    _enforce_compliance_in_ci()
    args = _parse_args()
    report = build_chinese_datasets(
        raw_books_path=args.raw_books,
        raw_interactions_path=args.raw_interactions,
        out_dir=args.out_dir,
        max_interactions=args.max_interactions,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
