from __future__ import annotations

from contextlib import contextmanager, asynccontextmanager
from datetime import datetime
from pathlib import Path
from statistics import median
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest


BASE_URL = str(os.getenv("UAT_BASE_URL") or "http://127.0.0.1:8210").rstrip("/")
TIMEOUT = 60.0
USER_WARM = "demo_user_001"
USER_COLD = "brand_new_user_uat_9999"
REPORT_PATH = Path(__file__).with_name("uat_report_production.txt")
BACKEND_UNAVAILABLE_MESSAGE = "backend unavailable"


SCENARIO_LABELS: Dict[str, str] = {
    "00": "Service health check",
    "01": "Warm user recommendation",
    "02": "Cold user degradation",
    "03": "Multi-turn session reuse",
    "04": "Positive feedback loop",
    "05": "Repeated negative feedback",
    "06": "Missing session_id -> 400",
    "07": "Empty query -> 400",
    "08": "Non-existent user degradation",
    "09": "Oversized top_k auto-clamp",
    "10": "Profile endpoint init check",
    "11": "Recommendation quality check",
    "12": "Latency baseline benchmark",
    "13": "Full closed-loop E2E",
}

LABEL_WIDTH = max(len(label) for label in SCENARIO_LABELS.values()) + 2

STATE: Dict[str, Any] = {
    "backend_available": None,
    "backend_unavailable_reason": "",
    "backend_unavailable_cause": "",
    "records": {},
    "artifacts": {},
}


class BackendUnavailableError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _record_result(
    scenario_id: str,
    *,
    status: str,
    detail: str = "",
    duration_s: Optional[float] = None,
) -> None:
    STATE["records"][scenario_id] = {
        "scenario_id": scenario_id,
        "label": SCENARIO_LABELS.get(scenario_id, scenario_id),
        "status": status,
        "detail": detail,
        "duration_s": duration_s,
    }
    if scenario_id == "00":
        if status == "PASS":
            STATE["backend_available"] = True
            STATE["backend_unavailable_reason"] = ""
            STATE["backend_unavailable_cause"] = ""
        elif status in {"FAIL", "ERROR"}:
            STATE["backend_available"] = False
            if detail:
                STATE["backend_unavailable_reason"] = detail


def _mark_backend_unavailable(reason: str) -> None:
    STATE["backend_available"] = False
    STATE["backend_unavailable_reason"] = BACKEND_UNAVAILABLE_MESSAGE
    STATE["backend_unavailable_cause"] = reason or BACKEND_UNAVAILABLE_MESSAGE


@contextmanager
def _scenario_context(scenario_id: str):
    started_at = time.perf_counter()
    meta = {"status": "PASS", "detail": ""}
    try:
        yield meta
    except BackendUnavailableError as exc:
        meta["status"] = "ERROR"
        meta["detail"] = str(exc) or BACKEND_UNAVAILABLE_MESSAGE
        _record_result(
            scenario_id,
            status=meta["status"],
            detail=meta["detail"],
            duration_s=time.perf_counter() - started_at,
        )
        raise
    except Exception as exc:  # noqa: BLE001 - UAT needs the exact failure root cause
        meta["status"] = "FAIL"
        meta["detail"] = str(exc)
        _record_result(
            scenario_id,
            status=meta["status"],
            detail=meta["detail"],
            duration_s=time.perf_counter() - started_at,
        )
        raise
        raise
        raise
    else:
        _record_result(
            scenario_id,
            status=meta["status"],
            detail=meta["detail"],
            duration_s=time.perf_counter() - started_at,
        )


def _require_backend_ready() -> None:
    if STATE["backend_available"] is False:
        raise BackendUnavailableError(STATE.get("backend_unavailable_reason") or BACKEND_UNAVAILABLE_MESSAGE)


@asynccontextmanager
async def _open_client():
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx.Timeout(TIMEOUT),
        trust_env=False,
    ) as client:
        yield client


