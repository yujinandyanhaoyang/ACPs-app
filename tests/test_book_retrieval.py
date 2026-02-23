from pathlib import Path

from scripts.build_books_min_dataset import build_dataset
from services.book_retrieval import load_books, retrieve_books_by_query


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "books_min_sample.jsonl"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "books_min.jsonl"


def test_build_books_min_dataset_generates_output():
    count = build_dataset(RAW_PATH, OUT_PATH)
    assert count >= 24
    assert OUT_PATH.exists()


def test_load_books_returns_non_empty_records():
    build_dataset(RAW_PATH, OUT_PATH)
    books = load_books(OUT_PATH)
    assert books
    assert {"book_id", "title", "author", "description", "genres"}.issubset(books[0].keys())


def test_retrieve_books_by_query_returns_relevant_candidates():
    build_dataset(RAW_PATH, OUT_PATH)
    books = load_books(OUT_PATH)

    sci = retrieve_books_by_query("science fiction space", books, top_k=5)
    hist = retrieve_books_by_query("history civilization", books, top_k=5)

    assert sci
    assert hist
    assert any("science_fiction" in row.get("genres", []) for row in sci)
    assert any("history" in row.get("genres", []) for row in hist)


def test_load_books_prefers_goodreads_default_or_fallback():
    books = load_books()
    assert books
    assert {"book_id", "title", "author", "description", "genres"}.issubset(books[0].keys())


def test_load_books_respects_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom_books.jsonl"
    custom.write_text(
        '{"book_id": "custom_001", "title": "Custom", "author": "A", "description": "B", "genres": ["x"]}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("BOOK_RETRIEVAL_DATASET_PATH", str(custom))
    books = load_books()
    assert len(books) == 1
    assert books[0]["book_id"] == "custom_001"
