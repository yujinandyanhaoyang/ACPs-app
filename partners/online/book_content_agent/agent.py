from __future__ import annotations

import json
import math
import os
import sys
import time
import uuid
from dataclasses import dataclass
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
from base import get_agent_logger, register_acs_route
from services.model_backends import generate_text_embeddings_async

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore

load_dotenv(_PROJECT_ROOT / ".env")

ACS_PATH = _CURRENT_DIR / "acs.json"
CONFIG_PATH = _CURRENT_DIR / "config.toml"

AGENT_ID = os.getenv("BOOK_CONTENT_AGENT_ID", "book_content_agent_001")
AIP_ENDPOINT = os.getenv("BOOK_CONTENT_AGENT_ENDPOINT", "/book-content/rpc")
LOG_LEVEL = os.getenv("BOOK_CONTENT_AGENT_LOG_LEVEL", "INFO").upper()

logger = get_agent_logger("partner.book_content_agent", "BOOK_CONTENT_AGENT_LOG_LEVEL", LOG_LEVEL)


@dataclass
class AgentConfig:
    port: int = 8212
    encoder_model: str = "all-MiniLM-L6-v2"
    proj_matrix_path: str = "proj_matrix.npy"
    mismatch_threshold: float = 0.4


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
    model = data.get("model") if isinstance(data, dict) else {}

    try:
        if isinstance(server, dict) and server.get("port"):
            cfg.port = int(server["port"])
    except Exception:
        pass
    if isinstance(model, dict):
        cfg.encoder_model = str(model.get("ENCODER_MODEL") or cfg.encoder_model)
        cfg.proj_matrix_path = str(model.get("PROJ_MATRIX_PATH") or cfg.proj_matrix_path)
        try:
            cfg.mismatch_threshold = float(model.get("MISMATCH_THRESHOLD") or cfg.mismatch_threshold)
        except Exception:
            pass
    return cfg


CFG = _load_config()

app = FastAPI(
    title="Book Content Agent (Phase 2)",
    description="Negotiation-ready content proposal partner with alignment and divergence analysis.",
)
register_acs_route(app, str(ACS_PATH))


def _parse_payload(message: Message) -> Dict[str, Any]:
    params = getattr(message, "commandParams", None) or {}
    payload = params.get("payload") if isinstance(params, dict) else None
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_action(payload: Dict[str, Any]) -> str:
    return str(
        payload.get("action")
        or payload.get("skill")
        or payload.get("intent")
        or payload.get("command")
        or "bca.build_content_proposal"
    ).strip()


def _normalize_genre_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    return token


