from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import faiss  # type: ignore
from services.book_retrieval import retrieve_books_by_vector
from services.model_backends import generate_text_embeddings

SMOKE_INDEX_PATH = Path(os.environ.get("SMOKE_INDEX_PATH", "/root/WORK/DATA/processed/books_index.faiss"))
SMOKE_META_PATH = Path(os.environ.get("SMOKE_META_PATH", "/root/WORK/DATA/processed/books_index_meta.jsonl"))
MASTER_PATH = Path("/root/WORK/DATA/processed/books_master_merged.jsonl")
QUERY = "a mystery novel with psychological thriller elements"
TOP_K = 20


def _load_index_ntotal(index_path: Path) -> int:
    if not index_path.exists():
        return 0
    try:
        index = faiss.read_index(str(index_path))
        return int(getattr(index, "ntotal", 0))
    except Exception:
        return 0


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _load_master_by_id(path: Path) -> Dict[str, Dict[str, Any]]:
    books: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return books
    with path.open("r", encoding="utf-8") as f:
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
            book_id = _safe_str(row.get("book_id") or row.get("id"))
            if book_id and book_id not in books:
                books[book_id] = row
    return books


def _print_result(i: int, row: Dict[str, Any]) -> None:
    title = _safe_str(row.get("title"))
    genres = row.get("genres") if isinstance(row.get("genres"), list) else []
    description = _safe_str(row.get("description"))
    rating = row.get("rating")
    score = row.get("score")
    print(f"[{i}] title={title}")
    print(f"     genres={genres}")
    print(f"     description={description[:80]}...")
    print(f"     rating={rating}")
    print(f"     score={float(score):.4f}" if isinstance(score, (int, float)) else f"     score={score}")


def _okfail(ok: bool, message: str) -> None:
    print(f"[{'OK' if ok else 'FAIL'}] {message}")


def main() -> int:
    ntotal = _load_index_ntotal(SMOKE_INDEX_PATH)
    print(f"[info] index ntotal: {ntotal}")

    query_vectors, embed_meta = generate_text_embeddings(
        [QUERY],
        model_name="all-MiniLM-L6-v2",
        fallback_dim=384,
    )
    print(f"[info] embedding backend: {embed_meta['backend']}")
    assert embed_meta["backend"] == "sentence-transformers", (
        f"expected sentence-transformers, got {embed_meta['backend']}"
    )
    query_vector = query_vectors[0]

    results = retrieve_books_by_vector(
        query_vector,
        top_k=TOP_K,
        index_path=SMOKE_INDEX_PATH,
        meta_path=SMOKE_META_PATH,
    )

    master_by_id = _load_master_by_id(MASTER_PATH)
    enriched_results: List[Dict[str, Any]] = []
    for row in results:
        merged = dict(master_by_id.get(_safe_str(row.get("book_id")), {}))
        merged.update(row)
        enriched_results.append(merged)

    n = len(enriched_results)
    for i, row in enumerate(enriched_results[:3], start=1):
        _print_result(i, row)

    _okfail(n == TOP_K, f"retrieve returned {n} results (expected 20)")
    _okfail(all(_safe_str(r.get("title")) for r in enriched_results), "all results have non-empty title")
    _okfail(
        all(_safe_str(r.get("description")) for r in enriched_results),
        "all results have non-empty description",
    )
    _okfail(
        all(isinstance(r.get("genres"), list) for r in enriched_results),
        "all results have genres as list",
    )
    non_null_rating = sum(1 for r in enriched_results if r.get("rating") is not None)
    print(f"[{'OK' if non_null_rating > 0 else 'WARN'}] {non_null_rating}/20 have non-null rating")
    _okfail(all("score" in r for r in enriched_results), "all results have score field")

    bca_ready = all(
        _safe_str(r.get("book_id"))
        and _safe_str(r.get("title"))
        and _safe_str(r.get("description"))
        and isinstance(r.get("genres"), list)
        for r in enriched_results
    )
    _okfail(bca_ready, "BCA input fields present in all 20 results")

    ranking_ready = all(
        isinstance(r.get("genres"), list) and (r.get("rating") is None or isinstance(r.get("rating"), (int, float)))
        for r in enriched_results
    )
    _okfail(ranking_ready, "ranking agent fields valid in all 20 results")

    blockers: List[str] = []
    if n != TOP_K:
        blockers.append("retrieve_books_by_vector did not return 20 results")
    if not all(_safe_str(r.get("title")) for r in enriched_results):
        blockers.append("some results have empty title")
    if not all(_safe_str(r.get("description")) for r in enriched_results):
        blockers.append("some results have empty description")
    if not all(isinstance(r.get("genres"), list) for r in enriched_results):
        blockers.append("some results have non-list genres")
    if not all("score" in r for r in enriched_results):
        blockers.append("some results are missing score")
    if not bca_ready:
        blockers.append("BCA input incompatibility")
    if not ranking_ready:
        blockers.append("ranking input incompatibility")

    print("=== Pipeline Smoke Test ===")
    print(f"Index records : {ntotal}")
    print(f'Query         : "{QUERY}"')
    print(f"Results       : {n}/20")
    print(f"BCA ready     : {'YES' if bca_ready else 'NO'}")
    print(f"Ranking ready : {'YES' if ranking_ready else 'NO'}")
    print(f"Blockers      : {'none' if not blockers else '; '.join(blockers)}")

    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
