from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _write_svg(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _bar_svg(title: str, labels: Sequence[str], values: Sequence[float], width: int = 1200, height: int = 700) -> str:
    left = 120
    top = 90
    bottom = 150
    right = 60
    plot_w = width - left - right
    plot_h = height - top - bottom
    n = max(1, len(labels))
    max_v = max(values) if values else 1.0
    max_v = max(max_v, 1e-8)
    bar_w = max(16, int(plot_w / (n * 1.6)))
    gap = (plot_w - n * bar_w) / max(1, n - 1) if n > 1 else 0

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{width/2:.1f}" y="44" text-anchor="middle" font-size="28" font-family="Arial">{title}</text>',
        f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#222"/>',
    ]

    for i, (label, value) in enumerate(zip(labels, values)):
        x = left + i * (bar_w + gap)
        h = (value / max_v) * plot_h
        y = top + plot_h - h
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{h:.2f}" fill="#2563eb"/>')
        parts.append(f'<text x="{x + bar_w/2:.2f}" y="{y - 8:.2f}" text-anchor="middle" font-size="12" font-family="Arial">{value:.4f}</text>')
        parts.append(
            f'<text x="{x + bar_w/2:.2f}" y="{top + plot_h + 28:.2f}" text-anchor="middle" font-size="13" '
            f'font-family="Arial" transform="rotate(25 {x + bar_w/2:.2f},{top + plot_h + 28:.2f})">{label}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _grouped_bar_svg(
    title: str,
    labels: Sequence[str],
    series: Sequence[Tuple[str, Sequence[float], str]],
    width: int = 1400,
    height: int = 760,
) -> str:
    left = 120
    top = 90
    bottom = 170
    right = 80
    plot_w = width - left - right
    plot_h = height - top - bottom
    n = max(1, len(labels))
    m = max(1, len(series))
    max_v = 1e-8
    for _, vals, _ in series:
        if vals:
            max_v = max(max_v, max(vals))
    group_w = plot_w / n
    bar_w = max(10, group_w / (m + 1.4))

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{width/2:.1f}" y="44" text-anchor="middle" font-size="28" font-family="Arial">{title}</text>',
        f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#111"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#111"/>',
    ]
    for t in range(6):
        y = top + plot_h - (plot_h * t / 5.0)
        v = max_v * t / 5.0
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left+plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left-12}" y="{y+4:.2f}" text-anchor="end" font-size="12" font-family="Arial">{v:.2f}</text>')

    for i, label in enumerate(labels):
        gx = left + i * group_w
        for j, (_, vals, color) in enumerate(series):
            val = _safe_float(vals[i] if i < len(vals) else 0.0, 0.0)
            h = (val / max_v) * plot_h
            x = gx + (j + 0.3) * bar_w
            y = top + plot_h - h
            parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{h:.2f}" fill="{color}"/>')
        cx = gx + (m * bar_w) / 2.0
        parts.append(
            f'<text x="{cx:.2f}" y="{top+plot_h+34:.2f}" text-anchor="middle" font-size="13" '
            f'font-family="Arial" transform="rotate(25 {cx:.2f},{top+plot_h+34:.2f})">{label}</text>'
        )

    lx = left + plot_w - 300
    ly = top + 20
    for name, _, color in series:
        parts.append(f'<rect x="{lx}" y="{ly-12}" width="18" height="10" fill="{color}"/>')
        parts.append(f'<text x="{lx+26}" y="{ly-2}" font-size="13" font-family="Arial">{name}</text>')
        ly += 22

    parts.append("</svg>")
    return "\n".join(parts)


