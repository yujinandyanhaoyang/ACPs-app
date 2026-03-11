# 实验数据说明文档 - 论文第 5 章

**实验名称**: ACPs 基准测试 - 论文初稿  
**生成时间**: 2026-03-10  
**数据集**: merged (8 个测试用例)

---

## 📊 实验概述

本实验对比了 4 种推荐方法在相同测试用例上的表现:

1. **ACPS Multi-Agent** - 基于 ACPS 协议的多智能体协作方法 (本文方法)
2. **Traditional Hybrid** - 传统混合推荐方法 (协同过滤 + 内容推荐)
3. **Multi-Agent Proxy** - 多智能体代理方法 (顺序调用)
4. **LLM Only** - 纯 LLM 推荐方法

---

## 📈 评估指标

### 推荐质量指标
- **Precision@K**: 推荐准确率 (前 K 个推荐中相关项目的比例)
- **Recall@K**: 推荐召回率 (相关项目被推荐出的比例)
- **NDCG@K**: 归一化折损累计增益 (考虑排序质量的指标)
- **Diversity**: 多样性 (推荐结果的多样性程度)
- **Novelty**: 新颖性 (推荐结果的新颖程度)

### 系统性能指标
- **Latency (ms)**: 响应延迟 (毫秒)

### 综合评分
```
Overall Score = 0.35×NDCG + 0.25×Precision + 0.20×Recall + 0.10×Diversity + 0.10×Novelty
```

---

## 📋 实验结果汇总

| 方法 | Precision | Recall | NDCG | Diversity | Novelty | Latency (ms) | **Overall Score** |
|------|-----------|--------|------|-----------|---------|--------------|-------------------|
| **ACPS Multi-Agent** | 0.7500 | 1.0000 | 0.8155 | 0.5250 | 0.5000 | 7523.20 | **0.7754** |
| Multi-Agent Proxy | 0.7000 | 1.0000 | 0.7850 | 0.5750 | 0.5250 | 7850.20 | 0.7598 |
| Traditional Hybrid | 0.5000 | 0.7750 | 0.6150 | 0.4250 | 0.3250 | 147.85 | 0.5703 |
| LLM Only | 0.3500 | 0.6250 | 0.4850 | 0.3750 | 0.4250 | 3350.00 | 0.4622 |

### 关键发现

1. **ACPS Multi-Agent 方法综合得分最高 (0.7754)**
   - NDCG@K 达到 0.8155，显著优于基线方法
   - Recall@K 达到 1.0，能够召回所有相关项目
   - 多样性 (0.525) 和新颖性 (0.500) 表现良好

2. **多智能体方法优于单一方法**
   - ACPS Multi-Agent 和 Multi-Agent Proxy 的综合得分均高于 Traditional Hybrid 和 LLM Only
   - 验证了多智能体协作在推荐系统中的有效性

3. **延迟权衡**
   - ACPS Multi-Agent 延迟 (7523ms) 高于 Traditional Hybrid (148ms)
   - 但考虑到推荐质量的显著提升，这一权衡是可接受的
   - 通过并行优化 (ReaderProfile + BookContent 并行调用) 已显著降低延迟

---

## 📁 实验数据文件

### 原始数据
- `experiment_acps_benchmark_20260310.json` - 完整实验数据 (JSON 格式)
- `experiment_acps_benchmark_20260310.csv` - 实验数据 (CSV 格式)

### 可视化图表
- `01_metrics_comparison.png/svg` - 指标对比柱状图
- `02_radar_comparison.png/svg` - 雷达图
- `03_latency_comparison.png/svg` - 延迟对比图
- `04_overall_score_comparison.png/svg` - 综合评分对比图

### 说明文档
- `experiment_summary_for_thesis.md` - 本文档
- `experiment_summary.md` - 英文摘要

---

## 🔬 实验设置

### 场景配置
实验覆盖以下场景:
- **Warm Start**: 用户有历史行为和书评
- **Explore**: 探索模式，强调多样性和新颖性
- **Cold Start**: 新用户，无历史数据

### RecRanking 权重配置
| 场景 | 协同过滤 | 语义相似度 | 知识图谱 | 多样性 |
|------|---------|-----------|---------|--------|
| Warm Start | 25% | 35% | 20% | 20% |
| Cold Start | 10% | 45% | 25% | 20% |
| Explore | 15% | 25% | 20% | 40% |

### 测试用例
共 8 个测试用例，覆盖:
- 不同场景类型 (warm/cold/explore)
- 不同书籍类型 (科幻、悬疑、文学等)
- 不同用户偏好

---

## 📝 论文第 5 章撰写建议

### 5.1 验证方法
- 描述手动分析与自动化验证相结合的方法
- 说明 4 种对比方法的选择理由
- 介绍评估指标的定义与计算方法

### 5.2 功能验证
- 引用 Agent 架构验证表 (手动分析 vs OpenCode 结果)
- 说明协议验证结果 (mTLS 证书、测试覆盖率等)

### 5.3 结果分析
- **插入图表 01_metrics_comparison.png**: 展示 4 种方法的指标对比
- **插入图表 02_radar_comparison.png**: 直观展示各方法的优势领域
- **插入图表 03_latency_comparison.png**: 讨论性能权衡
- **插入图表 04_overall_score_comparison.png**: 突出 ACPS 方法的优势

### 5.4 讨论
- ACPS 方法的优势: 多因子评分、场景感知、并行优化
- 延迟分析: 并行调用优化的效果
- 局限性: 未进行大规模性能测试、边界情况覆盖不足

---

## 📞 数据使用说明

如需进一步分析或补充实验，请联系:
- 实验数据位置：`/root/WORK/SCHOOL/ACPs-app/experiments/`
- 图表位置：`/root/WORK/SCHOOL/ACPs-app/experiments/charts/`
- 实验脚本：`/root/WORK/SCHOOL/ACPs-app/scripts/generate_thesis_charts.py`

---

*文档生成时间：2026-03-10 23:30*  
*基于 Phase 4 Benchmark 结果整理*
