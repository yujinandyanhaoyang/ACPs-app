"""
book_content_agent live HTTP E2E tests (requires real service process).

Example:
    set END_TO_END=1
    set BOOK_CONTENT_BASE_URL=http://localhost:8212
    set BOOK_CONTENT_AIP_ENDPOINT=/book-content/rpc
    venv\Scripts\python.exe -m pytest -q tests/test_book_content_agent_e2e.py
"""

import os
import uuid
import time
from datetime import datetime, timezone

import pytest
import requests

pytestmark = pytest.mark.skipif(
    os.getenv("END_TO_END") != "1",
    reason="Set END_TO_END=1 to run live HTTP integration tests.",
)


@pytest.fixture(autouse=True)
def patch_openai():
    yield


BASE_URL = os.getenv("BOOK_CONTENT_BASE_URL", "http://localhost:8212").rstrip("/")
ENDPOINT = os.getenv("BOOK_CONTENT_AIP_ENDPOINT", "/book-content/rpc")
RPC_URL = f"{BASE_URL}{ENDPOINT}"


def _build_rpc_payload(payload: dict, task_id: str, command: str = "start"):
    sent_at = datetime.now(timezone.utc).isoformat()
    message = {
        "type": "message",
        "id": str(uuid.uuid4()),
        "sentAt": sent_at,
        "senderRole": "leader",
        "senderId": "book-content-e2e",
        "command": command,
        "dataItems": [{"type": "text", "text": ""}],
        "taskId": task_id,
        "sessionId": "session-book-content-e2e",
        "commandParams": {"payload": payload},
    }
    return {
        "jsonrpc": "2.0",
        "method": "rpc",
        "id": str(uuid.uuid4()),
        "params": {"message": message},
    }


def _state(resp_json):
    return ((resp_json or {}).get("result") or {}).get("status", {}).get("state")


def _products(resp_json):
    return ((resp_json or {}).get("result") or {}).get("products") or []


def _post(payload: dict, timeout=30):
    try:
        response = requests.post(RPC_URL, json=payload, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        pytest.skip(f"Cannot connect to server at {RPC_URL}: {exc}")
    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"
    return response.json()


def _get(task_id: str):
    return _post(_build_rpc_payload({}, task_id, command="get"))


def _wait_for_state(task_id: str, expect_set: set[str], timeout_s=6.0, interval_s=0.2):
    deadline = time.time() + timeout_s
    latest = None
    while time.time() < deadline:
        latest = _get(task_id)
        if _state(latest) in expect_set:
            return _state(latest), latest
        time.sleep(interval_s)
    return _state(latest), latest


def test_http_live_book_content_start_to_completed():
    task_id = f"task-{uuid.uuid4()}"
    payload = {
        "books": [
            {
                "book_id": "live-1",
                "title": "Live Test Book",
                "description": "A practical technology guide with global perspective.",
                "genres": ["technology", "nonfiction"],
            }
        ],
        "kg_mode": "remote",
        "use_remote_kg": True,
        "kg_endpoint": "https://kg.books.live",
    }
    start = _post(_build_rpc_payload(payload, task_id))
    assert _state(start) in {"completed", "working", "accepted"}
    state, latest = _wait_for_state(task_id, {"completed", "failed", "awaiting-input"})
    assert state == "completed"
    assert len(_products(latest)) >= 1


def test_http_live_book_content_continue_path():
    task_id = f"task-{uuid.uuid4()}"
    start = _post(_build_rpc_payload({"books": []}, task_id))
    assert _state(start) in {"awaiting-input", "working", "accepted"}

    continue_payload = {
        "candidate_ids": ["live-candidate-1", "live-candidate-2"],
        "kg_mode": "remote",
        "use_remote_kg": True,
        "kg_endpoint": "https://kg.books.live",
    }
    cont = _post(_build_rpc_payload(continue_payload, task_id, command="continue"))
    assert _state(cont) in {"completed", "working", "awaiting-input"}
    state, latest = _wait_for_state(task_id, {"completed", "failed", "awaiting-input"})
    assert state == "completed"
    assert len(_products(latest)) >= 1
