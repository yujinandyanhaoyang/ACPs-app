from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List
from datetime import datetime, timezone

_CURRENT_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from services.book_retrieval import load_books, retrieve_books_by_query
from services.model_backends import estimate_collaborative_scores_with_svd, load_cf_item_vectors
from services.data_paths import get_processed_data_path
import reading_concierge.reading_concierge as concierge

PROJECT_ROOT = Path(_PROJECT_ROOT)
DEFAULT_CASES_PATH = PROJECT_ROOT / "scripts" / "phase4_cases.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "scripts" / "pretrained_cf_coverage_report.json"
DEFAULT_INTERACTIONS_PATH = get_processed_data_path("goodreads", "interactions_train.jsonl")


def _load_cases(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("cases file must be a JSON list")
    return [row for row in payload if isinstance(row, dict)]


def _book_id(row: Dict[str, Any]) -> str:
    return str(row.get("book_id") or row.get("id") or "").strip()


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _build_books_index(books: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for row in books:
        if not isinstance(row, dict):
            continue
        bid = _book_id(row)
        if not bid:
            continue
        if bid not in index:
            index[bid] = row
    return index


def _resolve_case_candidates(
    case: Dict[str, Any],
    books_index: Dict[str, Dict[str, Any]],
    full_books: List[Dict[str, Any]],
    default_pool: int,
) -> List[Dict[str, Any]]:
    explicit_books = case.get("books") or []
    if isinstance(explicit_books, list) and explicit_books:
        return [row for row in explicit_books if isinstance(row, dict)]

    candidate_ids = case.get("candidate_ids") or []
    candidates: List[Dict[str, Any]] = []
    if isinstance(candidate_ids, list) and candidate_ids:
        for cid in candidate_ids:
            row = books_index.get(str(cid))
            if row:
                candidates.append(row)

    if candidates:
        return candidates

    query = str(case.get("query") or "").strip()
    if query:
        return retrieve_books_by_query(query=query, books=full_books, top_k=default_pool)

    return full_books[: max(1, default_pool)]


def _compute_case_coverage(
    case: Dict[str, Any],
    cf_item_vectors: Dict[str, List[float]],
    books_index: Dict[str, Dict[str, Any]],
    full_books: List[Dict[str, Any]],
    default_pool: int,
) -> Dict[str, Any]:
    case_id = str(case.get("case_id") or "unknown_case")
    history = case.get("history") if isinstance(case.get("history"), list) else []
    query = str(case.get("query") or "").strip()
    candidate_ids = case.get("candidate_ids") if isinstance(case.get("candidate_ids"), list) else []
    if query:
        try:
            candidates = asyncio.run(concierge._derive_books_from_query(query, candidate_ids))
        except Exception:
            candidates = _resolve_case_candidates(case, books_index, full_books, default_pool)
    else:
        candidates = _resolve_case_candidates(case, books_index, full_books, default_pool)

    candidate_ids: List[str] = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        bid = _book_id(row)
        if bid:
            candidate_ids.append(bid)

    covered_count = sum(1 for cid in candidate_ids if cid in cf_item_vectors)
    candidate_count = len(candidate_ids)
    direct_coverage_rate = round(covered_count / max(1, candidate_count), 4)

    scores, backend_meta = estimate_collaborative_scores_with_svd(
        history=history,
        candidates=candidates,
        n_components=8,
    )

    return {
        "case_id": case_id,
        "query": query,
        "candidate_count": candidate_count,
        "covered_count": covered_count,
        "direct_coverage_rate": direct_coverage_rate,
        "backend": backend_meta.get("backend"),
        "pretrained_candidate_coverage": backend_meta.get("pretrained_candidate_coverage", 0.0),
        "history_items": int(backend_meta.get("history_items") or 0),
        "scored_items": len(scores),
    }


def _derive_query_from_history(history_books: List[Dict[str, Any]]) -> str:
    shelf_tags = {
        "to_read",
        "currently_reading",
        "favorites",
        "owned",
        "owned_books",
        "default",
        "kindle",
        "books_i_own",
        "audiobook",
    }
    genre_counts: Dict[str, int] = {}
    for row in history_books:
        for genre in row.get("genres") or []:
            token = str(genre).replace("_", " ").strip().lower()
            if not token:
                continue
            if token.replace(" ", "_") in shelf_tags:
                continue
            genre_counts[token] = genre_counts.get(token, 0) + 1
    top_genres = [k for k, _ in sorted(genre_counts.items(), key=lambda item: item[1], reverse=True)[:3]]
    if top_genres:
        return "recommend books about " + ", ".join(top_genres)

    title_terms: Dict[str, int] = {}
    for row in history_books:
        title = str(row.get("title") or "").strip().lower()
        for token in title.split():
            token = token.strip(".,:;!?")
            if len(token) < 4:
                continue
            title_terms[token] = title_terms.get(token, 0) + 1
    top_terms = [k for k, _ in sorted(title_terms.items(), key=lambda item: item[1], reverse=True)[:3]]
    if top_terms:
        return "recommend books like " + " ".join(top_terms)

    return "recommend books"


def _build_real_user_cases(
    interactions_path: Path,
    books_index: Dict[str, Dict[str, Any]],
    sample_users: int,
    min_history: int,
) -> List[Dict[str, Any]]:
    if not interactions_path.exists():
        raise FileNotFoundError(f"interactions file not found: {interactions_path}")

    per_user: Dict[str, List[Dict[str, Any]]] = {}
    for row in _iter_jsonl(interactions_path):
        user_id = str(row.get("user_id") or "").strip()
        book_id = str(row.get("book_id") or "").strip()
        if not user_id or not book_id:
            continue
        book = books_index.get(book_id)
        if not book:
            continue
        try:
            rating = float(row.get("rating") or 0.0)
        except (TypeError, ValueError):
            rating = 0.0

        per_user.setdefault(user_id, []).append(
            {
                "book_id": book_id,
                "title": book.get("title"),
                "genres": book.get("genres") or [],
                "themes": book.get("themes") or [],
                "rating": rating,
                "language": book.get("language") or "en",
            }
        )

    cases: List[Dict[str, Any]] = []
    for user_id, rows in per_user.items():
        if len(rows) < min_history:
            continue
        history = rows[:min(8, len(rows))]
        query = _derive_query_from_history(history)
        cases.append(
            {
                "case_id": f"real_user_{user_id}",
                "query": query,
                "history": history,
                "constraints": {"scenario": "warm", "top_k": 5},
            }
        )
        if len(cases) >= sample_users:
            break
    return cases


def build_report(
    source: str,
    cases_path: Path,
    interactions_path: Path,
    report_path: Path,
    default_pool: int,
    threshold: float,
    sample_users: int,
    min_history: int,
) -> Dict[str, Any]:
    if source == "phase4-cases" and not cases_path.exists():
        raise FileNotFoundError(f"cases file not found: {cases_path}")

    cf_item_vectors = load_cf_item_vectors(force_reload=True)
    if not cf_item_vectors:
        raise RuntimeError(
            "No pre-factored CF vectors found. Run scripts/build_cf_model.py first."
        )

    books = load_books()
    books_index = _build_books_index(books)

    if source == "phase4-cases":
        cases = _load_cases(cases_path)
    else:
        cases = _build_real_user_cases(
            interactions_path=interactions_path,
            books_index=books_index,
            sample_users=sample_users,
            min_history=min_history,
        )

    if not cases:
        raise RuntimeError("No valid cases/payloads generated for coverage verification")

    case_rows: List[Dict[str, Any]] = []
    for case in cases:
        case_rows.append(
            _compute_case_coverage(
                case=case,
                cf_item_vectors=cf_item_vectors,
                books_index=books_index,
                full_books=books,
                default_pool=default_pool,
            )
        )

    direct_coverages = [float(row["direct_coverage_rate"]) for row in case_rows]
    meta_coverages = [float(row["pretrained_candidate_coverage"] or 0.0) for row in case_rows]
    passing_cases = [row for row in case_rows if float(row["pretrained_candidate_coverage"] or 0.0) >= threshold]

    summary = {
        "case_count": len(case_rows),
        "threshold": threshold,
        "mean_direct_coverage": round(mean(direct_coverages), 4) if direct_coverages else 0.0,
        "median_direct_coverage": round(median(direct_coverages), 4) if direct_coverages else 0.0,
        "mean_pretrained_candidate_coverage": round(mean(meta_coverages), 4) if meta_coverages else 0.0,
        "median_pretrained_candidate_coverage": round(median(meta_coverages), 4) if meta_coverages else 0.0,
        "cases_meeting_threshold": len(passing_cases),
        "pass_rate": round(len(passing_cases) / max(1, len(case_rows)), 4),
        "all_cases_meet_threshold": len(passing_cases) == len(case_rows),
    }

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {
            "source": source,
            "cases_path": str(cases_path),
            "interactions_path": str(interactions_path),
            "book_dataset_path": os.getenv("BOOK_RETRIEVAL_DATASET_PATH") or "auto",
            "cf_item_factors_path": os.getenv("CF_ITEM_FACTORS_PATH") or str(get_processed_data_path("cf_item_factors.npy")),
            "cf_book_index_path": os.getenv("CF_BOOK_INDEX_PATH") or str(get_processed_data_path("cf_book_id_index.json")),
            "default_candidate_pool": default_pool,
            "sample_users": sample_users,
            "min_history": min_history,
        },
        "summary": summary,
        "case_rows": case_rows,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify pretrained CF coverage on real ranking-like request payloads"
    )
    parser.add_argument(
        "--source",
        choices=["real-users", "phase4-cases"],
        default="real-users",
        help="Payload source: real users from interactions_train (default) or phase4 benchmark cases",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to benchmark cases JSON (default: scripts/phase4_cases.json)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Where to write the JSON report",
    )
    parser.add_argument(
        "--candidate-pool",
        type=int,
        default=30,
        help="Fallback retrieval candidate pool when a case has no explicit books",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Coverage threshold used for pass-rate summary",
    )
    parser.add_argument(
        "--interactions",
        type=Path,
        default=DEFAULT_INTERACTIONS_PATH,
        help="Path to interactions_train.jsonl used for real-users payload generation",
    )
    parser.add_argument(
        "--sample-users",
        type=int,
        default=50,
        help="Number of real user payloads to evaluate when --source=real-users",
    )
    parser.add_argument(
        "--min-history",
        type=int,
        default=3,
        help="Minimum history length required to include a real user payload",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    report = build_report(
        source=args.source,
        cases_path=args.cases,
        interactions_path=args.interactions,
        report_path=args.report,
        default_pool=max(1, args.candidate_pool),
        threshold=max(0.0, min(1.0, args.threshold)),
        sample_users=max(1, args.sample_users),
        min_history=max(1, args.min_history),
    )

    summary = report["summary"]
    print("[CF Coverage] report:", args.report)
    print(
        "[CF Coverage] source=", args.source,
        "[CF Coverage] cases=", summary["case_count"],
        "mean_pretrained=", summary["mean_pretrained_candidate_coverage"],
        "pass_rate=", summary["pass_rate"],
        "threshold=", summary["threshold"],
    )
