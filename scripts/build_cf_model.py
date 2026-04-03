from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.neighbors import NearestNeighbors

from services.data_paths import get_processed_data_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTERACTIONS_PATH = get_processed_data_path("merged", "interactions_merged.jsonl")
DEFAULT_OUT_DIR = get_processed_data_path()
DEFAULT_ALS_MODEL_PATH = PROJECT_ROOT / "data" / "als_model.npz"
DEFAULT_USER_SIM_PATH = PROJECT_ROOT / "data" / "user_sim.bin"


def _iter_jsonl(path: Path) -> Iterable[Dict[str, object]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _build_indices(path: Path) -> Tuple[Dict[str, int], Dict[str, int], List[Tuple[int, int, float]]]:
    user_to_idx: Dict[str, int] = {}
    book_to_idx: Dict[str, int] = {}
    rows: List[int] = []
    cols: List[int] = []
    values: List[float] = []

    for row in _iter_jsonl(path):
        user_id = str(row.get("user_id") or "").strip()
        book_id = str(row.get("book_id") or "").strip()
        if not user_id or not book_id:
            continue

        try:
            rating = float(row.get("rating") or 0.0)
        except (TypeError, ValueError):
            rating = 0.0

        if user_id not in user_to_idx:
            user_to_idx[user_id] = len(user_to_idx)
        if book_id not in book_to_idx:
            book_to_idx[book_id] = len(book_to_idx)

        rows.append(user_to_idx[user_id])
        cols.append(book_to_idx[book_id])
        values.append(rating)

    triples = list(zip(rows, cols, values))
    return user_to_idx, book_to_idx, triples


def _build_indices_from_user_behavior_events(runtime_db: Path) -> Tuple[Dict[str, int], Dict[str, int], List[Tuple[int, int, float]]]:
    if not runtime_db.exists():
        return {}, {}, []
    conn = sqlite3.connect(str(runtime_db))
    conn.row_factory = sqlite3.Row
    try:
        try:
            rows = conn.execute(
                """
                SELECT user_id, book_id, weight, rating
                FROM user_behavior_events
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return {}, {}, []
    finally:
        conn.close()

    user_to_idx: Dict[str, int] = {}
    book_to_idx: Dict[str, int] = {}
    triples: List[Tuple[int, int, float]] = []
    for row in rows:
        user_id = str(row["user_id"] or "").strip()
        book_id = str(row["book_id"] or "").strip()
        if not user_id or not book_id:
            continue
        rating_raw = row["rating"]
        weight_raw = row["weight"]
        score = float(rating_raw) if rating_raw is not None else float(weight_raw or 0.0)
        if score <= 0:
            continue
        if user_id not in user_to_idx:
            user_to_idx[user_id] = len(user_to_idx)
        if book_id not in book_to_idx:
            book_to_idx[book_id] = len(book_to_idx)
        triples.append((user_to_idx[user_id], book_to_idx[book_id], score))
    return user_to_idx, book_to_idx, triples


def _save_user_similarity_index(user_factors: np.ndarray, out_path: Path) -> str:
    """Persist user similarity index; use hnswlib when available, sklearn fallback otherwise."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import hnswlib  # type: ignore

        dim = int(user_factors.shape[1])
        index = hnswlib.Index(space="cosine", dim=dim)
        index.init_index(max_elements=int(user_factors.shape[0]), ef_construction=200, M=16)
        index.add_items(user_factors, ids=np.arange(user_factors.shape[0], dtype=np.int32))
        index.set_ef(100)
        index.save_index(str(out_path))
        return "hnswlib"
    except Exception:
        nbrs = NearestNeighbors(metric="cosine", algorithm="brute")
        nbrs.fit(user_factors)
        with out_path.open("wb") as f:
            np.savez(
                f,
                backend="sklearn_fallback",
                vectors=user_factors.astype(np.float32),
            )
        return "sklearn_fallback"


def build_cf_model(
    interactions_path: Path = DEFAULT_INTERACTIONS_PATH,
    out_dir: Path = DEFAULT_OUT_DIR,
    als_model_path: Path = DEFAULT_ALS_MODEL_PATH,
    user_sim_path: Path = DEFAULT_USER_SIM_PATH,
    runtime_db_path: Path = PROJECT_ROOT / "data" / "recommendation_runtime.db",
    n_components: int = 50,
) -> Dict[str, object]:
    if interactions_path.exists():
        user_to_idx, book_to_idx, triples = _build_indices(interactions_path)
        source = f"jsonl:{interactions_path}"
    else:
        user_to_idx, book_to_idx, triples = _build_indices_from_user_behavior_events(runtime_db_path)
        source = f"sqlite:{runtime_db_path}"
    if not triples:
        raise RuntimeError(
            "No valid user-book-rating rows found. "
            f"Checked interactions file ({interactions_path}) and fallback DB ({runtime_db_path})."
        )

    user_count = len(user_to_idx)
    book_count = len(book_to_idx)
    rows, cols, values = zip(*triples)

    interaction_matrix = csr_matrix(
        (np.asarray(values, dtype=np.float32), (np.asarray(rows), np.asarray(cols))),
        shape=(user_count, book_count),
        dtype=np.float32,
    )

    max_components = min(max(2, n_components), max(2, min(interaction_matrix.shape) - 1))
    svd = TruncatedSVD(n_components=max_components, random_state=42)

    user_factors = svd.fit_transform(interaction_matrix).astype(np.float32)
    item_factors = svd.components_.T.astype(np.float32)

    out_dir.mkdir(parents=True, exist_ok=True)

    user_factors_path = out_dir / "cf_user_factors.npy"
    item_factors_path = out_dir / "cf_item_factors.npy"
    book_index_path = out_dir / "cf_book_id_index.json"
    user_index_path = out_dir / "cf_user_id_index.json"

    np.save(user_factors_path, user_factors)
    np.save(item_factors_path, item_factors)
    als_model_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        als_model_path,
        algorithm="truncated_svd",
        user_factors=user_factors,
        item_factors=item_factors,
        n_components=max_components,
    )
    user_sim_backend = _save_user_similarity_index(user_factors, user_sim_path)

    with book_index_path.open("w", encoding="utf-8") as f:
        json.dump(book_to_idx, f, ensure_ascii=False)

    with user_index_path.open("w", encoding="utf-8") as f:
        json.dump(user_to_idx, f, ensure_ascii=False)

    return {
        "interactions_path": str(interactions_path),
        "source": source,
        "user_count": user_count,
        "book_count": book_count,
        "interaction_count": len(triples),
        "n_components": max_components,
        "explained_variance_ratio_sum": float(np.sum(svd.explained_variance_ratio_)),
        "outputs": {
            "cf_user_factors": str(user_factors_path),
            "cf_item_factors": str(item_factors_path),
            "cf_book_id_index": str(book_index_path),
            "cf_user_id_index": str(user_index_path),
            "als_model": str(als_model_path),
            "user_similarity_index": str(user_sim_path),
            "user_similarity_backend": user_sim_backend,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build pre-factored CF model from merged interactions")
    parser.add_argument(
        "--interactions",
        type=Path,
        default=DEFAULT_INTERACTIONS_PATH,
        help="Path to interactions_train.jsonl",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory to write CF artifacts",
    )
    parser.add_argument(
        "--als-model",
        type=Path,
        default=DEFAULT_ALS_MODEL_PATH,
        help="Path to write ALS/SVD bundle (.npz) expected by Phase 1 docs",
    )
    parser.add_argument(
        "--user-sim-index",
        type=Path,
        default=DEFAULT_USER_SIM_PATH,
        help="Path to write user similarity index (hnswlib or fallback bundle)",
    )
    parser.add_argument(
        "--runtime-db",
        type=Path,
        default=PROJECT_ROOT / "data" / "recommendation_runtime.db",
        help="SQLite runtime DB used as fallback interaction source",
    )
    parser.add_argument(
        "--components",
        type=int,
        default=50,
        help="Requested number of SVD latent components",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary = build_cf_model(
        interactions_path=args.interactions,
        out_dir=args.out_dir,
        als_model_path=args.als_model,
        user_sim_path=args.user_sim_index,
        runtime_db_path=args.runtime_db,
        n_components=args.components,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
