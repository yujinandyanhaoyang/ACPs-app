# 实验数据采集与可视化指南

本文档介绍如何使用 ACPs-app 的实验数据采集模块和性能对比图表生成模块。

## 📋 目录

- [实验数据采集模块](#实验数据采集模块)
- [性能对比图表生成模块](#性能对比图表生成模块)
- [快速开始](#快速开始)
- [API 参考](#api-参考)
- [示例](#示例)

---

## 🔬 实验数据采集模块

### 概述

`services/experiment_data_collector.py` 提供了一套完整的实验数据采集系统，用于：

- 采集推荐系统的性能指标
- 记录实验运行详情
- 支持数据导出（JSON、CSV 格式）
- 保证实验可复现性

### 核心类

#### `ExperimentMetadata`
实验元数据，包含：
- `experiment_id`: 实验唯一标识
- `experiment_name`: 实验名称
- `timestamp`: 时间戳
- `dataset`: 数据集信息
- `model_version`: 模型版本
- `notes`: 备注

#### `RecommendationMetrics`
推荐指标：
- `precision_at_k`: 精确率
- `recall_at_k`: 召回率
- `ndcg_at_k`: NDCG 指标
- `diversity`: 多样性
- `novelty`: 新颖性
- `mrr`: 平均倒数排名
- `hit_rate`: 命中率

#### `PerformanceMetrics`
性能指标：
- `latency_ms`: 延迟（毫秒）
- `throughput_qps`: 吞吐量（查询/秒）
- `memory_mb`: 内存使用
- `cpu_percent`: CPU 使用率
- `api_calls`: API 调用次数
- `cache_hit_rate`: 缓存命中率

#### `ExperimentRun`
单次实验运行记录，包含完整的上下文信息。

#### `ExperimentBatch`
实验批次，包含多次运行记录和汇总统计。

#### `ExperimentDataCollector`
数据采集器主类，提供：
- `start_experiment()`: 开始新实验
- `record_run()`: 记录单次运行
- `save_batch()`: 保存实验数据
- `load_batch()`: 加载实验数据

### 使用示例

```python
from services.experiment_data_collector import (
    create_collector,
    RecommendationMetrics,
    PerformanceMetrics,
)

# 创建采集器
collector = create_collector(output_dir="./experiments")

# 开始实验
batch = collector.start_experiment(
    experiment_name="推荐系统基准测试",
    dataset="Goodreads+Amazon",
    dataset_size=1000000,
    model_version="v1.0.0",
)

# 记录运行
collector.record_run(
    case_id="case_001",
    method="acps_multi_agent",
    recommendations=[{"book_id": "b1", "score": 0.9}],
    ground_truth_ids=["b1", "b2"],
    user_id="user_123",
    query="推荐科幻小说",
    top_k=5,
    recommendation_metrics=RecommendationMetrics(
        precision_at_k=0.8,
        recall_at_k=0.6,
        ndcg_at_k=0.75,
        diversity=0.5,
        novelty=0.4,
    ),
    performance_metrics=PerformanceMetrics(
        latency_ms=1500.0,
    ),
    success=True,
)

# 保存数据
output_path = collector.save_batch()
print(f"实验数据已保存到：{output_path}")
```

### 数据格式

保存的 JSON 文件包含：
```json
{
  "batch_id": "abc123",
  "metadata": {
    "experiment_id": "exp_001",
    "experiment_name": "推荐系统基准测试",
    "timestamp": "2026-03-11T10:00:00",
    "dataset": "Goodreads+Amazon"
  },
  "summary": {
    "total_runs": 100,
    "successful_runs": 98,
    "success_rate": 0.98,
    "methods": {
      "acps_multi_agent": {
        "count": 25,
        "precision_avg": 0.82,
        "recall_avg": 0.75,
        "ndcg_avg": 0.78,
        "latency_avg": 1500.0
      }
    }
  },
  "runs": [...]
}
```

---

## 📊 性能对比图表生成模块

### 概述

`services/performance_chart_generator.py` 提供性能对比可视化功能，支持：

- 多种图表类型（柱状图、雷达图、延迟对比图等）
- 多种输出格式（PNG、HTML、Markdown）
- 自动从实验数据生成图表
- 支持 matplotlib 和 plotly 两种后端

### 核心类

#### `MethodComparison`
方法对比数据容器：
```python
@dataclass
class MethodComparison:
    method_name: str
    precision_at_k: float
    recall_at_k: float
    ndcg_at_k: float
    diversity: float
    novelty: float
    latency_ms: float
    throughput_qps: float
    success_rate: float
```

#### `PerformanceChartGenerator`
图表生成器主类，提供：
- `generate_all_charts()`: 生成所有类型图表
- `generate_metrics_bar_chart()`: 指标对比柱状图
- `generate_radar_chart()`: 综合能力雷达图
- `generate_latency_chart()`: 延迟对比图
- `generate_overall_score_chart()`: 综合评分图
- `generate_from_experiment_data()`: 从实验数据生成

### 使用示例

```python
from services.performance_chart_generator import (
    create_chart_generator,
    MethodComparison,
)

# 创建生成器
generator = create_chart_generator(output_dir="./experiments/charts")

# 准备数据
methods = [
    MethodComparison("acps_multi_agent", 0.82, 0.75, 0.78, 0.65, 0.58, 1500.0),
    MethodComparison("traditional_hybrid", 0.78, 0.70, 0.72, 0.55, 0.50, 800.0),
    MethodComparison("multi_agent_proxy", 0.80, 0.73, 0.76, 0.60, 0.55, 1200.0),
]

# 生成所有图表
generated = generator.generate_all_charts(
    methods,
    "ACPs 推荐系统性能对比"
)

# 从实验数据生成
charts = generator.generate_from_experiment_data(
    Path("experiments/experiment_xxx.json")
)
```

### 图表类型

#### 1. 指标对比柱状图 (`metrics_comparison`)
展示各方法在不同指标上的对比。

#### 2. 雷达图 (`radar_comparison`)
展示各方法的综合能力剖面。

#### 3. 延迟对比图 (`latency_comparison`)
展示各方法的平均延迟。

#### 4. 综合评分图 (`overall_score_comparison`)
展示加权综合评分。

**综合评分计算公式：**
```
Overall Score = 0.35×NDCG + 0.25×Precision + 0.20×Recall + 0.10×Diversity + 0.10×Novelty
```

---

## 🚀 快速开始

### 运行完整实验并生成图表

```bash
cd /root/WORK/SCHOOL/ACPs-app

# 运行实验并自动生成图表
python scripts/run_experiment_and_generate_charts.py \
    --experiment-name "ACPs 基准测试" \
    --output-dir ./experiments
```

### 从现有数据生成图表

```bash
# 从已有的实验数据文件生成图表
python scripts/run_experiment_and_generate_charts.py \
    --from-file experiments/experiment_abc123_20260311_100000.json
```

### 仅生成图表（跳过实验）

```bash
python scripts/run_experiment_and_generate_charts.py \
    --skip-experiment \
    --from-file experiments/latest.json
```

---

## 📖 API 参考

### ExperimentDataCollector

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `start_experiment()` | experiment_name, dataset, dataset_size, model_version, notes | ExperimentBatch | 开始新实验 |
| `record_run()` | case_id, method, recommendations, ground_truth_ids, ... | ExperimentRun | 记录单次运行 |
| `save_batch()` | filename | Path | 保存实验数据 |
| `load_batch()` | path | ExperimentBatch | 加载实验数据 |

### PerformanceChartGenerator

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `generate_all_charts()` | methods, experiment_name, formats | Dict[str, Path] | 生成所有图表 |
| `generate_metrics_bar_chart()` | methods, title, formats | Path | 指标柱状图 |
| `generate_radar_chart()` | methods, title, formats | Path | 雷达图 |
| `generate_latency_chart()` | methods, title, formats | Path | 延迟对比图 |
| `generate_overall_score_chart()` | methods, title, formats | Path | 综合评分图 |
| `generate_from_experiment_data()` | experiment_path, title | Dict[str, Path] | 从实验数据生成 |

---

## 💡 示例场景

### 场景 1: A/B 测试对比

```python
from services.experiment_data_collector import create_collector, RecommendationMetrics

collector = create_collector()
batch = collector.start_experiment(
    experiment_name="A/B 测试：新排序算法",
    dataset="merged",
)

# A 组：当前算法
for case in test_cases:
    result_a = run_method_a(case)
    collector.record_run(
        case_id=case['id'],
        method="method_a",
        recommendations=result_a,
        ground_truth_ids=case['ground_truth'],
        recommendation_metrics=calculate_metrics(result_a, case['ground_truth']),
    )

# B 组：新算法
for case in test_cases:
    result_b = run_method_b(case)
    collector.record_run(
        case_id=case['id'],
        method="method_b",
        recommendations=result_b,
        ground_truth_ids=case['ground_truth'],
        recommendation_metrics=calculate_metrics(result_b, case['ground_truth']),
    )

output_path = collector.save_batch()
```

### 场景 2: 批量性能测试

```python
from services.performance_chart_generator import create_chart_generator, MethodComparison

generator = create_chart_generator()

# 从 benchmark 结果提取数据
methods = []
for method_name, stats in benchmark_results.items():
    methods.append(MethodComparison(
        method_name=method_name,
        precision_at_k=stats['precision'],
        recall_at_k=stats['recall'],
        ndcg_at_k=stats['ndcg'],
        latency_ms=stats['latency'],
    ))

# 生成对比图表
charts = generator.generate_all_charts(methods, "性能对比")
```

### 场景 3: 消融实验

```python
# 运行消融实验
ablation_configs = [
    {"name": "full", "components": ["cf", "semantic", "kg", "diversity"]},
    {"name": "no_cf", "components": ["semantic", "kg", "diversity"]},
    {"name": "no_semantic", "components": ["cf", "kg", "diversity"]},
    {"name": "no_kg", "components": ["cf", "semantic", "diversity"]},
]

collector = create_collector()
batch = collector.start_experiment(experiment_name="消融实验")

for config in ablation_configs:
    for case in test_cases:
        result = run_with_components(case, config['components'])
        collector.record_run(
            case_id=case['id'],
            method=config['name'],
            recommendations=result,
            ground_truth_ids=case['ground_truth'],
        )

collector.save_batch()
```

---

## 📁 输出文件结构

```
experiments/
├── experiment_abc123_20260311_100000.json    # 实验数据 (JSON)
├── experiment_abc123_20260311_100000.csv     # 实验数据 (CSV)
└── charts/
    ├── metrics_comparison.png                # 指标对比图
    ├── metrics_comparison.html               # 交互式指标对比图
    ├── radar_comparison.png                  # 雷达图
    ├── radar_comparison.html                 # 交互式雷达图
    ├── latency_comparison.png                # 延迟对比图
    └── overall_score_comparison.png          # 综合评分图
```

---

## 🔧 依赖

### 必需依赖
- Python 3.8+
- 标准库 (json, csv, pathlib, dataclasses)

### 可选依赖（用于图表生成）

**Matplotlib (静态图表):**
```bash
pip install matplotlib
```

**Plotly (交互式图表):**
```bash
pip install plotly
```

如果未安装这些库，系统会自动降级生成 Markdown 文本报告。

---

## 📝 最佳实践

1. **实验命名**: 使用描述性的实验名称，包含日期和版本信息
2. **元数据完整**: 填写完整的实验元数据，便于后续追溯
3. **数据备份**: 定期备份实验数据到外部存储
4. **版本控制**: 不要将大型实验数据文件提交到 git
5. **图表格式**: 
   - 论文/报告使用 PNG 格式（高分辨率）
   - 网页展示使用 HTML 格式（交互式）
6. **可复现性**: 记录所有实验配置参数和环境信息

---

## 🐛 故障排除

### 问题：图表生成失败
**解决**: 检查是否安装了 matplotlib 或 plotly，或接受降级到 Markdown 报告

### 问题：实验数据文件过大
**解决**: 
- 减少记录的 recommendations 详情
- 使用 CSV 格式代替 JSON
- 压缩历史实验数据

### 问题：内存不足
**解决**: 
- 分批运行实验
- 减少并发运行数量
- 增加系统内存

---

## 📚 相关文档

- [PLAN.md](../PLAN.md) - 项目实施计划
- [WORKLOG_DEV.md](../WORKLOG_DEV.md) - 开发日志
- [tests/](../tests/) - 测试用例

---

*最后更新：2026-03-11*
