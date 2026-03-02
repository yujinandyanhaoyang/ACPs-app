from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS_DIR = PROJECT_ROOT / "data" / "raw" / "chinese_sources"
DEFAULT_OUT_BOOKS = PROJECT_ROOT / "data" / "raw" / "chinese" / "books_raw.jsonl"
DEFAULT_OUT_INTERACTIONS = PROJECT_ROOT / "data" / "raw" / "chinese" / "interactions_raw.jsonl"


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                yield payload


def _iter_json(path: Path) -> Iterator[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict):
                yield row
        return

    if isinstance(payload, dict):
        for key in ["data", "records", "items", "books", "interactions"]:
            value = payload.get(key)
            if isinstance(value, list):
                for row in value:
                    if isinstance(row, dict):
                        yield row
                return
        yield payload


def _iter_csv(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if isinstance(row, dict):
                yield row


def _iter_parquet(path: Path) -> Iterator[Dict[str, Any]]:
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Parquet input requires pandas (and pyarrow/fastparquet). "
            "Install pandas to use parquet sources."
        ) from exc

    frame = pd.read_parquet(path)
    for row in frame.to_dict(orient="records"):
        if isinstance(row, dict):
            yield row


def _iter_records(path: Path) -> Iterator[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        yield from _iter_jsonl(path)
        return
    if suffix == ".json":
        yield from _iter_json(path)
        return
    if suffix == ".csv":
        yield from _iter_csv(path)
        return
    if suffix == ".parquet":
        yield from _iter_parquet(path)
        return
    raise ValueError(f"unsupported file extension: {path}")


def _first(row: Dict[str, Any], keys: List[str], default: Any = "") -> Any:
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return default


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item for item in re.split(r"[,;/|、]", value) if item.strip()]
    return []


def _normalize_book(raw: Dict[str, Any], source: str, fallback_index: int) -> Dict[str, Any] | None:
    source_book_id = _clean_text(_first(raw, ["book_id", "id", "item_id", "bookId", "sid"], default=f"book_{fallback_index}"))
    title = _clean_text(_first(raw, ["title", "name", "book_title", "bookName"]))
    if not title:
        return None

    new_book_id = f"{source}:{source_book_id}"
    normalized: Dict[str, Any] = {
        "book_id": new_book_id,
        "source_book_id": source_book_id,
        "title": title,
        "original_title": _clean_text(_first(raw, ["original_title", "originalTitle"], default=title)),
        "author": _clean_text(_first(raw, ["author", "authors", "writer"], default="Unknown")) or "Unknown",
        "description": _clean_text(_first(raw, ["description", "intro", "summary", "content"])),
        "genres": _as_list(_first(raw, ["genres", "tags", "subjects", "category"])),
        "language": _clean_text(_first(raw, ["language", "lang"], default="zh")) or "zh",
        "source": source,
        "publisher": _clean_text(_first(raw, ["publisher", "press"])),
        "published_year": _first(raw, ["published_year", "year", "publish_year"], default=None),
        "isbn10": _clean_text(_first(raw, ["isbn10", "isbn_10"])),
        "isbn13": _clean_text(_first(raw, ["isbn13", "isbn_13", "isbn"])),
        "canonical_work_id": _clean_text(_first(raw, ["canonical_work_id", "work_id", "series_id"], default=f"cw_{new_book_id}")),
    }
    return normalized


def _normalize_interaction(
    raw: Dict[str, Any],
    source: str,
    raw_to_prefixed_book_id: Dict[str, str],
    fallback_index: int,
) -> Dict[str, Any] | None:
    source_user_id = _clean_text(_first(raw, ["user_id", "uid", "user", "userId", "reviewer_id"], default=f"user_{fallback_index}"))
    source_book_id = _clean_text(_first(raw, ["book_id", "item_id", "book", "bookId", "sid"]))
    if not source_user_id or not source_book_id:
        return None

    mapped_book_id = raw_to_prefixed_book_id.get(source_book_id)
    if mapped_book_id is None:
        mapped_book_id = f"{source}:{source_book_id}"

    rating_raw = _first(raw, ["rating", "score", "stars"], default=0)
    try:
        rating = float(rating_raw)
    except (TypeError, ValueError):
        return None

    return {
        "user_id": f"{source}:{source_user_id}",
        "book_id": mapped_book_id,
        "rating": rating,
        "timestamp": _first(raw, ["timestamp", "time", "created_at"], default=None),
        "review_text": _clean_text(_first(raw, ["review_text", "review", "comment"])),
        "source": source,
    }


