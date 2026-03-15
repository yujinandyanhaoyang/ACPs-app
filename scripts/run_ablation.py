from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence

import httpx
from dotenv import load_dotenv

_CURRENT_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 加载 .env 配置
load_dotenv(Path(_PROJECT_ROOT) / ".env")

# Force deterministic offline execution for empirical ablation.
# This avoids flaky external API failures and ensures local embedding backends.
# os.environ["OPENAI_API_KEY"] = ""  # 注释掉，允许使用 DashScope API
# os.environ["OPENAI_BASE_URL"] = ""
os.environ.setdefault("BOOK_CONTENT_EMBED_MODEL", "all-MiniLM-L6-v2")
os.environ.setdefault("REC_RANKING_EMBED_MODEL", "all-MiniLM-L6-v2")

import reading_concierge.reading_concierge as concierge_module
from reading_concierge.reading_concierge import app as concierge_app
from services.book_retrieval import load_books
from services.evaluation_metrics import compute_recommendation_metrics, load_test_interactions
from services.data_paths import get_processed_data_path

PROJECT_ROOT = Path(_PROJECT_ROOT)
DEFAULT_TRAIN_PATH = get_processed_data_path("merged", "interactions_merged.jsonl")
DEFAULT_OUT_PATH = PROJECT_ROOT / "scripts" / "ablation_report.json"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    positive = {k: max(_safe_float(v), 0.0) for k, v in weights.items()}
    total = sum(positive.values())
    if total <= 0:
        return {"collaborative": 0.25, "semantic": 0.35, "knowledge": 0.2, "diversity": 0.2}
    return {k: round(v / total, 6) for k, v in positive.items()}


def _ablated_weights(base_weights: Dict[str, float], remove_key: str | None) -> Dict[str, float]:
    weights = dict(base_weights)
    if remove_key:
        weights[remove_key] = 0.0
    return _normalize_weights(weights)


