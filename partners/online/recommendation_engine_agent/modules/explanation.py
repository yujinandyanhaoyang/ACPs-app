from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from typing import Any, Dict, List, Tuple
from pathlib import Path

from base import call_openai_chat


_METADATA_GAP_FILL_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


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


def _extract_json_obj(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    left = text.find("{")
    right = text.rfind("}")
    if left >= 0 and right > left:
        try:
            parsed = json.loads(text[left : right + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


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


def _load_reading_history_titles(user_id: str, limit: int = 10) -> List[str]:
    uid = str(user_id or "").strip()
    if not uid:
        return []

    db_path = _PROJECT_ROOT / "data" / "recommendation_runtime.db"
    if not db_path.exists():
        return []

    book_ids: List[str] = []
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT book_id, rating, created_at
                FROM user_behavior_events
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (uid, max(1, int(limit))),
            ).fetchall()
        for row in rows:
            try:
                rating = float(row["rating"]) if row["rating"] is not None else 0.0
            except Exception:
                rating = 0.0
            if rating >= 4.0:
                book_id = str(row["book_id"] or "").strip()
                if book_id:
                    book_ids.append(book_id)
    except Exception:
        return []

    if not book_ids:
        return []

    try:
        from services.book_retrieval import _load_books_by_id

        books_by_id = _load_books_by_id()
    except Exception:
        books_by_id = {}

    titles: List[str] = []
    seen: set[str] = set()
    for book_id in book_ids:
        if book_id in seen:
            continue
        seen.add(book_id)
        title = str((books_by_id.get(book_id) or {}).get("title") or book_id).strip()
        if title:
            titles.append(title)
    return titles[: max(1, int(limit))]


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
    if not reading_history:
        reading_history = _load_reading_history_titles(str(payload.get("user_id") or ""), limit=10)
    description_text = _clean_text(description)
    return {
        "preferred_genres": _format_list(preferred_genres),
        "reading_history": _format_list(reading_history),
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


def _needs_metadata_gap_fill(row: Dict[str, Any]) -> bool:
    description = str(row.get("description") or "").strip()
    author = str(row.get("author") or "").strip()
    genres = row.get("genres") if isinstance(row.get("genres"), list) else []
    return (not author) or (not genres) or (len(description) < 20)


def _fallback_gap_fill(row: Dict[str, Any]) -> Dict[str, Any]:
    title = str(row.get("title") or row.get("book_id") or "")
    author = str(row.get("author") or "佚名").strip() or "佚名"
    genres = row.get("genres") if isinstance(row.get("genres"), list) else []
    genre_tags_zh = [str(g).strip() for g in genres if str(g).strip()]
    if not genre_tags_zh:
        genre_tags_zh = ["文学", "小说"]
    description = str(row.get("description") or "").strip()
    summary = description[:50] if description else f"围绕《{title}》的作品，风格与题材值得关注(AI推断)"
    return {
        "author_display": author,
        "genre_tags_zh": genre_tags_zh[:2],
        "summary_zh": summary if summary.endswith("(AI推断)") else f"{summary}(AI推断)" if not description else summary,
        "title_zh": title,
    }


async def _gap_fill_metadata(
    row: Dict[str, Any],
    *,
    gap_fill_template: str,
    llm_model: str,
    llm_temperature: float,
    llm_max_tokens: int,
    session_key: str,
) -> Dict[str, Any]:
    book_id = str(row.get("book_id") or "").strip()
    if not book_id or not _needs_metadata_gap_fill(row):
        return {
            "metadata_gap_filled": False,
            "author_display": str(row.get("author") or "佚名").strip() or "佚名",
            "genre_tags_zh": row.get("genres") if isinstance(row.get("genres"), list) else [],
            "summary_zh": str(row.get("description") or ""),
            "title_zh": str(row.get("title") or book_id),
        }

    cache_key = (session_key, book_id)
    cached = _METADATA_GAP_FILL_CACHE.get(cache_key)
    if cached is not None:
        return {**cached, "metadata_gap_filled": True}

    prompt = gap_fill_template.format(
        title=str(row.get("title") or book_id),
        author=str(row.get("author") or ""),
        description=str(row.get("description") or ""),
    )
    result: Dict[str, Any] = {}
    if gap_fill_template.strip():
        try:
            raw = await call_openai_chat(
                [
                    {"role": "system", "content": "你是一个严格输出 JSON 的图书元数据补全助手。"},
                    {"role": "user", "content": prompt},
                ],
                model=llm_model,
                temperature=llm_temperature,
                max_tokens=llm_max_tokens,
            )
            parsed = _extract_json_obj(raw)
            if parsed:
                result = parsed
        except Exception:
            result = {}

    if not result:
        result = _fallback_gap_fill(row)

    author_display = str(result.get("author_display") or row.get("author") or "佚名").strip() or "佚名"
    title_zh = str(result.get("title_zh") or row.get("title") or book_id).strip() or str(row.get("title") or book_id)
    summary_zh = str(result.get("summary_zh") or row.get("description") or "").strip()
    genre_tags_zh = result.get("genre_tags_zh") if isinstance(result.get("genre_tags_zh"), list) else []
    genre_tags_zh = [str(item).strip() for item in genre_tags_zh if str(item).strip()]
    if not genre_tags_zh:
        genre_tags_zh = [str(item).strip() for item in (row.get("genres") if isinstance(row.get("genres"), list) else []) if str(item).strip()]

    normalized = {
        "metadata_gap_filled": True,
        "author_display": author_display,
        "genre_tags_zh": genre_tags_zh,
        "summary_zh": summary_zh,
        "title_zh": title_zh,
    }
    _METADATA_GAP_FILL_CACHE[cache_key] = normalized
    return normalized


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
    title = str(row.get("title_display") or row.get("title") or book_id)
    author = str(row.get("author_display") or row.get("author") or "佚名")
    genres = row.get("genre_tags_zh") if isinstance(row.get("genre_tags_zh"), list) and row.get("genre_tags_zh") else (
        row.get("genres") if isinstance(row.get("genres"), list) else []
    )
    genre_tags = ", ".join(str(g) for g in genres if str(g).strip()) or "题材待补全"
    content_similarity = _safe_float(row.get("content_sim"), 0.0)
    cf_evidence = "available" if _safe_float(row.get("cf_score"), 0.0) > 0 else "not available"
    matched = row.get("matched_prefs") if isinstance(row.get("matched_prefs"), list) else []
    matched_preferences = ", ".join(str(m) for m in matched if str(m).strip()) or "N/A"
    description_text = str(description or "暂无简介")
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
            description_is_short="true" if prompt_context["description_is_short"] else "false",
        )
        try:
            raw = await call_openai_chat(
                [
                {"role": "system", "content": "你是专业图书推荐助手，请严格用中文输出推荐理由。"},
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
    gap_fill_template = str(prompts.get("metadata_gap_fill") or "")

    _llm_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("LLM_API_KEY")
        or ""
    )
    use_llm = bool(_llm_key.strip()) and bool(main_template.strip())
    user_query = str((payload or {}).get("query") or "")
    session_key = str((payload or {}).get("session_id") or "__default__")

    enriched_rows: List[Dict[str, Any]] = []
    gap_fill_tasks = [
        _gap_fill_metadata(
            row,
            gap_fill_template=gap_fill_template,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
            llm_max_tokens=llm_max_tokens,
            session_key=session_key,
        )
        for row in final_list
    ]
    gap_fill_results = await asyncio.gather(*gap_fill_tasks) if gap_fill_tasks else []

    for row, gap_fill in zip(final_list, gap_fill_results):
        enriched = dict(row)
        enriched["title_display"] = str(gap_fill.get("title_zh") or enriched.get("title") or enriched.get("book_id") or "")
        enriched["author_display"] = str(gap_fill.get("author_display") or enriched.get("author") or "佚名")
        enriched["genre_tags_zh"] = gap_fill.get("genre_tags_zh") if isinstance(gap_fill.get("genre_tags_zh"), list) else []
        enriched["summary_zh"] = str(gap_fill.get("summary_zh") or enriched.get("description") or "")
        enriched["metadata_gap_filled"] = bool(gap_fill.get("metadata_gap_filled"))
        enriched_rows.append(enriched)

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
        for row in enriched_rows
    ]
    if not tasks:
        return []
    explanations = await asyncio.gather(*tasks)
    merged: List[Dict[str, Any]] = []
    for row, explanation in zip(enriched_rows, explanations):
        merged.append(
            {
                **explanation,
                "title_display": row.get("title_display") or row.get("title") or row.get("book_id"),
                "author_display": row.get("author_display") or row.get("author") or "佚名",
                "genre_tags_zh": row.get("genre_tags_zh") if isinstance(row.get("genre_tags_zh"), list) else [],
                "summary_zh": row.get("summary_zh") or "",
                "metadata_gap_filled": bool(row.get("metadata_gap_filled")),
            }
        )
    return merged
