import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field
from dotenv import load_dotenv

_CURRENT_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from base import get_agent_logger
from agents.reader_profile_agent import profile_agent as reader_profile
from agents.book_content_agent import book_content_agent as book_content
from agents.rec_ranking_agent import rec_ranking_agent as rec_ranking

load_dotenv()

LEADER_ID = os.getenv("READING_CONCIERGE_ID", "reading_concierge_001")
LOG_LEVEL = os.getenv("READING_CONCIERGE_LOG_LEVEL", "INFO").upper()

logger = get_agent_logger("agent.reading_concierge", "READING_CONCIERGE_LOG_LEVEL", LOG_LEVEL)

app = FastAPI(
    title="Reading Concierge",
    description="Coordinator that orchestrates profile, content, and ranking agents.",
)

sessions: Dict[str, Dict[str, Any]] = {}


class UserRequest(BaseModel):
    session_id: Optional[str] = None
    query: str = ""
    user_profile: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    reviews: List[Dict[str, Any]] = Field(default_factory=list)
    books: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_ids: List[str] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)


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


def _derive_books_from_query(query: str, candidate_ids: List[str]) -> List[Dict[str, Any]]:
    if candidate_ids:
        return [
            {
                "book_id": cid,
                "title": cid,
                "description": f"Auto candidate generated for query: {query[:80]}",
                "genres": [],
            }
            for cid in candidate_ids
        ]

    if not query.strip():
        return []

    return [
        {
            "book_id": "seed-001",
            "title": "Seed Book One",
            "description": f"Seed candidate inferred from query: {query[:80]}",
            "genres": ["fiction"],
        },
        {
            "book_id": "seed-002",
            "title": "Seed Book Two",
            "description": f"Alternative seed candidate inferred from query: {query[:80]}",
            "genres": ["nonfiction"],
        },
    ]


def _build_ranking_candidates(content_outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    vectors = content_outputs.get("content_vectors") or []
    tags = content_outputs.get("book_tags") or []
    tags_by_id = {row.get("book_id"): row for row in tags if isinstance(row, dict)}

    candidates: List[Dict[str, Any]] = []
    for row in vectors:
        if not isinstance(row, dict):
            continue
        bid = row.get("book_id")
        tag = tags_by_id.get(bid) or {}
        diversity_signal = 0.2 + 0.2 * len(tag.get("diversity_indicators") or [])
        novelty_signal = 0.3 + 0.1 * len(tag.get("topics") or [])
        candidates.append(
            {
                "book_id": bid,
                "title": bid,
                "vector": row.get("vector") or [],
                "kg_signal": min(1.0, 0.2 + 0.2 * len(content_outputs.get("kg_refs") or [])),
                "novelty_score": min(1.0, novelty_signal),
                "diversity_score": min(1.0, diversity_signal),
            }
        )
    return candidates


async def _orchestrate_reading_flow(req: UserRequest) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    partner_tasks: Dict[str, Any] = {}
    partner_results: Dict[str, Any] = {}

    profile_payload = {
        "user_profile": req.user_profile,
        "history": req.history,
        "reviews": req.reviews,
        "scenario": req.constraints.get("scenario", "warm"),
    }
    profile_resp = await _invoke_agent_rpc(
        reader_profile.app,
        "/reader-profile/rpc",
        profile_payload,
    )
    profile_state = _task_state(profile_resp)
    profile_data = _extract_structured_result(profile_resp)
    partner_tasks[reader_profile.AGENT_ID] = {"state": profile_state}
    partner_results[reader_profile.AGENT_ID] = {
        "state": profile_state,
        "result": profile_data,
    }

    if profile_state != "completed":
        return partner_tasks, partner_results

    books = req.books or _derive_books_from_query(req.query, req.candidate_ids)
    content_payload = {
        "books": books,
        "candidate_ids": req.candidate_ids,
        "kg_mode": req.constraints.get("kg_mode", "local"),
        "use_remote_kg": req.constraints.get("use_remote_kg", False),
        "kg_endpoint": req.constraints.get("kg_endpoint"),
    }
    content_resp = await _invoke_agent_rpc(
        book_content.app,
        "/book-content/rpc",
        content_payload,
    )
    content_state = _task_state(content_resp)
    content_data = _extract_structured_result(content_resp)
    partner_tasks[book_content.AGENT_ID] = {"state": content_state}
    partner_results[book_content.AGENT_ID] = {
        "state": content_state,
        "result": content_data,
    }

    if content_state != "completed":
        return partner_tasks, partner_results

    content_outputs = content_data.get("outputs") or {}
    ranking_payload = {
        "profile_vector": profile_data.get("preference_vector") or {},
        "candidates": _build_ranking_candidates(content_outputs),
        "constraints": {
            "top_k": req.constraints.get("top_k", 5),
            "novelty_threshold": req.constraints.get("novelty_threshold", 0.45),
            "min_new_items": req.constraints.get("min_new_items", 0),
        },
        "scoring_weights": req.constraints.get("scoring_weights") or {
            "collaborative": 0.25,
            "semantic": 0.35,
            "knowledge": 0.2,
            "diversity": 0.2,
        },
    }
    ranking_resp = await _invoke_agent_rpc(
        rec_ranking.app,
        "/rec-ranking/rpc",
        ranking_payload,
    )
    ranking_state = _task_state(ranking_resp)
    ranking_data = _extract_structured_result(ranking_resp)
    partner_tasks[rec_ranking.AGENT_ID] = {"state": ranking_state}
    partner_results[rec_ranking.AGENT_ID] = {
        "state": ranking_state,
        "result": ranking_data,
    }

    return partner_tasks, partner_results


@app.post("/user_api")
async def user_api(req: UserRequest):
    session_id = req.session_id or f"session-{uuid.uuid4()}"
    session = sessions.setdefault(
        session_id,
        {
            "messages": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_partner_results": {},
        },
    )
    session["messages"].append({"role": "user", "content": req.query})

    partner_tasks, partner_results = await _orchestrate_reading_flow(req)

    session["last_partner_results"] = partner_results

    ranking_result = (partner_results.get(rec_ranking.AGENT_ID) or {}).get("result") or {}
    ranking_outputs = ranking_result.get("outputs") or {}
    recommendations = ranking_outputs.get("ranking") or []

    final_state = "completed" if recommendations else "needs_input"
    response = {
        "session_id": session_id,
        "leader_id": LEADER_ID,
        "state": final_state,
        "partner_tasks": partner_tasks,
        "partner_results": partner_results,
        "recommendations": recommendations,
        "explanations": ranking_outputs.get("explanations") or [],
        "metric_snapshot": ranking_outputs.get("metric_snapshot") or {},
    }

    session["messages"].append({"role": "assistant", "content": "orchestration_completed"})
    logger.info(
        "event=reading_orchestration_complete session_id=%s state=%s recommendation_count=%s",
        session_id,
        final_state,
        len(recommendations),
    )
    return response
