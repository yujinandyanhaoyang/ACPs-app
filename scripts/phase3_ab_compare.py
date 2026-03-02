from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Sequence

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.book_retrieval import (
    detect_query_language,
    load_books_dual_corpus,
    retrieve_books_by_variant_with_diagnostics,
)
from services.evaluation_metrics import compute_recommendation_metrics


PROJECT_ROOT = _PROJECT_ROOT
OUT_LOG_PATH = PROJECT_ROOT / "scripts" / "phase3_ab_experiment_log.jsonl"
OUT_SUMMARY_PATH = PROJECT_ROOT / "scripts" / "phase3_ab_summary.json"
OUT_SUMMARY_MD_PATH = PROJECT_ROOT / "scripts" / "phase3_ab_summary.md"

VARIANTS = ["baseline", "metadata-first-fusion", "full-fusion"]

QUERIES: List[Dict[str, str]] = [
    {"id": "zh_01", "language": "zh", "query": "推荐历史小说，最好有家国叙事"},
    {"id": "zh_02", "language": "zh", "query": "我想看现实主义题材的中文文学"},
    {"id": "zh_03", "language": "zh", "query": "有没有儿童童话和温暖治愈故事"},
    {"id": "zh_04", "language": "zh", "query": "想找悬疑推理小说"},
    {"id": "zh_05", "language": "zh", "query": "推荐中国基层治理相关书籍"},
    {"id": "en_01", "language": "en", "query": "recommend science fiction with social themes"},
    {"id": "en_02", "language": "en", "query": "books about public policy and governance"},
    {"id": "en_03", "language": "en", "query": "uplifting children fairy tales"},
    {"id": "en_04", "language": "en", "query": "dark suspense and thriller novels"},
    {"id": "en_05", "language": "en", "query": "rural literature and family history"},
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _simple_tokens(text: str) -> List[str]:
    normalized = str(text or "").lower()
    return [tok for tok in re.findall(r"[a-zA-Z\u3400-\u4dbf\u4e00-\u9fff]{2,}", normalized) if tok]


def _book_text(row: Dict[str, Any]) -> str:
    title = str(row.get("title") or "")
    description = str(row.get("description") or "")
    genres = " ".join(str(item) for item in (row.get("genres") or []))
    return f"{title} {description} {genres}".strip().lower()


def _ground_truth_ids(query: str, expected_language: str, books: Sequence[Dict[str, Any]], top_n: int = 5) -> List[str]:
    q_tokens = _simple_tokens(query)
    scored: List[tuple[str, int]] = []
    for row in books:
        row_lang = str(row.get("language") or "").lower()
        if expected_language == "zh" and not row_lang.startswith("zh"):
            continue
        if expected_language == "en" and not row_lang.startswith("en"):
            continue
        bid = str(row.get("book_id") or "").strip()
        if not bid:
            continue
        text = _book_text(row)
        overlap = sum(1 for token in q_tokens if token in text)
        if overlap <= 0:
            continue
        scored.append((bid, overlap))

    scored.sort(key=lambda item: item[1], reverse=True)
    return [bid for bid, _ in scored[: max(1, top_n)]]


def _duplicate_ratio_by_canonical(rows: Sequence[Dict[str, Any]]) -> float:
    canonical = [str(r.get("canonical_work_id") or "").strip() for r in rows if str(r.get("canonical_work_id") or "").strip()]
    if not canonical:
        return 0.0
    return max(0.0, (len(canonical) - len(set(canonical))) / len(canonical))


def _aggregate(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    if not rows:
        return {
            "case_count": 0.0,
            "precision_at_5": 0.0,
            "recall_at_5": 0.0,
            "ndcg_at_5": 0.0,
            "latency_ms_mean": 0.0,
            "fallback_rate": 0.0,
            "duplicate_ratio_topk_mean": 0.0,
        }

    return {
        "case_count": float(len(rows)),
        "precision_at_5": round(mean(_safe_float(r["metrics"].get("precision_at_k"), 0.0) for r in rows), 4),
        "recall_at_5": round(mean(_safe_float(r["metrics"].get("recall_at_k"), 0.0) for r in rows), 4),
        "ndcg_at_5": round(mean(_safe_float(r["metrics"].get("ndcg_at_k"), 0.0) for r in rows), 4),
        "latency_ms_mean": round(mean(_safe_float(r.get("latency_ms"), 0.0) for r in rows), 4),
        "fallback_rate": round(mean(1.0 if bool(r.get("fallback_used")) else 0.0 for r in rows), 4),
        "duplicate_ratio_topk_mean": round(mean(_safe_float(r.get("duplicate_ratio_topk"), 0.0) for r in rows), 4),
    }


def run_phase3_ab() -> Dict[str, Any]:
    corpora = load_books_dual_corpus()
    books_en = list(corpora.get("en") or [])
    books_zh = list(corpora.get("zh") or [])
    all_books = books_en + books_zh

    run_rows: List[Dict[str, Any]] = []
    for item in QUERIES:
        query = item["query"]
        expected_language = item["language"]
        gt_ids = _ground_truth_ids(query, expected_language, all_books, top_n=5)
        if not gt_ids:
            pseudo_recs, _ = retrieve_books_by_variant_with_diagnostics(
                query=query,
                top_k=5,
                variant="metadata-first-fusion",
                min_primary_hits=5,
                books_en=books_en,
                books_zh=books_zh,
            )
            gt_ids = [str(row.get("book_id") or "").strip() for row in pseudo_recs if str(row.get("book_id") or "").strip()][:3]

        for variant in VARIANTS:
            start = time.perf_counter()
            recs, diag = retrieve_books_by_variant_with_diagnostics(
                query=query,
                top_k=5,
                variant=variant,
                min_primary_hits=5,
                books_en=books_en,
                books_zh=books_zh,
            )
            latency_ms = (time.perf_counter() - start) * 1000

            metrics = compute_recommendation_metrics(
                recommendations=recs,
                ground_truth_ids=gt_ids,
                k=5,
                avg_diversity=0.0,
                avg_novelty=0.0,
            )
            row = {
                "query_id": item["id"],
                "query": query,
                "expected_language": expected_language,
                "detected_query_language": detect_query_language(query).get("language", "mixed"),
                "variant": variant,
                "metrics": metrics,
                "latency_ms": round(latency_ms, 4),
                "fallback_used": bool(diag.get("fallback_used", False)),
                "primary_corpus": diag.get("primary_corpus", "unknown"),
                "duplicate_ratio_topk": round(_duplicate_ratio_by_canonical(recs), 4),
                "ground_truth_count": len(gt_ids),
                "result_count": len(recs),
            }
            run_rows.append(row)

    OUT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_LOG_PATH.open("w", encoding="utf-8") as f:
        for row in run_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary_rows: List[Dict[str, Any]] = []
    for variant in VARIANTS:
        variant_rows = [row for row in run_rows if row["variant"] == variant]
        zh_rows = [row for row in variant_rows if row["expected_language"] == "zh"]
        en_rows = [row for row in variant_rows if row["expected_language"] == "en"]

        summary_rows.append(
            {
                "variant": variant,
                "overall": _aggregate(variant_rows),
                "zh": _aggregate(zh_rows),
                "en": _aggregate(en_rows),
            }
        )

    by_variant = {row["variant"]: row for row in summary_rows}
    baseline = by_variant.get("baseline", {})
    metadata = by_variant.get("metadata-first-fusion", {})

    baseline_zh_ndcg = _safe_float((baseline.get("zh") or {}).get("ndcg_at_5"), 0.0)
    metadata_zh_ndcg = _safe_float((metadata.get("zh") or {}).get("ndcg_at_5"), 0.0)
    baseline_en_ndcg = _safe_float((baseline.get("en") or {}).get("ndcg_at_5"), 0.0)
    metadata_en_ndcg = _safe_float((metadata.get("en") or {}).get("ndcg_at_5"), 0.0)
    baseline_latency = _safe_float((baseline.get("overall") or {}).get("latency_ms_mean"), 0.0)
    metadata_latency = _safe_float((metadata.get("overall") or {}).get("latency_ms_mean"), 0.0)

    acceptance = {
        "metadata_beats_baseline_on_zh_ndcg": metadata_zh_ndcg >= baseline_zh_ndcg,
        "metadata_no_regression_on_en_ndcg": metadata_en_ndcg >= max(0.0, baseline_en_ndcg - 0.02),
        "metadata_latency_regression_le_100ms": (metadata_latency - baseline_latency) < 100.0,
    }
    acceptance["passed"] = all(acceptance.values())

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": {"en_count": len(books_en), "zh_count": len(books_zh)},
        "variants": summary_rows,
        "acceptance": acceptance,
        "artifacts": {
            "experiment_log": str(OUT_LOG_PATH),
            "summary_json": str(OUT_SUMMARY_PATH),
            "summary_md": str(OUT_SUMMARY_MD_PATH),
        },
    }

    OUT_SUMMARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase 3 A/B Summary",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Dataset: en={len(books_en)}, zh={len(books_zh)}",
        "",
        "## Variant Metrics",
        "| variant | lang | ndcg@5 | precision@5 | recall@5 | latency_ms_mean | fallback_rate | duplicate_ratio_topk_mean |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    for row in summary_rows:
        variant = row["variant"]
        for lang_key in ["overall", "zh", "en"]:
            stats = row[lang_key]
            lines.append(
                f"| {variant} | {lang_key} | {stats['ndcg_at_5']:.4f} | {stats['precision_at_5']:.4f} | {stats['recall_at_5']:.4f} | {stats['latency_ms_mean']:.4f} | {stats['fallback_rate']:.4f} | {stats['duplicate_ratio_topk_mean']:.4f} |"
            )

    lines.extend(
        [
            "",
            "## Acceptance",
            f"- metadata_beats_baseline_on_zh_ndcg: {acceptance['metadata_beats_baseline_on_zh_ndcg']}",
            f"- metadata_no_regression_on_en_ndcg: {acceptance['metadata_no_regression_on_en_ndcg']}",
            f"- metadata_latency_regression_le_100ms: {acceptance['metadata_latency_regression_le_100ms']}",
            f"- passed: {acceptance['passed']}",
            "",
            "## Logging Schema",
            "- One JSONL row per `(query_id, variant)` with fields: `variant`, `expected_language`, `detected_query_language`, `metrics`, `latency_ms`, `fallback_used`, `primary_corpus`, `duplicate_ratio_topk`, `ground_truth_count`, `result_count`.",
        ]
    )

    OUT_SUMMARY_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    report = run_phase3_ab()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
