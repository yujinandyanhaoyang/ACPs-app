from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

from services.data_paths import get_processed_data_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOOKS_PATH = get_processed_data_path("merged", "books_master_merged.jsonl")
DEFAULT_OUT_PATH = PROJECT_ROOT / "data" / "book_faiss.index"
DEFAULT_META_PATH = PROJECT_ROOT / "data" / "book_faiss.meta.json"


def _iter_books(path: Path) -> Iterable[Dict[str, object]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def _book_key(row: Dict[str, object]) -> str:
    return str(row.get("book_id") or row.get("id") or "").strip()


def _book_text(row: Dict[str, object]) -> str:
    title = str(row.get("title") or "")
    author = str(row.get("author") or "")
    description = str(row.get("description") or "")
    genres = row.get("genres")
    genre_text = " ".join(str(g) for g in genres) if isinstance(genres, list) else ""
    return "\n".join(part for part in [title, author, genre_text, description] if part)


def _hash_embed(text: str, dim: int) -> np.ndarray:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big", signed=False)
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(size=(dim,), dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm <= 0:
        return vec
    return vec / norm


def _encode_texts(texts: List[str], dim: int, model_name: str) -> Tuple[np.ndarray, str]:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        model = SentenceTransformer(model_name)
        embeddings = model.encode(
            texts,
            batch_size=64,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype(np.float32)
        if embeddings.shape[1] != dim:
            raise RuntimeError(f"Embedding dimension mismatch: expected {dim}, got {embeddings.shape[1]}")
        return embeddings, "sentence_transformers"
    except Exception:
        vectors = [_hash_embed(t, dim=dim) for t in texts]
        return np.vstack(vectors).astype(np.float32), "hash_fallback"


def build_index(
    books_path: Path,
    out_path: Path,
    out_meta_path: Path,
    dim: int = 384,
    ef_construction: int = 200,
    m: int = 32,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    limit: int = 0,
) -> Dict[str, object]:
    if not books_path.exists():
        raise FileNotFoundError(f"Books corpus not found: {books_path}")

    ids: List[str] = []
    texts: List[str] = []
    for row in _iter_books(books_path):
        book_id = _book_key(row)
        if not book_id:
            continue
        text = _book_text(row)
        if not text:
            continue
        ids.append(book_id)
        texts.append(text)
        if limit > 0 and len(ids) >= limit:
            break

    if not ids:
        raise RuntimeError("No valid book records available to build index")

    embeddings, encoder_backend = _encode_texts(texts, dim=dim, model_name=model_name)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_meta_path.parent.mkdir(parents=True, exist_ok=True)

    index_backend = "faiss"
    try:
        import faiss  # type: ignore

        index = faiss.IndexHNSWFlat(dim, m)
        index.hnsw.efConstruction = ef_construction
        index.add(embeddings)
        faiss.write_index(index, str(out_path))
    except Exception:
        index_backend = "numpy_fallback"
        with out_path.open("wb") as f:
            np.savez(
                f,
                embeddings=embeddings,
                ids=np.asarray(ids, dtype=object),
                metric="cosine",
            )

    meta = {
        "books_path": str(books_path),
        "index_path": str(out_path),
        "book_count": len(ids),
        "dimension": dim,
        "encoder_backend": encoder_backend,
        "index_backend": index_backend,
        "hnsw": {"m": m, "ef_construction": ef_construction},
    }
    out_meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build book ANN index for Recommendation Engine RecallModule")
    parser.add_argument("--books", type=Path, default=DEFAULT_BOOKS_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META_PATH)
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--dim", type=int, default=384)
    parser.add_argument("--hnsw-m", type=int, default=32)
    parser.add_argument("--hnsw-ef-construction", type=int, default=200)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary = build_index(
        books_path=args.books,
        out_path=args.out,
        out_meta_path=args.meta,
        dim=int(args.dim),
        ef_construction=int(args.hnsw_ef_construction),
        m=int(args.hnsw_m),
        model_name=str(args.model),
        limit=int(args.limit),
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
