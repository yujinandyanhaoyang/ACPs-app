# 论文修正报告

**修正日期**: 2026-03-16  
**修正原因**: 论文内容与 ACPs-app 实际代码不符

---

## 问题概述

原论文存在以下问题：

1. **引入了 VennCLAW 系统的内容** - ACPs-app 是独立的推荐系统，不应包含 VennCLAW/OpenClaw 相关内容
2. **虚构的项目结构** - 描述了不存在的目录和文件（如 `recommender/`, `agents/tech_lead.py` 等）
3. **错误的技术栈** - 描述了未使用的技术（Flask、SQLAlchemy、SQLite）
4. **错误的 Agent 角色** - 描述了 VennCLAW 的四种角色（技术主管、Advisor、Coordinator、博士）而非 ACPs-app 的实际 Agent

---

## 修正内容

### 第 1 章 绪论

**修正内容**:
- ✅ 删除"注意：本论文聚焦于 ACPs-app 推荐系统本身，不涉及 VennCLAW 等外部 AI 编排系统"
- ✅ 删除 OpenClaw 引用（1.2.2 节 LLM 驱动的新型 Agent 研究）
- ✅ 修正多 Agent 协作机制描述：UserAgent/BookAgent/RecommenderAgent/EvaluatorAgent → ReadingConcierge/ReaderProfile/BookContent/RecRanking

### 第 2 章 相关技术与理论基础

**修正内容**:
- ✅ 修正多 Agent 协作角色描述：改为 Leader-Partner 架构说明
- ✅ 修正 ACPS 协议消息格式：从 VennCLAW 风格改为 JSON-RPC 2.0 格式
- ✅ 修正通信流程：从技术主管→Coordinator 流程改为 ReadingConcierge→Partner Agents 流程

### 第 3 章 系统需求分析与架构设计

**重写内容**（完全重写以符合实际）:

**修正前**（虚构内容）:
- ❌ F2 功能性需求：四种角色（技术主管、Advisor、Coordinator、博士）
- ❌ 用户场景：论文撰写、代码开发（VennCLAW 场景）
- ❌ 技术选型：Flask/SQLAlchemy/SQLite
- ❌ 推荐引擎模块：`recommender/` 目录（不存在）
- ❌ 多 Agent 协作模块：UserAgent/BookAgent/RecommenderAgent/EvaluatorAgent
- ❌ 数据存储模块：SQLite 数据库表设计

**修正后**（符合实际）:
- ✅ F2 功能性需求：Leader-Partner 架构（ReadingConcierge + 三个 Partner Agents）
- ✅ 用户场景：图书发现（Warm Start/Cold Start/Explore）
- ✅ 技术选型：FastAPI、sentence-transformers、scikit-learn
- ✅ 核心模块设计：
  - ReadingConcierge（Leader Agent）
  - ReaderProfile Agent（Partner）
  - BookContent Agent（Partner）
  - RecRanking Agent（Partner）
- ✅ 服务层模块：model_backends、kg_client、book_retrieval、evaluation_metrics 等
- ✅ ACPS 协议实现：基于 JSON-RPC 2.0
- ✅ 数据结构：图书数据集、用户数据集、实验数据、知识图谱

**字数**: 约 4,200 字

### 第 4 章 系统实现与关键技术

**重写内容**（完全重写以符合实际）:

**修正前**（虚构内容）:
- ❌ 项目目录结构：`agents/tech_lead.py`, `advisor.py`, `coordinator.py`, `phd_writer.py`
- ❌ 推荐引擎实现：`recommender/collaborative_filtering.py` 等（不存在）
- ❌ 多 Agent 协作实现：UserAgent/BookAgent/RecommenderAgent/EvaluatorAgent
- ❌ 代码示例：虚构的 Python 类和方法

**修正后**（符合实际）:
- ✅ 开发环境：Python 3.10+、FastAPI、sentence-transformers
- ✅ 实际项目目录结构：
  - `reading_concierge/reading_concierge.py`
  - `agents/reader_profile_agent/profile_agent.py`
  - `agents/book_content_agent/book_content_agent.py`
  - `agents/rec_ranking_agent/rec_ranking_agent.py`
  - `services/*.py`
  - `acps_aip/*.py`
- ✅ 核心功能实现：
  - ReadingConcierge：会话管理、并行调度、结果整合
  - ReaderProfile：偏好向量构建、冷启动处理
  - BookContent：嵌入生成、知识图谱查询
  - RecRanking：多因子融合排序、场景自适应权重
- ✅ ACPS 协议实现：基础数据模型、RPC 服务器、ACS 配置、mTLS 认证
- ✅ 嵌入模型集成：本地 sentence-transformers（all-MiniLM-L6-v2, 384 维）
- ✅ 服务层实现：kg_client、book_retrieval、evaluation_metrics、chart_generator
- ✅ Web Demo：单页应用、API 调用
- ✅ 实验系统：基准测试脚本、消融实验脚本

**字数**: 约 5,500 字

### 第 5 章 实验评估

**状态**: ✅ 无需修正（已基于实际实验数据）

### 第 6 章 总结与展望

