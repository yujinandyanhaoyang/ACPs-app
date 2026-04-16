from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np

from services.data_paths import get_processed_data_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MERGED_ENRICHED_DATASET_PATH = get_processed_data_path("books_master_merged_enriched.jsonl")
MERGED_DATASET_PATH = get_processed_data_path("books_master_merged.jsonl")
BOOKS_ENRICHED_DATASET_PATH = get_processed_data_path("books_enriched.jsonl")
GOODREADS_DATASET_PATH = get_processed_data_path("goodreads", "books_master.jsonl")
BOOKS_MIN_DATASET_PATH = get_processed_data_path("books_min.jsonl")
DATASET_ENV_KEY = "BOOK_RETRIEVAL_DATASET_PATH"


def _normalize_dataset_path(path: Path) -> Path:
    if not path.is_dir():
        return path

    preferred = [
        path / "books_master_merged_enriched.jsonl",
        path / "books_master_merged.jsonl",
        path / "books_enriched.jsonl",
        path / "books_master.jsonl",
        path / "books_min.jsonl",
    ]
    for candidate in preferred:
        if candidate.exists():
            return candidate

    preferred_names = [
        "books_master_merged_enriched.jsonl",
        "books_master_merged.jsonl",
        "books_enriched.jsonl",
        "books_master.jsonl",
        "books_min.jsonl",
    ]
    for name in preferred_names:
        matches = sorted(candidate for candidate in path.rglob(name) if candidate.is_file())
        if matches:
            return matches[0]

    for candidate in sorted(path.rglob("*.jsonl")):
        if candidate.is_file():
            return candidate

    # Fallback to the standard dataset resolution chain when env path points to a directory.
    if MERGED_ENRICHED_DATASET_PATH.exists():
        return MERGED_ENRICHED_DATASET_PATH
    if MERGED_DATASET_PATH.exists():
        return MERGED_DATASET_PATH
    if BOOKS_ENRICHED_DATASET_PATH.exists():
        return BOOKS_ENRICHED_DATASET_PATH
    if GOODREADS_DATASET_PATH.exists():
        return GOODREADS_DATASET_PATH
    return BOOKS_MIN_DATASET_PATH


def _resolve_dataset_path(dataset_path: Path | None = None) -> Path:
    if dataset_path is not None:
        return _normalize_dataset_path(dataset_path)

    env_path = str(os.getenv(DATASET_ENV_KEY) or "").strip()
    if env_path:
        return _normalize_dataset_path(Path(env_path))

    if MERGED_ENRICHED_DATASET_PATH.exists():
        return MERGED_ENRICHED_DATASET_PATH
    if MERGED_DATASET_PATH.exists():
        return MERGED_DATASET_PATH
    if BOOKS_ENRICHED_DATASET_PATH.exists():
        return BOOKS_ENRICHED_DATASET_PATH
    if GOODREADS_DATASET_PATH.exists():
        return GOODREADS_DATASET_PATH
    return BOOKS_MIN_DATASET_PATH


def get_active_retrieval_corpus_info(dataset_path: Path | None = None) -> Dict[str, Any]:
    path = _resolve_dataset_path(dataset_path)
    source = "unknown"
    if dataset_path is not None:
        source = "explicit"
    elif str(os.getenv(DATASET_ENV_KEY) or "").strip():
        source = "env"
    elif path == MERGED_ENRICHED_DATASET_PATH:
        source = "merged-enriched-default"
    elif path == MERGED_DATASET_PATH:
        source = "merged-default"
    elif path == BOOKS_ENRICHED_DATASET_PATH:
        source = "books-enriched-default"
    elif path == GOODREADS_DATASET_PATH:
        source = "goodreads-default"
    elif path == BOOKS_MIN_DATASET_PATH:
        source = "books-min-fallback"

    exists = path.exists()
    return {
        "path": str(path),
        "exists": exists,
        "selection_source": source,
        "file_name": path.name,
    }


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[\w]+", text.lower(), flags=re.UNICODE) if len(tok) >= 2}


def _book_text(book: Dict[str, Any]) -> str:
    title = str(book.get("title") or "")
    description = str(book.get("description") or "")
    genres = " ".join(str(g) for g in (book.get("genres") or []))
    author = str(book.get("author") or "")
    return f"{title} {author} {description} {genres}"


def load_books(dataset_path: Path | None = None, limit: int | None = None) -> List[Dict[str, Any]]:
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
            if limit is not None and limit > 0 and len(books) >= limit:
                break
    return books


def iter_books(
    dataset_path: Path | None = None,
    offset: int = 0,
    limit: int | None = None,
):
    """Yield book dicts one at a time, skipping the first `offset` records."""
    path = _resolve_dataset_path(dataset_path)
    if not path.exists():
        return
    skipped = 0
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if skipped < offset:
                skipped += 1
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            yield row
            count += 1
            if limit is not None and limit > 0 and count >= limit:
                return


@lru_cache(maxsize=4)
def _load_vector_index(index_path: str):
    import faiss  # type: ignore

    return faiss.read_index(index_path)


@lru_cache(maxsize=4)
def _load_vector_meta(meta_path: str) -> List[Dict[str, Any]]:
    path = Path(meta_path)
    if not path.exists():
        return []

    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


