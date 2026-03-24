import os
import sys
import json
import uuid
import asyncio
import re
import hashlib
from collections import OrderedDict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from jsonschema import Draft202012Validator

_CURRENT_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_DEMO_HTML_PATH = Path(_PROJECT_ROOT) / "web_demo" / "index.html"
_BENCHMARK_SUMMARY_PATH = Path(_PROJECT_ROOT) / "scripts" / "phase4_benchmark_summary.json"
_CONTRACT_SCHEMA_DIR = Path(_PROJECT_ROOT) / "docs" / "contracts"

from base import get_agent_logger, call_openai_chat, register_acs_route
from services.evaluation_metrics import compute_recommendation_metrics, build_ablation_report
from services.book_retrieval import load_books, retrieve_books_by_query, get_active_retrieval_corpus_info
from services.model_backends import load_cf_item_vectors
from services.user_profile_store import profile_store
from agents.reader_profile_agent import profile_agent as reader_profile
from agents.book_content_agent import book_content_agent as book_content
from agents.rec_ranking_agent import rec_ranking_agent as rec_ranking

load_dotenv()

LEADER_ID = os.getenv("READING_CONCIERGE_ID", "reading_concierge_001")
LOG_LEVEL = os.getenv("READING_CONCIERGE_LOG_LEVEL", "INFO").upper()
DISCOVERY_BASE_URL = os.getenv("READING_DISCOVERY_BASE_URL")
REGISTRY_BASE_URL = os.getenv("READING_REGISTRY_BASE_URL")
PARTNER_MODE = os.getenv("READING_PARTNER_MODE", "auto").lower()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "qwen-plus")
BOOK_RETRIEVAL_TOP_K = int(os.getenv("BOOK_RETRIEVAL_TOP_K", "8"))
BOOK_RETRIEVAL_CANDIDATE_POOL = int(os.getenv("BOOK_RETRIEVAL_CANDIDATE_POOL", "30"))
READING_CONCIERGE_BASE_URL = str(os.getenv("READING_CONCIERGE_BASE_URL", "http://localhost:8100")).rstrip("/")

_REMOTE_ENDPOINT_ENV = {
    "profile": "READER_PROFILE_RPC_URL",
    "content": "BOOK_CONTENT_RPC_URL",
    "ranking": "REC_RANKING_RPC_URL",
}

_DISCOVERY_QUERY = {
    "profile": "reader profile analysis agent",
    "content": "book content analysis agent",
    "ranking": "recommendation decision ranking agent",
}

_PARTNER_SKILL_HINTS = {
    "profile": ["profile.extract", "preference.embedding", "sentiment.analysis"],
    "content": ["book.vectorize", "kg.enrich", "tag.extract"],
    "ranking": ["ranking.svd", "ranking.multifactor", "explanation.llm"],
}

logger = get_agent_logger("agent.reading_concierge", "READING_CONCIERGE_LOG_LEVEL", LOG_LEVEL)

app = FastAPI(
    title="Reading Concierge",
    description="Coordinator that orchestrates profile, content, and ranking agents.",
)

_ACS_JSON_PATH = str(Path(_CURRENT_DIR) / "reading_concierge.json")
register_acs_route(
    app,
    _ACS_JSON_PATH,
    endpoint_override_url=f"{READING_CONCIERGE_BASE_URL}/user_api",
)


@app.on_event("startup")
async def _startup_runtime_diagnostics() -> None:
    retrieval_info = get_active_retrieval_corpus_info()
    logger.info(
        "event=retrieval_corpus_active path=%s exists=%s selection_source=%s",
        retrieval_info.get("path"),
        retrieval_info.get("exists"),
        retrieval_info.get("selection_source"),
    )

MAX_SESSIONS = int(os.getenv("READING_CONCIERGE_MAX_SESSIONS", "200"))
sessions: OrderedDict[str, Dict[str, Any]] = OrderedDict()
_CONTRACT_VALIDATORS: Dict[str, Draft202012Validator] = {}


def _get_contract_validator(schema_name: str) -> Optional[Draft202012Validator]:
    existing = _CONTRACT_VALIDATORS.get(schema_name)
    if existing is not None:
        return existing
    schema_path = _CONTRACT_SCHEMA_DIR / schema_name
    if not schema_path.exists():
        logger.warning("event=contract_schema_missing schema=%s", schema_name)
        return None
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
    except Exception as exc:
        logger.warning("event=contract_schema_load_failed schema=%s error=%s", schema_name, exc)
        return None
    _CONTRACT_VALIDATORS[schema_name] = validator
    return validator


