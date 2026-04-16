from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from acps_aip.aip_base_model import Message, Product, StructuredDataItem, Task, TaskState, TextDataItem
from acps_aip.aip_rpc_server import CommandHandlers, TaskManager, add_aip_rpc_router
from base import get_agent_logger, register_acs_route
from partners.online.recommendation_engine_agent.modules.explanation import assess_confidence, generate_rationale
from partners.online.recommendation_engine_agent.modules.ranking import rerank_round2, score_round1
from partners.online.recommendation_engine_agent.modules.recall import recall_candidates

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

load_dotenv()

ACS_PATH = _CURRENT_DIR / "acs.json"
CONFIG_PATH = _CURRENT_DIR / "config.toml"
PROMPTS_PATH = _CURRENT_DIR / "prompts.toml"

AGENT_ID = os.getenv("RECOMMENDATION_ENGINE_AGENT_ID", "recommendation_engine_agent_001")
AIP_ENDPOINT = os.getenv("RECOMMENDATION_ENGINE_AGENT_ENDPOINT", "/recommendation-engine/rpc")
LOG_LEVEL = os.getenv("RECOMMENDATION_ENGINE_AGENT_LOG_LEVEL", "INFO").upper()

logger = get_agent_logger("partner.recommendation_engine_agent", "RECOMMENDATION_ENGINE_AGENT_LOG_LEVEL", LOG_LEVEL)


@dataclass
class AgentConfig:
    port: int = 8214
    faiss_index_path: str = field(init=False)
    faiss_index_meta_path: str = field(init=False)
    book_retrieval_dataset_path: str = field(init=False)
    cf_item_factors_path: str = field(init=False)
    cf_user_factors_path: str = field(init=False)
    cf_book_index_path: str = field(init=False)
    cf_user_index_path: str = field(init=False)
    als_model_path: str = field(init=False)
    hnswlib_path: str = field(init=False)
    llm_model: str = field(init=False)
    llm_temperature: float = field(init=False)
    llm_max_tokens: int = field(init=False)
    confidence_penalty_threshold: float = field(init=False)
    penalty_multiplier: float = field(init=False)
    default_mmr_lambda: float = field(init=False)
    default_min_coverage: float = field(init=False)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _missing_config_error(section: str, key: str) -> RuntimeError:
    return RuntimeError(f"Missing required config key: [{section}].{key} — set it in config.toml")


def _require_section(data: Dict[str, Any], section: str, required_key: str) -> Dict[str, Any]:
    section_data = data.get(section)
    if not isinstance(section_data, dict):
        raise _missing_config_error(section, required_key)
    return section_data


def _require_value(section_data: Dict[str, Any], section: str, key: str) -> Any:
    if key not in section_data:
        raise _missing_config_error(section, key)
    value = section_data.get(key)
    if value is None:
        raise _missing_config_error(section, key)
    if isinstance(value, str) and not value.strip():
        raise _missing_config_error(section, key)
    return value


