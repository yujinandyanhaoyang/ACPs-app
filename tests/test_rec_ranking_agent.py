import json

import pytest

from acps_aip.aip_base_model import TaskCommand, TaskState
from tests.conftest import build_rpc_payload


def _post(client, payload):
    resp = client.post("/rec-ranking/rpc", json=payload)
    assert resp.status_code == 200
    return resp.json()


def _state(body):
    return body.get("result", {}).get("status", {}).get("state")


def _products(body):
    return body.get("result", {}).get("products") or []


def _with_payload(task_id, payload, command=TaskCommand.Start):
    wrapper = build_rpc_payload("", task_id, command=command)
    wrapper["params"]["message"]["commandParams"] = {"payload": payload}
    return wrapper


def _print_e2e_response(body):
    print("\n[rec_ranking_agent E2E] RPC response:")
    print(json.dumps(body, ensure_ascii=False, indent=2))


@pytest.mark.usefixtures("patch_openai")
def test_start_missing_required_fields_prompts_for_input(client_rec_ranking, new_task_id):
    payload = {
        "profile_vector": {},
        "content_vectors": [],
    }
    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.AwaitingInput.value
    data_items = res["result"]["status"].get("dataItems") or []
    assert any("missing_fields" in (item.get("text") or "") for item in data_items)


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_start_completes_with_ranked_outputs(client_rec_ranking, new_task_id):
    payload = {
        "profile_vector": {
            "genres": {"science_fiction": 0.7, "history": 0.3},
            "themes": {"politics": 0.6, "identity": 0.4},
            "difficulty": {"intermediate": 0.8},
        },
        "content_vectors": [
            {
                "book_id": "b1",
                "title": "Dune",
                "vector": [0.9, 0.8, 0.7, 0.6],
                "kg_signal": 0.7,
                "novelty_score": 0.5,
                "diversity_score": 0.4,
            },
            {
                "book_id": "b2",
                "title": "The Martian",
                "vector": [0.8, 0.8, 0.6, 0.5],
                "kg_signal": 0.4,
                "novelty_score": 0.3,
                "diversity_score": 0.2,
            },
        ],
        "svd_factors": [
            {"book_id": "b1", "score": 0.75},
            {"book_id": "b2", "score": 0.62},
        ],
        "constraints": {"top_k": 2},
    }
    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value
    structured = _products(res)[0]["dataItems"][0]
    assert structured["type"] == "data"
    outputs = structured["data"]["outputs"]
    assert len(outputs["ranking"]) == 2
    assert "metric_snapshot" in outputs
    assert "explanations" in outputs
    assert outputs["collaborative_backend"]["backend"] == "provided-factors"
    assert outputs["semantic_backend"]["backend"] == "deterministic-384d"


@pytest.mark.usefixtures("patch_openai")
def test_continue_unblocks_after_missing_input(client_rec_ranking, new_task_id):
    start_payload = {"profile_vector": {}, "content_vectors": []}
    start_res = _post(client_rec_ranking, _with_payload(new_task_id, start_payload))
    assert _state(start_res) == TaskState.AwaitingInput.value

    continue_payload = {
        "profile_vector": {"genres": {"mystery": 1.0}},
        "candidates": [
            {
                "book_id": "m1",
                "title": "Murder on the Orient Express",
                "vector": [0.7, 0.4, 0.5],
                "kg_signal": 0.3,
                "novelty_score": 0.35,
                "diversity_score": 0.25,
            }
        ],
        "constraints": {"top_k": 1},
    }
    cont = _post(
        client_rec_ranking,
        _with_payload(new_task_id, continue_payload, command=TaskCommand.Continue),
    )
    assert _state(cont) == TaskState.Completed.value
    summary = _products(cont)[0]["dataItems"][1]["text"]
    assert "Top recommendation" in summary
    outputs = _products(cont)[0]["dataItems"][0]["data"]["outputs"]
    assert outputs["collaborative_backend"]["backend"] in {
        "sklearn-truncated-svd",
        "overlap-fallback",
        "pretrained-svd",
        "pretrained-svd+overlap-fallback",
    }


