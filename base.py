"""Common utilities for Agents (logging, helpers, LLM calls)."""

from __future__ import annotations
import logging
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Iterable, Any

try:  # Optional dependency available at runtime in agents
    import openai  # type: ignore
except Exception:  # pragma: no cover - keep base utils import-safe
    openai = None  # type: ignore

_async_client: Any = None


def _get_async_openai_client() -> Any:
    """Lazily create and cache a single AsyncOpenAI client instance."""
    global _async_client
    if _async_client is None and openai is not None:
        _async_client = openai.AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
    return _async_client

# Beijing timezone (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))


class BeijingTimeFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):  # type: ignore[override]
        dt = datetime.fromtimestamp(record.created, BEIJING_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        # Default ISO-like with offset
        return dt.strftime("%Y-%m-%d %H:%M:%S%z")


def get_agent_logger(
    name: str, level_env_var: str, default_level: str = "INFO"
) -> logging.Logger:
    """Return a configured logger.

    Parameters
    ----------
    name: logger name (e.g. "agent.beijing_urban")
    level_env_var: environment variable name to read logging level from
    default_level: fallback level string
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = BeijingTimeFormatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S%z",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    # Resolve log level
    level_name = os.getenv(level_env_var, default_level).upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def truncate(text: Optional[str], limit: int = 300) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit] + "…(truncated)"


def extract_text_from_message(message: Any) -> str:
    """Extract all text segments from a Message.dataItems list.

    - Collects items that have a ``text`` attribute (e.g., TextDataItem).
    - Joins multiple segments with newlines.
    - Returns empty string if nothing found.
    """
    txt_parts: list[str] = []
    try:
        items: Iterable[Any] = getattr(message, "dataItems", []) or []
        for item in items:
            # Be tolerant: check attribute instead of exact class to avoid tight coupling
            if hasattr(item, "text") and isinstance(getattr(item, "text"), str):
                t = getattr(item, "text")
                if t:
                    txt_parts.append(t)
    except Exception:
        # Be defensive; don't raise from helper
        return ""
    return "\n".join(txt_parts).strip()


def load_capabilities_snippet_from_json(json_path: str, fallback: str) -> str:
    """Load a short capabilities snippet from a JSON file.

    Expected JSON shape (optional keys):
      { "description": "...", "skills": [{"name": "..."}, ...] }
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        desc = (meta or {}).get("description", "")
        skills = (meta or {}).get("skills", []) or []
        skill_names = [
            s.get("name") for s in skills if isinstance(s, dict) and s.get("name")
        ]
        skills_line = ("技能：" + "、".join(skill_names)) if skill_names else ""
        return (desc + ("\n" + skills_line if skills_line else "")).strip()
    except Exception:
        return fallback


async def call_openai_chat(
    messages: list[dict],
    *,
    model: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Call OpenAI-compatible chat completion API using the async client.

    Uses AsyncOpenAI so that ``await`` truly yields control back to the
    event loop, enabling real parallelism inside ``asyncio.gather()``.
    """
    client = _get_async_openai_client()
    if client is None:  # pragma: no cover
        return ""
    kwargs: dict = {"messages": messages, "model": model}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    try:
        chat_completion = await client.chat.completions.create(**kwargs)
    except TypeError:
        chat_completion = await client.chat.completions.create(
            messages=messages,
            model=model,
        )
    return getattr(chat_completion.choices[0].message, "content", "") or ""
