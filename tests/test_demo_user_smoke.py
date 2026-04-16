from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from reading_concierge import reading_concierge as rc


class _DummyMessage:
    def __init__(self, content: str):
        self.content = content


class _DummyChoice:
    def __init__(self, content: str):
        self.message = _DummyMessage(content)


class _DummyCompletion:
    def __init__(self, content: str):
        self.choices = [_DummyChoice(content)]


def _install_offline_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the smoke test fully offline and fast.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    import base as base_module
    import services.model_backends as model_backends

    async def fake_create(*, messages, model, **kwargs):
        prompt = str(messages[-1].get("content") or "").lower()
        if "latent_genres" in prompt or "behavior_genres" in prompt:
            return _DummyCompletion('{"latent_genres":["fiction","history"],"confidence_adjustment_hint":"stable"}')
        if "decision" in prompt or "plan" in prompt:
            return _DummyCompletion('{"decision":"accept","plan":"offline"}')
        return _DummyCompletion('{"decision":"accept"}')

    class _FakeCompletions:
        create = staticmethod(fake_create)

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeAsyncClient:
        chat = _FakeChat()

    monkeypatch.setattr(base_module, "_get_async_openai_client", lambda: _FakeAsyncClient())
    monkeypatch.setattr(model_backends, "_resolve_sentence_transformer", lambda _model_name: None)


def _post_case(client: TestClient, *, user_id: str, query: str, scenario: str, top_k: int) -> Dict[str, Any]:
    response = client.post(
        "/user_api",
        json={
            "user_id": user_id,
            "query": query,
            "session_id": None,
            "constraints": {"scenario": scenario, "top_k": top_k},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _summarize_case(body: Dict[str, Any]) -> Dict[str, Any]:
    recommendations = body.get("recommendations") if isinstance(body.get("recommendations"), list) else []
    rpa = body.get("partner_results", {}).get("rpa", {}) if isinstance(body.get("partner_results"), dict) else {}
    engine = body.get("partner_results", {}).get("engine", {}) if isinstance(body.get("partner_results"), dict) else {}
    engine_meta = engine.get("engine_meta", {}) if isinstance(engine, dict) else {}
    top_titles = [str(row.get("title") or "") for row in recommendations[:3]]
    rank1 = recommendations[0] if recommendations else {}
    score_parts = rank1.get("score_parts") if isinstance(rank1.get("score_parts"), dict) else {}
    return {
        "top_titles": top_titles,
        "rank1_score_parts": {
            "content": float(score_parts.get("content") or 0.0),
            "cf": float(score_parts.get("cf") or 0.0),
            "novelty": float(score_parts.get("novelty") or 0.0),
            "recency": float(score_parts.get("recency") or 0.0),
        },
        "rpa_cold_start": bool(rpa.get("cold_start", False)),
        "rpa_event_count": int(rpa.get("event_count") or 0),
        "rpa_strategy": str(rpa.get("strategy_suggestion") or ""),
        "engine_meta": {
            "ann_index_path": str(engine_meta.get("modules", {}).get("recall", {}).get("ann_runtime", {}).get("index_path") or ""),
            "ann_mode": str(engine_meta.get("modules", {}).get("recall", {}).get("ann_runtime", {}).get("mode") or ""),
            "cf_item_factors_path": str(engine_meta.get("modules", {}).get("recall", {}).get("cf_runtime", {}).get("item_factors_path") or ""),
            "cf_mode": str(engine_meta.get("modules", {}).get("recall", {}).get("cf_runtime", {}).get("mode") or ""),
        },
    }


@pytest.mark.usefixtures("tmp_path")
def test_demo_user_smoke(monkeypatch: pytest.MonkeyPatch):
    _install_offline_patches(monkeypatch)

    with TestClient(rc.app) as client:
        warm_profile_1 = client.get("/api/profile", params={"user_id": "demo_user_001"})
        warm_profile_2 = client.get("/api/profile", params={"user_id": "demo_user_002"})

        assert warm_profile_1.status_code == 200, warm_profile_1.text
        assert warm_profile_2.status_code == 200, warm_profile_2.text

        warm_profile_body_1 = warm_profile_1.json()
        warm_profile_body_2 = warm_profile_2.json()
        assert warm_profile_body_1["cold_start"] is False
        assert warm_profile_body_2["cold_start"] is False
        assert warm_profile_body_1["event_count"] >= 20
        assert warm_profile_body_2["event_count"] >= 20
        assert warm_profile_body_1["strategy_suggestion"] == "exploit"
        assert warm_profile_body_2["strategy_suggestion"] == "exploit"

        cases = [
            (
                "cold_start",
                {
                    "user_id": "demo_user_004",
                    "query": "悬疑推理犯罪小说",
                    "scenario": "cold_start",
                    "top_k": 3,
                },
            ),
            (
                "warm",
                {
                    "user_id": "demo_user_001",
                    "query": "20世纪欧洲历史人物传记",
                    "scenario": "warm",
                    "top_k": 3,
                },
            ),
            (
                "explore",
                {
                    "user_id": "demo_user_002",
                    "query": "太空歌剧科幻小说",
                    "scenario": "explore",
                    "top_k": 3,
                },
            ),
        ]

        summaries: Dict[str, Dict[str, Any]] = {}
        for label, payload in cases:
            body = _post_case(client, **payload)
            summary = _summarize_case(body)
            summaries[label] = summary
            print(
                json.dumps(
                    {
                        "case": label,
                        "user_id": payload["user_id"],
                        "query": payload["query"],
                        **summary,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )

        cold = summaries["cold_start"]
        warm = summaries["warm"]
        explore = summaries["explore"]

        assert cold["rpa_cold_start"] is True
        assert cold["rank1_score_parts"]["content"] > 0.0
        assert warm["rpa_cold_start"] is False
        assert warm["rank1_score_parts"]["cf"] > 0.0
        assert explore["rpa_cold_start"] is False
        assert explore["rank1_score_parts"]["content"] > 0.0

        for summary in summaries.values():
            assert summary["engine_meta"]["ann_index_path"].endswith("books_index_v2.faiss")
            assert summary["engine_meta"]["cf_item_factors_path"].endswith("cf_item_factors_v2.npy")
            assert summary["engine_meta"]["ann_mode"] != "fallback_vector_cosine"
            assert summary["engine_meta"]["cf_mode"] != "fallback_item_factor_similarity"