async def _probe_backend(client: httpx.AsyncClient) -> Tuple[int, Dict[str, Any], float, str]:
    started_at = time.perf_counter()
    try:
        response = await client.get("/demo/status")
    except httpx.TimeoutException as exc:
        latency = time.perf_counter() - started_at
        return 0, {}, latency, f"timeout after {latency:.2f}s: {exc}"
    except httpx.HTTPError as exc:
        latency = time.perf_counter() - started_at
        return 0, {}, latency, f"request failed after {latency:.2f}s: {exc}"

    latency = time.perf_counter() - started_at
    try:
        body = response.json()
        if not isinstance(body, dict):
            body = {"_raw": body}
    except Exception:
        body = {"_raw": response.text}
    return response.status_code, body, latency, ""


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[httpx.Response, Dict[str, Any], float]:
    started_at = time.perf_counter()
    try:
        response = await client.request(method, path, json=json_body, params=params)
    except httpx.TimeoutException as exc:
        latency = time.perf_counter() - started_at
        raise AssertionError(f"{method} {path} timed out after {latency:.2f}s: {exc}") from exc
    except httpx.HTTPError as exc:
        latency = time.perf_counter() - started_at
        raise AssertionError(f"{method} {path} failed after {latency:.2f}s: {exc}") from exc

    latency = time.perf_counter() - started_at
    try:
        body = response.json()
        if not isinstance(body, dict):
            body = {"_raw": body}
    except Exception:
        body = {"_raw": response.text}
    return response, body, latency


def _response_text(body: Dict[str, Any]) -> str:
    raw = body.get("_raw")
    if raw is not None:
        return str(raw)
    return str(body)


def _assert_status(
    response: httpx.Response,
    expected_status: int,
    body: Dict[str, Any],
    *,
    context: str,
) -> None:
    assert response.status_code == expected_status, (
        f"{context}: expected HTTP {expected_status}, got {response.status_code}; body={_response_text(body)}"
    )


def _assert_non_empty_string(value: Any, *, field: str, context: str) -> None:
    assert isinstance(value, str) and value.strip(), f"{context}: {field} must be a non-empty string, got {value!r}"


def _assert_valid_recommendation(item: Dict[str, Any], *, context: str) -> None:
    for field in ("book_id", "title", "score_total", "justification"):
        assert field in item, f"{context}: recommendation missing field {field!r}; item={item}"
    _assert_non_empty_string(item.get("book_id"), field="book_id", context=context)
    _assert_non_empty_string(item.get("title"), field="title", context=context)
    assert isinstance(item.get("score_total"), (int, float)), f"{context}: score_total must be numeric; item={item}"
    assert 0.0 <= float(item.get("score_total")) <= 1.0, f"{context}: score_total out of range; item={item}"
    assert isinstance(item.get("rank"), int), f"{context}: rank must be an int; item={item}"

    justification = str(item.get("justification") or "")
    assert len(justification) > 10, f"{context}: justification too short; item={item}"
    assert "{title}" not in justification, f"{context}: placeholder {{title}} found in justification; item={item}"
    assert "{author}" not in justification, f"{context}: placeholder {{author}} found in justification; item={item}"
    assert "{genre_tags}" not in justification, f"{context}: placeholder {{genre_tags}} found in justification; item={item}"
    assert "None" not in justification, f"{context}: string 'None' found in justification; item={item}"


async def _warm_recommendation(client: httpx.AsyncClient) -> Tuple[Dict[str, Any], float]:
    cached = STATE["artifacts"].get("warm_recommendation")
    if isinstance(cached, dict):
        return cached, float(cached.get("latency_s") or 0.0)

    payload = {
        "user_id": USER_WARM,
        "query": "我想看一本关于孤独与自我成长的小说",
        "session_id": None,
        "constraints": {"top_k": 5, "scenario": "warm"},
    }
    response, body, latency = await _request_json(client, "POST", "/user_api", json_body=payload)
    result = {
        "response": response,
        "body": body,
        "latency_s": latency,
        "request": payload,
    }
    STATE["artifacts"]["warm_recommendation"] = result
    return result, latency


def _book_id_list(body: Dict[str, Any]) -> List[str]:
    recs = body.get("recommendations")
    if not isinstance(recs, list):
        return []
    ids: List[str] = []
    for item in recs:
        if isinstance(item, dict):
            book_id = str(item.get("book_id") or "").strip()
            if book_id:
                ids.append(book_id)
    return ids


