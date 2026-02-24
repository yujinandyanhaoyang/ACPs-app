import json

import pytest

from acps_aip.aip_base_model import TaskCommand, TaskState
from tests.conftest import build_rpc_payload


def _post(client, payload):
    resp = client.post("/book-content/rpc", json=payload)
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
    print("\n[book_content_agent E2E] RPC response:")
    print(json.dumps(body, ensure_ascii=False, indent=2))


@pytest.mark.usefixtures("patch_openai")
def test_start_missing_candidates_prompts_for_input(client_book_content, new_task_id):
    payload = {
        "books": [],
        "candidate_ids": [],
    }
    res = _post(client_book_content, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.AwaitingInput.value
    data_items = res["result"]["status"].get("dataItems") or []
    assert any("missing_fields" in (item.get("text") or "") for item in data_items)


@pytest.mark.usefixtures("patch_openai", "patch_embeddings_384d")
def test_start_completes_with_valid_books(client_book_content, new_task_id):
    payload = {
        "books": [
            {
                "book_id": "b1",
                "title": "Deep Learning for Readers",
                "description": "A practical guide for technology enthusiasts.",
                "genres": ["technology", "nonfiction"],
                "pages": 320,
            },
            {
                "book_id": "b2",
                "title": "Global Stories",
                "description": "A multicultural fiction anthology with hopeful tone.",
                "genres": ["fiction"],
                "page_count": 260,
            },
        ],
        "kg_mode": "local",
    }
    res = _post(client_book_content, _with_payload(new_task_id, payload))
    assert _state(res) == TaskState.Completed.value
    assert len(_products(res)) == 1
    structured = _products(res)[0]["dataItems"][0]
    assert structured["type"] == "data"
    outputs = structured["data"]["outputs"]
    assert len(outputs["content_vectors"]) == 2
    assert outputs["content_vectors"][0]["vector_dim"] == 384
    assert outputs["embedding_backend"]["backend"] == "deterministic-384d"
    assert "kg_refs" in outputs
    assert "book_tags" in outputs
    assert "embedding_backend" in outputs


@pytest.mark.usefixtures("patch_openai")
def test_continue_unblocks_after_missing_input(client_book_content, new_task_id):
    start_payload = {"books": []}
    start_res = _post(client_book_content, _with_payload(new_task_id, start_payload))
    assert _state(start_res) == TaskState.AwaitingInput.value

    continue_payload = {
        "candidate_ids": ["book-101", "book-102"],
        "use_remote_kg": True,
        "kg_endpoint": "https://kg.example.com",
    }
    cont = _post(
        client_book_content,
        _with_payload(new_task_id, continue_payload, command=TaskCommand.Continue),
    )
    assert _state(cont) == TaskState.Completed.value
    products = _products(cont)
    summary = products[0]["dataItems"][1]["text"]
    assert "Books analyzed" in summary


@pytest.mark.usefixtures("patch_openai")
def test_book_content_agent_end_to_end_env_and_llm(monkeypatch, client_book_content, new_task_id):
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    async def fake_call(messages, model, temperature=None, max_tokens=None):
        return json.dumps(
            {
                "llm_tags": [
                    {"book_id": "b1", "tags": ["space-opera", "politics"]},
                    {"book_id": "b2", "tags": ["multicultural", "uplifting"]},
                ]
            }
        )

    monkeypatch.setattr(
        "agents.book_content_agent.book_content_agent.call_openai_chat",
        fake_call,
    )

    payload = {
        "books": [
            {
                "book_id": "b1",
                "title": "Dune",
                "description": "Epic science fiction with political strategy and ecology.",
                "genres": ["science", "fiction"],
                "kg_node_id": "kg:dune",
            },
            {
                "book_id": "b2",
                "title": "The Left Hand of Darkness",
                "description": "A global classic on identity and culture.",
                "genres": ["science", "classic"],
            },
        ],
        "kg_mode": "remote",
        "use_remote_kg": True,
        "kg_endpoint": "https://kg.books.local",
    }

    res = _post(client_book_content, _with_payload(new_task_id, payload))
    _print_e2e_response(res)
    assert _state(res) == TaskState.Completed.value

    structured = _products(res)[0]["dataItems"][0]["data"]
    outputs = structured["outputs"]
    llm_enrichment = outputs["llm_enrichment"]
    assert llm_enrichment["source"] == "llm"
    assert len(llm_enrichment["llm_tags"]) >= 1
    assert len(outputs["kg_refs"]) >= 1
    diagnostics = structured["diagnostics"]
    assert diagnostics["api_key_present"] is True
    assert diagnostics["embedding_backend"]["backend"] in {"sentence-transformers", "hash-fallback", "dashscope"}
