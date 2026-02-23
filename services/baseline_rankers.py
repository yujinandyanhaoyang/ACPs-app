from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Dict, List, Sequence

from base import call_openai_chat
from services.book_retrieval import load_books, retrieve_books_by_query


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
    has_explicit_candidate_ids = bool(case_payload.get("candidate_ids")) and not bool(case_payload.get("books"))
    if has_explicit_candidate_ids:
        lexical_candidates = _normalize_books(case_payload)
    else:
        dataset_books = load_books()
        lexical_candidates = retrieve_books_by_query(
            query,
            books=dataset_books,
            top_k=max(top_k * 3, 12),
        )
    if not lexical_candidates:
        lexical_candidates = _normalize_books(case_payload)

    llm_ids = _llm_select_book_ids_sync(query, lexical_candidates, top_k=max(1, top_k))
    if not llm_ids:
        return lexical_candidates[: max(1, top_k)]

    by_id = {str(book.get("book_id") or ""): book for book in lexical_candidates}
    selected = [by_id[bid] for bid in llm_ids if bid in by_id]
    if len(selected) < max(1, top_k):
        seen = {str(book.get("book_id") or "") for book in selected}
        for candidate in lexical_candidates:
            cid = str(candidate.get("book_id") or "")
            if cid in seen:
                continue
            selected.append(candidate)
            seen.add(cid)
            if len(selected) >= max(1, top_k):
                break
    return selected[: max(1, top_k)]


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
    history_genres = _history_genres(case_payload)
    query_tokens = _query_tokens(case_payload)

    rows: List[Dict[str, Any]] = []
    for idx, book in enumerate(books):
        b_tokens = _book_tokens(book)
        overlap = len(history_genres.intersection({str(g).lower() for g in book.get("genres") or []}))
        semantic = len(query_tokens.intersection(b_tokens)) / max(1, len(query_tokens)) if query_tokens else 0.0
        popularity = _safe_float(book.get("popularity"), max(0.1, 1.0 - idx * 0.1))

        score_parts = {
            "collaborative": min(1.0, overlap / 2.0),
            "semantic": min(1.0, semantic),
            "knowledge": 0.2,
            "diversity": 0.2,
        }
        composite = (
            score_parts["collaborative"] * 0.35
            + score_parts["semantic"] * 0.35
            + score_parts["knowledge"] * 0.1
            + score_parts["diversity"] * 0.2
            + popularity * 0.1
        )
        rows.append(
            {
                "book_id": book["book_id"],
                "title": book.get("title") or book["book_id"],
                "score_parts": score_parts,
                "composite_score": round(min(1.0, composite), 4),
                "novelty_score": round(max(0.1, 0.6 - popularity * 0.3), 4),
            }
        )

    rows.sort(key=lambda item: item["composite_score"], reverse=True)
    return _attach_rank(rows[: max(1, top_k)])


def multi_agent_proxy_rank(case_payload: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
    books = _normalize_books(case_payload)
    query_tokens = _query_tokens(case_payload)

    rows: List[Dict[str, Any]] = []
    for idx, book in enumerate(books):
        b_tokens = _book_tokens(book)
        semantic = len(query_tokens.intersection(b_tokens)) / max(1, len(query_tokens)) if query_tokens else 0.0
        diversity_signal = min(1.0, 0.2 + 0.25 * len(set(str(g).lower() for g in book.get("genres") or [])))
        novelty = min(1.0, 0.25 + 0.12 * (idx + 1))

        score_parts = {
            "collaborative": 0.2,
            "semantic": min(1.0, semantic + 0.1),
            "knowledge": 0.25,
            "diversity": diversity_signal,
        }
        composite = (
            score_parts["collaborative"] * 0.15
            + score_parts["semantic"] * 0.35
            + score_parts["knowledge"] * 0.2
            + score_parts["diversity"] * 0.3
            + novelty * 0.05
        )
        rows.append(
            {
                "book_id": book["book_id"],
                "title": book.get("title") or book["book_id"],
                "score_parts": score_parts,
                "composite_score": round(min(1.0, composite), 4),
                "novelty_score": round(novelty, 4),
            }
        )

    rows.sort(key=lambda item: item["composite_score"], reverse=True)
    return _attach_rank(rows[: max(1, top_k)])


def _attach_rank(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        ranked.append({"rank": index, **row})
    return ranked