def _line_svg(title: str, points: Sequence[Tuple[int, float]], width: int = 1200, height: int = 700) -> str:
    left = 120
    top = 90
    bottom = 140
    right = 60
    plot_w = width - left - right
    plot_h = height - top - bottom
    if not points:
        points = [(0, 0.0), (1, 0.0)]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if max_x == min_x:
        max_x += 1
    if max_y == min_y:
        max_y += 1e-6

    def map_x(x: float) -> float:
        return left + ((x - min_x) / (max_x - min_x)) * plot_w

    def map_y(y: float) -> float:
        return top + plot_h - ((y - min_y) / (max_y - min_y)) * plot_h

    path_parts: List[str] = []
    for i, (x, y) in enumerate(points):
        px = map_x(x)
        py = map_y(y)
        if i == 0:
            path_parts.append(f"M{px:.2f},{py:.2f}")
        else:
            path_parts.append(f"L{px:.2f},{py:.2f}")
    path_d = " ".join(path_parts)

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{width/2:.1f}" y="44" text-anchor="middle" font-size="28" font-family="Arial">{title}</text>',
        f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#222"/>',
        f'<path d="{path_d}" fill="none" stroke="#ef4444" stroke-width="2"/>',
    ]
    for x, y in points[:: max(1, len(points) // 30)]:
        cx, cy = map_x(x), map_y(y)
        parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="2.5" fill="#ef4444"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def _multi_line_svg(
    title: str,
    series: Sequence[Tuple[str, Sequence[Tuple[int, float]], str]],
    width: int = 1400,
    height: int = 760,
) -> str:
    left = 120
    top = 90
    bottom = 140
    right = 80
    plot_w = width - left - right
    plot_h = height - top - bottom
    all_points = [p for _, pts, _ in series for p in pts]
    if not all_points:
        all_points = [(0, 0.0), (1, 0.0)]
    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if max_x == min_x:
        max_x += 1
    if max_y == min_y:
        max_y += 1e-6

    def map_x(x: float) -> float:
        return left + ((x - min_x) / (max_x - min_x)) * plot_w

    def map_y(y: float) -> float:
        return top + plot_h - ((y - min_y) / (max_y - min_y)) * plot_h

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{width/2:.1f}" y="44" text-anchor="middle" font-size="28" font-family="Arial">{title}</text>',
        f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#111"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#111"/>',
    ]

    for t in range(6):
        y = top + plot_h - (plot_h * t / 5.0)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left+plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')

    lx = left + plot_w - 340
    ly = top + 24
    for name, pts, color in series:
        if not pts:
            continue
        path = []
        for i, (x, y) in enumerate(pts):
            px = map_x(x)
            py = map_y(y)
            path.append(("M" if i == 0 else "L") + f"{px:.2f},{py:.2f}")
        parts.append(f'<path d="{" ".join(path)}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        parts.append(f'<rect x="{lx}" y="{ly-11}" width="18" height="10" fill="{color}"/>')
        parts.append(f'<text x="{lx+26}" y="{ly-2}" font-size="13" font-family="Arial">{name}</text>')
        ly += 22

    parts.append("</svg>")
    return "\n".join(parts)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pick_metric(summary: Dict[str, Any], candidates: Sequence[str]) -> float:
    for key in candidates:
        if key in summary:
            return _safe_float(summary.get(key), 0.0)
    return 0.0


def generate_charts(
    benchmark_report: Path,
    ablation_report: Path,
    online_report: Path,
    out_dir: Path,
) -> Dict[str, str]:
    bench = _load_json(benchmark_report)
    ablation = _load_json(ablation_report)
    online = _load_json(online_report)

    methods = bench.get("methods") or []
    labels: List[str] = []
    ndcgs: List[float] = []
    for row in methods:
        if not isinstance(row, dict):
            continue
        method = str(row.get("method") or "")
        summary = row.get("summary") or {}
        labels.append(method)
        ndcgs.append(_pick_metric(summary, ["ndcg_at_k", "ndcg_at_10", "ndcg_at_5"]))
    chart1 = out_dir / "phase5_baseline_ndcg.svg"
    _write_svg(chart1, _bar_svg("Baseline Comparison - NDCG@10", labels, ndcgs))

    # Thesis-ready grouped primary metric chart.
    precisions: List[float] = []
    recalls: List[float] = []
    for row in methods:
        summary = row.get("summary") if isinstance(row, dict) else {}
        precisions.append(_pick_metric(summary or {}, ["precision_at_k", "precision_at_10", "precision_at_5"]))
        recalls.append(_pick_metric(summary or {}, ["recall_at_k", "recall_at_10", "recall_at_5"]))
    chart1b = out_dir / "phase5_baseline_primary_metrics.svg"
    _write_svg(
        chart1b,
        _grouped_bar_svg(
            "Baseline Comparison - Primary Metrics",
            labels,
            [
                ("Precision@10", precisions, "#2563eb"),
                ("Recall@10", recalls, "#16a34a"),
                ("NDCG@10", ndcgs, "#dc2626"),
            ],
        ),
    )

    rows = ablation.get("rows") or []
    ab_labels: List[str] = []
    ab_vals: List[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("scenario") or "")
        if not label or label == "full":
            continue
        delta_keys = [k for k in row.keys() if k.startswith("delta_ndcg_at_") and k.endswith("_vs_full")]
        delta = _safe_float(row.get(delta_keys[0]) if delta_keys else 0.0, 0.0)
        ab_labels.append(label)
        ab_vals.append(delta)
    chart2 = out_dir / "phase5_ablation_delta_ndcg.svg"
    _write_svg(chart2, _bar_svg("Ablation - Delta NDCG vs Full", ab_labels, ab_vals))

    ab_prec_vals: List[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("scenario") or "")
        if not label or label == "full":
            continue
        keys = [k for k in row.keys() if k.startswith("delta_precision_at_") and k.endswith("_vs_full")]
        ab_prec_vals.append(_safe_float(row.get(keys[0]) if keys else 0.0, 0.0))
    chart2b = out_dir / "phase5_ablation_delta_precision.svg"
    _write_svg(chart2b, _bar_svg("Ablation - Delta Precision@10 vs Full", ab_labels, ab_prec_vals))

    curve = online.get("reward_curve") or []
    points = [
        (int(item.get("cycle") or 0), _safe_float(item.get("running_avg_reward"), 0.0))
        for item in curve
        if isinstance(item, dict)
    ]
    chart3 = out_dir / "phase5_online_learning_curve.svg"
    _write_svg(chart3, _line_svg("Online Learning - Running Avg Reward", points))

    ctx = online.get("context_trends") or {}
    ctx_series: List[Tuple[str, Sequence[Tuple[int, float]], str]] = [("global", points, "#dc2626")]
    palette = ["#2563eb", "#16a34a", "#7c3aed", "#ea580c"]
    for i, (name, payload) in enumerate(ctx.items()):
        if not isinstance(payload, dict):
            continue
        slope = _safe_float(payload.get("slope_running_avg_reward"), 0.0)
        final_v = _safe_float(payload.get("final_running_avg_reward"), 0.0)
        ctx_points = [(0, max(0.0, final_v - slope * 1000.0)), (1000, final_v)]
        ctx_series.append((f"{name} (slope={slope:.5f})", ctx_points, palette[i % len(palette)]))
    chart3b = out_dir / "phase5_online_learning_context_trends.svg"
    _write_svg(chart3b, _multi_line_svg("Online Learning - Context Trend Slopes", ctx_series))

    return {
        "baseline_chart": str(chart1),
        "baseline_primary_chart": str(chart1b),
        "ablation_chart": str(chart2),
        "ablation_precision_chart": str(chart2b),
        "online_chart": str(chart3),
        "online_context_chart": str(chart3b),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate thesis-ready SVG charts for phase 5 reports")
    parser.add_argument("--benchmark-report", type=Path, default=Path("scripts/phase4_benchmark_report.json"))
    parser.add_argument("--ablation-report", type=Path, default=Path("scripts/ablation_report.json"))
    parser.add_argument("--online-report", type=Path, default=Path("scripts/phase5_online_learning_report.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("scripts/charts"))
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    outputs = generate_charts(
        benchmark_report=args.benchmark_report,
        ablation_report=args.ablation_report,
        online_report=args.online_report,
        out_dir=args.out_dir,
    )
    payload = {"generated": outputs}
    text = json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
