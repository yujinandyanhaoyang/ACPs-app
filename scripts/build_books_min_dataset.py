from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from services.data_paths import get_raw_data_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = get_raw_data_path("books_min_sample.jsonl")
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "books_min.jsonl"


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_genres(value: Any) -> List[str]:
    genres: List[str] = []
    if isinstance(value, list):
        source = value
    elif isinstance(value, str):
        source = [value]
    else:
        source = []

    for item in source:
        token = _clean_text(item).lower().replace(" ", "_")
        if token:
            genres.append(token)

    deduped: List[str] = []
    seen = set()
    for genre in genres:
        if genre not in seen:
            deduped.append(genre)
            seen.add(genre)
    return deduped


def _normalize_row(row: Dict[str, Any], fallback_idx: int) -> Dict[str, Any] | None:
    title = _clean_text(row.get("title"))
    if not title:
        return None

    book_id = _clean_text(row.get("book_id") or row.get("id") or f"book_{fallback_idx}")
    if not book_id:
        return None

    normalized = {
        "book_id": book_id,
        "title": title,
        "author": _clean_text(row.get("author")) or "Unknown",
        "description": _clean_text(row.get("description")),
        "genres": _normalize_genres(row.get("genres")),
        "source": _clean_text(row.get("source")) or "unknown",
    }
    return normalized


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def build_dataset(raw_path: Path = RAW_PATH, out_path: Path = OUT_PATH) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    seen_ids = set()
    count = 0
    with out_path.open("w", encoding="utf-8") as out_file:
        for idx, row in enumerate(_iter_jsonl(raw_path), start=1):
            normalized = _normalize_row(row, idx)
            if not normalized:
                continue
            if normalized["book_id"] in seen_ids:
                continue
            seen_ids.add(normalized["book_id"])
            out_file.write(json.dumps(normalized, ensure_ascii=False) + "\n")
            count += 1
    return count


if __name__ == "__main__":
    total = build_dataset()
    print(f"built dataset: {total} records -> {OUT_PATH}")
