from __future__ import annotations

import json
import math
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from acps_aip.aip_base_model import Message, Product, StructuredDataItem, Task, TaskState, TextDataItem
from acps_aip.aip_rpc_server import CommandHandlers, TaskManager, add_aip_rpc_router
from base import call_openai_chat, get_agent_logger, register_acs_route

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None

load_dotenv(_PROJECT_ROOT / ".env")

ACS_PATH = _CURRENT_DIR / "acs.json"
CONFIG_PATH = _CURRENT_DIR / "config.toml"
PROMPTS_PATH = _CURRENT_DIR / "prompts.toml"

AGENT_ID = os.getenv("READER_PROFILE_AGENT_ID", "reader_profile_agent_001")
AIP_ENDPOINT = os.getenv("READER_PROFILE_AGENT_ENDPOINT", "/reader-profile/rpc")
LOG_LEVEL = os.getenv("READER_PROFILE_AGENT_LOG_LEVEL", "INFO").upper()

logger = get_agent_logger("partner.reader_profile_agent", "READER_PROFILE_AGENT_LOG_LEVEL", LOG_LEVEL)


@dataclass
class AgentConfig:
    port: int = 8211
    dsn: str = "postgresql://user:pass@localhost:5432/acps"
    lambda_decay: float = 0.05
    warm_threshold: int = 20
    vector_dim: int = 256


def _load_config() -> AgentConfig:
    cfg = AgentConfig()
    if not tomllib or not CONFIG_PATH.exists():
        return cfg
    try:
        data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("event=config_parse_failed error=%s", exc)
        return cfg

    server = data.get("server") if isinstance(data, dict) else {}
    database = data.get("database") if isinstance(data, dict) else {}
    model = data.get("model") if isinstance(data, dict) else {}

    try:
        if isinstance(server, dict) and server.get("port"):
            cfg.port = int(server["port"])
    except Exception:
        pass
    if isinstance(database, dict) and database.get("dsn"):
        cfg.dsn = str(database["dsn"])
    env_dsn = str(os.getenv("READER_PROFILE_DB_DSN") or os.getenv("DATABASE_URL") or "").strip()
    if env_dsn:
        cfg.dsn = env_dsn
    try:
        if isinstance(model, dict) and model.get("LAMBDA") is not None:
            cfg.lambda_decay = float(model["LAMBDA"])
        if isinstance(model, dict) and model.get("WARM_THRESHOLD") is not None:
            cfg.warm_threshold = int(model["WARM_THRESHOLD"])
        if isinstance(model, dict) and model.get("VECTOR_DIM") is not None:
            cfg.vector_dim = int(model["VECTOR_DIM"])
    except Exception:
        pass
    return cfg


CFG = _load_config()


def _load_prompts() -> Dict[str, Dict[str, str]]:
    defaults = {
        "semantic_preference_induction": {
            "system": "Infer stable reader preference genres from behavior events.",
            "user_template": (
                "User ID: {user_id}\nWindow days: {window_days}\nEvent summary: {event_summary}\n"
                "Return JSON with key latent_genres as string list."
            ),
        },
        "evidence_request_response": {
            "system": "Provide conservative supplemental evidence for sparse profiles.",
            "user_template": (
                "Need fields: demographic_prior, adjusted_confidence, profile_vector_updated."
            ),
        },
    }
    if not tomllib or not PROMPTS_PATH.exists():
        return defaults
    try:
        data = tomllib.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("event=prompts_parse_failed error=%s", exc)
        return defaults
    for section in defaults:
        src = data.get(section) if isinstance(data, dict) else None
        if isinstance(src, dict):
            defaults[section]["system"] = str(src.get("system") or defaults[section]["system"])
            defaults[section]["user_template"] = str(src.get("user_template") or defaults[section]["user_template"])
    return defaults


PROMPTS = _load_prompts()


def _llm_available() -> bool:
    if not str(os.getenv("OPENAI_API_KEY") or "").strip():
        return False
    proxy_candidates = [
        str(os.getenv("HTTP_PROXY") or ""),
        str(os.getenv("HTTPS_PROXY") or ""),
        str(os.getenv("ALL_PROXY") or ""),
    ]
    uses_socks = any(p.lower().startswith("socks") for p in proxy_candidates if p)
    if uses_socks:
        try:
            import socksio  # type: ignore  # noqa: F401
        except Exception:
            return False
    return True

