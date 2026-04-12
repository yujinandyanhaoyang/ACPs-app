from __future__ import annotations

import asyncio
import csv
import gzip
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DESCRIPTION_PROMPT_TEMPLATE = """书名：{title}
作者：{author}（如不确定可忽略）
分类：{genres_str}（如不确定可忽略）

请用1-2句中文写出这本书的简介，约60-80个汉字，不要剧透，语气中性客观。只返回简介文本，不要任何解释。"""

SYSTEM_PROMPT = "You are a book metadata assistant. Write a short, neutral Chinese book description."

_SPACE_RE = re.compile(r"\s+")
_STRIP_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_GZ_SUFFIX = ".json.gz"


@dataclass(frozen=True)
class EnrichmentConfig:
    dataset_root: Path
    raw_root: Path
    output_path: Path
    augmentation_base_url: str
    augmentation_api_key: str
    augmentation_model: str


@dataclass(frozen=True)
class UnifiedBookRecord:
    source: str
    book_id: str
    title: str
    author: str
    genres: List[str]
    description: str
    rating: Optional[float]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return _SPACE_RE.sub(" ", " ".join(clean_text(item) for item in value if clean_text(item)).strip())
    if isinstance(value, dict):
        return _SPACE_RE.sub(" ", json.dumps(value, ensure_ascii=False, sort_keys=True).strip())
    return _SPACE_RE.sub(" ", str(value).replace("\u00a0", " ").strip())


def normalize_key(value: Any) -> str:
    return _STRIP_RE.sub("", clean_text(value).lower())


def flatten_strings(value: Any) -> List[str]:
    items: List[str] = []
    if isinstance(value, list):
        source = value
    elif value is None:
        source = []
    else:
        source = [value]

    for item in source:
        if isinstance(item, list):
            items.extend(flatten_strings(item))
            continue
        text = clean_text(item)
        if text:
            items.append(text)

    deduped: List[str] = []
    seen = set()
    for item in items:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def parse_float(value: Any) -> Optional[float]:
    text = clean_text(value)
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def description_length(value: Any) -> int:
    text = clean_text(value)
    return len(text)


def has_valid_description(value: Any) -> bool:
    return description_length(value) >= 50


def build_description_messages(title: str, author: str, genres: Sequence[str]) -> List[Dict[str, str]]:
    genres_str = "、".join(genres) if genres else ""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": DESCRIPTION_PROMPT_TEMPLATE.format(
                title=title or "",
                author=author or "",
                genres_str=genres_str,
            ),
        },
    ]