def _report_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for scenario_id in sorted(SCENARIO_LABELS):
        record = STATE["records"].get(scenario_id)
        if not record:
            if STATE["backend_available"] is False and scenario_id != "00":
                record = {
                    "scenario_id": scenario_id,
                    "label": SCENARIO_LABELS.get(scenario_id, scenario_id),
                    "status": "ERROR",
                    "detail": STATE.get("backend_unavailable_reason") or BACKEND_UNAVAILABLE_MESSAGE,
                    "duration_s": None,
                }
            else:
                record = {
                    "scenario_id": scenario_id,
                    "label": SCENARIO_LABELS.get(scenario_id, scenario_id),
                    "status": "ERROR",
                    "detail": "not executed",
                    "duration_s": None,
                }
        rows.append(record)
    return rows


def _duration_display(record: Dict[str, Any]) -> str:
    scenario_id = str(record.get("scenario_id") or "")
    if scenario_id == "12" and record.get("detail"):
        return str(record["detail"])
    duration_s = record.get("duration_s")
    if duration_s is None:
        return "-"
    return f"{float(duration_s):.2f}s"


def _format_report() -> str:
    rows = _report_rows()
    lines = ["===== ACPs Reading Concierge Production UAT Report =====", f"Timestamp: {_now_iso()}"]
    lines.append("")
    for record in rows:
        lines.append(
            f"Scenario {record['scenario_id']} | {record['label'].ljust(LABEL_WIDTH)} | "
            f"{record['status']} | {_duration_display(record)}"
        )

    counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "ERROR": 0}
    for record in rows:
        status = str(record.get("status") or "ERROR")
        counts[status] = counts.get(status, 0) + 1

    lines.append("")
    total_line = f"Total: {counts['PASS']} PASS | {counts['FAIL']} FAIL | {counts['WARN']} WARN"
    if counts["ERROR"]:
        total_line += f" | {counts['ERROR']} ERROR"
    lines.append(total_line)

    critical: List[str] = []
    for record in rows:
        if record.get("status") in {"FAIL", "ERROR"}:
            critical.append(
                f"Scenario {record['scenario_id']} | {record['label']} | {record.get('detail') or BACKEND_UNAVAILABLE_MESSAGE}"
            )
    lines.append("Critical issues: " + ("None" if not critical else "; ".join(critical[:3])))
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="session", autouse=True)
def _write_report_on_exit():
    yield
    REPORT_PATH.write_text(_format_report(), encoding="utf-8")


@pytest.mark.asyncio
async def test_scenario_00_service_health_check():
    async with _open_client() as client:
        with _scenario_context("00") as meta:
            status, body, latency, error = await _probe_backend(client)
            if error:
                _mark_backend_unavailable(error)
                raise AssertionError(
                    "ABORT: Production server at 127.0.0.1:8210 is not reachable."
                )
            assert status == 200, f"GET /demo/status expected HTTP 200, got {status}; body={body}"
            assert body.get("service") == "reading_concierge", f"GET /demo/status service mismatch: {body}"
            assert body.get("demo_page_available") is True, f"GET /demo/status demo_page_available expected true: {body}"
            meta["detail"] = f"HTTP {status}; latency={latency:.2f}s"
            STATE["backend_available"] = True
            STATE["backend_unavailable_reason"] = ""