def _optional_str(section_data: Dict[str, Any], key: str, default: str = "") -> str:
    value = section_data.get(key)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _load_config() -> AgentConfig:
    cfg = AgentConfig()
    if not tomllib:
        raise RuntimeError("Missing required TOML parser support for config.toml")
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"Missing required config file: {CONFIG_PATH}")
    try:
        data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Failed to parse config.toml: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Invalid config.toml format: expected a TOML table at the top level")

    try:
        server = data.get("server") if isinstance(data, dict) else {}
        if isinstance(server, dict) and server.get("port") is not None:
            cfg.port = int(server["port"])
    except Exception:
        pass

    index = _require_section(data, "index", "FAISS_INDEX_PATH")
    cfg.faiss_index_path = str(_require_value(index, "index", "FAISS_INDEX_PATH"))
    cfg.faiss_index_meta_path = _optional_str(index, "FAISS_INDEX_META_PATH", str(os.getenv("FAISS_INDEX_META_PATH") or ""))
    cfg.book_retrieval_dataset_path = _optional_str(
        index,
        "BOOK_RETRIEVAL_DATASET_PATH",
        str(os.getenv("BOOK_RETRIEVAL_DATASET_PATH") or ""),
    )
    cfg.cf_item_factors_path = _optional_str(index, "CF_ITEM_FACTORS_PATH", str(os.getenv("CF_ITEM_FACTORS_PATH") or ""))
    cfg.cf_user_factors_path = _optional_str(index, "CF_USER_FACTORS_PATH", str(os.getenv("CF_USER_FACTORS_PATH") or ""))
    cfg.cf_book_index_path = _optional_str(index, "CF_BOOK_INDEX_PATH", str(os.getenv("CF_BOOK_INDEX_PATH") or ""))
    cfg.cf_user_index_path = _optional_str(index, "CF_USER_INDEX_PATH", str(os.getenv("CF_USER_INDEX_PATH") or ""))
    cfg.als_model_path = str(_require_value(index, "index", "ALS_MODEL_PATH"))
    cfg.hnswlib_path = str(_require_value(index, "index", "HNSWLIB_PATH"))
    logger.info(
        "event=config_loaded section=index faiss=%s faiss_meta=%s corpus=%s cf_item=%s cf_user=%s cf_book_index=%s cf_user_index=%s als=%s hnswlib=%s",
        cfg.faiss_index_path,
        cfg.faiss_index_meta_path,
        cfg.book_retrieval_dataset_path,
        cfg.cf_item_factors_path,
        cfg.cf_user_factors_path,
        cfg.cf_book_index_path,
        cfg.cf_user_index_path,
        cfg.als_model_path,
        cfg.hnswlib_path,
    )

    llm = _require_section(data, "llm", "model")
    configured_llm_model = str(_require_value(llm, "llm", "model"))
    cfg.llm_model = configured_llm_model
    cfg.llm_temperature = _safe_float(_require_value(llm, "llm", "temperature"))
    cfg.llm_max_tokens = int(_require_value(llm, "llm", "max_tokens"))
    logger.info(
        "event=config_loaded section=llm model=%s temperature=%s max_tokens=%s",
        configured_llm_model,
        cfg.llm_temperature,
        cfg.llm_max_tokens,
    )
    env_llm_model = str(os.getenv("RECOMMENDATION_ENGINE_LLM_MODEL") or "").strip()
    if env_llm_model:
        cfg.llm_model = env_llm_model
        if cfg.llm_model != configured_llm_model:
            logger.info(
                "event=config_override section=llm source=env var=RECOMMENDATION_ENGINE_LLM_MODEL model=%s",
                cfg.llm_model,
            )

    ranking = _require_section(data, "ranking", "CONFIDENCE_PENALTY_THRESHOLD")
    cfg.confidence_penalty_threshold = _safe_float(
        _require_value(ranking, "ranking", "CONFIDENCE_PENALTY_THRESHOLD")
    )
    cfg.penalty_multiplier = _safe_float(_require_value(ranking, "ranking", "PENALTY_MULTIPLIER"))
    cfg.default_mmr_lambda = _safe_float(_require_value(ranking, "ranking", "DEFAULT_MMR_LAMBDA"))
    logger.info(
        "event=config_loaded section=ranking confidence_penalty_threshold=%s penalty_multiplier=%s default_mmr_lambda=%s",
        cfg.confidence_penalty_threshold,
        cfg.penalty_multiplier,
        cfg.default_mmr_lambda,
    )

    quality = _require_section(data, "quality", "DEFAULT_MIN_COVERAGE")
    cfg.default_min_coverage = _safe_float(_require_value(quality, "quality", "DEFAULT_MIN_COVERAGE"))
    logger.info(
        "event=config_loaded section=quality default_min_coverage=%s",
        cfg.default_min_coverage,
    )

    return cfg


def _load_prompts() -> Dict[str, str]:
    defaults = {
        "main": "",
        "fallback": (
            'Based on your reading history and the characteristics of this book, '
            'we believe "{title}" by {author} may be of interest to you.'
        ),
    }
    if not tomllib or not PROMPTS_PATH.exists():
        return defaults
    try:
        data = tomllib.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
        em = data.get("explanation_main") if isinstance(data, dict) else {}
        ef = data.get("explanation_fallback") if isinstance(data, dict) else {}
        if isinstance(em, dict) and em.get("template"):
            defaults["main"] = str(em.get("template"))
        if isinstance(ef, dict) and ef.get("template"):
            defaults["fallback"] = str(ef.get("template"))
    except Exception as exc:
        logger.warning("event=prompt_parse_failed error=%s", exc)
    return defaults


