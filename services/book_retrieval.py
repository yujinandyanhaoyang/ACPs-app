from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MERGED_DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "books_master_merged.jsonl"
GOODREADS_DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "goodreads" / "books_master.jsonl"
ZH_DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "books_master_zh.jsonl"
BOOKS_MIN_DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "books_min.jsonl"
DATASET_ENV_KEY = "BOOK_RETRIEVAL_DATASET_PATH"
DATASET_ENV_KEY_EN = "BOOK_RETRIEVAL_DATASET_PATH_EN"
DATASET_ENV_KEY_ZH = "BOOK_RETRIEVAL_DATASET_PATH_ZH"
ROUTING_MODE_ENV_KEY = "BOOK_RETRIEVAL_ROUTING_MODE"
MIN_PRIMARY_HITS_ENV_KEY = "BOOK_RETRIEVAL_MIN_PRIMARY_HITS"
VARIANT_ENV_KEY = "BOOK_RETRIEVAL_VARIANT"

_EN_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "about",
}
_ZH_STOP_CHARS = {"的", "了", "和", "是", "在", "我", "想", "看", "一些", "请", "推荐"}


def _resolve_dataset_path(dataset_path: Path | None = None) -> Path:
    if dataset_path is not None:
        return dataset_path

    env_path = str(os.getenv(DATASET_ENV_KEY) or "").strip()
    if env_path:
        return Path(env_path)

    if MERGED_DATASET_PATH.exists():
        return MERGED_DATASET_PATH
    if GOODREADS_DATASET_PATH.exists():
        return GOODREADS_DATASET_PATH
    return BOOKS_MIN_DATASET_PATH


def _resolve_dataset_path_en() -> Path:
    env_path = str(os.getenv(DATASET_ENV_KEY_EN) or "").strip()
    if env_path:
        return Path(env_path)
    return GOODREADS_DATASET_PATH


def _resolve_dataset_path_zh() -> Path:
    env_path = str(os.getenv(DATASET_ENV_KEY_ZH) or "").strip()
    if env_path:
        return Path(env_path)
    return ZH_DATASET_PATH


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text))


