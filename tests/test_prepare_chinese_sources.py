import csv
import json
from pathlib import Path

from scripts.prepare_chinese_sources import prepare_sources


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


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
            if line:
                rows.append(json.loads(line))
    return rows


def test_prepare_sources_builds_unified_raw_files(tmp_path):
    inputs_dir = tmp_path / "sources"
    douban_dir = inputs_dir / "douban"
    modelscope_dir = inputs_dir / "modelscope"

    _write_csv(
        douban_dir / "books.csv",
        [
            {"id": "db1", "title": "白鹿原", "author": "陈忠实", "genres": "乡土文学,现实主义", "language": "zh"},
            {"id": "db2", "title": "基层治理概论", "author": "张三", "genres": "治理,政策", "language": "zh"},
        ],
    )
    _write_jsonl(
        douban_dir / "interactions.jsonl",
        [
            {"uid": "u1", "item_id": "db1", "score": 5},
            {"uid": "u2", "item_id": "db2", "score": 4.5},
        ],
    )

    _write_jsonl(
        modelscope_dir / "books.jsonl",
        [
            {"book_id": "ms1", "title": "温暖童话集", "author": "李四", "tags": ["儿童", "童话"]},
        ],
    )
    _write_csv(
        modelscope_dir / "ratings.csv",
        [
            {"user_id": "u3", "book_id": "ms1", "rating": 4.0},
        ],
    )

    out_books = tmp_path / "raw" / "books_raw.jsonl"
    out_interactions = tmp_path / "raw" / "interactions_raw.jsonl"

    report = prepare_sources(
        inputs_dir=inputs_dir,
        out_books=out_books,
        out_interactions=out_interactions,
    )

    assert report["books_count"] == 3
    assert report["interactions_count"] == 3

    books = _read_jsonl(out_books)
    interactions = _read_jsonl(out_interactions)

    assert all(str(row.get("book_id") or "").startswith(("douban:", "modelscope:")) for row in books)
    assert all(str(row.get("user_id") or "").startswith(("douban:", "modelscope:")) for row in interactions)
    assert all(str(row.get("book_id") or "") in {item["book_id"] for item in books} for row in interactions)


def test_prepare_sources_filters_interactions_missing_books(tmp_path):
    inputs_dir = tmp_path / "sources"
    source_dir = inputs_dir / "douban"

    _write_jsonl(source_dir / "books.jsonl", [{"book_id": "b1", "title": "书A"}])
    _write_jsonl(
        source_dir / "interactions.jsonl",
        [
            {"user_id": "u1", "book_id": "b1", "rating": 5},
            {"user_id": "u2", "book_id": "missing", "rating": 4},
        ],
    )

    out_books = tmp_path / "raw" / "books_raw.jsonl"
    out_interactions = tmp_path / "raw" / "interactions_raw.jsonl"

    report = prepare_sources(inputs_dir=inputs_dir, out_books=out_books, out_interactions=out_interactions)
    assert report["books_count"] == 1
    assert report["interactions_count"] == 1
