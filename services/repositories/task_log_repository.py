from __future__ import annotations

import json
from typing import Any, Dict, Optional

from services.db import transaction, utc_now


class TaskLogRepository:
    def __init__(self, db_url: Optional[str] = None) -> None:
        self.db_url = db_url

    def append(
        self,
        *,
        task_id: str,
        state_transition: str,
        session_id: Optional[str] = None,
        sender_id: Optional[str] = None,
        receiver_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        if not str(task_id or "").strip() or not str(state_transition or "").strip():
            return
        with transaction(self.db_url) as conn:
            conn.execute(
                """
                INSERT INTO agent_task_logs (
                    task_id,
                    session_id,
                    sender_id,
                    receiver_id,
                    state_transition,
                    payload_json,
                    timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    session_id,
                    sender_id,
                    receiver_id,
                    state_transition,
                    json.dumps(payload or {}, ensure_ascii=False),
                    timestamp or utc_now(),
                ),
            )
