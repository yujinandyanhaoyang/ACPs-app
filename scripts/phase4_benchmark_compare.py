import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import httpx

_CURRENT_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import reading_concierge.reading_concierge as concierge_module
from reading_concierge.reading_concierge import app as concierge_app
from services.baseline_rankers import traditional_hybrid_rank, multi_agent_proxy_rank
from services.phase4_benchmark import aggregate_method_runs, evaluate_method_case, rank_methods


BASELINE_METHODS: Dict[str, Callable[[Dict[str, Any], int], List[Dict[str, Any]]]] = {
    "traditional_hybrid": traditional_hybrid_rank,
    "multi_agent_proxy": multi_agent_proxy_rank,
}


DEFAULT_FINDING_THRESHOLDS: Dict[str, float] = {
    "quality_ndcg_good": 0.8,
    "quality_ndcg_warn": 0.7,
    "latency_mean_warn_ms": 7000.0,
    "reliability_fallback_warn": 0.2,
    "reliability_strict_fail_warn": 0.1,
    "reliability_remote_success_good": 0.2,
}


class _RemoteStressPatch:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._orig_partner_mode = None
        self._orig_resolve_remote = None
        self._orig_invoke_remote = None

    async def __aenter__(self):
        if not self.enabled:
            return self

        self._orig_partner_mode = concierge_module.PARTNER_MODE
        self._orig_resolve_remote = concierge_module._resolve_remote_partner_url
        self._orig_invoke_remote = concierge_module._invoke_remote_rpc

        concierge_module.PARTNER_MODE = "auto"

        async def _fake_resolve_remote(partner_key: str):
            return f"http://127.0.0.1:9999/remote-stress/{partner_key}"

        async def _fake_invoke_remote(rpc_url: str, payload: Dict[str, Any], task_id: str | None = None):
            raise RuntimeError(f"synthetic remote stress failure: {rpc_url}")

        concierge_module._resolve_remote_partner_url = _fake_resolve_remote
        concierge_module._invoke_remote_rpc = _fake_invoke_remote
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if not self.enabled:
            return False

        concierge_module.PARTNER_MODE = self._orig_partner_mode
        concierge_module._resolve_remote_partner_url = self._orig_resolve_remote
        concierge_module._invoke_remote_rpc = self._orig_invoke_remote
        return False


def _is_remote_stress_case(case: Dict[str, Any]) -> bool:
    constraints = case.get("constraints") or {}
    return constraints.get("remote_stress") is True


