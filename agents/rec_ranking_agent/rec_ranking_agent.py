import os
import sys
import json
import uuid
import time
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI
from dotenv import load_dotenv

_CURRENT_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, os.pardir, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from base import get_agent_logger, extract_text_from_message, call_openai_chat, register_acs_route
from services.model_backends import estimate_collaborative_scores_with_svd, generate_text_embeddings_async
from acps_aip.aip_base_model import (
    Message,
    Task,
    TaskState,
    Product,
    TextDataItem,
    StructuredDataItem,
)
from acps_aip.aip_rpc_server import add_aip_rpc_router, TaskManager, CommandHandlers

load_dotenv()

AGENT_ID = os.getenv("REC_RANKING_AGENT_ID", "rec_ranking_agent_001")
AIP_ENDPOINT = os.getenv("REC_RANKING_AGENT_ENDPOINT", "/rec-ranking/rpc")
LOG_LEVEL = os.getenv("REC_RANKING_AGENT_LOG_LEVEL", "INFO").upper()
LLM_MODEL = os.getenv("REC_RANKING_MODEL", os.getenv("OPENAI_MODEL", "qwen-plus"))
EMBED_MODEL = os.getenv("BOOK_CONTENT_EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_VECTOR_DIM = max(8, int(os.getenv("BOOK_CONTENT_VECTOR_DIM", "12")))
RANKING_VERSION = os.getenv("REC_RANKING_VERSION", "rec_ranking_v1")
DEFAULT_TOP_K = max(1, int(os.getenv("REC_RANKING_TOP_K", "5")))
DEFAULT_NOVELTY_THRESHOLD = float(os.getenv("REC_RANKING_NOVELTY_THRESHOLD", "0.45"))

logger = get_agent_logger("agent.rec_ranking", "REC_RANKING_AGENT_LOG_LEVEL", LOG_LEVEL)

app = FastAPI(
    title="Recommendation Ranking Agent",
    description="ACPs-compliant recommendation decision agent with multi-factor scoring.",
)

_ACS_JSON_PATH = str(Path(_CURRENT_DIR) / "config.example.json")
register_acs_route(app, _ACS_JSON_PATH)

_RANKING_CONTEXT: Dict[str, Dict[str, Any]] = {}


def _parse_payload(message: Message) -> Dict[str, Any]:
    params = getattr(message, "commandParams", None) or {}
    payload = params.get("payload") if isinstance(params, dict) else None
    if isinstance(payload, dict):
        return payload
    text = extract_text_from_message(message)
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("event=payload_parse_failed task_id=%s", message.taskId)
        return {}


def _merge_payload(task_id: str, new_payload: Dict[str, Any]) -> Dict[str, Any]:
    base_payload = _RANKING_CONTEXT.get(task_id, {})
    merged: Dict[str, Any] = {**base_payload}
    for key, value in new_payload.items():
        if value in (None, ""):
            continue
        if key in {"content_vectors", "candidates", "svd_factors"}:
            existing = merged.get(key) or []
            if isinstance(value, list):
                merged[key] = existing + value
            continue
        if key in {"profile_vector", "scoring_weights", "constraints"}:
            existing_obj = merged.get(key) or {}
            if isinstance(value, dict):
                merged[key] = {**existing_obj, **value}
            continue
        merged[key] = value
    _RANKING_CONTEXT[task_id] = merged
    return merged


def _validate_payload(payload: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    profile_vector = payload.get("profile_vector")
    if not isinstance(profile_vector, dict) or not profile_vector:
        missing.append("profile_vector")

    has_vectors = bool(payload.get("content_vectors"))
    has_candidates = bool(payload.get("candidates"))
    if not (has_vectors or has_candidates):
        missing.append("content_vectors|candidates")

    return missing


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    positive = {k: max(v, 0.0) for k, v in weights.items()}
    total = sum(positive.values())
    if total <= 0:
        return {
            "collaborative": 0.25,
            "semantic": 0.35,
            "knowledge": 0.2,
            "diversity": 0.2,
        }
    return {k: round(v / total, 4) for k, v in positive.items()}


def _vector_similarity(candidate_vector: List[float], target_vector: List[float]) -> float:
    if not candidate_vector or not target_vector:
        return 0.0
    size = min(len(candidate_vector), len(target_vector))
    dot = sum(candidate_vector[i] * target_vector[i] for i in range(size))
    cand_norm = sum(candidate_vector[i] ** 2 for i in range(size)) ** 0.5
    target_norm = sum(target_vector[i] ** 2 for i in range(size)) ** 0.5
    if cand_norm == 0 or target_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (cand_norm * target_norm)))


