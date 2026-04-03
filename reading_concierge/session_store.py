from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


class SessionStore:
    """Redis-first session context wrapper with in-memory fallback."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis = None
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._init_redis()

    def _init_redis(self) -> None:
        if redis is None:
            return
        try:
            client = redis.from_url(self.redis_url, decode_responses=True)
            client.ping()
            self._redis = client
        except Exception:
            self._redis = None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get(self, session_id: str) -> Dict[str, Any]:
        if self._redis is not None:
            try:
                raw = self._redis.get(f"rc:session:{session_id}")
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return dict(self._memory.get(session_id) or {})

    def set(self, session_id: str, value: Dict[str, Any], ttl_sec: int = 86400) -> None:
        payload = dict(value)
        payload.setdefault("updated_at", self._now())
        if self._redis is not None:
            try:
                self._redis.setex(f"rc:session:{session_id}", ttl_sec, json.dumps(payload, ensure_ascii=False))
                return
            except Exception:
                pass
        self._memory[session_id] = payload

    def append_message(self, session_id: str, role: str, content: str) -> None:
        state = self.get(session_id)
        messages = state.get("messages") if isinstance(state.get("messages"), list) else []
        messages.append(
            {
                "role": role,
                "content": content,
                "timestamp": self._now(),
            }
        )
        state["messages"] = messages
        self.set(session_id, state)

    def update_fields(self, session_id: str, fields: Dict[str, Any]) -> None:
        state = self.get(session_id)
        state.update(fields or {})
        self.set(session_id, state)
