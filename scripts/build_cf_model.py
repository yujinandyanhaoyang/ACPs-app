from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTERACTIONS_PATH = PROJECT_ROOT / "data" / "processed" / "goodreads" / "interactions_train.jsonl"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "processed"


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


def build_cf_model(
    interactions_path: Path = DEFAULT_INTERACTIONS_PATH,
    out_dir: Path = DEFAULT_OUT_DIR,
    n_components: int = 50,
) -> Dict[str, object]:
    if not interactions_path.exists():
        raise FileNotFoundError(f"interactions file not found: {interactions_path}")

    user_to_idx, book_to_idx, triples = _build_indices(interactions_path)
    if not triples:
        raise RuntimeError("No valid user-book-rating rows found in interactions file")

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

    with book_index_path.open("w", encoding="utf-8") as f:
        json.dump(book_to_idx, f, ensure_ascii=False)

    with user_index_path.open("w", encoding="utf-8") as f:
        json.dump(user_to_idx, f, ensure_ascii=False)

    return {
        "interactions_path": str(interactions_path),
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
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build pre-factored CF model from Goodreads interactions")
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
        "--components",
        type=int,
        default=50,
        help="Requested number of SVD latent components",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary = build_cf_model(args.interactions, args.out_dir, args.components)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
