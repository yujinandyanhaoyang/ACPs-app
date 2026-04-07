from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from acps_aip.aip_base_model import Message, Product, StructuredDataItem, Task, TaskState, TextDataItem
from acps_aip.aip_rpc_server import CommandHandlers, TaskManager, add_aip_rpc_router
from base import get_agent_logger, register_acs_route

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore

load_dotenv()

ACS_PATH = _CURRENT_DIR / "acs.json"
CONFIG_PATH = _CURRENT_DIR / "config.toml"
LOCAL_ARM_STORE_PATH = _CURRENT_DIR / "arm_records.local.json"

AGENT_ID = os.getenv("RECOMMENDATION_DECISION_AGENT_ID", "recommendation_decision_agent_001")
AIP_ENDPOINT = os.getenv("RECOMMENDATION_DECISION_AGENT_ENDPOINT", "/recommendation-decision/rpc")
LOG_LEVEL = os.getenv("RECOMMENDATION_DECISION_AGENT_LOG_LEVEL", "INFO").upper()

logger = get_agent_logger("partner.recommendation_decision_agent", "RECOMMENDATION_DECISION_AGENT_LOG_LEVEL", LOG_LEVEL)


@dataclass
class AgentConfig:
    port: int = 8213
    redis_url: str = "redis://localhost:6379/1"
    ucb_c: float = 1.41
    max_rounds: int = 1
    min_trials_for_confidence: int = 20


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
    redis_cfg = data.get("redis") if isinstance(data, dict) else {}
    bandit = data.get("bandit") if isinstance(data, dict) else {}

    try:
        if isinstance(server, dict) and server.get("port") is not None:
            cfg.port = int(server["port"])
    except Exception:
        pass

    if isinstance(redis_cfg, dict) and redis_cfg.get("url"):
        cfg.redis_url = str(redis_cfg["url"])

    try:
        if isinstance(bandit, dict) and bandit.get("UCB_C") is not None:
            cfg.ucb_c = float(bandit["UCB_C"])
        if isinstance(bandit, dict) and bandit.get("MAX_ROUNDS") is not None:
            cfg.max_rounds = int(bandit["MAX_ROUNDS"])
        if isinstance(bandit, dict) and bandit.get("MIN_TRIALS_FOR_CONFIDENCE") is not None:
            cfg.min_trials_for_confidence = int(bandit["MIN_TRIALS_FOR_CONFIDENCE"])
    except Exception:
        pass

    return cfg


CFG = _load_config()

app = FastAPI(
    title="Recommendation Decision Agent (Phase 2)",
    description="Neutral mediator that performs proposal quality gating and UCB arbitration.",
)
register_acs_route(app, str(ACS_PATH))


