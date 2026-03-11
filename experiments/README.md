# 实验数据采集与可视化模块

本目录包含 ACPs 推荐系统的实验数据采集和性能对比图表生成功能。

## 📦 模块说明

### `experiment_data_collector.py`
实验数据采集模块，提供：
- 实验元数据管理
- 推荐指标采集 (Precision, Recall, NDCG, Diversity, Novelty)
- 性能指标采集 (延迟、吞吐量)
- 数据导出 (JSON, CSV)
- 实验批次管理

### `performance_chart_generator.py`
性能对比图表生成模块，提供：
- 指标对比柱状图
- 综合能力雷达图
- 延迟对比图
- 综合评分图
- 多格式输出 (PNG, HTML, Markdown)

## 🚀 快速开始

### 运行实验并生成图表

```bash
cd /root/WORK/SCHOOL/ACPs-app

# 运行完整实验
python scripts/run_experiment_and_generate_charts.py \
    --experiment-name "ACPs 基准测试" \
    --output-dir ./experiments
```

### 从现有数据生成图表

```bash
python scripts/run_experiment_and_generate_charts.py \
    --from-file experiments/experiment_xxx.json
```

## 📖 详细文档

- [实验数据采集指南](../docs/experiment_data_collection_guide.md)
- [进度报告](../docs/progress_report_2026-03-11.md)

## 🧪 测试

```bash
python scripts/test_experiment_modules.py
```

## 📊 输出示例

```
experiments/
├── experiment_abc123_20260311_100000.json  # 实验数据
├── experiment_abc123_20260311_100000.csv   # CSV 格式
└── charts/
    ├── metrics_comparison.png              # 指标对比图
    ├── radar_comparison.png                # 雷达图
    ├── latency_comparison.png              # 延迟对比图
    └── overall_score_comparison.png        # 综合评分图
```

## 📝 API 示例

```python
from services.experiment_data_collector import create_collector, RecommendationMetrics
from services.performance_chart_generator import create_chart_generator, MethodComparison

# 数据采集
collector = create_collector()
batch = collector.start_experiment(experiment_name="测试")
collector.record_run(
    case_id="case_001",
    method="acps_multi_agent",
    recommendations=[...],
    ground_truth_ids=["b1", "b2"],
    recommendation_metrics=RecommendationMetrics(
        precision_at_k=0.8,
        ndcg_at_k=0.75,
    ),
)
collector.save_batch()

# 图表生成
generator = create_chart_generator()
methods = [
    MethodComparison("acps_multi_agent", 0.82, 0.75, 0.78, 0.65, 0.58, 1500.0),
    MethodComparison("traditional_hybrid", 0.78, 0.70, 0.72, 0.55, 0.50, 800.0),
]
generator.generate_all_charts(methods, "性能对比")
```

## 📅 开发日志

- **2026-03-11**: 初始版本完成
  - 实验数据采集模块
  - 性能图表生成模块
  - 集成脚本和测试
  - 完整文档

---

*最后更新：2026-03-11*
