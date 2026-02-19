from services.phase4_optimizer import (
    aggregate_experiment_runs,
    objective_score,
    select_best_experiment,
)


def test_aggregate_experiment_runs_computes_core_fields():
    runs = [
        {
            "state": "completed",
            "latency_ms": 12.0,
            "metrics": {
                "precision_at_k": 0.5,
                "recall_at_k": 0.6,
                "ndcg_at_k": 0.7,
                "diversity": 0.4,
                "novelty": 0.5,
            },
        },
        {
            "state": "completed",
            "latency_ms": 18.0,
            "metrics": {
                "precision_at_k": 0.3,
                "recall_at_k": 0.4,
                "ndcg_at_k": 0.5,
                "diversity": 0.6,
                "novelty": 0.7,
            },
        },
    ]

    summary = aggregate_experiment_runs(runs)
    assert summary["cases"] == 2.0
    assert summary["success_rate"] == 1.0
    assert summary["precision_at_k"] == 0.4
    assert summary["latency_ms_mean"] == 15.0
    assert summary["latency_ms_p95"] >= 17.0


def test_objective_score_penalizes_latency():
    low_latency = {
        "precision_at_k": 0.5,
        "recall_at_k": 0.5,
        "ndcg_at_k": 0.5,
        "diversity": 0.5,
        "novelty": 0.5,
        "latency_ms_mean": 10,
    }
    high_latency = {**low_latency, "latency_ms_mean": 100}

    assert objective_score(low_latency) > objective_score(high_latency)


def test_select_best_experiment_returns_highest_objective():
    experiments = [
        {
            "config": {"config_id": "a"},
            "summary": {
                "precision_at_k": 0.3,
                "recall_at_k": 0.3,
                "ndcg_at_k": 0.3,
                "diversity": 0.3,
                "novelty": 0.3,
                "latency_ms_mean": 10.0,
            },
        },
        {
            "config": {"config_id": "b"},
            "summary": {
                "precision_at_k": 0.6,
                "recall_at_k": 0.6,
                "ndcg_at_k": 0.6,
                "diversity": 0.6,
                "novelty": 0.6,
                "latency_ms_mean": 20.0,
            },
        },
    ]

    best = select_best_experiment(experiments)
    assert best["config"]["config_id"] == "b"
    assert "objective_score" in best
