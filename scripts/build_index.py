from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import faiss  # type: ignore
from services.book_retrieval import _book_text, load_books

_configured_root = (
    os.getenv("BOOK_RETRIEVAL_DATASET_PATH", "").strip()
    or os.getenv("DATASET_ROOT", "").strip()
)
DEFAULT_DATASET_ROOT = Path(_configured_root).expanduser() if _configured_root else PROJECT_ROOT / "data"
DEFAULT_INPUT_PATH = DEFAULT_DATASET_ROOT / "processed" / "books_master_merged.jsonl"
DEFAULT_INDEX_PATH = DEFAULT_DATASET_ROOT / "processed" / "books_index.faiss"
DEFAULT_META_PATH = DEFAULT_DATASET_ROOT / "processed" / "books_index_meta.jsonl"
DEFAULT_MODEL = os.getenv("BOOK_CONTENT_EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_DIM = 384


def _normalize_rows(vectors: Sequence[Sequence[float]]) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.size == 0:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)
    if matrix.shape[1] != EMBED_DIM:
        if matrix.shape[1] > EMBED_DIM:
            matrix = matrix[:, :EMBED_DIM]
        else:
            padded = np.zeros((matrix.shape[0], EMBED_DIM), dtype=np.float32)
            padded[:, : matrix.shape[1]] = matrix
            matrix = padded
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return (matrix / norms).astype(np.float32)


def build_index(
    books_path: Path,
    out_path: Path,
    out_meta_path: Path,
    model_name: str = DEFAULT_MODEL,
    limit: int = 0,
    batch_size: int = 1024,
) -> Dict[str, Any]:
    if not books_path.exists():
        raise FileNotFoundError(f"Books corpus not found: {books_path}")

    books = load_books(books_path, limit=limit if limit > 0 else None)
    if not books:
        raise RuntimeError(f"No valid book records available from {books_path}")

    batch_size = max(1, int(batch_size))
    index = faiss.IndexFlatIP(EMBED_DIM)
    started = time.perf_counter()

    from services.model_backends import generate_text_embeddings

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_meta_path.parent.mkdir(parents=True, exist_ok=True)
    with out_meta_path.open("w", encoding="utf-8") as meta_fp:
        for i in range(0, len(books), batch_size):
            batch = books[i : i + batch_size]
            texts = [_book_text(book) for book in batch]

            vectors, _meta = generate_text_embeddings(
                texts,
                model_name=model_name,
                fallback_dim=EMBED_DIM,
            )
            embeddings = _normalize_rows(vectors)
            index.add(embeddings)

            for j, book in enumerate(batch):
                meta_fp.write(
                    json.dumps(
                        {
                            "idx": i + j,
                            "book_id": str(book.get("book_id") or ""),
                            "source": str(book.get("source") or ""),
                            "title": str(book.get("title") or ""),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            meta_fp.flush()

            done = i + len(batch)
            print(
                f"[progress] {done}/{len(books)} ({done / len(books) * 100:.1f}%) batch={batch_size}",
                flush=True,
            )

    faiss.write_index(index, str(out_path))
    elapsed = time.perf_counter() - started
    return {
        "records_indexed": len(books),
        "embedding_dim": EMBED_DIM,
        "index_type": "IndexFlatIP",
        "index_path": str(out_path),
        "meta_path": str(out_meta_path),
        "elapsed_seconds": elapsed,
        "batch_size": batch_size,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the vector retrieval index for books_master_merged.jsonl")
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N books")
    parser.add_argument("--batch-size", type=int, default=1024, help="Embedding batch size")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Embedding model name")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META_PATH)
    return parser.parse_args()


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    args = _parse_args()
    started = time.perf_counter()
    summary = build_index(
        books_path=args.input,
        out_path=args.index,
        out_meta_path=args.meta,
        model_name=str(args.model),
        limit=int(args.limit),
        batch_size=int(args.batch_size),
    )
    elapsed = time.perf_counter() - started

    print("=== Index Build Complete ===")
    print(f"Records indexed  : {summary['records_indexed']}")
    print(f"Embedding dim    : {summary['embedding_dim']}")
    print(f"Index type       : {summary['index_type']}")
    print(f"Index saved to   : {summary['index_path']}")
    print(f"Meta saved to    : {summary['meta_path']}")
    print(f"Batch size       : {summary['batch_size']}")
    print(f"Elapsed          : {elapsed:.1f}s")


if __name__ == "__main__":
    main()