@pytest.mark.asyncio
async def test_scenario_01_warm_user_recommendation():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("01") as meta:
            warm, latency = await _warm_recommendation(client)
            response = warm["response"]
            body = warm["body"]
            _assert_status(response, 200, body, context="Scenario 01 /user_api")
            assert latency < TIMEOUT, f"Scenario 01 exceeded timeout threshold: {latency:.2f}s"
            assert body.get("state") == "completed", f"Scenario 01 expected state=completed: {body}"

            recs = body.get("recommendations")
            assert isinstance(recs, list), f"Scenario 01 recommendations must be a list: {body}"
            assert len(recs) == 5, f"Scenario 01 expected 5 recommendations, got {len(recs)}; body={body}"
            for idx, item in enumerate(recs):
                _assert_valid_recommendation(item, context=f"Scenario 01 recommendation #{idx + 1}")

            session_id = str(body.get("session_id") or "").strip()
            _assert_non_empty_string(session_id, field="session_id", context="Scenario 01")
            assert session_id.startswith("session-"), f"Scenario 01 session_id should start with 'session-': {session_id!r}"

            rpa = body.get("partner_results", {}).get("rpa", {})
            rda = body.get("partner_results", {}).get("rda", {})
            assert rpa.get("cold_start") is False, f"Scenario 01 expected hot-start profile; partner_results.rpa={rpa}"
            assert str(rda.get("chosen_action") or "") != "conservative", (
                f"Scenario 01 expected non-conservative RDA action; partner_results.rda={rda}"
            )

            partner_tasks = body.get("partner_tasks")
            assert isinstance(partner_tasks, dict), f"Scenario 01 partner_tasks must be a dict: {body}"
            for key in ("rpa", "bca", "rda", "engine"):
                assert key in partner_tasks, f"Scenario 01 missing partner_tasks[{key!r}]; body={body}"
                assert partner_tasks[key].get("state") == "completed", (
                    f"Scenario 01 expected partner task {key} completed; got {partner_tasks[key]}"
                )

            meta["detail"] = f"session_id={session_id}; books={len(recs)}; latency={latency:.2f}s"
            STATE["artifacts"]["warm_response"] = body
            STATE["artifacts"]["warm_session_id"] = session_id
            STATE["artifacts"]["warm_book_ids"] = _book_id_list(body)
            STATE["artifacts"]["warm_context_type"] = str(rda.get("context_type") or "")
            STATE["artifacts"]["warm_arm_action"] = str(rda.get("chosen_action") or "")
            STATE["artifacts"]["warm_initial_profile_count"] = int(rpa.get("event_count") or 0)


@pytest.mark.asyncio
async def test_scenario_02_cold_user_fallback():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("02") as meta:
            payload = {
                "user_id": USER_COLD,
                "query": "随便推荐几本书",
                "session_id": None,
                "constraints": {"top_k": 5, "scenario": "cold"},
            }
            response, body, latency = await _request_json(client, "POST", "/user_api", json_body=payload)
            _assert_status(response, 200, body, context="Scenario 02 /user_api")
            assert latency < TIMEOUT, f"Scenario 02 exceeded timeout threshold: {latency:.2f}s"
            recs = body.get("recommendations")
            assert isinstance(recs, list) and len(recs) > 0, f"Scenario 02 expected recommendations, got {body}"
            rpa = body.get("partner_results", {}).get("rpa", {})
            rda = body.get("partner_results", {}).get("rda", {})
            assert rpa.get("cold_start") is True, f"Scenario 02 expected cold-start profile; partner_results.rpa={rpa}"
            assert str(rda.get("chosen_action") or "") == "conservative", (
                f"Scenario 02 expected conservative RDA action; partner_results.rda={rda}"
            )
            for idx, item in enumerate(recs):
                justification = str(item.get("justification") or "")
                assert justification.strip(), f"Scenario 02 recommendation #{idx + 1} missing justification; item={item}"
            meta["detail"] = f"recommendations={len(recs)}; latency={latency:.2f}s"


