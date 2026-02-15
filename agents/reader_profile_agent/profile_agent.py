import os
import sys
import json
import uuid
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI
from dotenv import load_dotenv

_CURRENT_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, os.pardir, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from base import get_agent_logger, extract_text_from_message, call_openai_chat
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

AGENT_ID = os.getenv("READER_PROFILE_AGENT_ID", "reader_profile_agent_001")
AIP_ENDPOINT = os.getenv("READER_PROFILE_AGENT_ENDPOINT", "/reader-profile/rpc")
LOG_LEVEL = os.getenv("READER_PROFILE_AGENT_LOG_LEVEL", "INFO").upper()
LLM_MODEL = os.getenv("PROFILE_EMBED_MODEL", os.getenv("OPENAI_MODEL", "Doubao-pro-32k"))
EMBEDDING_VERSION = os.getenv("READER_PROFILE_EMBEDDING_VERSION", "reader_profile_v1")
DEFAULT_GENRE_PRIORS = os.getenv(
    "READER_PROFILE_DEFAULT_GENRES",
    "fiction:0.25,science_fiction:0.2,history:0.15,nonfiction:0.15,fantasy:0.15,mystery:0.1",
)
DEFAULT_SCENARIO = os.getenv("READER_PROFILE_DEFAULT_SCENARIO", "warm")

logger = get_agent_logger("agent.reader_profile", "READER_PROFILE_AGENT_LOG_LEVEL", LOG_LEVEL)

app = FastAPI(
    title="Reader Profile Agent",
    description="ACPs-compliant agent that synthesizes user preference vectors for reading journeys.",
)

_PROFILE_CONTEXT: dict[str, Dict[str, Any]] = {}


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
    base_payload = _PROFILE_CONTEXT.get(task_id, {})
    merged: Dict[str, Any] = {**base_payload}
    for key, value in new_payload.items():
        if value in (None, ""):
            continue
        if key in {"history", "reviews"}:
            existing = merged.get(key) or []
            if isinstance(value, list):
                merged[key] = existing + value
            else:
                merged[key] = existing
        elif key == "user_profile":
            existing_profile = merged.get("user_profile") or {}
            if isinstance(value, dict):
                merged["user_profile"] = {**existing_profile, **value}
        else:
            merged[key] = value
    _PROFILE_CONTEXT[task_id] = merged
    return merged


def _parse_priors() -> Dict[str, float]:
    priors: Dict[str, float] = {}
    for chunk in DEFAULT_GENRE_PRIORS.split(","):
        if not chunk:
            continue
        if ":" in chunk:
            name, val = chunk.split(":", 1)
            try:
                priors[name.strip().lower()] = float(val)
            except ValueError:
                continue
        else:
            priors[chunk.strip().lower()] = 1.0
    total = sum(priors.values())
    if total <= 0:
        return {}
    return {k: round(v / total, 3) for k, v in priors.items()}


