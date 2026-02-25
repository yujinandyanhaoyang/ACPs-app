from __future__ import annotations

import json
from pathlib import Path

from scripts.run_ablation import _ablated_weights
from services.evaluation_metrics import load_test_interactions


def test_load_test_interactions_reads_rows(tmp_path: Path):
    p = tmp_path / "interactions_test.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps({"user_id": "u1", "book_id": "b1", "rating": 5}),
                json.dumps({"user_id": "u2", "book_id": "b2", "rating": 4}),
                json.dumps({"user_id": "", "book_id": "b3", "rating": 3}),
            ]
        ),
        encoding="utf-8",
    )

    rows = load_test_interactions(n=10, test_path=p)
    assert len(rows) == 2
    assert rows[0]["user_id"] == "u1"
    assert rows[0]["book_id"] == "b1"
    assert rows[0]["rating"] == 5.0


def test_load_test_interactions_respects_limit(tmp_path: Path):
    p = tmp_path / "interactions_test.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps({"user_id": "u1", "book_id": "b1", "rating": 5}),
                json.dumps({"user_id": "u2", "book_id": "b2", "rating": 4}),
                json.dumps({"user_id": "u3", "book_id": "b3", "rating": 3}),
            ]
        ),
        encoding="utf-8",
    )

    rows = load_test_interactions(n=2, test_path=p)
    assert len(rows) == 2


def test_ablated_weights_zeroes_target_and_renormalizes():
    base = {
        "collaborative": 0.25,
        "semantic": 0.35,
        "knowledge": 0.2,
        "diversity": 0.2,
    }
    ablated = _ablated_weights(base, "semantic")
    assert ablated["semantic"] == 0.0
    assert abs(sum(ablated.values()) - 1.0) <= 1e-5
    assert ablated["collaborative"] > 0.0
    assert ablated["knowledge"] > 0.0
    assert ablated["diversity"] > 0.0
