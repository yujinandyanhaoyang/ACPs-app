from services.phase4_benchmark import evaluate_method_case, aggregate_method_runs, rank_methods


def test_evaluate_method_case_computes_metrics():
    recs = [
        {
            "book_id": "b1",
            "score_parts": {"diversity": 0.4},
            "novelty_score": 0.5,
        },
        {
            "book_id": "b2",
            "score_parts": {"diversity": 0.6},
            "novelty_score": 0.4,
        },
    ]
    metrics = evaluate_method_case(recs, ["b1", "b3"], top_k=2)
    assert metrics["precision_at_k"] == 0.5
    assert metrics["recall_at_k"] == 0.5
    assert metrics["ndcg_at_k"] > 0
    assert metrics["diversity"] == 0.5


def test_aggregate_method_runs_returns_objective_score():
    runs = [
        {
            "metrics": {
                "precision_at_k": 0.5,
                "recall_at_k": 0.6,
                "ndcg_at_k": 0.7,
                "diversity": 0.4,
                "novelty": 0.5,
            },
            "latency_ms": 8.0,
            "strict_failure": 0.0,
            "remote_attempt_rate": 1.0,
            "fallback_rate": 0.5,
            "remote_success_rate": 0.5,
        },
        {
            "metrics": {
                "precision_at_k": 0.4,
                "recall_at_k": 0.5,
                "ndcg_at_k": 0.6,
                "diversity": 0.5,
                "novelty": 0.6,
            },
            "latency_ms": 12.0,
            "strict_failure": 1.0,
            "remote_attempt_rate": 0.0,
            "fallback_rate": 0.0,
            "remote_success_rate": 0.0,
        },
    ]
    summary = aggregate_method_runs(runs)
    assert summary["cases"] == 2.0
    assert summary["strict_failure_rate"] == 0.5
    assert summary["remote_attempt_rate"] == 0.5
    assert summary["fallback_rate"] == 0.25
    assert summary["remote_success_rate"] == 0.25
    assert "objective_score" in summary
    assert "objective_score_latency_aware" in summary


def test_rank_methods_orders_by_objective_score():
    rows = rank_methods(
        [
            {"method": "a", "summary": {"objective_score": 0.3, "objective_score_latency_aware": 0.2, "ndcg_at_k": 0.5, "latency_ms_mean": 10}},
            {"method": "b", "summary": {"objective_score": 0.6, "objective_score_latency_aware": 0.5, "ndcg_at_k": 0.4, "latency_ms_mean": 12}},
        ]
    )
    assert rows[0]["method"] == "b"
    assert rows[0]["rank"] == 1