def _group_test_by_user(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        user_id = str(row.get("user_id") or "").strip()
        if not user_id:
            continue
        grouped[user_id].append(row)
    return grouped


def _load_train_by_user(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if not path.exists():
        return grouped
    for row in _iter_jsonl(path):
        user_id = str(row.get("user_id") or "").strip()
        book_id = str(row.get("book_id") or "").strip()
        if not user_id or not book_id:
            continue
        grouped[user_id].append(
            {
                "book_id": book_id,
                "rating": _safe_float(row.get("rating"), 0.0),
            }
        )
    return grouped


def _book_index() -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for row in load_books():
        if not isinstance(row, dict):
            continue
        bid = str(row.get("book_id") or "").strip()
        if bid and bid not in idx:
            idx[bid] = row
    return idx


def _history_to_query(history: List[Dict[str, Any]]) -> str:
    genre_counts: Dict[str, int] = defaultdict(int)
    for row in history:
        for g in row.get("genres") or []:
            token = str(g).replace("_", " ").strip().lower()
            if token:
                genre_counts[token] += 1
    top = [k for k, _ in sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:3]]
    if top:
        return "recommend books about " + ", ".join(top)
    return "recommend books"


def _build_history(user_rows: List[Dict[str, Any]], books_idx: Dict[str, Dict[str, Any]], max_items: int = 8) -> List[Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    for row in user_rows:
        book = books_idx.get(str(row.get("book_id") or ""))
        if not book:
            continue
        history.append(
            {
                "book_id": book.get("book_id"),
                "title": book.get("title"),
                "genres": book.get("genres") or [],
                "themes": book.get("themes") or [],
                "rating": _safe_float(row.get("rating"), 0.0),
                "language": book.get("language") or "en",
            }
        )
        if len(history) >= max_items:
            break
    return history


async def _run_case(
    client: httpx.AsyncClient,
    history: List[Dict[str, Any]],
    ground_truth_ids: List[str],
    scoring_weights: Dict[str, float],
    top_k: int,
) -> Dict[str, float]:
    query = _history_to_query(history)
    payload = {
        "query": query,
        "history": history,
        "user_profile": {"preferred_language": "en"},
        "constraints": {
            "scenario": "warm",
            "top_k": top_k,
            "scoring_weights": scoring_weights,
            "ground_truth_ids": ground_truth_ids,
        },
    }
    response = await client.post("/user_api", json=payload)
    response.raise_for_status()
    body = response.json()

    recommendations = body.get("recommendations") or []
    metric_snapshot = body.get("metric_snapshot") or {}
    return compute_recommendation_metrics(
        recommendations=recommendations,
        ground_truth_ids=ground_truth_ids,
        k=top_k,
        avg_diversity=_safe_float(metric_snapshot.get("avg_diversity"), 0.0),
        avg_novelty=_safe_float(metric_snapshot.get("avg_novelty"), 0.0),
    )


def _avg_metric(rows: Sequence[Dict[str, float]], key: str) -> float:
    values = [
        _safe_float(row.get(key), 0.0)
        for row in rows
        if row.get(key) is not None
    ]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def _aggregate(rows: Sequence[Dict[str, float]]) -> Dict[str, float]:
    return {
        "precision_at_5": _avg_metric(rows, "precision_at_k"),
        "recall_at_5": _avg_metric(rows, "recall_at_k"),
        "ndcg_at_5": _avg_metric(rows, "ndcg_at_k"),
        "diversity": _avg_metric(rows, "diversity"),
        "novelty": _avg_metric(rows, "novelty"),
    }


async def run_ablation(
    n_users: int = 10,
    top_k: int = 5,
    train_path: Path = DEFAULT_TRAIN_PATH,
    min_history: int = 3,
    min_ground_truth: int = 1,
    min_ground_truth_rating: float = 4.0,
) -> Dict[str, Any]:
    test_rows = load_test_interactions(n=max(1, n_users * 40))
    test_by_user = _group_test_by_user(test_rows)
    train_by_user = _load_train_by_user(train_path)
    books_idx = _book_index()

    candidate_user_ids: List[str] = []
    user_ground_truth: Dict[str, List[str]] = {}
    for uid, heldout_rows in test_by_user.items():
        train_rows = train_by_user.get(uid) or []
        if len(train_rows) < max(1, min_history):
            continue

        deduped_gt: List[str] = []
        seen_gt: set[str] = set()
        for row in heldout_rows:
            bid = str(row.get("book_id") or "").strip()
            if not bid or bid in seen_gt:
                continue
            if _safe_float(row.get("rating"), 0.0) < min_ground_truth_rating:
                continue
            seen_gt.add(bid)
            deduped_gt.append(bid)

        if len(deduped_gt) < max(1, min_ground_truth):
            continue

        user_ground_truth[uid] = deduped_gt
        candidate_user_ids.append(uid)

    user_ids = candidate_user_ids[: max(1, n_users)]

    base_weights = _normalize_weights(
        {
            "collaborative": 0.25,
            "semantic": 0.35,
            "knowledge": 0.2,
            "diversity": 0.2,
        }
    )
    scenarios = [
        ("full", None),
        ("ablate_collaborative", "collaborative"),
        ("ablate_semantic", "semantic"),
        ("ablate_knowledge", "knowledge"),
        ("ablate_diversity", "diversity"),
    ]

    results: Dict[str, Dict[str, Any]] = {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=concierge_app), base_url="http://local") as client:
        for label, remove_key in scenarios:
            weights = _ablated_weights(base_weights, remove_key)
            per_user_metrics: List[Dict[str, float]] = []
            evaluated_users = 0

            for user_id in user_ids:
                history = _build_history(train_by_user[user_id], books_idx)
                if len(history) < max(1, min_history):
                    continue
                ground_truth_ids = user_ground_truth.get(user_id) or []
                if len(ground_truth_ids) < max(1, min_ground_truth):
                    continue
                metrics = await _run_case(
                    client=client,
                    history=history,
                    ground_truth_ids=ground_truth_ids,
                    scoring_weights=weights,
                    top_k=top_k,
                )
                per_user_metrics.append(metrics)
                evaluated_users += 1

            results[label] = {
                "weights": weights,
                "evaluated_users": evaluated_users,
                "metrics": _aggregate(per_user_metrics),
            }

    full_ndcg = _safe_float(results.get("full", {}).get("metrics", {}).get("ndcg_at_5"), 0.0)
    report_rows: List[Dict[str, Any]] = []
    for label, _ in scenarios:
        row = results[label]
        ndcg = _safe_float(row["metrics"].get("ndcg_at_5"), 0.0)
        report_rows.append(
            {
                "scenario": label,
                "weights": row["weights"],
                "evaluated_users": row["evaluated_users"],
                "precision_at_5": row["metrics"].get("precision_at_5"),
                "recall_at_5": row["metrics"].get("recall_at_5"),
                "ndcg_at_5": ndcg,
                "delta_ndcg_at_5_vs_full": round(ndcg - full_ndcg, 6),
                "diversity": row["metrics"].get("diversity"),
                "novelty": row["metrics"].get("novelty"),
            }
        )

    return {
        "generated_at": concierge_module.datetime.now(concierge_module.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "top_k": top_k,
        "requested_users": n_users,
        "candidate_users": len(candidate_user_ids),
        "evaluated_users": results.get("full", {}).get("evaluated_users", 0),
        "filters": {
            "min_history": max(1, min_history),
            "min_ground_truth": max(1, min_ground_truth),
            "min_ground_truth_rating": float(min_ground_truth_rating),
        },
        "rows": report_rows,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run empirical ablation against merged-dataset interactions")
    parser.add_argument("--users", type=int, default=10, help="Number of users to evaluate")
    parser.add_argument("--top-k", type=int, default=5, help="Top-k for metrics")
    parser.add_argument("--min-history", type=int, default=3, help="Minimum train interactions per user")
    parser.add_argument("--min-ground-truth", type=int, default=1, help="Minimum held-out positives per user")
    parser.add_argument("--min-ground-truth-rating", type=float, default=4.0, help="Minimum held-out rating to count as positive")
    parser.add_argument("--train", type=Path, default=DEFAULT_TRAIN_PATH, help="Path to interactions_train.jsonl")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH, help="Output report path")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = asyncio.run(
        run_ablation(
            n_users=max(1, args.users),
            top_k=max(1, args.top_k),
            train_path=args.train,
            min_history=max(1, args.min_history),
            min_ground_truth=max(1, args.min_ground_truth),
            min_ground_truth_rating=float(args.min_ground_truth_rating),
        )
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
