import json

import pytest

from acps_aip.aip_base_model import TaskCommand, TaskState
from tests.conftest import build_rpc_payload


def _post(client, payload):
    resp = client.post("/reader-profile/rpc", json=payload)
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
    print("\n[reader_profile_agent E2E] RPC response:")
    print(json.dumps(body, ensure_ascii=False, indent=2))


@pytest.mark.usefixtures("patch_openai")
def test_start_missing_history_prompts_for_input(client_reader_profile, new_task_id):
    payload = {
        "user_profile": {},
        "history": [],
        "reviews": [],
    }
    res = _post(client_reader_profile, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.AwaitingInput.value
    data_items = res["result"]["status"].get("dataItems") or []
    assert any("missing_fields" in (item.get("text") or "") for item in data_items)


@pytest.mark.usefixtures("patch_openai")
def test_start_completes_with_valid_history(client_reader_profile, new_task_id):
    payload = {
        "user_profile": {"age": 28, "preferred_language": "en"},
        "history": [
            {
                "title": "Project Hail Mary",
                "genres": ["science_fiction", "adventure"],
                "rating": 5,
                "format": "audiobook",
                "language": "en",
            },
            {
                "title": "三体",
                "genres": ["science_fiction", "thriller"],
                "rating": 4,
                "format": "ebook",
                "language": "zh",
            },
        ],
        "reviews": [
            {"rating": 5, "text": "Loved the pacing"},
            {"rating": 4, "text": "Great science discussion"},
        ],
        "scenario": "warm",
    }
    res = _post(client_reader_profile, _with_payload(new_task_id, payload))
    _print_e2e_response(res)
    assert _state(res) == TaskState.Completed.value
    assert len(_products(res)) == 1
    structured = _products(res)[0]["dataItems"][0]
    assert structured["type"] == "data"
    assert "preference_vector" in structured["data"]
    assert "intent_keywords" in structured["data"]


@pytest.mark.usefixtures("patch_openai")
def test_continue_unblocks_after_missing_data(client_reader_profile, new_task_id):
    start_payload = {
        "user_profile": {},
        "history": [],
        "reviews": [],
    }
    start_res = _post(client_reader_profile, _with_payload(new_task_id, start_payload))
    assert _state(start_res) == TaskState.AwaitingInput.value

    continue_payload = {
        "user_profile": {"age": 30},
        "history": [
            {
                "title": "The Pragmatic Programmer",
                "genres": ["nonfiction", "technology"],
                "rating": 5,
                "format": "print",
                "language": "en",
            }
        ],
    }
    cont = _post(
        client_reader_profile,
        _with_payload(new_task_id, continue_payload, command=TaskCommand.Continue),
    )
    assert _state(cont) == TaskState.Completed.value
    products = _products(cont)
    assert products and products[0]["dataItems"]
    summary = products[0]["dataItems"][1]["text"]
    assert "Top genres" in summary


@pytest.mark.usefixtures("patch_openai")
def test_reader_profile_agent_end_to_end_env_and_llm(
    monkeypatch, client_reader_profile, new_task_id
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    async def fake_call(messages, model, temperature=None, max_tokens=None):
        return json.dumps(
            {
                "keywords": ["deep space", "character arcs", "inventive plots"],
                "intent_summary": "Sci-fi exploration with emotional depth",
            }
        )

    monkeypatch.setattr(
        "agents.reader_profile_agent.profile_agent.call_openai_chat",
        fake_call,
    )

    payload = {
        "user_profile": {"age": 25, "preferred_language": "en"},
        "history": [
            {
                "title": "Dune",
                "genres": ["science_fiction", "epic"],
                "themes": ["politics", "ecology"],
                "rating": 5,
                "format": "print",
                "language": "en",
                "pacing": "steady",
                "difficulty": "advanced",
            },
            {
                "title": "The Left Hand of Darkness",
                "genres": ["science_fiction", "classic"],
                "themes": ["identity", "culture"],
                "rating": 4,
                "format": "ebook",
                "language": "en",
                "pacing": "thoughtful",
                "pages": 300,
            },
        ],
        "reviews": [
            {"rating": 5, "text": "Loved the sweeping worldbuilding and political intrigue."},
            {"rating": 4, "text": "Prefer stories that balance science ideas with human emotions."},
        ],
        "scenario": "explore",
    }

    res = _post(client_reader_profile, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value
    structured = _products(res)[0]["dataItems"][0]["data"]
    intents = structured["intent_keywords"]
    assert intents["source"] == "llm"
    assert len(intents["keywords"]) >= 2
    diagnostics = structured["diagnostics"]["environment"]
    assert diagnostics["api_key_present"] is True
