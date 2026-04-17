"""Common utilities for Agents (logging, helpers, LLM calls)."""

from __future__ import annotations
import asyncio
import logging
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Iterable, Any, Dict, List
import httpx

try:  # Optional dependency available at runtime in agents
    import openai  # type: ignore
except Exception:  # pragma: no cover - keep base utils import-safe
    openai = None  # type: ignore

_async_client: Any = None
_async_client_init_failed = False


def _get_async_openai_client() -> Any:
    """Lazily create and cache a single AsyncOpenAI client instance."""
    global _async_client, _async_client_init_failed
    if _async_client_init_failed:
        return None
    if _async_client is None and openai is not None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        base_url = (
            os.getenv("RECOMMENDATION_ENGINE_LLM_BASE_URL")
            or os.getenv("DASHSCOPE_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
        )
        if not api_key or not base_url:
            return None

        # DashScope compatible-mode needs an extra proxy header; keep it optional for plain OpenAI.
        default_headers: Optional[Dict[str, str]] = None
        if base_url and "dashscope.aliyuncs.com" in base_url and api_key:
            default_headers = {"X-DashScope-Proxy-Authorization": f"Bearer {api_key}"}

        # Avoid inheriting SOCKS proxy env from host shell by default, which can
        # break client init when optional socks deps are not installed.
        trust_env = str(os.getenv("OPENAI_TRUST_ENV", "0")).strip().lower() in {"1", "true", "yes", "on"}
        http_client = httpx.AsyncClient(timeout=15, trust_env=trust_env)
        try:
            _async_client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                default_headers=default_headers,
                http_client=http_client,
            )
        except Exception:
            _async_client_init_failed = True
            try:
                import asyncio

                loop = asyncio.get_running_loop()
                loop.create_task(http_client.aclose())
            except Exception:
                pass
            logging.getLogger("agent.base").warning(
                "event=openai_client_init_failed trust_env=%s fallback=disable_llm",
                trust_env,
            )
            return None
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
    timeout_errors: tuple[type[BaseException], ...] = (TimeoutError, httpx.TimeoutException)
    api_timeout_error = getattr(openai, "APITimeoutError", None) if openai is not None else None
    if isinstance(api_timeout_error, type):
        timeout_errors = timeout_errors + (api_timeout_error,)
    try:
        chat_completion = await asyncio.wait_for(
            client.chat.completions.create(**kwargs),
            timeout=6.0,
        )
    except timeout_errors as exc:
        logging.getLogger("agent.base").warning(
            "event=openai_chat_timeout model=%s error=%s",
            model,
            exc,
        )
        return ""
    except TypeError:
        try:
            chat_completion = await asyncio.wait_for(
                client.chat.completions.create(
                    messages=messages,
                    model=model,
                ),
                timeout=6.0,
            )
        except timeout_errors as exc:
            logging.getLogger("agent.base").warning(
                "event=openai_chat_timeout model=%s error=%s",
                model,
                exc,
            )
            return ""
    return getattr(chat_completion.choices[0].message, "content", "") or ""


def _normalize_acs_skills(skills: Any) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    if not isinstance(skills, list):
        return normalized
    for item in skills:
        if isinstance(item, str):
            sid = item.strip()
            if sid:
                normalized.append({"id": sid, "name": sid})
            continue
        if isinstance(item, dict):
            sid = str(item.get("id") or item.get("name") or "").strip()
            if sid:
                normalized.append(
                    {
                        "id": sid,
                        "name": str(item.get("name") or sid),
                        "description": str(item.get("description") or "").strip(),
                    }
                )
    return normalized


def _normalize_acs_endpoints(endpoints: Any, endpoint_override_url: Optional[str] = None) -> List[Dict[str, str]]:
    if endpoint_override_url:
        return [
            {
                "transport": "JSONRPC",
                "url": endpoint_override_url,
                "description": "Primary orchestration endpoint",
            }
        ]

    if isinstance(endpoints, dict):
        endpoints = list(endpoints.values())
    if isinstance(endpoints, str):
        endpoints = [
            {
                "transport": "JSONRPC",
                "url": endpoints,
                "description": "RPC endpoint",
            }
        ]

    normalized: List[Dict[str, str]] = []
    if not isinstance(endpoints, list):
        return normalized

    for item in endpoints:
        if isinstance(item, str):
            url = item.strip()
            if url:
                normalized.append(
                    {
                        "transport": "JSONRPC",
                        "url": url,
                        "description": "RPC endpoint",
                    }
                )
            continue
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("URI") or item.get("endpoint") or "").strip()
        if not url:
            continue
        normalized.append(
            {
                "transport": str(item.get("transport") or "JSONRPC").upper(),
                "url": url,
                "description": str(item.get("description") or "").strip(),
            }
        )
    return normalized


def _load_acs_descriptor(json_path: str, endpoint_override_url: Optional[str] = None) -> Dict[str, Any]:
    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    raw = payload.get("acs") if isinstance(payload, dict) and isinstance(payload.get("acs"), dict) else payload
    if not isinstance(raw, dict):
        raw = {}

    skills = _normalize_acs_skills(raw.get("skills") or [])
    endpoints = _normalize_acs_endpoints(
        raw.get("endPoints") or raw.get("endpoints") or raw.get("endpoint") or [],
        endpoint_override_url=endpoint_override_url,
    )

    descriptor: Dict[str, Any] = {
        "aic": str(raw.get("aic") or "").strip(),
        "protocolVersion": str(raw.get("protocolVersion") or "01.00").strip() or "01.00",
        "name": str(raw.get("name") or "").strip(),
        "description": str(raw.get("description") or "").strip(),
        "version": str(raw.get("version") or "1.0.0").strip() or "1.0.0",
        "skills": skills,
        "endPoints": endpoints,
    }

    for key in ["provider", "securitySchemes", "capabilities", "active"]:
        if key in raw:
            descriptor[key] = raw[key]
    return descriptor


def register_acs_route(app: Any, json_path: str, endpoint_override_url: Optional[str] = None) -> None:
    @app.get("/acs")
    async def _acs_descriptor() -> Dict[str, Any]:
        return _load_acs_descriptor(json_path, endpoint_override_url=endpoint_override_url)