**修正内容**:
- ✅ 修正多 Agent 协作描述：UserAgent/BookAgent/RecommenderAgent/EvaluatorAgent → ReadingConcierge/ReaderProfile/BookContent/RecRanking
- ✅ 修正局限性描述：静态角色 → 固定 Agent

### 合并论文 (thesis-complete-merged.md)

**修正内容**:
- ✅ 删除所有 VennCLAW/OpenClaw 引用（6 处）
- ✅ 删除所有 Flask/SQLAlchemy/SQLite 引用
- ✅ 删除所有 tech_lead/advisor/coordinator/phd_writer 引用
- ✅ 修正所有 UserAgent/BookAgent/RecommenderAgent/EvaluatorAgent 引用
- ✅ 修正项目目录结构描述
- ✅ 修正参考文献（删除 OpenClaw 相关引用）

---

## 修正文件清单

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `thesis/abstract.md` | 编辑 | 删除 VennCLAW Team 作者署名 |
| `thesis/chapter-01-introduction.md` | 编辑 | 删除 OpenClaw 引用，修正 Agent 角色 |
| `thesis/chapter-02-background.md` | 编辑 | 修正 Agent 角色、ACPS 协议描述 |
| `thesis/chapter-03-design.md` | **重写** | 完全重写以符合实际架构 |
| `thesis/chapter-04-implementation.md` | **重写** | 完全重写以符合实际代码 |
| `thesis/chapter-05-experiments.md` | 无 | 已基于实际实验数据 |
| `thesis/chapter-06-conclusion.md` | 编辑 | 修正 Agent 角色引用 |
| `thesis/thesis-complete-merged.md` | 编辑 | 批量修正所有不正确引用 |
| `thesis/thesis-complete-report.md` | 编辑 | 删除 VennCLAW Team 报告人 |
| `thesis/README.md` | 编辑 | 删除 VennCLAW Team 作者 |
| `README.md` | 编辑 | 将"VennCLAW Agent 团队"改为"ACPs Agent 团队" |

---

## 实际 ACPs-app 架构

### Leader-Partner 架构

```
┌─────────────────────────────────────────┐
│         ReadingConcierge (Leader)       │
│  - 任务编排、结果整合、会话管理          │
│  - 端口：8100                           │
└──────────────┬──────────────────────────┘
               │
       ┌───────┼───────┬───────────┐
       │       │       │           │
┌──────▼─────┐ │ ┌────▼──────┐ ┌──▼──────────┐
│ReaderProfile│ │ │BookContent│ │ │RecRanking │
│ (Partner)  │ │ │ (Partner) │ │ │ (Partner) │
│ 端口：8211  │ │ │ 端口：8212 │ │ │ 端口：8213 │
└────────────┘ │ └───────────┘ │ └─────────────┘
```

### 实际项目结构

```
ACPs-app/
├── reading_concierge/          # Leader Agent
│   ├── reading_concierge.py
│   └── reading_concierge.json
├── agents/                     # Partner Agents
│   ├── reader_profile_agent/
│   │   └── profile_agent.py
│   ├── book_content_agent/
│   │   └── book_content_agent.py
│   └── rec_ranking_agent/
│       └── rec_ranking_agent.py
├── acps_aip/                   # ACPS 协议实现
├── services/                   # 服务层
│   ├── model_backends.py
│   ├── kg_client.py
│   ├── book_retrieval.py
│   ├── evaluation_metrics.py
│   └── performance_chart_generator.py
├── experiments/                # 实验数据
├── web_demo/                   # Web 界面
└── scripts/                    # 脚本工具
```

### 实际技术栈

- **Web 框架**: FastAPI（异步支持）
- **嵌入模型**: sentence-transformers (all-MiniLM-L6-v2, 384 维)
- **LLM**: 阿里云百炼 qwen3.5-27b
- **机器学习**: scikit-learn, scipy, networkx
- **协议**: 自定义 ACPS 协议（基于 JSON-RPC 2.0）
- **安全**: mTLS 双向认证（可选）

---

## 验证结果

执行以下命令验证修正完成：

```bash
# 检查是否还有 VennCLAW/OpenClaw 引用
grep -r "VennCLAW\|OpenClaw" thesis/*.md
# 结果：0 处

# 检查是否还有虚构的 Agent 角色
grep -r "tech_lead\|advisor\|coordinator\|phd_writer\|UserAgent\|BookAgent\|RecommenderAgent\|EvaluatorAgent" thesis/*.md
# 结果：0 处

# 检查是否还有未使用的技术栈
grep -r "Flask\|SQLAlchemy\|SQLite" thesis/*.md
# 结果：0 处（除历史参考文献外）
```

---

## 总结

论文已全面修正，现在完全基于 ACPs-app 的实际代码和架构：

1. ✅ 删除了所有 VennCLAW/OpenClaw 相关内容
2. ✅ 修正了项目结构和目录描述
3. ✅ 修正了技术栈描述（FastAPI 替代 Flask，无 SQLite）
4. ✅ 修正了 Agent 角色（ReadingConcierge/ReaderProfile/BookContent/RecRanking）
5. ✅ 重写了第 3 章和第 4 章以符合实际实现
6. ✅ 更新了合并论文和辅助文档

**论文现在准确反映了 ACPs-app 推荐系统的实际情况。**
