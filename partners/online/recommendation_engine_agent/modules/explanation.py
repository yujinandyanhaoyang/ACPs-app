from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List

from base import call_openai_chat


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_text_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        items = value
    elif _clean_text(value):
        items = [value]
    else:
        items = []
    out: List[str] = []
    for item in items:
        text = _clean_text(item)
        if text:
            out.append(text)
    return out


def _format_list(value: Any, *, empty: str = "not provided") -> str:
    items = _clean_text_list(value)
    return ", ".join(items) if items else empty


def _normalize_locale(value: Any) -> str:
    text = _clean_text(value).lower().replace("-", "_")
    if not text:
        return ""
    prefix = text.split("_", 1)[0]
    mapping = {
        "en": "English",
        "zh": "Chinese",
        "ja": "Japanese",
        "ko": "Korean",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "pt": "Portuguese",
        "it": "Italian",
        "ru": "Russian",
        "ar": "Arabic",
    }
    return mapping.get(prefix, text)


def _extract_prompt_context(payload: Dict[str, Any] | None, row: Dict[str, Any], description: str) -> Dict[str, Any]:
    payload = payload or {}
    user_profile = payload.get("user_profile") if isinstance(payload.get("user_profile"), dict) else {}
    intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}

    preferred_genres = (
        payload.get("preferred_genres")
        or intent.get("preferred_genres")
        or user_profile.get("preferred_genres")
        or row.get("matched_prefs")
        or []
    )
    reading_history = (
        payload.get("reading_history")
        or payload.get("history")
        or user_profile.get("reading_history")
        or user_profile.get("history")
        or []
    )
    user_language = (
        _normalize_locale(payload.get("user_language"))
        or _normalize_locale(payload.get("preferred_language"))
        or _normalize_locale(payload.get("language"))
        or _normalize_locale(payload.get("locale"))
        or _normalize_locale(user_profile.get("language"))
        or _normalize_locale(user_profile.get("preferred_language"))
        or "English"
    )

    description_text = _clean_text(description)
    return {
        "preferred_genres": _format_list(preferred_genres),
        "reading_history": _format_list(reading_history),
        "user_language": user_language,
        "description_is_short": len(description_text) < 80,
    }


def assess_confidence(preliminary_list: List[Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for row in preliminary_list:
        book_id = str(row.get("book_id") or "")
        if not book_id:
            continue

        conf = 0.0
        if _safe_float(row.get("content_sim"), 0.0) > 0.5:
            conf += 0.30

        cf_neighbors = row.get("cf_neighbors")
        cf_neighbors_present = (
            (isinstance(cf_neighbors, list) and len(cf_neighbors) > 0)
            or _safe_float(row.get("cf_score"), 0.0) > 0.0
        )
        if cf_neighbors_present:
            conf += 0.30

        matched = row.get("matched_prefs")
        if isinstance(matched, list) and matched:
            conf += 0.20

        kg_features = row.get("kg_features")
        kg_present = (isinstance(kg_features, list) and kg_features) or (isinstance(row.get("kg_refs"), list) and row.get("kg_refs"))
        if kg_present:
            conf += 0.20

        out[book_id] = round(max(0.0, min(1.0, conf)), 6)

    return out


def _fallback_rationale(
    item: Dict[str, Any],
    fallback_template: str,
    prompt_context: Dict[str, Any] | None = None,
) -> str:
    title = str(item.get("title") or item.get("book_id") or "this book")
    author = str(item.get("author") or "the author")
    genres = item.get("genres") if isinstance(item.get("genres"), list) else []
    genre_tags = ", ".join(str(g) for g in genres if str(g).strip()) or "general interest"
    prompt_context = prompt_context or {}
    description = "" if prompt_context.get("description_is_short") else str(item.get("description") or "")
    try:
        return fallback_template.format(
            title=title,
            author=author,
            genre_tags=genre_tags,
            preferred_genres=prompt_context.get("preferred_genres") or genre_tags,
            reading_history=prompt_context.get("reading_history") or "not provided",
            description=description,
        )
    except KeyError:
        return f'We recommend "{title}" by {author}.'


async def _generate_one(
    row: Dict[str, Any],
    *,
    main_template: str,
    fallback_template: str,
    payload: Dict[str, Any] | None = None,
    user_query: str = "",
    description: str = "",
    use_llm: bool,
    llm_model: str,
    llm_temperature: float,
    llm_max_tokens: int,
) -> Dict[str, Any]:
    book_id = str(row.get("book_id") or "")
    title = str(row.get("title") or book_id)
    author = str(row.get("author") or "Unknown")
    genres = row.get("genres") if isinstance(row.get("genres"), list) else []
    genre_tags = ", ".join(str(g) for g in genres if str(g).strip()) or "N/A"
    content_similarity = _safe_float(row.get("content_sim"), 0.0)
    cf_evidence = "available" if _safe_float(row.get("cf_score"), 0.0) > 0 else "not available"
    matched = row.get("matched_prefs") if isinstance(row.get("matched_prefs"), list) else []
    matched_preferences = ", ".join(str(m) for m in matched if str(m).strip()) or "N/A"
    description_text = str(description or "No description available.")
    query_text = str(user_query or "")
    prompt_context = _extract_prompt_context(payload, row, description_text)

    rationale = _fallback_rationale(row, fallback_template, prompt_context)
    source = "fallback"
    if use_llm and main_template.strip():
        prompt = main_template.format(
            title=title,
            author=author,
            genre_tags=genre_tags,
            content_similarity=content_similarity,
            cf_evidence=cf_evidence,
            matched_preferences=matched_preferences,
            description=description_text,
            query=query_text,
            preferred_genres=prompt_context["preferred_genres"],
            reading_history=prompt_context["reading_history"],
            user_language=prompt_context["user_language"],
            description_is_short="true" if prompt_context["description_is_short"] else "false",
        )
        try:
            raw = await call_openai_chat(
                [
                    {"role": "system", "content": "You generate concise personalized recommendation rationales."},
                    {"role": "user", "content": prompt},
                ],
                model=llm_model,
                temperature=llm_temperature,
                max_tokens=llm_max_tokens,
            )
            text = str(raw or "").strip()
            if text:
                rationale = text
                source = "llm"
        except Exception:
            source = "fallback"

    return {
        "book_id": book_id,
        "justification": rationale,
        "source": source,
    }


async def generate_rationale(
    final_list: List[Dict[str, Any]],
    prompts: Dict[str, str],
    llm_model: str,
    llm_temperature: float,
    llm_max_tokens: int,
    payload: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    main_template = str(prompts.get("main") or "")
    fallback_template = str(
        prompts.get("fallback")
        or 'Because your preferred genres are {preferred_genres} and your reading history includes {reading_history}, "{title}" by {author} is a strong match for {genre_tags}. {description}'
    )

    _llm_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("LLM_API_KEY")
        or ""
    )
    use_llm = bool(_llm_key.strip()) and bool(main_template.strip())
    user_query = str((payload or {}).get("query") or "")
    tasks = [
        _generate_one(
            row,
            main_template=main_template,
            fallback_template=fallback_template,
            payload=payload,
            user_query=user_query,
            description=str(row.get("description") or ""),
            use_llm=use_llm,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
            llm_max_tokens=llm_max_tokens,
        )
        for row in final_list
    ]
    if not tasks:
        return []
    return await asyncio.gather(*tasks)
