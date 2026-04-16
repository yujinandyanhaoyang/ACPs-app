from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from acps_aip.aip_base_model import Message, Product, StructuredDataItem, Task, TaskState, TextDataItem
from acps_aip.aip_rpc_server import CommandHandlers, TaskManager, add_aip_rpc_router
from base import get_agent_logger, register_acs_route
from partners.online.reader_profile_agent import agent as reader_profile
from partners.online.recommendation_decision_agent import agent as recommendation_decision
from partners.online.recommendation_engine_agent import agent as recommendation_engine

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore

load_dotenv(_PROJECT_ROOT / ".env")

ACS_PATH = _CURRENT_DIR / "acs.json"
CONFIG_PATH = _CURRENT_DIR / "config.toml"

AGENT_ID = os.getenv("FEEDBACK_AGENT_ID", "feedback_agent_001")
AIP_ENDPOINT = os.getenv("FEEDBACK_AGENT_ENDPOINT", "/feedback/rpc")
LOG_LEVEL = os.getenv("FEEDBACK_AGENT_LOG_LEVEL", "INFO").upper()
PARTNER_MODE = os.getenv("FEEDBACK_PARTNER_MODE", "auto").strip().lower()

logger = get_agent_logger("partner.feedback_agent", "FEEDBACK_AGENT_LOG_LEVEL", LOG_LEVEL)

EVENT_WEIGHTS: Dict[str, float] = {
    "finish": 1.0,
    "rate_5": 1.0,
    "rate_4": 0.8,
    "rate_3": 0.3,
    "click": 0.3,
    "view": 0.1,
    "rate_2": -0.3,
    "skip": -0.5,
    "rate_1": -0.8,
}
RATING_EVENTS = {"rate_1", "rate_2", "rate_3", "rate_4", "rate_5"}
SESSION_COMPLETION_EVENTS = {"finish", "skip", "rate_1", "rate_2", "rate_3", "rate_4", "rate_5"}


@dataclass
class AgentConfig:
    port: int = 8215
    redis_url: str = "redis://localhost:6379/2"
    user_update_threshold: int = 20
    cf_retrain_threshold: int = 500
    rpa_aic: str = "<AIC-RPA>"
    engine_aic: str = "<AIC-ENGINE>"
    rda_aic: str = "<AIC-RDA>"


class BehaviorEvent(BaseModel):
    user_id: str
    event_type: str
    session_id: Optional[str] = None
    context_type: Optional[str] = None
    action: Optional[str] = None
    reward_override: Optional[float] = None
    session_completed: Optional[bool] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    event_time: Optional[str] = None


class EventStore:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis = None
        self._mem_events: List[Dict[str, Any]] = []
        self._mem_user_counts: Dict[str, int] = {}
        self._mem_rating_count: int = 0
        self._init_redis()

    def _init_redis(self) -> None:
        if redis is None:
            logger.warning("event=redis_client_unavailable fallback=memory")
            return
        try:
            client = redis.from_url(self.redis_url, decode_responses=True)
            client.ping()
            self._redis = client
        except Exception as exc:
            logger.warning("event=redis_connect_failed url=%s fallback=memory error=%s", self.redis_url, exc)

    def _event_key(self) -> str:
        return "fa:events"

    def _user_count_key(self, user_id: str) -> str:
        return f"fa:user_events:{user_id}"

    def _rating_count_key(self) -> str:
        return "fa:global_rating_events"

    def append_event(self, event: Dict[str, Any]) -> None:
        serialized = json.dumps(event, ensure_ascii=False)
        if self._redis is not None:
            try:
                self._redis.rpush(self._event_key(), serialized)
                return
            except Exception:
                pass
        self._mem_events.append(event)

    def incr_user_count(self, user_id: str) -> int:
        if self._redis is not None:
            try:
                return int(self._redis.incr(self._user_count_key(user_id)))
            except Exception:
                pass
        cur = int(self._mem_user_counts.get(user_id) or 0) + 1
        self._mem_user_counts[user_id] = cur
        return cur

    def incr_rating_count(self) -> int:
        if self._redis is not None:
            try:
                return int(self._redis.incr(self._rating_count_key()))
            except Exception:
                pass
        self._mem_rating_count += 1
        return self._mem_rating_count