def detect_query_language(query: str) -> Dict[str, Any]:
    text = unicodedata.normalize("NFKC", str(query or ""))
    letters = re.findall(r"[A-Za-z\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text)
    total_letters = len(letters)
    if total_letters == 0:
        return {
            "language": "mixed",
            "confidence": 0.0,
            "stats": {"cjk_ratio": 0.0, "latin_ratio": 0.0, "total_letters": 0},
        }

    cjk_chars = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    cjk_ratio = cjk_chars / max(1, total_letters)
    latin_ratio = latin_chars / max(1, total_letters)

    if cjk_chars > 0 and latin_chars > 0 and cjk_ratio >= 0.05:
        language = "mixed"
        confidence = abs(cjk_ratio - latin_ratio)
    elif cjk_ratio >= 0.25:
        language = "zh"
        confidence = min(1.0, cjk_ratio)
    elif latin_ratio >= 0.5:
        language = "en"
        confidence = min(1.0, latin_ratio)
    else:
        language = "mixed"
        confidence = abs(cjk_ratio - latin_ratio)

    return {
        "language": language,
        "confidence": round(confidence, 4),
        "stats": {
            "cjk_ratio": round(cjk_ratio, 4),
            "latin_ratio": round(latin_ratio, 4),
            "total_letters": total_letters,
        },
    }


def _tokenize_english(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return {
        tok
        for tok in re.findall(r"[\w]+", normalized, flags=re.UNICODE)
        if len(tok) >= 2 and tok not in _EN_STOPWORDS
    }


def _tokenize_chinese(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text)
    cjk_chunks = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", normalized)
    tokens: set[str] = set()
    for chunk in cjk_chunks:
        cleaned = "".join(ch for ch in chunk if ch not in _ZH_STOP_CHARS)
        if len(cleaned) >= 2:
            tokens.add(cleaned)
        for i in range(len(cleaned) - 1):
            bi = cleaned[i : i + 2]
            if len(bi) == 2:
                tokens.add(bi)
        for i in range(len(cleaned) - 2):
            tri = cleaned[i : i + 3]
            if len(tri) == 3:
                tokens.add(tri)
    return tokens


def _tokenize_multilingual(text: str, lang_hint: str | None = None) -> set[str]:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    hint = (lang_hint or "").lower().strip()
    detected = detect_query_language(normalized)["language"] if hint not in {"zh", "en", "mixed"} else hint

    if detected == "zh" or _contains_cjk(normalized):
        zh_tokens = _tokenize_chinese(normalized)
        en_tokens = _tokenize_english(normalized)
        return {tok for tok in (zh_tokens | en_tokens) if len(tok) >= 2}
    return _tokenize_english(normalized)


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text or "")).lower())
    if not normalized:
        return set()
    if len(normalized) <= n:
        return {normalized}
    return {normalized[idx : idx + n] for idx in range(len(normalized) - n + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _normalize_book_language(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in {"zh", "cn", "chinese", "zh-cn", "zh-hans", "zh-hant"}:
        return "zh"
    if token in {"en", "english", "en-us", "en-gb"}:
        return "en"
    return "mixed"


def _language_boost(query_lang: str, book_lang: str) -> float:
    if query_lang == "mixed":
        if book_lang in {"zh", "en", "mixed"}:
            return 0.4
        return 0.0
    if query_lang == book_lang:
        return 1.0
    if book_lang == "mixed":
        return 0.4
    return 0.0


def _popularity_signal(book: Dict[str, Any]) -> float:
    candidates = [
        book.get("ratings_count"),
        book.get("rating_count"),
        book.get("work_ratings_count"),
        book.get("text_reviews_count"),
        book.get("popular_shelves_count"),
    ]
    raw = 0.0
    for item in candidates:
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if value > raw:
            raw = value
    if raw <= 0:
        return 0.0
    return min(1.0, (raw ** 0.5) / 100.0)


def _score_candidate(query: str, query_tokens: set[str], query_lang: str, book: Dict[str, Any]) -> Dict[str, float]:
    text = _book_text(book)
    book_tokens = _tokenize_multilingual(text, lang_hint=query_lang)
    lexical = len(query_tokens.intersection(book_tokens)) / max(1, len(query_tokens))

    sem_query = _char_ngrams(query, n=3)
    sem_book = _char_ngrams(text, n=3)
    semantic = _jaccard(sem_query, sem_book)

    book_lang = _normalize_book_language(book.get("language"))
    lang_boost = _language_boost(query_lang, book_lang)
    popularity = _popularity_signal(book)
    return {
        "lexical": min(1.0, max(0.0, lexical)),
        "semantic": min(1.0, max(0.0, semantic)),
        "language_boost": min(1.0, max(0.0, lang_boost)),
        "popularity": min(1.0, max(0.0, popularity)),
    }


def _dedup_and_rank(
    scored_rows: List[Dict[str, Any]],
    top_k: int,
    dedup_penalty: float = 0.25,
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    seen_canonical: set[str] = set()

    for row in scored_rows:
        book = row["book"]
        canonical = str(book.get("canonical_work_id") or "").strip()
        if canonical and canonical in seen_canonical:
            continue
        penalty = dedup_penalty if canonical and canonical in seen_canonical else 0.0

        final_score = (
            0.35 * row["lexical"]
            + 0.35 * row["semantic"]
            + 0.20 * row["language_boost"]
            + 0.10 * row["popularity"]
            - penalty
        )
        if final_score < 0:
            final_score = 0.0

        enriched = dict(book)
        enriched["lexical_score"] = round(row["lexical"], 4)
        enriched["semantic_score"] = round(row["semantic"], 4)
        enriched["language_boost"] = round(row["language_boost"], 4)
        enriched["popularity_score"] = round(row["popularity"], 4)
        enriched["dedup_penalty"] = round(penalty, 4)
        enriched["fusion_score"] = round(final_score, 4)
        selected.append(enriched)

        if canonical:
            seen_canonical.add(canonical)
        if len(selected) >= max(1, top_k):
            break

    return selected


def _book_text(book: Dict[str, Any]) -> str:
    title = str(book.get("title") or "")
    description = str(book.get("description") or "")
    genres = " ".join(str(g) for g in (book.get("genres") or []))
    author = str(book.get("author") or "")
    return f"{title} {author} {description} {genres}"


def _tokenize(text: str) -> set[str]:
    return _tokenize_multilingual(text)


def load_books(dataset_path: Path | None = None) -> List[Dict[str, Any]]:
    path = _resolve_dataset_path(dataset_path)
    if not path.exists():
        return []

    books: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            books.append(row)
    return books


def load_books_dual_corpus() -> Dict[str, List[Dict[str, Any]]]:
    shared_override = str(os.getenv(DATASET_ENV_KEY) or "").strip()
    if shared_override:
        shared = load_books(Path(shared_override))
        return {"en": shared, "zh": shared}

    en_path = _resolve_dataset_path_en()
    zh_path = _resolve_dataset_path_zh()
    return {
        "en": load_books(en_path) if en_path.exists() else [],
        "zh": load_books(zh_path) if zh_path.exists() else [],
    }


def retrieve_books_by_query_with_diagnostics(
    query: str,
    top_k: int = 8,
    route_mode: str | None = None,
    min_primary_hits: int | None = None,
    books_en: Sequence[Dict[str, Any]] | None = None,
    books_zh: Sequence[Dict[str, Any]] | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    mode = (route_mode or str(os.getenv(ROUTING_MODE_ENV_KEY) or "soft")).strip().lower()
    if mode not in {"strict", "soft", "agnostic"}:
        mode = "soft"

    if min_primary_hits is None:
        try:
            min_primary_hits = int(str(os.getenv(MIN_PRIMARY_HITS_ENV_KEY) or "5"))
        except ValueError:
            min_primary_hits = 5
    min_primary_hits = max(1, int(min_primary_hits))

    lang_meta = detect_query_language(query or "")
    q_lang = str(lang_meta.get("language") or "mixed")
    q_tokens = _tokenize_multilingual(query or "", lang_hint=q_lang)

    if books_en is None or books_zh is None:
        corpora = load_books_dual_corpus()
        en_pool = list(books_en) if books_en is not None else corpora["en"]
        zh_pool = list(books_zh) if books_zh is not None else corpora["zh"]
    else:
        en_pool = list(books_en)
        zh_pool = list(books_zh)

    primary_corpus = "mixed"
    secondary_used = False
    primary_pool: List[Dict[str, Any]]
    secondary_pool: List[Dict[str, Any]]

    if mode == "agnostic":
        primary_corpus = "agnostic"
        primary_pool = en_pool + zh_pool
        secondary_pool = []
    elif q_lang == "zh":
        primary_corpus = "zh"
        primary_pool = zh_pool
        secondary_pool = en_pool
    elif q_lang == "en":
        primary_corpus = "en"
        primary_pool = en_pool
        secondary_pool = zh_pool
    else:
        primary_corpus = "mixed"
        primary_pool = en_pool + zh_pool
        secondary_pool = []

    if not q_tokens:
        fallback = (primary_pool + secondary_pool)[: max(1, top_k)]
        return [dict(row) for row in fallback], {
            "detected_query_language": q_lang,
            "language_confidence": lang_meta.get("confidence", 0.0),
            "primary_corpus": primary_corpus,
            "fallback_used": False,
            "candidate_counts": {"en": len(en_pool), "zh": len(zh_pool)},
            "fusion_component_avgs": {"lexical": 0.0, "semantic": 0.0, "language_boost": 0.0, "popularity": 0.0},
            "routing_mode": mode,
            "min_primary_hits": min_primary_hits,
        }

    primary_scored: List[Dict[str, Any]] = []
    for row in primary_pool:
        score = _score_candidate(query, q_tokens, q_lang, row)
        primary_scored.append({"book": row, **score})
    primary_scored.sort(key=lambda item: (item["lexical"] + item["semantic"]), reverse=True)

    primary_relevant = [
        item
        for item in primary_scored
        if (item["lexical"] > 0.0 or item["semantic"] >= 0.04)
    ]

    combined_scored = list(primary_scored)
    if mode == "soft" and secondary_pool and len(primary_relevant) < min_primary_hits:
        secondary_used = True
        secondary_scored: List[Dict[str, Any]] = []
        for row in secondary_pool:
            score = _score_candidate(query, q_tokens, q_lang, row)
            secondary_scored.append({"book": row, **score})
        secondary_scored.sort(key=lambda item: (item["lexical"] + item["semantic"]), reverse=True)
        combined_scored.extend(secondary_scored)

    combined_scored.sort(
        key=lambda item: (
            0.35 * item["lexical"] + 0.35 * item["semantic"] + 0.20 * item["language_boost"] + 0.10 * item["popularity"]
        ),
        reverse=True,
    )

    selected = _dedup_and_rank(combined_scored, top_k=max(1, top_k), dedup_penalty=0.25)

    if combined_scored:
        lexical_avg = sum(item["lexical"] for item in combined_scored) / len(combined_scored)
        semantic_avg = sum(item["semantic"] for item in combined_scored) / len(combined_scored)
        lang_avg = sum(item["language_boost"] for item in combined_scored) / len(combined_scored)
        pop_avg = sum(item["popularity"] for item in combined_scored) / len(combined_scored)
    else:
        lexical_avg = semantic_avg = lang_avg = pop_avg = 0.0

    diagnostics = {
        "detected_query_language": q_lang,
        "language_confidence": lang_meta.get("confidence", 0.0),
        "primary_corpus": primary_corpus,
        "fallback_used": secondary_used,
        "candidate_counts": {
            "en": len(en_pool),
            "zh": len(zh_pool),
            "primary": len(primary_pool),
            "secondary": len(secondary_pool),
            "scored_total": len(combined_scored),
        },
        "fusion_component_avgs": {
            "lexical": round(lexical_avg, 4),
            "semantic": round(semantic_avg, 4),
            "language_boost": round(lang_avg, 4),
            "popularity": round(pop_avg, 4),
        },
        "routing_mode": mode,
        "min_primary_hits": min_primary_hits,
    }
    return selected, diagnostics


def retrieve_books_by_query(
    query: str,
    books: Sequence[Dict[str, Any]] | None = None,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    if books is not None:
        pool = list(books)
        if not pool:
            return []
        lang_meta = detect_query_language(query or "")
        q_lang = str(lang_meta.get("language") or "mixed")
        q_tokens = _tokenize_multilingual(query or "", lang_hint=q_lang)
        if not q_tokens:
            return [dict(item) for item in pool[: max(1, top_k)]]

        scored_rows: List[Dict[str, Any]] = []
        for row in pool:
            score = _score_candidate(query, q_tokens, q_lang, row)
            scored_rows.append({"book": row, **score})
        scored_rows.sort(
            key=lambda item: (
                0.35 * item["lexical"]
                + 0.35 * item["semantic"]
                + 0.20 * item["language_boost"]
                + 0.10 * item["popularity"]
            ),
            reverse=True,
        )
        return _dedup_and_rank(scored_rows, top_k=max(1, top_k), dedup_penalty=0.25)

    selected, _ = retrieve_books_by_query_with_diagnostics(query=query, top_k=top_k)
    return selected


def retrieve_books_by_variant_with_diagnostics(
    query: str,
    top_k: int = 8,
    variant: str | None = None,
    min_primary_hits: int | None = None,
    books_en: Sequence[Dict[str, Any]] | None = None,
    books_zh: Sequence[Dict[str, Any]] | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    selected_variant = str(variant or os.getenv(VARIANT_ENV_KEY) or "metadata-first-fusion").strip().lower()
    alias = {
        "baseline": "baseline",
        "metadata-first-fusion": "metadata-first-fusion",
        "metadata_first_fusion": "metadata-first-fusion",
        "full-fusion": "full-fusion",
        "full_fusion": "full-fusion",
    }
    selected_variant = alias.get(selected_variant, "metadata-first-fusion")

    if books_en is None or books_zh is None:
        corpora = load_books_dual_corpus()
        en_pool = list(books_en) if books_en is not None else corpora["en"]
        zh_pool = list(books_zh) if books_zh is not None else corpora["zh"]
    else:
        en_pool = list(books_en)
        zh_pool = list(books_zh)

    if selected_variant == "baseline":
        merged_pool = en_pool + zh_pool
        baseline_rows = retrieve_books_by_query(query=query, books=merged_pool, top_k=top_k)
        lang_meta = detect_query_language(query or "")
        return baseline_rows, {
            "variant": "baseline",
            "detected_query_language": lang_meta.get("language", "mixed"),
            "language_confidence": lang_meta.get("confidence", 0.0),
            "primary_corpus": "merged",
            "fallback_used": False,
            "candidate_counts": {
                "en": len(en_pool),
                "zh": len(zh_pool),
                "primary": len(merged_pool),
                "secondary": 0,
                "scored_total": len(merged_pool),
            },
            "fusion_component_avgs": {},
            "routing_mode": "baseline",
            "min_primary_hits": max(1, int(min_primary_hits or 5)),
        }

    route_mode = "soft"
    if selected_variant == "full-fusion":
        route_mode = "agnostic"

    rows, diagnostics = retrieve_books_by_query_with_diagnostics(
        query=query,
        top_k=top_k,
        route_mode=route_mode,
        min_primary_hits=min_primary_hits,
        books_en=en_pool,
        books_zh=zh_pool,
    )
    diagnostics["variant"] = selected_variant
    return rows, diagnostics
