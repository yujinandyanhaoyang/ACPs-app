from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Tuple

import numpy as np


class IndexFlatIP:
    def __init__(self, dim: int):
        self.dim = int(dim)
        self._vectors = np.zeros((0, self.dim), dtype=np.float32)

    @property
    def ntotal(self) -> int:
        return int(self._vectors.shape[0])

    def add(self, vectors: Any) -> None:
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        if matrix.ndim != 2:
            raise ValueError("vectors must be a 2D array")
        if matrix.shape[1] != self.dim:
            raise ValueError(f"dimension mismatch: expected {self.dim}, got {matrix.shape[1]}")
        if self._vectors.size == 0:
            self._vectors = matrix.copy()
        else:
            self._vectors = np.vstack([self._vectors, matrix])

    def search(self, queries: Any, top_k: int) -> Tuple[np.ndarray, np.ndarray]:
        query_matrix = np.asarray(queries, dtype=np.float32)
        if query_matrix.ndim == 1:
            query_matrix = query_matrix.reshape(1, -1)
        if query_matrix.ndim != 2:
            raise ValueError("queries must be a 2D array")
        if query_matrix.shape[1] != self.dim:
            raise ValueError(f"dimension mismatch: expected {self.dim}, got {query_matrix.shape[1]}")
        top_k = max(1, int(top_k))

        if self.ntotal == 0:
            scores = np.full((query_matrix.shape[0], top_k), -np.inf, dtype=np.float32)
            indices = np.full((query_matrix.shape[0], top_k), -1, dtype=np.int64)
            return scores, indices

        scores_all = query_matrix @ self._vectors.T
        actual_k = min(top_k, self.ntotal)
        top_indices = np.argpartition(-scores_all, kth=actual_k - 1, axis=1)[:, :actual_k]
        row_indices = np.arange(scores_all.shape[0])[:, None]
        top_scores = scores_all[row_indices, top_indices]
        order = np.argsort(-top_scores, axis=1)
        sorted_indices = top_indices[row_indices, order]
        sorted_scores = top_scores[row_indices, order]

        if actual_k < top_k:
            pad_scores = np.full((query_matrix.shape[0], top_k - actual_k), -np.inf, dtype=np.float32)
            pad_indices = np.full((query_matrix.shape[0], top_k - actual_k), -1, dtype=np.int64)
            sorted_scores = np.concatenate([sorted_scores, pad_scores], axis=1)
            sorted_indices = np.concatenate([sorted_indices, pad_indices], axis=1)

        return sorted_scores.astype(np.float32), sorted_indices.astype(np.int64)

    def reconstruct(self, key: int, out: Any | None = None):
        vector = self._vectors[int(key)].astype(np.float32)
        if out is None:
            return vector.copy()
        out[...] = vector
        return out


def write_index(index: IndexFlatIP, path: str) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("wb") as f:
        np.savez_compressed(f, dim=np.asarray([index.dim], dtype=np.int64), vectors=index._vectors.astype(np.float32))


def _load_real_faiss():
    shim_path = Path(__file__).resolve()
    shim_dir = shim_path.parent

    original_sys_path = list(sys.path)
    try:
        sys.modules.pop("faiss", None)
        sys.path = [
            entry
            for entry in original_sys_path
            if Path(entry or ".").resolve() != shim_dir
        ]
        spec = importlib.util.find_spec("faiss")
        if spec is None or spec.loader is None or getattr(spec, "origin", None) == str(shim_path):
            raise ImportError("real faiss module not found")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_sys_path


def read_index(path: str) -> IndexFlatIP:
    file_path = Path(path)
    with file_path.open("rb") as f:
        magic = f.read(4)

    if magic[:2] == b"PK":
        with np.load(str(file_path), allow_pickle=False) as data:
            dim = int(np.asarray(data["dim"]).reshape(-1)[0])
            vectors = np.asarray(data["vectors"], dtype=np.float32) if "vectors" in data else np.zeros((0, dim), dtype=np.float32)
        index = IndexFlatIP(dim)
        if vectors.size:
            index.add(vectors.reshape((-1, dim)).astype(np.float32))
        return index

    real_faiss = _load_real_faiss()
    return real_faiss.read_index(str(file_path))
