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

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

SMOKE_INDEX_PATH = Path(os.environ.get("SMOKE_INDEX_PATH", "/root/WORK/DATA/processed/books_index.faiss"))
SMOKE_META_PATH = Path(os.environ.get("SMOKE_META_PATH", "/root/WORK/DATA/processed/books_index_meta.jsonl"))
MASTER_PATH = Path("/root/WORK/DATA/processed/books_master_merged.jsonl")
QUERY = "a mystery novel with psychological thriller elements"
TOP_K = 20
ENGINE_CONFIG_PATH = PROJECT_ROOT / "partners" / "online" / "recommendation_engine_agent" / "config.toml"


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


def _load_llm_config() -> Dict[str, Any]:
    if not tomllib or not ENGINE_CONFIG_PATH.exists():
        raise RuntimeError(f"missing config file: {ENGINE_CONFIG_PATH}")
    data = tomllib.loads(ENGINE_CONFIG_PATH.read_text(encoding="utf-8"))
    llm = data.get("llm") if isinstance(data, dict) else {}
    if not isinstance(llm, dict):
        raise RuntimeError(f"[llm] section missing in {ENGINE_CONFIG_PATH}")
    model = _safe_str(llm.get("model"))
    if not model:
        raise RuntimeError(f"llm model missing in {ENGINE_CONFIG_PATH}")
    temperature = float(llm.get("temperature") or 0.2)
    max_tokens = int(llm.get("max_tokens") or 1024)
    gap_fill = llm.get("gap_fill") if isinstance(llm, dict) else {}
    gap_fill_max_tokens = int(gap_fill.get("max_tokens") or 256) if isinstance(gap_fill, dict) else 256
    return {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "gap_fill_max_tokens": gap_fill_max_tokens,
    }


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

    # ── Phase 2: Full REA pipeline (recall → rank → explain) ──────────────
    print("\n=== Phase 2: REA Pipeline Smoke Test ===")

    from partners.online.recommendation_engine_agent.modules.recall import recall_candidates
    from partners.online.recommendation_engine_agent.modules.ranking import rerank_round2, score_round1
    from partners.online.recommendation_engine_agent.modules.explanation import assess_confidence, generate_rationale
    import asyncio as _asyncio
    import json as _json

    _ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
    _ARTIFACTS_DIR.mkdir(exist_ok=True)

    rea_payload = {
        "candidates": enriched_results,
        "profile_vector": query_vector,
        "preferred_genres": ["Mystery", "Thriller"],
        "user_profile": {
            "preferred_genres": ["Mystery", "Thriller"],
            "reading_history": ["Gone Girl", "The Girl on the Train"],
            "language": "zh",
        },
        "top_k": 5,
        "mmr_lambda": 0.5,
        "ann_weight": 0.6,
        "cf_weight": 0.4,
    }

    recall_cfg = {
        "faiss_index_path": str(SMOKE_INDEX_PATH),
        "als_model_path": "data/als_model.npz",
        "hnswlib_path": "data/user_sim.bin",
        "ann_ef_search": 100,
        "ann_top_k": len(enriched_results),
        "cf_top_k": len(enriched_results),
        "cf_sim_users": 50,
    }

    recalled, recall_meta = recall_candidates(rea_payload, recall_cfg)
    preliminary, r1_meta = score_round1(recalled, score_weights={}, top_k=max(20, 5 * 10))
    confidence_map = assess_confidence(preliminary)

    final_ranked, r2_meta = rerank_round2(
        preliminary_list=preliminary,
        confidence_list=confidence_map,
        mmr_lambda=0.5,
        confidence_penalty_threshold=0.6,
        penalty_multiplier=0.7,
        top_k=5,
    )

    try:
        import tomllib as _tomllib
        _prompts_path = PROJECT_ROOT / "partners/online/recommendation_engine_agent/prompts.toml"
        _prompts_data = _tomllib.loads(_prompts_path.read_text(encoding="utf-8")) if _prompts_path.exists() else {}
        _em = _prompts_data.get("explanation_main") or {}
        _ef = _prompts_data.get("explanation_fallback") or {}
        _prompts = {
            "main": str(_em.get("template") or "") if isinstance(_em, dict) else "",
            "fallback": str(_ef.get("template") or "") if isinstance(_ef, dict) else "",
        }
    except Exception:
        _prompts = {"main": "", "fallback": ""}

    llm_cfg = _load_llm_config()

    explanations = _asyncio.run(generate_rationale(
        final_list=final_ranked,
        payload=rea_payload,
        prompts=_prompts,
        llm_model=str(llm_cfg["model"]),
        llm_temperature=float(llm_cfg["temperature"]),
        llm_max_tokens=int(llm_cfg["max_tokens"]),
        gap_fill_max_tokens=int(llm_cfg["gap_fill_max_tokens"]),
    ))

    _okfail(len(final_ranked) == 5, f"final_ranked has 5 items (got {len(final_ranked)})")
    _okfail(all(_safe_str(r.get("title")) for r in final_ranked), "all top-5 have non-empty title")
    _okfail(all(r.get("rank") in range(1, 6) for r in final_ranked), "rank fields are 1-5")
    _okfail(
        all(float(r.get("score_total") or r.get("score_round1") or 0) > 0 for r in final_ranked),
        "all score_total > 0",
    )
    _okfail(len(explanations) == 5, f"explanations has 5 items (got {len(explanations)})")
    _okfail(any(_safe_str(e.get("justification")) for e in explanations), "at least 1 non-empty justification")

    llm_count = sum(1 for e in explanations if e.get("source") == "llm")
    fb_count = len(explanations) - llm_count
    print(f"LLM explanations : {llm_count}/5")
    print(f"Fallback         : {fb_count}/5")
    if final_ranked:
        top1 = final_ranked[0]
        top1_just = next(
            (e.get("justification", "") for e in explanations if e.get("book_id") == top1.get("book_id")), ""
        )
        print(f"Top-1            : {_safe_str(top1.get('title'))} — {str(top1_just)[:80]}")

    _result = {
        "query": QUERY,
        "index_ntotal": ntotal,
        "top5": [
            {
                "rank": r.get("rank"),
                "book_id": r.get("book_id"),
                "title": r.get("title"),
                "genres": r.get("genres"),
                "score_total": r.get("score_total"),
                "justification": next(
                    (e.get("justification") for e in explanations if e.get("book_id") == r.get("book_id")), ""
                ),
                "explanation_source": next(
                    (e.get("source") for e in explanations if e.get("book_id") == r.get("book_id")), "fallback"
                ),
            }
            for r in final_ranked
        ],
        "recall_meta": recall_meta,
        "ranking_meta": {"round1": r1_meta, "round2": r2_meta},
    }
    _out_path = _ARTIFACTS_DIR / "e2e_phase2_result.json"
    _out_path.write_text(_json.dumps(_result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[info] Phase 2 result saved → {_out_path}")
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
