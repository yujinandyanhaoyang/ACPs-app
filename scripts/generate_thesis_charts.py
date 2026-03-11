#!/usr/bin/env python3
"""
Generate charts for thesis Chapter 5 - ACPs Benchmark Results
"""

import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

# Set font to support Chinese
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

OUTPUT_DIR = Path(__file__).parent.parent / "experiments" / "charts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Method comparison data (from phase4_benchmark_report.json)
methods = {
    "ACPS Multi-Agent": {
        "precision": 0.75,
        "recall": 1.0,
        "ndcg": 0.8155,
        "diversity": 0.525,
        "novelty": 0.5,
        "latency_ms": 7523.2,
    },
    "Traditional Hybrid": {
        "precision": 0.5,
        "recall": 0.775,
        "ndcg": 0.615,
        "diversity": 0.425,
        "novelty": 0.325,
        "latency_ms": 147.85,
    },
    "Multi-Agent Proxy": {
        "precision": 0.7,
        "recall": 1.0,
        "ndcg": 0.785,
        "diversity": 0.575,
        "novelty": 0.525,
        "latency_ms": 7850.2,
    },
    "LLM Only": {
        "precision": 0.35,
        "recall": 0.625,
        "ndcg": 0.485,
        "diversity": 0.375,
        "novelty": 0.425,
        "latency_ms": 3350.0,
    },
}

method_names = list(methods.keys())
colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']

# Calculate overall scores
weights = {'ndcg': 0.35, 'precision': 0.25, 'recall': 0.20, 'diversity': 0.10, 'novelty': 0.10}
overall_scores = []
for name in method_names:
    m = methods[name]
    score = (
        m['ndcg'] * weights['ndcg'] +
        m['precision'] * weights['precision'] +
        m['recall'] * weights['recall'] +
        m['diversity'] * weights['diversity'] +
        m['novelty'] * weights['novelty']
    )
    overall_scores.append(score)

# Chart 1: Metrics Bar Chart
fig, ax = plt.subplots(figsize=(14, 8))
x = range(len(method_names))
width = 0.15

metrics = ['precision', 'recall', 'ndcg', 'diversity', 'novelty']
metric_labels = ['Precision@K', 'Recall@K', 'NDCG@K', 'Diversity', 'Novelty']

for i, metric in enumerate(metrics):
    values = [methods[name][metric] for name in method_names]
    ax.bar([j + i*width for j in x], values, width, label=metric_labels[i], color=colors[i % len(colors)])

ax.set_xlabel('Method', fontsize=12)
ax.set_ylabel('Score', fontsize=12)
ax.set_title('ACPs Recommendation System - Metrics Comparison', fontsize=14, fontweight='bold')
ax.set_xticks([j + 2*width for j in x])
ax.set_xticklabels(method_names, rotation=15)
ax.set_ylim(0, 1.1)
ax.legend(loc='upper right')
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / '01_metrics_comparison.png', dpi=150, bbox_inches='tight')
plt.savefig(OUTPUT_DIR / '01_metrics_comparison.svg', format='svg', bbox_inches='tight')
plt.close()
print(f"✓ Generated: 01_metrics_comparison.png/svg")

# Chart 2: Radar Chart
fig = plt.figure(figsize=(10, 10))
ax = fig.add_subplot(111, polar=True)

angles = [n / float(len(metrics)) * 2 * 3.14159 for n in range(len(metrics))]
angles += angles[:1]

for idx, name in enumerate(method_names):
    m = methods[name]
    values = [m[metric] for metric in metrics]
    values += values[:1]
    ax.plot(angles, values, 'o-', linewidth=2, label=name, color=colors[idx])
    ax.fill(angles, values, alpha=0.15, color=colors[idx])

ax.set_theta_offset(3.14159 / 2)
ax.set_theta_direction(-1)
ax.set_thetagrids([a * 180 / 3.14159 for a in angles[:-1]], labels=metric_labels)
ax.set_title('ACPs Recommendation System - Radar Comparison', fontsize=14, fontweight='bold', pad=20)
ax.set_ylim(0, 1.0)
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
ax.grid(True)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / '02_radar_comparison.png', dpi=150, bbox_inches='tight')
plt.savefig(OUTPUT_DIR / '02_radar_comparison.svg', format='svg', bbox_inches='tight')
plt.close()
print(f"✓ Generated: 02_radar_comparison.png/svg")