@pytest.mark.asyncio
async def test_scenario_03_session_reuse_across_turns():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("03") as meta:
            first_payload = {
                "user_id": USER_WARM,
                "query": "推荐一本关于旅行的书",
                "session_id": None,
                "constraints": {"top_k": 5, "scenario": "warm"},
            }
            first_response, first_body, first_latency = await _request_json(
                client, "POST", "/user_api", json_body=first_payload
            )
            _assert_status(first_response, 200, first_body, context="Scenario 03 first /user_api")
            session_id = str(first_body.get("session_id") or "").strip()
            assert session_id, f"Scenario 03 first turn did not return session_id: {first_body}"
            first_books = _book_id_list(first_body)

            second_payload = {
                "user_id": USER_WARM,
                "query": "我想看悬疑小说",
                "session_id": session_id,
                "constraints": {"top_k": 5, "scenario": "warm"},
            }
            second_response, second_body, second_latency = await _request_json(
                client, "POST", "/user_api", json_body=second_payload
            )
            _assert_status(second_response, 200, second_body, context="Scenario 03 second /user_api")
            assert str(second_body.get("session_id") or "").strip() == session_id, (
                f"Scenario 03 expected session reuse, got {second_body.get('session_id')!r} vs {session_id!r}"
            )

            second_books = _book_id_list(second_body)
            assert first_books and second_books, f"Scenario 03 expected non-empty recommendation lists: {first_body}, {second_body}"
            assert first_books != second_books, (
                f"Scenario 03 expected diversity across turns, but book_id lists are identical: {first_books}"
            )
            meta["detail"] = f"session_id={session_id}; first={first_latency:.2f}s; second={second_latency:.2f}s"


@pytest.mark.asyncio
async def test_scenario_04_positive_feedback_profile_updates():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("04") as meta:
            warm, _ = await _warm_recommendation(client)
            warm_body = warm["body"]
            session_id = str(warm_body.get("session_id") or STATE["artifacts"].get("warm_session_id") or "").strip()
            assert session_id, f"Scenario 04 requires a warm session_id; warm body={warm_body}"
            rec_ids = _book_id_list(warm_body)
            assert rec_ids, f"Scenario 04 requires recommendation book ids; warm body={warm_body}"
            context_type = str(warm_body.get("partner_results", {}).get("rda", {}).get("context_type") or "")
            arm_action = str(warm_body.get("partner_results", {}).get("rda", {}).get("chosen_action") or "")

            initial_profile_count = STATE["artifacts"].get("warm_initial_profile_count")
            if not isinstance(initial_profile_count, int):
                initial_profile_count = 0

            triggers_seen: List[bool] = []
            last_response: Dict[str, Any] = {}
            for idx in range(20):
                book_id = rec_ids[idx % len(rec_ids)] if idx % 2 == 0 else f"uat-feedback-book-{idx:02d}"
                payload = {
                    "user_id": USER_WARM,
                    "session_id": session_id,
                    "book_id": book_id,
                    "event_type": "rate_5",
                    "context_type": context_type,
                    "arm_action": arm_action,
                }
                response, body, _ = await _request_json(client, "POST", "/api/feedback", json_body=payload)
                _assert_status(response, 200, body, context="Scenario 04 /api/feedback")
                assert body.get("status") == "accepted", f"Scenario 04 expected accepted feedback response: {body}"
                profile_updated = bool(body.get("triggers", {}).get("profile_updated"))
                triggers_seen.append(profile_updated)
                last_response = body

            assert any(triggers_seen), (
                f"Scenario 04 expected at least one profile update after 20 feedback events; "
                f"initial_count={initial_profile_count}; body={last_response}"
            )

            profile_response, profile_body, _ = await _request_json(
                client, "GET", "/api/profile", params={"user_id": USER_WARM}
            )
            _assert_status(profile_response, 200, profile_body, context="Scenario 04 /api/profile")
            assert profile_body.get("event_count", 0) >= initial_profile_count + 20 or profile_body.get("event_count", 0) >= 20, (
                f"Scenario 04 expected profile event_count to grow; initial={initial_profile_count}; profile={profile_body}"
            )
            assert profile_body.get("cold_start") is False, f"Scenario 04 expected warm profile after feedback loop: {profile_body}"

            first_trigger_idx = next((idx + 1 for idx, flag in enumerate(triggers_seen) if flag), None)
            meta["detail"] = (
                f"first_trigger={first_trigger_idx}; profile_count={profile_body.get('event_count')}; "
                f"last_trigger={triggers_seen[-1] if triggers_seen else None}"
            )
            STATE["artifacts"]["positive_feedback_last_response"] = last_response
            STATE["artifacts"]["positive_feedback_profile"] = profile_body