def _normalize_books(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    books = payload.get("books") if isinstance(payload.get("books"), list) else []
    candidate_ids = payload.get("candidate_ids") if isinstance(payload.get("candidate_ids"), list) else []

    by_id: Dict[str, Dict[str, Any]] = {}
    for idx, row in enumerate(books):
        if not isinstance(row, dict):
            continue
        book_id = str(row.get("book_id") or row.get("id") or f"book_{idx}").strip()
        if not book_id:
            continue
        item = dict(row)
        item["book_id"] = book_id
        item["title"] = str(row.get("title") or book_id)
        item["description"] = str(row.get("description") or "")
        raw_genres = row.get("genres") if isinstance(row.get("genres"), list) else []
        item["genres"] = [g for g in (_normalize_genre_token(x) for x in raw_genres) if g]
        by_id[book_id] = item

    for cid in candidate_ids:
        book_id = str(cid or "").strip()
        if not book_id or book_id in by_id:
            continue
        by_id[book_id] = {
            "book_id": book_id,
            "title": book_id,
            "description": "",
            "genres": [],
        }

    return list(by_id.values())


def _book_text(book: Dict[str, Any]) -> str:
    return "\n".join(
        [
            str(book.get("title") or ""),
            " ".join(str(x) for x in (book.get("genres") or []) if str(x).strip()),
            str(book.get("description") or ""),
        ]
    )


def _load_projection_matrix() -> Optional[Any]:
    if np is None:
        return None
    matrix_path = Path(CFG.proj_matrix_path)
    if not matrix_path.is_absolute():
        matrix_path = _CURRENT_DIR / matrix_path
    if not matrix_path.exists():
        logger.warning("event=projection_matrix_missing path=%s", matrix_path)
        return None
    try:
        matrix = np.load(matrix_path, allow_pickle=False)
        if len(getattr(matrix, "shape", ())) != 2 or matrix.shape != (256, 384):
            logger.warning("event=projection_matrix_shape_invalid shape=%s", getattr(matrix, "shape", None))
            return None
        return matrix.astype(np.float32)
    except Exception as exc:
        logger.warning("event=projection_matrix_load_failed error=%s", exc)
        return None


def _project_vectors(vectors_384: List[List[float]], proj_matrix: Any) -> List[List[float]]:
    if np is None or proj_matrix is None:
        return []
    if not vectors_384:
        return []
    x = np.asarray(vectors_384, dtype=np.float32)
    if len(x.shape) != 2 or x.shape[1] != 384:
        return []
    y = x @ proj_matrix.T
    return [[round(float(v), 6) for v in row.tolist()] for row in y]


def _distribution(tokens: List[str]) -> Dict[str, float]:
    counts: Dict[str, float] = {}
    for token in tokens:
        if not token:
            continue
        counts[token] = counts.get(token, 0.0) + 1.0
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def _js_divergence(left: Dict[str, float], right: Dict[str, float]) -> float:
    eps = 1e-12
    keys = set(left.keys()) | set(right.keys())
    if not keys:
        return 0.0
    p = {k: float(left.get(k, 0.0)) + eps for k in keys}
    q = {k: float(right.get(k, 0.0)) + eps for k in keys}
    sp = sum(p.values())
    sq = sum(q.values())
    p = {k: v / sp for k, v in p.items()}
    q = {k: v / sq for k, v in q.items()}
    m = {k: 0.5 * (p[k] + q[k]) for k in keys}

    def _kl(a: Dict[str, float], b: Dict[str, float]) -> float:
        return sum(a[k] * math.log(a[k] / b[k]) for k in keys)

    return float(0.5 * _kl(p, m) + 0.5 * _kl(q, m))


def _declared_genres(payload: Dict[str, Any]) -> List[str]:
    genres: List[str] = []
    raw = payload.get("declared_genres")
    if isinstance(raw, list):
        genres.extend([_normalize_genre_token(x) for x in raw])
    user_profile = payload.get("user_profile") if isinstance(payload.get("user_profile"), dict) else {}
    for key in ["preferred_genres", "genres"]:
        value = user_profile.get(key)
        if isinstance(value, list):
            genres.extend([_normalize_genre_token(x) for x in value])
    return [g for g in genres if g]


def _behavior_genres(payload: Dict[str, Any], books: List[Dict[str, Any]]) -> List[str]:
    raw = payload.get("behavior_genres")
    if isinstance(raw, list) and raw:
        return [g for g in (_normalize_genre_token(x) for x in raw) if g]
    out: List[str] = []
    for book in books:
        for g in book.get("genres") or []:
            token = _normalize_genre_token(g)
            if token:
                out.append(token)
    return out


def _alignment_report(payload: Dict[str, Any], books: List[Dict[str, Any]]) -> Dict[str, Any]:
    declared = _declared_genres(payload)
    behavior = _behavior_genres(payload, books)
    p = _distribution(declared)
    q = _distribution(behavior)
    divergence = _js_divergence(p, q)

    if divergence <= 0.2:
        status = "aligned"
    elif divergence <= CFG.mismatch_threshold:
        status = "soft_mismatch"
    else:
        status = "mismatch"

    return {
        "divergence_score": round(divergence, 6),
        "alignment_status": status,
        "declared_genres": declared,
        "behavior_genres": behavior,
        "mismatch_threshold": CFG.mismatch_threshold,
    }


def _coverage_report(books: List[Dict[str, Any]]) -> Dict[str, Any]:
    genres = set()
    described = 0
    for book in books:
        if str(book.get("description") or "").strip():
            described += 1
        for g in book.get("genres") or []:
            token = _normalize_genre_token(g)
            if token:
                genres.add(token)
    return {
        "book_count": len(books),
        "genre_coverage": len(genres),
        "description_coverage": round(described / max(1, len(books)), 4),
    }


def _weight_suggestion(divergence_score: float) -> Dict[str, float]:
    content_weight = max(0.2, min(0.85, 0.25 + divergence_score))
    profile_weight = max(0.15, min(0.8, 1.0 - content_weight))
    return {
        "profile_weight": round(profile_weight, 4),
        "content_weight": round(content_weight, 4),
    }


async def _build_content_proposal(payload: Dict[str, Any]) -> Dict[str, Any]:
    books = _normalize_books(payload)
    texts = [_book_text(book) for book in books]
    embeddings_384, embed_meta = await generate_text_embeddings_async(
        texts,
        model_name=CFG.encoder_model,
        fallback_dim=384,
    )

    if embeddings_384 and len(embeddings_384[0]) != 384:
        # Keep the contract stable at 384-dim.
        if np is not None:
            arr = np.asarray(embeddings_384, dtype=np.float32)
            if arr.shape[1] < 384:
                pad = np.zeros((arr.shape[0], 384 - arr.shape[1]), dtype=np.float32)
                arr = np.concatenate([arr, pad], axis=1)
            else:
                arr = arr[:, :384]
            embeddings_384 = [[round(float(v), 6) for v in row.tolist()] for row in arr]

    proj_matrix = _load_projection_matrix()
    embeddings_256 = _project_vectors(embeddings_384, proj_matrix)

    content_vectors = []
    for idx, book in enumerate(books):
        content_vectors.append(
            {
                "book_id": book["book_id"],
                "vector_384": embeddings_384[idx] if idx < len(embeddings_384) else [],
                "vector_256": embeddings_256[idx] if idx < len(embeddings_256) else [],
                "genres": book.get("genres") or [],
            }
        )

    alignment = _alignment_report(payload, books)
    divergence = float(alignment.get("divergence_score") or 0.0)
    report = {
        "divergence_score": divergence,
        "alignment_status": alignment.get("alignment_status"),
        "weight_suggestion": _weight_suggestion(divergence),
        "coverage_report": _coverage_report(books),
        "alignment_report": alignment,
        "content_vectors": content_vectors,
        "embedding_backend": embed_meta,
    }

    if divergence > CFG.mismatch_threshold:
        report["counter_proposal"] = {
            "reason": "preference_divergence",
            "counter_strategy": "explore",
            "mmr_lambda": 0.65,
            "message": "Divergence exceeds mismatch threshold; propose exploration-heavy rebalancing.",
        }

    return report


def _supplement_for_evidence_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    divergence = float(payload.get("divergence_score") or 0.0)
    fallback_strategy = "explore_then_exploit" if divergence > 0.4 else "balanced"
    exploration_budget = 0.35 if divergence > 0.4 else 0.2
    return {
        "fallback_strategy": fallback_strategy,
        "exploration_budget": exploration_budget,
    }


async def _handle_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = _extract_action(payload)

    if action in {"supplement_proposal", "request.supplement_proposal", "rda.evidence_request"}:
        return {
            "action": action,
            "supplement": _supplement_for_evidence_request(payload),
        }

    proposal = await _build_content_proposal(payload)
    return {
        "action": action,
        "outputs": proposal,
    }


def _fail_task(task_id: str, reason: str) -> Task:
    TaskManager.update_task_status(task_id, TaskState.Failed, data_items=[TextDataItem(text=reason)])
    return TaskManager.get_task(task_id)


def _complete_task(task_id: str, result: Dict[str, Any]) -> Task:
    product = Product(
        id=str(uuid.uuid4()),
        name="book-content-proposal",
        description="Book content proposal for negotiation",
        dataItems=[
            StructuredDataItem(data=result),
            TextDataItem(text="book content proposal complete"),
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


handlers = CommandHandlers(on_start=handle_start, on_continue=handle_continue, on_cancel=handle_cancel)
add_aip_rpc_router(app, AIP_ENDPOINT, handlers)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("BOOK_CONTENT_HOST", "0.0.0.0")
    port = int(os.getenv("BOOK_CONTENT_PORT", str(CFG.port)))
    uvicorn.run(app, host=host, port=port)
