from services.evaluation_metrics import compute_recommendation_metrics, build_ablation_report


def test_compute_recommendation_metrics_with_ground_truth():
    recommendations = [
        {"book_id": "b1"},
        {"book_id": "b2"},
        {"book_id": "b3"},
    ]
    metrics = compute_recommendation_metrics(
        recommendations=recommendations,
        ground_truth_ids=["b1", "b4"],
        k=3,
        avg_diversity=0.6,
        avg_novelty=0.5,
    )
    assert metrics["precision_at_k"] == 0.3333
    assert metrics["recall_at_k"] == 0.5
    assert metrics["ndcg_at_k"] > 0.0
    assert metrics["diversity"] == 0.6
    assert metrics["novelty"] == 0.5


def test_build_ablation_report_returns_component_drops():
    recommendations = [
        {
            "book_id": "b1",
            "score_parts": {
                "collaborative": 0.8,
                "semantic": 0.7,
                "knowledge": 0.5,
                "diversity": 0.4,
            },
        },
        {
            "book_id": "b2",
            "score_parts": {
                "collaborative": 0.6,
                "semantic": 0.9,
                "knowledge": 0.3,
                "diversity": 0.7,
            },
        },
    ]
    report = build_ablation_report(
        recommendations=recommendations,
        scoring_weights={
            "collaborative": 0.25,
            "semantic": 0.35,
            "knowledge": 0.2,
            "diversity": 0.2,
        },
    )
    assert "component_mean_scores" in report
    assert "estimated_drop_if_removed" in report
    assert report["estimated_drop_if_removed"]["semantic"] > 0