CFG = _load_config()
PROMPTS = _load_prompts()

app = FastAPI(
    title="Recommendation Engine Agent (Phase 3)",
    description="Reactive execution partner with Recall, Ranking, and Explanation modules.",
)
register_acs_route(app, str(ACS_PATH))


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
    return str(payload.get("action") or payload.get("skill") or "engine.dispatch").strip().lower()


def _extract_required_evidence_types(payload: Dict[str, Any]) -> List[str]:
    raw = payload.get("required_evidence_types")
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _coverage(candidates: List[Dict[str, Any]], required_evidence_types: List[str]) -> float:
    if not required_evidence_types:
        return 1.0
    covered = 0
    for row in candidates:
        types = row.get("evidence_types") if isinstance(row.get("evidence_types"), list) else []
        if set(required_evidence_types).issubset({str(x) for x in types}):
            covered += 1
    if not candidates:
        return 0.0
    return covered / max(len(candidates), 1)


async def _dispatch(payload: Dict[str, Any]) -> Dict[str, Any]:
    dispatch_start = time.perf_counter()

    score_weights = payload.get("score_weights") if isinstance(payload.get("score_weights"), dict) else {}
    mmr_lambda = _safe_float(payload.get("mmr_lambda"), CFG.default_mmr_lambda)
    threshold = _safe_float(payload.get("confidence_penalty_threshold"), CFG.confidence_penalty_threshold)
    min_coverage = _safe_float(payload.get("min_coverage"), CFG.default_min_coverage)
    required_evidence_types = _extract_required_evidence_types(payload)
    top_k = max(1, int(payload.get("top_k") or 10))

    recall_cfg = {
        "faiss_index_path": CFG.faiss_index_path,
        "faiss_index_meta_path": CFG.faiss_index_meta_path,
        "book_retrieval_dataset_path": CFG.book_retrieval_dataset_path,
        "cf_item_factors_path": CFG.cf_item_factors_path,
        "cf_user_factors_path": CFG.cf_user_factors_path,
        "cf_book_index_path": CFG.cf_book_index_path,
        "cf_user_index_path": CFG.cf_user_index_path,
        "als_model_path": CFG.als_model_path,
        "hnswlib_path": CFG.hnswlib_path,
        "ann_ef_search": 100,
        "ann_top_k": 200,
        "cf_top_k": 100,
        "cf_sim_users": 50,
    }
    recalled, recall_meta = recall_candidates(payload, recall_cfg)

    cold_start = bool(payload.get("cold_start", False))

    preliminary, round1_meta = score_round1(
        recalled,
        score_weights=score_weights,
        top_k=max(20, top_k * 10),
        cold_start=cold_start,
    )
    confidence_list = assess_confidence(preliminary)

    final_ranked, round2_meta = rerank_round2(
        preliminary_list=preliminary,
        confidence_list=confidence_list,
        mmr_lambda=mmr_lambda,
        confidence_penalty_threshold=threshold,
        penalty_multiplier=CFG.penalty_multiplier,
        cold_start=cold_start,
        top_k=top_k,
    )

    explanations = await generate_rationale(
        final_list=final_ranked,
        payload=payload,
        prompts=PROMPTS,
        llm_model=CFG.llm_model,
        llm_temperature=CFG.llm_temperature,
        llm_max_tokens=CFG.llm_max_tokens,
    )
    explanation_by_id = {str(x.get("book_id")): x for x in explanations}

    recommendations: List[Dict[str, Any]] = []
    for row in final_ranked:
        book_id = str(row.get("book_id") or "")
        rec = {
            "rank": int(row.get("rank") or 0),
            "book_id": book_id,
            "title": row.get("title"),
            "genres": row.get("genres") if isinstance(row.get("genres"), list) else [],
            "novelty_score": _safe_float(row.get("novelty_score"), 0.0),
            "diversity_score": _safe_float(row.get("diversity_score"), 0.0),
            "score_total": _safe_float(row.get("score_total"), 0.0),
            "recall_source": row.get("recall_source"),
            "score_parts": row.get("score_parts") or {},
            "justification": (explanation_by_id.get(book_id) or {}).get("justification", ""),
        }
        recommendations.append(rec)

    observed_coverage = _coverage(preliminary, required_evidence_types)
    quality_flags = {
        "coverage_ok": observed_coverage >= min_coverage,
        "coverage": round(observed_coverage, 6),
        "required_evidence_types": required_evidence_types,
        "min_coverage": min_coverage,
    }

    engine_meta = {
        "modules": {
            "recall": recall_meta,
            "ranking_round1": round1_meta,
            "ranking_round2": round2_meta,
            "explanation": {
                "llm_model": CFG.llm_model,
                "llm_enabled": bool(str(os.getenv("OPENAI_API_KEY") or "").strip()),
                "items": len(explanations),
            },
        },
        "quality": quality_flags,
        "latency_ms": round((time.perf_counter() - dispatch_start) * 1000, 3),
    }

    return {
        "performative": "inform",
        "action": "engine.result",
        "recommendations": recommendations,
        "explanations": explanations,
        "engine_meta": engine_meta,
    }


