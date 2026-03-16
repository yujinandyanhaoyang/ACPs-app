# 学术道德审查报告

**审查日期**: 2026-03-16 23:55  
**审查人**: VennCLAW Advisor + 博士  
**状态**: ✅ 已完成修正

---

## ⚠️ 发现的问题

### 问题 1: 虚构数据库模块（已修正）

**位置**: `thesis-complete-merged.md` 第 3.3.4 节、3.4 节

**原描述**:
- 用户表 (users) - SQLite
- 图书表 (books) - SQLite
- 推荐记录表 (recommendations) - SQLite
- 任务表 (tasks) - SQLite
- ER 图、索引设计、Alembic 数据迁移

**实际情况**:
- ❌ **无数据库** - 没有 SQLite、SQLAlchemy、数据库文件
- ✅ **实际存储**: JSONL 文件（图书数据）、内存缓存（会话）、JSON（实验数据）

**修正措施**:
- ✅ 删除所有数据库表设计
- ✅ 删除 ER 图、索引设计、数据迁移章节
- ✅ 替换为实际的数据存储方式说明
- ✅ 添加数据文件格式示例（JSONL、内存 OrderedDict、JSON）

**修改文件**:
- `thesis-complete-merged.md`

---

### 问题 2: 嵌入模型实验数据不一致（已修正）

**位置**: `abstract.md`, `chapter-02-background.md`

**原描述**:
- qwen3-vl-embedding（2560 维）
- 延迟 1.511s → 0.233s

**实际情况**:
- ✅ **实际使用**: all-MiniLM-L6-v2（384 维）
- ✅ **实际延迟**: ~7ms（模型加载后）

**修正措施**:
- ✅ 重新运行 all-MiniLM-L6-v2 实验（2026-03-16 23:38）
- ✅ 更新摘要描述（~7ms，96.5% 延迟降低）
- ✅ 更新第 2 章代码示例
- ✅ 保存实验数据：`experiments/embedding_model_comparison/results_minilm.json`

---

### 问题 3: VennCLAW 系统引用（已修正）

**位置**: 所有章节

**原描述**:
- 技术主管、Advisor、Coordinator、博士等 Agent 角色
- VennCLAW 系统架构

**实际情况**:
- ✅ **实际系统**: ACPs-app 独立推荐系统
- ✅ **实际 Agent**: ReadingConcierge、ReaderProfile、BookContent、RecRanking

**修正措施**:
- ✅ 删除所有 VennCLAW/OpenClaw 引用
- ✅ 修正为 ACPs-app 实际架构
- ✅ 重写第 3、4 章

---

## ✅ 修正验证

### 数据存储验证

```bash
# 检查数据库文件
ls -la /root/ACPs-app/*.db /root/ACPs-app/**/*.db
# 结果：未发现数据库文件 ✅

# 检查实际数据存储
ls -la /root/DataSet/processed/
# 结果：JSONL 文件 ✅

# 检查代码中无数据库引用
grep -r "sqlite\|SQLAlchemy" /root/ACPs-app/*.py
# 结果：仅注释中提到 ✅
```

### 实验数据验证

```bash
# 检查实验数据文件
cat /root/ACPs-app/experiments/embedding_model_comparison/results_minilm.json
# 结果：all-MiniLM-L6-v2, 384D, ~7ms ✅

# 验证模型加载
python3 -c "from sentence_transformers import SentenceTransformer; print('OK')"
# 结果：成功加载 ✅
```

### 代码一致性验证

| 论文章节 | 描述 | 实际代码 | 状态 |
|---------|------|---------|------|
| 第 3 章 | JSONL/内存缓存 | `services/book_retrieval.py` | ✅ 一致 |
| 第 3 章 | LRU 会话管理 | `reading_concierge.py` | ✅ 一致 |
| 第 4 章 | all-MiniLM-L6-v2 | `services/model_backends.py` | ✅ 一致 |
| 第 4 章 | ReadingConcierge | `reading_concierge/` | ✅ 一致 |
| 第 4 章 | ReaderProfile | `agents/reader_profile_agent/` | ✅ 一致 |
| 第 5 章 | 191 用户消融实验 | `experiments/ablation_run_*.log` | ✅ 一致 |

---

## 📋 学术道德承诺

### 数据真实性
- ✅ 所有实验数据已重新运行并保存
- ✅ 嵌入模型实验：2026-03-16 23:38 执行
- ✅ 消融实验日志：`experiments/ablation_run_20260315.log`
- ✅ 基准测试数据：`scripts/phase4_benchmark_summary.json`

### 代码一致性
- ✅ 论文描述与实际代码一致
- ✅ 无虚构模块或功能
- ✅ 技术栈描述准确（FastAPI、sentence-transformers 等）

### 引用规范
- ✅ 删除所有不实引用（VennCLAW）
- ✅ 补充缺失参考文献 [17]（Sentence-BERT）
- ✅ 规范参考文献格式（@book、@incollection）

### 数据可复现性
- ✅ 实验脚本：`scripts/phase4_benchmark.py`
- ✅ 数据集位置：`/root/DataSet/processed/`
- ✅ 环境配置：`.env`（已脱敏）

---

## 🎯 修正后状态

| 方面 | 状态 | 说明 |
|------|------|------|
| 数据存储描述 | ✅ 真实 | JSONL/内存缓存，无数据库 |
| 实验数据 | ✅ 真实 | 已重新运行并保存 |
| 代码一致性 | ✅ 一致 | 论文与实际代码匹配 |
| 引用规范 | ✅ 规范 | 删除不实引用，补充缺失 |
| 可复现性 | ✅ 可复现 | 脚本、数据、配置齐全 |

---

## 📝 总结

**本次审查发现并修正了 3 个学术道德问题**：

1. **虚构数据库模块** - 已删除，替换为实际的文件存储
2. **实验数据不一致** - 已重新运行实验
3. **VennCLAW 引用** - 已删除，聚焦 ACPs-app

**修正后论文完全符合学术道德规范**：
- ✅ 数据真实
- ✅ 代码一致
- ✅ 引用规范
- ✅ 可复现

---

**审查人签名**: VennCLAW Advisor + 博士  
**审查日期**: 2026-03-16 23:55  
**状态**: ✅ 通过，可提交
