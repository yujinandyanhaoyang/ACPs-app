from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import multiprocessing as mp
import os
import sys
import tempfile
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
from services.model_backends import generate_text_embeddings, generate_text_embeddings_async

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
EMBED_BATCH_SIZE = 1024


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


def _split_evenly(items: Sequence[Dict[str, Any]], parts: int) -> List[List[Dict[str, Any]]]:
    parts = max(1, min(int(parts), len(items)))
    if parts <= 1:
        return [list(items)]
    total = len(items)
    base = total // parts
    remainder = total % parts
    chunks: List[List[Dict[str, Any]]] = []
    start = 0
    for index in range(parts):
        size = base + (1 if index < remainder else 0)
        end = start + size
        chunks.append(list(items[start:end]))
        start = end
    return chunks


async def _embed_texts_async(texts: Sequence[str], model_name: str) -> np.ndarray:
    vectors, _meta = await generate_text_embeddings_async(
        texts,
        model_name=model_name,
        fallback_dim=EMBED_DIM,
    )
    return _normalize_rows(vectors)


async def _embed_chunk_async(books_chunk: Sequence[Dict[str, Any]], model_name: str) -> np.ndarray:
    texts = [_book_text(book) for book in books_chunk]
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)

    batches: List[np.ndarray] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        batch_vectors = await _embed_texts_async(batch, model_name=model_name)
        batches.append(batch_vectors)
    if not batches:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)
    return np.vstack(batches).astype(np.float32)


