from __future__ import annotations

from typing import Any, Dict, List, Sequence


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