def _discover_source_dirs(inputs_dir: Path, explicit_dirs: List[Path] | None = None) -> List[Path]:
    if explicit_dirs:
        return [item for item in explicit_dirs if item.exists() and item.is_dir()]

    if not inputs_dir.exists():
        return []

    children = [child for child in inputs_dir.iterdir() if child.is_dir()]
    if children:
        return sorted(children)
    return [inputs_dir]


def _discover_data_files(source_dir: Path) -> Tuple[List[Path], List[Path]]:
    supported = {".jsonl", ".json", ".csv", ".parquet"}
    files = [path for path in source_dir.rglob("*") if path.is_file() and path.suffix.lower() in supported]
    books: List[Path] = []
    interactions: List[Path] = []
    for path in files:
        token = path.name.lower()
        if "interact" in token or "rating" in token or "review" in token:
            interactions.append(path)
        elif "book" in token or "item" in token or "meta" in token:
            books.append(path)
    return sorted(books), sorted(interactions)


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def prepare_sources(
    inputs_dir: Path = DEFAULT_INPUTS_DIR,
    source_dirs: List[Path] | None = None,
    out_books: Path = DEFAULT_OUT_BOOKS,
    out_interactions: Path = DEFAULT_OUT_INTERACTIONS,
    max_books: int = 0,
    max_interactions: int = 0,
) -> Dict[str, Any]:
    discovered = _discover_source_dirs(inputs_dir=inputs_dir, explicit_dirs=source_dirs)
    if not discovered:
        raise FileNotFoundError(f"no source directories found under: {inputs_dir}")

    normalized_books: List[Dict[str, Any]] = []
    normalized_interactions: List[Dict[str, Any]] = []
    seen_book_ids: set[str] = set()
    source_book_map: Dict[str, Dict[str, str]] = {}
    source_stats: Dict[str, Dict[str, int]] = {}

    for source_dir in discovered:
        source_name = source_dir.name.lower().replace(" ", "_")
        books_files, interactions_files = _discover_data_files(source_dir)
        source_book_map[source_name] = {}
        source_stats[source_name] = {
            "book_files": len(books_files),
            "interaction_files": len(interactions_files),
            "books": 0,
            "interactions": 0,
        }

        for file_path in books_files:
            for idx, row in enumerate(_iter_records(file_path), start=1):
                if max_books > 0 and len(normalized_books) >= max_books:
                    break
                normalized = _normalize_book(row, source_name, idx)
                if not normalized:
                    continue
                book_id = str(normalized["book_id"])
                if book_id in seen_book_ids:
                    continue
                seen_book_ids.add(book_id)
                source_book_id = str(normalized.get("source_book_id") or "")
                if source_book_id:
                    source_book_map[source_name][source_book_id] = book_id
                normalized_books.append(normalized)
                source_stats[source_name]["books"] += 1

        for file_path in interactions_files:
            for idx, row in enumerate(_iter_records(file_path), start=1):
                if max_interactions > 0 and len(normalized_interactions) >= max_interactions:
                    break
                normalized = _normalize_interaction(
                    row,
                    source_name,
                    raw_to_prefixed_book_id=source_book_map.get(source_name, {}),
                    fallback_index=idx,
                )
                if not normalized:
                    continue
                if str(normalized.get("book_id") or "") not in seen_book_ids:
                    continue
                normalized_interactions.append(normalized)
                source_stats[source_name]["interactions"] += 1

    books_count = _write_jsonl(out_books, normalized_books)
    interactions_count = _write_jsonl(out_interactions, normalized_interactions)

    return {
        "books_count": books_count,
        "interactions_count": interactions_count,
        "outputs": {
            "books_raw": str(out_books),
            "interactions_raw": str(out_interactions),
        },
        "sources": source_stats,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare mixed-format Chinese source datasets into unified raw JSONL files.")
    parser.add_argument("--inputs-dir", type=Path, default=DEFAULT_INPUTS_DIR)
    parser.add_argument("--source-dirs", type=Path, nargs="*", default=None)
    parser.add_argument("--out-books", type=Path, default=DEFAULT_OUT_BOOKS)
    parser.add_argument("--out-interactions", type=Path, default=DEFAULT_OUT_INTERACTIONS)
    parser.add_argument("--max-books", type=int, default=0)
    parser.add_argument("--max-interactions", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = prepare_sources(
        inputs_dir=args.inputs_dir,
        source_dirs=args.source_dirs,
        out_books=args.out_books,
        out_interactions=args.out_interactions,
        max_books=args.max_books,
        max_interactions=args.max_interactions,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
