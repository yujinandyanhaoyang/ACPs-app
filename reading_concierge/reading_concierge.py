from __future__ import annotations

import json
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from base import call_openai_chat, get_agent_logger, register_acs_route
from reading_concierge.session_store import SessionStore

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

from partners.online.reader_profile_agent import agent as reader_profile
from partners.online.book_content_agent import agent as book_content
from partners.online.feedback_agent import agent as feedback_agent
from partners.online.recommendation_decision_agent import agent as recommendation_decision
from partners.online.recommendation_engine_agent import agent as recommendation_engine
from services.book_retrieval import retrieve_books_by_query

load_dotenv(_PROJECT_ROOT / ".env")

CONFIG_PATH = _CURRENT_DIR / "config.toml"
PROMPTS_PATH = _CURRENT_DIR / "prompts.toml"
ACS_PATH = (_CURRENT_DIR / "acs.json") if (_CURRENT_DIR / "acs.json").exists() else (_CURRENT_DIR / "reading_concierge.json")
DEMO_HTML_PATH = _PROJECT_ROOT / "web_demo" / "index.html"

LEADER_ID = os.getenv("READING_CONCIERGE_ID", "reading_concierge_001")
READING_CONCIERGE_BASE_URL = str(os.getenv("READING_CONCIERGE_BASE_URL", "http://localhost:8100")).rstrip("/")
PARTNER_MODE = str(os.getenv("READING_PARTNER_MODE", "auto")).lower()
LOG_LEVEL = str(os.getenv("READING_CONCIERGE_LOG_LEVEL", "INFO")).upper()
DISCOVERY_BASE_URL = str(os.getenv("DISCOVERY_BASE_URL", "http://127.0.0.1:8005")).rstrip("/")
DISCOVERY_ENABLED = str(os.getenv("READING_DISCOVERY_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"}
DISCOVERY_TIMEOUT = float(str(os.getenv("READING_DISCOVERY_TIMEOUT", "5")))
PARTNER_TIMEOUT = float(str(os.getenv("PARTNER_TIMEOUT", "60")))

logger = get_agent_logger("agent.reading_concierge", "READING_CONCIERGE_LOG_LEVEL", LOG_LEVEL)

PARTNER_SKILL_MAP = {
    "profile": "uma.build_profile",
    "content": "bca.build_content_proposal",
    "rda": "rda.arbitrate",
    "engine": "engine.dispatch",
}
_DISCOVERY_CACHE: Dict[str, Dict[str, Any]] = {}
_DISCOVERY_CACHE_TTL_SEC = 30


class RuntimeConfig(BaseModel):
    port: int = 8210
    redis_url: str = "redis://localhost:6379/0"
    llm_model: str = "gui-plus-2026-02-26"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024
    partner_aics: Dict[str, str] = Field(default_factory=dict)


def _load_runtime_config() -> RuntimeConfig:
    cfg = RuntimeConfig()
    if tomllib and CONFIG_PATH.exists():
        try:
            data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            server = data.get("server") if isinstance(data, dict) else {}
            redis_cfg = data.get("redis") if isinstance(data, dict) else {}
            llm = data.get("llm") if isinstance(data, dict) else {}
            agents = data.get("agents") if isinstance(data, dict) else {}

            if isinstance(server, dict) and server.get("port") is not None:
                cfg.port = int(server["port"])
            if isinstance(redis_cfg, dict) and redis_cfg.get("url"):
                cfg.redis_url = str(redis_cfg["url"])
            if isinstance(llm, dict):
                if llm.get("model"):
                    cfg.llm_model = str(llm["model"])
                if llm.get("temperature") is not None:
                    cfg.llm_temperature = float(llm["temperature"])
                if llm.get("max_tokens") is not None:
                    cfg.llm_max_tokens = int(llm["max_tokens"])
            if isinstance(agents, dict):
                mapping = {
                    "profile": str(agents.get("RPA_AIC") or "").strip(),
                    "content": str(agents.get("BCA_AIC") or "").strip(),
                    "rda": str(agents.get("RDA_AIC") or "").strip(),
                    "engine": str(agents.get("ENGINE_AIC") or "").strip(),
                    "feedback": str(agents.get("FEEDBACK_AIC") or "").strip(),
                }
                cfg.partner_aics = {k: v for k, v in mapping.items() if v}
        except Exception as exc:
            logger.warning("event=config_parse_failed error=%s", exc)

    return cfg


def _load_intent_prompt() -> Dict[str, str]:
    defaults = {
        "system": "Parse reading query into structured intent JSON.",
        "user_template": "User query: {query}. Return strict JSON with keys intent,constraints,preferred_genres,scenario_hint,response_style.",
    }
    if not tomllib or not PROMPTS_PATH.exists():
        return defaults
    try:
        data = tomllib.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
        section = data.get("intent_parsing") if isinstance(data, dict) else {}
        if isinstance(section, dict):
            defaults["system"] = str(section.get("system") or defaults["system"])
            defaults["user_template"] = str(section.get("user_template") or defaults["user_template"])
    except Exception as exc:
        logger.warning("event=prompts_parse_failed error=%s", exc)
    return defaults


RUNTIME = _load_runtime_config()
INTENT_PROMPT = _load_intent_prompt()
SESSION_STORE = SessionStore(RUNTIME.redis_url)

app = FastAPI(
    title="Reading Concierge",
    description="Leader coordinator for GroupMgmt broadcast, arbitration routing, and response assembly.",
)
register_acs_route(
    app,
    str(ACS_PATH),
    endpoint_override_url=f"{READING_CONCIERGE_BASE_URL}/user_api",
)


@app.on_event("startup")
async def _warmup() -> None:
    from services.book_retrieval import _load_books_by_id
    from services.model_backends import warmup_embedding_model
    from partners.online.recommendation_engine_agent.modules.recall import _load_book_metadata

    loop = asyncio.get_event_loop()
    _books_cache, _meta_cache, embed_model = await asyncio.gather(
        loop.run_in_executor(None, _load_books_by_id),
        loop.run_in_executor(None, _load_book_metadata),
        loop.run_in_executor(None, warmup_embedding_model, None),
    )
    logger.info(
        "event=embedding_model_warm model=%s",
        embed_model or os.getenv("BOOK_CONTENT_EMBED_MODEL_PATH") or "",
    )
    logger.info(
        "event=startup_complete leader_id=%s port=%s books_cached=%s",
        LEADER_ID,
        RUNTIME.port,
        len(_load_books_by_id()),
    )


class UserRequest(BaseModel):
    session_id: Optional[str] = None
    user_id: str = ""
    query: str = ""
    user_profile: Dict[str, Any] = Field(default_factory=dict, deprecated=True)
    history: List[Dict[str, Any]] = Field(default_factory=list, deprecated=True)
    reviews: List[Dict[str, Any]] = Field(default_factory=list, deprecated=True)
    books: List[Dict[str, Any]] = Field(default_factory=list, deprecated=True)
    candidate_ids: List[str] = Field(default_factory=list, deprecated=True)
    constraints: Dict[str, Any] = Field(default_factory=dict)


class ProfileResponse(BaseModel):
    user_id: str
    confidence: float
    cold_start: bool
    event_count: int
    behavior_genres: List[str] = Field(default_factory=list)
    strategy_suggestion: str
    profile_vector_dim: int
    model: Dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    user_id: str = ""
    session_id: str = ""
    book_id: str = ""
    event_type: str = ""
    context_type: Optional[str] = None
    arm_action: Optional[str] = None
    reward_override: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _detect_language_code(text: str) -> str:
    sample = str(text or "")
    if any("\u4e00" <= ch <= "\u9fff" for ch in sample):
        return "zh"
    return "en"


def _resolve_partner(partner_key: str) -> Dict[str, Any]:
    remote_env = {
        "profile": "READER_PROFILE_RPC_URL",
        "content": "BOOK_CONTENT_RPC_URL",
        "rda": "RECOMMENDATION_DECISION_RPC_URL",
        "engine": "RECOMMENDATION_ENGINE_RPC_URL",
        "feedback": "FEEDBACK_AGENT_RPC_URL",
    }
    local_map = {
        "profile": {
            "agent_id": reader_profile.AGENT_ID,
            "app": reader_profile.app,
            "endpoint": "/reader-profile/rpc",
        },
        "content": {
            "agent_id": book_content.AGENT_ID,
            "app": book_content.app,
            "endpoint": "/book-content/rpc",
        },
        "rda": {
            "agent_id": recommendation_decision.AGENT_ID,
            "app": recommendation_decision.app,
            "endpoint": "/recommendation-decision/rpc",
        },
        "engine": {
            "agent_id": recommendation_engine.AGENT_ID,
            "app": recommendation_engine.app,
            "endpoint": "/recommendation-engine/rpc",
        },
        "feedback": {
            "agent_id": feedback_agent.AGENT_ID,
            "app": feedback_agent.app,
            "endpoint": "/feedback/rpc",
        },
    }
    item = dict(local_map[partner_key])
    discovered_remote = _discover_partner_rpc_url(partner_key) if DISCOVERY_ENABLED else None
    env_remote = str(os.getenv(remote_env[partner_key]) or "").strip() or None
    item["remote_url"] = discovered_remote or env_remote
    item["discovery"] = "adp" if discovered_remote else ("env" if env_remote else "local")
    return item


def _search_discovery(query: str) -> List[Dict[str, Any]]:
    if not DISCOVERY_ENABLED:
        return []
    cache_key = f"q:{query}"
    now = time.time()
    cached = _DISCOVERY_CACHE.get(cache_key)
    if cached and (now - float(cached.get("ts", 0))) < _DISCOVERY_CACHE_TTL_SEC:
        return list(cached.get("results") or [])

    try:
        payload = {"query": query, "top_k": 20}
        paths = ["/api/discovery/search", "/acps-adp-v2/discover", "/acps-adp-v2/discover/v1"]
        data = None
        with httpx.Client(timeout=DISCOVERY_TIMEOUT, trust_env=False) as client:
            for path in paths:
                try:
                    resp = client.post(f"{DISCOVERY_BASE_URL}{path}", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except Exception:
                    continue
        if isinstance(data, dict):
            results = data.get("results")
            if not isinstance(results, list):
                results = data.get("data")
            if not isinstance(results, list):
                result = data.get("result")
                if isinstance(result, dict):
                    results = result.get("results")
                    if not isinstance(results, list):
                        acs_map = result.get("acsMap")
                        if isinstance(acs_map, dict):
                            results = list(acs_map.values())
            if isinstance(results, list):
                _DISCOVERY_CACHE[cache_key] = {"ts": now, "results": results}
                return results
    except Exception as exc:
        logger.warning("event=adp_search_failed query=%s error=%s", query, exc)
    return []


def _item_skill_ids(item: Dict[str, Any]) -> List[str]:
    raw_skills = item.get("skills")
    if not isinstance(raw_skills, list):
        card = item.get("agent_card")
        if isinstance(card, dict):
            raw_skills = card.get("skills")
    if not isinstance(raw_skills, list):
        return []
    ids: List[str] = []
    for sk in raw_skills:
        if isinstance(sk, dict):
            sid = sk.get("id")
            if sid:
                ids.append(str(sid))
        elif isinstance(sk, str):
            ids.append(sk)
    return ids


def _item_endpoints(item: Dict[str, Any]) -> List[str]:
    endpoints = item.get("endPoints")
    if not isinstance(endpoints, list):
        card = item.get("agent_card")
        if isinstance(card, dict):
            endpoints = card.get("endPoints")
    urls: List[str] = []
    if not isinstance(endpoints, list):
        return urls
    for ep in endpoints:
        if isinstance(ep, dict) and ep.get("url"):
            urls.append(str(ep["url"]))
    return urls


def _item_aic(item: Dict[str, Any]) -> str:
    aic = item.get("aic")
    if aic:
        return str(aic)
    card = item.get("agent_card")
    if isinstance(card, dict) and card.get("aic"):
        return str(card.get("aic"))
    return ""


def _discover_partner_rpc_url(partner_key: str) -> Optional[str]:
    skill_id = PARTNER_SKILL_MAP.get(partner_key)
    if not skill_id:
        return None
    expected_aic = str((RUNTIME.partner_aics or {}).get(partner_key) or "").strip()
    for item in _search_discovery(skill_id):
        if not isinstance(item, dict):
            continue
        if expected_aic and _item_aic(item) != expected_aic:
            continue
        skills = _item_skill_ids(item)
        if skill_id not in skills:
            continue
        urls = _item_endpoints(item)
        if urls:
            return urls[0]
    if expected_aic:
        logger.warning("event=partner_discovery_miss partner=%s expected_aic=%s", partner_key, expected_aic)
    return None


def _mk_rpc_payload(task_id: str, payload: Dict[str, Any], command: str = "start") -> Dict[str, Any]:
    message = {
        "type": "message",
        "id": str(uuid.uuid4()),
        "sentAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "senderRole": "leader",
        "senderId": LEADER_ID,
        "command": command,
        "dataItems": [{"type": "text", "text": ""}],
        "taskId": task_id,
        "sessionId": "reading-session",
        "commandParams": {"payload": payload},
    }
    return {
        "jsonrpc": "2.0",
        "method": "rpc",
        "id": str(uuid.uuid4()),
        "params": {"message": message},
    }


async def _invoke_local(app_obj: FastAPI, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    rpc = _mk_rpc_payload(f"task-{uuid.uuid4()}", payload)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_obj),
        base_url="http://agent",
        timeout=PARTNER_TIMEOUT,
        trust_env=False,
    ) as client:
        resp = await client.post(endpoint, json=rpc)
    resp.raise_for_status()
    return resp.json()


async def _invoke_remote(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    rpc = _mk_rpc_payload(f"task-{uuid.uuid4()}", payload)
    async with httpx.AsyncClient(timeout=PARTNER_TIMEOUT, trust_env=False) as client:
        resp = await client.post(url, json=rpc)
    resp.raise_for_status()
    return resp.json()


def _extract_result(rpc_resp: Dict[str, Any]) -> Dict[str, Any]:
    products = ((rpc_resp or {}).get("result") or {}).get("products") or []
    if not products:
        return {}
    items = products[0].get("dataItems") or []
    for item in items:
        if item.get("type") == "data" and isinstance(item.get("data"), dict):
            return item["data"]
    return {}


def _state(rpc_resp: Dict[str, Any]) -> str:
    return str((((rpc_resp or {}).get("result") or {}).get("status") or {}).get("state") or "unknown")


async def _invoke_partner(partner_key: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    partner = _resolve_partner(partner_key)
    remote_url = partner.get("remote_url")
    if remote_url and PARTNER_MODE in {"auto", "remote"}:
        try:
            resp = await _invoke_remote(str(remote_url), payload)
            return resp, {"route": "remote", "rpc_url": remote_url, "remote_source": partner.get("discovery")}
        except Exception as exc:
            logger.warning("event=partner_remote_failed partner=%s error=%s", partner_key, exc)
            if PARTNER_MODE == "remote":
                return {"jsonrpc": "2.0", "result": {"status": {"state": "failed"}, "products": []}}, {"route": "remote_failed"}

    if partner.get("app") is None or not partner.get("endpoint"):
        return {"jsonrpc": "2.0", "result": {"status": {"state": "failed"}, "products": []}}, {"route": "local_unavailable"}

    resp = await _invoke_local(partner["app"], partner["endpoint"], payload)
    return resp, {"route": "local"}


def _safe_json_object(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    left = text.find("{")
    right = text.rfind("}")
    if left >= 0 and right > left:
        try:
            obj = json.loads(text[left : right + 1])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


async def _parse_intent(query: str) -> Dict[str, Any]:
    query = str(query or "").strip()
    if not query:
        raise RuntimeError("_parse_intent called with empty query")
    if not str(os.getenv("OPENAI_API_KEY") or "").strip():
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. "
            "Intent parsing requires LLM. Please check your environment configuration."
        )
    raw = await asyncio.wait_for(
        call_openai_chat(
            [
                {"role": "system", "content": INTENT_PROMPT["system"]},
                {"role": "user", "content": INTENT_PROMPT["user_template"].format(query=query)},
            ],
            model=RUNTIME.llm_model,
            temperature=RUNTIME.llm_temperature,
            max_tokens=RUNTIME.llm_max_tokens,
            timeout_s=60.0,
        ),
        timeout=60.0,
    )
    parsed = _safe_json_object(raw)
    if not parsed:
        raise RuntimeError(
            f"LLM returned invalid or empty JSON for intent parsing. raw_response={raw!r}"
        )

    if not str(parsed.get("search_query") or "").strip():
        raise RuntimeError(
            f"LLM intent parsing returned empty search_query. parsed={parsed!r}"
        )

    sq = str(parsed.get("search_query") or "")
    if any("\u4e00" <= ch <= "\u9fff" for ch in sq):
        raise RuntimeError(
            f"LLM failed to translate query to English. search_query still contains Chinese: {sq!r}"
        )

    if not str(parsed.get("original_language") or "").strip():
        parsed["original_language"] = _detect_language_code(query)
    return parsed


def _normalize_book_row(row: Dict[str, Any], index: int) -> Dict[str, Any]:
    book_id = str(row.get("book_id") or row.get("id") or row.get("asin") or row.get("title") or f"book_{index}").strip()
    title = str(row.get("title") or row.get("name") or book_id)
    author = str(row.get("author") or row.get("authors") or "unknown")
    description = str(row.get("description") or row.get("desc") or "")
    genres = row.get("genres") if isinstance(row.get("genres"), list) else []
    return {
        "book_id": book_id,
        "title": title,
        "author": author,
        "description": description,
        "genres": [str(g).strip().lower() for g in genres if str(g).strip()],
    }


def _load_reading_history_titles(user_id: str, limit: int = 10) -> List[str]:
    uid = str(user_id or "").strip()
    if not uid:
        return []

    recent_book_ids: List[str] = []
    try:
        import sqlite3

        db_path = _PROJECT_ROOT / "data" / "recommendation_runtime.db"
        if db_path.exists():
            with sqlite3.connect(str(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT book_id, rating, created_at
                    FROM user_behavior_events
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (uid, max(1, int(limit))),
                ).fetchall()
            for row in rows:
                try:
                    rating = float(row["rating"]) if row["rating"] is not None else 0.0
                except Exception:
                    rating = 0.0
                if rating >= 4.0:
                    book_id = str(row["book_id"] or "").strip()
                    if book_id:
                        recent_book_ids.append(book_id)
    except Exception:
        return []

    if not recent_book_ids:
        return []

    try:
        from services.book_retrieval import _load_books_by_id

        by_id = _load_books_by_id()
    except Exception:
        by_id = {}

    titles: List[str] = []
    seen: set[str] = set()
    for book_id in recent_book_ids:
        if book_id in seen:
            continue
        seen.add(book_id)
        row = by_id.get(book_id) or {}
        title = str(row.get("title") or book_id).strip()
        if title:
            titles.append(title)
    return titles[: max(1, int(limit))]


@lru_cache(maxsize=1)
def _catalog_index() -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """
    Lightweight stub: delegates to the shared FAISS meta cache.
    Does NOT load the 1.4 GB books_master_merged.jsonl.
    """
    from services.book_retrieval import _load_books_by_id

    by_id = _load_books_by_id()
    normalized = list(by_id.values())
    return normalized, by_id


async def _derive_books_from_query(
    query: str,
    candidate_ids: List[str],
    top_k: int = 5,
    *,
    search_query: str | None = None,
) -> List[Dict[str, Any]]:
    retrieval_size = max(20, min(120, max(1, int(top_k)) * 20))
    seen: set[str] = set()
    results: List[Dict[str, Any]] = []

    # Resolve any explicitly requested candidate_ids first (deprecated path).
    if candidate_ids:
        from services.book_retrieval import _load_books_by_id

        by_id = _load_books_by_id()
        for cid in candidate_ids:
            key = str(cid or "").strip()
            if not key or key in seen:
                continue
            row = by_id.get(key) or {
                "book_id": key,
                "title": key,
                "author": "unknown",
                "description": "",
                "genres": [],
            }
            results.append(dict(row))
            seen.add(key)

    # Primary path: FAISS vector recall (books=None triggers the fast path).
    effective_query = str(search_query or query or "").strip()
    for row in retrieve_books_by_query(query=query, search_query=search_query, books=None, top_k=retrieval_size):
        normalized = _normalize_book_row(
            row if isinstance(row, dict) else {}, len(results)
        )
        key = normalized["book_id"]
        if not key or key in seen:
            continue
        results.append(normalized)
        seen.add(key)

    return results[:max(20, retrieval_size)]


def _normalize_recommendations_for_frontend(
    recommendations: List[Dict[str, Any]],
    explanations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    explain_by_id: Dict[str, Dict[str, Any]] = {}
    for row in explanations:
        if isinstance(row, dict) and row.get("book_id"):
            explain_by_id[str(row.get("book_id"))] = row

    normalized: List[Dict[str, Any]] = []
    for idx, row in enumerate(recommendations):
        if not isinstance(row, dict):
            continue
        book_id = str(row.get("book_id") or f"book_{idx + 1}")
        explanation = explain_by_id.get(book_id, {})
        item = dict(row)
        item["rank"] = int(row.get("rank") or (idx + 1))
        item["book_id"] = book_id
        item["score_total"] = float(row.get("score_total") or row.get("composite_score") or 0.0)
        item["novelty_score"] = float(row.get("novelty_score") or 0.0)
        item["diversity_score"] = float(row.get("diversity_score") or 0.0)
        item["score_parts"] = row.get("score_parts") if isinstance(row.get("score_parts"), dict) else {}
        item["justification"] = str(row.get("justification") or explanation.get("justification") or "")
        normalized.append(item)
    return normalized


async def _orchestrate_inner(req: UserRequest, allow_deprecated_payload: bool = False) -> Dict[str, Any]:
    session_id = req.session_id or f"session-{uuid.uuid4()}"
    SESSION_STORE.append_message(session_id, "user", req.query)
    req_payload = req.model_dump()

    intent = await _parse_intent(req.query)
    search_query = str(intent.get("search_query") or req.query or "").strip()

    constraints = req.constraints if isinstance(req.constraints, dict) else {}
    ablation_flags = constraints.get("ablation_flags") if isinstance(constraints.get("ablation_flags"), dict) else {}
    scoring_weights = constraints.get("scoring_weights") if isinstance(constraints.get("scoring_weights"), dict) else {}
    requested_top_k = int(constraints.get("top_k") or 5)
    top_k = max(1, min(requested_top_k, 5))

    # 1) Notify RDA to stand by.
    rda_standby_payload = {
        "performative": "request",
        "action": "rda.standby",
        "session_id": session_id,
        "user_id": req.user_id,
    }
    standby_resp, standby_route = await _invoke_partner("rda", rda_standby_payload)

    # 2) GroupMgmt broadcast to RPA + BCA in parallel.
    profile_payload = {
        "performative": "request",
        "action": "uma.build_profile",
        "user_id": req.user_id,
        "query": req.query,
        "user_profile": req_payload.get("user_profile") if isinstance(req_payload.get("user_profile"), dict) else {},
        "history": req_payload.get("history") if isinstance(req_payload.get("history"), list) else [],
        "reviews": req_payload.get("reviews") if isinstance(req_payload.get("reviews"), list) else [],
    }
    req_books = req_payload.get("books") if isinstance(req_payload.get("books"), list) else []
    req_candidate_ids = req_payload.get("candidate_ids") if isinstance(req_payload.get("candidate_ids"), list) else []
    content_payload = {
        "performative": "request",
        "action": "bca.build_content_proposal",
        "user_id": req.user_id,
        "query": req.query,
        "books": req_books if allow_deprecated_payload and req_books else await _derive_books_from_query(
            query=req.query,
            candidate_ids=req_candidate_ids if allow_deprecated_payload else [],
            top_k=top_k,
            search_query=search_query,
        ),
        "candidate_ids": req_candidate_ids if allow_deprecated_payload else [],
        "declared_genres": intent.get("preferred_genres") or [],
    }
    if ablation_flags.get("disable_alignment"):
        # Alignment ablation: neutralize declared preference signals to BCA.
        content_payload["declared_genres"] = []

    (profile_resp, profile_route), (content_resp, content_route) = await asyncio.gather(
        _invoke_partner("profile", profile_payload),
        _invoke_partner("content", content_payload),
    )

    profile_data = _extract_result(profile_resp)
    content_data = _extract_result(content_resp)
    profile_state = _state(profile_resp)
    content_state = _state(content_resp)

    # 3) Forward proposals to RDA arbitration.
    content_outputs = content_data.get("outputs") if isinstance(content_data.get("outputs"), dict) else {}
    reading_history = _load_reading_history_titles(req.user_id, limit=10)
    rda_payload = {
        "performative": "request",
        "action": "rda.arbitrate",
        "session_id": session_id,
        "profile_proposal": {
            "performative": "propose",
            "profile_vector": profile_data.get("profile_vector") or profile_data.get("preference_vector") or [],
            "confidence": profile_data.get("confidence", 0.2),
            "behavior_genres": profile_data.get("behavior_genres") or [],
            "strategy_suggestion": profile_data.get("strategy_suggestion") or "balanced",
        },
        "content_proposal": {
            "performative": "propose",
            "divergence_score": content_outputs.get("divergence_score", content_data.get("divergence_score", 0.5)),
            "alignment_status": content_outputs.get("alignment_status", content_data.get("alignment_status")),
            "weight_suggestion": content_outputs.get("weight_suggestion"),
            "coverage_report": content_outputs.get("coverage_report"),
            "counter_proposal": content_outputs.get("counter_proposal"),
            "counter_proposal_performative": "reject-proposal" if content_outputs.get("counter_proposal") else None,
        },
        "counter_proposal_received": bool(content_outputs.get("counter_proposal")),
    }
    rda_resp, rda_route = await _invoke_partner("rda", rda_payload)
    rda_data = _extract_result(rda_resp)
    rda_state = _state(rda_resp)

    if ablation_flags.get("fixed_arbitration_weights") or ablation_flags.get("freeze_feedback"):
        # Ablation mode: bypass learned/adaptive arbitration output with fixed weights.
        cf_weight = float(scoring_weights.get("collaborative", 0.25) or 0.25)
        ann_weight = max(0.0, 1.0 - cf_weight)
        rda_data = {
            **rda_data,
            "final_weights": {"ann_weight": ann_weight, "cf_weight": cf_weight},
            "score_weights": {
                "content": float(scoring_weights.get("semantic", 0.35) or 0.35),
                "cf": cf_weight,
                "novelty": float(scoring_weights.get("diversity", 0.2) or 0.2),
                "recency": float(scoring_weights.get("knowledge", 0.2) or 0.2),
            },
            "mmr_lambda": rda_data.get("mmr_lambda", 0.5),
            "strategy": "fixed" if ablation_flags.get("fixed_arbitration_weights") else "frozen_feedback",
            "ablation_override": True,
        }

    # 4) Compose dispatch and send to Engine.
    engine_payload = {
        "performative": "request",
        "action": "engine.dispatch",
        "session_id": session_id,
        "user_id": req.user_id,
        "query": req.query,
        "search_query": search_query,
        "reading_history": reading_history,
        "history": reading_history,
        "user_profile": {"reading_history": reading_history},
        "intent": intent,
        "profile_vector": (rda_payload.get("profile_proposal") or {}).get("profile_vector") or [],
        "ann_weight": rda_data.get("final_weights", {}).get("ann_weight", 0.6),
        "cf_weight": rda_data.get("final_weights", {}).get("cf_weight", 0.4),
        "score_weights": rda_data.get("score_weights") or {},
        "mmr_lambda": rda_data.get("mmr_lambda", 0.5),
        "strategy": rda_data.get("strategy", "balanced"),
        "candidates": content_outputs.get("content_vectors") or [],
        "cold_start": bool(profile_data.get("cold_start", False)),
        "top_k": top_k,
        "reading_history": reading_history,
        "embed_backend": (content_data.get("embedding_backend") or {}).get("backend") if isinstance(content_data.get("embedding_backend"), dict) else "",
        "vector_dim": int((content_data.get("embedding_backend") or {}).get("vector_dim") or 0) if isinstance(content_data.get("embedding_backend"), dict) else 0,
    }
    if ablation_flags.get("disable_cf_path"):
        engine_payload["cf_weight"] = 0.0
        engine_payload["ann_weight"] = 1.0
        sw = engine_payload.get("score_weights") if isinstance(engine_payload.get("score_weights"), dict) else {}
        sw = {**sw, "cf": 0.0}
        engine_payload["score_weights"] = sw
    if ablation_flags.get("disable_mmr"):
        engine_payload["mmr_lambda"] = 1.0
    if ablation_flags.get("disable_explain_constraint"):
        engine_payload["required_evidence_types"] = []
        engine_payload["min_coverage"] = 0.0
    if ablation_flags:
        engine_payload["ablation_flags"] = ablation_flags
    engine_resp, engine_route = await _invoke_partner("engine", engine_payload)
    engine_data = _extract_result(engine_resp)
    engine_state = _state(engine_resp)

    recommendations = engine_data.get("recommendations") if isinstance(engine_data.get("recommendations"), list) else []
    explanations = engine_data.get("explanations") if isinstance(engine_data.get("explanations"), list) else []
    normalized_recommendations = _normalize_recommendations_for_frontend(recommendations, explanations)

    response = {
        "session_id": session_id,
        "user_id": req.user_id,
        "leader_id": LEADER_ID,
        "intent": intent,
        "state": "completed" if normalized_recommendations else "needs_input",
        "partner_tasks": {
            "rda_standby": {"state": _state(standby_resp), **standby_route},
            "rpa": {"state": profile_state, **profile_route},
            "bca": {"state": content_state, **content_route},
            "rda": {"state": rda_state, **rda_route},
            "engine": {"state": engine_state, **engine_route},
        },
        "partner_results": {
            "rpa": profile_data,
            "bca": content_data,
            "rda": rda_data,
            "engine": engine_data,
        },
        "ablation_flags": ablation_flags,
        "recommendations": normalized_recommendations,
        "explanations": explanations,
    }

    SESSION_STORE.update_fields(session_id, {"last_response": response, "intent": intent})
    SESSION_STORE.append_message(session_id, "assistant", "orchestration_completed")
    return response


async def _orchestrate(req: UserRequest, allow_deprecated_payload: bool = False) -> Dict[str, Any]:
    try:
        return await asyncio.wait_for(
            _orchestrate_inner(req, allow_deprecated_payload),
            timeout=150.0,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="推荐请求超时（后端处理超过 150 秒）。请稍后重试或减少 Top K 数量。",
        ) from exc


@app.get("/", response_class=HTMLResponse)
async def demo_root() -> HTMLResponse:
    if DEMO_HTML_PATH.exists():
        return HTMLResponse(DEMO_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h3>Demo page not found.</h3>", status_code=404)


@app.get("/demo", response_class=HTMLResponse)
async def demo_page() -> HTMLResponse:
    return await demo_root()


@app.get("/demo/status")
async def demo_status() -> Dict[str, Any]:
    return {
        "service": "reading_concierge",
        "leader_id": LEADER_ID,
        "partner_mode": PARTNER_MODE,
        "redis_url": RUNTIME.redis_url,
        "llm_model": RUNTIME.llm_model,
        "llm_max_tokens": RUNTIME.llm_max_tokens,
        "embed_backend": str(os.getenv("EMBED_BACKEND") or "not_set"),
        "embed_model_path": str(os.getenv("BOOK_CONTENT_EMBED_MODEL_PATH") or "not_set"),
        "demo_page_available": DEMO_HTML_PATH.exists(),
        "openai_api_key_set": bool(str(os.getenv("OPENAI_API_KEY") or "").strip()),
        "openai_base_url": str(os.getenv("OPENAI_BASE_URL") or "not_set"),
    }


@app.post("/user_api")
async def user_api(req: UserRequest):
    if not str(req.user_id or "").strip():
        raise HTTPException(status_code=422, detail="user_id is required for /user_api")
    if not str(req.query or "").strip():
        raise HTTPException(status_code=400, detail="query must not be empty or blank")
    return await _orchestrate(req, allow_deprecated_payload=False)


@app.post("/user_api_debug")
async def user_api_debug(req: UserRequest):
    if not str(req.query or "").strip():
        raise HTTPException(status_code=400, detail="query must not be empty or blank")
    if not str(req.user_id or "").strip():
        req.user_id = f"anon-{uuid.uuid4()}"
    return await _orchestrate(req, allow_deprecated_payload=True)


@app.get("/api/profile", response_model=ProfileResponse)
async def api_profile(user_id: str = ""):
    uid = str(user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id is required")

    payload = {
        "performative": "request",
        "action": "uma.build_profile",
        "user_id": uid,
    }
    profile_resp, _ = await _invoke_partner("profile", payload)
    if _state(profile_resp) in {"failed", "rejected", "canceled"}:
        raise HTTPException(status_code=503, detail="profile agent unavailable")

    profile_data = _extract_result(profile_resp)
    if not profile_data:
        raise HTTPException(status_code=404, detail="profile not found")

    model_info = profile_data.get("model") if isinstance(profile_data.get("model"), dict) else {}
    profile_vector = profile_data.get("profile_vector") if isinstance(profile_data.get("profile_vector"), list) else []
    lambda_decay = model_info.get("lambda_decay")
    if lambda_decay is None:
        lambda_decay = model_info.get("lambda")
    vector_dim = int(model_info.get("vector_dim") or len(profile_vector) or 0)

    return {
        "user_id": uid,
        "confidence": float(profile_data.get("confidence") or 0.0),
        "cold_start": bool(profile_data.get("cold_start", False)),
        "event_count": int(profile_data.get("event_count") or 0),
        "behavior_genres": profile_data.get("behavior_genres") if isinstance(profile_data.get("behavior_genres"), list) else [],
        "strategy_suggestion": str(profile_data.get("strategy_suggestion") or "balanced"),
        "profile_vector_dim": vector_dim,
        "model": {
            "lambda_decay": float(lambda_decay or 0.0),
            "vector_dim": vector_dim,
            "warm_threshold": int(model_info.get("warm_threshold") or 0),
        },
    }


async def _post_feedback_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    webhook_url = str(os.getenv("FEEDBACK_AGENT_WEBHOOK_URL") or "").strip()
    if webhook_url:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=feedback_agent.app),
        base_url="http://agent",
        timeout=20,
        trust_env=False,
    ) as client:
        resp = await client.post("/feedback/webhook", json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


@app.post("/api/feedback")
async def api_feedback(req: FeedbackRequest):
    user_id = str(req.user_id or "").strip()
    session_id = str(req.session_id or "").strip()
    book_id = str(req.book_id or "").strip()
    event_type = str(req.event_type or "").strip().lower()

    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    if not book_id:
        raise HTTPException(status_code=400, detail="book_id is required")
    if not event_type:
        raise HTTPException(status_code=400, detail="event_type is required")

    metadata = dict(req.metadata or {})
    if "book_id" not in metadata:
        metadata["book_id"] = book_id

    payload = {
        "user_id": user_id,
        "event_type": event_type,
        "session_id": session_id,
        "context_type": req.context_type,
        "action": req.arm_action,
        "reward_override": req.reward_override,
        "metadata": metadata,
    }
    try:
        feedback_result = await _post_feedback_webhook(payload)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"feedback agent unavailable: {exc}")

    triggers = feedback_result.get("triggers") if isinstance(feedback_result.get("triggers"), dict) else {}
    event = feedback_result.get("event") if isinstance(feedback_result.get("event"), dict) else {}
    counters = feedback_result.get("counters") if isinstance(feedback_result.get("counters"), dict) else {}
    return {
        "status": str(feedback_result.get("status") or "accepted"),
        "event_id": str(event.get("event_id") or ""),
        "counters": {
            "user_event_count": int(counters.get("user_event_count") or 0),
            "global_rating_count": int(counters.get("global_rating_count") or 0),
        },
        "triggers": {
            "profile_updated": bool(triggers.get("profile_updated", False)),
            "cf_retrain_triggered": bool(triggers.get("cf_retrain_triggered", False)),
            "rda_reward_updated": bool(triggers.get("rda_reward_updated", False)),
        },
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("READING_CONCIERGE_HOST", "0.0.0.0")
    port = int(os.getenv("READING_CONCIERGE_PORT", str(RUNTIME.port)))
    uvicorn.run("reading_concierge.reading_concierge:app", host=host, port=port)
