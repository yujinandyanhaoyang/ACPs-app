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


@pytest.mark.usefixtures("patch_openai")
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
    assert structured["diagnostics"]["api_key_present"] is True
