from __future__ import annotations

import json
from pathlib import Path

from scripts.enrich_books_openlibrary import _best_doc, enrich_row
from scripts.merge_book_corpora import merge_books, merge_interactions


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_merge_books_dedupes_on_title_author(tmp_path: Path) -> None:
    p1 = tmp_path / "g.jsonl"
    p2 = tmp_path / "a.jsonl"
    _write_jsonl(
        p1,
        [{"book_id": "gr_1", "title": "Dune", "author": "Frank Herbert", "description": "", "genres": ["science_fiction"], "source": "goodreads"}],
    )
    _write_jsonl(
        p2,
        [{"book_id": "amz_1", "title": "Dune", "author": "Frank Herbert", "description": "Epic desert saga", "genres": ["space_opera"], "source": "amazon-books-2018"}],
    )

    merged, stats = merge_books([p1, p2])
    assert len(merged) == 1
    assert stats["deduped_books"] == 1
    assert merged[0]["description"] == "Epic desert saga"
    assert set(merged[0]["genres"]) == {"science_fiction", "space_opera"}


def test_merge_interactions_filters_books(tmp_path: Path) -> None:
    p1 = tmp_path / "i.jsonl"
    _write_jsonl(
        p1,
        [
            {"user_id": "u1", "book_id": "gr_1", "rating": 5},
            {"user_id": "u2", "book_id": "missing", "rating": 4},
        ],
    )

    merged, stats = merge_interactions([p1], {"gr_1"})
    assert len(merged) == 1
    assert stats["dropped_missing_book"] == 1


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    def get(self, _url: str, params: dict, timeout: float):
        assert timeout > 0
        assert params["title"] == "Dune"
        return _FakeResponse(
            {
                "docs": [
                    {
                        "title": "Dune",
                        "author_name": ["Frank Herbert"],
                        "publisher": ["Ace"],
                        "first_publish_year": 1965,
                        "subject": ["Science fiction", "Space opera"],
                    }
                ]
            }
        )


def test_best_doc_prefers_title_author_match() -> None:
    doc = _best_doc(
        "Dune",
        "Frank Herbert",
        [
            {"title": "Dune Messiah", "author_name": ["Frank Herbert"]},
            {"title": "Dune", "author_name": ["Frank Herbert"]},
        ],
    )
    assert doc is not None
    assert doc["title"] == "Dune"


def test_enrich_row_backfills_metadata() -> None:
    row = {"book_id": "gr_1", "title": "Dune", "author": "Frank Herbert", "description": "", "genres": [], "source": "goodreads"}
    enriched = enrich_row(_FakeSession(), row, timeout=5.0)
    assert enriched["publisher"] == "Ace"
    assert enriched["published_year"] == 1965
    assert "science_fiction" in enriched["genres"]
    assert "openlibrary" in enriched["source"]