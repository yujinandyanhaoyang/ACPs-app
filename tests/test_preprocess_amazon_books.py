from __future__ import annotations

import gzip
import json
from pathlib import Path

from scripts.preprocess_amazon_books import _iter_books, _split_interactions


def _write_gzip_jsonl(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_iter_books_normalizes_amazon_metadata(tmp_path: Path) -> None:
    metadata_path = tmp_path / "meta_Books.json.gz"
    _write_gzip_jsonl(
        metadata_path,
        [
            {
                "asin": "A1",
                "title": " Test Book ",
                "brand": "Author Name",
                "description": [" First line ", "Second line"],
                "categories": [["Books", "Science Fiction", "Space Opera"]],
                "publisher": "Test Publisher",
                "date": "2001-05-01",
            }
        ],
    )

    books = list(_iter_books(metadata_path, source_name="amazon-books-2018", max_books=10))
    assert len(books) == 1
    assert books[0]["book_id"] == "amz_A1"
    assert books[0]["title"] == "Test Book"
    assert books[0]["author"] == "Author Name"
    assert books[0]["published_year"] == 2001
    assert books[0]["genres"] == ["science_fiction", "space_opera"]


def test_split_interactions_filters_unknown_books_and_splits(tmp_path: Path) -> None:
    reviews_path = tmp_path / "Books_5.json.gz"
    _write_gzip_jsonl(
        reviews_path,
        [
            {
                "reviewerID": "U1",
                "asin": "A1",
                "overall": 5.0,
                "summary": "Great",
                "reviewText": "Loved it",
                "unixReviewTime": 1234567890,
            },
            {
                "reviewerID": "U2",
                "asin": "MISSING",
                "overall": 4.0,
            },
        ],
    )

    train, valid, test = _split_interactions(
        reviews_path,
        valid_book_ids={"amz_A1"},
        source_name="amazon-books-2018",
        max_reviews=10,
    )

    total = train + valid + test
    assert len(total) == 1
    assert total[0]["book_id"] == "amz_A1"
    assert total[0]["user_id"] == "amz_u_U1"
    assert total[0]["review_text"] == "Great. Loved it"