app = FastAPI(
    title="Reader Profile Agent (Phase 2)",
    description="Negotiation-ready reader profile partner with decay-weighted behavior modeling.",
)
register_acs_route(app, str(ACS_PATH))


def _parse_payload(message: Message) -> Dict[str, Any]:
    params = getattr(message, "commandParams", None) or {}
    payload = params.get("payload") if isinstance(params, dict) else None
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_structured_payload_from_message(message: Message) -> Dict[str, Any]:
    for item in getattr(message, "dataItems", []) or []:
        if getattr(item, "type", "") == "data" and isinstance(getattr(item, "data", None), dict):
            return item.data
    return {}


def _parse_iso(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _load_behavior_sequence(user_id: str, window_days: int = 90) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    if "change_me" in CFG.dsn:
        logger.warning("event=database_dsn_placeholder_detected dsn=%s", CFG.dsn)

    # Primary path: PostgreSQL
    if CFG.dsn.startswith("postgresql") and psycopg is not None:
        try:
            with psycopg.connect(CFG.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT user_id, book_id, event_type, weight, rating, duration_sec, created_at
                        FROM user_behavior_events
                        WHERE user_id = %s AND created_at >= %s
                        ORDER BY created_at DESC
                        """,
                        (user_id, cutoff),
                    )
                    rows = cur.fetchall()
            return [
                {
                    "user_id": r[0],
                    "book_id": r[1],
                    "event_type": r[2],
                    "weight": r[3],
                    "rating": r[4],
                    "duration_sec": r[5],
                    "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6] or ""),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("event=postgres_load_failed user_id=%s error=%s", user_id, exc)

    # Fallback path for local development
    try:
        import sqlite3

        db_path = _PROJECT_ROOT / "data" / "recommendation_runtime.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT user_id, book_id, event_type, weight, rating, duration_sec, created_at
                FROM user_behavior_events
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
        finally:
            conn.close()

        out: List[Dict[str, Any]] = []
        for row in rows:
            ts = _parse_iso(row["created_at"])
            if ts is not None and ts < cutoff:
                continue
            out.append(dict(row))
        return out
    except Exception as exc:
        logger.warning("event=sqlite_fallback_load_failed user_id=%s error=%s", user_id, exc)
        return []


def _stable_bucket(text: str, dim: int) -> int:
    return abs(hash(text)) % dim


def _compute_decay_weight(created_at: Any, base_weight: float = 1.0) -> float:
    event_time = _parse_iso(created_at)
    if event_time is None:
        return float(base_weight)
    age_days = max(0.0, (datetime.now(timezone.utc) - event_time).total_seconds() / 86400.0)
    return float(base_weight) * math.exp(-CFG.lambda_decay * age_days)


def _build_profile_vector(events: List[Dict[str, Any]], dim: int) -> List[float]:
    vec = [0.0] * dim
    for event in events:
        book_id = str(event.get("book_id") or "")
        event_type = str(event.get("event_type") or "unknown")
        rating = float(event.get("rating") or 0.0)
        weight = float(event.get("weight") or 1.0)
        score = _compute_decay_weight(event.get("created_at"), base_weight=max(weight, rating, 0.1))
        idx_a = _stable_bucket(f"book:{book_id}", dim)
        idx_b = _stable_bucket(f"evt:{event_type}", dim)
        idx_c = _stable_bucket(f"joint:{book_id}:{event_type}", dim)
        vec[idx_a] += 0.50 * score
        vec[idx_b] += 0.30 * score
        vec[idx_c] += 0.20 * score

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [round(v / norm, 6) for v in vec]
    return vec


def _confidence_from_events(event_count: int) -> float:
    base = min(1.0, event_count / float(max(1, CFG.warm_threshold)))
    return max(0.05, min(1.0, round(base, 4)))


def _derive_behavior_genres_from_payload(payload: Dict[str, Any], events: List[Dict[str, Any]]) -> List[str]:
    existing = payload.get("behavior_genres")
    if isinstance(existing, list) and existing:
        return [str(g).strip().lower() for g in existing if str(g).strip()]

    counts: Dict[str, float] = {}
    for event in events:
        genre = str(event.get("genre") or event.get("event_type") or "").strip().lower()
        if not genre:
            continue
        counts[genre] = counts.get(genre, 0.0) + _compute_decay_weight(event.get("created_at"), 1.0)
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, _ in ordered[:8]]


def _event_summary(events: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for row in events[:30]:
        lines.append(
            " | ".join(
                [
                    f"book={row.get('book_id', '')}",
                    f"type={row.get('event_type', '')}",
                    f"rating={row.get('rating', '')}",
                    f"weight={row.get('weight', '')}",
                    f"at={row.get('created_at', '')}",
                ]
            )
        )
    return "\n".join(lines) or "no events"


def _extract_json_obj(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    left = raw.find("{")
    right = raw.rfind("}")
    if left >= 0 and right > left:
        snippet = raw[left : right + 1]
        try:
            parsed = json.loads(snippet)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


async def _infer_behavior_genres(user_id: str, window_days: int, events: List[Dict[str, Any]], baseline: List[str]) -> List[str]:
    if not _llm_available():
        return baseline
    prompt_cfg = PROMPTS.get("semantic_preference_induction") or {}
    system_prompt = str(prompt_cfg.get("system") or "")
    template = str(prompt_cfg.get("user_template") or "")
    user_prompt = template.format(
        user_id=user_id,
        window_days=window_days,
        event_summary=_event_summary(events),
    )
    # Keep explicit baseline in-context so LLM extraction remains anchored.
    user_prompt += f"\nBaseline behavior_genres: {json.dumps(baseline, ensure_ascii=False)}"

    try:
        raw = await call_openai_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=os.getenv("READER_PROFILE_LLM_MODEL", os.getenv("OPENAI_MODEL", "qwen3.5-35b-a3b")),
            temperature=0.1,
            max_tokens=180,
        )
        parsed = _extract_json_obj(raw)
        latent = parsed.get("latent_genres")
        if isinstance(latent, list):
            cleaned = [str(x).strip().lower() for x in latent if str(x).strip()]
            if cleaned:
                return cleaned[:10]
    except Exception as exc:
        logger.warning("event=llm_genre_inference_failed user_id=%s error=%s", user_id, exc)
    return baseline


def _extract_action(payload: Dict[str, Any]) -> str:
    action = str(
        payload.get("action")
        or payload.get("skill")
        or payload.get("intent")
        or payload.get("command")
        or "uma.build_profile"
    ).strip()
    return action


async def _run_profile_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(payload.get("user_id") or "").strip() or "anonymous"
    window_days = int(payload.get("window_days") or 90)
    events = _load_behavior_sequence(user_id, window_days=window_days)
    event_count = len(events)

    profile_vector = _build_profile_vector(events, dim=CFG.vector_dim)
    confidence = _confidence_from_events(event_count)
    cold_start = event_count < 5
    if cold_start:
        confidence = min(confidence, 0.25)

    baseline_genres = _derive_behavior_genres_from_payload(payload, events)
    behavior_genres = await _infer_behavior_genres(user_id, window_days, events, baseline_genres)

    strategy = "explore" if cold_start else "exploit"
    return {
        "user_id": user_id,
        "profile_vector": profile_vector,
        "confidence": round(float(confidence), 4),
        "event_count": event_count,
        "cold_start": cold_start,
        "behavior_genres": behavior_genres,
        "strategy_suggestion": strategy,
        "window_days": window_days,
        "model": {
            "lambda": CFG.lambda_decay,
            "vector_dim": CFG.vector_dim,
            "warm_threshold": CFG.warm_threshold,
        },
    }


def _build_supplement(profile: Dict[str, Any]) -> Dict[str, Any]:
    cold_start = bool(profile.get("cold_start"))
    confidence = float(profile.get("confidence") or 0.1)
    adjusted_confidence = min(confidence, 0.3) if cold_start else confidence
    return {
        "demographic_prior": {
            "cluster": "general_reader",
            "genre_prior": ["fiction", "history", "nonfiction"],
        },
        "adjusted_confidence": round(float(adjusted_confidence), 4),
        "profile_vector_updated": profile.get("profile_vector") or [],
    }


async def _handle_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = _extract_action(payload)

    # Required negotiation interfaces from Phase 2 plan.
    if action in {"uma.build_profile", "uma.validate_consistency", "uma.update_profile"}:
        profile = await _run_profile_pipeline(payload)
        consistency = {
            "valid": bool(profile.get("profile_vector")),
            "reason": "ok" if profile.get("profile_vector") else "empty_profile_vector",
        }
        return {
            "action": action,
            **profile,
            "consistency": consistency,
            "negotiation_interfaces": [
                "uma.build_profile",
                "uma.validate_consistency",
                "uma.update_profile",
            ],
        }

    # RDA evidence request branch.
    if action in {"supplement_proposal", "request.supplement_proposal", "rda.evidence_request"}:
        profile = await _run_profile_pipeline(payload)
        return {
            "action": action,
            **profile,
            "supplement": _build_supplement(profile),
        }

    # Feedback Agent trigger for incremental update.
    if action in {"feedback.update_profile", "update_profile", "fa.trigger_update"}:
        profile = await _run_profile_pipeline(payload)
        return {
            "action": action,
            "trigger": "feedback_agent",
            **profile,
            "update_mode": "incremental",
        }

    profile = await _run_profile_pipeline(payload)
    return {"action": action, **profile}


def _fail_task(task_id: str, reason: str) -> Task:
    TaskManager.update_task_status(task_id, TaskState.Failed, data_items=[TextDataItem(text=reason)])
    return TaskManager.get_task(task_id)


def _complete_task(task_id: str, result: Dict[str, Any]) -> Task:
    product = Product(
        id=str(uuid.uuid4()),
        name="reader-profile-proposal",
        description="Reader profile proposal for negotiation",
        dataItems=[
            StructuredDataItem(data=result),
            TextDataItem(text=f"profile built for user={result.get('user_id', 'unknown')}"),
        ],
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
        started = time.perf_counter()
        result = await _handle_payload(payload)
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        result["agent_id"] = AGENT_ID
        return _complete_task(task.id, result)
    except Exception as exc:
        logger.exception("event=handle_start_failed task_id=%s", task.id)
        return _fail_task(task.id, f"handle_start_failed: {exc}")


async def handle_continue(message: Message, task: Task) -> Task:
    TaskManager.add_message_to_history(task.id, message)
    if task.status.state in {TaskState.Completed, TaskState.Canceled, TaskState.Failed, TaskState.Rejected}:
        return task
    hinted = _extract_structured_payload_from_message(message)
    performative = str(hinted.get("performative") or hinted.get("action") or "").strip().lower()
    if performative in {"inform", "feedback.update_profile", "fa.trigger_update", "update_profile"}:
        return await notification_handlers.on_inform(message, task)
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


class NotificationHandlers:
    def __init__(self, on_inform):
        self.on_inform = on_inform


async def _on_inform(message: Message, task: Task) -> Task:
    payload = _extract_structured_payload_from_message(message)
    # mentions field acts as subscription-like filter for targeted async informs
    mentions = getattr(message, "mentions", None)
    if isinstance(mentions, list) and AGENT_ID not in mentions and "all" not in mentions:
        return task
    performative = str(payload.get("performative") or payload.get("action") or "").strip().lower()
    if performative not in {"inform", "feedback.update_profile", "fa.trigger_update", "update_profile"}:
        return task

    next_payload = dict(payload)
    next_payload["action"] = "feedback.update_profile"
    result = await _handle_payload(next_payload)
    result["agent_id"] = AGENT_ID
    result["notification"] = {"source": message.senderId, "mentions": mentions}
    return _complete_task(task.id, result)


notification_handlers = NotificationHandlers(on_inform=_on_inform)


async def _on_message(message: Message, task: Task | None) -> Task:
    if task is None:
        task = TaskManager.create_task(message, initial_state=TaskState.Working)
    return await notification_handlers.on_inform(message, task)


handlers = CommandHandlers(
    on_start=handle_start,
    on_continue=handle_continue,
    on_cancel=handle_cancel,
    on_message=_on_message,
)
add_aip_rpc_router(app, AIP_ENDPOINT, handlers)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("READER_PROFILE_HOST", "0.0.0.0")
    port = int(os.getenv("READER_PROFILE_PORT", str(CFG.port)))
    uvicorn.run(app, host=host, port=port)
