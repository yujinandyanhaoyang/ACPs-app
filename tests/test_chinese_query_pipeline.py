from __future__ import annotations

import json

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


def _fake_translation(query: str) -> tuple[str, list[str]]:
    q = query.lower()
    if "悬疑" in query or "推理" in query or "犯罪" in query:
        return "mystery crime thriller novels", ["mystery", "crime", "thriller"]
    if "历史" in query or "传记" in query:
        return "20th century european biography and history books", ["biography", "history"]
    if "太空" in query or "科幻" in query:
        return "space opera science fiction novels", ["science fiction", "space opera"]
    return "general fiction books", ["fiction"]


def _install_offline_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-openai-key")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    import base as base_module
    import partners.online.recommendation_engine_agent.modules.explanation as explanation_module

    async def fake_create(*, messages, model, **kwargs):
        prompt = str(messages[-1].get("content") or "")
        lower_prompt = prompt.lower()
        full_prompt = "\n".join(str(msg.get("content") or "") for msg in messages)
        if "search_query" in full_prompt and "original_language" in full_prompt:
            query_line = ""
            for line in full_prompt.splitlines():
                if line.startswith("User query:"):
                    query_line = line.split(":", 1)[1].strip()
                    break
            translated, genres = _fake_translation(query_line)
            payload = {
                "intent": "recommend_books",
                "constraints": {},
                "preferred_genres": genres,
                "scenario_hint": "auto",
                "response_style": "concise",
                "search_query": translated,
                "original_language": "zh",
            }
            return _DummyCompletion(json.dumps(payload, ensure_ascii=False))
        if "请补全缺失字段" in prompt or "genre_tags_zh" in prompt:
            title = ""
            author = ""
            for line in prompt.splitlines():
                if line.strip().startswith("- 书名："):
                    title = line.split("：", 1)[1].strip()
                elif line.strip().startswith("- 作者："):
                    author = line.split("：", 1)[1].split("（", 1)[0].strip()
            payload = {
                "author_display": author or "佚名",
                "genre_tags_zh": ["文学", "小说"],
                "summary_zh": "中文摘要(AI推断)",
                "title_zh": f"{title}（英文原名）" if title else "未命名图书（英文原名）",
            }
            return _DummyCompletion(json.dumps(payload, ensure_ascii=False))
        if "请用中文撰写推荐理由" in prompt or "推荐理由" in prompt:
            title = ""
            author = ""
            preferred = ""
            history = ""
            query = ""
            genre_tags = ""
            description_is_short = False
            for line in prompt.splitlines():
                stripped = line.strip()
                if stripped.startswith("- 偏好题材："):
                    preferred = stripped.split("：", 1)[1].strip()
                elif stripped.startswith("- 阅读历史："):
                    history = stripped.split("：", 1)[1].strip()
                elif stripped.startswith("- 本次需求："):
                    query = stripped.split("：", 1)[1].strip()
                elif stripped.startswith("- 书名："):
                    title = stripped.split("：", 1)[1].strip()
                elif stripped.startswith("- 作者："):
                    author = stripped.split("：", 1)[1].strip() or "佚名"
                elif stripped.startswith("- 题材标签："):
                    genre_tags = stripped.split("：", 1)[1].strip()
                elif "description_is_short=true" in lower_prompt:
                    description_is_short = True
            suffix = "（简介暂缺）" if description_is_short else ""
            text = (
                f"因为您喜欢{preferred}，而且阅读历史中已有相似兴趣，"
                f"所以《{title}》会很适合您。"
                f"它的{genre_tags}气质与本次需求“{query}”相匹配，"
                f"也能延续您对{history}的阅读方向。{suffix}"
            )
            return _DummyCompletion(text)
        if "decision" in lower_prompt or "plan" in lower_prompt:
            return _DummyCompletion('{"decision":"accept","plan":"offline"}')
        return _DummyCompletion('{"decision":"accept"}')

    class _FakeCompletions:
        create = staticmethod(fake_create)

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeAsyncClient:
        chat = _FakeChat()

    monkeypatch.setattr(base_module, "_get_async_openai_client", lambda: _FakeAsyncClient())
    monkeypatch.setattr(
        explanation_module,
        "_needs_metadata_gap_fill",
        lambda row: True,
    )


def _post_case(client: TestClient, *, user_id: str, query: str, scenario: str, top_k: int) -> dict:
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