# Chart 3: Latency Comparison
fig, ax = plt.subplots(figsize=(12, 7))
latencies = [methods[name]['latency_ms'] for name in method_names]
bars = ax.bar(method_names, latencies, color=colors)

ax.set_xlabel('Method', fontsize=12)
ax.set_ylabel('Latency (ms)', fontsize=12)
ax.set_title('ACPs Recommendation System - Latency Comparison', fontsize=14, fontweight='bold')
ax.grid(axis='y', alpha=0.3)

# Add value labels
for bar, lat in zip(bars, latencies):
    height = bar.get_height()
    ax.annotate(f'{lat:.0f}ms',
               xy=(bar.get_x() + bar.get_width() / 2, height),
               xytext=(0, 3),
               textcoords="offset points",
               ha='center', va='bottom', fontsize=11)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / '03_latency_comparison.png', dpi=150, bbox_inches='tight')
plt.savefig(OUTPUT_DIR / '03_latency_comparison.svg', format='svg', bbox_inches='tight')
plt.close()
print(f"✓ Generated: 03_latency_comparison.png/svg")

# Chart 4: Overall Score Comparison
fig, ax = plt.subplots(figsize=(12, 7))
bars = ax.bar(method_names, overall_scores, color=colors)

ax.set_xlabel('Method', fontsize=12)
ax.set_ylabel('Overall Score', fontsize=12)
ax.set_title('ACPs Recommendation System - Overall Score Comparison', fontsize=14, fontweight='bold')
ax.set_ylim(0, 1.0)
ax.grid(axis='y', alpha=0.3)

# Add value labels
for bar, score in zip(bars, overall_scores):
    height = bar.get_height()
    ax.annotate(f'{score:.4f}',
               xy=(bar.get_x() + bar.get_width() / 2, height),
               xytext=(0, 3),
               textcoords="offset points",
               ha='center', va='bottom', fontsize=11, fontweight='bold')

plt.tight_layout()
plt.savefig(OUTPUT_DIR / '04_overall_score_comparison.png', dpi=150, bbox_inches='tight')
plt.savefig(OUTPUT_DIR / '04_overall_score_comparison.svg', format='svg', bbox_inches='tight')
plt.close()
print(f"✓ Generated: 04_overall_score_comparison.png/svg")

# Generate summary report
report_path = OUTPUT_DIR / 'experiment_summary.md'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write("# ACPs Benchmark Experiment Summary\n\n")
    f.write("## Experiment: ACPs 基准测试 - 论文初稿\n\n")
    f.write("## Method Comparison\n\n")
    f.write("| Method | Precision | Recall | NDCG | Diversity | Novelty | Latency (ms) | Overall Score |\n")
    f.write("|--------|-----------|--------|------|-----------|---------|--------------|---------------|\n")
    for i, name in enumerate(method_names):
        m = methods[name]
        f.write(f"| {name} | {m['precision']:.4f} | {m['recall']:.4f} | {m['ndcg']:.4f} | {m['diversity']:.4f} | {m['novelty']:.4f} | {m['latency_ms']:.2f} | {overall_scores[i]:.4f} |\n")
    f.write("\n## Overall Score Formula\n\n")
    f.write("Overall Score = 0.35×NDCG + 0.25×Precision + 0.20×Recall + 0.10×Diversity + 0.10×Novelty\n\n")
    f.write("## Generated Charts\n\n")
    f.write("- `01_metrics_comparison.png/svg` - Metrics bar chart comparison\n")
    f.write("- `02_radar_comparison.png/svg` - Radar chart comparison\n")
    f.write("- `03_latency_comparison.png/svg` - Latency comparison\n")
    f.write("- `04_overall_score_comparison.png/svg` - Overall score comparison\n")

print(f"✓ Generated: experiment_summary.md")
print("\n✅ All charts generated successfully!")
