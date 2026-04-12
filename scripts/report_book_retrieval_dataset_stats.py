from __future__ import annotations

import argparse
import csv
import gzip
import heapq
import json
import math
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.data_paths import get_raw_data_root


_SPACE_RE = re.compile(r"\s+")
_STRIP_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_DEFAULT_MD_PATH = Path("artifacts") / "book_retrieval_dataset_report.md"


@dataclass(frozen=True)
class BookRow:
    source: str
    book_id: str
    title: str
    author: str
    description: Any
    genres: Any
    rating: str
    completeness: int
    valid_description: bool


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return " | ".join(_norm_text(item) for item in value if _norm_text(item))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _SPACE_RE.sub(" ", str(value).replace("\u00a0", " ").strip())


def _norm_key(value: Any) -> str:
    return _STRIP_RE.sub("", _norm_text(value).lower())


def _is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    if isinstance(value, list):
        return any(_is_nonempty(item) for item in value)
    if isinstance(value, dict):
        return bool(value)
    return bool(_norm_text(value))


def _desc_length(value: Any) -> int:
    if not _is_nonempty(value):
        return 0
    if isinstance(value, list):
        text = " ".join(_norm_text(item) for item in value if _norm_text(item))
    else:
        text = _norm_text(value)
    return len(text)


def _genre_count(value: Any) -> int:
    if isinstance(value, list):
        return sum(1 for item in value if _norm_text(item))
    return 1 if _is_nonempty(value) else 0


def _pct(part: int, whole: int) -> float:
    return (100.0 * part / whole) if whole else 0.0