def _validate_contract_payload(schema_name: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
    validator = _get_contract_validator(schema_name)
    if validator is None:
        return False, f"schema_unavailable:{schema_name}"
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    if errors:
        return False, "; ".join(error.message for error in errors[:3])
    return True, "ok"


def _lru_session_get(session_id: str) -> Dict[str, Any]:
    """Return an existing session (moving it to most-recent) or create a new one.

    When the cache exceeds *MAX_SESSIONS* entries the oldest session is evicted.
    """
    if session_id in sessions:
        sessions.move_to_end(session_id)
        return sessions[session_id]
    # Evict oldest if at capacity
    while len(sessions) >= MAX_SESSIONS:
        sessions.popitem(last=False)
    new_session: Dict[str, Any] = {
        "messages": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_partner_results": {},
    }
    sessions[session_id] = new_session
    return new_session


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


def _evaluation_from_response(req: UserRequest, ranking_outputs: Dict[str, Any]) -> Dict[str, Any]:
    recommendations = ranking_outputs.get("ranking") or []
    metric_snapshot = ranking_outputs.get("metric_snapshot") or {}
    constraints = req.constraints or {}

    def _num(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    ground_truth_ids = constraints.get("ground_truth_ids") or []
    if not isinstance(ground_truth_ids, list):
        ground_truth_ids = []

    if ground_truth_ids:
        eval_metrics = compute_recommendation_metrics(
            recommendations=recommendations,
            ground_truth_ids=ground_truth_ids,
            k=int(constraints.get("top_k") or len(recommendations) or 1),
            avg_diversity=metric_snapshot.get("avg_diversity", 0.0),
            avg_novelty=metric_snapshot.get("avg_novelty", 0.0),
        )
    else:
        eval_metrics = {
            "precision_at_k": None,
            "recall_at_k": None,
            "ndcg_at_k": None,
            "diversity": round(_num(metric_snapshot.get("avg_diversity", 0.0)), 4),
            "novelty": round(_num(metric_snapshot.get("avg_novelty", 0.0)), 4),
        }

    report = {"metrics": eval_metrics}
    if constraints.get("ablation") is True:
        report["ablation"] = build_ablation_report(
            recommendations=recommendations,
            scoring_weights=ranking_outputs.get("scoring_weights") or {},
        )
    return report


def _extract_jsonrpc_endpoint(agent_info: Dict[str, Any]) -> Optional[str]:
    endpoints = (
        agent_info.get("endPoints")
        or agent_info.get("endpoints")
        or agent_info.get("endpoint")
        or []
    )
    if isinstance(endpoints, dict):
        endpoints = list(endpoints.values())
    if not isinstance(endpoints, list):
        return None

    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        transport = str(ep.get("transport", "")).upper()
        if transport == "JSONRPC":
            return ep.get("url") or ep.get("URI") or ep.get("endpoint")
    return None


async def _discover_partner_endpoint(partner_key: str) -> Optional[str]:
    if not DISCOVERY_BASE_URL:
        return None
    query = _DISCOVERY_QUERY.get(partner_key)
    if not query:
        return None

    url = DISCOVERY_BASE_URL.rstrip("/") + "/api/discovery/"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={"query": query, "limit": 1})
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning(
            "event=partner_discovery_failed partner=%s error=%s",
            partner_key,
            exc,
        )
        return None

    agents = payload.get("agents") if isinstance(payload, dict) else None
    if not agents:
        return None
    first = agents[0]
    if not isinstance(first, dict):
        return None
    acs = first.get("acs") if "acs" in first else first
    if isinstance(acs, str):
        try:
            acs = json.loads(acs)
        except json.JSONDecodeError:
            return None
    if not isinstance(acs, dict):
        return None
    return _extract_jsonrpc_endpoint(acs)


async def _resolve_partner_from_registry(partner_key: str) -> Optional[str]:
    if not REGISTRY_BASE_URL:
        return None
    url = REGISTRY_BASE_URL.rstrip("/") + "/api/registry/resolve"
    payload = {
        "partner": partner_key,
        "skills": _PARTNER_SKILL_HINTS.get(partner_key, []),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        logger.warning(
            "event=registry_resolution_failed partner=%s error=%s",
            partner_key,
            exc,
        )
        return None

    if not isinstance(body, dict):
        return None
    endpoint = body.get("rpc_url") or body.get("endpoint")
    if endpoint:
        return str(endpoint)
    agent_info = body.get("agent") or {}
    if isinstance(agent_info, dict):
        return _extract_jsonrpc_endpoint(agent_info)
    return None


async def _resolve_remote_partner_url(partner_key: str) -> Optional[str]:
    remote_env_url = os.getenv(_REMOTE_ENDPOINT_ENV[partner_key])
    discovered_url = await _discover_partner_endpoint(partner_key) if PARTNER_MODE in {"auto", "remote"} else None
    registry_url = await _resolve_partner_from_registry(partner_key) if PARTNER_MODE in {"auto", "remote"} else None
    return remote_env_url or discovered_url or registry_url


def _validate_partner_outputs(partner_key: str, state: str, result: Dict[str, Any]) -> Tuple[bool, str]:
    if state != "completed":
        return False, f"state_not_completed:{state}"

    if partner_key == "profile":
        vector = result.get("preference_vector") if isinstance(result, dict) else None
        if not isinstance(vector, dict) or not vector:
            return False, "missing_preference_vector"
        return True, "ok"

    if partner_key == "content":
        outputs = result.get("outputs") if isinstance(result, dict) else None
        vectors = outputs.get("content_vectors") if isinstance(outputs, dict) else None
        if not isinstance(vectors, list) or not vectors:
            return False, "missing_content_vectors"
        return True, "ok"

    if partner_key == "ranking":
        outputs = result.get("outputs") if isinstance(result, dict) else None
        ranking = outputs.get("ranking") if isinstance(outputs, dict) else None
        if not isinstance(ranking, list):
            return False, "missing_ranking"
        return True, "ok"

    return True, "ok"


def _resolve_local_partner(partner_key: str) -> Dict[str, Any]:
    mapping = {
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
        "ranking": {
            "agent_id": rec_ranking.AGENT_ID,
            "app": rec_ranking.app,
            "endpoint": "/rec-ranking/rpc",
        },
    }
    return mapping[partner_key]


def _mk_rpc_payload(task_id: str, payload: Dict[str, Any], command: str = "start") -> Dict[str, Any]:
    sent_at = datetime.now(timezone.utc).isoformat()
    message = {
        "type": "message",
        "id": str(uuid.uuid4()),
        "sentAt": sent_at,
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


async def _invoke_agent_rpc(
    agent_app: FastAPI,
    endpoint: str,
    payload: Dict[str, Any],
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    task_id = task_id or f"task-{uuid.uuid4()}"
    rpc_body = _mk_rpc_payload(task_id, payload)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=agent_app),
        base_url="http://agent",
        timeout=30,
    ) as client:
        response = await client.post(endpoint, json=rpc_body)
    response.raise_for_status()
    return response.json()


async def _invoke_remote_rpc(
    rpc_url: str,
    payload: Dict[str, Any],
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    task_id = task_id or f"task-{uuid.uuid4()}"
    rpc_body = _mk_rpc_payload(task_id, payload)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(rpc_url, json=rpc_body)
    response.raise_for_status()
    return response.json()


def _mk_failed_rpc_response(reason: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "result": {
            "status": {
                "state": "failed",
                "reason": reason,
            },
            "products": [],
        },
    }


async def _invoke_partner_with_fallback(
    partner_key: str,
    payload: Dict[str, Any],
    strict_remote_validation: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    local = _resolve_local_partner(partner_key)
    remote_url = await _resolve_remote_partner_url(partner_key)

    if PARTNER_MODE in {"auto", "remote"} and remote_url:
        try:
            response = await _invoke_remote_rpc(remote_url, payload)
            return response, {
                "route": "remote",
                "rpc_url": remote_url,
                "fallback": False,
                "remote_attempted": True,
                "route_outcome": "remote_success",
            }
        except Exception as exc:
            logger.warning(
                "event=partner_remote_failed partner=%s rpc_url=%s error=%s",
                partner_key,
                remote_url,
                exc,
            )
            if strict_remote_validation:
                return _mk_failed_rpc_response("remote_failure_strict"), {
                    "route": "remote",
                    "rpc_url": remote_url,
                    "fallback": False,
                    "remote_attempted": True,
                    "route_outcome": "remote_failed_strict",
                }
            if PARTNER_MODE == "remote":
                # In strict remote mode, still provide local fallback as safety per policy requirement.
                logger.info("event=partner_remote_fallback_local partner=%s", partner_key)

    if strict_remote_validation and PARTNER_MODE in {"auto", "remote"} and not remote_url:
        return _mk_failed_rpc_response("remote_unavailable_strict"), {
            "route": "none",
            "rpc_url": None,
            "fallback": False,
            "remote_attempted": False,
            "route_outcome": "remote_unavailable_strict",
        }

    response = await _invoke_agent_rpc(local["app"], local["endpoint"], payload)
    if remote_url:
        return response, {
            "route": "local",
            "rpc_url": None,
            "fallback": True,
            "remote_attempted": True,
            "route_outcome": "remote_failed_local_fallback",
        }

    return response, {
        "route": "local",
        "rpc_url": None,
        "fallback": False,
        "remote_attempted": False,
        "route_outcome": "local_only",
    }


def _task_state(rpc_response: Dict[str, Any]) -> str:
    return (
        ((rpc_response or {}).get("result") or {})
        .get("status", {})
        .get("state", "unknown")
    )


def _extract_structured_result(rpc_response: Dict[str, Any]) -> Dict[str, Any]:
    products = ((rpc_response or {}).get("result") or {}).get("products") or []
    if not products:
        return {}
    data_items = products[0].get("dataItems") or []
    for item in data_items:
        if item.get("type") == "data" and isinstance(item.get("data"), dict):
            return item["data"]
    return {}


def _try_parse_json(value: str) -> Any:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except Exception:
            return None
    return None


async def _llm_select_book_ids(query: str, candidate_pool: List[Dict[str, Any]], top_k: int) -> List[str]:
    if not candidate_pool:
        return []

    candidate_lines: List[str] = []
    for row in candidate_pool:
        bid = str(row.get("book_id") or "")
        title = str(row.get("title") or "")
        author = str(row.get("author") or "")
        genres = ", ".join(str(g) for g in (row.get("genres") or []))
        desc = str(row.get("description") or "")[:220]
        candidate_lines.append(
            f"- book_id={bid}; title={title}; author={author}; genres={genres}; description={desc}"
        )

    prompt = (
        "You are a book recommendation selector.\n"
        f"User query: {query}\n"
        f"Choose up to {top_k} best-matching book_ids ONLY from the candidate list below.\n"
        "Return strict JSON object with this schema: "
        '{"book_ids": ["id1", "id2", ...]} and do not include any extra text.\n\n'
        "Candidates:\n"
        + "\n".join(candidate_lines)
    )
    messages = [
        {"role": "system", "content": "Return valid JSON only."},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = await call_openai_chat(
            messages,
            model=OPENAI_MODEL,
            temperature=0.2,
            max_tokens=400,
        )
    except Exception:
        return []

    parsed = _try_parse_json(raw)
    if not isinstance(parsed, dict):
        return []

    raw_ids = parsed.get("book_ids")
    if not isinstance(raw_ids, list):
        return []

    valid_ids = {str(row.get("book_id") or "") for row in candidate_pool}
    selected: List[str] = []
    seen: set[str] = set()
    for item in raw_ids:
        bid = str(item or "").strip()
        if not bid or bid not in valid_ids or bid in seen:
            continue
        selected.append(bid)
        seen.add(bid)
        if len(selected) >= top_k:
            break
    return selected


async def _derive_books_from_query(query: str, candidate_ids: List[str]) -> List[Dict[str, Any]]:
    books = load_books()
    if not books:
        return []

    if candidate_ids:
        wanted = {str(cid) for cid in candidate_ids if str(cid).strip()}
        return [row for row in books if str(row.get("book_id") or "") in wanted]

    if not query.strip():
        return []

    pool_target = max(BOOK_RETRIEVAL_TOP_K, BOOK_RETRIEVAL_CANDIDATE_POOL)
    retrieval_pool = min(len(books), max(pool_target, pool_target * 4))

    lexical = retrieve_books_by_query(
        query=query,
        books=books,
        top_k=retrieval_pool,
    )
    if not lexical:
        return []

    cf_vectors = load_cf_item_vectors()
    if cf_vectors:
        covered: List[Dict[str, Any]] = []
        uncovered: List[Dict[str, Any]] = []
        for row in lexical:
            bid = str(row.get("book_id") or "")
            if bid and bid in cf_vectors:
                covered.append(row)
            else:
                uncovered.append(row)
        candidate_pool = (covered + uncovered)[:pool_target]
    else:
        candidate_pool = lexical[:pool_target]

    selected_ids = await _llm_select_book_ids(
        query=query,
        candidate_pool=candidate_pool,
        top_k=BOOK_RETRIEVAL_TOP_K,
    )

    if not selected_ids:
        return candidate_pool[:BOOK_RETRIEVAL_TOP_K]

    by_id = {str(row.get("book_id") or ""): row for row in candidate_pool}
    selected_books = [by_id[bid] for bid in selected_ids if bid in by_id]
    return selected_books[:BOOK_RETRIEVAL_TOP_K]


def _detect_scenario(req: UserRequest) -> str:
    requested = str(req.constraints.get("scenario") or "").lower()
    if requested in {"cold", "warm", "explore"}:
        return requested
    if req.constraints.get("explore") is True:
        return "explore"
    if not req.history and not req.reviews:
        return "cold"
    return "warm"


def _debug_payload_override_enabled(req: UserRequest) -> bool:
    return bool((req.constraints or {}).get("debug_payload_override", False))


def _normalize_user_id(req: UserRequest, session_id: str, *, allow_anonymous: bool) -> str:
    uid = str(req.user_id or "").strip()
    if uid:
        return uid
    if allow_anonymous:
        return f"anon-{session_id}"
    return ""


def _hydrate_request_context(req: UserRequest, session_id: str, *, allow_anonymous: bool) -> None:
    req.user_id = _normalize_user_id(req, session_id, allow_anonymous=allow_anonymous)
    if not req.user_id:
        raise ValueError("user_id is required for production /user_api requests")
    persisted = profile_store.get_user_context(req.user_id)

    hydrated_profile = persisted.get("user_profile") or {}
    hydrated_profile.setdefault("user_id", req.user_id)
    hydrated_history = persisted.get("history") or []
    hydrated_reviews = persisted.get("reviews") or []

    if _debug_payload_override_enabled(req):
        if req.user_profile:
            hydrated_profile = {**hydrated_profile, **req.user_profile}
        if req.history:
            hydrated_history = req.history
        if req.reviews:
            hydrated_reviews = req.reviews

    req.user_profile = hydrated_profile
    req.history = hydrated_history
    req.reviews = hydrated_reviews


def _build_profile_snapshot(user_id: str, profile_result: Dict[str, Any], req: UserRequest) -> Dict[str, Any]:
    snapshot_from_agent = profile_result.get("profile_snapshot") or {}
    if isinstance(snapshot_from_agent, dict) and snapshot_from_agent:
        snapshot = dict(snapshot_from_agent)
        snapshot["user_id"] = user_id
    else:
        snapshot = {}

    latest_snapshot = profile_store.get_latest_profile(user_id) if user_id else {}
    latest_version = str((latest_snapshot or {}).get("profile_version") or "").strip()

    def _parse_version(raw: str) -> Tuple[str, int]:
        parts = raw.rsplit("-v", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0], int(parts[1])
        return raw, 0

    requested_version = str(
        snapshot.get("profile_version")
        or profile_result.get("profile_version")
        or profile_result.get("embedding_version")
        or "reader_profile_v1"
    )
    req_base, req_idx = _parse_version(requested_version)
    latest_base, latest_idx = _parse_version(latest_version)

    if latest_idx > 0 and (latest_base == req_base or requested_version == "reader_profile_v1"):
        profile_version = f"{latest_base}-v{latest_idx + 1}"
    elif req_idx > 0:
        profile_version = requested_version
    else:
        base = user_id.replace(" ", "_") if user_id else "profile"
        profile_version = f"{base}-v1"

    preference_vector = profile_result.get("preference_vector") or {}
    sentiment_summary = profile_result.get("sentiment_summary") or {"label": "neutral", "score": 0.0}
    intent_keywords = profile_result.get("intent_keywords") or {"keywords": [], "intent_summary": ""}
    diagnostics = profile_result.get("diagnostics") or {}
    generated_at = str(diagnostics.get("generated_at") or datetime.now(timezone.utc).isoformat())

    fallback_snapshot = {
        "user_id": user_id,
        "profile_version": profile_version,
        "generated_at": generated_at,
        "source_event_window": {
            "history_count": len(req.history or []),
            "review_count": len(req.reviews or []),
        },
        "explicit_preferences": {
            "genres": preference_vector.get("genres") or {},
            "themes": preference_vector.get("themes") or {},
            "formats": preference_vector.get("formats") or {},
            "languages": preference_vector.get("languages") or {},
        },
        "implicit_preferences": {
            "intent_keywords": intent_keywords,
            "tones": preference_vector.get("tones") or {},
            "pacing": preference_vector.get("pacing") or {},
            "difficulty": preference_vector.get("difficulty") or {},
        },
        "sentiment_summary": sentiment_summary,
        "feature_vector": preference_vector,
        "cold_start_flag": _detect_scenario(req) == "cold",
        "user_profile": {**(req.user_profile or {}), "user_id": user_id},
    }

    if snapshot:
        merged = {**fallback_snapshot, **snapshot}
        merged["profile_version"] = profile_version
        merged["user_profile"] = {**(req.user_profile or {}), "user_id": user_id}
        return merged
    return fallback_snapshot


def _build_candidate_provenance(req: UserRequest, books: List[Dict[str, Any]]) -> Dict[str, Any]:
    retrieval_info = get_active_retrieval_corpus_info() or {}
    candidate_ids = [str(row.get("book_id") or row.get("id") or "").strip() for row in books]
    candidate_ids = [cid for cid in candidate_ids if cid]
    ids_hash = hashlib.sha256("|".join(candidate_ids).encode("utf-8")).hexdigest() if candidate_ids else ""

    if req.candidate_ids:
        retrieval_rule = "explicit_candidate_ids"
    elif req.books:
        retrieval_rule = "explicit_books_payload"
    else:
        retrieval_rule = "leader_local_retrieval_pipeline"

    dataset_version = str(
        retrieval_info.get("dataset_version")
        or retrieval_info.get("path")
        or retrieval_info.get("selection_source")
        or "unknown"
    )

    return {
        "retrieval_rule": retrieval_rule,
        "dataset_version": dataset_version,
        "filter_parameters": {
            "top_k": req.constraints.get("top_k", BOOK_RETRIEVAL_TOP_K),
            "candidate_pool": BOOK_RETRIEVAL_CANDIDATE_POOL,
            "scenario": req.constraints.get("scenario"),
            "strict_remote_validation": bool(req.constraints.get("strict_remote_validation", False)),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_ids": candidate_ids,
        "candidate_ids_hash": ids_hash,
    }


def _build_candidate_book_set(req: UserRequest, books: List[Dict[str, Any]], provenance: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    for row in books:
        if not isinstance(row, dict):
            continue
        bid = str(row.get("book_id") or row.get("id") or "").strip()
        if not bid:
            continue
        candidates.append(
            {
                "book_id": bid,
                "title": str(row.get("title") or ""),
                "author": str(row.get("author") or ""),
                "genres": row.get("genres") if isinstance(row.get("genres"), list) else [],
                "description": str(row.get("description") or ""),
            }
        )

    return {
        "user_id": req.user_id,
        "query": req.query,
        "candidates": candidates,
        "provenance": {
            "retrieval_rule": provenance.get("retrieval_rule") or "leader_local_retrieval_pipeline",
            "dataset_version": provenance.get("dataset_version") or "unknown",
            "filter_parameters": provenance.get("filter_parameters") or {},
            "generated_at": provenance.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        },
    }


def _build_ranked_recommendation_contract(
    ranking_outputs: Dict[str, Any],
    *,
    scenario_policy: str,
) -> Dict[str, Any]:
    ranking_rows = ranking_outputs.get("ranking") or []
    explanations = ranking_outputs.get("explanations") or []
    explanation_by_id = {
        str(item.get("book_id") or ""): str(item.get("justification") or "").strip()
        for item in explanations
        if isinstance(item, dict)
    }

    def _f(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    normalized: List[Dict[str, Any]] = []
    for idx, row in enumerate(ranking_rows, start=1):
        if not isinstance(row, dict):
            continue
        book_id = str(row.get("book_id") or "").strip()
        if not book_id:
            continue
        score_parts = row.get("score_parts") if isinstance(row.get("score_parts"), dict) else {}
        explanation = explanation_by_id.get(book_id) or str(row.get("reason") or row.get("explanation") or "").strip()
        if not explanation:
            explanation = "Score-based recommendation from collaborative, semantic, knowledge, and diversity factors."
        normalized.append(
            {
                "book_id": book_id,
                "title": str(row.get("title") or ""),
                "score_total": _f(row.get("composite_score") or row.get("score_total")),
                "score_cf": _f(score_parts.get("collaborative") or row.get("score_cf")),
                "score_content": _f(score_parts.get("semantic") or row.get("score_content")),
                "score_kg": _f(score_parts.get("knowledge") or row.get("score_kg")),
                "score_diversity": _f(score_parts.get("diversity") or row.get("score_diversity")),
                "rank_position": int(row.get("rank") or row.get("rank_position") or idx),
                "scenario_policy": scenario_policy,
                "explanation": explanation,
                "explanation_evidence_refs": [
                    "score_parts.collaborative",
                    "score_parts.semantic",
                    "score_parts.knowledge",
                    "score_parts.diversity",
                ],
            }
        )

    return {
        "scenario_policy": scenario_policy,
        "ranking": normalized,
    }


async def _seed_cold_start_history(req: UserRequest, books: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    local_books = books if books is not None else (req.books or await _derive_books_from_query(req.query, req.candidate_ids))
    if not local_books:
        return []

    seeded: List[Dict[str, Any]] = []
    preferred_language = (req.user_profile or {}).get("preferred_language", "unknown")
    for book in local_books[:2]:
        seeded.append(
            {
                "title": str(book.get("title") or book.get("book_id") or "seed_book"),
                "genres": book.get("genres") or [],
                "rating": 3,
                "format": "unknown",
                "language": preferred_language,
            }
        )
    return seeded


def _scenario_policy(req: UserRequest) -> Dict[str, Any]:
    scenario = _detect_scenario(req)

    profile_user = req.user_profile or {}
    profile_history = req.history
    profile_reviews = req.reviews

    if scenario == "cold":
        if not profile_user:
            profile_user = {"segment": "cold_start", "preferred_language": "unknown", "user_id": req.user_id}
    profile_user["user_id"] = req.user_id
    needs_cold_seed = scenario == "cold" and not profile_history and not profile_reviews

    ranking_constraints = {
        "top_k": req.constraints.get("top_k", 5),
        "novelty_threshold": req.constraints.get("novelty_threshold", 0.45),
        "min_new_items": req.constraints.get("min_new_items", 0),
    }
    ranking_weights = req.constraints.get("scoring_weights") or {
        "collaborative": 0.25,
        "semantic": 0.35,
        "knowledge": 0.2,
        "diversity": 0.2,
    }

    if scenario == "explore":
        ranking_constraints["novelty_threshold"] = req.constraints.get("novelty_threshold", 0.5)
        ranking_constraints["min_new_items"] = max(int(ranking_constraints["min_new_items"]), 1)
        ranking_weights = {
            "collaborative": 0.15,
            "semantic": 0.25,
            "knowledge": 0.2,
            "diversity": 0.4,
        }
    elif scenario == "cold":
        ranking_weights = {
            "collaborative": 0.1,
            "semantic": 0.45,
            "knowledge": 0.25,
            "diversity": 0.2,
        }

    return {
        "scenario": scenario,
        "profile": {
            "user_profile": profile_user,
            "history": profile_history,
            "reviews": profile_reviews,
        },
        "needs_cold_seed": needs_cold_seed,
        "ranking_constraints": ranking_constraints,
        "ranking_weights": ranking_weights,
    }


def _build_ranking_candidates(content_outputs: Dict[str, Any], books: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    vectors = content_outputs.get("content_vectors") or []
    tags = content_outputs.get("book_tags") or []
    tags_by_id = {row.get("book_id"): row for row in tags if isinstance(row, dict)}
    books_by_id = {
        str(row.get("book_id") or row.get("id") or ""): row
        for row in (books or [])
        if isinstance(row, dict)
    }

    candidates: List[Dict[str, Any]] = []
    for row in vectors:
        if not isinstance(row, dict):
            continue
        bid = row.get("book_id")
        tag = tags_by_id.get(bid) or {}
        source_book = books_by_id.get(str(bid)) or {}
        title = source_book.get("title") or row.get("title") or bid
        diversity_signal = 0.2 + 0.2 * len(tag.get("diversity_indicators") or [])
        novelty_signal = 0.3 + 0.1 * len(tag.get("topics") or [])
        candidates.append(
            {
                "book_id": bid,
                "title": title,
                "author": source_book.get("author") or "",
                "description": source_book.get("description") or row.get("description") or "",
                "genres": source_book.get("genres") or row.get("genres") or [],
                "topics": tag.get("topics") or [],
                "vector": row.get("vector") or [],
                "kg_signal": min(
                    1.0,
                    max(
                        0.0,
                        float(row["kg_signal"]) if "kg_signal" in row else 0.2,
                    ),
                ),
                "novelty_score": min(1.0, novelty_signal),
                "diversity_score": min(1.0, diversity_signal),
            }
        )
    return candidates


async def _orchestrate_reading_flow(req: UserRequest) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    partner_tasks: Dict[str, Any] = {}
    partner_results: Dict[str, Any] = {}
    policy = _scenario_policy(req)
    scenario = policy["scenario"]
    strict_remote_validation = bool(req.constraints.get("strict_remote_validation", False))
    books = req.books or await _derive_books_from_query(req.query, req.candidate_ids)
    candidate_provenance = _build_candidate_provenance(req, books)
    candidate_book_set = _build_candidate_book_set(req, books, candidate_provenance)
    candidate_valid, candidate_reason = _validate_contract_payload(
        "candidate_book_set.schema.json", candidate_book_set
    )

    if policy.get("needs_cold_seed") and not policy["profile"]["history"]:
        policy["profile"]["history"] = await _seed_cold_start_history(req, books)

    profile_payload = {
        "user_id": req.user_id,
        "user_profile": policy["profile"]["user_profile"],
        "history": policy["profile"]["history"],
        "reviews": policy["profile"]["reviews"],
        "query": req.query,
        "scenario": scenario,
    }
    content_payload = {
        "books": books,
        "candidate_ids": req.candidate_ids,
        "query": req.query,
        "kg_mode": req.constraints.get("kg_mode", "local"),
        "use_remote_kg": req.constraints.get("use_remote_kg", False),
        "kg_endpoint": req.constraints.get("kg_endpoint"),
    }

    profile_task = _invoke_partner_with_fallback(
        "profile",
        profile_payload,
        strict_remote_validation=strict_remote_validation,
    )
    content_task = _invoke_partner_with_fallback(
        "content",
        content_payload,
        strict_remote_validation=strict_remote_validation,
    )
    (profile_resp, profile_route), (content_resp, content_route) = await asyncio.gather(profile_task, content_task)

    profile_state = _task_state(profile_resp)
    profile_data = _extract_structured_result(profile_resp)
    profile_ok, profile_reason = _validate_partner_outputs("profile", profile_state, profile_data)

    partner_tasks[reader_profile.AGENT_ID] = {
        "state": profile_state,
        "acceptance": {"passed": profile_ok, "reason": profile_reason},
        **profile_route,
    }
    partner_results[reader_profile.AGENT_ID] = {
        "state": profile_state,
        "result": profile_data,
    }

    content_state = _task_state(content_resp)
    content_data = _extract_structured_result(content_resp)
    content_ok, content_reason = _validate_partner_outputs("content", content_state, content_data)

    partner_tasks[book_content.AGENT_ID] = {
        "state": content_state,
        "acceptance": {"passed": content_ok, "reason": content_reason},
        **content_route,
    }
    partner_results[book_content.AGENT_ID] = {
        "state": content_state,
        "result": content_data,
    }

    partner_results["_candidate_set"] = candidate_book_set
    partner_results["_candidate_provenance"] = candidate_provenance
    partner_results["_contract_validation"] = {
        "candidate_book_set": {"passed": candidate_valid, "reason": candidate_reason}
    }

    if not profile_ok or not content_ok:
        return partner_tasks, partner_results

    content_outputs = content_data.get("outputs") or {}
    ranking_payload = {
        "query": req.query,
        "profile_vector": profile_data.get("preference_vector") or {},
        "candidates": _build_ranking_candidates(content_outputs, books),
        "history": policy["profile"]["history"],
        "constraints": policy["ranking_constraints"],
        "scoring_weights": policy["ranking_weights"],
    }
    ranking_resp, ranking_route = await _invoke_partner_with_fallback(
        "ranking",
        ranking_payload,
        strict_remote_validation=strict_remote_validation,
    )
    ranking_state = _task_state(ranking_resp)
    ranking_data = _extract_structured_result(ranking_resp)
    ranking_ok, ranking_reason = _validate_partner_outputs("ranking", ranking_state, ranking_data)
    partner_tasks[rec_ranking.AGENT_ID] = {
        "state": ranking_state,
        "acceptance": {"passed": ranking_ok, "reason": ranking_reason},
        **ranking_route,
    }
    partner_results[rec_ranking.AGENT_ID] = {
        "state": ranking_state,
        "result": ranking_data,
    }

    partner_results["_policy"] = {
        "scenario": scenario,
        "ranking_constraints": policy["ranking_constraints"],
        "ranking_weights": policy["ranking_weights"],
        "strict_remote_validation": strict_remote_validation,
    }

    return partner_tasks, partner_results


@app.get("/", response_class=HTMLResponse)
async def demo_root() -> HTMLResponse:
    if _DEMO_HTML_PATH.exists():
        return HTMLResponse(_DEMO_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h3>Demo page not found. Expected: web_demo/index.html</h3>", status_code=404)


@app.get("/demo", response_class=HTMLResponse)
async def demo_page() -> HTMLResponse:
    if _DEMO_HTML_PATH.exists():
        return HTMLResponse(_DEMO_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h3>Demo page not found. Expected: web_demo/index.html</h3>", status_code=404)


@app.get("/demo/benchmark-summary")
async def demo_benchmark_summary() -> JSONResponse:
    if not _BENCHMARK_SUMMARY_PATH.exists():
        return JSONResponse(
            {
                "available": False,
                "message": "Benchmark summary not found. Run scripts/phase4_benchmark_compare.py first.",
                "expected_path": str(_BENCHMARK_SUMMARY_PATH),
            }
        )

    try:
        payload = json.loads(_BENCHMARK_SUMMARY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return JSONResponse(
            {
                "available": False,
                "message": "Failed to parse benchmark summary file.",
                "error": str(exc),
            },
            status_code=500,
        )

    return JSONResponse({"available": True, "summary": payload})


@app.get("/demo/status")
async def demo_status() -> Dict[str, Any]:
    retrieval_info = get_active_retrieval_corpus_info()
    return {
        "service": "reading_concierge",
        "leader_id": LEADER_ID,
        "partner_mode": PARTNER_MODE,
        "demo_page_available": _DEMO_HTML_PATH.exists(),
        "benchmark_summary_available": _BENCHMARK_SUMMARY_PATH.exists(),
        "retrieval_corpus": retrieval_info,
    }


@app.get("/demo/retrieval-corpus")
async def demo_retrieval_corpus() -> Dict[str, Any]:
    return get_active_retrieval_corpus_info()


async def _handle_user_api(req: UserRequest, *, allow_anonymous: bool) -> Dict[str, Any]:
    session_id = req.session_id or f"session-{uuid.uuid4()}"
    if not str(req.query or "").strip():
        raise HTTPException(status_code=422, detail="query is required")

    raw_user_profile = dict(req.user_profile or {})
    raw_history = list(req.history or [])
    raw_reviews = list(req.reviews or [])

    _hydrate_request_context(req, session_id, allow_anonymous=allow_anonymous)

    # WS-A ingestion adapters: persist raw event sources so future user_id-only calls can rebuild context.
    if raw_user_profile:
        profile_store.ingest_user_basic_info(req.user_id, raw_user_profile)
    if raw_history:
        profile_store.ingest_history_events(req.user_id, raw_history)
    if raw_reviews:
        profile_store.ingest_review_events(req.user_id, raw_reviews)

    session = _lru_session_get(session_id)
    session["messages"].append({"role": "user", "content": req.query})

    profile_store.append_event(
        req.user_id,
        "query",
        {
            "query": req.query,
            "constraints": req.constraints,
            "debug_payload_override": _debug_payload_override_enabled(req),
        },
    )

    partner_tasks, partner_results = await _orchestrate_reading_flow(req)

    session["last_partner_results"] = partner_results

    ranking_result = (partner_results.get(rec_ranking.AGENT_ID) or {}).get("result") or {}
    ranking_outputs = ranking_result.get("outputs") or {}
    recommendations = ranking_outputs.get("ranking") or []
    policy_data = partner_results.get("_policy") or {}
    scenario_policy = str(policy_data.get("scenario") or _detect_scenario(req))
    ranked_contract = _build_ranked_recommendation_contract(
        ranking_outputs,
        scenario_policy=scenario_policy,
    )
    ranked_valid, ranked_reason = _validate_contract_payload(
        "ranked_recommendation_list.schema.json", ranked_contract
    )

    contract_validation = dict(partner_results.get("_contract_validation") or {})
    contract_validation["ranked_recommendation_list"] = {
        "passed": ranked_valid,
        "reason": ranked_reason,
    }
    partner_results["_contract_validation"] = contract_validation

    strict_contract_validation = bool(
        (req.constraints or {}).get("strict_contract_validation", True)
    )
    failed_contracts = {
        name: details
        for name, details in contract_validation.items()
        if isinstance(details, dict) and details.get("passed") is False
    }
    if strict_contract_validation and failed_contracts:
        logger.error(
            "event=contract_validation_failed user_id=%s failed=%s",
            req.user_id,
            failed_contracts,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "contract_validation_failed",
                "failed_contracts": failed_contracts,
            },
        )

    evaluation = _evaluation_from_response(req, ranking_outputs)

    final_state = "completed" if recommendations else "needs_input"
    response = {
        "session_id": session_id,
        "user_id": req.user_id,
        "leader_id": LEADER_ID,
        "state": final_state,
        "scenario": scenario_policy,
        "partner_tasks": partner_tasks,
        "partner_results": partner_results,
        "recommendations": recommendations,
        "explanations": ranking_outputs.get("explanations") or [],
        "metric_snapshot": ranking_outputs.get("metric_snapshot") or {},
        "evaluation": evaluation,
        "contract_artifacts": {
            "candidate_book_set": partner_results.get("_candidate_set") or {},
            "ranked_recommendation_list": ranked_contract,
        },
        "contract_validation": contract_validation,
    }

    profile_result = (partner_results.get(reader_profile.AGENT_ID) or {}).get("result") or {}
    persisted_snapshot: Optional[Dict[str, Any]] = None
    if profile_result:
        persisted_snapshot = _build_profile_snapshot(req.user_id, profile_result, req)
        profile_store.save_profile_snapshot(req.user_id, persisted_snapshot)

    recommendations = response.get("recommendations") or []
    candidate_provenance = partner_results.get("_candidate_provenance") or {}
    if recommendations:
        profile_store.record_recommendation_run(
            user_id=req.user_id,
            query=req.query,
            profile_version=str((persisted_snapshot or {}).get("profile_version") or "reader_profile_v1"),
            candidate_set_version_or_hash=str(
                req.constraints.get("candidate_set_version")
                or candidate_provenance.get("candidate_ids_hash")
                or "local-retrieval"
            ),
            book_feature_version_or_hash=str(req.constraints.get("book_feature_version") or "book_content_v1"),
            ranking_policy_version=str(req.constraints.get("ranking_policy_version") or "rec_ranking_v1"),
            weights_or_policy_snapshot=policy_data.get("ranking_weights") or req.constraints.get("scoring_weights") or {},
            candidate_provenance=candidate_provenance,
        )

    session["messages"].append({"role": "assistant", "content": "orchestration_completed"})
    logger.info(
        "event=reading_orchestration_complete session_id=%s state=%s recommendation_count=%s",
        session_id,
        final_state,
        len(recommendations),
    )
    return response


@app.post("/user_api")
async def user_api(req: UserRequest):
    if not str(req.user_id or "").strip():
        raise HTTPException(status_code=422, detail="user_id is required for /user_api")
    return await _handle_user_api(req, allow_anonymous=False)


@app.post("/user_api_debug")
async def user_api_debug(req: UserRequest):
    return await _handle_user_api(req, allow_anonymous=True)


if __name__ == "__main__":
    import uvicorn
    from acps_aip.mtls_config import load_mtls_context, build_uvicorn_ssl_kwargs

    host = os.getenv("READING_CONCIERGE_HOST", "0.0.0.0")
    port = int(os.getenv("READING_CONCIERGE_PORT", "8100"))
    config_path = os.getenv("READING_CONCIERGE_MTLS_CONFIG_PATH", _ACS_JSON_PATH)
    cert_dir = os.getenv("AGENT_MTLS_CERT_DIR")

    ssl_context = load_mtls_context(config_path, purpose="server", cert_dir=cert_dir)
    ssl_kwargs = build_uvicorn_ssl_kwargs(config_path, cert_dir=cert_dir) if ssl_context else {}

    uvicorn.run(
        "reading_concierge.reading_concierge:app",
        host=host,
        port=port,
        **ssl_kwargs,
    )
