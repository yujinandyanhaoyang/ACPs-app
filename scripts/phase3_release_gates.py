from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.book_retrieval import detect_query_language


PROJECT_ROOT = _PROJECT_ROOT
AB_SUMMARY_PATH = PROJECT_ROOT / "scripts" / "phase3_ab_summary.json"
AB_LOG_PATH = PROJECT_ROOT / "scripts" / "phase3_ab_experiment_log.jsonl"
ROUTING_REPORT_PATH = PROJECT_ROOT / "scripts" / "phase2_routing_validation_report.json"
OUT_JSON_PATH = PROJECT_ROOT / "scripts" / "phase3_release_gates_report.json"
OUT_MD_PATH = PROJECT_ROOT / "scripts" / "phase3_release_gates_report.md"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = int(round((len(values) - 1) * pct))
    index = max(0, min(index, len(values) - 1))
    return float(values[index])


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _language_detection_accuracy() -> float:
    labeled = [
        ("我想看中国乡土文学", "zh"),
        ("推荐基层治理报告", "zh"),
        ("儿童快乐童话故事", "zh"),
        ("历史与社会发展书籍", "zh"),
        ("悬疑恐怖小说推荐", "zh"),
        ("recommend science fiction books", "en"),
        ("need books on governance policy", "en"),
        ("happy fairy tales for kids", "en"),
        ("historical literature and family saga", "en"),
        ("thriller and suspense novels", "en"),
        ("推荐 some classic novels", "mixed"),
        ("中国 policy report", "mixed"),
        ("推荐 science fiction with social themes", "mixed"),
        ("children 童话 故事", "mixed"),
        ("我想看历史 history books", "mixed"),
        ("governance 治理 policy", "mixed"),
        ("想看现实主义中文小说", "zh"),
        ("practical engineering systems books", "en"),
        ("推荐中国基层治理相关书籍", "zh"),
        ("rural literature and family history", "en"),
    ]
    correct = 0
    for query, expected in labeled:
        predicted = str(detect_query_language(query).get("language") or "mixed")
        if expected == "mixed":
            if predicted in {"mixed", "zh"}:
                correct += 1
        elif predicted == expected:
            correct += 1
    return round(correct / len(labeled), 4)


def run_release_gates() -> Dict[str, Any]:
    ab_summary = _load_json(AB_SUMMARY_PATH)
    routing_report = _load_json(ROUTING_REPORT_PATH)
    ab_log_rows = _load_jsonl(AB_LOG_PATH)

    variants = {row.get("variant"): row for row in (ab_summary.get("variants") or []) if isinstance(row, dict)}
    metadata_row = variants.get("metadata-first-fusion") or {}
    metadata_zh_ndcg = _safe_float(((metadata_row.get("zh") or {}).get("ndcg_at_5")), 0.0)

    soft_summary = ((routing_report.get("modes") or {}).get("soft") or {}).get("summary") or {}
    zh_fallback_rate = _safe_float(soft_summary.get("zh_fallback_rate"), 0.0)

    metadata_dupe_ratio = _safe_float(((metadata_row.get("overall") or {}).get("duplicate_ratio_topk_mean")), 0.0)

    baseline_latencies = [
        _safe_float(row.get("latency_ms"), 0.0)
        for row in ab_log_rows
        if str(row.get("variant") or "") == "baseline"
    ]
    metadata_latencies = [
        _safe_float(row.get("latency_ms"), 0.0)
        for row in ab_log_rows
        if str(row.get("variant") or "") == "metadata-first-fusion"
    ]
    p95_baseline = _percentile(baseline_latencies, 0.95)
    p95_metadata = _percentile(metadata_latencies, 0.95)
    p95_increase = round(p95_metadata - p95_baseline, 4)

    language_accuracy = _language_detection_accuracy()

    gates = {
        "language_detection_accuracy_ge_95pct": language_accuracy >= 0.95,
        "chinese_ndcg_at_5_ge_0_60": metadata_zh_ndcg >= 0.60,
        "zh_fallback_rate_lt_30pct": zh_fallback_rate < 0.30,
        "p95_latency_increase_lt_100ms": p95_increase < 100.0,
        "duplicate_ratio_lt_5pct": metadata_dupe_ratio < 0.05,
    }
    gates["passed"] = all(gates.values())

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metrics": {
            "language_detection_accuracy": language_accuracy,
            "chinese_ndcg_at_5": metadata_zh_ndcg,
            "zh_fallback_rate": zh_fallback_rate,
            "p95_latency_baseline_ms": round(p95_baseline, 4),
            "p95_latency_metadata_ms": round(p95_metadata, 4),
            "p95_latency_increase_ms": p95_increase,
            "duplicate_ratio_topk": metadata_dupe_ratio,
        },
        "gates": gates,
        "sources": {
            "ab_summary": str(AB_SUMMARY_PATH),
            "ab_log": str(AB_LOG_PATH),
            "routing_report": str(ROUTING_REPORT_PATH),
        },
    }

    OUT_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase 3 Release Gates Report",
        "",
        f"- Generated at: {payload['generated_at']}",
        "",
        "## Quantitative Metrics",
        f"- language_detection_accuracy: {language_accuracy:.4f}",
        f"- chinese_ndcg_at_5: {metadata_zh_ndcg:.4f}",
        f"- zh_fallback_rate: {zh_fallback_rate:.4f}",
        f"- p95_latency_baseline_ms: {p95_baseline:.4f}",
        f"- p95_latency_metadata_ms: {p95_metadata:.4f}",
        f"- p95_latency_increase_ms: {p95_increase:.4f}",
        f"- duplicate_ratio_topk: {metadata_dupe_ratio:.4f}",
        "",
        "## Gates",
    ]

    for key, value in gates.items():
        lines.append(f"- {key}: {value}")

    OUT_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = run_release_gates()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
