from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOODREADS_DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "goodreads" / "books_master.jsonl"
BOOKS_MIN_DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "books_min.jsonl"
DATASET_ENV_KEY = "BOOK_RETRIEVAL_DATASET_PATH"


def _resolve_dataset_path(dataset_path: Path | None = None) -> Path:
    if dataset_path is not None:
        return dataset_path

    env_path = str(os.getenv(DATASET_ENV_KEY) or "").strip()
    if env_path:
        return Path(env_path)

    if GOODREADS_DATASET_PATH.exists():
        return GOODREADS_DATASET_PATH
    return BOOKS_MIN_DATASET_PATH


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[\w]+", text.lower(), flags=re.UNICODE) if len(tok) >= 2}


def _book_text(book: Dict[str, Any]) -> str:
    title = str(book.get("title") or "")
    description = str(book.get("description") or "")
    genres = " ".join(str(g) for g in (book.get("genres") or []))
    author = str(book.get("author") or "")
    return f"{title} {author} {description} {genres}"


def load_books(dataset_path: Path | None = None) -> List[Dict[str, Any]]:
    path = _resolve_dataset_path(dataset_path)
    if not path.exists():
        return []

    books: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            books.append(row)
    return books


def retrieve_books_by_query(
    query: str,
    books: Sequence[Dict[str, Any]] | None = None,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    pool = list(books) if books is not None else load_books()
    if not pool:
        return []

    q_tokens = _tokenize(query or "")
    if not q_tokens:
        return [dict(item) for item in pool[: max(1, top_k)]]

    scored: List[tuple[float, Dict[str, Any]]] = []
    for idx, book in enumerate(pool):
        tokens = _tokenize(_book_text(book))
        overlap = len(q_tokens.intersection(tokens))
        coverage = overlap / max(1, len(q_tokens))
        genre_bonus = 0.0
        for genre in book.get("genres") or []:
            g = str(genre).replace("_", " ").lower()
            if any(part in q_tokens for part in g.split()):
                genre_bonus += 0.05
        score = coverage + min(0.15, genre_bonus) + max(0.0, 0.001 * (len(pool) - idx))
        scored.append((score, book))

    scored.sort(key=lambda row: row[0], reverse=True)
    return [dict(book) for _, book in scored[: max(1, top_k)]]
