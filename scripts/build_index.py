from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import faiss  # type: ignore
from services.book_retrieval import _book_text, iter_books

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


def _normalize_rows(vectors: List[List[float]]) -> np.ndarray:
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
    return matrix.astype(np.float32)


def _count_total_records(path: Path) -> int:
    with path.open("r", encoding="utf-8") as f:
        return sum(1 for ln in f if ln.strip())


def _checkpoint_path(out_path: Path) -> Path:
    return out_path.parent / "books_index_checkpoint.json"


def _load_checkpoint(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_checkpoint_atomic(path: Path, payload: Dict[str, Any]) -> None:
    tmp_path = path.parent / "books_index_checkpoint.json.tmp"
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp_path, path)


def _checkpoint_matches(
    checkpoint: Dict[str, Any],
    batch_size: int,
    model_name: str,
    index_path: Path,
) -> bool:
    return (
        str(checkpoint.get("model") or "") == model_name
        and int(checkpoint.get("batch_size") or -1) == batch_size
        and str(checkpoint.get("index_path") or "") == str(index_path)
    )


def build_index(
    books_path: Path,
    out_path: Path,
    out_meta_path: Path,
    model_name: str = DEFAULT_MODEL,
    limit: int = 0,
    batch_size: int = 1024,
    resume: bool = True,
) -> Dict[str, Any]:
    if not books_path.exists():
        raise FileNotFoundError(f"Books corpus not found: {books_path}")

    total_records = _count_total_records(books_path)
    effective_total = limit if limit and limit > 0 else total_records
    if effective_total <= 0:
        raise RuntimeError(f"No valid book records available from {books_path}")

    batch_size = max(1, int(batch_size))
    checkpoint_path = _checkpoint_path(out_path)
    checkpoint = _load_checkpoint(checkpoint_path) if resume else None

    resumed = False
    done = 0
    if checkpoint and _checkpoint_matches(checkpoint, batch_size, model_name, out_path):
        done = int(checkpoint.get("done") or 0)
        if 0 <= done < effective_total and out_path.exists():
            index = faiss.read_index(str(out_path))
            resumed = True
        else:
            done = 0
            index = faiss.IndexFlatIP(EMBED_DIM)
            out_meta_path.parent.mkdir(parents=True, exist_ok=True)
            out_meta_path.write_text("", encoding="utf-8")
    else:
        index = faiss.IndexFlatIP(EMBED_DIM)
        out_meta_path.parent.mkdir(parents=True, exist_ok=True)
        out_meta_path.write_text("", encoding="utf-8")

    if resumed:
        print(f"[resume] continuing from record {done}")
    else:
        print("[start] building index from scratch")
        done = 0

    from services.model_backends import generate_text_embeddings

    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta_mode = "a" if resumed else "w"
    started = time.perf_counter()

    with out_meta_path.open(meta_mode, encoding="utf-8") as meta_fp:
        current_batch: List[Dict[str, Any]] = []
        batch_start = done
        remaining = effective_total - done if effective_total > done else 0
        for book in iter_books(books_path, offset=done, limit=remaining):
            if not current_batch:
                batch_start = done
            current_batch.append(book)
            if len(current_batch) < batch_size:
                continue

            texts = [_book_text(b) for b in current_batch]
            vectors, _meta = generate_text_embeddings(
                texts,
                model_name=model_name,
                fallback_dim=EMBED_DIM,
            )
            embeddings = np.asarray(vectors, dtype=np.float32)
            index.add(embeddings)

            for j, book_item in enumerate(current_batch):
                meta_fp.write(
                    json.dumps(
                        {
                            "idx": batch_start + j,
                            "book_id": str(book_item.get("book_id") or ""),
                            "source": str(book_item.get("source") or ""),
                            "title": str(book_item.get("title") or ""),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            done += len(current_batch)
            _write_checkpoint_atomic(
                checkpoint_path,
                {
                    "done": done,
                    "batch_size": batch_size,
                    "model": model_name,
                    "index_path": str(out_path),
                    "meta_path": str(out_meta_path),
                },
            )
            faiss.write_index(index, str(out_path))
            elapsed = time.perf_counter() - started
            speed = done / elapsed if elapsed > 0 else 0.0
            eta = (effective_total - done) / speed if speed > 0 else 0.0
            print(
                (
                    f"[progress] {done}/{effective_total} "
                    f"({done / effective_total * 100:.1f}%) "
                    f"elapsed={elapsed:.0f}s eta={eta:.0f}s batch={batch_size}"
                ),
                flush=True,
            )
            current_batch = []

        if current_batch:
            texts = [_book_text(b) for b in current_batch]
            vectors, _meta = generate_text_embeddings(
                texts,
                model_name=model_name,
                fallback_dim=EMBED_DIM,
            )
            embeddings = np.asarray(vectors, dtype=np.float32)
            index.add(embeddings)

            for j, book_item in enumerate(current_batch):
                meta_fp.write(
                    json.dumps(
                        {
                            "idx": batch_start + j,
                            "book_id": str(book_item.get("book_id") or ""),
                            "source": str(book_item.get("source") or ""),
                            "title": str(book_item.get("title") or ""),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            done += len(current_batch)
            _write_checkpoint_atomic(
                checkpoint_path,
                {
                    "done": done,
                    "batch_size": batch_size,
                    "model": model_name,
                    "index_path": str(out_path),
                    "meta_path": str(out_meta_path),
                },
            )
            faiss.write_index(index, str(out_path))
            elapsed = time.perf_counter() - started
            speed = done / elapsed if elapsed > 0 else 0.0
            eta = (effective_total - done) / speed if speed > 0 else 0.0
            print(
                (
                    f"[progress] {done}/{effective_total} "
                    f"({done / effective_total * 100:.1f}%) "
                    f"elapsed={elapsed:.0f}s eta={eta:.0f}s batch={batch_size}"
                ),
                flush=True,
            )

    if checkpoint_path.exists():
        checkpoint_path.unlink()
    elapsed = time.perf_counter() - started
    print(f"[done] indexed {done} records in {elapsed:.1f}s")
    return {
        "records_indexed": done,
        "embedding_dim": EMBED_DIM,
        "index_type": "IndexFlatIP",
        "index_path": str(out_path),
        "meta_path": str(out_meta_path),
        "elapsed_seconds": elapsed,
        "batch_size": batch_size,
        "resumed": resumed,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the vector retrieval index for books_master_merged.jsonl")
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N books")
    parser.add_argument("--batch-size", type=int, default=1024, help="Embedding batch size")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Embedding model name")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META_PATH)
    parser.add_argument(
        "--no-resume", action="store_true", default=False,
        help="Ignore existing checkpoint and rebuild from scratch",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    args = _parse_args()
    checkpoint = _checkpoint_path(args.index)
    if args.no_resume and checkpoint.exists():
        checkpoint.unlink()

    started = time.perf_counter()
    summary = build_index(
        books_path=args.input,
        out_path=args.index,
        out_meta_path=args.meta,
        model_name=str(args.model),
        limit=int(args.limit),
        batch_size=int(args.batch_size),
        resume=not args.no_resume,
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
