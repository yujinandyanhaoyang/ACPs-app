import os
import sys
import json
import uuid
import asyncio
import re
from collections import OrderedDict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

_CURRENT_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_DEMO_HTML_PATH = Path(_PROJECT_ROOT) / "web_demo" / "index.html"
_BENCHMARK_SUMMARY_PATH = Path(_PROJECT_ROOT) / "scripts" / "phase4_benchmark_summary.json"

from base import get_agent_logger, call_openai_chat
from services.evaluation_metrics import compute_recommendation_metrics, build_ablation_report
from services.book_retrieval import load_books, retrieve_books_by_query
from services.model_backends import load_cf_item_vectors
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

MAX_SESSIONS = int(os.getenv("READING_CONCIERGE_MAX_SESSIONS", "200"))
sessions: OrderedDict[str, Dict[str, Any]] = OrderedDict()


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
            profile_user = {"segment": "cold_start", "preferred_language": "unknown"}
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

    if policy.get("needs_cold_seed") and not policy["profile"]["history"]:
        policy["profile"]["history"] = await _seed_cold_start_history(req, books)

    profile_payload = {
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
    return {
        "service": "reading_concierge",
        "leader_id": LEADER_ID,
        "partner_mode": PARTNER_MODE,
        "demo_page_available": _DEMO_HTML_PATH.exists(),
        "benchmark_summary_available": _BENCHMARK_SUMMARY_PATH.exists(),
    }


@app.post("/user_api")
async def user_api(req: UserRequest):
    session_id = req.session_id or f"session-{uuid.uuid4()}"
    session = _lru_session_get(session_id)
    session["messages"].append({"role": "user", "content": req.query})

    partner_tasks, partner_results = await _orchestrate_reading_flow(req)

    session["last_partner_results"] = partner_results

    ranking_result = (partner_results.get(rec_ranking.AGENT_ID) or {}).get("result") or {}
    ranking_outputs = ranking_result.get("outputs") or {}
    recommendations = ranking_outputs.get("ranking") or []
    policy_data = partner_results.get("_policy") or {}
    evaluation = _evaluation_from_response(req, ranking_outputs)

    final_state = "completed" if recommendations else "needs_input"
    response = {
        "session_id": session_id,
        "leader_id": LEADER_ID,
        "state": final_state,
        "scenario": policy_data.get("scenario", _detect_scenario(req)),
        "partner_tasks": partner_tasks,
        "partner_results": partner_results,
        "recommendations": recommendations,
        "explanations": ranking_outputs.get("explanations") or [],
        "metric_snapshot": ranking_outputs.get("metric_snapshot") or {},
        "evaluation": evaluation,
    }

    session["messages"].append({"role": "assistant", "content": "orchestration_completed"})
    logger.info(
        "event=reading_orchestration_complete session_id=%s state=%s recommendation_count=%s",
        session_id,
        final_state,
        len(recommendations),
    )
    return response
