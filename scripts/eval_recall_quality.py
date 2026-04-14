#!/usr/bin/env python3
"""召回质量评估脚本

用法:
  python scripts/eval_recall_quality.py
  python scripts/eval_recall_quality.py --query "sci-fi space exploration" --top-k 100
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.book_retrieval import retrieve_books_by_vector
from services.model_backends import generate_text_embeddings

ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
_DATA_ROOT = Path(os.getenv("BOOK_RETRIEVAL_DATASET_PATH", "/root/WORK/DATA"))
DEFAULT_INDEX = _DATA_ROOT / "processed" / "books_index.faiss"
DEFAULT_META = _DATA_ROOT / "processed" / "books_index_meta.jsonl"


def _safe_str(v) -> str:
    return str(v or "").strip()


def evaluate(query: str, top_k: int, index_path: Path, meta_path: Path) -> dict:
    vectors, embed_meta = generate_text_embeddings(
        [query], model_name="all-MiniLM-L6-v2", fallback_dim=384
    )
    results = retrieve_books_by_vector(
        vectors[0], top_k=top_k, index_path=index_path, meta_path=meta_path
    )

    genre_counter: Counter = Counter()
    desc_filled = 0
    rating_filled = 0
    source_counter: Counter = Counter()

    for r in results:
        for g in (r.get("genres") or []):
            token = _safe_str(g).lower()
            if token:
                genre_counter[token] += 1
        if _safe_str(r.get("description")):
            desc_filled += 1
        if r.get("rating") is not None:
            rating_filled += 1
        source_counter[_safe_str(r.get("source")) or "unknown"] += 1

    n = len(results)
    return {
        "query": query,
        "index_path": str(index_path),
        "top_k_requested": top_k,
        "top_k_returned": n,
        "embedding_backend": embed_meta.get("backend"),
        "genre_coverage": {
            "unique_genres": len(genre_counter),
            "top10_genres": genre_counter.most_common(10),
        },
        "description_coverage": round(desc_filled / max(n, 1), 4),
        "rating_coverage": round(rating_filled / max(n, 1), 4),
        "source_distribution": dict(source_counter),
        "top5_sample": [
            {
                "rank": i + 1,
                "title": _safe_str(r.get("title")),
                "score": round(float(r.get("score") or 0), 4),
                "genres": (r.get("genres") or [])[:3],
                "has_description": bool(_safe_str(r.get("description"))),
                "rating": r.get("rating"),
            }
            for i, r in enumerate(results[:5])
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="召回质量评估")
    parser.add_argument("--query", default="a mystery novel with psychological thriller elements")
    parser.add_argument("--top-k", type=int, default=100)
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    args = parser.parse_args()

    index_path = Path(args.index)
    meta_path = index_path.parent / "books_index_meta.jsonl"

    if not index_path.exists():
        print(f"[ERROR] Index not found: {index_path}")
        return 1

    report = evaluate(args.query, args.top_k, index_path, meta_path)

    print("\n=== 召回质量报告 ===")
    print(f"Query              : {report['query']}")
    print(f"Index              : {report['index_path']}")
    print(f"Embedding backend  : {report['embedding_backend']}")
    print(f"Results returned   : {report['top_k_returned']}/{report['top_k_requested']}")
    print(f"Genre coverage     : {report['genre_coverage']['unique_genres']} unique genres")
    print(f"Description filled : {report['description_coverage'] * 100:.1f}%")
    print(f"Rating filled      : {report['rating_coverage'] * 100:.1f}%")
    print(f"Source distribution: {report['source_distribution']}")
    print("\nTop-5 样本:")
    for s in report["top5_sample"]:
        desc_mark = "✓" if s["has_description"] else "✗"
        print(f"  [{s['rank']}] {s['title']} | score={s['score']} | genres={s['genres']} | desc={desc_mark} | rating={s['rating']}")
    print(f"\nTop-10 genres: {report['genre_coverage']['top10_genres']}")

    ARTIFACTS_DIR.mkdir(exist_ok=True)
    out = ARTIFACTS_DIR / "recall_quality_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[info] 报告已保存 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
