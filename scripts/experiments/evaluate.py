"""离线评估：NDCG@5、Precision@5、Intra-List Diversity（ILD）、Coverage。

使用方式：
    python evaluate.py [--input artifacts/experiments/raw/<run_id>_all.jsonl]

若不指定 --input，将自动选取 artifacts/experiments/raw/ 下最新的 *_all.jsonl。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import csv

# ── 评估指标实现 ───────────────────────────────────────────────────────────────

def dcg_at_k(relevances: List[float], k: int) -> float:
    """折扣累积增益 DCG@k。"""
    return sum(
        rel / math.log2(i + 2)
        for i, rel in enumerate(relevances[:k])
    )


def ndcg_at_k(rec_book_ids: List[str], relevant_set: Dict[str, float], k: int) -> float:
    """NDCG@k。relevant_set: {book_id -> relevance_score}，分数范围 0~5（如 Goodreads 评分）。"""
    if not relevant_set:
        return 0.0
    gains = [relevant_set.get(bid, 0.0) for bid in rec_book_ids[:k]]
    ideal_gains = sorted(relevant_set.values(), reverse=True)[:k]
    idcg = dcg_at_k(ideal_gains, k)
    if idcg == 0:
        return 0.0
    return dcg_at_k(gains, k) / idcg


def precision_at_k(rec_book_ids: List[str], relevant_set: Set[str], k: int) -> float:
    """Precision@k，relevant_set 为相关书籍 ID 集合（评分 >= 阈值）。"""
    hits = sum(1 for bid in rec_book_ids[:k] if bid in relevant_set)
    return hits / k


def intra_list_diversity(rec_items: List[Dict[str, Any]]) -> float:
    """ILD：推荐列表内平均 genre 差异度（Jaccard 距离）。
    
    返回值越高代表多样性越强（0 = 完全相同，1 = 完全不同）。
    """
    genre_sets: List[Set[str]] = []
    for item in rec_items:
        genres = item.get("genres") or item.get("genre") or []
        if isinstance(genres, str):
            genres = [g.strip() for g in genres.split(",") if g.strip()]
        genre_sets.append(set(str(g).lower() for g in genres))

    n = len(genre_sets)
    if n < 2:
        return 0.0

    total_dist = 0.0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = genre_sets[i], genre_sets[j]
            union = len(a | b)
            if union == 0:
                dist = 0.0
            else:
                dist = 1.0 - len(a & b) / union
            total_dist += dist
            pairs += 1

    return total_dist / pairs if pairs > 0 else 0.0


def coverage(all_variant_recs: Dict[str, List[str]], catalog_size: int) -> Dict[str, float]:
    """Catalog Coverage：推荐过的书籍占总书籍比例。"""
    return {
        vid: len(set(bids)) / max(1, catalog_size)
        for vid, bids in all_variant_recs.items()
    }


# ── 假设相关性评估（离线代理）────────────────────────────────────────────────
# 当没有真实用户反馈时，使用推荐结果的 score_total / score_round1 作为相关性代理。
# 你也可以替换为真实 Goodreads 评分数据。

def extract_proxy_relevance(item: Dict[str, Any]) -> float:
    """从 API 响应中提取相关性代理分数（0~5 归一化为 0~1）。"""
    score = item.get("score_total") or item.get("score_round1") or item.get("score") or 0.0
    try:
        s = float(score)
        # 将 0~1 范围的 score 映射到 0~5（模拟 Goodreads 评分量级）
        return min(5.0, s * 5.0)
    except Exception:
        return 0.0


# ── 主评估流程 ─────────────────────────────────────────────────────────────────

def load_results(path: Path) -> List[Dict[str, Any]]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def extract_recommendations(response: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从 API response 中提取 recommendations 列表。"""
    if response is None:
        return []
    # 兼容不同响应结构
    recs = (
        response.get("recommendations")
        or response.get("data", {}).get("recommendations")
        or response.get("result", {}).get("recommendations")
        or []
    )
    return recs if isinstance(recs, list) else []


