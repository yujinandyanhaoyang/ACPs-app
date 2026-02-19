from services.baseline_rankers import traditional_hybrid_rank, multi_agent_proxy_rank


def _sample_case():
    return {
        "query": "Recommend history and science fiction books",
        "history": [
            {"title": "Dune", "genres": ["science_fiction"], "rating": 5},
            {"title": "Sapiens", "genres": ["history"], "rating": 4},
        ],
        "books": [
            {
                "book_id": "b1",
                "title": "Foundation",
                "description": "Science fiction civilization saga",
                "genres": ["science_fiction"],
                "popularity": 0.9,
            },
            {
                "book_id": "b2",
                "title": "The Silk Roads",
                "description": "Global history and trade",
                "genres": ["history"],
                "popularity": 0.7,
            },
        ],
    }


def test_traditional_hybrid_rank_returns_ranked_rows():
    rows = traditional_hybrid_rank(_sample_case(), top_k=2)
    assert len(rows) == 2
    assert rows[0]["rank"] == 1
    assert "composite_score" in rows[0]
    assert "score_parts" in rows[0]


def test_multi_agent_proxy_rank_returns_ranked_rows():
    rows = multi_agent_proxy_rank(_sample_case(), top_k=2)
    assert len(rows) == 2
    assert rows[0]["rank"] == 1
    assert "novelty_score" in rows[0]
    assert rows[0]["score_parts"]["diversity"] >= 0.2


def test_rankers_fallback_to_candidate_ids_when_books_missing():
    case_payload = {
        "query": "starter books",
        "history": [],
        "candidate_ids": ["c1", "c2", "c3"],
    }
    rows = traditional_hybrid_rank(case_payload, top_k=3)
    assert len(rows) == 3
    assert rows[0]["book_id"] in {"c1", "c2", "c3"}
