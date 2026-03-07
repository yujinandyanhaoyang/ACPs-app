from pathlib import Path

from scripts.build_books_min_dataset import build_dataset
from services.data_paths import get_raw_data_path
from services.book_retrieval import load_books, retrieve_books_by_query, get_active_retrieval_corpus_info


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = get_raw_data_path("books_min_sample.jsonl")
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


def test_load_books_prefers_merged_goodreads_or_fallback():
    books = load_books()
    assert books
    assert {"book_id", "title", "author", "description", "genres"}.issubset(books[0].keys())


def test_load_books_prefers_merged_and_enriched_when_present(monkeypatch, tmp_path):
    merged = tmp_path / "books_master_merged.jsonl"
    enriched = tmp_path / "books_master_merged_enriched.jsonl"
    merged.write_text(
        '{"book_id": "merged_001", "title": "Merged", "author": "A", "description": "B", "genres": ["x"]}\n',
        encoding="utf-8",
    )
    enriched.write_text(
        '{"book_id": "enriched_001", "title": "Enriched", "author": "A", "description": "B", "genres": ["x"]}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr("services.book_retrieval.MERGED_DATASET_PATH", merged)
    monkeypatch.setattr("services.book_retrieval.MERGED_ENRICHED_DATASET_PATH", enriched)
    monkeypatch.setattr("services.book_retrieval.GOODREADS_DATASET_PATH", tmp_path / "missing_goodreads.jsonl")
    monkeypatch.setattr("services.book_retrieval.BOOKS_MIN_DATASET_PATH", tmp_path / "missing_books_min.jsonl")
    monkeypatch.delenv("BOOK_RETRIEVAL_DATASET_PATH", raising=False)

    books = load_books()
    assert len(books) == 1
    assert books[0]["book_id"] == "enriched_001"


def test_get_active_retrieval_corpus_info_reports_selection(monkeypatch, tmp_path):
    merged = tmp_path / "books_master_merged.jsonl"
    merged.write_text(
        '{"book_id": "merged_001", "title": "Merged", "author": "A", "description": "B", "genres": ["x"]}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr("services.book_retrieval.MERGED_ENRICHED_DATASET_PATH", tmp_path / "missing_enriched.jsonl")
    monkeypatch.setattr("services.book_retrieval.MERGED_DATASET_PATH", merged)
    monkeypatch.setattr("services.book_retrieval.GOODREADS_DATASET_PATH", tmp_path / "missing_goodreads.jsonl")
    monkeypatch.setattr("services.book_retrieval.BOOKS_MIN_DATASET_PATH", tmp_path / "missing_books_min.jsonl")
    monkeypatch.delenv("BOOK_RETRIEVAL_DATASET_PATH", raising=False)

    info = get_active_retrieval_corpus_info()
    assert info["exists"] is True
    assert info["selection_source"] == "merged-default"
    assert info["file_name"] == "books_master_merged.jsonl"


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
