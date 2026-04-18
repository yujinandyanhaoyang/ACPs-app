from __future__ import annotations

import json
import os
import math
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore


logger = logging.getLogger(__name__)
_BOOK_META_CACHE: Dict[str, Dict[str, Any]] | None = None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _norm(vec: List[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


def _cosine(left: List[float], right: List[float]) -> float:
    size = min(len(left), len(right))
    if size <= 0:
        return 0.0
    dot = sum(left[i] * right[i] for i in range(size))
    ln = _norm(left[:size])
    rn = _norm(right[:size])
    if ln <= 0 or rn <= 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (ln * rn)))


def _extract_vector(row: Dict[str, Any]) -> List[float]:
    for key in ["vector384", "vector_384", "vector256", "vector", "content_vector", "embedding"]:
        raw = row.get(key)
        if isinstance(raw, list):
            return [_safe_float(v) for v in raw]
    return []


def _normalize_candidates(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        book_id = str(row.get("book_id") or row.get("id") or f"book_{idx}").strip()
        if not book_id:
            continue
        item = dict(row)
        item["book_id"] = book_id
        if not str(item.get("title") or "").strip():
            item["title"] = ""
        if not str(item.get("author") or "").strip():
            item["author"] = ""
        if not isinstance(item.get("genres"), list):
            item["genres"] = []
        if not str(item.get("description") or "").strip():
            item["description"] = ""
        item["_vector"] = _extract_vector(item)
        out.append(item)
    return out


def _ann_recall_fallback(
    candidates: List[Dict[str, Any]],
    profile_vector: List[float],
    top_k: int,
) -> List[Dict[str, Any]]:
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for row in candidates:
        content_sim = _cosine(profile_vector, row.get("_vector") or []) if profile_vector else 0.0
        enriched = dict(row)
        enriched["content_sim"] = round(max(0.0, content_sim), 6)
        enriched["recall_source"] = "ann"
        scored.append((enriched["content_sim"], enriched))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in scored[: max(1, top_k)]]


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_metadata_path() -> Path | None:
    root = str(os.getenv("BOOK_RETRIEVAL_DATASET_PATH") or "").strip()
    if not root:
        return None
    base = Path(root)

    # 当 env 指向文件本身时直接返回
    if base.is_file() and base.suffix == ".jsonl":
        return base

    # 当 env 指向目录时，按优先级查找
    candidates = [
        base / "processed" / "books_master_merged.jsonl",
        base / "processed" / "books_enriched.jsonl",
        base / "processed" / "goodreads" / "books_master.jsonl",
        base / "processed" / "books_min.jsonl",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    logger.warning("event=metadata_source_missing root=%s", root)
    return None


def _load_book_metadata() -> Dict[str, Dict[str, Any]]:
    global _BOOK_META_CACHE
    if _BOOK_META_CACHE is not None:
        return _BOOK_META_CACHE

    # Preferred source: stream the configured books corpus and cache full
    # metadata so author/genres/description remain available downstream.
    try:
        from services.book_retrieval import iter_books

        meta: Dict[str, Dict[str, Any]] = {}
        for row in iter_books():
            if not isinstance(row, dict):
                continue
            book_id = str(row.get("book_id") or "").strip()
            if not book_id or book_id in meta:
                continue
            meta[book_id] = {
                "book_id": book_id,
                "title": str(row.get("title") or ""),
                "author": str(row.get("author") or ""),
                "genres": row.get("genres") if isinstance(row.get("genres"), list) else [],
                "description": str(row.get("description") or row.get("blurb") or ""),
                "source": str(row.get("source") or ""),
            }
        if meta:
            _BOOK_META_CACHE = meta
            logger.info(
                "event=metadata_loaded_from_corpus count=%d", len(meta)
            )
            return _BOOK_META_CACHE
    except Exception as exc:
        logger.warning(
            "event=metadata_load_from_corpus_failed error=%s", exc
        )

    # Hard fallback: read FAISS meta file directly.
    try:
        from services.data_paths import get_processed_data_root
        env_meta = str(os.getenv("FAISS_INDEX_META_PATH") or "").strip()
        meta_path = Path(env_meta) if env_meta else (
            get_processed_data_root() / "books_index_meta_v2.jsonl"
        )
        meta: Dict[str, Dict[str, Any]] = {}
        if meta_path.exists():
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
                    book_id = str(row.get("book_id") or "").strip()
                    if book_id:
                        meta[book_id] = row
        _BOOK_META_CACHE = meta
        logger.info(
            "event=metadata_loaded_via_faiss_meta count=%d", len(meta)
        )
    except Exception as exc:
        logger.warning("event=metadata_load_fallback_failed error=%s", exc)
        _BOOK_META_CACHE = {}

    return _BOOK_META_CACHE


def _enrich_candidates_with_metadata(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    book_meta = _load_book_metadata()
    if not book_meta:
        return candidates

    enriched_count = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        book_id = str(candidate.get("book_id") or "").strip()
        if not book_id:
            continue
        meta = book_meta.get(book_id)
        if not meta:
            continue

        before = dict(candidate)
        if not str(candidate.get("title") or "").strip():
            candidate["title"] = meta.get("title") or candidate.get("title")
        if not str(candidate.get("author") or "").strip():
            candidate["author"] = meta.get("author") or ""
        if not isinstance(candidate.get("genres"), list) or not candidate.get("genres"):
            candidate["genres"] = meta.get("genres") or []
        if not str(candidate.get("description") or "").strip():
            candidate["description"] = meta.get("description") or meta.get("blurb") or ""

        if candidate != before:
            enriched_count += 1

    logger.info("event=metadata_enriched total=%d enriched=%d", len(candidates), enriched_count)
    return candidates


def _cf_recall_fallback(
    candidates: List[Dict[str, Any]],
    profile_vector: List[float],
    top_k: int,
) -> List[Dict[str, Any]]:
    if np is None:
        return []

    try:
        from services.model_backends import load_cf_item_vectors

        cf_vectors = load_cf_item_vectors(force_reload=False)
    except Exception:
        cf_vectors = {}

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for row in candidates:
        book_id = str(row.get("book_id") or "")
        cf_score = _safe_float(row.get("cf_score"), 0.0)

        item_vec = cf_vectors.get(book_id)
        if item_vec and profile_vector:
            cf_score = max(cf_score, max(0.0, _cosine(profile_vector, [_safe_float(v) for v in item_vec])))

        enriched = dict(row)
        enriched["cf_score"] = round(max(0.0, cf_score), 6)
        enriched["recall_source"] = "cf"
        scored.append((enriched["cf_score"], enriched))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in scored[: max(1, top_k)]]


def _merge_ann_cf(
    ann_rows: List[Dict[str, Any]],
    cf_rows: List[Dict[str, Any]],
    ann_weight: float,
    cf_weight: float,
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for row in ann_rows:
        book_id = str(row.get("book_id"))
        if not book_id:
            continue
        item = dict(row)
        item.setdefault("content_sim", 0.0)
        item.setdefault("cf_score", 0.0)
        item["_ann_seen"] = True
        merged[book_id] = item

    for row in cf_rows:
        book_id = str(row.get("book_id"))
        if not book_id:
            continue
        existing = merged.get(book_id)
        if existing is None:
            item = dict(row)
            item.setdefault("content_sim", 0.0)
            item.setdefault("cf_score", 0.0)
            item["_cf_seen"] = True
            merged[book_id] = item
            continue
        existing["cf_score"] = max(_safe_float(existing.get("cf_score"), 0.0), _safe_float(row.get("cf_score"), 0.0))
        existing["_cf_seen"] = True

    out: List[Dict[str, Any]] = []
    for row in merged.values():
        ann_seen = bool(row.pop("_ann_seen", False))
        cf_seen = bool(row.pop("_cf_seen", False))
        if ann_seen and cf_seen:
            row["recall_source"] = "both"
        elif ann_seen:
            row["recall_source"] = "ann"
        else:
            row["recall_source"] = "cf"

        content_sim = _safe_float(row.get("content_sim"), 0.0)
        cf_score = _safe_float(row.get("cf_score"), 0.0)
        row["merged_recall_score"] = round((ann_weight * content_sim) + (cf_weight * cf_score), 6)
        out.append(row)

    out.sort(key=lambda x: _safe_float(x.get("merged_recall_score"), 0.0), reverse=True)
    return out


def recall_candidates(payload: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    candidates = _normalize_candidates(payload)
    ann_weight = _safe_float(payload.get("ann_weight"), 0.6)
    cf_weight = _safe_float(payload.get("cf_weight"), 0.4)
    cold_start = bool(payload.get("cold_start", False))
    intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}
    search_query = str(payload.get("search_query") or intent.get("search_query") or "").strip()

    total = max(ann_weight + cf_weight, 1e-9)
    ann_weight = ann_weight / total
    cf_weight = cf_weight / total

    profile_vector = payload.get("profile_vector") if isinstance(payload.get("profile_vector"), list) else []
    profile_vector = [_safe_float(v) for v in profile_vector]

    ann_top_k = int(cfg.get("ann_top_k") or 200)
    cf_top_k = int(cfg.get("cf_top_k") or 100)

    faiss_index_path = Path(str(cfg.get("faiss_index_path") or ""))
    faiss_index_meta_path = Path(str(cfg.get("faiss_index_meta_path") or ""))
    cf_item_factors_path = Path(str(cfg.get("cf_item_factors_path") or ""))
    cf_book_index_path = Path(str(cfg.get("cf_book_index_path") or ""))
    cf_user_factors_path = Path(str(cfg.get("cf_user_factors_path") or ""))
    cf_user_index_path = Path(str(cfg.get("cf_user_index_path") or ""))

    meta = {
        "backend": str(cfg.get("embed_backend") or ""),
        "vector_dim": int(cfg.get("vector_dim") or 0),
    }
    logger.info(
        "event=ann_query search_query=%r embed_backend=%s vector_dim=%d",
        search_query,
        meta.get("backend"),
        meta.get("vector_dim", 0),
    )

    ann_rows = _ann_recall_fallback(candidates, profile_vector, top_k=ann_top_k)
    cf_rows = [] if cold_start else _cf_recall_fallback(candidates, profile_vector, top_k=cf_top_k)

    merged = _merge_ann_cf(ann_rows, cf_rows, ann_weight=ann_weight, cf_weight=cf_weight)
    if cold_start:
        for row in merged:
            row["cf_score"] = 0.0
            row["merged_recall_score"] = round((ann_weight * _safe_float(row.get("content_sim"), 0.0)), 6)
    merged = _enrich_candidates_with_metadata(merged)

    ann_mode = "vector_cosine" if faiss_index_path.exists() and faiss_index_meta_path.exists() else "fallback_vector_cosine"
    cf_mode = "item_factor_similarity" if cf_item_factors_path.exists() and cf_book_index_path.exists() else "fallback_item_factor_similarity"

    meta = {
        "ann_top_k": ann_top_k,
        "cf_top_k": cf_top_k,
        "ann_candidates": len(ann_rows),
        "cf_candidates": len(cf_rows),
        "merged_candidates": len(merged),
        "ann_weight": round(ann_weight, 6),
        "cf_weight": round(cf_weight, 6),
        "ann_runtime": {
            "index_path": str(faiss_index_path or ""),
            "meta_path": str(faiss_index_meta_path or ""),
            "book_corpus_path": str(cfg.get("book_retrieval_dataset_path") or ""),
            "ef_search": int(cfg.get("ann_ef_search") or 100),
            "mode": ann_mode,
        },
        "cf_runtime": {
            "item_factors_path": str(cf_item_factors_path or ""),
            "book_index_path": str(cf_book_index_path or ""),
            "user_factors_path": str(cf_user_factors_path or ""),
            "user_index_path": str(cf_user_index_path or ""),
            "mode": cf_mode,
            "similar_users_k": int(cfg.get("cf_sim_users") or 50),
        },
        "cold_start": bool(cold_start),
        "embed_backend": meta["backend"],
        "vector_dim": meta["vector_dim"],
    }
    return merged, meta