def _load_cases(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("cases file must be a JSON list")
    return payload


def _acps_constraints(base_constraints: Dict[str, Any]) -> Dict[str, Any]:
    constraints = {**(base_constraints or {})}
    constraints.setdefault("top_k", 5)
    constraints.setdefault(
        "scoring_weights",
        {
            "collaborative": 0.25,
            "semantic": 0.35,
            "knowledge": 0.2,
            "diversity": 0.2,
        },
    )
    constraints.setdefault("novelty_threshold", 0.45)
    constraints.setdefault("min_new_items", 0)
    return constraints


async def _run_acps_case(client: httpx.AsyncClient, case: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "query": case.get("query") or "",
        "user_profile": case.get("user_profile") or {},
        "history": case.get("history") or [],
        "reviews": case.get("reviews") or [],
        "books": case.get("books") or [],
        "candidate_ids": case.get("candidate_ids") or [],
        "constraints": _acps_constraints(case.get("constraints") or {}),
    }

    start = time.perf_counter()
    async with _RemoteStressPatch(_is_remote_stress_case(case)):
        response = await client.post("/user_api", json=payload)
    latency_ms = round((time.perf_counter() - start) * 1000, 4)
    response.raise_for_status()
    body = response.json()

    metrics = ((body.get("evaluation") or {}).get("metrics") or {})
    recommendations = body.get("recommendations") or []
    top_k = int((payload.get("constraints") or {}).get("top_k") or len(recommendations) or 1)
    ground_truth = (payload.get("constraints") or {}).get("ground_truth_ids") or []

    if metrics.get("precision_at_k") is None:
        metrics = evaluate_method_case(recommendations, ground_truth, top_k)

    strict_remote_validation = bool((payload.get("constraints") or {}).get("strict_remote_validation", False))

    partner_tasks = body.get("partner_tasks") or {}
    task_rows = [row for row in partner_tasks.values() if isinstance(row, dict)]
    task_count = len(task_rows)
    remote_attempted_count = sum(1 for row in task_rows if row.get("remote_attempted") is True)
    fallback_count = sum(1 for row in task_rows if row.get("fallback") is True)
    remote_success_count = sum(1 for row in task_rows if str(row.get("route") or "") == "remote")

    if task_count:
        remote_attempt_rate = round(remote_attempted_count / task_count, 4)
        fallback_rate = round(fallback_count / task_count, 4)
        remote_success_rate = round(remote_success_count / task_count, 4)
    else:
        remote_attempt_rate = 0.0
        fallback_rate = 0.0
        remote_success_rate = 0.0

    return {
        "case_id": case.get("case_id"),
        "state": body.get("state"),
        "metrics": metrics,
        "latency_ms": latency_ms,
        "strict_remote_validation": strict_remote_validation,
        "strict_failure": 1.0 if strict_remote_validation and body.get("state") != "completed" else 0.0,
        "remote_attempt_rate": remote_attempt_rate,
        "fallback_rate": fallback_rate,
        "remote_success_rate": remote_success_rate,
        "task_count": task_count,
        "remote_attempted_count": remote_attempted_count,
        "fallback_count": fallback_count,
        "recommendations": recommendations,
    }


def _run_baseline_case(method_name: str, case: Dict[str, Any]) -> Dict[str, Any]:
    top_k = int(((case.get("constraints") or {}).get("top_k") or 5))
    ground_truth = ((case.get("constraints") or {}).get("ground_truth_ids") or [])

    ranker = BASELINE_METHODS[method_name]
    start = time.perf_counter()
    recommendations = ranker(case, top_k=top_k)
    latency_ms = round((time.perf_counter() - start) * 1000, 4)
    metrics = evaluate_method_case(recommendations, ground_truth, top_k)

    return {
        "case_id": case.get("case_id"),
        "state": "completed" if recommendations else "needs_input",
        "metrics": metrics,
        "latency_ms": latency_ms,
        "strict_remote_validation": False,
        "strict_failure": 0.0,
        "remote_attempt_rate": 0.0,
        "fallback_rate": 0.0,
        "remote_success_rate": 0.0,
        "task_count": 0,
        "remote_attempted_count": 0,
        "fallback_count": 0,
        "recommendations": recommendations,
    }


def _build_reliability_dashboard(method_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    methods = {row.get("method"): row for row in method_reports}
    acps = methods.get("acps_multi_agent") or {}
    acps_runs = acps.get("runs") or []
    acps_summary = acps.get("summary") or {}

    strict_runs = [row for row in acps_runs if row.get("strict_remote_validation") is True]
    fallback_mode_runs = [row for row in acps_runs if row.get("strict_remote_validation") is not True]

    strict_failure_runs = sum(1 for row in strict_runs if row.get("strict_failure") == 1.0)
    fallback_observed_runs = sum(1 for row in fallback_mode_runs if float(row.get("fallback_rate") or 0.0) > 0.0)

    def _rate(part: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return round(part / total, 4)

    return {
        "acps_reliability": {
            "strict_mode": {
                "case_count": len(strict_runs),
                "failure_case_count": strict_failure_runs,
                "failure_rate": _rate(strict_failure_runs, len(strict_runs)),
            },
            "fallback_mode": {
                "case_count": len(fallback_mode_runs),
                "fallback_observed_case_count": fallback_observed_runs,
                "fallback_observed_rate": _rate(fallback_observed_runs, len(fallback_mode_runs)),
            },
            "overall": {
                "remote_attempt_rate": round(float(acps_summary.get("remote_attempt_rate") or 0.0), 4),
                "fallback_rate": round(float(acps_summary.get("fallback_rate") or 0.0), 4),
                "remote_success_rate": round(float(acps_summary.get("remote_success_rate") or 0.0), 4),
                "strict_failure_rate": round(float(acps_summary.get("strict_failure_rate") or 0.0), 4),
            },
        }
    }


def _build_compact_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    winner = report.get("winner") or {}
    methods = report.get("methods") or []
    by_method = {row.get("method"): row for row in methods}
    acps_summary = (by_method.get("acps_multi_agent") or {}).get("summary") or {}
    reliability_dashboard = report.get("reliability_dashboard") or {}

    return {
        "generated_at": report.get("generated_at"),
        "case_count": report.get("case_count"),
        "winner_method": winner.get("method"),
        "winner_objective_score": winner.get("objective_score"),
        "acps_quality": {
            "precision_at_k": acps_summary.get("precision_at_k"),
            "recall_at_k": acps_summary.get("recall_at_k"),
            "ndcg_at_k": acps_summary.get("ndcg_at_k"),
        },
        "acps_efficiency": {
            "latency_ms_mean": acps_summary.get("latency_ms_mean"),
        },
        "acps_reliability": (reliability_dashboard.get("acps_reliability") or {}),
    }


def _build_findings_and_recommendations(
    summary: Dict[str, Any],
    thresholds: Dict[str, float] | None = None,
) -> Dict[str, List[str]]:
    rules = thresholds or DEFAULT_FINDING_THRESHOLDS
    quality = summary.get("acps_quality") or {}
    efficiency = summary.get("acps_efficiency") or {}
    reliability = summary.get("acps_reliability") or {}
    overall = reliability.get("overall") or {}

    findings: List[str] = []
    recommendations: List[str] = []

    ndcg = float(quality.get("ndcg_at_k") or 0.0)
    latency = float(efficiency.get("latency_ms_mean") or 0.0)
    fallback_rate = float(overall.get("fallback_rate") or 0.0)
    strict_failure_rate = float(overall.get("strict_failure_rate") or 0.0)
    remote_success_rate = float(overall.get("remote_success_rate") or 0.0)

    if ndcg >= rules["quality_ndcg_good"]:
        findings.append(f"Ranking quality is strong (NDCG@k={ndcg:.4f}).")
    elif ndcg >= rules["quality_ndcg_warn"]:
        findings.append(f"Ranking quality is acceptable but improvable (NDCG@k={ndcg:.4f}).")
        recommendations.append("Tune semantic/collaborative weights for marginal quality gains.")
    else:
        findings.append(f"Ranking quality is below target (NDCG@k={ndcg:.4f}).")
        recommendations.append("Prioritize scoring and candidate-quality optimization before deployment.")

    if latency > rules["latency_mean_warn_ms"]:
        findings.append(f"Average latency is high (mean={latency:.4f} ms).")
        recommendations.append("Reduce model/runtime overhead or increase async parallelism to lower latency.")
    else:
        findings.append(f"Latency is within current threshold (mean={latency:.4f} ms).")

    if fallback_rate > rules["reliability_fallback_warn"]:
        findings.append(f"Fallback dependency is elevated (fallback_rate={fallback_rate:.4f}).")
        recommendations.append("Improve remote endpoint stability and discovery quality to reduce fallback frequency.")
    else:
        findings.append(f"Fallback dependency remains controlled (fallback_rate={fallback_rate:.4f}).")

    if strict_failure_rate > rules["reliability_strict_fail_warn"]:
        findings.append(f"Strict-mode failures are notable (strict_failure_rate={strict_failure_rate:.4f}).")
        recommendations.append("Harden remote infra path (timeout/retry/availability checks) before strict-mode rollout.")
    else:
        findings.append(f"Strict-mode failure rate is low (strict_failure_rate={strict_failure_rate:.4f}).")

    if remote_success_rate >= rules["reliability_remote_success_good"]:
        findings.append(f"Remote success signal is healthy (remote_success_rate={remote_success_rate:.4f}).")
    else:
        findings.append(f"Remote success signal is limited (remote_success_rate={remote_success_rate:.4f}).")
        recommendations.append("Add more remote-healthy scenarios to validate non-fallback execution confidence.")

    if not recommendations:
        recommendations.append("Keep current configuration and expand benchmark coverage for stronger confidence.")

    return {"findings": findings, "recommendations": recommendations}


def _build_markdown_report(report: Dict[str, Any], summary: Dict[str, Any]) -> str:
    generated_at = summary.get("generated_at") or report.get("generated_at") or "n/a"
    case_count = summary.get("case_count") or report.get("case_count") or 0
    winner_method = summary.get("winner_method") or "n/a"
    winner_score = summary.get("winner_objective_score")

    quality = summary.get("acps_quality") or {}
    efficiency = summary.get("acps_efficiency") or {}
    reliability = summary.get("acps_reliability") or {}
    strict_mode = reliability.get("strict_mode") or {}
    fallback_mode = reliability.get("fallback_mode") or {}
    overall = reliability.get("overall") or {}
    decision = _build_findings_and_recommendations(summary)

    def _fmt_num(value: Any) -> str:
        if value is None:
            return "n/a"
        try:
            return f"{float(value):.4f}"
        except (TypeError, ValueError):
            return str(value)

    lines = [
        "# Phase IV Benchmark Report (Compact)",
        "",
        "## Run Summary",
        f"- Generated at: {generated_at}",
        f"- Case count: {case_count}",
        f"- Winner method: {winner_method}",
        f"- Winner objective score: {_fmt_num(winner_score)}",
        "",
        "## ACPs Quality",
        f"- Precision@k: {_fmt_num(quality.get('precision_at_k'))}",
        f"- Recall@k: {_fmt_num(quality.get('recall_at_k'))}",
        f"- NDCG@k: {_fmt_num(quality.get('ndcg_at_k'))}",
        "",
        "## ACPs Efficiency",
        f"- Latency mean (ms): {_fmt_num(efficiency.get('latency_ms_mean'))}",
        "",
        "## ACPs Reliability Dashboard",
        "### Strict Mode",
        f"- Case count: {strict_mode.get('case_count', 0)}",
        f"- Failure case count: {strict_mode.get('failure_case_count', 0)}",
        f"- Failure rate: {_fmt_num(strict_mode.get('failure_rate'))}",
        "",
        "### Fallback Mode",
        f"- Case count: {fallback_mode.get('case_count', 0)}",
        f"- Fallback observed case count: {fallback_mode.get('fallback_observed_case_count', 0)}",
        f"- Fallback observed rate: {_fmt_num(fallback_mode.get('fallback_observed_rate'))}",
        "",
        "### Overall",
        f"- Remote attempt rate: {_fmt_num(overall.get('remote_attempt_rate'))}",
        f"- Fallback rate: {_fmt_num(overall.get('fallback_rate'))}",
        f"- Remote success rate: {_fmt_num(overall.get('remote_success_rate'))}",
        f"- Strict failure rate: {_fmt_num(overall.get('strict_failure_rate'))}",
        "",
        "## Findings & Recommendations",
        "### Findings",
    ]
    for item in decision.get("findings") or []:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("### Recommendations")
    for item in decision.get("recommendations") or []:
        lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


async def run_benchmark(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    reports: List[Dict[str, Any]] = []

    acps_runs: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=concierge_app), base_url="http://local") as client:
        for case in cases:
            acps_runs.append(await _run_acps_case(client, case))

    reports.append({"method": "acps_multi_agent", "runs": acps_runs, "summary": aggregate_method_runs(acps_runs)})

    for method_name in BASELINE_METHODS:
        runs = []
        for case in cases:
            runs.append(_run_baseline_case(method_name, case))
        reports.append({"method": method_name, "runs": runs, "summary": aggregate_method_runs(runs)})

    leaderboard = rank_methods(reports)
    reliability_dashboard = _build_reliability_dashboard(reports)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "case_count": len(cases),
        "methods": reports,
        "leaderboard": leaderboard,
        "winner": leaderboard[0] if leaderboard else {},
        "reliability_dashboard": reliability_dashboard,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase IV benchmark compare (ACPs vs baselines)")
    parser.add_argument("--cases", default="scripts/phase4_cases.json")
    parser.add_argument("--out", default="scripts/phase4_benchmark_report.json")
    parser.add_argument("--summary-out", default="scripts/phase4_benchmark_summary.json")
    parser.add_argument("--md-out", default="scripts/phase4_benchmark_report.md")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    cases = _load_cases(Path(args.cases))
    report = asyncio.run(run_benchmark(cases))

    output = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None)
    Path(args.out).write_text(output, encoding="utf-8")

    summary = _build_compact_summary(report)
    summary_output = json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None)
    Path(args.summary_out).write_text(summary_output, encoding="utf-8")

    markdown_output = _build_markdown_report(report, summary)
    Path(args.md_out).write_text(markdown_output, encoding="utf-8")

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