@pytest.mark.asyncio
async def test_scenario_05_repeated_negative_feedback_is_stable():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("05") as meta:
            warm, _ = await _warm_recommendation(client)
            warm_body = warm["body"]
            session_id = str(warm_body.get("session_id") or STATE["artifacts"].get("warm_session_id") or "").strip()
            assert session_id, f"Scenario 05 requires a session_id; warm body={warm_body}"
            book_id = (_book_id_list(warm_body) or ["book_001"])[0]
            for idx in range(3):
                payload = {
                    "user_id": USER_WARM,
                    "session_id": session_id,
                    "book_id": book_id,
                    "event_type": "rate_1",
                }
                response, body, _ = await _request_json(client, "POST", "/api/feedback", json_body=payload)
                _assert_status(response, 200, body, context=f"Scenario 05 /api/feedback attempt {idx + 1}")
                assert body.get("status") == "accepted", f"Scenario 05 expected accepted response on attempt {idx + 1}: {body}"
            meta["detail"] = f"book_id={book_id}; attempts=3"


@pytest.mark.asyncio
async def test_scenario_06_feedback_without_session_id_rejected():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("06") as meta:
            payload = {
                "user_id": USER_WARM,
                "session_id": "",
                "book_id": "book_001",
                "event_type": "click",
            }
            response, body, _ = await _request_json(client, "POST", "/api/feedback", json_body=payload)
            assert response.status_code == 400, f"Scenario 06 expected HTTP 400, got {response.status_code}; body={body}"
            assert response.status_code != 500, f"Scenario 06 must not return HTTP 500; body={body}"
            assert any(key in body for key in ("detail", "message")), f"Scenario 06 expected error details in response: {body}"
            meta["detail"] = f"HTTP {response.status_code}"


@pytest.mark.asyncio
async def test_scenario_07_empty_query_is_rejected():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("07") as meta:
            payload = {
                "user_id": USER_WARM,
                "query": "",
                "session_id": None,
            }
            response, body, _ = await _request_json(client, "POST", "/user_api", json_body=payload)
            assert response.status_code == 400, f"Scenario 07 expected HTTP 400, got {response.status_code}; body={body}"
            assert response.status_code != 500, f"Scenario 07 must not return HTTP 500; body={body}"
            meta["detail"] = f"HTTP {response.status_code}"


@pytest.mark.asyncio
async def test_scenario_08_unknown_user_falls_back_to_cold_start():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("08") as meta:
            payload = {
                "user_id": "ghost_user_nonexistent_99999",
                "query": "科幻小说推荐",
                "session_id": None,
            }
            response, body, latency = await _request_json(client, "POST", "/user_api", json_body=payload)
            _assert_status(response, 200, body, context="Scenario 08 /user_api")
            recs = body.get("recommendations")
            assert isinstance(recs, list) and len(recs) > 0, f"Scenario 08 expected cold-start recommendations: {body}"
            rpa = body.get("partner_results", {}).get("rpa", {})
            assert rpa.get("cold_start") is True, f"Scenario 08 expected cold_start=true for unknown user; partner_results.rpa={rpa}"
            meta["detail"] = f"recommendations={len(recs)}; latency={latency:.2f}s"


@pytest.mark.asyncio
async def test_scenario_09_top_k_is_clamped():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("09") as meta:
            payload = {
                "user_id": USER_WARM,
                "query": "历史小说",
                "session_id": None,
                "constraints": {"top_k": 999},
            }
            response, body, latency = await _request_json(client, "POST", "/user_api", json_body=payload)
            _assert_status(response, 200, body, context="Scenario 09 /user_api")
            recs = body.get("recommendations")
            assert isinstance(recs, list), f"Scenario 09 recommendations must be a list: {body}"
            assert len(recs) <= 10, f"Scenario 09 expected clamp <= 10, got {len(recs)}; body={body}"
            assert latency < TIMEOUT, f"Scenario 09 exceeded timeout threshold: {latency:.2f}s"
            meta["detail"] = f"recommendations={len(recs)}; latency={latency:.2f}s"


