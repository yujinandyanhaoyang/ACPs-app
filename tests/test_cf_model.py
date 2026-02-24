from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from services.model_backends import load_cf_item_vectors, estimate_collaborative_scores_with_svd


def _write_cf_artifacts(tmp_path: Path):
    item_factors = np.asarray(
        [
            [0.9, 0.1, 0.0],
            [0.8, 0.2, 0.1],
            [0.1, 0.9, 0.2],
        ],
        dtype=np.float32,
    )
    item_path = tmp_path / "cf_item_factors.npy"
    np.save(item_path, item_factors)

    index = {"b1": 0, "b2": 1, "b3": 2}
    index_path = tmp_path / "cf_book_id_index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    return item_path, index_path


def test_load_cf_item_vectors_known_book_id(monkeypatch, tmp_path: Path):
    item_path, index_path = _write_cf_artifacts(tmp_path)
    monkeypatch.setenv("CF_ITEM_FACTORS_PATH", str(item_path))
    monkeypatch.setenv("CF_BOOK_INDEX_PATH", str(index_path))

    vectors = load_cf_item_vectors(force_reload=True)
    assert "b1" in vectors
    assert len(vectors["b1"]) == 3
    assert vectors["b1"][0] == 0.9


def test_estimate_collaborative_scores_uses_pretrained_backend(monkeypatch, tmp_path: Path):
    item_path, index_path = _write_cf_artifacts(tmp_path)
    monkeypatch.setenv("CF_ITEM_FACTORS_PATH", str(item_path))
    monkeypatch.setenv("CF_BOOK_INDEX_PATH", str(index_path))
    load_cf_item_vectors(force_reload=True)

    history = [{"book_id": "b1", "rating": 5.0}]
    candidates = [{"book_id": "b1"}, {"book_id": "b2"}]

    scores, meta = estimate_collaborative_scores_with_svd(history=history, candidates=candidates, n_components=8)
    assert set(scores.keys()) == {"b1", "b2"}
    assert meta["backend"] == "pretrained-svd"
    assert meta["pretrained_candidate_coverage"] == 1.0


def test_estimate_collaborative_scores_mixed_coverage(monkeypatch, tmp_path: Path):
    item_path, index_path = _write_cf_artifacts(tmp_path)
    monkeypatch.setenv("CF_ITEM_FACTORS_PATH", str(item_path))
    monkeypatch.setenv("CF_BOOK_INDEX_PATH", str(index_path))
    load_cf_item_vectors(force_reload=True)

    history = [{"book_id": "b1", "rating": 5.0, "genres": ["scifi"]}]
    candidates = [
        {"book_id": "b2", "genres": ["scifi"]},
        {"book_id": "b_unknown", "genres": ["mystery"]},
    ]

    scores, meta = estimate_collaborative_scores_with_svd(history=history, candidates=candidates, n_components=8)
    assert set(scores.keys()) == {"b2", "b_unknown"}
    assert meta["backend"] in {"pretrained-svd+overlap-fallback", "pretrained-svd"}
    assert meta["pretrained_candidate_coverage"] >= 0.5
