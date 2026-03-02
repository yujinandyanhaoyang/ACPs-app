import json
from pathlib import Path

from scripts.preprocess_chinese_dataset import build_chinese_datasets


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def test_build_chinese_datasets_outputs_expected_files(tmp_path):
    books_raw = tmp_path / "books_raw.jsonl"
    interactions_raw = tmp_path / "interactions_raw.jsonl"
    out_dir = tmp_path / "processed"

    _write_jsonl(
        books_raw,
        [
            {
                "book_id": "zh_001",
                "title": "白鹿原",
                "author": "陈忠实",
                "language": "zh",
                "source": "douban",
                "genres": ["乡土文学", "现实主义"],
                "isbn13": "9787020042493",
            },
            {
                "book_id": "zh_002",
                "title": "基层治理概论",
                "author": "张三",
                "language": "中文",
                "source": "douban",
                "genres": "治理,政策",
            },
            {
                "book_id": "zh_003",
                "title": "",
                "author": "ignored",
            },
        ],
    )

    _write_jsonl(
        interactions_raw,
        [
            {"user_id": "u1", "book_id": "zh_001", "rating": 5, "source": "douban"},
            {"user_id": "u2", "book_id": "zh_002", "rating": 4, "source": "douban"},
            {"user_id": "u3", "book_id": "zh_404", "rating": 5, "source": "douban"},
        ],
    )

    report = build_chinese_datasets(
        raw_books_path=books_raw,
        raw_interactions_path=interactions_raw,
        out_dir=out_dir,
    )

    assert report["books_count"] == 2
    assert report["train_count"] + report["valid_count"] + report["test_count"] == 2

    books = _read_jsonl(out_dir / "books_master_zh.jsonl")
    assert len(books) == 2
    assert {
        "book_id",
        "canonical_work_id",
        "title",
        "language",
        "source",
        "author",
        "description",
        "genres",
    }.issubset(books[0].keys())
    assert all(row["language"] in {"zh", "en", "mixed"} for row in books)


def test_build_chinese_datasets_normalizes_missing_author(tmp_path):
    books_raw = tmp_path / "books_raw.jsonl"
    interactions_raw = tmp_path / "interactions_raw.jsonl"
    out_dir = tmp_path / "processed"

    _write_jsonl(
        books_raw,
        [{"book_id": "zh_100", "title": "测试图书", "language": "zh", "source": "openlibrary"}],
    )
    _write_jsonl(interactions_raw, [{"user_id": "u1", "book_id": "zh_100", "rating": 3.5}])

    build_chinese_datasets(books_raw, interactions_raw, out_dir)
    books = _read_jsonl(out_dir / "books_master_zh.jsonl")

    assert books
    assert books[0]["author"] == "Unknown"
