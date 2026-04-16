from __future__ import annotations

from pathlib import Path

from partners.online.recommendation_engine_agent.modules.ranking import score_round1
from partners.online.recommendation_engine_agent.modules.recall import recall_candidates


def test_cold_start_keeps_content_score_positive():
    candidates = [
        {
            "book_id": "book_001",
            "title": "A History of Power",
            "genres": ["history", "biography"],
            "content_sim": 0.0,
            "cf_score": 0.0,
            "novelty_score": 0.2,
        },
        {
            "book_id": "book_002",
            "title": "Politics and Memory",
            "genres": ["politics"],
            "content_sim": 0.0,
            "cf_score": 0.0,
            "novelty_score": 0.1,
        },
    ]

    ranked, meta = score_round1(
        candidates,
        score_weights={"content": 0.35, "cf": 0.35, "novelty": 0.15, "recency": 0.15},
        top_k=2,
        cold_start=True,
    )

    assert meta["selected_count"] == 2
    assert ranked[0]["score_parts"]["content"] > 0.0


def test_recall_meta_uses_v2_paths_and_non_fallback_modes(monkeypatch, tmp_path):
    # Keep the test isolated from corpus loading and factor loading.
    monkeypatch.setattr(
        "partners.online.recommendation_engine_agent.modules.recall._load_book_metadata",
        lambda: {},
    )
    monkeypatch.setattr(
        "services.model_backends.load_cf_item_vectors",
        lambda force_reload=False: {},
    )

    faiss_index = tmp_path / "books_index_v2.faiss"
    faiss_meta = tmp_path / "books_index_meta_v2.jsonl"
    cf_item = tmp_path / "cf_item_factors_v2.npy"
    cf_book_index = tmp_path / "cf_book_id_index_v2.json"
    cf_user = tmp_path / "cf_user_factors_v2.npy"
    cf_user_index = tmp_path / "cf_user_id_index_v2.json"
    for path in [faiss_index, faiss_meta, cf_item, cf_book_index, cf_user, cf_user_index]:
        path.write_text("", encoding="utf-8")

    payload = {
        "cold_start": True,
        "profile_vector": [],
        "ann_weight": 0.6,
        "cf_weight": 0.4,
        "candidates": [
            {
                "book_id": "book_001",
                "title": "A History of Power",
                "vector_384": [0.1, 0.2, 0.3],
                "genres": ["history"],
            }
        ],
    }
    cfg = {
        "faiss_index_path": str(faiss_index),
        "faiss_index_meta_path": str(faiss_meta),
        "book_retrieval_dataset_path": str(tmp_path / "books_master_merged_v2.jsonl"),
        "cf_item_factors_path": str(cf_item),
        "cf_book_index_path": str(cf_book_index),
        "cf_user_factors_path": str(cf_user),
        "cf_user_index_path": str(cf_user_index),
        "ann_ef_search": 100,
        "ann_top_k": 10,
        "cf_top_k": 10,
        "cf_sim_users": 50,
    }

    merged, meta = recall_candidates(payload, cfg)

    assert merged, "recall should return candidates"
    assert meta["ann_runtime"]["index_path"].endswith("books_index_v2.faiss")
    assert meta["ann_runtime"]["meta_path"].endswith("books_index_meta_v2.jsonl")
    assert meta["cf_runtime"]["item_factors_path"].endswith("cf_item_factors_v2.npy")
    assert meta["cf_runtime"]["book_index_path"].endswith("cf_book_id_index_v2.json")
    assert meta["cf_runtime"]["mode"] != "fallback_item_factor_similarity"
    assert meta["ann_runtime"]["mode"] != "fallback_vector_cosine"