@pytest.mark.asyncio
async def test_scenario_10_profile_snapshot_shape():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("10") as meta:
            response, body, latency = await _request_json(
                client, "GET", "/api/profile", params={"user_id": USER_WARM}
            )
            _assert_status(response, 200, body, context="Scenario 10 /api/profile")
            for field in ("user_id", "confidence", "cold_start", "event_count"):
                assert field in body, f"Scenario 10 missing field {field!r}: {body}"
            confidence = body.get("confidence")
            assert isinstance(confidence, (int, float)), f"Scenario 10 confidence must be numeric: {body}"
            assert 0.0 <= float(confidence) <= 1.0, f"Scenario 10 confidence must be within [0,1]: {body}"
            assert "profile_vector" not in body, f"Scenario 10 must not expose profile_vector: {body}"
            meta["detail"] = f"event_count={body.get('event_count')}; latency={latency:.2f}s"

            ghost_response, ghost_body, _ = await _request_json(
                client, "GET", "/api/profile", params={"user_id": "ghost_user_99999"}
            )
            assert ghost_response.status_code in {200, 404}, (
                f"Scenario 10 expected 200 or 404 for missing user, got {ghost_response.status_code}; body={ghost_body}"
            )
            assert ghost_response.status_code != 500, f"Scenario 10 must not return HTTP 500 for missing user; body={ghost_body}"


@pytest.mark.asyncio
async def test_scenario_11_recommendation_copy_quality():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("11") as meta:
            warm, _ = await _warm_recommendation(client)
            body = warm["body"]
            recs = body.get("recommendations")
            assert isinstance(recs, list) and recs, f"Scenario 11 expected warm recommendations: {body}"
            seen_ids: set[str] = set()
            scores: List[float] = []
            for idx, item in enumerate(recs):
                _assert_valid_recommendation(item, context=f"Scenario 11 recommendation #{idx + 1}")
                book_id = str(item.get("book_id") or "")
                assert book_id not in seen_ids, f"Scenario 11 expected unique book_id values, duplicate {book_id!r}: {recs}"
                seen_ids.add(book_id)
                scores.append(float(item.get("score_total") or 0.0))
                novelty_score = item.get("novelty_score")
                if novelty_score is not None:
                    assert isinstance(novelty_score, (int, float)), f"Scenario 11 novelty_score must be numeric: {item}"
                    assert 0.0 <= float(novelty_score) <= 1.0, f"Scenario 11 novelty_score out of range: {item}"
                assert 0.0 <= float(item.get("score_total") or 0.0) <= 1.0, f"Scenario 11 score_total out of range: {item}"

            top_three = scores[:3]
            assert len(top_three) >= 3, f"Scenario 11 needs at least 3 recommendations to verify rank ordering: {recs}"
            assert top_three[0] >= top_three[1] >= top_three[2], (
                f"Scenario 11 expected score_total to be non-increasing for the top 3 items: {top_three}"
            )
            meta["detail"] = f"unique_books={len(seen_ids)}; top3={top_three[:3]}"


@pytest.mark.asyncio
async def test_scenario_12_latency_benchmark():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("12") as meta:
            queries = [
                "想看轻松一点的旅行小说",
                "推荐一本关于友情与成长的书",
                "我想找节奏快一点的悬疑书",
                "给我几本科幻题材的好书",
                "推荐一本历史题材的小说",
            ]
            latencies: List[float] = []
            for query in queries:
                payload = {
                    "user_id": USER_WARM,
                    "query": query,
                    "session_id": None,
                    "constraints": {"top_k": 5, "scenario": "warm"},
                }
                response, body, latency = await _request_json(client, "POST", "/user_api", json_body=payload)
                _assert_status(response, 200, body, context=f"Scenario 12 /user_api query={query!r}")
                assert latency <= TIMEOUT, f"Scenario 12 request exceeded timeout threshold: {latency:.2f}s; query={query!r}"
                latencies.append(latency)

            assert len(latencies) == 5, f"Scenario 12 expected 5 latency samples, got {len(latencies)}"
            p50 = float(median(latencies))
            sorted_latencies = sorted(latencies)
            p90_index = max(0, math.ceil(0.9 * len(sorted_latencies)) - 1)
            p90 = float(sorted_latencies[p90_index])
            max_latency = float(max(sorted_latencies))
            assert max_latency <= TIMEOUT, f"Scenario 12 observed latency over TIMEOUT: {max_latency:.2f}s"
            meta["status"] = "WARN" if p50 > 15.0 else "PASS"
            meta["detail"] = f"P50={p50:.2f}s | P90={p90:.2f}s | Max={max_latency:.2f}s"