CFG = AgentConfig()
if tomllib and CONFIG_PATH.exists():
    try:
        data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        server = data.get("server") if isinstance(data, dict) else {}
        redis_cfg = data.get("redis") if isinstance(data, dict) else {}
        trigger = data.get("trigger") if isinstance(data, dict) else {}
        agents = data.get("agents") if isinstance(data, dict) else {}

        if isinstance(server, dict) and server.get("port") is not None:
            CFG.port = int(server["port"])
        if isinstance(redis_cfg, dict) and redis_cfg.get("url"):
            CFG.redis_url = str(redis_cfg["url"])
        if isinstance(trigger, dict):
            if trigger.get("USER_UPDATE_THRESHOLD") is not None:
                CFG.user_update_threshold = int(trigger["USER_UPDATE_THRESHOLD"])
            if trigger.get("CF_RETRAIN_THRESHOLD") is not None:
                CFG.cf_retrain_threshold = int(trigger["CF_RETRAIN_THRESHOLD"])
        if isinstance(agents, dict):
            CFG.rpa_aic = str(agents.get("RPA_AIC") or CFG.rpa_aic)
            CFG.engine_aic = str(agents.get("ENGINE_AIC") or CFG.engine_aic)
            CFG.rda_aic = str(agents.get("RDA_AIC") or CFG.rda_aic)
    except Exception as exc:
        logger.warning("event=config_parse_failed error=%s", exc)

STORE = EventStore(CFG.redis_url)

app = FastAPI(
    title="Feedback Agent (Phase 3)",
    description="Behavior-event webhook receiver and reward/trigger emitter.",
)
register_acs_route(app, str(ACS_PATH))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_weight(event_type: str, reward_override: Optional[float]) -> float:
    if reward_override is not None:
        try:
            return float(reward_override)
        except Exception:
            return 0.0
    return float(EVENT_WEIGHTS.get(event_type, 0.0))


def _session_completed(event_type: str, session_completed: Optional[bool]) -> bool:
    if session_completed is not None:
        return bool(session_completed)
    return event_type in SESSION_COMPLETION_EVENTS


def _mk_rpc_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    message = {
        "type": "message",
        "id": str(uuid.uuid4()),
        "sentAt": _now_iso(),
        "senderRole": "partner",
        "senderId": AGENT_ID,
        "command": "start",
        "dataItems": [{"type": "text", "text": ""}],
        "taskId": f"task-{uuid.uuid4()}",
        "sessionId": payload.get("session_id") or "feedback-session",
        "commandParams": {"payload": payload},
    }
    return {
        "jsonrpc": "2.0",
        "method": "rpc",
        "id": str(uuid.uuid4()),
        "params": {"message": message},
    }


def _resolve_partner(partner_key: str) -> Dict[str, Any]:
    remote_env = {
        "rda": "RECOMMENDATION_DECISION_RPC_URL",
        "rpa": "READER_PROFILE_RPC_URL",
        "engine": "RECOMMENDATION_ENGINE_RPC_URL",
    }
    local_map = {
        "rda": {
            "app": recommendation_decision.app,
            "endpoint": "/recommendation-decision/rpc",
        },
        "rpa": {
            "app": reader_profile.app,
            "endpoint": "/reader-profile/rpc",
        },
        "engine": {
            "app": recommendation_engine.app,
            "endpoint": "/recommendation-engine/rpc",
        },
    }
    item = dict(local_map[partner_key])
    item["remote_url"] = str(os.getenv(remote_env[partner_key]) or "").strip() or None
    return item


async def _invoke_local(app_obj: FastAPI, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    rpc = _mk_rpc_payload(payload)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_obj),
        base_url="http://agent",
        timeout=20,
        trust_env=False,
    ) as client:
        resp = await client.post(endpoint, json=rpc)
    resp.raise_for_status()
    return resp.json()