def _fmt_pct(part: int, whole: int) -> str:
    return f"{_pct(part, whole):.2f}%"


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _iter_goodreads_books(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def _iter_jsonl_gz(path: Path) -> Iterable[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            if isinstance(row, dict):
                yield row


def _book_completeness(row: BookRow) -> int:
    return sum(
        1
        for present in (
            bool(row.book_id),
            bool(row.title),
            bool(row.author),
            _is_nonempty(row.description),
            bool(_genre_count(row.genres)),
            bool(row.rating),
        )
        if present
    )


def _book_to_jsonable(row: BookRow) -> Dict[str, Any]:
    return {
        "source": row.source,
        "book_id": row.book_id,
        "title": row.title,
        "author": row.author,
        "description": row.description if _is_nonempty(row.description) else "",
        "genres": row.genres if _is_nonempty(row.genres) else [],
        "rating": row.rating,
        "completeness": row.completeness,
        "valid_description": row.valid_description,
    }


def _make_md(stats: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Book Retrieval Dataset Stats")
    lines.append("")
    lines.append(f"- Dataset root: `{stats['dataset_root']}`")
    lines.append(f"- Goodreads source: `{stats['goodreads_path']}`")
    lines.append(f"- Amazon sources: `{stats['amazon_paths'][0]}`, `{stats['amazon_paths'][1]}`")
    lines.append(f"- Match heuristic: normalized `title + author/brand`")
    lines.append("")
    lines.append("## 1. 总书目数量")
    lines.append("")
    lines.append(f"- Goodreads 书目数: **{_fmt_int(stats['goodreads_rows'])}**")
    lines.append(f"- Amazon 书目数: **{_fmt_int(stats['amazon_rows'])}**")
    lines.append(f"- 合计扫描记录数: **{_fmt_int(stats['goodreads_rows'] + stats['amazon_rows'])}**")
    lines.append("")
    lines.append("## 2. 各字段填充率")
    lines.append("")
    lines.append("### Goodreads (`books.csv`)")
    lines.append("")
    lines.append("| 字段 | 填充数 | 填充率 |")
    lines.append("|---|---:|---:|")
    for field in ("book_id", "title", "author", "rating"):
        lines.append(
            f"| {field} | {_fmt_int(stats['goodreads_counts'][field])} | {_fmt_pct(stats['goodreads_counts'][field], stats['goodreads_rows'])} |"
        )
    lines.append("| description / blurb / summary | 0 | 0.00% |")
    lines.append("| genres / categories / tags | 0 | 0.00% |")
    lines.append("")
    lines.append("### Amazon (`meta_*.json.gz`)")
    lines.append("")
    lines.append("| 字段 | 填充数 | 填充率 |")
    lines.append("|---|---:|---:|")
    for field in ("book_id", "title", "author", "description", "genres", "rating"):
        lines.append(
            f"| {field} | {_fmt_int(stats['amazon_counts'][field])} | {_fmt_pct(stats['amazon_counts'][field], stats['amazon_rows'])} |"
        )
    lines.append("")
    lines.append("## 3. Description 平均长度")
    lines.append("")
    lines.append(
        f"- 非空 description 平均字符长度: **{stats['amazon_desc_avg_len_all_nonempty']:.2f}**"
    )
    lines.append(
        f"- 有效 description 平均字符长度（>=50 字符）: **{stats['amazon_desc_avg_len_valid_50']:.2f}**"
    )
    lines.append(
        f"- 有效 description 数量（>=50 字符）: **{_fmt_int(stats['amazon_desc_valid_count_50'])}**"
    )
    lines.append("")
    lines.append("## 4. Goodreads vs Amazon 交叉匹配率")
    lines.append("")
    lines.append(
        "- 口径：按归一化后的 `title + author/brand` 做近似匹配，因为原始两套源数据并没有统一全局 `book_id`。"
    )
    lines.append(
        f"- Goodreads 中可在 Amazon 找到匹配的比例: **{_fmt_pct(stats['cross_match_count'], stats['goodreads_rows'])}**"
    )
    lines.append(
        f"- Amazon 中可在 Goodreads 找到匹配的比例: **{_fmt_pct(stats['cross_match_count'], stats['amazon_rows'])}**"
    )
    lines.append(
        f"- 命中记录数: **{_fmt_int(stats['cross_match_count'])}**"
    )
    lines.append("")
    lines.append("## 5. 样本")
    lines.append("")
    lines.append("### 字段最完整的 5 条")
    lines.append("")
    lines.append("| source | book_id | title | author | completeness | valid_description |")
    lines.append("|---|---|---|---|---:|---:|")
    for row in stats["most_complete"]:
        lines.append(
            "| {source} | {book_id} | {title} | {author} | {completeness} | {valid_description} |".format(
                source=row["source"],
                book_id=row["book_id"] or "",
                title=row["title"] or "",
                author=row["author"] or "",
                completeness=row["completeness"],
                valid_description="yes" if row["valid_description"] else "no",
            )
        )
    lines.append("")
    lines.append("```json")
    for row in stats["most_complete"]:
        lines.append(json.dumps(row, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("### 字段最少的 5 条")
    lines.append("")
    lines.append("| source | book_id | title | author | completeness | valid_description |")
    lines.append("|---|---|---|---|---:|---:|")
    for row in stats["least_complete"]:
        lines.append(
            "| {source} | {book_id} | {title} | {author} | {completeness} | {valid_description} |".format(
                source=row["source"],
                book_id=row["book_id"] or "",
                title=row["title"] or "",
                author=row["author"] or "",
                completeness=row["completeness"],
                valid_description="yes" if row["valid_description"] else "no",
            )
        )
    lines.append("")
    lines.append("```json")
    for row in stats["least_complete"]:
        lines.append(json.dumps(row, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan BOOK_RETRIEVAL_DATASET_PATH and generate a Markdown stats report.")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path(os.getenv("BOOK_RETRIEVAL_DATASET_PATH", "")).expanduser()
        if os.getenv("BOOK_RETRIEVAL_DATASET_PATH", "").strip()
        else get_raw_data_root().parent,
        help="Dataset root that contains the raw/ directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_MD_PATH,
        help="Markdown output path.",
    )
    args = parser.parse_args()

    dataset_root = args.dataset_root.expanduser().resolve()
    raw_root = dataset_root / "raw"
    goodreads_path = raw_root / "goodreads" / "books.csv"
    amazon_paths = [
        raw_root / "amazon_books" / "meta_Books.json.gz",
        raw_root / "amazon_books" / "meta_Kindle_Store.json.gz",
    ]

    if not goodreads_path.exists():
        raise FileNotFoundError(f"Goodreads file not found: {goodreads_path}")
    for path in amazon_paths:
        if not path.exists():
            raise FileNotFoundError(f"Amazon file not found: {path}")

    goodreads_rows = 0
    goodreads_counts = {"book_id": 0, "title": 0, "author": 0, "rating": 0}
    goodreads_keys: set[Tuple[str, str]] = set()

    for row in _iter_goodreads_books(goodreads_path):
        goodreads_rows += 1
        title = _norm_text(row.get("title"))
        author = _norm_text(row.get("authors"))
        goodreads_counts["book_id"] += 1 if _norm_text(row.get("book_id")) else 0
        goodreads_counts["title"] += 1 if title else 0
        goodreads_counts["author"] += 1 if author else 0
        goodreads_counts["rating"] += 1 if _norm_text(row.get("average_rating")) else 0
        goodreads_keys.add((_norm_key(title), _norm_key(author)))

    amazon_rows = 0
    amazon_counts = {"book_id": 0, "title": 0, "author": 0, "description": 0, "genres": 0, "rating": 0}
    amazon_desc_len_sum = 0
    amazon_desc_valid_count_50 = 0
    amazon_desc_valid_len_sum = 0
    cross_match_count = 0

    most_complete: List[Tuple[int, int, BookRow]] = []
    least_complete: List[Tuple[int, int, BookRow]] = []
    seq = 0

    for path in amazon_paths:
        for row in _iter_jsonl_gz(path):
            amazon_rows += 1
            title = _norm_text(row.get("title"))
            author = _norm_text(row.get("brand"))
            description = row.get("description")
            genres = row.get("category")
            rating = _norm_text(row.get("average_rating") or row.get("rating"))
            book_id = _norm_text(row.get("asin"))
            has_desc = _is_nonempty(description)
            has_genres = _genre_count(genres) > 0
            valid_desc = has_desc and _desc_length(description) >= 50

            amazon_counts["book_id"] += 1 if book_id else 0
            amazon_counts["title"] += 1 if title else 0
            amazon_counts["author"] += 1 if author else 0
            amazon_counts["description"] += 1 if has_desc else 0
            amazon_counts["genres"] += 1 if has_genres else 0
            amazon_counts["rating"] += 1 if rating else 0

            if has_desc:
                desc_len = _desc_length(description)
                amazon_desc_len_sum += desc_len
                if desc_len >= 50:
                    amazon_desc_valid_count_50 += 1
                    amazon_desc_valid_len_sum += desc_len

            if (_norm_key(title), _norm_key(author)) in goodreads_keys:
                cross_match_count += 1

            book_row = BookRow(
                source="amazon",
                book_id=book_id,
                title=title,
                author=author,
                description=description,
                genres=genres,
                rating=rating,
                completeness=0,
                valid_description=valid_desc,
            )
            scored = replace(book_row, completeness=_book_completeness(book_row))
            seq += 1
            item = (scored.completeness, seq, scored)

            if len(most_complete) < 5:
                heapq.heappush(most_complete, item)
            else:
                heapq.heappushpop(most_complete, item)

            worst_item = (-scored.completeness, seq, scored)
            if len(least_complete) < 5:
                heapq.heappush(least_complete, worst_item)
            else:
                heapq.heappushpop(least_complete, worst_item)

    # Add Goodreads rows into sample selection too.
    seq = 0
    for row in _iter_goodreads_books(goodreads_path):
        title = _norm_text(row.get("title"))
        author = _norm_text(row.get("authors"))
        book_row = BookRow(
            source="goodreads",
            book_id=_norm_text(row.get("book_id")),
            title=title,
            author=author,
            description="",
            genres=[],
            rating=_norm_text(row.get("average_rating")),
            completeness=0,
            valid_description=False,
        )
        scored = replace(book_row, completeness=_book_completeness(book_row))
        seq += 1
        item = (scored.completeness, seq, scored)
        if len(most_complete) < 5:
            heapq.heappush(most_complete, item)
        else:
            heapq.heappushpop(most_complete, item)
        worst_item = (-scored.completeness, seq, scored)
        if len(least_complete) < 5:
            heapq.heappush(least_complete, worst_item)
        else:
            heapq.heappushpop(least_complete, worst_item)

    most_complete_rows = [
        _book_to_jsonable(item[2])
        for item in sorted(most_complete, key=lambda x: (-x[0], x[1], x[2].source, x[2].book_id))
    ][:5]
    least_complete_rows = [
        _book_to_jsonable(item[2])
        for item in sorted(least_complete, key=lambda x: (x[0], x[1], x[2].source, x[2].book_id))
    ][:5]

    stats = {
        "dataset_root": str(dataset_root),
        "goodreads_path": str(goodreads_path),
        "amazon_paths": [str(p) for p in amazon_paths],
        "goodreads_rows": goodreads_rows,
        "amazon_rows": amazon_rows,
        "goodreads_counts": goodreads_counts,
        "amazon_counts": amazon_counts,
        "amazon_desc_avg_len_all_nonempty": (amazon_desc_len_sum / amazon_counts["description"]) if amazon_counts["description"] else 0.0,
        "amazon_desc_avg_len_valid_50": (amazon_desc_valid_len_sum / amazon_desc_valid_count_50) if amazon_desc_valid_count_50 else 0.0,
        "amazon_desc_valid_count_50": amazon_desc_valid_count_50,
        "cross_match_count": cross_match_count,
        "most_complete": most_complete_rows,
        "least_complete": least_complete_rows,
    }

    md = _make_md(stats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    print(f"Markdown report written to: {args.output}")
    print(f"Goodreads rows: {goodreads_rows}")
    print(f"Amazon rows: {amazon_rows}")
    print(f"Cross-match rows: {cross_match_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
