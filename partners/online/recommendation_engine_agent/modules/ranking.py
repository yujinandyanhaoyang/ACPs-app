from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _cosine(left: List[float], right: List[float]) -> float:
    size = min(len(left), len(right))
    if size <= 0:
        return 0.0
    dot = sum(left[i] * right[i] for i in range(size))
    ln = math.sqrt(sum(left[i] * left[i] for i in range(size)))
    rn = math.sqrt(sum(right[i] * right[i] for i in range(size)))
    if ln <= 0.0 or rn <= 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (ln * rn)))


def _normalize_weights(score_weights: Dict[str, Any]) -> Dict[str, float]:
    raw = {
        "content": _safe_float(score_weights.get("content"), 0.4),
        "cf": _safe_float(score_weights.get("cf"), 0.3),
        "novelty": _safe_float(score_weights.get("novelty"), 0.2),
        "recency": _safe_float(score_weights.get("recency"), 0.1),
    }
    clipped = {k: max(0.0, v) for k, v in raw.items()}
    total = sum(clipped.values())
    if total <= 0.0:
        return {"content": 0.4, "cf": 0.3, "novelty": 0.2, "recency": 0.1}
    return {k: v / total for k, v in clipped.items()}


def _extract_vector(row: Dict[str, Any]) -> List[float]:
    for key in ["_vector", "vector256", "vector", "content_vector", "embedding"]:
        raw = row.get(key)
        if isinstance(raw, list):
            return [_safe_float(v) for v in raw]
    return []


def _recency_score(row: Dict[str, Any]) -> float:
    year = row.get("published_year")
    if year is None:
        return _safe_float(row.get("recency"), 0.5)
    y = int(_safe_float(year, 0.0))
    if y <= 0:
        return 0.5
    # Soft normalization: books newer than 2020 trend toward high recency.
    return max(0.0, min(1.0, (y - 1990) / 40.0))


def score_round1(candidates: List[Dict[str, Any]], score_weights: Dict[str, Any], top_k: int = 50) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    weights = _normalize_weights(score_weights or {})
    scored: List[Dict[str, Any]] = []
    genre_freq: Dict[str, int] = {}
    for row in candidates:
        raw = row.get("genres")
        if not isinstance(raw, list):
            continue
        for g in raw:
            token = str(g).strip().lower()
            if token:
                genre_freq[token] = genre_freq.get(token, 0) + 1

    for row in candidates:
        content = _safe_float(row.get("content_sim"), 0.0)
        cf = _safe_float(row.get("cf_score"), 0.0)
        novelty = _safe_float(row.get("novelty_score"), max(0.0, 1.0 - content))
        raw_genres = row.get("genres")
        genres = raw_genres if isinstance(raw_genres, list) else []
        if genres:
            rarity = []
            for g in genres:
                token = str(g).strip().lower()
                if token:
                    rarity.append(1.0 / max(1.0, float(genre_freq.get(token, 1))))
            diversity = max(0.0, min(1.0, sum(rarity) / max(1, len(rarity)))) if rarity else novelty
        else:
            diversity = novelty
        recency = _recency_score(row)

        s = (
            (weights["content"] * content)
            + (weights["cf"] * cf)
            + (weights["novelty"] * ((novelty + diversity) / 2.0))
            + (weights["recency"] * recency)
        )

        item = dict(row)
        item["score_parts"] = {
            "content": round(content, 6),
            "cf": round(cf, 6),
            "novelty": round(novelty, 6),
            "diversity": round(diversity, 6),
            "recency": round(recency, 6),
        }
        item["novelty_score"] = round(novelty, 6)
        item["diversity_score"] = round(diversity, 6)
        item["score_round1"] = round(s, 6)
        item["_vector"] = _extract_vector(item)
        scored.append(item)

    scored.sort(key=lambda x: _safe_float(x.get("score_round1"), 0.0), reverse=True)
    selected = scored[: max(1, int(top_k))]

    meta = {
        "weights": {k: round(v, 6) for k, v in weights.items()},
        "candidate_count": len(candidates),
        "selected_count": len(selected),
    }
    return selected, meta


def rerank_round2(
    preliminary_list: List[Dict[str, Any]],
    confidence_list: Dict[str, float],
    mmr_lambda: float,
    confidence_penalty_threshold: float,
    penalty_multiplier: float,
    top_k: int = 5,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    lam = max(0.0, min(1.0, _safe_float(mmr_lambda, 0.5)))
    threshold = max(0.0, min(1.0, _safe_float(confidence_penalty_threshold, 0.6)))
    penalty = max(0.0, min(1.0, _safe_float(penalty_multiplier, 0.7)))

    pool: List[Dict[str, Any]] = []
    penalty_count = 0
    for row in preliminary_list:
        book_id = str(row.get("book_id") or "")
        conf = _safe_float(confidence_list.get(book_id), 0.0)
        base = _safe_float(row.get("score_round1"), 0.0)

        adjusted = base
        if conf < threshold:
            adjusted = adjusted * penalty
            penalty_count += 1

        item = dict(row)
        item["explain_confidence"] = round(conf, 6)
        item["score_round2_base"] = round(adjusted, 6)
        pool.append(item)

    selected: List[Dict[str, Any]] = []
    remaining = list(pool)

    while remaining and len(selected) < max(1, int(top_k)):
        best_row = None
        best_mmr = None
        for row in remaining:
            rel = _safe_float(row.get("score_round2_base"), 0.0)
            vec_i = row.get("_vector") or []

            if not selected:
                mmr = rel
            else:
                max_sim = max(_cosine(vec_i, s.get("_vector") or []) for s in selected)
                mmr = (lam * rel) - ((1.0 - lam) * max_sim)

            if best_row is None or (best_mmr is not None and mmr > best_mmr):
                best_row = row
                best_mmr = mmr

        if best_row is None:
            break

        picked = dict(best_row)
        picked["mmr_score"] = round(_safe_float(best_mmr, 0.0), 6)
        picked["score_total"] = round(_safe_float(picked.get("score_round2_base"), 0.0), 6)
        selected.append(picked)
        remaining = [x for x in remaining if str(x.get("book_id")) != str(picked.get("book_id"))]

    for idx, row in enumerate(selected, start=1):
        row["rank"] = idx

    meta = {
        "lambda": round(lam, 6),
        "confidence_penalty_threshold": round(threshold, 6),
        "penalty_multiplier": round(penalty, 6),
        "penalty_applied_count": penalty_count,
        "final_count": len(selected),
    }
    return selected, meta
