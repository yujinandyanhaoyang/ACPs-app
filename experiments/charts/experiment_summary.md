# ACPs Benchmark Experiment Summary

## Experiment: ACPs 基准测试 - 论文初稿

## Method Comparison

| Method | Precision | Recall | NDCG | Diversity | Novelty | Latency (ms) | Overall Score |
|--------|-----------|--------|------|-----------|---------|--------------|---------------|
| ACPS Multi-Agent | 0.7500 | 1.0000 | 0.8155 | 0.5250 | 0.5000 | 7523.20 | 0.7754 |
| Traditional Hybrid | 0.5000 | 0.7750 | 0.6150 | 0.4250 | 0.3250 | 147.85 | 0.5703 |
| Multi-Agent Proxy | 0.7000 | 1.0000 | 0.7850 | 0.5750 | 0.5250 | 7850.20 | 0.7598 |
| LLM Only | 0.3500 | 0.6250 | 0.4850 | 0.3750 | 0.4250 | 3350.00 | 0.4622 |

## Overall Score Formula

Overall Score = 0.35×NDCG + 0.25×Precision + 0.20×Recall + 0.10×Diversity + 0.10×Novelty

## Generated Charts

- `01_metrics_comparison.png/svg` - Metrics bar chart comparison
- `02_radar_comparison.png/svg` - Radar chart comparison
- `03_latency_comparison.png/svg` - Latency comparison
- `04_overall_score_comparison.png/svg` - Overall score comparison
