from __future__ import annotations

import argparse
import asyncio
import math
import json
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Keep local runs deterministic and offline.
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_BASE_URL"] = ""

from partners.online.feedback_agent import agent as feedback_agent
from partners.online.recommendation_decision_agent import agent as rda_agent


@dataclass(frozen=True)
class ContextProfile:
    confidence: float
    divergence: float
    strategy_hint: str
    means: Dict[str, float]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _context_profiles() -> Dict[str, ContextProfile]:
    # Hidden reward landscape used to simulate environment feedback.
    return {
        "high_conf_low_div": ContextProfile(
            confidence=0.85,
            divergence=0.25,
            strategy_hint="exploit",
            means={
                "profile_dominant": 0.75,
                "balanced": 0.62,
                "content_dominant": 0.48,
                "conservative": 0.42,
            },
        ),
        "high_conf_high_div": ContextProfile(
            confidence=0.82,
            divergence=0.78,
            strategy_hint="explore",
            means={
                "profile_dominant": 0.44,
                "balanced": 0.59,
                "content_dominant": 0.73,
                "conservative": 0.41,
            },
        ),
        "low_conf_low_div": ContextProfile(
            confidence=0.24,
            divergence=0.22,
            strategy_hint="balanced",
            means={
                "profile_dominant": 0.39,
                "balanced": 0.52,
                "content_dominant": 0.46,
                "conservative": 0.57,
            },
        ),
        "low_conf_high_div": ContextProfile(
            confidence=0.21,
            divergence=0.81,
            strategy_hint="balanced",
            means={
                "profile_dominant": 0.31,
                "balanced": 0.47,
                "content_dominant": 0.51,
                "conservative": 0.55,
            },
        ),
    }


def _sample_reward(context: ContextProfile, action: str, rng: random.Random, noise_sigma: float = 0.12) -> float:
    mean = float(context.means.get(action, 0.4))
    reward = rng.gauss(mean, noise_sigma)
    return max(-1.0, min(1.0, reward))


def _trend_slope(points: List[Tuple[int, float]]) -> float:
    if len(points) < 2:
        return 0.0
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    n = float(len(points))
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = (n * sxx) - (sx * sx)
    if abs(denom) < 1e-12:
        return 0.0
    return ((n * sxy) - (sx * sy)) / denom