def _extract_titles(body: dict) -> list[str]:
    recs = body.get("recommendations") if isinstance(body.get("recommendations"), list) else []
    return [str(row.get("title") or row.get("title_display") or "") for row in recs[:3]]


def _extract_rank1(body: dict) -> dict:
    recs = body.get("recommendations") if isinstance(body.get("recommendations"), list) else []
    return recs[0] if recs else {}


def _extract_engine_meta(body: dict) -> dict:
    engine = body.get("partner_results", {}).get("engine", {}) if isinstance(body.get("partner_results"), dict) else {}
    return engine.get("engine_meta", {}) if isinstance(engine, dict) else {}


@pytest.mark.usefixtures("tmp_path")
def test_chinese_query_pipeline(monkeypatch: pytest.MonkeyPatch):
    _install_offline_patches(monkeypatch)

    with TestClient(rc.app) as client:
        cases = [
            (
                "cold_start",
                {
                    "user_id": "demo_user_004",
                    "query": "悬疑推理犯罪小说",
                    "scenario": "cold_start",
                    "top_k": 3,
                },
                ("mystery", "crime", "thriller"),
            ),
            (
                "warm",
                {
                    "user_id": "demo_user_001",
                    "query": "20世纪欧洲历史人物传记",
                    "scenario": "warm",
                    "top_k": 3,
                },
                ("biography", "history"),
            ),
            (
                "explore",
                {
                    "user_id": "demo_user_002",
                    "query": "太空歌剧科幻小说",
                    "scenario": "explore",
                    "top_k": 3,
                },
                ("science fiction", "space opera"),
            ),
        ]

        reports: dict[str, dict] = {}
        for label, payload, expected_terms in cases:
            body = _post_case(client, **payload)
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            titles = _extract_titles(body)
            rank1 = _extract_rank1(body)
            explanations = body.get("explanations") if isinstance(body.get("explanations"), list) else []
            engine_meta = _extract_engine_meta(body)
            explanation_text = str(rank1.get("justification") or "")
            metadata_gap_filled = any(bool(row.get("metadata_gap_filled")) for row in body.get("recommendations", []))

            combined = " ".join(
                str(row.get("title") or "")
                + " "
                + str(row.get("description") or "")
                + " "
                + " ".join(row.get("genres") or [])
                for row in (body.get("recommendations") if isinstance(body.get("recommendations"), list) else [])
            ).lower()

            assert intent.get("original_language") == "zh"
            assert isinstance(intent.get("search_query"), str) and intent["search_query"].strip()
            for term in expected_terms:
                assert term in str(intent["search_query"]).lower()
            assert len(titles) == 3
            assert all(title.strip() for title in titles)
            assert "Unfortunately, I cannot provide" not in explanation_text
            assert "因为您喜欢" in explanation_text
            assert metadata_gap_filled is True
            recall_meta = engine_meta.get("modules", {}).get("recall", {}) if isinstance(engine_meta, dict) else {}
            assert recall_meta.get("ann_runtime", {}).get("index_path", "").endswith("books_index_v2.faiss")
            assert recall_meta.get("cf_runtime", {}).get("item_factors_path", "").endswith("cf_item_factors_v2.npy")
            assert recall_meta.get("ann_runtime", {}).get("mode") != "fallback_vector_cosine"
            assert recall_meta.get("cf_runtime", {}).get("mode") != "fallback_item_factor_similarity"

            if label == "cold_start":
                assert rank1.get("score_parts", {}).get("content", 0.0) > 0.0
            elif label == "warm":
                assert body.get("partner_results", {}).get("rpa", {}).get("cold_start") is False
                assert body.get("partner_results", {}).get("rpa", {}).get("event_count", 0) >= 20
                assert rank1.get("score_parts", {}).get("cf", 0.0) > 0.0
            else:
                assert body.get("partner_results", {}).get("rpa", {}).get("cold_start") is False
                assert rank1.get("score_parts", {}).get("content", 0.0) > 0.0

            reports[label] = {
                "intent_search_query": intent.get("search_query"),
                "intent_original_language": intent.get("original_language"),
                "titles": titles,
                "rank1_explanation": explanation_text,
                "metadata_gap_filled": metadata_gap_filled,
            }
            print(json.dumps({"case": label, **reports[label]}, ensure_ascii=False, indent=2))
