# 嵌入模型对比实验

**实验编号**: EMB-20260311-001  
**实验日期**: 2026-03-11  
**负责人**: Coordinator + 博士  
**状态**: 🟡 待执行

---

## 📋 实验目标

验证 `qwen3-vl-embedding` 模型是否适合 ACPs-app 的书籍推荐场景，对比当前 `hash-fallback` 方案的性能提升。

---

## 🎯 实验假设

**H1**: `qwen3-vl-embedding` 的 NDCG@5 显著高于 `hash-fallback`（预期 +50% 以上）

**H2**: `qwen3-vl-embedding` 的语义相似度准确率更高（预期 85%+ vs 60%）

**H3**: 成本增加可接受（¥1/月 vs ¥0）

---

## 📊 实验设计

### 实验组别

| 组别 | 模型 | 维度 | 成本 | 类型 |
|------|------|------|------|------|
| **对照组 (A)** | hash-fallback | 12 | ¥0 | 确定性哈希 |
| **实验组 (B)** | qwen3-vl-embedding | 1024 | ¥0.0005/千 tokens | 语义嵌入 |

### 测试数据集

**来源**: `/home/dataset/bookset/processed/`

| 数据 | 数量 | 说明 |
|------|------|------|
| 书籍池 | 10,000 册 | Goodreads + Amazon 合并 |
| 测试查询 | 8 个 | 标准场景（见下文） |
| 用户历史 | 100 个 | 模拟用户阅读历史 |

### 测试场景

| ID | 场景类型 | 查询示例 | 预期结果 |
|----|----------|----------|----------|
| S1 | 明确类型 | "科幻小说 太空歌剧" | 《三体》《沙丘》等 |
| S2 | 模糊偏好 | "感人的书" | 情感类小说 |
| S3 | 作者导向 | "刘慈欣 类似作品" | 硬科幻作品 |
| S4 | 主题探索 | "人工智能 伦理" | AI 伦理相关书籍 |
| S5 | 跨类型 | "历史 悬疑" | 历史悬疑小说 |
| S6 | 冷启动 | 无历史，仅查询"推理" | 热门推理小说 |
| S7 | 长尾查询 | "赛博朋克 日本 1980s" | 特定时期作品 |
| S8 | 多样性 | "推荐一些不同的书" | 高多样性结果 |

---

## 🔧 实验步骤

### 步骤 1：配置环境

```bash
# 1. 进入项目目录
cd /root/WORK/SCHOOL/ACPs-app

# 2. 配置 API Key（项目总监提供）
cp .env.example .env
nano .env  # 填入 DASHSCOPE_API_KEY

# 3. 验证配置
python -c "from services.model_backends import generate_text_embeddings; print('OK')"
```

---

### 步骤 2：运行基线测试（对照组 A）

```bash
# 使用 hash-fallback（无需 API Key）
cd /root/WORK/SCHOOL/ACPs-app
python experiments/run_embedding_benchmark.py --model hash-fallback --output experiments/embedding_model_comparison/results_baseline.json
```

**预计时间**: 10-15 分钟

---

### 步骤 3：运行实验测试（实验组 B）

```bash
# 使用 qwen3-vl-embedding（需要 API Key）
cd /root/WORK/SCHOOL/ACPs-app
python experiments/run_embedding_benchmark.py --model qwen3-vl-embedding --output experiments/embedding_model_comparison/results_qwen3vl.json
```

**预计时间**: 15-20 分钟（含 API 调用）

---

### 步骤 4：生成对比报告

```bash
# 生成对比报告
python experiments/embedding_model_comparison/analyze_results.py \
  --baseline experiments/embedding_model_comparison/results_baseline.json \
  --experimental experiments/embedding_model_comparison/results_qwen3vl.json \
  --output experiments/embedding_model_comparison/comparison_report.md
```

---

## 📈 评估指标

### 主要指标

| 指标 | 定义 | 权重 |
|------|------|------|
| **NDCG@5** | 归一化折损累计增益（Top-5） | 40% |
| **Precision@5** | 查准率（Top-5） | 20% |
| **Recall@5** | 查全率（Top-5） | 15% |
| **Diversity** | 结果多样性（ILS） | 15% |
| **Latency** | 平均响应时间 | 10% |

### 综合评分公式

```
综合评分 = NDCG@5 × 0.40 + Precision@5 × 0.20 + Recall@5 × 0.15 + 
          (1 - ILS) × 0.15 + (1 - Latency/10s) × 0.10
```

---

## 📊 预期结果

### 性能对比（预估）

| 指标 | hash-fallback | qwen3-vl-embedding | 提升 |
|------|---------------|--------------------|------|
| NDCG@5 | 0.38 | **0.60** | +58% |
| Precision@5 | 0.42 | **0.65** | +55% |
| Recall@5 | 0.35 | **0.58** | +66% |
| Diversity | 0.75 | **0.80** | +7% |
| Latency | 0.01s | **0.15s** | -1400% |
| **综合评分** | **0.42** | **0.63** | **+50%** |

### 成本对比

| 项目 | hash-fallback | qwen3-vl-embedding |
|------|---------------|--------------------|
| API 成本 | ¥0 | ¥0.0005/千 tokens |
| 月度成本（预估） | ¥0 | **¥1.00** |
| 启动时间 | <1s | ~2s |

---

## ✅ 验收标准

### 通过标准（满足任意 2 项）

- [ ] NDCG@5 提升 ≥ 40%
- [ ] 综合评分 ≥ 0.55
- [ ] 用户满意度（人工评估）≥ 80%
- [ ] 成本增加 ≤ ¥2/月

### 不通过标准（满足任意 1 项）

