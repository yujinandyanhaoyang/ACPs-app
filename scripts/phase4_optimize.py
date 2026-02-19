import argparse
import asyncio
import json
import time
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx

_CURRENT_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from reading_concierge.reading_concierge import app as concierge_app
from services.phase4_optimizer import aggregate_experiment_runs, select_best_experiment


DEFAULT_CONFIGS: List[Dict[str, Any]] = [
    {
        "config_id": "baseline",
        "scoring_weights": {
            "collaborative": 0.25,
            "semantic": 0.35,
            "knowledge": 0.2,
            "diversity": 0.2,
        },
        "novelty_threshold": 0.45,
        "min_new_items": 0,
    },
    {
        "config_id": "novelty_plus",
        "scoring_weights": {
            "collaborative": 0.2,
            "semantic": 0.25,
            "knowledge": 0.2,
            "diversity": 0.35,
        },
        "novelty_threshold": 0.5,
        "min_new_items": 1,
    },
    {
        "config_id": "semantic_plus",
        "scoring_weights": {
            "collaborative": 0.2,
            "semantic": 0.45,
            "knowledge": 0.2,
            "diversity": 0.15,
        },
        "novelty_threshold": 0.4,
        "min_new_items": 0,
    },
]


def _load_cases(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("phase4 cases file must be a JSON list")
    return payload


def _merge_case_with_config(case: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    constraints = {**(case.get("constraints") or {})}
    constraints["scoring_weights"] = config.get("scoring_weights") or constraints.get("scoring_weights")
    constraints["novelty_threshold"] = config.get("novelty_threshold", constraints.get("novelty_threshold", 0.45))
    constraints["min_new_items"] = config.get("min_new_items", constraints.get("min_new_items", 0))

    return {
        "query": case.get("query") or "",
        "user_profile": case.get("user_profile") or {},
        "history": case.get("history") or [],
        "reviews": case.get("reviews") or [],
        "books": case.get("books") or [],
        "candidate_ids": case.get("candidate_ids") or [],
        "constraints": constraints,
    }


async def _run_case_local(client: httpx.AsyncClient, payload: Dict[str, Any]) -> Dict[str, Any]:
    start = time.perf_counter()
    response = await client.post("/user_api", json=payload)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.raise_for_status()
    body = response.json()
    return {
        "state": body.get("state"),
        "metrics": ((body.get("evaluation") or {}).get("metrics") or {}),
        "latency_ms": round(elapsed_ms, 4),
    }


async def run_optimization(cases: List[Dict[str, Any]], configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    experiments: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=concierge_app), base_url="http://local") as client:
        for config in configs:
            case_runs: List[Dict[str, Any]] = []
            for case in cases:
                payload = _merge_case_with_config(case, config)
                run = await _run_case_local(client, payload)
                run["case_id"] = case.get("case_id")
                case_runs.append(run)

            experiments.append(
                {
                    "config": config,
                    "runs": case_runs,
                    "summary": aggregate_experiment_runs(case_runs),
                }
            )

    best = select_best_experiment(experiments)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "experiment_count": len(experiments),
        "experiments": experiments,
        "best": best,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase IV optimization runner for ACPs reading recommender")
    parser.add_argument("--cases", default="scripts/phase4_cases.json", help="Path to benchmark cases JSON")
    parser.add_argument("--out", default="scripts/phase4_optimization_report.json", help="Output report JSON path")
    parser.add_argument("--pretty", action="store_true", help="Pretty print output JSON")
    args = parser.parse_args()

    cases = _load_cases(Path(args.cases))
    report = asyncio.run(run_optimization(cases, DEFAULT_CONFIGS))

    output = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None)
    Path(args.out).write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