def _csv_rows(path: Path) -> Iterable[Dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as f:  # type: ignore[arg-type]
        reader = csv.DictReader(f)
        yield from reader


def _jsonl_gz_rows(path: Path) -> Iterable[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            if isinstance(row, dict):
                yield row


def resolve_input_paths(raw_root: Path) -> Tuple[Path, List[Path]]:
    goodreads_candidates = [
        raw_root / "goodreads" / "books.csv",
        raw_root / "goodreads" / "books.csv.gz",
    ]
    goodreads_path = next((path for path in goodreads_candidates if path.exists()), None)
    if goodreads_path is None:
        raise FileNotFoundError(
            "Could not find Goodreads books.csv under "
            f"{raw_root / 'goodreads'}"
        )

    explicit_amazon_candidates = [
        raw_root / "amazon_books" / "meta_Books.json.gz",
        raw_root / "amazon_books" / "meta_Kindle_Store.json.gz",
        raw_root / "amazon_books" / "metaBooks.json.gz",
        raw_root / "amazon_books" / "metaKindleStore.json.gz",
        raw_root / "amazon" / "books" / "metaBooks.json.gz",
        raw_root / "amazon" / "books" / "metaKindleStore.json.gz",
        raw_root / "amazon" / "books" / "meta_Books.json.gz",
        raw_root / "amazon" / "books" / "meta_Kindle_Store.json.gz",
    ]
    amazon_paths: List[Path] = []
    seen = set()
    for path in explicit_amazon_candidates:
        if path.exists() and path not in seen:
            amazon_paths.append(path)
            seen.add(path)

    if len(amazon_paths) < 2:
        normalized_targets = {
            "metabooksjsongz",
            "metakindlestorejsongz",
        }
        for path in sorted(raw_root.rglob("*.json.gz")):
            normalized_name = normalize_key(path.name.replace(".", ""))
            if normalized_name not in normalized_targets:
                continue
            if path not in seen:
                amazon_paths.append(path)
                seen.add(path)
            if len(amazon_paths) >= 2:
                break

    if len(amazon_paths) < 2:
        raise FileNotFoundError(
            "Could not find both Amazon metadata files under raw data root. "
            "Expected meta_Books.json.gz and meta_Kindle_Store.json.gz (or equivalent)."
        )

    amazon_paths = sorted(amazon_paths)
    return goodreads_path, amazon_paths[:2]


def load_config() -> EnrichmentConfig:
    dataset_root_value = clean_text(os.getenv("BOOK_RETRIEVAL_DATASET_PATH"))
    base_url = clean_text(os.getenv("BOOK_AUGMENTATION_BASE_URL"))
    api_key = clean_text(os.getenv("BOOK_AUGMENTATION_API_KEY"))
    model = clean_text(os.getenv("BOOK_AUGMENTATION_MODEL")) or "qwen-turbo"

    missing = [
        name
        for name, value in [
            ("BOOK_RETRIEVAL_DATASET_PATH", dataset_root_value),
            ("BOOK_AUGMENTATION_BASE_URL", base_url),
            ("BOOK_AUGMENTATION_API_KEY", api_key),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Please set them in .env before running scripts/enrich_books.py."
        )

    dataset_root = Path(dataset_root_value).expanduser().resolve()
    raw_root = dataset_root / "raw"
    output_path_value = clean_text(os.getenv("BOOK_ENRICHED_DATASET_PATH"))
    output_path = (
        Path(output_path_value).expanduser().resolve()
        if output_path_value
        else (dataset_root / "processed" / "books_enriched.jsonl")
    )
    return EnrichmentConfig(
        dataset_root=dataset_root,
        raw_root=raw_root,
        output_path=output_path,
        augmentation_base_url=base_url.rstrip("/"),
        augmentation_api_key=api_key,
        augmentation_model=model,
    )


def normalize_goodreads_row(row: Dict[str, Any]) -> UnifiedBookRecord:
    return UnifiedBookRecord(
        source="goodreads",
        book_id=clean_text(row.get("book_id")),
        title=clean_text(row.get("title")),
        author=clean_text(row.get("authors")),
        genres=[],
        description="",
        rating=parse_float(row.get("average_rating")),
    )


def normalize_amazon_row(row: Dict[str, Any]) -> UnifiedBookRecord:
    author_value = clean_text(row.get("brand"))
    if not author_value:
        author_list = flatten_strings(row.get("author"))
        author_value = author_list[0] if author_list else ""

    raw_genres = row.get("categories")
    if raw_genres is None:
        raw_genres = row.get("category")
    genres = flatten_strings(raw_genres)

    description_value = ""
    raw_description = row.get("description")
    if isinstance(raw_description, list):
        desc_items = flatten_strings(raw_description)
        description_value = desc_items[0] if desc_items else ""
    elif raw_description is not None:
        description_value = clean_text(raw_description)

    return UnifiedBookRecord(
        source="amazon",
        book_id=clean_text(row.get("asin")),
        title=clean_text(row.get("title")),
        author=author_value,
        genres=genres,
        description=description_value,
        rating=None,
    )


def iter_goodreads_records(path: Path) -> Iterable[UnifiedBookRecord]:
    for row in _csv_rows(path):
        yield normalize_goodreads_row(row)


def iter_amazon_records(path: Path) -> Iterable[UnifiedBookRecord]:
    for row in _jsonl_gz_rows(path):
        yield normalize_amazon_row(row)


def record_key(record: UnifiedBookRecord) -> Tuple[str, str]:
    return record.source, record.book_id


def clean_enriched_description(text: str) -> str:
    return clean_text(text)


def compact_jsonl_row(record: UnifiedBookRecord, description: str, description_source: str) -> Dict[str, Any]:
    return {
        "source": record.source,
        "book_id": record.book_id,
        "title": record.title,
        "author": record.author,
        "genres": record.genres,
        "description": description,
        "rating": record.rating,
        "description_source": description_source,
    }


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        min_request_interval: float = 0.0,
        max_requests_per_minute: Optional[int] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._min_request_interval = max(0.0, float(min_request_interval))
        self._max_requests_per_minute = int(max_requests_per_minute) if max_requests_per_minute else None
        self._client: Any = None
        self._backend = "httpx"
        self._httpx = None
        self._aiohttp = None
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._request_timestamps: List[float] = []

    async def __aenter__(self) -> "OpenAICompatibleClient":
        try:
            import httpx  # type: ignore

            self._httpx = httpx
            self._client = httpx.AsyncClient(timeout=self._timeout, trust_env=False)
            self._backend = "httpx"
        except ImportError:
            import aiohttp  # type: ignore

            self._aiohttp = aiohttp
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._client = aiohttp.ClientSession(timeout=timeout)
            self._backend = "aiohttp"
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose() if self._backend == "httpx" else await self._client.close()

    async def _throttle(self) -> None:
        async with self._request_lock:
            now = time.monotonic()
            if self._min_request_interval > 0:
                wait_for_interval = self._last_request_at + self._min_request_interval - now
                if wait_for_interval > 0:
                    await asyncio.sleep(wait_for_interval)
                    now = time.monotonic()

            if self._max_requests_per_minute and self._max_requests_per_minute > 0:
                cutoff = now - 60.0
                self._request_timestamps = [ts for ts in self._request_timestamps if ts >= cutoff]
                if len(self._request_timestamps) >= self._max_requests_per_minute:
                    oldest = self._request_timestamps[0]
                    wait_for_window = 60.0 - (now - oldest)
                    if wait_for_window > 0:
                        await asyncio.sleep(wait_for_window)
                        now = time.monotonic()
                        cutoff = now - 60.0
                        self._request_timestamps = [ts for ts in self._request_timestamps if ts >= cutoff]

            self._last_request_at = time.monotonic()
            self._request_timestamps.append(self._last_request_at)

    async def chat_completion(self, messages: Sequence[Dict[str, str]], max_tokens: int = 256) -> Tuple[Optional[str], Optional[str]]:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": list(messages),
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }

        last_error = ""
        for attempt in range(3):
            try:
                await self._throttle()
                if self._backend == "httpx":
                    response = await self._client.post(url, headers=headers, json=payload)  # type: ignore[union-attr]
                    status = response.status_code
                    data = response.json() if response.content else {}
                else:
                    async with self._client.post(url, headers=headers, json=payload) as response:  # type: ignore[union-attr]
                        status = response.status
                        data = await response.json(content_type=None)

                if status == 429 or 500 <= status <= 599:
                    last_error = _error_message_from_payload(data, fallback=f"HTTP {status}")
                    if attempt < 2:
                        await asyncio.sleep(2**attempt)
                        continue
                    return None, last_error

                if status >= 400:
                    return None, _error_message_from_payload(data, fallback=f"HTTP {status}")

                content = _extract_chat_content(data)
                content = clean_enriched_description(content)
                if content:
                    return content, None
                return None, "empty model response"
            except Exception as exc:  # pragma: no cover - network/backend failures
                last_error = str(exc)
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
                return None, last_error

        return None, last_error or "unknown error"


def _extract_chat_content(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        text = first.get("text") if isinstance(first, dict) else None
        if isinstance(text, str):
            return text
    if isinstance(payload.get("text"), str):
        return str(payload["text"])
    return ""


def _error_message_from_payload(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return fallback


def is_fatal_provider_error(error_text: str) -> bool:
    text = (error_text or "").lower()
    fatal_markers = (
        "rate-limit",
        "rate limit",
        "request limit",
        "quota",
        "insufficient_quota",
        "free tier of the model has been exhausted",
        "free tier only",
        "billing",
        "service unavailable",
        "unavailable",
        "gateway timeout",
        "connection reset",
        "connection refused",
        "timeout",
        "503",
        "502",
        "504",
    )
    return any(marker in text for marker in fatal_markers)