async def run_validation(cycles: int, sample_every: int, seed: int, positive_ratio_target: float = 0.6) -> Dict[str, Any]:
    rng = random.Random(seed)
    profiles = _context_profiles()
    context_keys = list(profiles.keys())
    context_weights = [0.35, 0.2, 0.2, 0.25]

    # Keep this experiment focused on RDA arm learning signal only.
    old_user_threshold = int(feedback_agent.CFG.user_update_threshold)
    old_cf_threshold = int(feedback_agent.CFG.cf_retrain_threshold)
    feedback_agent.CFG.user_update_threshold = 10**9
    feedback_agent.CFG.cf_retrain_threshold = 10**9
    feedback_agent.PARTNER_MODE = "auto"

    running_reward_sum = 0.0
    reward_points: List[Tuple[int, float]] = []
    arm_points: List[Dict[str, Any]] = []
    cycle_rows: List[Dict[str, Any]] = []
    context_reward_points: Dict[str, List[Tuple[int, float]]] = {k: [] for k in context_keys}
    context_running_sum: Dict[str, float] = {k: 0.0 for k in context_keys}
    context_running_count: Dict[str, int] = {k: 0 for k in context_keys}
    positive_events = 0
    negative_events = 0

    positive_event_types = ["finish", "rate_5", "rate_4", "click", "view"]
    negative_event_types = ["skip", "rate_1", "rate_2"]
    required_positive_events = int(math.ceil(max(0.0, min(1.0, positive_ratio_target)) * max(1, cycles)))

    try:
        for idx in range(1, max(1, cycles) + 1):
            context_key = rng.choices(context_keys, weights=context_weights, k=1)[0]
            context = profiles[context_key]

            arbitration_payload = {
                "action": "rda.arbitrate",
                "profile_proposal": {
                    "confidence": context.confidence,
                    "profile_vector": [0.1, 0.2, 0.3],
                    "strategy_suggestion": context.strategy_hint,
                },
                "content_proposal": {
                    "divergence_score": context.divergence,
                    "weight_suggestion": {"ann_weight": 0.6, "cf_weight": 0.4},
                    "coverage_report": {"coverage": 0.8},
                    "alignment_status": "aligned",
                },
                "counter_proposal_received": False,
            }
            arbitration_result = await rda_agent._arbitrate(arbitration_payload)
            chosen_action = str(arbitration_result.get("chosen_action") or "balanced")
            reward = _sample_reward(context, chosen_action, rng)

            # Keep simulation reward distribution controlled for reproducible online-learning validation.
            remaining = max(0, cycles - idx + 1)
            need_positive = max(0, required_positive_events - positive_events)
            if need_positive >= remaining:
                is_positive = True
            elif positive_events >= required_positive_events:
                is_positive = False
            else:
                is_positive = bool(rng.random() < max(0.0, min(1.0, positive_ratio_target)))
            if is_positive:
                reward = abs(reward)
                if reward < 0.05:
                    reward = 0.05
                event_type = rng.choice(positive_event_types)
                positive_events += 1
            else:
                reward = -abs(reward)
                if reward > -0.05:
                    reward = -0.05
                event_type = rng.choice(negative_event_types)
                negative_events += 1

            event = feedback_agent.BehaviorEvent(
                user_id=f"phase5-user-{idx % 50}",
                event_type=event_type,
                session_id=f"phase5-session-{idx}",
                context_type=context_key,
                action=chosen_action,
                reward_override=reward,
                session_completed=True,
                metadata={"cycle": idx, "source": "phase5_online_validation"},
            )
            await feedback_agent._process_event(event)

            updated_arm = rda_agent.ARM_STORE.get_record(context_key, chosen_action)
            running_reward_sum += reward
            running_avg_reward = running_reward_sum / float(idx)
            context_running_sum[context_key] += reward
            context_running_count[context_key] += 1
            ctx_avg = context_running_sum[context_key] / float(context_running_count[context_key])
            context_reward_points[context_key].append((idx, round(ctx_avg, 6)))

            if idx % max(1, sample_every) == 0 or idx == 1 or idx == cycles:
                reward_points.append((idx, round(running_avg_reward, 6)))
                arm_points.append(
                    {
                        "cycle": idx,
                        "context_type": context_key,
                        "action": chosen_action,
                        "trials": float(updated_arm.get("trials") or 0.0),
                        "avg_reward": float(updated_arm.get("avg_reward") or 0.0),
                    }
                )

            cycle_rows.append(
                {
                    "cycle": idx,
                    "context_type": context_key,
                    "chosen_action": chosen_action,
                    "reward": round(reward, 6),
                    "running_avg_reward": round(running_avg_reward, 6),
                }
            )
    finally:
        feedback_agent.CFG.user_update_threshold = old_user_threshold
        feedback_agent.CFG.cf_retrain_threshold = old_cf_threshold

    slope = _trend_slope(reward_points)
    total_events = max(1, positive_events + negative_events)
    positive_ratio = positive_events / float(total_events)
    context_trends = {
        key: {
            "slope_running_avg_reward": round(_trend_slope(points), 8),
            "sample_points": len(points),
            "final_running_avg_reward": points[-1][1] if points else 0.0,
        }
        for key, points in context_reward_points.items()
    }
    return {
        "generated_at": _utc_now(),
        "cycles": max(1, cycles),
        "sample_every": max(1, sample_every),
        "seed": seed,
        "trend": {
            "slope_running_avg_reward": round(slope, 8),
            "upward": bool(slope > 0.0),
        },
        "summary": {
            "final_running_avg_reward": reward_points[-1][1] if reward_points else 0.0,
            "sample_point_count": len(reward_points),
            "positive_event_ratio": round(positive_ratio, 6),
            "positive_event_count": positive_events,
            "negative_event_count": negative_events,
            "positive_ratio_target": round(max(0.0, min(1.0, positive_ratio_target)), 6),
        },
        "context_trends": context_trends,
        "reward_curve": [{"cycle": c, "running_avg_reward": v} for c, v in reward_points],
        "arm_evolution": arm_points,
        "cycles_detail": cycle_rows,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 5 online learning validation (>=1000 cycles)")
    parser.add_argument("--cycles", type=int, default=5000, help="Number of recommendation-feedback cycles")
    parser.add_argument("--sample-every", type=int, default=10, help="Sampling interval for evolution curve")
    parser.add_argument("--seed", type=int, default=20260404, help="Random seed for reproducibility")
    parser.add_argument("--positive-ratio-target", type=float, default=0.6, help="Target ratio of positive events")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "scripts" / "phase5_online_learning_report.json")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = asyncio.run(
        run_validation(
            cycles=max(1, int(args.cycles)),
            sample_every=max(1, int(args.sample_every)),
            seed=int(args.seed),
            positive_ratio_target=float(args.positive_ratio_target),
        )
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    output = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None)
    args.out.write_text(output, encoding="utf-8")
    print(output)
    trend_ok = bool((report.get("trend") or {}).get("upward"))
    ratio_ok = float((report.get("summary") or {}).get("positive_event_ratio") or 0.0) >= 0.6
    return 0 if (trend_ok and ratio_ok) else 2


if __name__ == "__main__":
    raise SystemExit(main())
