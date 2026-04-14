from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence

from base import call_openai_chat
from services.book_retrieval import load_books, retrieve_books_by_query
from services.data_paths import get_processed_data_path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_INTERACTIONS_TRAIN_PATH = get_processed_data_path("merged", "interactions_merged.jsonl")
_POPULARITY_COUNTS_CACHE: Dict[str, int] | None = None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_books(case_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    books = case_payload.get("books") or []
    normalized: List[Dict[str, Any]] = []

    if isinstance(books, list) and books:
        for index, item in enumerate(books):
            if not isinstance(item, dict):
                continue
            book_id = str(item.get("book_id") or item.get("id") or f"book_{index}")
            normalized.append({**item, "book_id": book_id})

    if normalized:
        return normalized

    for index, cid in enumerate(case_payload.get("candidate_ids") or []):
        normalized.append(
            {
                "book_id": str(cid),
                "title": str(cid),
                "description": str(case_payload.get("query") or ""),
                "genres": [],
                "popularity": max(0.1, 1.0 - index * 0.1),
            }
        )
    return normalized


def _safe_json_loads(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def _llm_select_book_ids_sync(query: str, candidates: List[Dict[str, Any]], top_k: int) -> List[str]:
    if not query.strip() or not candidates or not os.getenv("OPENAI_API_KEY"):
        return []
    model = os.getenv("OPENAI_MODEL", "qwen-plus")
    rows = []
    for book in candidates[:40]:
        rows.append(
            {
                "book_id": book.get("book_id"),
                "title": book.get("title"),
                "author": book.get("author"),
                "genres": book.get("genres") or [],
                "description": str(book.get("description") or "")[:180],
            }
        )
    prompt = (
        "Select the best matching books for the user query from the provided candidates. "
        "Return strict JSON only: {\"book_ids\": [\"...\"]}.\n"
        f"query: {query}\n"
        f"top_k: {max(1, top_k)}\n"
        f"candidates: {json.dumps(rows, ensure_ascii=False)}"
    )
    try:
        asyncio.get_running_loop()
        return []
    except RuntimeError:
        raw = asyncio.run(
            call_openai_chat(
                [
                    {"role": "system", "content": "You select candidate book IDs for retrieval."},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=0.1,
                max_tokens=256,
            )
        )
    if not isinstance(raw, str):
        return []
    payload = _safe_json_loads(raw)
    ids = payload.get("book_ids")
    if not isinstance(ids, list):
        return []
    cleaned: List[str] = []
    seen: set[str] = set()
    for value in ids:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
        if len(cleaned) >= max(1, top_k):
            break
    return cleaned


def _retrieve_baseline_candidate_pool(case_payload: Dict[str, Any], top_k: int) -> List[Dict[str, Any]]:
    query = str(case_payload.get("query") or "")
    inline_books = _normalize_books(case_payload)
    if inline_books:
        return inline_books[: max(1, top_k)]
    explicit_candidate_ids = [str(item or "").strip() for item in (case_payload.get("candidate_ids") or []) if str(item or "").strip()]
    dataset_books = load_books()

    if explicit_candidate_ids:
        id_set = set(explicit_candidate_ids)
        filtered = [row for row in dataset_books if str((row or {}).get("book_id") or "") in id_set]
        if filtered:
            return filtered[: max(1, top_k)]
        return _normalize_books(case_payload)[: max(1, top_k)]

    lexical_candidates = retrieve_books_by_query(
        query,
        books=dataset_books,
        top_k=max(top_k * 3, 12),
    )
    if not lexical_candidates:
        lexical_candidates = _normalize_books(case_payload)

    return lexical_candidates[: max(1, top_k)]


def _load_popularity_counts() -> Dict[str, int]:
    global _POPULARITY_COUNTS_CACHE
    if _POPULARITY_COUNTS_CACHE is not None:
        return _POPULARITY_COUNTS_CACHE

    counts: Dict[str, int] = {}
    if _INTERACTIONS_TRAIN_PATH.exists():
        with _INTERACTIONS_TRAIN_PATH.open("r", encoding="utf-8") as f:
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
                book_id = str(row.get("book_id") or "").strip()
                if not book_id:
                    continue
                counts[book_id] = counts.get(book_id, 0) + 1

    _POPULARITY_COUNTS_CACHE = counts
    return _POPULARITY_COUNTS_CACHE


def _history_genres(case_payload: Dict[str, Any]) -> set[str]:
    genres: set[str] = set()
    for row in case_payload.get("history") or []:
        if not isinstance(row, dict):
            continue
        for item in row.get("genres") or []:
            token = str(item or "").strip().lower()
            if token:
                genres.add(token)
    return genres


def _query_tokens(case_payload: Dict[str, Any]) -> set[str]:
    query = str(case_payload.get("query") or "").lower()
    return {tok for tok in query.replace("-", " ").split() if tok}


def _book_tokens(book: Dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    title = str(book.get("title") or "").lower()
    desc = str(book.get("description") or "").lower()
    for source in (title, desc):
        tokens.update(tok for tok in source.replace("-", " ").split() if tok)
    for genre in book.get("genres") or []:
        token = str(genre or "").strip().lower()
        if token:
            tokens.add(token)
    return tokens


def traditional_hybrid_rank(case_payload: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
    books = _retrieve_baseline_candidate_pool(case_payload, top_k=max(1, top_k))
    if not books:
        books = _normalize_books(case_payload)
    query_tokens = _query_tokens(case_payload)
    popularity_counts = _load_popularity_counts()

    # Popularity: log(1 + rating_count), normalized within candidate pool
    raw_popularity: Dict[str, float] = {}
    for idx, book in enumerate(books):
        book_id = str(book.get("book_id") or "")
        rating_count = popularity_counts.get(book_id)
        if rating_count is None:
            # fallback to optional provided popularity hint / stable floor
            hint = _safe_float(book.get("popularity"), max(0.1, 1.0 - idx * 0.05))
            raw_popularity[book_id] = max(0.0, hint)
        else:
            raw_popularity[book_id] = math.log1p(max(0, int(rating_count)))

    pop_values = list(raw_popularity.values())
    pop_min = min(pop_values) if pop_values else 0.0
    pop_max = max(pop_values) if pop_values else 0.0
    pop_span = max(pop_max - pop_min, 1e-8)

    rows: List[Dict[str, Any]] = []
    for book in books:
        book_id = str(book.get("book_id") or "")
        b_tokens = _book_tokens(book)
        content_similarity = (
            len(query_tokens.intersection(b_tokens)) / max(1, len(query_tokens)) if query_tokens else 0.0
        )
        popularity_score = (raw_popularity.get(book_id, 0.0) - pop_min) / pop_span
        hybrid_score = 0.5 * popularity_score + 0.5 * content_similarity

        score_parts = {
            "collaborative": round(min(1.0, popularity_score), 4),
            "semantic": round(min(1.0, content_similarity), 4),
            "knowledge": 0.0,
            "diversity": 0.0,
        }
        rows.append(
            {
                "book_id": book_id,
                "title": book.get("title") or book_id,
                "score_parts": score_parts,
                "composite_score": round(min(1.0, hybrid_score), 4),
                "novelty_score": round(max(0.1, 1.0 - popularity_score), 4),
            }
        )

    rows.sort(key=lambda item: item["composite_score"], reverse=True)
    return _attach_rank(rows[: max(1, top_k)])


def multi_agent_proxy_rank(case_payload: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
    rows = traditional_hybrid_rank(case_payload, top_k=top_k)
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item.setdefault("score_diversity", _safe_float(item.get("novelty_score"), 0.0))
        normalized.append(item)
    return normalized


def llm_only_rank(case_payload: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
    query = str(case_payload.get("query") or "")
    candidate_pool = _retrieve_baseline_candidate_pool(case_payload, max(top_k * 3, 15))
    if not candidate_pool:
        candidate_pool = _normalize_books(case_payload)

    llm_ids = _llm_select_book_ids_sync(query, candidate_pool, top_k=max(1, top_k))
    by_id = {str(row.get("book_id") or ""): row for row in candidate_pool}

    selected: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for book_id in llm_ids:
        if book_id in seen or book_id not in by_id:
            continue
        selected.append(by_id[book_id])
        seen.add(book_id)
        if len(selected) >= max(1, top_k):
            break

    if len(selected) < max(1, top_k):
        for row in candidate_pool:
            book_id = str(row.get("book_id") or "")
            if not book_id or book_id in seen:
                continue
            selected.append(row)
            seen.add(book_id)
            if len(selected) >= max(1, top_k):
                break

    ranked: List[Dict[str, Any]] = []
    for row in selected[: max(1, top_k)]:
        book_id = str(row.get("book_id") or "")
        ranked.append(
            {
                "book_id": book_id,
                "title": row.get("title") or book_id,
                "score_parts": {
                    "collaborative": 0.0,
                    "semantic": 1.0,
                    "knowledge": 0.0,
                    "diversity": 0.0,
                },
                "composite_score": 1.0,
                "novelty_score": 0.5,
            }
        )
    return _attach_rank(ranked)


def _attach_rank(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        ranked.append({"rank": index, **row})
    return ranked