@pytest.mark.usefixtures("patch_openai")
def test_rec_ranking_agent_end_to_end_env_and_llm(monkeypatch, client_rec_ranking, new_task_id):
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    async def fake_call(messages, model, temperature=None, max_tokens=None):
        return "Recommended because it strongly matches your themes and keeps diversity in the final list."

    monkeypatch.setattr(
        "agents.rec_ranking_agent.rec_ranking_agent.call_openai_chat",
        fake_call,
    )

    payload = {
        "profile_vector": {
            "genres": {"science_fiction": 0.8, "classic": 0.2},
            "themes": {"exploration": 0.6, "ethics": 0.4},
            "difficulty": {"advanced": 0.5, "intermediate": 0.5},
        },
        "candidates": [
            {
                "book_id": "b1",
                "title": "Dune",
                "vector": [0.9, 0.8, 0.7, 0.6, 0.5],
                "kg_signal": 0.9,
                "novelty_score": 0.65,
                "diversity_score": 0.45,
            },
            {
                "book_id": "b2",
                "title": "Foundation",
                "vector": [0.85, 0.7, 0.62, 0.55, 0.4],
                "kg_signal": 0.6,
                "novelty_score": 0.52,
                "diversity_score": 0.5,
            },
        ],
        "svd_factors": [{"book_id": "b1", "score": 0.81}, {"book_id": "b2", "score": 0.74}],
        "scoring_weights": {
            "collaborative": 0.3,
            "semantic": 0.35,
            "knowledge": 0.2,
            "diversity": 0.15,
        },
        "constraints": {"top_k": 2, "novelty_threshold": 0.5, "min_new_items": 1},
    }

    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    _print_e2e_response(res)
    assert _state(res) == TaskState.Completed.value

    structured = _products(res)[0]["dataItems"][0]["data"]
    outputs = structured["outputs"]
    assert len(outputs["ranking"]) == 2
    assert len(outputs["explanations"]) == 2
    assert outputs["explanations"][0]["source"] == "llm"
    metrics = outputs["metric_snapshot"]
    assert "avg_novelty" in metrics
    assert "avg_diversity" in metrics
    assert "collaborative_backend" in outputs
    assert structured["diagnostics"]["api_key_present"] is True


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_ranking_output_contract_compliance(client_rec_ranking, new_task_id):
    """Verify ranking agent output conforms to ranked_recommendation_list.schema.json v1.0.0."""
    payload = {
        "profile_vector": {
            "genres": {"science_fiction": 0.8, "classic": 0.2},
            "themes": {"exploration": 0.6, "ethics": 0.4},
            "difficulty": {"advanced": 0.5, "intermediate": 0.5},
        },
        "candidates": [
            {
                "book_id": "b1",
                "title": "Dune",
                "vector": [0.9, 0.8, 0.7, 0.6, 0.5],
                "kg_signal": 0.9,
                "novelty_score": 0.65,
                "diversity_score": 0.45,
            },
            {
                "book_id": "b2",
                "title": "Foundation",
                "vector": [0.85, 0.7, 0.62, 0.55, 0.4],
                "kg_signal": 0.6,
                "novelty_score": 0.52,
                "diversity_score": 0.5,
            },
        ],
        "svd_factors": [{"book_id": "b1", "score": 0.81}, {"book_id": "b2", "score": 0.74}],
        "scoring_weights": {
            "collaborative": 0.3,
            "semantic": 0.35,
            "knowledge": 0.2,
            "diversity": 0.15,
        },
        "constraints": {"top_k": 2, "novelty_threshold": 0.5, "min_new_items": 1},
    }

    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value

    structured = _products(res)[0]["dataItems"][0]["data"]
    outputs = structured["outputs"]

    # Contract requirement: scenario_policy must be present
    assert "scenario_policy" in outputs
    assert outputs["scenario_policy"] in {
        "cold",
        "warm",
        "explore",
    }

    # Contract requirement: ranking items must have all required fields
    ranking = outputs["ranking"]
    assert len(ranking) == 2
    
    for idx, item in enumerate(ranking):
        # Required scalar fields
        assert "book_id" in item
        assert "title" in item
        assert "score_total" in item
        assert "score_cf" in item
        assert "score_content" in item
        assert "score_kg" in item
        assert "score_diversity" in item
        assert "rank_position" in item
        assert "scenario_policy" in item
        assert "explanation" in item
        assert "explanation_evidence_refs" in item
        
        # Verify rank positions are sequential
        assert item["rank_position"] == idx + 1
        
        # Verify explanation_evidence_refs is a list
        assert isinstance(item["explanation_evidence_refs"], list)
        
        # Verify scores are numeric
        assert isinstance(item["score_total"], (int, float))
        assert isinstance(item["score_cf"], (int, float))
        assert isinstance(item["score_content"], (int, float))
        assert isinstance(item["score_kg"], (int, float))
        assert isinstance(item["score_diversity"], (int, float))


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_scenario_policy_is_propagated_to_all_ranked_items(client_rec_ranking, new_task_id):
    payload = {
        "query": "discover new sci-fi",
        "scenario_policy": "discovery",
        "profile_vector": {
            "genres": {"science_fiction": 0.9},
            "themes": {"exploration": 0.8},
        },
        "candidates": [
            {
                "book_id": "b1",
                "title": "Dune",
                "vector": [0.9, 0.8, 0.7],
                "kg_signal": 0.7,
                "novelty_score": 0.6,
                "diversity_score": 0.4,
            },
            {
                "book_id": "b2",
                "title": "Foundation",
                "vector": [0.85, 0.7, 0.62],
                "kg_signal": 0.6,
                "novelty_score": 0.52,
                "diversity_score": 0.5,
            },
        ],
        "constraints": {"top_k": 2},
    }

    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value

    outputs = _products(res)[0]["dataItems"][0]["data"]["outputs"]
    assert outputs["scenario_policy"] == "explore"
    for item in outputs["ranking"]:
        assert item["scenario_policy"] == "explore"


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_explanation_evidence_refs_are_flat_string_list(client_rec_ranking, new_task_id):
    payload = {
        "query": "history books",
        "profile_vector": {
            "genres": {"history": 1.0},
        },
        "content_vectors": [
            {
                "book_id": "h1",
                "title": "The Silk Roads",
                "vector": [0.7, 0.6, 0.5],
                "kg_signal": 0.5,
                "novelty_score": 0.4,
                "diversity_score": 0.3,
            }
        ],
        "constraints": {"top_k": 1},
    }

    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value

    item = _products(res)[0]["dataItems"][0]["data"]["outputs"]["ranking"][0]
    refs = item.get("explanation_evidence_refs") or []
    assert isinstance(refs, list)
    assert all(isinstance(ref, str) for ref in refs)


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_candidate_membership_is_not_expanded_by_vector_only_rows(client_rec_ranking, new_task_id):
    payload = {
        "scenario_policy": "warm",
        "profile_vector": {"genres": {"history": 1.0}},
        "candidates": [
            {
                "book_id": "b1",
                "title": "Known Candidate",
                "novelty_score": 0.3,
                "diversity_score": 0.3,
            }
        ],
        "content_vectors": [
            {"book_id": "b1", "vector": [0.8, 0.7, 0.6], "kg_signal": 0.4},
            {"book_id": "rogue-b2", "vector": [0.7, 0.6, 0.5], "kg_signal": 0.9},
        ],
        "svd_factors": [{"book_id": "b1", "score": 0.8}, {"book_id": "rogue-b2", "score": 0.95}],
        "constraints": {"top_k": 3},
    }

    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value

    ranking = _products(res)[0]["dataItems"][0]["data"]["outputs"]["ranking"]
    assert len(ranking) == 1
    assert ranking[0]["book_id"] == "b1"


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_hard_minimums_for_novelty_and_diversity_are_enforced(client_rec_ranking, new_task_id):
    payload = {
        "scenario_policy": "warm",
        "profile_vector": {"genres": {"science_fiction": 1.0}},
        "candidates": [
            {"book_id": "a", "title": "A", "vector": [0.9, 0.9, 0.9], "novelty_score": 0.2, "diversity_score": 0.2},
            {"book_id": "b", "title": "B", "vector": [0.88, 0.88, 0.88], "novelty_score": 0.3, "diversity_score": 0.25},
            {"book_id": "c", "title": "C", "vector": [0.7, 0.7, 0.7], "novelty_score": 0.75, "diversity_score": 0.72},
            {"book_id": "d", "title": "D", "vector": [0.65, 0.65, 0.65], "novelty_score": 0.8, "diversity_score": 0.78},
        ],
        "svd_factors": [
            {"book_id": "a", "score": 0.95},
            {"book_id": "b", "score": 0.9},
            {"book_id": "c", "score": 0.4},
            {"book_id": "d", "score": 0.35},
        ],
        "scoring_weights": {"collaborative": 1.0, "semantic": 0.0, "knowledge": 0.0, "diversity": 0.0},
        "constraints": {
            "top_k": 3,
            "novelty_threshold": 0.7,
            "min_new_items": 2,
            "diversity_threshold": 0.7,
            "min_diverse_items": 2,
        },
    }

    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value

    outputs = _products(res)[0]["dataItems"][0]["data"]["outputs"]
    ranking = outputs["ranking"]
    metrics = outputs["metric_snapshot"]

    ranked_ids = {item["book_id"] for item in ranking}
    assert {"c", "d"}.issubset(ranked_ids)
    assert metrics["new_item_count"] >= 2
    assert metrics["diverse_item_count"] >= 2


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_constraints_scenario_is_used_as_primary_policy(client_rec_ranking, new_task_id):
    payload = {
        "query": "recommend something",
        "profile_vector": {"genres": {"fantasy": 1.0}},
        "candidates": [
            {
                "book_id": "x1",
                "title": "X1",
                "vector": [0.8, 0.7, 0.6],
                "kg_signal": 0.3,
                "novelty_score": 0.5,
                "diversity_score": 0.5,
            }
        ],
        "constraints": {"scenario": "cold", "top_k": 1},
    }

    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value

    outputs = _products(res)[0]["dataItems"][0]["data"]["outputs"]
    assert outputs["scenario_policy"] == "cold"
    assert outputs["ranking"][0]["scenario_policy"] == "cold"


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_query_cue_derives_explore_scenario(client_rec_ranking, new_task_id):
    payload = {
        "query": "discover something new",
        "profile_vector": {"genres": {"science_fiction": 1.0}},
        "candidates": [
            {
                "book_id": "e1",
                "title": "Explore Candidate",
                "vector": [0.8, 0.7, 0.6],
                "kg_signal": 0.3,
                "novelty_score": 0.6,
                "diversity_score": 0.6,
            }
        ],
        "constraints": {"top_k": 1},
    }

    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value

    outputs = _products(res)[0]["dataItems"][0]["data"]["outputs"]
    assert outputs["scenario_policy"] == "explore"
    assert outputs["ranking"][0]["scenario_policy"] == "explore"


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_default_branch_derives_warm_scenario(client_rec_ranking, new_task_id):
    payload = {
        "query": "recommend classics",
        "profile_vector": {
            "genres": {"classic": 1.0},
            "pacing": {"fast": 0.8, "slow": 0.2},
            "difficulty": {"beginner": 0.7, "advanced": 0.2},
        },
        "candidates": [
            {
                "book_id": "w1",
                "title": "Warm Candidate",
                "vector": [0.8, 0.7, 0.6],
                "kg_signal": 0.2,
                "novelty_score": 0.4,
                "diversity_score": 0.4,
            }
        ],
        "constraints": {"top_k": 1},
    }

    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value

    outputs = _products(res)[0]["dataItems"][0]["data"]["outputs"]
    assert outputs["scenario_policy"] == "warm"
    assert outputs["ranking"][0]["scenario_policy"] == "warm"


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_explanation_evidence_refs_are_field_paths(client_rec_ranking, new_task_id):
    payload = {
        "query": "science books",
        "profile_vector": {"genres": {"science": 1.0}},
        "candidates": [
            {
                "book_id": "r1",
                "title": "Evidence Candidate",
                "vector": [0.8, 0.7, 0.6],
                "kg_signal": 0.7,
                "novelty_score": 0.6,
                "diversity_score": 0.5,
                "genres": ["science"],
            }
        ],
        "constraints": {"top_k": 1},
    }

    res = _post(client_rec_ranking, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value

    item = _products(res)[0]["dataItems"][0]["data"]["outputs"]["ranking"][0]
    refs = item["explanation_evidence_refs"]
    assert "score_parts.collaborative" in refs
    assert "score_parts.semantic" in refs
    assert "score_parts.knowledge" in refs
    assert "score_parts.diversity" in refs
    assert "composite_score" in refs
