import math
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_TEST_INTERACTIONS_PATH = _PROJECT_ROOT / "data" / "processed" / "goodreads" / "interactions_test.jsonl"


def load_test_interactions(n: int = 100, test_path: Path | None = None) -> List[Dict[str, Any]]:
	"""Load up to *n* held-out interactions for empirical evaluation.

	Each returned row contains at least: ``user_id``, ``book_id``, ``rating``.
	Rows with missing ``user_id`` or ``book_id`` are skipped.
	"""
	path = test_path or _DEFAULT_TEST_INTERACTIONS_PATH
	if n <= 0 or not path.exists():
		return []

	rows: List[Dict[str, Any]] = []
	with path.open("r", encoding="utf-8") as f:
		for line in f:
			line = line.strip()
			if not line:
				continue
			try:
				payload = json.loads(line)
			except json.JSONDecodeError:
				continue
			if not isinstance(payload, dict):
				continue

			user_id = str(payload.get("user_id") or "").strip()
			book_id = str(payload.get("book_id") or "").strip()
			if not user_id or not book_id:
				continue

			rows.append(
				{
					"user_id": user_id,
					"book_id": book_id,
					"rating": _safe_float(payload.get("rating"), 0.0),
				}
			)
			if len(rows) >= n:
				break
	return rows


def _safe_float(value: Any, default: float = 0.0) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return default


def _dcg(relevance_scores: Sequence[float]) -> float:
	total = 0.0
	for index, rel in enumerate(relevance_scores, start=1):
		total += (2 ** rel - 1) / math.log2(index + 1)
	return total


def compute_recommendation_metrics(
	recommendations: List[Dict[str, Any]],
	ground_truth_ids: List[str],
	k: int,
	avg_diversity: float = 0.0,
	avg_novelty: float = 0.0,
) -> Dict[str, float]:
	if k <= 0:
		return {
			"precision_at_k": 0.0,
			"recall_at_k": 0.0,
			"ndcg_at_k": 0.0,
			"diversity": round(_safe_float(avg_diversity), 4),
			"novelty": round(_safe_float(avg_novelty), 4),
		}

	recommended_ids = [str(item.get("book_id") or "") for item in recommendations[:k]]
	ground_truth = {str(item) for item in (ground_truth_ids or []) if str(item)}
	if not recommended_ids:
		return {
			"precision_at_k": 0.0,
			"recall_at_k": 0.0,
			"ndcg_at_k": 0.0,
			"diversity": round(_safe_float(avg_diversity), 4),
			"novelty": round(_safe_float(avg_novelty), 4),
		}

	hits = [1.0 if rid in ground_truth else 0.0 for rid in recommended_ids]
	precision = sum(hits) / len(recommended_ids)
	recall = sum(hits) / len(ground_truth) if ground_truth else 0.0
	dcg_value = _dcg(hits)
	ideal_count = min(len(ground_truth), len(recommended_ids))
	idcg_value = _dcg([1.0] * ideal_count + [0.0] * (len(recommended_ids) - ideal_count))
	ndcg = (dcg_value / idcg_value) if idcg_value > 0 else 0.0

	return {
		"precision_at_k": round(precision, 4),
		"recall_at_k": round(recall, 4),
		"ndcg_at_k": round(ndcg, 4),
		"diversity": round(_safe_float(avg_diversity), 4),
		"novelty": round(_safe_float(avg_novelty), 4),
	}


def build_ablation_report(
	recommendations: List[Dict[str, Any]],
	scoring_weights: Dict[str, Any],
) -> Dict[str, Any]:
	"""Return an algebraic component decomposition for one recommendation list.

	This function does **not** perform empirical ablation runs on held-out data;
	it computes estimated component contribution as:

	``component_mean_score * max(weight, 0)``.

	For empirical ablation (re-running the full pipeline with one component removed
	at a time), use ``scripts/run_ablation.py``.
	"""
	score_keys = ["collaborative", "semantic", "knowledge", "diversity"]
	weights = {key: _safe_float(scoring_weights.get(key), 0.0) for key in score_keys}
	if not recommendations:
		return {
			"weights": weights,
			"component_mean_scores": {key: 0.0 for key in score_keys},
			"estimated_drop_if_removed": {key: 0.0 for key in score_keys},
		}

	component_means: Dict[str, float] = {}
	for key in score_keys:
		values: List[float] = []
		for item in recommendations:
			parts = item.get("score_parts") or {}
			values.append(_safe_float(parts.get(key), 0.0))
		component_means[key] = round(sum(values) / len(values), 4) if values else 0.0

	estimated_drop = {
		key: round(component_means[key] * max(weights[key], 0.0), 4)
		for key in score_keys
	}
	return {
		"weights": weights,
		"component_mean_scores": component_means,
		"estimated_drop_if_removed": estimated_drop,
	}