def _tokenize_text(value: Any) -> List[str]:
    text = str(value or "").lower()
    return [tok for tok in re.findall(r"[\w]+", text, re.UNICODE) if len(tok) >= 2]


def _derive_scenario_policy(payload: Dict[str, Any]) -> str:
    """Derive scenario_policy from payload or profile characteristics."""
    profile_vector = payload.get("profile_vector", {})
    query = payload.get("query", "")
    
    # Check for explicit scenario indicators in query
    query_lower = query.lower()
    if "quick" in query_lower or "short" in query_lower:
        return "quick_read"
    if "deep" in query_lower or "comprehensive" in query_lower:
        return "deep_exploration"
    if "new" in query_lower or "discover" in query_lower:
        return "discovery"
    if "similar" in query_lower or "like" in query_lower:
        return "similarity_based"
    
    # Derive from profile characteristics
    pacing = profile_vector.get("pacing", {})
    if isinstance(pacing, dict):
        fast_pace = _safe_float(pacing.get("fast", 0))
        slow_pace = _safe_float(pacing.get("slow", 0))
        if fast_pace > slow_pace:
            return "quick_read"
        elif slow_pace > fast_pace:
            return "deep_exploration"
    
    difficulty = profile_vector.get("difficulty", {})
    if isinstance(difficulty, dict):
        high_diff = _safe_float(difficulty.get("advanced", 0))
        low_diff = _safe_float(difficulty.get("beginner", 0))
        if high_diff > low_diff:
            return "deep_exploration"
        elif low_diff > high_diff:
            return "casual_reading"
    
    # Default scenario
    return "balanced_recommendation"


def _query_candidate_alignment(query: str, candidate: Dict[str, Any]) -> float:
    query_tokens = set(_tokenize_text(query))
    if not query_tokens:
        return 0.0

    candidate_text = " ".join(
        [
            str(candidate.get("title") or ""),
            str(candidate.get("description") or ""),
            " ".join(str(g) for g in (candidate.get("genres") or [])),
            " ".join(str(t) for t in (candidate.get("topics") or [])),
        ]
    )
    candidate_tokens = set(_tokenize_text(candidate_text))
    if not candidate_tokens:
        return 0.0

    overlap = len(query_tokens & candidate_tokens)
    return round(max(0.0, min(1.0, overlap / max(len(query_tokens), 1))), 4)


def _flatten_profile_to_vector(profile_vector: Dict[str, Any], size: int = 12) -> List[float]:
    packed: List[float] = []
    for key in ["genres", "themes", "formats", "languages", "tones", "difficulty", "pacing"]:
        val = profile_vector.get(key)
        if isinstance(val, dict):
            packed.extend([_safe_float(v) for v in val.values()])
    if not packed:
        packed = [0.1] * size
    while len(packed) < size:
        packed.extend(packed)
    return packed[:size]


