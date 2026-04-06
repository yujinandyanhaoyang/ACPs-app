from __future__ import annotations

import uuid
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from acps_aip.aip_base_model import TaskCommand
from partners.online.feedback_agent import agent as feedback_agent
from partners.online.reader_profile_agent import agent as reader_profile_agent
from partners.online.recommendation_decision_agent import agent as recommendation_decision_agent
from partners.online.recommendation_engine_agent import agent as recommendation_engine_agent
from tests.conftest import build_rpc_payload


def _rpc_with_payload(payload: Dict[str, Any], command: TaskCommand = TaskCommand.Start) -> Dict[str, Any]:
    wrapper = build_rpc_payload("", f"task-{uuid.uuid4()}", command=command)
    wrapper["params"]["message"]["commandParams"] = {"payload": payload}
    return wrapper


def _extract_result_data(body: Dict[str, Any]) -> Dict[str, Any]:
    products = body.get("result", {}).get("products") or []
    assert products, "RPC result missing products"
    data_items = products[0].get("dataItems") or []
    assert data_items, "RPC product missing dataItems"
    first = data_items[0]
    assert first.get("type") == "data", "first dataItem is not structured data"
    assert isinstance(first.get("data"), dict), "structured dataItem missing dict payload"
    return first["data"]


def test_rda_counter_proposal_triggers_evidence_request_branch():
    client = TestClient(recommendation_decision_agent.app)
    payload = {
        "action": "rda.arbitrate",
        "profile_proposal": {
            "profile_vector": [0.1, 0.2, 0.3],
            "confidence": 0.82,
            "strategy_suggestion": "balanced",
        },
        "content_proposal": {
            "divergence_score": 0.25,
            "weight_suggestion": {"ann_weight": 0.6, "cf_weight": 0.4},
            "coverage_report": {"coverage": 0.9},
            # intentionally no counter_proposal field
        },
        "counter_proposal_received": True,
    }

    resp = client.post("/recommendation-decision/rpc", json=_rpc_with_payload(payload))
    assert resp.status_code == 200
    body = resp.json()
    data = _extract_result_data(body)

    rounds = data.get("quality_rounds") or []
    assert rounds, "expected at least one quality round"
    first_round = rounds[0]
    assert first_round.get("status") == "needs_evidence"

    issue_reasons = {issue.get("reason") for issue in first_round.get("issues") or []}
    assert "counter_proposal_missing_payload" in issue_reasons

    evidence_requests = first_round.get("evidence_requests") or []
    assert any(
        req.get("to") == "book_content_agent" and req.get("reason") == "counter_proposal_missing_payload"
        for req in evidence_requests
    )


@pytest.mark.usefixtures("patch_openai")
def test_feedback_agent_routes_informs_to_rda_rpa_engine(monkeypatch):
    # Trigger all three informs deterministically.
    monkeypatch.setattr(feedback_agent.CFG, "user_update_threshold", 1)
    monkeypatch.setattr(feedback_agent.CFG, "cf_retrain_threshold", 1)

    captured = []

    async def _fake_emit(partner_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        captured.append({"partner": partner_key, "payload": payload})
        return {"partner": partner_key, "status": "sent", "route": "test"}

    monkeypatch.setattr(feedback_agent, "_emit_inform", _fake_emit)

    client = TestClient(feedback_agent.app)
    event = {
        "user_id": "phase4-user-1",
        "event_type": "rate_5",
        "session_id": "phase4-session-1",
        "context_type": "low_conf_high_div",
        "action": "balanced",
        "session_completed": True,
    }
    resp = client.post("/feedback/webhook", json=event)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"

    partners = {x["partner"] for x in captured}
    assert partners == {"rda", "rpa", "engine"}

    payload_by_partner = {x["partner"]: x["payload"] for x in captured}
    assert payload_by_partner["rda"]["performative"] == "inform"
    assert payload_by_partner["rda"]["action"] == "feedback.reward"
    assert payload_by_partner["rpa"]["action"] == "feedback.update_profile"
    assert payload_by_partner["rpa"]["trigger"] == "update_profile"
    assert payload_by_partner["engine"]["action"] == "feedback.retrain_cf"
    assert payload_by_partner["engine"]["trigger"] == "retrain_cf"


@pytest.mark.usefixtures("patch_openai")
def test_feedback_inform_handled_by_rda_rpa_engine(monkeypatch):
    # Avoid invoking real retrain subprocess in engine.
    monkeypatch.setattr(
        recommendation_engine_agent,
        "_retrain_cf",
        lambda: {
            "performative": "inform",
            "action": "engine.retrain_cf",
            "status": "success",
            "latency_ms": 1.0,
        },
    )

    rda_client = TestClient(recommendation_decision_agent.app)
    rpa_client = TestClient(reader_profile_agent.app)
    engine_client = TestClient(recommendation_engine_agent.app)

    rda_payload = {
        "performative": "inform",
        "action": "feedback.reward",
        "context_type": "low_conf_high_div",
        "arm_action": "balanced",
        "reward": 0.8,
    }
    rda_resp = rda_client.post("/recommendation-decision/rpc", json=_rpc_with_payload(rda_payload))
    assert rda_resp.status_code == 200
    rda_data = _extract_result_data(rda_resp.json())
    assert rda_data.get("action") == "reward_update_applied"
    assert rda_data.get("performative") == "inform"

    rpa_payload = {
        "performative": "inform",
        "action": "feedback.update_profile",
        "trigger": "update_profile",
        "user_id": "phase4-user-2",
    }
    rpa_resp = rpa_client.post("/reader-profile/rpc", json=_rpc_with_payload(rpa_payload))
    assert rpa_resp.status_code == 200
    rpa_data = _extract_result_data(rpa_resp.json())
    assert rpa_data.get("action") == "feedback.update_profile"
    assert rpa_data.get("update_mode") == "incremental"

    engine_payload = {
        "performative": "inform",
        "action": "feedback.retrain_cf",
        "trigger": "retrain_cf",
    }
    engine_resp = engine_client.post("/recommendation-engine/rpc", json=_rpc_with_payload(engine_payload))
    assert engine_resp.status_code == 200
    engine_data = _extract_result_data(engine_resp.json())
    assert engine_data.get("action") == "engine.retrain_cf"
    assert engine_data.get("status") == "success"
