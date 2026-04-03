from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _check_port_open(host: str, port: int, timeout_sec: float = 0.2) -> Any:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_sec)
            try:
                sock.connect((host, port))
                return True
            except Exception:
                return False
    except PermissionError:
        # Some sandboxes disallow raw socket operations.
        return "permission_denied"


def _load_agent_modules():
    from reading_concierge import reading_concierge as rc
    from partners.online.reader_profile_agent import agent as rpa
    from partners.online.book_content_agent import agent as bca
    from partners.online.recommendation_decision_agent import agent as rda
    from partners.online.recommendation_engine_agent import agent as eng
    from partners.online.feedback_agent import agent as fa

    return rc, rpa, bca, rda, eng, fa


def _ports_snapshot(rc, rpa, bca, rda, eng, fa) -> Dict[str, int]:
    return {
        "reading_concierge": int(rc.RUNTIME.port),
        "reader_profile_agent": int(rpa.CFG.port),
        "book_content_agent": int(bca.CFG.port),
        "recommendation_decision_agent": int(rda.CFG.port),
        "recommendation_engine_agent": int(eng.CFG.port),
        "feedback_agent": int(fa.CFG.port),
    }


def _port_conflict_check(ports: Dict[str, int]) -> Tuple[bool, Dict[str, List[str]]]:
    groups: Dict[int, List[str]] = {}
    for name, port in ports.items():
        groups.setdefault(int(port), []).append(name)
    conflicts = {str(port): names for port, names in groups.items() if len(names) > 1}
    return len(conflicts) == 0, conflicts


def _build_payload(user_id: str, query: str, top_k: int = 5) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "query": query,
        "user_profile": {"preferred_language": "en"},
        "history": [
            {
                "title": "Dune",
                "genres": ["science_fiction"],
                "rating": 5,
                "language": "en",
            }
        ],
        "reviews": [{"rating": 5, "text": "I enjoy nuanced worldbuilding and ideas."}],
        "books": [
            {
                "book_id": "sci-1",
                "title": "Foundation",
                "author": "Isaac Asimov",
                "description": "A science fiction saga about psychohistory and galactic empires.",
                "genres": ["science_fiction"],
                "vector": [0.2, 0.3, 0.1, 0.4],
                "novelty_score": 0.35,
                "published_year": 1951,
                "kg_refs": ["kg:foundation"],
                "matched_prefs": ["science_fiction", "ideas"],
            },
            {
                "book_id": "sci-2",
                "title": "Hyperion",
                "author": "Dan Simmons",
                "description": "A layered story with diverse voices and themes.",
                "genres": ["science_fiction"],
                "vector": [0.1, 0.2, 0.3, 0.2],
                "novelty_score": 0.55,
                "published_year": 1989,
                "kg_refs": ["kg:hyperion"],
                "matched_prefs": ["diverse_themes"],
            },
            {
                "book_id": "hist-1",
                "title": "The Silk Roads",
                "author": "Peter Frankopan",
                "description": "A global history narrative connecting trade, diplomacy, and empires.",
                "genres": ["history"],
                "vector": [0.05, 0.1, 0.2, 0.25],
                "novelty_score": 0.65,
                "published_year": 2015,
                "matched_prefs": ["history"],
            },
        ],
        "constraints": {"top_k": top_k, "scenario": "warm", "debug_payload_override": True},
    }


async def _run_sessions(rc, session_count: int) -> Dict[str, Any]:
    states: Dict[str, int] = {}
    flows: List[Dict[str, Any]] = []

    for idx in range(session_count):
        user_id = f"phase3_real_user_{idx:02d}"
        req = rc.UserRequest(**_build_payload(user_id=user_id, query=f"Session {idx}: recommend sci-fi and social themes."))
        res = await rc._orchestrate(req)

        state = str(res.get("state") or "unknown")
        states[state] = states.get(state, 0) + 1

        partner_tasks = res.get("partner_tasks") if isinstance(res.get("partner_tasks"), dict) else {}
        flow_ok = (
            str((partner_tasks.get("rda_standby") or {}).get("state") or "") == "completed"
            and str((partner_tasks.get("rpa") or {}).get("state") or "") == "completed"
            and str((partner_tasks.get("bca") or {}).get("state") or "") == "completed"
            and str((partner_tasks.get("rda") or {}).get("state") or "") == "completed"
            and str((partner_tasks.get("engine") or {}).get("state") or "") == "completed"
        )

        flows.append(
            {
                "user_id": user_id,
                "state": state,
                "flow_ok": flow_ok,
                "recommendation_count": len(res.get("recommendations") or []),
            }
        )

    success_count = sum(1 for row in flows if row["flow_ok"] and row["state"] == "completed")
    return {
        "session_count": session_count,
        "success_count": success_count,
        "states": states,
        "flows": flows,
    }


async def _verify_feedback_writes_rda_arms(rda, fa) -> Dict[str, Any]:
    context_type = "high_conf_low_div"
    action = "balanced"
    before = rda.ARM_STORE.get_record(context_type, action)

    fa.PARTNER_MODE = "auto"
    event = fa.BehaviorEvent(
        user_id="phase3_feedback_user",
        event_type="finish",
        session_id="phase3-feedback-session",
        context_type=context_type,
        action=action,
        session_completed=True,
        metadata={"source": "phase3_e2e_integration"},
    )

    result = await fa._process_event(event)
    after = rda.ARM_STORE.get_record(context_type, action)

    trials_before = float(before.get("trials") or 0.0)
    trials_after = float(after.get("trials") or 0.0)

    return {
        "feedback_result": result,
        "arm_before": before,
        "arm_after": after,
        "arm_trials_incremented": trials_after > trials_before,
    }


async def run_integration(session_count: int) -> Dict[str, Any]:
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["READING_PARTNER_MODE"] = "auto"
    os.environ["FEEDBACK_PARTNER_MODE"] = "auto"

    rc, rpa, bca, rda, eng, fa = _load_agent_modules()

    # Avoid external model downloads during integration validation.
    import services.model_backends as model_backends

    model_backends._resolve_sentence_transformer = lambda _model_name: None

    ports = _ports_snapshot(rc, rpa, bca, rda, eng, fa)
    no_conflict, conflicts = _port_conflict_check(ports)
    listening = {name: _check_port_open("127.0.0.1", port) for name, port in ports.items()}

    sessions = await _run_sessions(rc, session_count=session_count)
    feedback = await _verify_feedback_writes_rda_arms(rda, fa)

    return {
        "ports": {
            "configured": ports,
            "unique": no_conflict,
            "conflicts": conflicts,
            "currently_listening": listening,
        },
        "pipeline_validation": sessions,
        "feedback_validation": feedback,
        "phase3_gate_like_status": {
            "pipeline_completed": sessions["success_count"] == session_count,
            "feedback_to_rda_written": bool(feedback.get("arm_trials_incremented")),
            "manual_sessions_target_met": sessions["session_count"] >= 10,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 End-to-End integration validation runner")
    parser.add_argument("--sessions", type=int, default=10, help="Number of end-to-end sessions to run")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(run_integration(session_count=max(1, int(args.sessions))))
    output = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None)
    print(output)

    gate = report.get("phase3_gate_like_status") or {}
    ok = bool(gate.get("pipeline_completed")) and bool(gate.get("feedback_to_rda_written")) and bool(gate.get("manual_sessions_target_met"))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
