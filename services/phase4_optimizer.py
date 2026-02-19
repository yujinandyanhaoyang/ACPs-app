from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def aggregate_experiment_runs(runs: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    if not runs:
        return {
            "cases": 0,
            "success_rate": 0.0,
            "precision_at_k": 0.0,
            "recall_at_k": 0.0,
            "ndcg_at_k": 0.0,
            "diversity": 0.0,
            "novelty": 0.0,
            "latency_ms_mean": 0.0,
            "latency_ms_p95": 0.0,
        }

    metric_keys = ["precision_at_k", "recall_at_k", "ndcg_at_k", "diversity", "novelty"]
    metric_values: Dict[str, List[float]] = {key: [] for key in metric_keys}
    latencies: List[float] = []
    success = 0

    for row in runs:
        if str(row.get("state") or "") == "completed":
            success += 1
        metrics = row.get("metrics") or {}
        for key in metric_keys:
            value = metrics.get(key)
            if value is None:
                continue
            metric_values[key].append(_safe_float(value))
        latencies.append(_safe_float(row.get("latency_ms"), 0.0))

    summary: Dict[str, float] = {
        "cases": float(len(runs)),
        "success_rate": round(success / len(runs), 4),
        "latency_ms_mean": round(sum(latencies) / len(latencies), 4) if latencies else 0.0,
        "latency_ms_p95": round(_percentile(latencies, 95), 4) if latencies else 0.0,
    }

    for key in metric_keys:
        values = metric_values[key]
        summary[key] = round(sum(values) / len(values), 4) if values else 0.0
    return summary


def objective_score(
    summary: Dict[str, Any],
    objective_weights: Dict[str, float] | None = None,
) -> float:
    weights = objective_weights or {
        "precision_at_k": 0.25,
        "recall_at_k": 0.2,
        "ndcg_at_k": 0.35,
        "diversity": 0.1,
        "novelty": 0.1,
        "latency_penalty": 0.002,
    }

    reward = 0.0
    reward += _safe_float(summary.get("precision_at_k")) * _safe_float(weights.get("precision_at_k"), 0.0)
    reward += _safe_float(summary.get("recall_at_k")) * _safe_float(weights.get("recall_at_k"), 0.0)
    reward += _safe_float(summary.get("ndcg_at_k")) * _safe_float(weights.get("ndcg_at_k"), 0.0)
    reward += _safe_float(summary.get("diversity")) * _safe_float(weights.get("diversity"), 0.0)
    reward += _safe_float(summary.get("novelty")) * _safe_float(weights.get("novelty"), 0.0)

    penalty = _safe_float(summary.get("latency_ms_mean")) * _safe_float(weights.get("latency_penalty"), 0.0)
    score = reward - penalty
    return round(score, 6)


def select_best_experiment(
    experiments: Sequence[Dict[str, Any]],
    objective_weights: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    if not experiments:
        return {}

    best: Dict[str, Any] | None = None
    for row in experiments:
        summary = row.get("summary") or {}
        current = {
            **row,
            "objective_score": objective_score(summary, objective_weights),
        }
        if best is None:
            best = current
            continue
        if current["objective_score"] > best["objective_score"]:
            best = current
            continue
        if (
            current["objective_score"] == best["objective_score"]
            and _safe_float(summary.get("latency_ms_mean"))
            < _safe_float((best.get("summary") or {}).get("latency_ms_mean"))
        ):
            best = current

    return best or {}


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (len(sorted_values) - 1) * (percentile / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[lower]

    ratio = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * ratio
