from __future__ import annotations

import json
import os
import sys
import uuid
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

from agents.reader_profile_agent import profile_agent as reader_profile
from agents.book_content_agent import book_content_agent as book_content
from partners.online.recommendation_decision_agent import agent as recommendation_decision
from partners.online.recommendation_engine_agent import agent as recommendation_engine

load_dotenv()

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
    llm_model: str = "qwen-flash-character"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 512


def _load_runtime_config() -> RuntimeConfig:
    cfg = RuntimeConfig()
    if tomllib and CONFIG_PATH.exists():
        try:
            data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            server = data.get("server") if isinstance(data, dict) else {}
            redis_cfg = data.get("redis") if isinstance(data, dict) else {}
            llm = data.get("llm") if isinstance(data, dict) else {}

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
        except Exception as exc:
            logger.warning("event=config_parse_failed error=%s", exc)

    cfg.llm_model = str(os.getenv("READING_LLM_MODEL") or os.getenv("OPENAI_MODEL") or cfg.llm_model)
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


class UserRequest(BaseModel):
    session_id: Optional[str] = None
    user_id: str = ""
    query: str = ""
    user_profile: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    reviews: List[Dict[str, Any]] = Field(default_factory=list)
    books: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_ids: List[str] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)


def _resolve_partner(partner_key: str) -> Dict[str, Any]:
    remote_env = {
        "profile": "READER_PROFILE_RPC_URL",
        "content": "BOOK_CONTENT_RPC_URL",
        "rda": "RECOMMENDATION_DECISION_RPC_URL",
        "engine": "RECOMMENDATION_ENGINE_RPC_URL",
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
    }
    item = dict(local_map[partner_key])
    discovered_remote = _discover_partner_rpc_url(partner_key)
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
        with httpx.Client(timeout=DISCOVERY_TIMEOUT) as client:
            resp = client.post(f"{DISCOVERY_BASE_URL}/api/discovery/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict):
            results = data.get("results")
            if not isinstance(results, list):
                results = data.get("data")
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


def _discover_partner_rpc_url(partner_key: str) -> Optional[str]:
    skill_id = PARTNER_SKILL_MAP.get(partner_key)
    if not skill_id:
        return None
    for item in _search_discovery(skill_id):
        if not isinstance(item, dict):
            continue
        skills = _item_skill_ids(item)
        if skill_id not in skills:
            continue
        urls = _item_endpoints(item)
        if urls:
            return urls[0]
    return None


def _mk_rpc_payload(task_id: str, payload: Dict[str, Any], command: str = "start") -> Dict[str, Any]:
    message = {
        "type": "message",
        "id": str(uuid.uuid4()),
        "sentAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
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
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_obj), base_url="http://agent", timeout=30) as client:
        resp = await client.post(endpoint, json=rpc)
    resp.raise_for_status()
    return resp.json()