def _validate_payload(payload: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    user_profile = payload.get("user_profile")
    history = payload.get("history")
    reviews = payload.get("reviews")
    if not isinstance(user_profile, dict) or not user_profile:
        missing.append("user_profile")
    if not (isinstance(history, list) and history) and not (isinstance(reviews, list) and reviews):
        missing.append("history|reviews")
    return missing


def _normalize(
    weights: Dict[str, float], fallback: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    positive_items = {k: max(v, 0.0) for k, v in weights.items() if max(v, 0.0) > 0}
    total = sum(positive_items.values())
    if total <= 0:
        return fallback or {}
    normalized = {k: round(v / total, 3) for k, v in positive_items.items()}
    return dict(sorted(normalized.items(), key=lambda item: item[1], reverse=True))


def _summarize_sentiment(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not reviews:
        return {"label": "neutral", "score": 0.0, "highlights": []}
    total = 0.0
    highlights: List[str] = []
    for review in reviews:
        rating = review.get("rating") or 0
        total += float(rating) - 3.0
        text = (review.get("text") or "").strip()
        if text:
            highlights.append(text[:80])
    avg = total / (len(reviews) * 2.0)
    avg = max(min(avg, 1.0), -1.0)
    label = "positive" if avg > 0.1 else "negative" if avg < -0.1 else "neutral"
    return {"label": label, "score": round(avg, 3), "highlights": highlights[:3]}


def _derive_format_preferences(history: List[Dict[str, Any]]) -> Dict[str, float]:
    counts: Dict[str, float] = defaultdict(float)
    for entry in history:
        fmt = (entry.get("format") or "").lower().strip()
        if not fmt:
            continue
        weight = float(entry.get("rating", 3)) / 5.0
        counts[fmt] += weight
    return _normalize(counts, fallback={})


def _derive_language_distribution(history: List[Dict[str, Any]]) -> Dict[str, float]:
    counts: Dict[str, float] = defaultdict(float)
    for entry in history:
        lang = (entry.get("language") or "").lower().strip() or "unknown"
        counts[lang] += 1.0
    return _normalize(counts, fallback={})


def _derive_genre_weights(history: List[Dict[str, Any]]) -> Dict[str, float]:
    counts: Dict[str, float] = defaultdict(float)
    for entry in history:
        genres = entry.get("genres") or []
        rating = float(entry.get("rating", 3)) / 5.0
        for genre in genres:
            g = str(genre).lower().strip()
            if not g:
                continue
            counts[g] += rating
    return _normalize(counts, fallback=_parse_priors())


def _derive_tone_preferences(history: List[Dict[str, Any]]) -> Dict[str, float]:
    counts: Dict[str, float] = defaultdict(float)
    for entry in history:
        tone = entry.get("tone") or entry.get("mood")
        if not tone:
            continue
        counts[str(tone).lower().strip()] += 1.0
    return _normalize(counts, fallback={})


def _derive_theme_preferences(history: List[Dict[str, Any]]) -> Dict[str, float]:
    counts: Dict[str, float] = defaultdict(float)
    for entry in history:
        themes = entry.get("themes") or []
        rating = float(entry.get("rating", 3)) / 5.0
        for theme in themes:
            label = str(theme).lower().strip()
            if not label:
                continue
            counts[label] += rating
    return _normalize(counts, fallback={})


def _derive_pacing_preferences(history: List[Dict[str, Any]]) -> Dict[str, float]:
    counts: Dict[str, float] = defaultdict(float)
    for entry in history:
        pacing = entry.get("pacing") or entry.get("tempo")
        if not pacing:
            continue
        counts[str(pacing).lower().strip()] += 1.0
    return _normalize(counts, fallback={})


def _derive_difficulty_preferences(history: List[Dict[str, Any]]) -> Dict[str, float]:
    counts: Dict[str, float] = defaultdict(float)
    for entry in history:
        difficulty = entry.get("difficulty") or entry.get("complexity")
        page_count = entry.get("page_count") or entry.get("pages")
        if difficulty:
            label = str(difficulty).lower().strip()
        elif page_count:
            try:
                pages = int(page_count)
                if pages >= 500:
                    label = "advanced"
                elif pages >= 300:
                    label = "intermediate"
                else:
                    label = "beginner"
            except (TypeError, ValueError):
                label = "intermediate"
        else:
            continue
        counts[label] += float(entry.get("rating", 3)) / 5.0
    return _normalize(counts, fallback={})


def _collect_review_corpus(reviews: List[Dict[str, Any]]) -> str:
    corpus: List[str] = []
    for review in reviews[:5]:
        text = (review.get("text") or "").strip()
        if not text:
            continue
        corpus.append(text[:200])
    return "\n".join(corpus)


def _heuristic_keywords(payload: Dict[str, Any]) -> List[str]:
    history = payload.get("history") or []
    reviews = payload.get("reviews") or []
    pool: List[str] = []
    for entry in history:
        pool.extend(entry.get("genres") or [])
        pool.extend(entry.get("themes") or [])
    for review in reviews:
        text = (review.get("text") or "").lower().strip()
        if not text:
            continue
        tokens = [token.strip(",.!?\"')") for token in text.split() if len(token) >= 5]
        pool.extend(tokens[:2])
    seen: Set[str] = set()
    keywords: List[str] = []
    for word in pool:
        normalized = str(word).lower().strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(normalized)
        if len(keywords) >= 5:
            break
    return keywords or ["personalized", "reading"]


def _parse_keywords_response(raw: str) -> Dict[str, Any]:
    if not raw:
        return {"keywords": [], "intent_summary": ""}
    try:
        data = json.loads(raw)
        keywords = data.get("keywords")
        if isinstance(keywords, list):
            cleaned = [str(item).strip() for item in keywords if str(item).strip()]
        elif isinstance(data.get("plan"), str):
            cleaned = [data["plan"]]
        else:
            cleaned = []
        summary = (
            data.get("intent_summary")
            or data.get("summary")
            or data.get("intent")
            or data.get("plan")
            or ""
        )
    except json.JSONDecodeError:
        tokens = [segment.strip() for segment in raw.replace("\n", ",").split(",") if segment.strip()]
        cleaned = tokens
        summary = raw[:200]
    return {"keywords": cleaned[:5], "intent_summary": summary}


async def _generate_intent_keywords(payload: Dict[str, Any]) -> Dict[str, Any]:
    heuristics = _heuristic_keywords(payload)
    api_key_present = bool(os.getenv("OPENAI_API_KEY"))
    if not api_key_present:
        return {
            "source": "heuristic",
            "keywords": heuristics,
            "intent_summary": "API key missing; using heuristic keywords",
            "model": None,
        }
    history = payload.get("history") or []
    reviews = payload.get("reviews") or []
    history_lines = []
    for entry in history[:5]:
        title = entry.get("title") or "unknown"
        genres = ", ".join(entry.get("genres") or [])
        themes = ", ".join(entry.get("themes") or [])
        rating = entry.get("rating", "?")
        history_lines.append(f"{title} | genres={genres or 'n/a'} | themes={themes or 'n/a'} | rating={rating}")
    prompt = (
        "You are an assistant that extracts latent reading intents and topical keywords. "
        "Return JSON with keys 'keywords' (list of <=5 lowercase strings) and 'intent_summary' (string).\n"
        f"History samples:\n{os.linesep.join(history_lines) or 'none'}\n"
        f"Recent reviews:\n{_collect_review_corpus(reviews) or 'none'}"
    )
    try:
        raw = await call_openai_chat(
            [
                {"role": "system", "content": "Summarize user intent for reading recommendations."},
                {"role": "user", "content": prompt},
            ],
            model=LLM_MODEL,
            temperature=0.2,
            max_tokens=256,
        )
        parsed = _parse_keywords_response(raw)
        if parsed["keywords"]:
            parsed.update({"source": "llm", "model": LLM_MODEL})
            return parsed
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("event=intent_keywords_llm_failed error=%s", exc)
    return {
        "source": "heuristic",
        "keywords": heuristics,
        "intent_summary": "LLM generation failed; using heuristics",
        "model": LLM_MODEL,
    }


def _derive_cold_start_hints(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    history = payload.get("history") or []
    reviews = payload.get("reviews") or []
    hints: List[Dict[str, Any]] = []
    if len(history) < 3:
        priors = _parse_priors()
        top_genres = list(priors.keys())[:3]
        hints.append(
            {
                "reason": "history_insufficient",
                "suggestion": f"Seed with canonical {', '.join(top_genres)} titles",
            }
        )
    if not reviews:
        hints.append(
            {
                "reason": "missing_reviews",
                "suggestion": "Prompt user for recent favorites to improve sentiment calibration",
            }
        )
    if not hints:
        hints.append(
            {
                "reason": "ready",
                "suggestion": "Sufficient data for personalized recommendations",
            }
        )
    return hints


def _render_summary(result: Dict[str, Any]) -> str:
    pref = result.get("preference_vector", {})
    genres = pref.get("genres", {})
    top_genres = list(genres.keys())[:3]
    sentiment = result.get("sentiment_summary", {})
    hints = result.get("cold_start_hints", [])
    first_hint = hints[0]["suggestion"] if hints else ""
    return (
        f"Top genres: {', '.join(top_genres) or 'N/A'} | "
        f"Sentiment: {sentiment.get('label', 'neutral')} ({sentiment.get('score', 0)}) | "
        f"Next step: {first_hint}"
    )


async def _analyze_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    start_ts = time.perf_counter()
    history = payload.get("history") or []
    reviews = payload.get("reviews") or []
    preference_vector = {
        "genres": _derive_genre_weights(history),
        "formats": _derive_format_preferences(history),
        "languages": _derive_language_distribution(history),
        "tones": _derive_tone_preferences(history),
        "themes": _derive_theme_preferences(history),
        "pacing": _derive_pacing_preferences(history),
        "difficulty": _derive_difficulty_preferences(history),
        "scenario": payload.get("scenario") or DEFAULT_SCENARIO,
    }
    intent_keywords = await _generate_intent_keywords(payload)
    sentiment_summary = _summarize_sentiment(reviews)
    average_rating = (
        round(sum((entry.get("rating") or 0) for entry in history) / len(history), 2)
        if history
        else None
    )
    diagnostics = {
        "input_counts": {
            "history": len(history),
            "reviews": len(reviews),
            "genres": len(preference_vector["genres"]),
        },
        "average_rating": average_rating,
        "model": LLM_MODEL,
        "intent_source": intent_keywords.get("source"),
        "environment": {
            "api_key_present": bool(os.getenv("OPENAI_API_KEY")),
            "endpoint": AIP_ENDPOINT,
            "model": LLM_MODEL,
        },
        "embedding_version": EMBEDDING_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    elapsed = (time.perf_counter() - start_ts) * 1000
    diagnostics["latency_ms"] = round(elapsed, 2)
    return {
        "agent_id": AGENT_ID,
        "embedding_version": EMBEDDING_VERSION,
        "preference_vector": preference_vector,
        "sentiment_summary": sentiment_summary,
        "intent_keywords": intent_keywords,
        "cold_start_hints": _derive_cold_start_hints(payload),
        "diagnostics": diagnostics,
    }


def _finalize_task(task_id: str, result: Dict[str, Any]) -> Task:
    summary = _render_summary(result)
    structured_item = StructuredDataItem(data=result)
    text_item = TextDataItem(text=summary)
    product = Product(
        id=str(uuid.uuid4()),
        name="reader-profile-analysis",
        description="Normalized preference vector and narrative summary",
        dataItems=[structured_item, text_item],
    )
    TaskManager.set_products(task_id, [product])
    TaskManager.update_task_status(
        task_id,
        TaskState.Completed,
        data_items=[TextDataItem(text="Profile analysis complete")],
    )
    _PROFILE_CONTEXT.pop(task_id, None)
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
    _PROFILE_CONTEXT.pop(task_id, None)
    return TaskManager.get_task(task_id)


async def handle_start(message: Message, existing_task: Task | None) -> Task:
    if existing_task:
        return existing_task
    task = TaskManager.create_task(message, initial_state=TaskState.Working)
    payload = _merge_payload(task.id, _parse_payload(message))
    missing = _validate_payload(payload)
    if missing:
        logger.info("event=awaiting_input task_id=%s missing=%s", task.id, missing)
        return _set_awaiting_input(task.id, missing)
    try:
        result = await _analyze_profile(payload)
        return _finalize_task(task.id, result)
    except Exception as exc:  # pragma: no cover - safety fallback
        logger.exception("event=profile_analysis_failed task_id=%s", task.id)
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
    TaskManager.update_task_status(
        task.id, TaskState.Working, data_items=[TextDataItem(text="profiling")]
    )
    try:
        result = await _analyze_profile(payload)
        return _finalize_task(task.id, result)
    except Exception as exc:  # pragma: no cover
        logger.exception("event=profile_analysis_failed_continue task_id=%s", task.id)
        return _fail_task(task.id, f"analysis failed: {exc}")


def _cancel_handler(message: Message, task: Task) -> Task:
    _PROFILE_CONTEXT.pop(task.id, None)
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