def _profile_to_sentence(profile_vector: Dict[str, Any], query: str) -> str:
    def _top_keys(section: Any, limit: int = 3) -> List[str]:
        if not isinstance(section, dict):
            return []
        ranked = sorted(section.items(), key=lambda item: _safe_float(item[1]), reverse=True)
        return [str(key) for key, _ in ranked[:limit] if str(key)]

    parts: List[str] = []
    genres = _top_keys(profile_vector.get("genres"))
    themes = _top_keys(profile_vector.get("themes"))
    tones = _top_keys(profile_vector.get("tones"))
    pacing = _top_keys(profile_vector.get("pacing"), limit=2)
    difficulty = _top_keys(profile_vector.get("difficulty"), limit=2)
    formats = _top_keys(profile_vector.get("formats"), limit=2)
    languages = _top_keys(profile_vector.get("languages"), limit=2)

    if genres:
        parts.append(f"genres: {', '.join(genres)}")
    if themes:
        parts.append(f"themes: {', '.join(themes)}")
    if tones:
        parts.append(f"tones: {', '.join(tones)}")
    if pacing:
        parts.append(f"pacing: {', '.join(pacing)}")
    if difficulty:
        parts.append(f"difficulty: {', '.join(difficulty)}")
    if formats:
        parts.append(f"formats: {', '.join(formats)}")
    if languages:
        parts.append(f"languages: {', '.join(languages)}")

    summary = "Reader preferences: " + "; ".join(parts) if parts else "Reader preferences: unknown"
    if query:
        summary = f"{summary}. Current query: {query}"
    return summary


async def _profile_to_embedding(profile_vector: Dict[str, Any], query: str) -> Tuple[List[float], Dict[str, Any]]:
    summary = _profile_to_sentence(profile_vector, query)
    embeddings, backend = await generate_text_embeddings_async(
        [summary],
        model_name=EMBED_MODEL,
        fallback_dim=EMBED_VECTOR_DIM,
    )
    if embeddings:
        return embeddings[0], backend
    return _flatten_profile_to_vector(profile_vector, size=EMBED_VECTOR_DIM), {"backend": "fallback"}


def _candidate_pool(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    vectors = payload.get("content_vectors") or []
    candidates = payload.get("candidates") or []

    by_id: Dict[str, Dict[str, Any]] = {}

    for item in candidates:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("book_id") or item.get("id") or item.get("title") or uuid.uuid4())
        by_id[cid] = {**item, "book_id": cid}

    for item in vectors:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("book_id") or item.get("id") or item.get("title") or uuid.uuid4())
        current = by_id.get(cid, {"book_id": cid})
        current.update(item)
        by_id[cid] = current

    return list(by_id.values())


def _build_svd_map(payload: Dict[str, Any]) -> Dict[str, float]:
    svd_factors = payload.get("svd_factors") or []
    svd_map: Dict[str, float] = {}
    for item in svd_factors:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("book_id") or item.get("id") or "")
        if not cid:
            continue
        svd_map[cid] = _safe_float(item.get("score"), 0.0)
    return svd_map


def _normalize_score_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not rows:
        return rows

    if len(rows) < 3:
        for row in rows:
            for key in ["collaborative", "semantic", "knowledge", "diversity"]:
                value = _safe_float(row.get("score_parts", {}).get(key), 0.0)
                row["score_parts"][key] = round(max(0.0, min(1.0, value)), 4)
        return rows

    for key in ["collaborative", "semantic", "knowledge", "diversity"]:
        values = [_safe_float(r.get("score_parts", {}).get(key), 0.0) for r in rows]
        mn = min(values)
        mx = max(values)
        span = mx - mn
        for row in rows:
            value = _safe_float(row.get("score_parts", {}).get(key), 0.0)
            normalized = (value - mn) / span if span > 0 else value
            row["score_parts"][key] = round(max(0.0, min(1.0, normalized)), 4)
    return rows


