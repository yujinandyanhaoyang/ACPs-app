"""生成学术论文所需的消融实验对比图表。

产出：
  artifacts/experiments/figures/
    ├── ablation_bar_chart.png     # 各变体四指标分组柱状图
    ├── ablation_radar_chart.png   # 雷达图（综合能力对比）
    └── ablation_table.csv         # LaTeX 可用的指标表格

依赖：matplotlib, pandas, numpy
    pip install matplotlib pandas numpy
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


FIGURES_DIR = Path(__file__).parents[2] / "artifacts" / "experiments" / "figures"
METRICS_DIR = Path(__file__).parents[2] / "artifacts" / "experiments" / "metrics"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)


# ── 颜色主题（学术风格）────────────────────────────────────────────────────────
PALETTE = [
    "#2E86AB",  # S1 Full System — 蓝
    "#A23B72",  # S2 w/o BCA    — 紫红
    "#F18F01",  # S3 w/o RDA    — 橙
    "#C73E1D",  # S4 w/o CF     — 红
    "#3B1F2B",  # S5 w/o MMR    — 深紫
    "#44BBA4",  # S6 w/o Explain — 青绿
]

METRIC_LABELS = {
    "NDCG@5": "NDCG@5",
    "Precision@5": "Precision@5",
    "ILD": "ILD",
    "Coverage": "Coverage",
}


def load_metrics(metrics_dir: Path) -> Optional[List[Dict]]:
    candidates = sorted(metrics_dir.glob("*_metrics.csv"), reverse=True)
    if not candidates:
        return None
    with open(candidates[0], encoding="utf-8") as f:
        return list(csv.DictReader(f))


def plot_bar_chart(rows: List[Dict], metrics: List[str], output_path: Path) -> None:
    """分组柱状图：X 轴为指标，每组内各变体一根柱。"""
    variant_ids = [r["variant_id"] for r in rows]
    variant_names = [r["variant_name"] for r in rows]
    n_variants = len(rows)
    n_metrics = len(metrics)

    x = np.arange(n_metrics)
    total_width = 0.75
    bar_w = total_width / n_variants

    fig, ax = plt.subplots(figsize=(10, 5.5))

    for i, row in enumerate(rows):
        vals = [float(row.get(m, 0) or 0) for m in metrics]
        offsets = x - total_width / 2 + bar_w * i + bar_w / 2
        color = PALETTE[i % len(PALETTE)]
        bars = ax.bar(offsets, vals, width=bar_w * 0.9, color=color,
                      label=f"{row['variant_id']}: {row['variant_name']}",
                      alpha=0.88, edgecolor="white", linewidth=0.5)
        for bar, val in zip(bars, vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                        f"{val:.3f}", ha="center", va="bottom", fontsize=6.5, color="#333")

    ax.set_xticks(x)
    ax.set_xticklabels([METRIC_LABELS.get(m, m) for m in metrics], fontsize=11)
    ax.set_ylabel("Score", fontsize=11)
    ax.set_title("ACPs Recommendation System — Ablation Study Results", fontsize=13, fontweight="bold")
    ax.set_ylim(0, 1.15)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.85)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"Bar chart saved → {output_path}")


def plot_radar_chart(rows: List[Dict], metrics: List[str], output_path: Path) -> None:
    """雷达图（蜘蛛网图）：展示各变体综合能力分布。"""
    n = len(metrics)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles_closed = angles + [angles[0]]
    labels = [METRIC_LABELS.get(m, m) for m in metrics]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))

    for i, row in enumerate(rows):
        vals = [float(row.get(m, 0) or 0) for m in metrics]
        vals_closed = vals + [vals[0]]
        color = PALETTE[i % len(PALETTE)]
        ax.plot(angles_closed, vals_closed, "o-", linewidth=1.8,
                color=color, label=f"{row['variant_id']}: {row['variant_name']}")
        ax.fill(angles_closed, vals_closed, alpha=0.08, color=color)

    ax.set_thetagrids(np.degrees(angles), labels, fontsize=11)
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=8, color="gray")
    ax.set_title("ACPs Ablation Study — Radar Chart", fontsize=13,
                 fontweight="bold", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"Radar chart saved → {output_path}")


def generate_latex_table(rows: List[Dict], metrics: List[str], output_path: Path) -> None:
    """生成 LaTeX booktabs 格式的对比表格。"""
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Ablation Study Results on ACPs Recommendation System}",
        r"\label{tab:ablation}",
        r"\begin{tabular}{llcccc}",
        r"\toprule",
        r"\textbf{ID} & \textbf{Variant} & \textbf{NDCG@5} & \textbf{P@5} & \textbf{ILD} & \textbf{Cov.} \\\\",
        r"\midrule",
    ]
    for row in rows:
        vid = row["variant_id"]
        name = row["variant_name"].replace("w/o", r"\textit{w/o}")
        vals = [row.get(m, "0") for m in metrics]
        bold_prefix = r"\textbf{" if vid == "S1" else ""
        bold_suffix = "}" if vid == "S1" else ""
        val_str = " & ".join(f"{bold_prefix}{v}{bold_suffix}" for v in vals)
        lines.append(f"{vid} & {name} & {val_str} \\\\")
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"LaTeX table saved → {output_path}")


def main() -> None:
    rows = load_metrics(METRICS_DIR)
    if rows is None:
        # 使用 mock 数据演示图表格式（正式实验前用于验证可视化代码）
        print("No metrics found. Generating demo charts with placeholder data...")
        rows = [
            {"variant_id": "S1", "variant_name": "Full System",
             "NDCG@5": "0.7823", "Precision@5": "0.6400", "ILD": "0.5910", "Coverage": "0.000420"},
            {"variant_id": "S2", "variant_name": "w/o BCA Alignment",
             "NDCG@5": "0.7012", "Precision@5": "0.5600", "ILD": "0.5780", "Coverage": "0.000380"},
            {"variant_id": "S3", "variant_name": "w/o RDA Arbitration",
             "NDCG@5": "0.6934", "Precision@5": "0.5400", "ILD": "0.5650", "Coverage": "0.000350"},
            {"variant_id": "S4", "variant_name": "w/o CF Path",
             "NDCG@5": "0.6521", "Precision@5": "0.5200", "ILD": "0.5230", "Coverage": "0.000310"},
            {"variant_id": "S5", "variant_name": "w/o MMR Rerank",
             "NDCG@5": "0.7234", "Precision@5": "0.6000", "ILD": "0.3890", "Coverage": "0.000290"},
            {"variant_id": "S6", "variant_name": "w/o Explain Constraint",
             "NDCG@5": "0.7456", "Precision@5": "0.6200", "ILD": "0.5700", "Coverage": "0.000400"},
        ]

    metrics = ["NDCG@5", "Precision@5", "ILD", "Coverage"]
    # Coverage 数值极小，归一化到 0~1 便于可视化
    for row in rows:
        cov = float(row.get("Coverage", 0) or 0)
        row["Coverage"] = str(min(1.0, cov * 2000))  # scale for display

    plot_bar_chart(rows, metrics, FIGURES_DIR / "ablation_bar_chart.png")
    plot_radar_chart(rows, metrics, FIGURES_DIR / "ablation_radar_chart.png")
    generate_latex_table(
        rows, metrics,
        FIGURES_DIR / "ablation_table.tex"
    )
    print("\nAll figures generated in:", FIGURES_DIR)


if __name__ == "__main__":
    main()