async def _invoke_remote(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    rpc = _mk_rpc_payload(f"task-{uuid.uuid4()}", payload)
    async with httpx.AsyncClient(timeout=30) as client:
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
    template = INTENT_PROMPT["user_template"]
    user_prompt = template.format(query=query)
    if not str(os.getenv("OPENAI_API_KEY") or "").strip():
        return {"intent": "recommend_books", "constraints": {}, "preferred_genres": [], "scenario_hint": "auto", "response_style": "concise"}

    try:
        raw = await call_openai_chat(
            [
                {"role": "system", "content": INTENT_PROMPT["system"]},
                {"role": "user", "content": user_prompt},
            ],
            model=RUNTIME.llm_model,
            temperature=RUNTIME.llm_temperature,
            max_tokens=RUNTIME.llm_max_tokens,
        )
        parsed = _safe_json_object(raw)
        if parsed:
            return parsed
    except Exception as exc:
        logger.warning("event=intent_parse_failed error=%s", exc)

    return {"intent": "recommend_books", "constraints": {}, "preferred_genres": [], "scenario_hint": "auto", "response_style": "concise"}


async def _orchestrate(req: UserRequest) -> Dict[str, Any]:
    session_id = req.session_id or f"session-{uuid.uuid4()}"
    SESSION_STORE.append_message(session_id, "user", req.query)

    intent = await _parse_intent(req.query)

    # 1) Notify RDA to stand by.
    rda_standby_payload = {
        "action": "rda.standby",
        "session_id": session_id,
        "user_id": req.user_id,
    }
    standby_resp, standby_route = await _invoke_partner("rda", rda_standby_payload)

    # 2) GroupMgmt broadcast to RPA + BCA in parallel.
    profile_payload = {
        "action": "uma.build_profile",
        "user_id": req.user_id,
        "query": req.query,
        "user_profile": req.user_profile,
        "history": req.history,
        "reviews": req.reviews,
    }
    content_payload = {
        "action": "bca.build_content_proposal",
        "user_id": req.user_id,
        "query": req.query,
        "books": req.books,
        "candidate_ids": req.candidate_ids,
        "declared_genres": intent.get("preferred_genres") or [],
    }

    (profile_resp, profile_route), (content_resp, content_route) = await __import__("asyncio").gather(
        _invoke_partner("profile", profile_payload),
        _invoke_partner("content", content_payload),
    )

    profile_data = _extract_result(profile_resp)
    content_data = _extract_result(content_resp)
    profile_state = _state(profile_resp)
    content_state = _state(content_resp)

    # 3) Forward proposals to RDA arbitration.
    content_outputs = content_data.get("outputs") if isinstance(content_data.get("outputs"), dict) else {}
    rda_payload = {
        "action": "rda.arbitrate",
        "session_id": session_id,
        "profile_proposal": {
            "profile_vector": profile_data.get("profile_vector") or profile_data.get("preference_vector") or [],
            "confidence": profile_data.get("confidence", 0.2),
            "behavior_genres": profile_data.get("behavior_genres") or [],
            "strategy_suggestion": profile_data.get("strategy_suggestion") or "balanced",
        },
        "content_proposal": {
            "divergence_score": content_outputs.get("divergence_score", content_data.get("divergence_score", 0.5)),
            "alignment_status": content_outputs.get("alignment_status", content_data.get("alignment_status")),
            "weight_suggestion": content_outputs.get("weight_suggestion"),
            "coverage_report": content_outputs.get("coverage_report"),
            "counter_proposal": content_outputs.get("counter_proposal"),
        },
        "counter_proposal_received": bool(content_outputs.get("counter_proposal")),
    }
    rda_resp, rda_route = await _invoke_partner("rda", rda_payload)
    rda_data = _extract_result(rda_resp)
    rda_state = _state(rda_resp)

    # 4) Compose dispatch and send to Engine.
    engine_payload = {
        "action": "engine.dispatch",
        "session_id": session_id,
        "user_id": req.user_id,
        "query": req.query,
        "intent": intent,
        "profile_vector": (rda_payload.get("profile_proposal") or {}).get("profile_vector") or [],
        "ann_weight": rda_data.get("final_weights", {}).get("ann_weight", 0.6),
        "cf_weight": rda_data.get("final_weights", {}).get("cf_weight", 0.4),
        "score_weights": rda_data.get("score_weights") or {},
        "mmr_lambda": rda_data.get("mmr_lambda", 0.5),
        "strategy": rda_data.get("strategy", "balanced"),
        "candidates": content_outputs.get("content_vectors") or [],
    }
    engine_resp, engine_route = await _invoke_partner("engine", engine_payload)
    engine_data = _extract_result(engine_resp)
    engine_state = _state(engine_resp)

    recommendations = engine_data.get("recommendations") if isinstance(engine_data.get("recommendations"), list) else []
    explanations = engine_data.get("explanations") if isinstance(engine_data.get("explanations"), list) else []

    response = {
        "session_id": session_id,
        "user_id": req.user_id,
        "leader_id": LEADER_ID,
        "intent": intent,
        "state": "completed" if recommendations else "needs_input",
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
        "recommendations": recommendations,
        "explanations": explanations,
    }

    SESSION_STORE.update_fields(session_id, {"last_response": response, "intent": intent})
    SESSION_STORE.append_message(session_id, "assistant", "orchestration_completed")
    return response


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
        "demo_page_available": DEMO_HTML_PATH.exists(),
    }


@app.post("/user_api")
async def user_api(req: UserRequest):
    if not str(req.user_id or "").strip():
        raise HTTPException(status_code=422, detail="user_id is required for /user_api")
    if not str(req.query or "").strip():
        raise HTTPException(status_code=422, detail="query is required")
    return await _orchestrate(req)


@app.post("/user_api_debug")
async def user_api_debug(req: UserRequest):
    if not str(req.query or "").strip():
        raise HTTPException(status_code=422, detail="query is required")
    if not str(req.user_id or "").strip():
        req.user_id = f"anon-{uuid.uuid4()}"
    return await _orchestrate(req)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("READING_CONCIERGE_HOST", "0.0.0.0")
    port = int(os.getenv("READING_CONCIERGE_PORT", str(RUNTIME.port)))
    uvicorn.run("reading_concierge.reading_concierge:app", host=host, port=port)