def _worker_embed_chunk(task: Tuple[int, List[Dict[str, Any]], str, str]) -> Tuple[int, str, str, int, Dict[str, Any]]:
    chunk_id, books_chunk, model_name, temp_dir, thread_limit = task
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("OPENAI_BASE_URL", None)
    if thread_limit > 0:
        os.environ["OMP_NUM_THREADS"] = str(thread_limit)
        os.environ["MKL_NUM_THREADS"] = str(thread_limit)
        os.environ["OPENBLAS_NUM_THREADS"] = str(thread_limit)
        os.environ["NUMEXPR_NUM_THREADS"] = str(thread_limit)
        try:
            import torch  # type: ignore

            torch.set_num_threads(thread_limit)
            torch.set_num_interop_threads(1)
        except Exception:
            pass
    embeddings = asyncio.run(_embed_chunk_async(books_chunk, model_name=model_name))
    temp_root = Path(temp_dir)
    embed_path = temp_root / f"chunk_{chunk_id:04d}.npy"
    meta_path = temp_root / f"chunk_{chunk_id:04d}.jsonl"
    np.save(embed_path, embeddings.astype(np.float32))
    with meta_path.open("w", encoding="utf-8") as meta_fp:
        for book in books_chunk:
            meta_fp.write(
                json.dumps(
                    {
                        "book_id": str(book.get("book_id") or ""),
                        "source": str(book.get("source") or ""),
                        "title": str(book.get("title") or ""),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return chunk_id, str(embed_path), str(meta_path), len(books_chunk), {
        "backend": "sentence-transformers-or-fallback",
        "model": model_name,
        "records": len(books_chunk),
    }


def _warm_model(model_name: str) -> None:
    # Load once in the parent so forked workers can reuse the cached model when supported.
    generate_text_embeddings(["warmup"], model_name=model_name, fallback_dim=EMBED_DIM)


def _build_index_from_temp_files(
    chunk_results: Dict[int, Tuple[str, str, int, Dict[str, Any]]],
    total_count: int,
    index_path: Path,
    meta_path: Path,
) -> None:
    index = faiss.IndexFlatIP(EMBED_DIM)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    row_index = 0
    with meta_path.open("w", encoding="utf-8") as meta_fp:
        for chunk_id in sorted(chunk_results):
            embed_file, meta_file, count, _chunk_meta = chunk_results[chunk_id]
            embeddings = np.load(embed_file, allow_pickle=False)
            if embeddings.shape[0] != count:
                raise RuntimeError(
                    f"embedding count mismatch for chunk_index={chunk_id}: "
                    f"{embeddings.shape[0]} vs {count}"
                )
            index.add(_normalize_rows(embeddings))

            with Path(meta_file).open("r", encoding="utf-8") as chunk_meta_fp:
                for offset, line in enumerate(chunk_meta_fp):
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    meta_fp.write(
                        json.dumps(
                            {
                                "idx": row_index + offset,
                                "book_id": str(row.get("book_id") or ""),
                                "source": str(row.get("source") or ""),
                                "title": str(row.get("title") or ""),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            meta_fp.flush()
            row_index += count

    if row_index != total_count:
        raise RuntimeError(f"row count mismatch: expected {total_count}, wrote {row_index}")

    faiss.write_index(index, str(index_path))


def build_index(
    books_path: Path,
    out_path: Path,
    out_meta_path: Path,
    model_name: str = DEFAULT_MODEL,
    limit: int = 0,
    workers: int = 1,
) -> Dict[str, Any]:
    if not books_path.exists():
        raise FileNotFoundError(f"Books corpus not found: {books_path}")

    books = load_books(books_path, limit=limit if limit > 0 else None)
    if not books:
        raise RuntimeError(f"No valid book records available from {books_path}")

    workers = max(1, int(workers))
    chunks = _split_evenly(books, workers)
    if not chunks:
        raise RuntimeError("No chunks generated for index build")

    started = time.perf_counter()
    _warm_model(model_name)

    temp_dir = tempfile.mkdtemp(prefix="book_index_")
    chunk_results: Dict[int, Tuple[str, str, int, Dict[str, Any]]] = {}
    ctx_name = "fork" if "fork" in mp.get_all_start_methods() else "spawn"
    ctx = mp.get_context(ctx_name)
    cpu_count = os.cpu_count() or workers
    thread_limit = max(1, cpu_count // len(chunks))

    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=len(chunks), mp_context=ctx) as executor:
            future_map = {
                executor.submit(
                    _worker_embed_chunk,
                    (chunk_id, chunk_books, model_name, temp_dir, thread_limit),
                ): chunk_id
                for chunk_id, chunk_books in enumerate(chunks)
            }
            completed = 0
            for future in concurrent.futures.as_completed(future_map):
                chunk_id = future_map[future]
                returned_chunk_id, embed_path, meta_path, count, chunk_meta = future.result()
                if returned_chunk_id != chunk_id:
                    raise RuntimeError(
                        f"chunk ordering mismatch: expected {chunk_id}, got {returned_chunk_id}"
                    )
                chunk_results[chunk_id] = (embed_path, meta_path, count, chunk_meta)
                completed += 1
                print(
                    f"[progress] chunks={completed}/{len(chunks)} "
                    f"workers={len(chunks)} threads_per_worker={thread_limit}"
                )

        _build_index_from_temp_files(chunk_results, len(books), out_path, out_meta_path)
    finally:
        for embed_path, meta_path, _count, _chunk_meta in chunk_results.values():
            for raw_path in (embed_path, meta_path):
                try:
                    Path(raw_path).unlink(missing_ok=True)
                except Exception:
                    pass
        try:
            Path(temp_dir).rmdir()
        except Exception:
            pass

    elapsed = time.perf_counter() - started
    return {
        "records_indexed": len(books),
        "embedding_dim": EMBED_DIM,
        "index_type": "IndexFlatIP",
        "index_path": str(out_path),
        "meta_path": str(out_meta_path),
        "elapsed_seconds": elapsed,
        "workers": len(chunks),
        "threads_per_worker": thread_limit,
    }


def _parse_args() -> argparse.Namespace:
    cpu_count = os.cpu_count() or 2
    default_workers = max(1, min(6, cpu_count - 1))
    parser = argparse.ArgumentParser(description="Build the vector retrieval index for books_master_merged.jsonl")
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N books")
    parser.add_argument("--workers", type=int, default=default_workers, help="Number of embedding worker processes")
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
        workers=int(args.workers),
    )
    elapsed = time.perf_counter() - started

    print("=== Index Build Complete ===")
    print(f"Records indexed  : {summary['records_indexed']}")
    print(f"Embedding dim    : {summary['embedding_dim']}")
    print(f"Index type       : {summary['index_type']}")
    print(f"Index saved to   : {summary['index_path']}")
    print(f"Meta saved to    : {summary['meta_path']}")
    print(f"Workers          : {summary['workers']}")
    print(f"Threads/worker   : {summary['threads_per_worker']}")
    print(f"Elapsed          : {elapsed:.1f}s")


if __name__ == "__main__":
    main()
