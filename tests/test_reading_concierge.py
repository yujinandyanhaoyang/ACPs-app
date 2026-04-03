from __future__ import annotations

import uuid
from typing import Any, Dict, List

import pytest

import reading_concierge.reading_concierge as concierge


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
    call_actions: List[str] = []
    payloads_by_action: Dict[str, Dict[str, Any]] = {}

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    async def post(self, url: str, json: Dict[str, Any] | None = None):
        payload = (((json or {}).get("params") or {}).get("message") or {}).get("commandParams", {}).get("payload", {})
        action = str(payload.get("action") or "")
        self.call_actions.append(action)
        self.payloads_by_action[action] = payload

        if action == "rda.standby":
            return _FakeResponse(_rpc_result(state="completed", data={"standby": True}))
        if action == "uma.build_profile":
            return _FakeResponse(
                _rpc_result(
                    state="completed",
                    data={
                        "profile_vector": [0.1, 0.2, 0.3],
                        "confidence": 0.82,
                        "behavior_genres": ["science_fiction"],
                        "strategy_suggestion": "balanced",
                    },
                )
            )
        if action == "bca.build_content_proposal":
            return _FakeResponse(
                _rpc_result(
                    state="completed",
                    data={
                        "outputs": {
                            "divergence_score": 0.35,
                            "weight_suggestion": {"ann_weight": 0.58, "cf_weight": 0.42},
                            "coverage_report": {"coverage": 0.9},
                            "alignment_status": "aligned",
                            "content_vectors": [{"book_id": "b1", "v": [0.1, 0.2]}],
                        }
                    },
                )
            )
        if action == "rda.arbitrate":
            return _FakeResponse(
                _rpc_result(
                    state="completed",
                    data={
                        "final_weights": {"ann_weight": 0.7, "cf_weight": 0.3},
                        "score_weights": {"content": 0.7, "collab": 0.3},
                        "mmr_lambda": 0.55,
                        "strategy": "exploit",
                    },
                )
            )
        if action == "engine.dispatch":
            return _FakeResponse(
                _rpc_result(
                    state="completed",
                    data={
                        "recommendations": [{"book_id": "b1", "title": "Foundation"}],
                        "explanations": [{"book_id": "b1", "justification": "High intent match"}],
                    },
                )
            )

        return _FakeResponse(_rpc_result(state="failed", data={}), status_code=500)


def _rpc_result(state: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "result": {
            "status": {"state": state},
            "products": [
                {
                    "dataItems": [
                        {
                            "type": "data",
                            "data": data,
                        }
                    ]
                }
            ],
        },
    }


@pytest.fixture
def mock_partner_pipeline(monkeypatch):
    _AsyncClientMock.call_actions = []
    _AsyncClientMock.payloads_by_action = {}

    monkeypatch.setenv("READER_PROFILE_RPC_URL", "http://mock/rpa")
    monkeypatch.setenv("BOOK_CONTENT_RPC_URL", "http://mock/bca")
    monkeypatch.setenv("RECOMMENDATION_DECISION_RPC_URL", "http://mock/rda")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_RPC_URL", "http://mock/engine")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(concierge, "PARTNER_MODE", "remote")
    monkeypatch.setattr(concierge.httpx, "AsyncClient", _AsyncClientMock)
    return _AsyncClientMock


def test_demo_status_route_available(client_reading_concierge):
    resp = client_reading_concierge.get("/demo/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["service"] == "reading_concierge"
    assert "demo_page_available" in payload
    assert "partner_mode" in payload
    assert "redis_url" in payload


def test_user_api_requires_user_id_and_query(client_reading_concierge):
    missing_user = client_reading_concierge.post("/user_api", json={"query": "recommend books"})
    assert missing_user.status_code == 422

    missing_query = client_reading_concierge.post("/user_api", json={"user_id": "u-1", "query": ""})
    assert missing_query.status_code == 422


@pytest.mark.usefixtures("patch_openai")
def test_user_api_debug_allows_anonymous_payload_override(client_reading_concierge, mock_partner_pipeline):
    payload = {
        "query": "recommend sci-fi",
        "constraints": {"top_k": 1},
        "books": [{"book_id": "dbg-1", "title": "Debug Candidate"}],
    }
    resp = client_reading_concierge.post("/user_api_debug", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"].startswith("anon-")


def test_orchestration_pipeline_states_and_order(client_reading_concierge, mock_partner_pipeline):
    payload = {
        "session_id": f"sess-{uuid.uuid4()}",
        "user_id": "u-flow-1",
        "query": "I want personalized sci-fi recommendations.",
        "user_profile": {"preferred_language": "en"},
        "history": [{"title": "Dune", "genres": ["science_fiction"], "rating": 5}],
        "reviews": [{"rating": 5, "text": "Loved worldbuilding."}],
        "books": [{"book_id": "b1", "title": "Foundation", "genres": ["science_fiction"]}],
    }

    resp = client_reading_concierge.post("/user_api", json=payload)
    assert resp.status_code == 200
    res = resp.json()

    assert res["state"] == "completed"
    assert res["partner_tasks"]["rda_standby"]["state"] == "completed"
    assert res["partner_tasks"]["rpa"]["state"] == "completed"
    assert res["partner_tasks"]["bca"]["state"] == "completed"
    assert res["partner_tasks"]["rda"]["state"] == "completed"
    assert res["partner_tasks"]["engine"]["state"] == "completed"

    actions = mock_partner_pipeline.call_actions
    assert len(actions) == 5
    assert actions[0] == "rda.standby"
    assert set(actions[1:3]) == {"uma.build_profile", "bca.build_content_proposal"}
    assert actions[3] == "rda.arbitrate"
    assert actions[4] == "engine.dispatch"

    assert res["recommendations"]
    assert res["explanations"]


def test_resolve_partner_prefers_adp_discovery_over_env(monkeypatch):
    monkeypatch.setenv("READER_PROFILE_RPC_URL", "http://env/rpa")
    monkeypatch.setattr(concierge, "_discover_partner_rpc_url", lambda key: "http://adp/rpa" if key == "profile" else None)

    partner = concierge._resolve_partner("profile")
    assert partner["remote_url"] == "http://adp/rpa"
    assert partner["discovery"] == "adp"