async def _rank_candidates(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    profile_vector = payload.get("profile_vector") or {}
    scoring_weights = _normalize_weights(
        {
            "collaborative": _safe_float((payload.get("scoring_weights") or {}).get("collaborative"), 0.25),
            "semantic": _safe_float((payload.get("scoring_weights") or {}).get("semantic"), 0.35),
            "knowledge": _safe_float((payload.get("scoring_weights") or {}).get("knowledge"), 0.2),
            "diversity": _safe_float((payload.get("scoring_weights") or {}).get("diversity"), 0.2),
        }
    )

    constraints = payload.get("constraints") or {}
    top_k = int(constraints.get("top_k") or payload.get("top_k") or DEFAULT_TOP_K)
    novelty_threshold = _safe_float(
        constraints.get("novelty_threshold"), _safe_float(payload.get("novelty_threshold"), DEFAULT_NOVELTY_THRESHOLD)
    )
    min_new_items = int(constraints.get("min_new_items") or payload.get("min_new_items") or 0)

    query_text = str(payload.get("query") or payload.get("query_text") or "")
    profile_summary = _profile_to_sentence(profile_vector, query_text)
    user_vector, semantic_backend = await _profile_to_embedding(profile_vector, query_text)
    svd_map = _build_svd_map(payload)
    pool = _candidate_pool(payload)
    svd_backend_meta: Dict[str, Any] = {"backend": "provided-factors", "n_components": 0}
    if not svd_map:
        estimated_scores, svd_backend_meta = estimate_collaborative_scores_with_svd(
            history=payload.get("history") or [],
            candidates=pool,
            n_components=int((payload.get("constraints") or {}).get("svd_components") or 8),
        )
        svd_map = estimated_scores

    rows: List[Dict[str, Any]] = []
    for idx, candidate in enumerate(pool):
        cid = str(candidate.get("book_id") or f"cand_{idx}")
        candidate_vector = candidate.get("vector") or candidate.get("content_vector") or []
        if not isinstance(candidate_vector, list):
            candidate_vector = []
        semantic = _vector_similarity([_safe_float(v) for v in candidate_vector], user_vector)
        query_alignment = _query_candidate_alignment(query_text, candidate)
        if query_text.strip():
            semantic = round(semantic * 0.35 + query_alignment * 0.65, 4)

        collaborative = svd_map.get(cid)
        if collaborative is None:
            collaborative = _safe_float(candidate.get("svd_score"), 0.0)

        kg_signal = _safe_float(candidate.get("kg_signal"), 0.0)
        kg_refs = candidate.get("kg_refs") or []
        if isinstance(kg_refs, list) and kg_refs:
            kg_signal = max(kg_signal, min(1.0, len(kg_refs) / 5.0))

        novelty = _safe_float(candidate.get("novelty_score"), 0.0)
        diversity = _safe_float(candidate.get("diversity_score"), 0.0)
        diversity_boost = max(diversity, novelty)

        rows.append(
            {
                "book_id": cid,
                "title": candidate.get("title") or cid,
                "novelty_score": novelty,
                "score_parts": {
                    "collaborative": collaborative,
                    "semantic": semantic,
                    "knowledge": kg_signal,
                    "diversity": diversity_boost,
                },
                "raw_candidate": candidate,
            }
        )

    rows = _normalize_score_rows(rows)

    for row in rows:
        parts = row["score_parts"]
        row["composite_score"] = round(
            parts["collaborative"] * scoring_weights["collaborative"]
            + parts["semantic"] * scoring_weights["semantic"]
            + parts["knowledge"] * scoring_weights["knowledge"]
            + parts["diversity"] * scoring_weights["diversity"],
            4,
        )

    rows.sort(key=lambda item: item["composite_score"], reverse=True)

    selected = rows[: max(top_k, 1)]

    if min_new_items > 0:
        new_items = [r for r in rows if r["novelty_score"] >= novelty_threshold]
        keep_ids = {item["book_id"] for item in selected}
        injected = 0
        for fresh in new_items:
            if fresh["book_id"] in keep_ids:
                continue
            selected.append(fresh)
            keep_ids.add(fresh["book_id"])
            injected += 1
            if injected >= min_new_items:
                break
        selected = sorted(selected, key=lambda item: item["composite_score"], reverse=True)[: max(top_k, 1)]

    novelty_values = [_safe_float(r.get("novelty_score"), 0.0) for r in selected]
    diversity_values = [_safe_float(r.get("score_parts", {}).get("diversity"), 0.0) for r in selected]

    metric_snapshot = {
        "top_k": len(selected),
        "avg_composite_score": round(sum(r["composite_score"] for r in selected) / len(selected), 4)
        if selected
        else 0.0,
        "avg_novelty": round(sum(novelty_values) / len(novelty_values), 4) if novelty_values else 0.0,
        "avg_diversity": round(sum(diversity_values) / len(diversity_values), 4) if diversity_values else 0.0,
        "novelty_threshold": novelty_threshold,
        "new_item_count": sum(1 for r in selected if r["novelty_score"] >= novelty_threshold),
    }

    return selected, {
        "metric_snapshot": metric_snapshot,
        "scoring_weights": scoring_weights,
        "collaborative_backend": svd_backend_meta,
        "semantic_backend": semantic_backend,
        "query": query_text,
        "profile_summary": profile_summary,
        "constraints": {
            "top_k": top_k,
            "novelty_threshold": novelty_threshold,
            "min_new_items": min_new_items,
        },
    }


async def _generate_explanation_for_item(
    item: Dict[str, Any],
    query: str,
    profile_summary: str,
) -> Dict[str, Any]:
    parts = item.get("score_parts") or {}
    raw_candidate = item.get("raw_candidate") or {}
    description = str(raw_candidate.get("description") or "")[:500]
    genres = raw_candidate.get("genres") or []
    author = str(raw_candidate.get("author") or "")
    bullet_summary = [
        f"Composite score: {item.get('composite_score', 0)}",
        f"Semantic alignment: {parts.get('semantic', 0)}",
        f"Collaborative signal: {parts.get('collaborative', 0)}",
        f"Knowledge signal: {parts.get('knowledge', 0)}",
        f"Diversity signal: {parts.get('diversity', 0)}",
    ]

    if not os.getenv("OPENAI_API_KEY"):
        return {
            "book_id": item.get("book_id"),
            "bullet_summary": bullet_summary,
            "justification": (
                f"Matches query '{query}' using available content signals; "
                f"themes/genres considered: {', '.join(str(g) for g in genres[:3]) or 'n/a'}."
            ),
            "source": "heuristic",
        }

    book_line = f"Book: {item.get('title') or ''}" + (f" by {author}" if author else "")
    genre_str = ", ".join(str(g) for g in genres[:5]) if genres else "n/a"
    prompt = (
        f"User query: {query}\n"
        f"User preference: {profile_summary}\n"
        f"{book_line}\n"
        f"Description: {description}\n"
        f"Genres: {genre_str}\n"
        f"Scores: {json.dumps(parts, ensure_ascii=False)}\n"
        "Generate a concise recommendation explanation."
    )
    try:
        raw = await call_openai_chat(
            [
                {"role": "system", "content": "You explain recommendation rationale succinctly."},
                {"role": "user", "content": prompt},
            ],
            model=LLM_MODEL,
            temperature=0.2,
            max_tokens=180,
        )
        return {
            "book_id": item.get("book_id"),
            "bullet_summary": bullet_summary,
            "justification": (raw or "").strip() or "Model returned empty explanation.",
            "source": "llm",
        }
    except Exception as exc:  # pragma: no cover
        logger.exception("event=explanation_llm_failed book_id=%s error=%s", item.get("book_id"), exc)
        return {
            "book_id": item.get("book_id"),
            "bullet_summary": bullet_summary,
            "justification": "Fallback explanation due to model call failure.",
            "source": "heuristic",
        }


async def _build_explanations(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    query = ""
    profile_summary = ""
    if rows:
        meta = rows[0].get("_explain_meta") or {}
        query = str(meta.get("query") or "")
        profile_summary = str(meta.get("profile_summary") or "")
    explanations: List[Dict[str, Any]] = []
    for item in rows:
        explanations.append(
            await _generate_explanation_for_item(
                item,
                query=query,
                profile_summary=profile_summary,
            )
        )
    return explanations


async def _analyze_ranking(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rank candidates and produce contract-compliant output.
    
    Contract alignment (ranked_recommendation_list.schema.json v1.0.0):
    - scenario_policy: propagated from payload or derived from profile
    - ranking: array with required fields per item including explanation_evidence_refs
    """
    start_ts = time.perf_counter()

    ranked_rows, meta = await _rank_candidates(payload)
    scenario_policy = payload.get("scenario_policy") or _derive_scenario_policy(payload)
    
    for row in ranked_rows:
        row["_explain_meta"] = {
            "query": meta.get("query") or "",
            "profile_summary": meta.get("profile_summary") or "",
            "scenario_policy": scenario_policy,
        }
    explanations = await _build_explanations(ranked_rows)

    # Build contract-compliant ranking list
    ranked_items = []
    for rank_idx, item in enumerate(ranked_rows, start=1):
        score_parts = item.get("score_parts", {})
        expl = explanations[rank_idx - 1] if rank_idx <= len(explanations) else {}
        evidence_refs = []
        for bullet in expl.get("bullet_summary") or []:
            if isinstance(bullet, str) and bullet.strip():
                evidence_refs.append(bullet.strip())
        ranked_items.append(
            {
                "book_id": item.get("book_id"),
                "title": item.get("title"),
                "score_total": item.get("composite_score", 0.0),
                "score_cf": score_parts.get("collaborative", 0.0),
                "score_content": score_parts.get("semantic", 0.0),
                "score_kg": score_parts.get("knowledge", 0.0),
                "score_diversity": score_parts.get("diversity", 0.0),
                "rank_position": rank_idx,
                "scenario_policy": scenario_policy,
                "explanation": expl.get("justification", ""),
                "explanation_evidence_refs": evidence_refs,
            }
        )

    outputs = {
        "scenario_policy": scenario_policy,
        "ranking": ranked_items,
        "explanations": explanations,
        "metric_snapshot": meta["metric_snapshot"],
        "scoring_weights": meta["scoring_weights"],
        "constraints": meta["constraints"],
        "collaborative_backend": meta["collaborative_backend"],
        "semantic_backend": meta.get("semantic_backend"),
    }

    elapsed = (time.perf_counter() - start_ts) * 1000
    diagnostics = {
        "input_counts": {
            "candidates": len(payload.get("candidates") or []),
            "content_vectors": len(payload.get("content_vectors") or []),
            "svd_factors": len(payload.get("svd_factors") or []),
        },
        "api_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "model": LLM_MODEL,
        "ranking_version": RANKING_VERSION,
        "collaborative_backend": meta["collaborative_backend"],
        "latency_ms": round(elapsed, 2),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    return {
        "agent_id": AGENT_ID,
        "ranking_version": RANKING_VERSION,
        "outputs": outputs,
        "diagnostics": diagnostics,
    }


def _render_summary(result: Dict[str, Any]) -> str:
    outputs = result.get("outputs") or {}
    ranking = outputs.get("ranking") or []
    metrics = outputs.get("metric_snapshot") or {}
    if not ranking:
        return "No recommendations ranked"
    return (
        f"Top recommendation: {ranking[0].get('book_id')} | "
        f"Items: {len(ranking)} | "
        f"Avg score: {metrics.get('avg_composite_score', 0)}"
    )


def _finalize_task(task_id: str, result: Dict[str, Any]) -> Task:
    summary = _render_summary(result)
    product = Product(
        id=str(uuid.uuid4()),
        name="recommendation-ranking",
        description="Ranked recommendation list with explanations and metrics",
        dataItems=[StructuredDataItem(data=result), TextDataItem(text=summary)],
    )
    TaskManager.set_products(task_id, [product])
    TaskManager.update_task_status(
        task_id,
        TaskState.Completed,
        data_items=[TextDataItem(text="Recommendation ranking complete")],
    )
    _RANKING_CONTEXT.pop(task_id, None)
    return TaskManager.get_task(task_id)


def _set_awaiting_input(task_id: str, missing: List[str]) -> Task:
    TaskManager.update_task_status(
        task_id,
        TaskState.AwaitingInput,
        data_items=[TextDataItem(text=f"missing_fields: {', '.join(missing)}")],
    )
    return TaskManager.get_task(task_id)


def _fail_task(task_id: str, reason: str) -> Task:
    TaskManager.update_task_status(
        task_id,
        TaskState.Failed,
        data_items=[TextDataItem(text=reason)],
    )
    _RANKING_CONTEXT.pop(task_id, None)
    return TaskManager.get_task(task_id)


async def handle_start(message: Message, existing_task: Optional[Task]) -> Task:
    if existing_task:
        return existing_task
    task = TaskManager.create_task(message, initial_state=TaskState.Working)
    payload = _merge_payload(task.id, _parse_payload(message))
    missing = _validate_payload(payload)
    if missing:
        logger.info("event=awaiting_input task_id=%s missing=%s", task.id, missing)
        return _set_awaiting_input(task.id, missing)
    try:
        result = await _analyze_ranking(payload)
        return _finalize_task(task.id, result)
    except Exception as exc:  # pragma: no cover
        logger.exception("event=ranking_failed task_id=%s", task.id)
        return _fail_task(task.id, f"analysis failed: {exc}")


async def handle_continue(message: Message, task: Task) -> Task:
    TaskManager.add_message_to_history(task.id, message)
    if task.status.state not in {TaskState.AwaitingInput, TaskState.Working}:
        return task

    payload = _merge_payload(task.id, _parse_payload(message))
    missing = _validate_payload(payload)
    if missing:
        logger.info("event=awaiting_input_continue task_id=%s missing=%s", task.id, missing)
        return _set_awaiting_input(task.id, missing)

    TaskManager.update_task_status(task.id, TaskState.Working, data_items=[TextDataItem(text="ranking")])
    try:
        result = await _analyze_ranking(payload)
        return _finalize_task(task.id, result)
    except Exception as exc:  # pragma: no cover
        logger.exception("event=ranking_continue_failed task_id=%s", task.id)
        return _fail_task(task.id, f"analysis failed: {exc}")


def _cancel_handler(message: Message, task: Task) -> Task:
    _RANKING_CONTEXT.pop(task.id, None)
    TaskManager.add_message_to_history(task.id, message)
    if task.status.state in {
        TaskState.Completed,
        TaskState.Canceled,
        TaskState.Failed,
        TaskState.Rejected,
    }:
        return task
    return TaskManager.update_task_status(task.id, TaskState.Canceled)


agent_handlers = CommandHandlers(
    on_start=handle_start,
    on_continue=handle_continue,
    on_cancel=_cancel_handler,
)

add_aip_rpc_router(app, AIP_ENDPOINT, agent_handlers)


if __name__ == "__main__":
    import uvicorn
    from acps_aip.mtls_config import load_mtls_context, build_uvicorn_ssl_kwargs

    host = os.getenv("REC_RANKING_HOST", "0.0.0.0")
    port = int(os.getenv("REC_RANKING_PORT", "8213"))
    config_path = os.getenv("REC_RANKING_MTLS_CONFIG_PATH", _ACS_JSON_PATH)
    cert_dir = os.getenv("AGENT_MTLS_CERT_DIR")

    ssl_context = load_mtls_context(config_path, purpose="server", cert_dir=cert_dir)
    ssl_kwargs = build_uvicorn_ssl_kwargs(config_path, cert_dir=cert_dir) if ssl_context else {}

    uvicorn.run(
        "agents.rec_ranking_agent.rec_ranking_agent:app",
        host=host,
        port=port,
        **ssl_kwargs,
    )
