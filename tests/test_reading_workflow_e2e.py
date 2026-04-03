from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from reading_concierge import reading_concierge


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"fake status error: {self.status_code}")


class _AsyncClientMock:
    actions: List[str] = []
    payload_by_action: Dict[str, Dict[str, Any]] = {}

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    async def post(self, url: str, json: Dict[str, Any] | None = None):
        payload = (((json or {}).get("params") or {}).get("message") or {}).get("commandParams", {}).get("payload", {})
        action = str(payload.get("action") or "")
        self.actions.append(action)
        self.payload_by_action[action] = payload

        if action == "rda.standby":
            return _FakeResponse(_rpc(state="completed", data={"ok": True}))
        if action == "uma.build_profile":
            return _FakeResponse(_rpc(state="completed", data={"profile_vector": [0.9, 0.1], "confidence": 0.8}))
        if action == "bca.build_content_proposal":
            return _FakeResponse(
                _rpc(
                    state="completed",
                    data={
                        "outputs": {
                            "divergence_score": 0.25,
                            "weight_suggestion": {"ann_weight": 0.62, "cf_weight": 0.38},
                            "coverage_report": {"coverage": 0.88},
                            "content_vectors": [{"book_id": "wf-001", "v": [0.2, 0.4]}],
                        }
                    },
                )
            )
        if action == "rda.arbitrate":
            return _FakeResponse(
                _rpc(
                    state="completed",
                    data={
                        "final_weights": {"ann_weight": 0.66, "cf_weight": 0.34},
                        "score_weights": {"content": 0.6, "collab": 0.4},
                        "mmr_lambda": 0.42,
                        "strategy": "balanced",
                    },
                )
            )
        if action == "engine.dispatch":
            return _FakeResponse(
                _rpc(
                    state="completed",
                    data={
                        "recommendations": [
                            {"book_id": "wf-001", "title": "Foundation"},
                            {"book_id": "wf-002", "title": "The Left Hand of Darkness"},
                        ],
                        "explanations": [{"book_id": "wf-001", "justification": "Preference and content alignment"}],
                    },
                )
            )
        return _FakeResponse(_rpc(state="failed", data={}), status_code=500)


def _rpc(state: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "result": {
            "status": {"state": state},
            "products": [{"dataItems": [{"type": "data", "data": data}]}],
        },
    }


@pytest.mark.usefixtures("patch_openai")
def test_reading_workflow_e2e_validates_layered_pipeline(monkeypatch):
    _AsyncClientMock.actions = []
    _AsyncClientMock.payload_by_action = {}

    monkeypatch.setenv("READER_PROFILE_RPC_URL", "http://mock/rpa")
    monkeypatch.setenv("BOOK_CONTENT_RPC_URL", "http://mock/bca")
    monkeypatch.setenv("RECOMMENDATION_DECISION_RPC_URL", "http://mock/rda")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_RPC_URL", "http://mock/engine")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(reading_concierge, "PARTNER_MODE", "remote")
    monkeypatch.setattr(reading_concierge.httpx, "AsyncClient", _AsyncClientMock)

    client = TestClient(reading_concierge.app)
    payload = {
        "session_id": "session-e2e-01",
        "user_id": "e2e_user_01",
        "query": "Recommend diverse thoughtful science fiction",
        "history": [{"title": "Dune", "genres": ["science_fiction"], "rating": 5, "language": "en"}],
        "reviews": [{"rating": 5, "text": "I like worldbuilding and ideas"}],
        "books": [
            {
                "book_id": "wf-001",
                "title": "Foundation",
                "description": "Galactic empire and psychohistory.",
                "genres": ["science_fiction"],
            },
            {
                "book_id": "wf-002",
                "title": "The Left Hand of Darkness",
                "description": "Identity and culture exploration.",
                "genres": ["science_fiction"],
            },
        ],
        "constraints": {"top_k": 2},
    }

    resp = client.post("/user_api", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    assert body["state"] == "completed"
    assert body["partner_tasks"]["rda_standby"]["state"] == "completed"
    assert body["partner_tasks"]["rpa"]["state"] == "completed"
    assert body["partner_tasks"]["bca"]["state"] == "completed"
    assert body["partner_tasks"]["rda"]["state"] == "completed"
    assert body["partner_tasks"]["engine"]["state"] == "completed"

    actions = _AsyncClientMock.actions
    assert len(actions) == 5
    assert actions[0] == "rda.standby"
    assert set(actions[1:3]) == {"uma.build_profile", "bca.build_content_proposal"}
    assert actions[3:] == ["rda.arbitrate", "engine.dispatch"]

    engine_payload = _AsyncClientMock.payload_by_action["engine.dispatch"]
    assert engine_payload["ann_weight"] == pytest.approx(0.66)
    assert engine_payload["cf_weight"] == pytest.approx(0.34)
    assert engine_payload["strategy"] == "balanced"

    assert len(body["recommendations"]) == 2
    assert body["recommendations"][0]["book_id"] == "wf-001"
