from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from acps_aip.aip_base_model import TaskCommand, TaskState
from acps_aip.aip_rpc_server import CommandHandlers, TaskManager, handle_rpc_request
from tests.conftest import build_rpc_payload


@pytest.fixture(autouse=True)
def reset_task_store():
    TaskManager._tasks = {}
    yield
    TaskManager._tasks = {}


@pytest.fixture
def client_aip_conformance():
    app = FastAPI()
    handlers = CommandHandlers()

    @app.post("/rpc")
    async def _rpc(request: Request):
        return await handle_rpc_request(request, handlers)

    return TestClient(app)


def _post(client: TestClient, payload: dict) -> dict:
    resp = client.post("/rpc", json=payload)
    assert resp.status_code == 200
    return resp.json()


def test_start_creates_task_with_identity_fields(client_aip_conformance, new_task_id):
    body = _post(client_aip_conformance, build_rpc_payload("hello", new_task_id))
    result = body["result"]

    assert result["id"] == new_task_id
    assert result["sessionId"] == "session-test"
    assert result["status"]["state"] == TaskState.Accepted.value

    first_message = result["messageHistory"][0]
    assert first_message["taskId"] == new_task_id
    assert first_message["sessionId"] == "session-test"
    assert first_message["senderId"] == "test-suite"


def test_start_is_idempotent_for_existing_task(client_aip_conformance, new_task_id):
    _post(client_aip_conformance, build_rpc_payload("hello", new_task_id))
    TaskManager.update_task_status(new_task_id, TaskState.Working)

    body = _post(client_aip_conformance, build_rpc_payload("retry", new_task_id))
    result = body["result"]

    assert result["id"] == new_task_id
    assert result["status"]["state"] == TaskState.Working.value
    assert len(result["messageHistory"]) == 2


def test_get_returns_not_found_for_unknown_task(client_aip_conformance):
    payload = build_rpc_payload("", "task-missing", command=TaskCommand.Get)
    body = _post(client_aip_conformance, payload)

    assert body["error"]["code"] == -32001
    assert body["error"]["data"]["taskId"] == "task-missing"


def test_complete_only_transitions_from_awaiting_completion(
    client_aip_conformance, new_task_id
):
    _post(client_aip_conformance, build_rpc_payload("", new_task_id))

    no_op = _post(
        client_aip_conformance,
        build_rpc_payload("", new_task_id, command=TaskCommand.Complete),
    )
    assert no_op["result"]["status"]["state"] == TaskState.Accepted.value

    TaskManager.update_task_status(new_task_id, TaskState.AwaitingCompletion)
    completed = _post(
        client_aip_conformance,
        build_rpc_payload("", new_task_id, command=TaskCommand.Complete),
    )
    assert completed["result"]["status"]["state"] == TaskState.Completed.value


@pytest.mark.parametrize(
    "terminal_state",
    [
        TaskState.Completed,
        TaskState.Failed,
        TaskState.Rejected,
        TaskState.Canceled,
    ],
)
def test_cancel_does_not_overwrite_terminal_states(
    client_aip_conformance, new_task_id, terminal_state
):
    _post(client_aip_conformance, build_rpc_payload("", new_task_id))
    TaskManager.update_task_status(new_task_id, terminal_state)

    canceled = _post(
        client_aip_conformance,
        build_rpc_payload("", new_task_id, command=TaskCommand.Cancel),
    )
    assert canceled["result"]["status"]["state"] == terminal_state.value


def test_missing_task_id_returns_invalid_params(client_aip_conformance, new_task_id):
    payload = build_rpc_payload("hello", new_task_id)
    payload["params"]["message"].pop("taskId", None)

    body = _post(client_aip_conformance, payload)
    assert body["error"]["code"] == -32602
    assert "taskId is required" in str(body["error"]["data"])
