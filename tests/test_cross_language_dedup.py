import json
from pathlib import Path

from scripts.build_cross_language_canonical_map import build_canonical_map


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


def test_build_canonical_map_uses_isbn_and_declared_canonical(tmp_path):
    en_path = tmp_path / "en_books.jsonl"
    zh_path = tmp_path / "zh_books.jsonl"
    out_dir = tmp_path / "out"

    _write_jsonl(
        en_path,
        [
            {
                "book_id": "en_1",
                "title": "The Three-Body Problem",
                "author": "Liu Cixin",
                "isbn13": "9780765377067",
                "canonical_work_id": "cw_three_body",
            },
            {
                "book_id": "en_2",
                "title": "Independent Title",
                "author": "Alice",
            },
        ],
    )

    _write_jsonl(
        zh_path,
        [
            {
                "book_id": "zh_1",
                "title": "三体",
                "author": "刘慈欣",
                "isbn13": "9780765377067",
            },
            {
                "book_id": "zh_2",
                "title": "治理现代化",
                "author": "张三",
                "canonical_work_id": "cw_governance",
            },
        ],
    )

    report = build_canonical_map(en_path, zh_path, out_dir, fuzzy_threshold=0.93)
    assert report["book_count"] == 4

    with (out_dir / "book_canonical_map.json").open("r", encoding="utf-8") as f:
        mapping = json.load(f)

    assert mapping["en_1"] == mapping["zh_1"]
    assert mapping["zh_2"] == "cw_governance"
    assert mapping["en_2"].startswith("cw_auto_")

    merged = _read_jsonl(out_dir / "books_master_merged.jsonl")
    assert len(merged) == 4
    assert all(str(row.get("canonical_work_id") or "").strip() for row in merged)


def test_build_canonical_map_conservative_fuzzy_does_not_overmerge(tmp_path):
    en_path = tmp_path / "en_books.jsonl"
    zh_path = tmp_path / "zh_books.jsonl"
    out_dir = tmp_path / "out"

    _write_jsonl(
        en_path,
        [{"book_id": "en_a", "title": "Happy Kids Stories", "author": "Jane Doe"}],
    )
    _write_jsonl(
        zh_path,
        [{"book_id": "zh_a", "title": "Dark Crime Stories", "author": "John Roe"}],
    )

    build_canonical_map(en_path, zh_path, out_dir, fuzzy_threshold=0.95)
    with (out_dir / "book_canonical_map.json").open("r", encoding="utf-8") as f:
        mapping = json.load(f)

    assert mapping["en_a"] != mapping["zh_a"]
