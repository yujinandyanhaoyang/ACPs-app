import os
import sys
import uuid
import pathlib
import importlib
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

# Ensure project root (parent of this tests directory) is on sys.path in case pytest
# changes the working directory during collection.
ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _optional_import(path: str):
    try:
        return importlib.import_module(path)
    except ModuleNotFoundError:
        return None


# Import the FastAPI app objects directly from each agent module when available
beijing_urban = _optional_import("beijing_urban.beijing_urban")
beijing_rural = _optional_import("beijing_rural.beijing_rural")
beijing_catering = _optional_import("beijing_catering.beijing_catering")
china_hotel = _optional_import("china_hotel.china_hotel")
china_transport = _optional_import("china_transport.china_transport")
reader_profile_agent = _optional_import("agents.reader_profile_agent.profile_agent")
book_content_agent = _optional_import("agents.book_content_agent.book_content_agent")
rec_ranking_agent = _optional_import("agents.rec_ranking_agent.rec_ranking_agent")
reading_concierge = _optional_import("reading_concierge.reading_concierge")

from acps_aip.aip_base_model import Message, TextDataItem, TaskCommand

# Disable actual OpenAI network calls by monkeypatching the client method.
# We will craft a deterministic fake response JSON depending on the agent under test and input text.


class DummyMessage:
    def __init__(self, content: str):
        self.content = content


class DummyChoice:
    def __init__(self, content: str):
        self.message = DummyMessage(content)


class DummyCompletion:
    def __init__(self, content: str):
        self.choices = [DummyChoice(content)]


@pytest.fixture(autouse=True)
def patch_openai(monkeypatch):
    """Auto patch the OpenAI async client so tests run offline.

    Replaces ``base._get_async_openai_client`` with a lightweight fake that
    returns deterministic ``DummyCompletion`` objects.

    Input cues:
      - contains keyword REJECT -> decision=reject with reason.
      - contains keyword BADJSON -> return malformed JSON to test error handling.
      - otherwise decision=accept with simple plan.
    """
    import base as base_module

    async def fake_create(*, messages, model, **kwargs):
        user_content = messages[-1]["content"].lower()
        if '"book_ids"' in user_content or "book_ids" in user_content:
            return DummyCompletion('{"book_ids":["b1","b2","b3"]}')
        if "badjson" in user_content:
            return DummyCompletion("not a json string")
        if "reject" in user_content:
            return DummyCompletion('{"decision":"reject","reason":"测试拒绝分支"}')
        return DummyCompletion(
            '{"decision":"accept","plan":"示例规划输出 plan for model %s"}' % model
        )

    async def fake_dashscope_embeddings(texts, model_name, base_url, api_key):
        vectors = []
        for idx, _ in enumerate(texts):
            vectors.append([round(0.1 * (idx + 1), 4), 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        return vectors, {"backend": "dashscope", "model": model_name, "vector_dim": 8}

    class _FakeCompletions:
        create = staticmethod(fake_create)

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeAsyncClient:
        chat = _FakeChat()

    monkeypatch.setattr(base_module, "_get_async_openai_client", lambda: _FakeAsyncClient())

    import services.model_backends as model_backends_module

    monkeypatch.setattr(
        model_backends_module,
        "_resolve_dashscope_embeddings",
        fake_dashscope_embeddings,
    )


@pytest.fixture(scope="session")
def client_urban():
    if not beijing_urban:
        pytest.skip("beijing_urban module unavailable in this workspace")
    return TestClient(beijing_urban.app)


@pytest.fixture(scope="session")
def client_rural():
    if not beijing_rural:
        pytest.skip("beijing_rural module unavailable in this workspace")
    return TestClient(beijing_rural.app)


@pytest.fixture(scope="session")
def client_catering():
    if not beijing_catering:
        pytest.skip("beijing_catering module unavailable in this workspace")
    return TestClient(beijing_catering.app)


@pytest.fixture(scope="session")
def client_hotel():
    if not china_hotel:
        pytest.skip("china_hotel module unavailable in this workspace")
    return TestClient(china_hotel.app)


@pytest.fixture(scope="session")
def client_transport():
    if not china_transport:
        pytest.skip("china_transport module unavailable in this workspace")
    return TestClient(china_transport.app)


@pytest.fixture(scope="session")
def client_reader_profile():
    if not reader_profile_agent:
        pytest.skip("reader_profile_agent module unavailable in this workspace")
    return TestClient(reader_profile_agent.app)


@pytest.fixture(scope="session")
def client_book_content():
    if not book_content_agent:
        pytest.skip("book_content_agent module unavailable in this workspace")
    return TestClient(book_content_agent.app)


@pytest.fixture(scope="session")
def client_rec_ranking():
    if not rec_ranking_agent:
        pytest.skip("rec_ranking_agent module unavailable in this workspace")
    return TestClient(rec_ranking_agent.app)


@pytest.fixture(scope="session")
def client_reading_concierge():
    if not reading_concierge:
        pytest.skip("reading_concierge module unavailable in this workspace")
    return TestClient(reading_concierge.app)


def build_rpc_payload(
    app_message: str, task_id: str, command: TaskCommand = TaskCommand.Start
):
    # Minimal RPC request body aligned with RpcRequest schema
    sent_at = datetime.now(timezone.utc).isoformat()
    message = {
        "type": "message",
        "id": str(uuid.uuid4()),
        "sentAt": sent_at,
        "senderRole": "leader",
        "senderId": "test-suite",
        "command": command.value,
        "dataItems": [{"type": "text", "text": app_message}],
        "taskId": task_id,
        "sessionId": "session-test",
    }
    return {
        "jsonrpc": "2.0",
        "method": "rpc",
        "id": str(uuid.uuid4()),
        "params": {"message": message},
    }


@pytest.fixture
def new_task_id():
    return f"task-{uuid.uuid4()}"


@pytest.fixture
def patch_embeddings_384d(monkeypatch):
    """Patch embedding generation with deterministic 384-d vectors.

    This fixture is opt-in and is used by tests that must exercise vector-size
    code paths aligned with the offline SentenceTransformer default.
    """

    async def _fake_generate_text_embeddings_async(texts, model_name, fallback_dim=12):
        vectors = []
        text_list = [str(text or "") for text in texts]
        for idx, text in enumerate(text_list):
            base = ((len(text) + idx) % 31) / 31.0
            vector = [round((base + (j % 17) / 17.0) % 1.0, 6) for j in range(384)]
            vectors.append(vector)
        return vectors, {
            "backend": "deterministic-384d",
            "model": model_name,
            "vector_dim": 384,
        }

    import services.model_backends as model_backends_module

    monkeypatch.setattr(
        model_backends_module,
        "generate_text_embeddings_async",
        _fake_generate_text_embeddings_async,
    )

    if book_content_agent is not None:
        monkeypatch.setattr(
            book_content_agent,
            "generate_text_embeddings_async",
            _fake_generate_text_embeddings_async,
        )
    if rec_ranking_agent is not None:
        monkeypatch.setattr(
            rec_ranking_agent,
            "generate_text_embeddings_async",
            _fake_generate_text_embeddings_async,
        )
