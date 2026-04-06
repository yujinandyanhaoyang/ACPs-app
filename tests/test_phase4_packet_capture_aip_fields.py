from __future__ import annotations

import uuid
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

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


def _rpc_result(state: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "result": {
            "status": {"state": state},
            "products": [{"dataItems": [{"type": "data", "data": data}]}],
        },
    }


class _AsyncClientCapture:
    calls: List[Dict[str, Any]] = []

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    async def post(self, url: str, json: Dict[str, Any] | None = None):
        message = (((json or {}).get("params") or {}).get("message")) or {}
        payload = ((message.get("commandParams") or {}).get("payload")) or {}
        action = str(payload.get("action") or "")

        self.calls.append(
            {
                "url": url,
                "rpc": json or {},
                "message": message,
                "payload": payload,
                "action": action,
            }
        )

        if action == "rda.standby":
            return _FakeResponse(_rpc_result("completed", {"standby": True}))
        if action == "uma.build_profile":
            return _FakeResponse(
                _rpc_result(
                    "completed",
                    {
                        "profile_vector": [0.1, 0.2, 0.3],
                        "confidence": 0.81,
                        "behavior_genres": ["science_fiction"],
                        "strategy_suggestion": "balanced",
                    },
                )
            )
        if action == "bca.build_content_proposal":
            return _FakeResponse(
                _rpc_result(
                    "completed",
                    {
                        "outputs": {
                            "divergence_score": 0.35,
                            "weight_suggestion": {"ann_weight": 0.6, "cf_weight": 0.4},
                            "coverage_report": {"coverage": 0.85},
                            "alignment_status": "aligned",
                            "counter_proposal": {"reason": "promote diversity"},
                        }
                    },
                )
            )
        if action == "rda.arbitrate":
            return _FakeResponse(
                _rpc_result(
                    "completed",
                    {
                        "performative": "inform",
                        "final_weights": {"ann_weight": 0.62, "cf_weight": 0.38},
                        "score_weights": {"content": 0.62, "collab": 0.38},
                        "mmr_lambda": 0.48,
                        "strategy": "balanced",
                    },
                )
            )
        if action == "engine.dispatch":
            return _FakeResponse(
                _rpc_result(
                    "completed",
                    {
                        "performative": "inform",
                        "recommendations": [{"book_id": "b1", "title": "Foundation"}],
                        "explanations": [{"book_id": "b1", "justification": "Strong intent match"}],
                    },
                )
            )
        return _FakeResponse(_rpc_result("failed", {}), status_code=500)


@pytest.mark.usefixtures("patch_openai")
def test_packet_capture_style_aip_field_completeness(monkeypatch):
    _AsyncClientCapture.calls = []
    monkeypatch.setenv("READER_PROFILE_RPC_URL", "http://mock/rpa")
    monkeypatch.setenv("BOOK_CONTENT_RPC_URL", "http://mock/bca")
    monkeypatch.setenv("RECOMMENDATION_DECISION_RPC_URL", "http://mock/rda")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_RPC_URL", "http://mock/engine")
    monkeypatch.setattr(concierge, "PARTNER_MODE", "remote")
    monkeypatch.setattr(concierge.httpx, "AsyncClient", _AsyncClientCapture)
    monkeypatch.setattr(concierge, "_discover_partner_rpc_url", lambda _key: None)

    client = TestClient(concierge.app)
    payload = {
        "session_id": f"sess-{uuid.uuid4()}",
        "user_id": "phase4-packet-user",
        "query": "Recommend thoughtful science fiction with diversity",
        "history": [{"title": "Dune", "genres": ["science_fiction"], "rating": 5}],
        "books": [{"book_id": "b1", "title": "Foundation", "genres": ["science_fiction"]}],
    }
    resp = client.post("/user_api", json=payload)
    assert resp.status_code == 200

    calls = _AsyncClientCapture.calls
    assert len(calls) == 5

    by_action = {c["action"]: c for c in calls}
    for action in ["rda.standby", "uma.build_profile", "bca.build_content_proposal", "rda.arbitrate", "engine.dispatch"]:
        assert action in by_action

    # Packet-capture style envelope checks: required AIP message fields are present.
    required_message_fields = ["type", "id", "sentAt", "senderRole", "senderId", "command", "taskId", "sessionId"]
    for c in calls:
        msg = c["message"]
        for field in required_message_fields:
            assert field in msg
            assert msg[field] not in (None, "")
        assert msg["type"] == "message"
        assert msg["command"] == "start"
        assert isinstance(msg.get("commandParams"), dict)
        assert isinstance(msg["commandParams"].get("payload"), dict)

    # Verify performative semantics on RC outbound flow.
    assert by_action["rda.standby"]["payload"]["performative"] == "request"
    assert by_action["uma.build_profile"]["payload"]["performative"] == "request"
    assert by_action["bca.build_content_proposal"]["payload"]["performative"] == "request"
    assert by_action["rda.arbitrate"]["payload"]["performative"] == "request"
    assert by_action["engine.dispatch"]["payload"]["performative"] == "request"

    # Verify proposal semantics inside arbitration payload.
    arbitration_payload = by_action["rda.arbitrate"]["payload"]
    assert arbitration_payload["profile_proposal"]["performative"] == "propose"
    assert arbitration_payload["content_proposal"]["performative"] == "propose"
    assert arbitration_payload["content_proposal"]["counter_proposal_performative"] == "reject-proposal"
