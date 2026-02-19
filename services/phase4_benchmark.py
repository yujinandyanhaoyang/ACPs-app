from __future__ import annotations

from typing import Any, Dict, List, Sequence

from services.evaluation_metrics import compute_recommendation_metrics
from services.phase4_optimizer import objective_score


def evaluate_method_case(
    recommendations: Sequence[Dict[str, Any]],
    ground_truth_ids: Sequence[str],
    top_k: int,
) -> Dict[str, float]:
    recs = list(recommendations)
    diversities = []
    novelties = []
    for row in recs[: max(1, top_k)]:
        parts = row.get("score_parts") or {}
        diversities.append(_safe_float(parts.get("diversity"), 0.0))
        novelties.append(_safe_float(row.get("novelty_score"), 0.0))

    avg_div = sum(diversities) / len(diversities) if diversities else 0.0
    avg_nov = sum(novelties) / len(novelties) if novelties else 0.0

    return compute_recommendation_metrics(
        recommendations=recs,
        ground_truth_ids=list(ground_truth_ids),
        k=max(1, int(top_k)),
        avg_diversity=avg_div,
        avg_novelty=avg_nov,
    )


def aggregate_method_runs(runs: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    if not runs:
        return {
            "cases": 0.0,
            "precision_at_k": 0.0,
            "recall_at_k": 0.0,
            "ndcg_at_k": 0.0,
            "diversity": 0.0,
            "novelty": 0.0,
            "latency_ms_mean": 0.0,
            "strict_failure_rate": 0.0,
            "remote_attempt_rate": 0.0,
            "fallback_rate": 0.0,
            "remote_success_rate": 0.0,
            "objective_score": 0.0,
            "objective_score_latency_aware": 0.0,
        }

    metrics = [row.get("metrics") or {} for row in runs]
    summary = {
        "cases": float(len(runs)),
        "precision_at_k": _avg(metrics, "precision_at_k"),
        "recall_at_k": _avg(metrics, "recall_at_k"),
        "ndcg_at_k": _avg(metrics, "ndcg_at_k"),
        "diversity": _avg(metrics, "diversity"),
        "novelty": _avg(metrics, "novelty"),
        "latency_ms_mean": _avg(runs, "latency_ms"),
        "strict_failure_rate": _avg(runs, "strict_failure"),
        "remote_attempt_rate": _avg(runs, "remote_attempt_rate"),
        "fallback_rate": _avg(runs, "fallback_rate"),
        "remote_success_rate": _avg(runs, "remote_success_rate"),
    }
    summary["objective_score"] = objective_score(
        summary,
        {
            "precision_at_k": 0.25,
            "recall_at_k": 0.2,
            "ndcg_at_k": 0.35,
            "diversity": 0.1,
            "novelty": 0.1,
            "latency_penalty": 0.0,
        },
    )
    summary["objective_score_latency_aware"] = objective_score(
        summary,
        {
            "precision_at_k": 0.25,
            "recall_at_k": 0.2,
            "ndcg_at_k": 0.35,
            "diversity": 0.1,
            "novelty": 0.1,
            "latency_penalty": 0.00002,
        },
    )
    return summary


def rank_methods(method_reports: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for row in method_reports:
        summary = row.get("summary") or {}
        rows.append(
            {
                "method": row.get("method"),
                "objective_score": _safe_float(summary.get("objective_score"), -999.0),
                "objective_score_latency_aware": _safe_float(summary.get("objective_score_latency_aware"), -999.0),
                "ndcg_at_k": _safe_float(summary.get("ndcg_at_k"), 0.0),
                "precision_at_k": _safe_float(summary.get("precision_at_k"), 0.0),
                "latency_ms_mean": _safe_float(summary.get("latency_ms_mean"), 0.0),
                "strict_failure_rate": _safe_float(summary.get("strict_failure_rate"), 0.0),
                "remote_attempt_rate": _safe_float(summary.get("remote_attempt_rate"), 0.0),
                "fallback_rate": _safe_float(summary.get("fallback_rate"), 0.0),
                "remote_success_rate": _safe_float(summary.get("remote_success_rate"), 0.0),
            }
        )

    rows.sort(key=lambda item: (item["objective_score"], item["ndcg_at_k"], -item["latency_ms_mean"]), reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _avg(rows: Sequence[Dict[str, Any]], key: str) -> float:
    values = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        values.append(_safe_float(value))
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