def _retrain_cf() -> Dict[str, Any]:
    script_path = _PROJECT_ROOT / "scripts" / "build_cf_model.py"
    if not script_path.exists():
        return {
            "performative": "inform",
            "action": "engine.retrain_cf",
            "status": "failed",
            "reason": f"script_not_found:{script_path}",
        }

    cmd = [sys.executable, str(script_path)]
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_PROJECT_ROOT), timeout=300)
        ok = proc.returncode == 0
        summary = str(proc.stdout or proc.stderr or "").strip()
        parsed_summary = None
        if summary:
            try:
                parsed_summary = json.loads(summary.splitlines()[-1])
            except Exception:
                parsed_summary = None

        return {
            "performative": "inform",
            "action": "engine.retrain_cf",
            "status": "completed" if ok else "failed",
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "returncode": proc.returncode,
            "summary": parsed_summary,
            "stdout_tail": "\n".join((proc.stdout or "").splitlines()[-5:]),
            "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-5:]),
        }
    except Exception as exc:
        return {
            "performative": "inform",
            "action": "engine.retrain_cf",
            "status": "failed",
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "reason": str(exc),
        }


async def _handle_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = _extract_action(payload)
    trigger = str(payload.get("trigger") or "").strip().lower()

    if action in {"engine.retrain_cf", "feedback.retrain_cf", "retrain_cf"} or trigger == "retrain_cf":
        return _retrain_cf()
    return await _dispatch(payload)


def _fail_task(task_id: str, reason: str) -> Task:
    TaskManager.update_task_status(task_id, TaskState.Failed, data_items=[TextDataItem(text=reason)])
    return TaskManager.get_task(task_id)


def _complete_task(task_id: str, result: Dict[str, Any]) -> Task:
    product = Product(
        id=str(uuid.uuid4()),
        name="engine-result",
        description="Recommendation engine execution output",
        dataItems=[StructuredDataItem(data=result), TextDataItem(text="engine execution complete")],
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

    # Inbound autonomous mention handler: Feedback Agent may send inform trigger retrain_cf.
    mentions = getattr(message, "mentions", None)
    if isinstance(mentions, list) and AGENT_ID in mentions:
        performative = str(payload.get("performative") or "").strip().lower()
        if performative == "inform" and str(payload.get("trigger") or "").strip().lower() == "retrain_cf":
            payload["action"] = "engine.retrain_cf"

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
    trigger = str(payload.get("trigger") or "").strip().lower()
    if performative == "inform" and trigger == "retrain_cf":
        payload["action"] = "engine.retrain_cf"
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

    host = os.getenv("RECOMMENDATION_ENGINE_HOST", "0.0.0.0")
    port = int(os.getenv("RECOMMENDATION_ENGINE_PORT", str(CFG.port)))
    uvicorn.run(app, host=host, port=port)
