#!/usr/bin/env python3
"""Parallel index builder: splits dataset into shards, merges results."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import tempfile
import time
from multiprocessing import Process, Queue
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

import faiss  # type: ignore
from services.book_retrieval import _book_text, iter_books
from services.model_backends import generate_text_embeddings

EMBED_DIM = 384
DEFAULT_MODEL = os.getenv("BOOK_CONTENT_EMBED_MODEL", "all-MiniLM-L6-v2")
_configured_root = (
    os.getenv("BOOK_RETRIEVAL_DATASET_PATH", "").strip()
    or os.getenv("DATASET_ROOT", "").strip()
)
DEFAULT_DATASET_ROOT = Path(_configured_root).expanduser() if _configured_root else PROJECT_ROOT / "data"
DEFAULT_INPUT = DEFAULT_DATASET_ROOT / "processed" / "books_master_merged.jsonl"
DEFAULT_INDEX = DEFAULT_DATASET_ROOT / "processed" / "books_index.faiss"
DEFAULT_META = DEFAULT_DATASET_ROOT / "processed" / "books_index_meta.jsonl"


def _count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as f:
        return sum(1 for ln in f if ln.strip())


def _worker(
    worker_id: int,
    books_path: str,
    offset: int,
    limit: int,
    batch_size: int,
    model_name: str,
    shard_index_path: str,
    shard_meta_path: str,
    result_queue: Queue,
):
    """Run in a subprocess: build one shard of the index."""
    try:
        os.environ["OMP_NUM_THREADS"] = "2"
        os.environ["MKL_NUM_THREADS"] = "2"
        os.environ["OPENBLAS_NUM_THREADS"] = "2"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"

        index = faiss.IndexFlatIP(EMBED_DIM)
        done = 0
        batch: list = []

        with open(shard_meta_path, "w", encoding="utf-8") as meta_fp:
            for book in iter_books(Path(books_path), offset=offset, limit=limit):
                batch.append(book)
                if len(batch) >= batch_size:
                    texts = [_book_text(b) for b in batch]
                    vectors, _ = generate_text_embeddings(
                        texts, model_name=model_name, fallback_dim=EMBED_DIM
                    )
                    embeddings = np.asarray(vectors, dtype=np.float32)
                    index.add(embeddings)
                    for j, b in enumerate(batch):
                        meta_fp.write(
                            json.dumps(
                                {
                                    "idx": offset + done + j,
                                    "book_id": str(b.get("book_id") or ""),
                                    "source": str(b.get("source") or ""),
                                    "title": str(b.get("title") or ""),
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                    done += len(batch)
                    batch = []
                    print(
                        f"[worker-{worker_id}] {done}/{limit} ({done/limit*100:.1f}%)",
                        flush=True,
                    )

            if batch:
                texts = [_book_text(b) for b in batch]
                vectors, _ = generate_text_embeddings(
                    texts, model_name=model_name, fallback_dim=EMBED_DIM
                )
                embeddings = np.asarray(vectors, dtype=np.float32)
                index.add(embeddings)
                for j, b in enumerate(batch):
                    meta_fp.write(
                        json.dumps(
                            {
                                "idx": offset + done + j,
                                "book_id": str(b.get("book_id") or ""),
                                "source": str(b.get("source") or ""),
                                "title": str(b.get("title") or ""),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                done += len(batch)

        faiss.write_index(index, shard_index_path)
        result_queue.put({"worker_id": worker_id, "done": done, "status": "ok"})
    except Exception as exc:
        result_queue.put({"worker_id": worker_id, "done": 0, "status": "error", "error": str(exc)})


def _merge_shards(
    shard_index_paths: list[str],
    shard_meta_paths: list[str],
    out_index_path: Path,
    out_meta_path: Path,
) -> int:
    """Merge N shard indexes and meta files into the final output."""
    merged = faiss.IndexFlatIP(EMBED_DIM)
    with out_meta_path.open("w", encoding="utf-8") as meta_out:
        global_idx = 0
        for shard_idx_path, shard_meta_path in zip(shard_index_paths, shard_meta_paths):
            shard = faiss.read_index(shard_idx_path)
            n = shard.ntotal
            if n > 0:
                vecs = np.zeros((n, EMBED_DIM), dtype=np.float32)
                for i in range(n):
                    shard.reconstruct(i, vecs[i])
                merged.add(vecs)

            with open(shard_meta_path, "r", encoding="utf-8") as mf:
                for line in mf:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    row["idx"] = global_idx
                    meta_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    global_idx += 1

    faiss.write_index(merged, str(out_index_path))
    return merged.ntotal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--limit", type=int, default=0, help="Process only first N records (0 = all)")
    args = parser.parse_args()

    total = _count_lines(args.input)
    effective_total = args.limit if args.limit > 0 else total
    effective_total = min(effective_total, total)
    shard_size = (effective_total + args.workers - 1) // args.workers

    print(f"Total records  : {total}")
    print(f"Workers        : {args.workers}")
    print(f"Shard size     : {shard_size}")
    print(f"Batch size     : {args.batch_size}")

    tmpdir = Path(tempfile.mkdtemp(prefix="build_index_parallel_"))
    shard_index_paths: list[str] = []
    shard_meta_paths: list[str] = []
    processes: list[Process] = []
    queue: Queue = Queue()

    started = time.perf_counter()

    for i in range(args.workers):
        offset = i * shard_size
        limit = min(shard_size, max(0, effective_total - offset))
        if limit == 0:
            break
        shard_idx = str(tmpdir / f"shard_{i}.faiss")
        shard_meta = str(tmpdir / f"shard_{i}_meta.jsonl")
        shard_index_paths.append(shard_idx)
        shard_meta_paths.append(shard_meta)

        p = Process(
            target=_worker,
            args=(
                i,
                str(args.input),
                offset,
                limit,
                args.batch_size,
                args.model,
                shard_idx,
                shard_meta,
                queue,
            ),
            daemon=True,
        )
        p.start()
        processes.append(p)
        print(f"Started worker-{i}: offset={offset} limit={limit}")

    results = {}
    for _ in processes:
        r = queue.get()
        results[r["worker_id"]] = r
        if r["status"] == "ok":
            print(f"worker-{r['worker_id']} done: {r['done']} records")
        else:
            print(f"worker-{r['worker_id']} FAILED: {r['error']}")

    for p in processes:
        p.join()

    failures = [r for r in results.values() if r["status"] != "ok"]
    if failures:
        print(f"FAILED workers: {failures}")
        sys.exit(1)

    print("Merging shards...")
    args.index.parent.mkdir(parents=True, exist_ok=True)
    total_indexed = _merge_shards(shard_index_paths, shard_meta_paths, args.index, args.meta)
    elapsed = time.perf_counter() - started

    print("\n=== Parallel Index Build Complete ===")
    print(f"Records indexed : {total_indexed}")
    print(f"Index saved to  : {args.index}")
    print(f"Meta saved to   : {args.meta}")
    print(f"Elapsed         : {elapsed:.1f}s")
    print(f"Projected full  : {elapsed / max(1, effective_total) * total / 3600:.2f}h")

    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