async def _invoke_remote(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    rpc = _mk_rpc_payload(payload)
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
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


async def _emit_inform(partner_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if PARTNER_MODE in {"off", "disabled", "none"}:
        return {"partner": partner_key, "route": "disabled", "status": "skipped"}

    partner = _resolve_partner(partner_key)
    remote_url = partner.get("remote_url")

    if remote_url and PARTNER_MODE in {"auto", "remote"}:
        try:
            await _invoke_remote(str(remote_url), payload)
            return {"partner": partner_key, "route": "remote", "status": "sent"}
        except Exception as exc:
            logger.warning("event=feedback_inform_remote_failed partner=%s error=%s", partner_key, exc)
            if PARTNER_MODE == "remote":
                return {"partner": partner_key, "route": "remote", "status": "failed", "reason": str(exc)}

    try:
        await _invoke_local(partner["app"], partner["endpoint"], payload)
        return {"partner": partner_key, "route": "local", "status": "sent"}
    except Exception as exc:
        return {"partner": partner_key, "route": "local", "status": "failed", "reason": str(exc)}


async def _process_event(event: BehaviorEvent) -> Dict[str, Any]:
    event_type = str(event.event_type or "").strip().lower()
    weight = _event_weight(event_type, event.reward_override)

    row = {
        "event_id": str(uuid.uuid4()),
        "user_id": event.user_id,
        "event_type": event_type,
        "reward": weight,
        "session_id": event.session_id,
        "context_type": event.context_type,
        "action": event.action,
        "metadata": dict(event.metadata or {}),
        "event_time": event.event_time or _now_iso(),
        "ingested_at": _now_iso(),
    }
    STORE.append_event(row)

    user_count = STORE.incr_user_count(event.user_id)
    rating_count = None
    if event_type in RATING_EVENTS:
        rating_count = STORE.incr_rating_count()

    informs: List[Dict[str, Any]] = []
    rda_reward_updated = False
    profile_updated = False
    cf_retrain_triggered = False

    if _session_completed(event_type, event.session_completed):
        rda_payload = {
            "performative": "inform",
            "action": "feedback.reward",
            "context_type": str(event.context_type or "low_conf_high_div"),
            "arm_action": str(event.action or "balanced"),
            "reward": weight,
            "session_id": event.session_id,
            "user_id": event.user_id,
            "source": "feedback_agent",
        }
        rda_emit = await _emit_inform("rda", rda_payload)
        informs.append(rda_emit)
        rda_reward_updated = str(rda_emit.get("status") or "").lower() == "sent"

    should_update_profile = weight > 0 or (CFG.user_update_threshold > 0 and user_count >= CFG.user_update_threshold)
    if should_update_profile:
        profile_snapshot = await _invoke_local(
            reader_profile.app,
            "/reader-profile/rpc",
            {
                "performative": "request",
                "action": "uma.build_profile",
                "user_id": event.user_id,
            },
        )
        profile_data = _extract_result(profile_snapshot)
        profile_event_count = int(profile_data.get("event_count") or 0)
        should_update_profile = (profile_event_count + user_count) >= CFG.user_update_threshold

    if should_update_profile:
        rpa_payload = {
            "performative": "inform",
            "action": "feedback.update_profile",
            "trigger": "update_profile",
            "user_id": event.user_id,
            "event_count": user_count,
            "source": "feedback_agent",
        }
        rpa_emit = await _emit_inform("rpa", rpa_payload)
        informs.append(rpa_emit)
        profile_updated = should_update_profile

    if rating_count is not None and CFG.cf_retrain_threshold > 0 and rating_count % CFG.cf_retrain_threshold == 0:
        eng_payload = {
            "performative": "inform",
            "action": "feedback.retrain_cf",
            "trigger": "retrain_cf",
            "global_rating_events": rating_count,
            "source": "feedback_agent",
        }
        engine_emit = await _emit_inform("engine", eng_payload)
        informs.append(engine_emit)
        cf_retrain_triggered = str(engine_emit.get("status") or "").lower() == "sent"

    return {
        "status": "accepted",
        "event": row,
        "counters": {
            "user_event_count": user_count,
            "global_rating_count": rating_count,
        },
        "informs": informs,
        "triggers": {
            "profile_updated": profile_updated,
            "cf_retrain_triggered": cf_retrain_triggered,
            "rda_reward_updated": rda_reward_updated,
        },
    }


@app.post("/feedback/webhook")
async def feedback_webhook(event: BehaviorEvent):
    return await _process_event(event)


def _parse_payload(message: Message) -> Dict[str, Any]:
    params = getattr(message, "commandParams", None) or {}
    payload = params.get("payload") if isinstance(params, dict) else None
    if isinstance(payload, dict):
        return payload
    for item in getattr(message, "dataItems", []) or []:
        if getattr(item, "type", "") == "data" and isinstance(getattr(item, "data", None), dict):
            return item.data
    return {}


async def _handle_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    event = BehaviorEvent(
        user_id=str(payload.get("user_id") or ""),
        event_type=str(payload.get("event_type") or payload.get("action") or "view"),
        session_id=payload.get("session_id"),
        context_type=payload.get("context_type"),
        action=payload.get("arm_action") or payload.get("action_name") or payload.get("action"),
        reward_override=payload.get("reward"),
        session_completed=payload.get("session_completed"),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        event_time=payload.get("event_time"),
    )
    if not event.user_id:
        event.user_id = "anonymous"
    return await _process_event(event)


def _fail_task(task_id: str, reason: str) -> Task:
    TaskManager.update_task_status(task_id, TaskState.Failed, data_items=[TextDataItem(text=reason)])
    return TaskManager.get_task(task_id)


def _complete_task(task_id: str, result: Dict[str, Any]) -> Task:
    product = Product(
        id=str(uuid.uuid4()),
        name="feedback-result",
        description="Feedback ingestion and trigger dispatch result",
        dataItems=[StructuredDataItem(data=result), TextDataItem(text="feedback processed")],
    )
    TaskManager.set_products(task_id, [product])
    TaskManager.update_task_status(task_id, TaskState.Completed, data_items=[TextDataItem(text="completed")])
    return TaskManager.get_task(task_id)


async def handle_start(message: Message, existing_task: Task | None) -> Task:
    if existing_task:
        return existing_task
    task = TaskManager.create_task(message, initial_state=TaskState.Working)
    payload = _parse_payload(message)
    try:
        result = await _handle_payload(payload)
        result["agent_id"] = AGENT_ID
        return _complete_task(task.id, result)
    except Exception as exc:
        logger.exception("event=handle_start_failed task_id=%s", task.id)
        return _fail_task(task.id, f"handle_start_failed: {exc}")


async def handle_continue(message: Message, task: Task) -> Task:
    TaskManager.add_message_to_history(task.id, message)
    if task.status.state in {TaskState.Completed, TaskState.Canceled, TaskState.Failed, TaskState.Rejected}:
        return task

    payload = _parse_payload(message)
    try:
        result = await _handle_payload(payload)
        result["agent_id"] = AGENT_ID
        return _complete_task(task.id, result)
    except Exception as exc:
        logger.exception("event=handle_continue_failed task_id=%s", task.id)
        return _fail_task(task.id, f"handle_continue_failed: {exc}")


async def handle_cancel(message: Message, task: Task) -> Task:
    TaskManager.add_message_to_history(task.id, message)
    if task.status.state in {TaskState.Completed, TaskState.Canceled, TaskState.Failed, TaskState.Rejected}:
        return task
    return TaskManager.update_task_status(task.id, TaskState.Canceled)


async def handle_message(message: Message, task: Task | None) -> Task:
    if task is None:
        task = TaskManager.create_task(message, initial_state=TaskState.Working)
    payload = _parse_payload(message)
    result = await _handle_payload(payload)
    result["agent_id"] = AGENT_ID
    return _complete_task(task.id, result)


handlers = CommandHandlers(
    on_start=handle_start,
    on_continue=handle_continue,
    on_cancel=handle_cancel,
    on_message=handle_message,
)
add_aip_rpc_router(app, AIP_ENDPOINT, handlers)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("FEEDBACK_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("FEEDBACK_AGENT_PORT", str(CFG.port)))
    uvicorn.run(app, host=host, port=port)
