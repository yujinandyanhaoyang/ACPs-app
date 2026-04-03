from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore


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
    for key in ["vector256", "vector", "content_vector", "embedding"]:
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
        item.setdefault("title", book_id)
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


def _cf_recall_fallback(
    candidates: List[Dict[str, Any]],
    profile_vector: List[float],
    top_k: int,
    als_model_path: Path,
) -> List[Dict[str, Any]]:
    if np is None:
        return []

    # Optional ALS item factor support. If unavailable, use candidate-provided cf score fallback.
    item_index_path = als_model_path.parent / "cf_book_id_index.json"
    index_map = _load_json(item_index_path)
    item_factors_path = als_model_path.parent / "cf_item_factors.npy"

    factors = None
    if item_factors_path.exists():
        try:
            factors = np.load(item_factors_path, allow_pickle=False)
        except Exception:
            factors = None

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for row in candidates:
        book_id = str(row.get("book_id") or "")
        cf_score = _safe_float(row.get("cf_score"), 0.0)

        if factors is not None and isinstance(index_map, dict) and profile_vector:
            try:
                idx = int(index_map.get(book_id, -1))
            except Exception:
                idx = -1
            if idx >= 0 and idx < int(factors.shape[0]):
                item_vec = factors[idx].tolist()
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

    total = max(ann_weight + cf_weight, 1e-9)
    ann_weight = ann_weight / total
    cf_weight = cf_weight / total

    profile_vector = payload.get("profile_vector") if isinstance(payload.get("profile_vector"), list) else []
    profile_vector = [_safe_float(v) for v in profile_vector]

    ann_top_k = int(cfg.get("ann_top_k") or 200)
    cf_top_k = int(cfg.get("cf_top_k") or 100)

    als_model_path = Path(str(cfg.get("als_model_path") or "data/als_model.npz"))
    if not als_model_path.is_absolute():
        als_model_path = Path.cwd() / als_model_path

    ann_rows = _ann_recall_fallback(candidates, profile_vector, top_k=ann_top_k)
    cf_rows = _cf_recall_fallback(candidates, profile_vector, top_k=cf_top_k, als_model_path=als_model_path)

    merged = _merge_ann_cf(ann_rows, cf_rows, ann_weight=ann_weight, cf_weight=cf_weight)

    meta = {
        "ann_top_k": ann_top_k,
        "cf_top_k": cf_top_k,
        "ann_candidates": len(ann_rows),
        "cf_candidates": len(cf_rows),
        "merged_candidates": len(merged),
        "ann_weight": round(ann_weight, 6),
        "cf_weight": round(cf_weight, 6),
        "ann_runtime": {
            "index_path": str(cfg.get("faiss_index_path") or ""),
            "ef_search": int(cfg.get("ann_ef_search") or 100),
            "mode": "fallback_vector_cosine",
        },
        "cf_runtime": {
            "als_model_path": str(als_model_path),
            "user_sim_path": str(cfg.get("hnswlib_path") or ""),
            "mode": "fallback_item_factor_similarity",
            "similar_users_k": int(cfg.get("cf_sim_users") or 50),
        },
    }
    return merged, meta