- [ ] NDCG@5 提升 < 20%
- [ ] 延迟 > 2 秒（不可接受）
- [ ] API 稳定性差（失败率 > 5%）
- [ ] 成本 > ¥5/月

---

## 📝 团队分工

### @Coordinator（代码负责人）

**任务**：
- [ ] 配置 DashScope API Key
- [ ] 运行基线测试（hash-fallback）
- [ ] 运行实验测试（qwen3-vl-embedding）
- [ ] 记录实验日志

**预计时间**: 1 小时

---

### @博士（论文负责人）

**任务**：
- [ ] 设计测试查询场景（8 个）
- [ ] 人工评估推荐结果质量
- [ ] 记录语义相似度准确率
- [ ] 撰写实验分析

**预计时间**: 1.5 小时

---

### @Advisor（审查监督）

**任务**：
- [ ] 审查实验设计合理性
- [ ] 验证评估指标科学性
- [ ] 检查数据可复现性
- [ ] 提出改进建议

**预计时间**: 0.5 小时

---

### @技术主管（资源协调）

**任务**：
- [ ] 协调 API Key 获取
- [ ] 监控服务器资源
- [ ] 评估成本效益
- [ ] 最终决策建议

**预计时间**: 0.5 小时

---

## 📅 时间安排

| 阶段 | 时间 | 负责人 | 交付物 |
|------|------|--------|--------|
| **准备** | 30 分钟 | Coordinator | 环境配置完成 |
| **基线测试** | 30 分钟 | Coordinator | baseline_results.json |
| **实验测试** | 45 分钟 | Coordinator | qwen3vl_results.json |
| **人工评估** | 45 分钟 | 博士 | 评估报告 |
| **分析总结** | 30 分钟 | 全员 | comparison_report.md |
| **决策会议** | 30 分钟 | 全员 | 最终决策 |

**总预计时间**: 3.5 小时

---

## 📁 输出文件

```
experiments/embedding_model_comparison/
├── README.md                      # 本文档
├── results_baseline.json          # 基线测试结果
├── results_qwen3vl.json           # 实验组结果
├── comparison_report.md           # 对比报告
├── human_evaluation.xlsx          # 人工评估表
└── final_decision.md              # 最终决策
```

---

## 🔍 实验脚本

### run_embedding_benchmark.py

```python
#!/usr/bin/env python3
"""嵌入模型基准测试脚本"""

import json
import time
from pathlib import Path
from services.model_backends import generate_text_embeddings
from services.book_retrieval import load_books, retrieve_books_by_query
from services.evaluation_metrics import compute_recommendation_metrics

# 测试查询
TEST_QUERIES = [
    "科幻小说 太空歌剧",
    "感人的书",
    "刘慈欣 类似作品",
    "人工智能 伦理",
    "历史 悬疑",
    "推理",
    "赛博朋克 日本 1980s",
    "推荐一些不同的书"
]

def run_benchmark(model_name: str, output_path: str):
    results = []
    
    for i, query in enumerate(TEST_QUERIES, 1):
        print(f"[{i}/8] 测试查询：{query}")
        
        # 生成嵌入
        start_time = time.time()
        embeddings, meta = generate_text_embeddings([query], model_name=model_name)
        embed_time = time.time() - start_time
        
        # 检索书籍
        start_time = time.time()
        recommendations = retrieve_books_by_query(query, top_k=10)
        retrieve_time = time.time() - start_time
        
        # 记录结果
        results.append({
            "query": query,
            "embeddings": embeddings[0] if embeddings else [],
            "embedding_meta": meta,
            "recommendations": recommendations,
            "latency": {
                "embedding": embed_time,
                "retrieval": retrieve_time,
                "total": embed_time + retrieve_time
            }
        })
    
    # 保存结果
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 结果已保存到：{output_path}")
    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='嵌入模型基准测试')
    parser.add_argument('--model', type=str, required=True, 
                       choices=['hash-fallback', 'qwen3-vl-embedding'],
                       help='嵌入模型名称')
    parser.add_argument('--output', type=str, required=True,
                       help='输出文件路径')
    
    args = parser.parse_args()
    run_benchmark(args.model, args.output)
```

---

## 📊 结果分析模板

### comparison_report.md

```markdown
# 嵌入模型对比实验报告

## 实验概述
- 实验日期：2026-03-11
- 实验人员：[姓名]
- 实验版本：ACPs-app v2.0

## 性能对比

| 指标 | hash-fallback | qwen3-vl-embedding | 提升 |
|------|---------------|--------------------|------|
| NDCG@5 | X.XX | X.XX | +XX% |
| Precision@5 | X.XX | X.XX | +XX% |
| ... | ... | ... | ... |

## 成本对比

| 项目 | hash-fallback | qwen3-vl-embedding |
|------|---------------|--------------------|
| 月度成本 | ¥0 | ¥X.XX |

## 人工评估

[博士填写人工评估结果]

## 结论与建议

[全员讨论后填写]
```

---

## 🎯 决策流程

### 实验完成后

1. **查看结果** - 全员审阅对比报告
2. **讨论** - 优缺点分析
3. **投票** - 是否采用新模型
4. **决策** - 技术主管最终确认

### 决策选项

- ✅ **采用** - 更新生产环境配置
- ⚠️ **优化后采用** - 调整参数后重新测试
- ❌ **不采用** - 继续使用 hash-fallback

---

## 📞 联系方式

**实验问题**：
- GitHub Issues: https://github.com/yujinandyanhaoyang/ACPs-app/issues
- 项目负责人：Coordinator

**API 问题**：
- DashScope 文档：https://help.aliyun.com/zh/dashscope/
- 技术支持：阿里云工单

---

**实验开始时间**: [待填写]  
**实验结束时间**: [待填写]  
**最终决策**: [待填写]

---

**祝实验顺利！** 🧪