@pytest.mark.asyncio
async def test_scenario_13_full_end_to_end_flow():
    _require_backend_ready()
    async with _open_client() as client:
        with _scenario_context("13") as meta:
            step1_response, step1_body, _ = await _request_json(client, "GET", "/demo/status")
            _assert_status(step1_response, 200, step1_body, context="Scenario 13 step 1 /demo/status")

            step2_response, step2_body, _ = await _request_json(
                client, "GET", "/api/profile", params={"user_id": USER_WARM}
            )
            _assert_status(step2_response, 200, step2_body, context="Scenario 13 step 2 /api/profile")
            initial_event_count = int(step2_body.get("event_count") or 0)

            step3_payload = {
                "user_id": USER_WARM,
                "query": "推荐一本关于旅行的书",
                "session_id": None,
                "constraints": {"top_k": 5, "scenario": "warm"},
            }
            step3_response, step3_body, _ = await _request_json(client, "POST", "/user_api", json_body=step3_payload)
            _assert_status(step3_response, 200, step3_body, context="Scenario 13 step 3 /user_api")
            session_id = str(step3_body.get("session_id") or "").strip()
            assert session_id, f"Scenario 13 step 3 did not return session_id: {step3_body}"
            book_ids_step3 = _book_id_list(step3_body)
            assert book_ids_step3, f"Scenario 13 step 3 expected recommendations: {step3_body}"

            rda = step3_body.get("partner_results", {}).get("rda", {})
            step4_payload = {
                "user_id": USER_WARM,
                "session_id": session_id,
                "book_id": book_ids_step3[0],
                "event_type": "finish",
                "context_type": str(rda.get("context_type") or ""),
                "arm_action": str(rda.get("chosen_action") or ""),
            }
            step4_response, step4_body, _ = await _request_json(client, "POST", "/api/feedback", json_body=step4_payload)
            _assert_status(step4_response, 200, step4_body, context="Scenario 13 step 4 /api/feedback")
            assert step4_body.get("status") == "accepted", f"Scenario 13 step 4 expected accepted feedback response: {step4_body}"

            if bool(step4_body.get("triggers", {}).get("profile_updated")):
                step5_response, step5_body, _ = await _request_json(
                    client, "GET", "/api/profile", params={"user_id": USER_WARM}
                )
                _assert_status(step5_response, 200, step5_body, context="Scenario 13 step 5 /api/profile")
                assert int(step5_body.get("event_count") or 0) >= initial_event_count, (
                    f"Scenario 13 expected profile event_count to remain non-decreasing after feedback: "
                    f"before={initial_event_count}, after={step5_body}"
                )

            step6_payload = {
                "user_id": USER_WARM,
                "query": "想看悬疑小说",
                "session_id": session_id,
                "constraints": {"top_k": 5, "scenario": "warm"},
            }
            step6_response, step6_body, _ = await _request_json(client, "POST", "/user_api", json_body=step6_payload)
            _assert_status(step6_response, 200, step6_body, context="Scenario 13 step 6 /user_api")
            book_ids_step6 = _book_id_list(step6_body)
            assert book_ids_step6, f"Scenario 13 step 6 expected recommendations: {step6_body}"
            assert book_ids_step6 != book_ids_step3, (
                f"Scenario 13 expected second recommendation list to differ from the first: step3={book_ids_step3}, step6={book_ids_step6}"
            )

            meta["detail"] = f"session_id={session_id}; step3_books={len(book_ids_step3)}; step6_books={len(book_ids_step6)}"
            STATE["artifacts"]["full_flow_step3"] = step3_body
            STATE["artifacts"]["full_flow_step4"] = step4_body
            STATE["artifacts"]["full_flow_step6"] = step6_body
