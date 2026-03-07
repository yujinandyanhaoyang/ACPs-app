from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.book_retrieval import load_books, retrieve_books_by_query


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KINDLE_BOOKS_PATH = PROJECT_ROOT / "data" / "processed" / "amazon_kindle" / "books_master.jsonl"
KINDLE_INTERACTIONS_PATH = PROJECT_ROOT / "data" / "processed" / "amazon_kindle" / "interactions_train.jsonl"
MERGED_BOOKS_PATH = PROJECT_ROOT / "data" / "processed" / "merged" / "books_master_merged.jsonl"
MERGED_INTERACTIONS_PATH = PROJECT_ROOT / "data" / "processed" / "merged" / "interactions_merged.jsonl"


def _require(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"dataset artifact not found: {path}")


def _count_jsonl_rows(path: Path, limit: int | None = None) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
            if limit is not None and count >= limit:
                return count
    return count


def test_kindle_dataset_loads_and_retrieves() -> None:
    _require(KINDLE_BOOKS_PATH)
    books = load_books(KINDLE_BOOKS_PATH)
    assert len(books) >= 1000

    snowman = retrieve_books_by_query("snowman kindle", books, top_k=3)
    opera = retrieve_books_by_query("opera journeys bellini", books, top_k=3)

    assert snowman
    assert opera
    assert any("snowman" in str(row.get("title", "")).lower() for row in snowman)
    assert any("opera" in str(row.get("title", "")).lower() for row in opera)


def test_kindle_interactions_exist() -> None:
    _require(KINDLE_INTERACTIONS_PATH)
    assert _count_jsonl_rows(KINDLE_INTERACTIONS_PATH, limit=100) >= 100


def test_merged_dataset_loads_and_retrieves() -> None:
    _require(MERGED_BOOKS_PATH)
    books = load_books(MERGED_BOOKS_PATH)
    assert len(books) >= 1000

    hunger = retrieve_books_by_query("hunger games dystopian", books, top_k=3)
    assert hunger
    assert any("hunger games" in str(row.get("title", "")).lower() for row in hunger)


def test_merged_interactions_exist_and_are_jsonl() -> None:
    _require(MERGED_INTERACTIONS_PATH)
    assert _count_jsonl_rows(MERGED_INTERACTIONS_PATH, limit=100) >= 100

    with MERGED_INTERACTIONS_PATH.open("r", encoding="utf-8") as f:
        first = next((line for line in f if line.strip()), None)
    assert first is not None
    row = json.loads(first)
    assert {"user_id", "book_id", "rating"}.issubset(row.keys())