def evaluate_all(records: List[Dict[str, Any]], k: int = 5) -> Dict[str, Any]:
    """
    按 variant_id 分组计算各指标。
    返回 {variant_id: {metric: value, ...}}
    """
    # 聚合：variant_id -> list of (rec_items)
    variant_recs: Dict[str, List[List[Dict]]] = defaultdict(list)
    variant_book_ids: Dict[str, List[str]] = defaultdict(list)
    variant_names: Dict[str, str] = {}

    for rec in records:
        if rec.get("error") is not None:
            continue
        vid = rec["variant_id"]
        variant_names[vid] = rec.get("variant_name", vid)
        items = extract_recommendations(rec.get("response"))
        if not items:
            continue
        variant_recs[vid].append(items)
        for item in items:
            bid = str(item.get("book_id") or item.get("id") or "")
            if bid:
                variant_book_ids[vid].append(bid)

    # 估算 catalog size（使用所有出现过的 book_id 数量作为下界）
    all_book_ids: Set[str] = set()
    for bids in variant_book_ids.values():
        all_book_ids.update(bids)
    catalog_size = max(len(all_book_ids) * 10, 10000)  # 保守估算

    cov = coverage(variant_book_ids, catalog_size)

    results: Dict[str, Dict] = {}
    for vid, rec_lists in variant_recs.items():
        ndcg_scores, prec_scores, ild_scores = [], [], []
        for items in rec_lists:
            if not items:
                continue
            book_ids = [str(item.get("book_id") or item.get("id") or "") for item in items]
            # 构建相关性映射（使用代理分数）
            relevance_map = {
                book_ids[i]: extract_proxy_relevance(items[i])
                for i in range(len(items))
                if book_ids[i]
            }
            # 相关集合（代理：proxy score > 0.3 视为相关）
            relevant_set = {bid for bid, s in relevance_map.items() if s > 1.5}

            ndcg_scores.append(ndcg_at_k(book_ids, relevance_map, k))
            prec_scores.append(precision_at_k(book_ids, relevant_set, k))
            ild_scores.append(intra_list_diversity(items))

        def mean(lst): return sum(lst) / len(lst) if lst else 0.0

        results[vid] = {
            "variant_id": vid,
            "variant_name": variant_names.get(vid, vid),
            "sample_count": len(rec_lists),
            f"NDCG@{k}": round(mean(ndcg_scores), 4),
            f"Precision@{k}": round(mean(prec_scores), 4),
            "ILD": round(mean(ild_scores), 4),
            "Coverage": round(cov.get(vid, 0.0), 6),
        }

    return results


def save_metrics(metrics: Dict[str, Dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(metrics.values())
    if not rows:
        print("No metrics to save.")
        return
    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Metrics saved → {output_path}")


def find_latest_results(raw_dir: Path) -> Optional[Path]:
    candidates = sorted(raw_dir.glob("*_all.jsonl"), reverse=True)
    return candidates[0] if candidates else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ablation experiment results")
    parser.add_argument("--input", type=str, default=None,
                        help="Path to *_all.jsonl result file")
    parser.add_argument("--k", type=int, default=5, help="Cutoff k (default: 5)")
    args = parser.parse_args()

    raw_dir = Path(__file__).parents[2] / "artifacts" / "experiments" / "raw"
    metrics_dir = Path(__file__).parents[2] / "artifacts" / "experiments" / "metrics"

    if args.input:
        input_path = Path(args.input)
    else:
        input_path = find_latest_results(raw_dir)
        if input_path is None:
            print(f"No result files found in {raw_dir}. Run run_experiments.py first.")
            return

    print(f"Loading results from: {input_path}")
    records = load_results(input_path)
    print(f"Loaded {len(records)} records.")

    metrics = evaluate_all(records, k=args.k)

    print("\n=== Evaluation Results ===")
    headers = ["variant_id", "variant_name", "sample_count",
               f"NDCG@{args.k}", f"Precision@{args.k}", "ILD", "Coverage"]
    col_w = [10, 30, 12, 10, 14, 8, 10]
    header_line = "".join(h.ljust(w) for h, w in zip(headers, col_w))
    print(header_line)
    print("-" * sum(col_w))
    for vid in sorted(metrics.keys()):
        row = metrics[vid]
        line = "".join(str(row.get(h, "")).ljust(w) for h, w in zip(headers, col_w))
        print(line)

    run_id = input_path.stem.replace("_all", "")
    output_path = metrics_dir / f"{run_id}_metrics.csv"
    save_metrics(metrics, output_path)


if __name__ == "__main__":
    main()