class ArmStore:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis_client = None
        self._file_cache: Dict[str, Dict[str, float]] = {}
        self._load_local_file()
        self._try_init_redis()

    def _try_init_redis(self) -> None:
        if redis is None:
            logger.warning("event=redis_client_unavailable fallback=local_file")
            return
        try:
            client = redis.from_url(self.redis_url, decode_responses=True)
            client.ping()
            self._redis_client = client
        except Exception as exc:
            logger.warning("event=redis_connect_failed url=%s fallback=local_file error=%s", self.redis_url, exc)

    def _arm_key(self, context_type: str, action: str) -> str:
        digest = hashlib.sha1(action.encode("utf-8")).hexdigest()[:10]
        return f"bandit:{context_type}:{digest}"

    def _load_local_file(self) -> None:
        if not LOCAL_ARM_STORE_PATH.exists():
            self._file_cache = {}
            return
        try:
            data = json.loads(LOCAL_ARM_STORE_PATH.read_text(encoding="utf-8"))
            self._file_cache = data if isinstance(data, dict) else {}
        except Exception:
            self._file_cache = {}

    def _save_local_file(self) -> None:
        LOCAL_ARM_STORE_PATH.write_text(json.dumps(self._file_cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_record(self, context_type: str, action: str) -> Dict[str, float]:
        key = self._arm_key(context_type, action)
        if self._redis_client is not None:
            try:
                raw = self._redis_client.hgetall(key) or {}
                trials = float(raw.get("trials", 0.0))
                avg_reward = float(raw.get("avg_reward", 0.0))
                return {"trials": trials, "avg_reward": avg_reward}
            except Exception:
                pass

        local = self._file_cache.get(key) or {}
        return {
            "trials": float(local.get("trials", 0.0)),
            "avg_reward": float(local.get("avg_reward", 0.0)),
        }

    def update_reward(self, context_type: str, action: str, reward: float) -> Dict[str, float]:
        current = self.get_record(context_type, action)
        old_trials = float(current.get("trials", 0.0))
        old_avg = float(current.get("avg_reward", 0.0))
        new_trials = old_trials + 1.0
        new_avg = ((old_avg * old_trials) + float(reward)) / new_trials

        key = self._arm_key(context_type, action)
        if self._redis_client is not None:
            try:
                self._redis_client.hset(key, mapping={"trials": new_trials, "avg_reward": new_avg})
                return {"trials": new_trials, "avg_reward": new_avg}
            except Exception:
                pass

        self._file_cache[key] = {"trials": new_trials, "avg_reward": new_avg}
        self._save_local_file()
        return {"trials": new_trials, "avg_reward": new_avg}


ARM_STORE = ArmStore(CFG.redis_url)


def _parse_payload(message: Message) -> Dict[str, Any]:
    params = getattr(message, "commandParams", None) or {}
    payload = params.get("payload") if isinstance(params, dict) else None
    if isinstance(payload, dict):
        return payload
    for item in getattr(message, "dataItems", []) or []:
        if getattr(item, "type", "") == "data" and isinstance(getattr(item, "data", None), dict):
            return item.data
    return {}


def _extract_action(payload: Dict[str, Any]) -> str:
    return str(payload.get("action") or payload.get("skill") or "rda.arbitrate").strip()


def _context_type(confidence: float, divergence: float) -> str:
    c = "high_conf" if confidence >= 0.5 else "low_conf"
    d = "high_div" if divergence >= 0.5 else "low_div"
    return f"{c}_{d}"


def _quality_issues(profile: Dict[str, Any], content: Dict[str, Any], raw_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    confidence = float(profile.get("confidence") or 0.0)
    divergence = float(content.get("divergence_score") or 0.0)

    if confidence < 0.3:
        issues.append({
            "target": "rpa",
            "reason": "low_confidence",
            "required_fields": ["cold_start_prior", "adjusted_confidence"],
        })

    if content.get("weight_suggestion") is None or content.get("coverage_report") is None:
        issues.append({
            "target": "bca",
            "reason": "missing_content_fields",
            "required_fields": ["complete_weight_suggestion", "coverage_report"],
        })

    if divergence > 0.7 and confidence > 0.6:
        issues.append({
            "target": "both",
            "reason": "extreme_misalignment",
            "required_fields": ["extended_evidence"],
        })

    counter_received = bool(raw_payload.get("counter_proposal_received"))
    has_counter_payload = bool(content.get("counter_proposal"))
    if counter_received and not has_counter_payload:
        issues.append({
            "target": "bca",
            "reason": "counter_proposal_missing_payload",
            "required_fields": ["fallback_strategy"],
        })

    return issues


def _build_evidence_requests(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    requests: List[Dict[str, Any]] = []
    for issue in issues:
        target = issue.get("target")
        if target in {"rpa", "both"}:
            requests.append({
                "to": "reader_profile_agent",
                "performative": "request",
                "action": "supplement_proposal",
                "required_fields": issue.get("required_fields") or [],
                "reason": issue.get("reason"),
            })
        if target in {"bca", "both"}:
            requests.append({
                "to": "book_content_agent",
                "performative": "request",
                "action": "supplement_proposal",
                "required_fields": issue.get("required_fields") or [],
                "reason": issue.get("reason"),
            })
    return requests


def _arm_actions() -> List[str]:
    return [
        "profile_dominant",
        "balanced",
        "content_dominant",
        "conservative",
    ]


def _ucb_pick(context_type: str, confidence: float, divergence: float, strategy_hint: str) -> Tuple[str, Dict[str, Dict[str, float]]]:
    actions = _arm_actions()
    records = {action: ARM_STORE.get_record(context_type, action) for action in actions}
    min_trials = min(float(records[a]["trials"]) for a in actions)

    if min_trials < CFG.min_trials_for_confidence:
        if confidence >= 0.7 and divergence >= 0.5:
            return "balanced", records
        if confidence >= 0.7:
            return "profile_dominant", records
        if divergence >= 0.7:
            return "content_dominant", records
        return "conservative", records

    total_trials = sum(float(records[a]["trials"]) for a in actions)
    total_trials = max(total_trials, 1.0)

    scores: Dict[str, float] = {}
    for action in actions:
        n = float(records[action]["trials"])
        avg = float(records[action]["avg_reward"])
        if n <= 0:
            scores[action] = float("inf")
            continue
        scores[action] = avg + CFG.ucb_c * math.sqrt(math.log(total_trials) / n)

    best = max(scores.items(), key=lambda kv: kv[1])[0]
    sorted_scores = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if len(sorted_scores) >= 2:
        gap = sorted_scores[0][1] - sorted_scores[1][1]
        if gap <= 0.05 and strategy_hint in {"explore", "exploit"}:
            best = "content_dominant" if strategy_hint == "explore" else "profile_dominant"

    return best, records


def _decision_payload(action: str, confidence: float, divergence: float) -> Dict[str, Any]:
    if action == "profile_dominant":
        return {
            "ann_weight": 0.7,
            "cf_weight": 0.3,
            "score_weights": {"content": 0.45, "cf": 0.35, "novelty": 0.1, "recency": 0.1},
            "mmr_lambda": 0.35,
            "strategy": "profile_dominant",
        }
    if action == "content_dominant":
        return {
            "ann_weight": 0.8,
            "cf_weight": 0.2,
            "score_weights": {"content": 0.55, "cf": 0.2, "novelty": 0.2, "recency": 0.05},
            "mmr_lambda": 0.65,
            "strategy": "explore",
        }
    if action == "balanced":
        return {
            "ann_weight": 0.6,
            "cf_weight": 0.4,
            "score_weights": {"content": 0.4, "cf": 0.35, "novelty": 0.15, "recency": 0.1},
            "mmr_lambda": 0.5,
            "strategy": "balanced",
        }
    return {
        "ann_weight": 0.5,
        "cf_weight": 0.5,
        "score_weights": {"content": 0.35, "cf": 0.35, "novelty": 0.15, "recency": 0.15},
        "mmr_lambda": 0.55,
        "strategy": "conservative",
    }


async def _arbitrate(payload: Dict[str, Any]) -> Dict[str, Any]:
    profile = payload.get("profile_proposal") if isinstance(payload.get("profile_proposal"), dict) else {}
    content = payload.get("content_proposal") if isinstance(payload.get("content_proposal"), dict) else {}
    profile_supp = payload.get("rpa_supplement") if isinstance(payload.get("rpa_supplement"), dict) else {}
    content_supp = payload.get("bca_supplement") if isinstance(payload.get("bca_supplement"), dict) else {}
    cold_start = bool(profile.get("cold_start") or payload.get("cold_start"))
    max_rounds = 2 if cold_start else 1

    rounds: List[Dict[str, Any]] = []
    converged = False
    fallback_applied = False

    for round_idx in range(1, max(1, max_rounds) + 1):
        issues = _quality_issues(profile, content, payload)
        if not issues:
            converged = True
            rounds.append({"round": round_idx, "issues": [], "status": "converged"})
            break

        evidence_requests = _build_evidence_requests(issues)
        round_item: Dict[str, Any] = {
            "round": round_idx,
            "issues": issues,
            "evidence_requests": evidence_requests,
            "status": "needs_evidence",
        }

        if profile_supp:
            round_item["rpa_supplement_received"] = True
            if profile_supp.get("adjusted_confidence") is not None:
                profile["confidence"] = float(profile_supp["adjusted_confidence"])
        if content_supp:
            round_item["bca_supplement_received"] = True
            if content_supp.get("fallback_strategy"):
                content.setdefault("counter_proposal", {"fallback_strategy": content_supp.get("fallback_strategy")})
            if content_supp.get("weight_suggestion") and content.get("weight_suggestion") is None:
                content["weight_suggestion"] = content_supp.get("weight_suggestion")
            if content_supp.get("coverage_report") and content.get("coverage_report") is None:
                content["coverage_report"] = content_supp.get("coverage_report")

        rounds.append(round_item)

        if round_idx >= max_rounds:
            fallback_applied = True
            break

    confidence = float(profile.get("confidence") or 0.2)
    divergence = float(content.get("divergence_score") or 0.5)
    strategy_hint = str(profile.get("strategy_suggestion") or "balanced")
    context_type = _context_type(confidence, divergence)

    chosen_action, arm_records = _ucb_pick(context_type, confidence, divergence, strategy_hint)
    decision = _decision_payload(chosen_action, confidence, divergence)

    if fallback_applied and not converged:
        chosen_action = "conservative"
        decision = _decision_payload("conservative", confidence, divergence)

    result = {
        "performative": "inform",
        "action": "arbitration_result",
        "context_type": context_type,
        "chosen_action": chosen_action,
        "quality_rounds": rounds,
        "converged": converged,
        "fallback_applied": fallback_applied,
        "arm_records": arm_records,
        "final_weights": {
            "ann_weight": decision["ann_weight"],
            "cf_weight": decision["cf_weight"],
        },
        "score_weights": decision["score_weights"],
        "mmr_lambda": decision["mmr_lambda"],
        "strategy": decision["strategy"],
        "min_coverage": 0.2,
        "confidence_penalty_threshold": 0.6,
    }
    return result


async def _handle_feedback_inform(payload: Dict[str, Any]) -> Dict[str, Any]:
    context_type = str(payload.get("context_type") or "low_conf_high_div")
    action = str(payload.get("arm_action") or payload.get("action_name") or payload.get("action") or "balanced")
    reward = float(payload.get("reward") or 0.0)
    updated = ARM_STORE.update_reward(context_type, action, reward)
    return {
        "performative": "inform",
        "action": "reward_update_applied",
        "context_type": context_type,
        "arm_action": action,
        "reward": reward,
        "updated_record": updated,
    }


async def _handle_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = _extract_action(payload)
    if action in {"feedback.reward", "fa.reward", "update_reward"}:
        return await _handle_feedback_inform(payload)
    return await _arbitrate(payload)


def _fail_task(task_id: str, reason: str) -> Task:
    TaskManager.update_task_status(task_id, TaskState.Failed, data_items=[TextDataItem(text=reason)])
    return TaskManager.get_task(task_id)


def _complete_task(task_id: str, result: Dict[str, Any]) -> Task:
    product = Product(
        id=str(uuid.uuid4()),
        name="arbitration-result",
        description="RDA arbitration output",
        dataItems=[
            StructuredDataItem(data=result),
            TextDataItem(text="arbitration complete"),
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
        start = time.perf_counter()
        result = await _handle_payload(payload)
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
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
    # Inbound mention/inform handler for Feedback Agent reward updates.
    mentions = getattr(message, "mentions", None)
    if isinstance(mentions, list) and AGENT_ID in mentions:
        performative = str(payload.get("performative") or "").strip().lower()
        if performative == "inform":
            payload["action"] = "feedback.reward"

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
    # Catch-all notification-style handler for autonomous inform payloads.
    if task is None:
        task = TaskManager.create_task(message, initial_state=TaskState.Working)
    payload = _parse_payload(message)
    performative = str(payload.get("performative") or "").strip().lower()
    if performative == "inform":
        payload["action"] = "feedback.reward"
        result = await _handle_payload(payload)
        result["agent_id"] = AGENT_ID
        return _complete_task(task.id, result)
    return task


handlers = CommandHandlers(
    on_start=handle_start,
    on_continue=handle_continue,
    on_cancel=handle_cancel,
    on_message=handle_message,
)
add_aip_rpc_router(app, AIP_ENDPOINT, handlers)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("RECOMMENDATION_DECISION_HOST", "0.0.0.0")
    port = int(os.getenv("RECOMMENDATION_DECISION_PORT", str(CFG.port)))
    uvicorn.run(app, host=host, port=port)