@lru_cache(maxsize=1)
def _load_books_by_id() -> Dict[str, Dict[str, Any]]:
    """
    Build a lightweight book_id -> record map from the FAISS meta file
    (books_index_meta_v2.jsonl). This file is already loaded by _load_vector_meta()
    and contains book_id, title, source - enough for result enrichment without
    reading the 1.4 GB master file.
    """
    from services.data_paths import get_processed_data_root

    env_meta = str(os.getenv("FAISS_INDEX_META_PATH") or "").strip()
    if env_meta:
        meta_path = Path(env_meta)
    else:
        meta_path = get_processed_data_root() / "books_index_meta_v2.jsonl"

    books: Dict[str, Dict[str, Any]] = {}
    if not meta_path.exists():
        return books

    with meta_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            book_id = str(row.get("book_id") or row.get("id") or "").strip()
            if not book_id or book_id in books:
                continue
            books[book_id] = dict(row)
    return books


def _normalize_query_embedding(query_embedding: Sequence[float], dim: int) -> np.ndarray:
    vector = np.asarray(list(query_embedding), dtype=np.float32).reshape(-1)
    if vector.size == 0:
        vector = np.zeros((dim,), dtype=np.float32)
    if vector.size < dim:
        padded = np.zeros((dim,), dtype=np.float32)
        padded[: vector.size] = vector
        vector = padded
    elif vector.size > dim:
        vector = vector[:dim]
    norm = float(np.linalg.norm(vector))
    if norm > 0.0:
        vector = vector / norm
    return vector.reshape(1, dim)


def retrieve_books_by_vector(
    query_embedding: List[float],
    top_k: int = 100,
    index_path: Path | None = None,
    meta_path: Path | None = None,
) -> List[Dict[str, Any]]:
    """
    Given a 384-dim query embedding, return top_k candidate books
    from the FAISS index with their full metadata loaded from
    books_master_merged.jsonl.
    """

    if top_k <= 0:
        top_k = 1

    # Prefer explicit env vars (declared in .env.example)
    env_index = str(os.getenv("FAISS_INDEX_PATH") or "").strip()
    env_meta = str(os.getenv("FAISS_INDEX_META_PATH") or "").strip()
    if env_index and env_meta:
        default_index_path = Path(env_index)
        default_meta_path = Path(env_meta)
    else:
        # Fallback: derive from DATASET_ROOT or PROCESSED_DATA_ROOT
        from services.data_paths import get_processed_data_root

        proc_root = get_processed_data_root()
        default_index_path = proc_root / "books_index_v2.faiss"
        default_meta_path = proc_root / "books_index_meta_v2.jsonl"

    resolved_index_path = Path(index_path) if index_path is not None else default_index_path
    resolved_meta_path = Path(meta_path) if meta_path is not None else default_meta_path

    if not resolved_index_path.exists() or not resolved_meta_path.exists():
        return []

    index = _load_vector_index(str(resolved_index_path))
    dim = int(getattr(index, "dim", len(query_embedding) or 0))
    if dim <= 0:
        return []

    query = _normalize_query_embedding(query_embedding, dim)
    scores, indices = index.search(query, top_k)
    meta_rows = _load_vector_meta(str(resolved_meta_path))
    books_by_id = _load_books_by_id()

    results: List[Dict[str, Any]] = []
    row_scores = scores[0].tolist() if len(scores) else []
    row_indices = indices[0].tolist() if len(indices) else []
    for score, idx in zip(row_scores, row_indices):
        if int(idx) < 0:
            continue
        meta = meta_rows[int(idx)] if int(idx) < len(meta_rows) else None
        if not meta:
            continue
        book_id = str(meta.get("book_id") or "").strip()
        record = dict(books_by_id.get(book_id, {}))
        if not record:
            record = {
                "book_id": book_id,
                "source": str(meta.get("source") or ""),
                "title": str(meta.get("title") or ""),
            }
        record.setdefault("book_id", book_id)
        record.setdefault("source", str(meta.get("source") or ""))
        record.setdefault("title", str(meta.get("title") or ""))
        record["score"] = float(score)
        record["index"] = int(idx)
        results.append(record)
    return results


def retrieve_books_by_query(
    query: str,
    search_query: str | None = None,
    books: Sequence[Dict[str, Any]] | None = None,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    # Fast path: if we have a FAISS index and can embed the query, use vector recall
    # instead of a full-corpus keyword scan.
    effective_query = str(search_query or query or "").strip()
    if query and books is None:
        try:
            from services.model_backends import generate_text_embeddings, _DEFAULT_OFFLINE_EMBED_MODEL

            model_name = os.getenv("BOOK_CONTENT_EMBED_MODEL_PATH") or _DEFAULT_OFFLINE_EMBED_MODEL
            if (not search_query or not str(search_query).strip()) and any("\u4e00" <= ch <= "\u9fff" for ch in str(query or "")):
                logger.warning("event=query_translation_missing fallback=original_query")
            vectors, meta = generate_text_embeddings([effective_query or query], model_name)
            if vectors and vectors[0]:
                results = retrieve_books_by_vector(vectors[0], top_k=top_k)
                if results:
                    return results
        except Exception:
            pass

    pool = list(books) if books is not None else load_books()
    if not pool:
        return []

    q_tokens = _tokenize(effective_query or query or "")
    if not q_tokens:
        return [dict(item) for item in pool[: max(1, top_k)]]

    query_seed = sum(ord(ch) for ch in effective_query or query or "")
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
        tie_breaker = (((query_seed + idx * 17) % 997) / 997000.0)
        score = coverage + min(0.15, genre_bonus) + 0.001 * (1.0 - idx / max(1, len(pool))) + tie_breaker
        scored.append((score, book))

    scored.sort(key=lambda row: row[0], reverse=True)
    return [dict(book) for _, book in scored[: max(1, top_k)]]
