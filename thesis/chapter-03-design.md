# 第 3 章 系统需求分析与架构设计

## 3.1 需求分析

### 3.1.1 功能性需求

本系统是一个基于 ACPS 协议的多 Agent 协作图书推荐系统，主要功能需求包括：

**F1: 图书推荐功能**
- F1.1: 支持基于用户历史行为的偏好分析
- F1.2: 支持基于图书内容的语义理解
- F1.3: 支持多因子融合排序（协同过滤 + 语义相似度 + 知识图谱 + 多样性）
- F1.4: 支持场景感知推荐（Warm Start / Cold Start / Explore）

**F2: 多 Agent 协作功能**
- F2.1: 支持 Leader-Partner 架构（ReadingConcierge 为 Leader，三个 Partner Agents 执行专业任务）
- F2.2: 支持 Agent 间基于 ACPS 协议的通信
- F2.3: 支持并行任务调度（ReaderProfile 和 BookContent 可并行执行）
- F2.4: 支持任务状态追踪和结果整合

**F3: 嵌入模型集成功能**
- F3.1: 支持阿里云百炼 DashScope 嵌入 API
- F3.2: 支持本地 sentence-transformers 模型（all-MiniLM-L6-v2）
- F3.3: 支持嵌入向量缓存和复用

**F4: 数据管理功能**
- F4.1: 支持图书数据集加载（Amazon Books / Goodreads / Amazon Kindle）
- F4.2: 支持知识图谱查询（作者 - 书籍、出版社 - 书籍等关系）
- F4.3: 支持实验数据采集和导出
- F4.4: 支持性能指标可视化和图表生成

### 3.1.2 非功能性需求

**性能需求**
- NFR1: 推荐响应时间 < 10s（P95，含多 Agent 协作）
- NFR2: 嵌入模型调用延迟 < 500ms（P95，本地模型）
- NFR3: 支持并发用户数 ≥ 50
- NFR4: 系统可用性 ≥ 99%

**安全需求**
- NFR5: 支持 API Key 认证（阿里云百炼）
- NFR6: 支持 mTLS 双向认证（可选，Agent 间通信）
- NFR7: 敏感配置信息通过环境变量管理
- NFR8: 防止恶意请求和资源滥用

**可维护性需求**
- NFR9: 代码模块化，职责清晰
- NFR10: 支持单元测试和基准测试
- NFR11: 支持日志记录和监控
- NFR12: 配置文件与环境变量分离

**可扩展性需求**
- NFR13: 支持新增 Agent 角色
- NFR14: 支持插件式算法扩展（推荐策略、排序因子）
- NFR15: 支持多数据源接入

### 3.1.3 用户需求分析

**目标用户群体**
- 图书爱好者：获取个性化图书推荐
- 研究人员：了解多 Agent 协作系统在推荐领域的应用
- 开发者：学习 ACPS 协议和 Agent 协作实现
- 学生：参考本科毕业设计案例

**用户场景**
1. **场景 1: 图书发现（Warm Start）**
   - 用户有历史评分和书评数据
   - 系统分析用户偏好，召回相关图书
   - 多因子排序后返回 Top-K 推荐

2. **场景 2: 新书探索（Cold Start）**
   - 新用户无历史数据
   - 系统依赖内容推荐和知识图谱
   - 提高语义相似度权重，降低协同过滤权重

3. **场景 3: 多样性探索（Explore）**
   - 用户希望发现新类型的图书
   - 系统提高多样性因子权重（40%）
   - 推荐结果覆盖更多类别

## 3.2 系统架构设计

### 3.2.1 整体架构

本系统采用 Leader-Partner 架构，自顶向下分为三层：

```
┌─────────────────────────────────────────────────────────┐
│                    应用层 (Application)                  │
│  - Web Demo (index.html)  - FastAPI REST API            │
│  - 用户查询接口  - 实验数据接口                          │
├─────────────────────────────────────────────────────────┤
│                    业务层 (Business)                     │
│  ┌─────────────────┐  ┌─────────────────────────────┐   │
│  │ ReadingConcierge│  │   Partner Agents            │   │
│  │   (Leader)      │  │  - ReaderProfile            │   │
│  │  任务编排与整合  │  │  - BookContent              │   │
│  │                 │  │  - RecRanking               │   │
│  └─────────────────┘  └─────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│                    服务层 (Service)                      │
│  - model_backends.py (嵌入模型后端)                     │
│  - kg_client.py (知识图谱查询)                          │
│  - book_retrieval.py (图书检索)                         │
│  - evaluation_metrics.py (评估指标计算)                 │
│  - performance_chart_generator.py (图表生成)            │
└─────────────────────────────────────────────────────────┘
```

**应用层**: 提供 Web 界面和 REST API，处理用户请求和响应。基于 FastAPI 实现，支持异步处理。

**业务层**: 实现多 Agent 协作逻辑。ReadingConcierge 作为 Leader Agent 负责任务编排和结果整合；三个 Partner Agents（ReaderProfile、BookContent、RecRanking）负责专业化任务执行。

**服务层**: 提供通用服务模块，包括嵌入模型调用、知识图谱查询、图书检索、评估指标计算、图表生成等。

### 3.2.2 技术选型

**开发语言与框架**
- Python 3.10+: 主要开发语言
- FastAPI: Web API 框架（异步支持、自动文档）
- Pydantic: 数据验证和序列化

**数据存储**
- JSON/CSV: 实验数据导出格式
- 文件系统：图书数据集、知识图谱数据
- 内存缓存：会话管理、嵌入向量缓存

**AI 与嵌入**
- 阿里云百炼 DashScope API: LLM 调用（qwen3.5-27b）
- sentence-transformers: 本地嵌入模型（all-MiniLM-L6-v2, 384 维）
- scikit-learn: 机器学习工具（协同过滤、相似度计算）
- scipy: 科学计算（矩阵运算、相似度）
- networkx: 知识图谱处理

**多 Agent 协作**
- 自定义 ACPS 协议：基于 JSON-RPC 2.0 的 Agent 通信协议
- Leader-Partner 架构：ReadingConcierge 协调，Partner Agents 执行
- mTLS 双向认证：可选的 Agent 间通信安全

**开发工具**
- Git: 版本控制
- pytest: 单元测试和基准测试
- python-dotenv: 环境变量管理

### 3.2.3 部署架构

系统支持多种部署方式：

**单机部署**
- 适用于开发和测试环境
- 所有 Agent 和服务运行在同一台服务器
- 通过端口区分不同服务（ReadingConcierge: 8100, ReaderProfile: 8211, BookContent: 8212, RecRanking: 8213）
- 配置简单，成本低

**远程访问**
- 支持 SSH 端口转发访问 Web Demo
- 支持配置公网 URL 进行远程调用
- 适合云服务器部署场景

**容器化部署（计划）**
- 使用 Docker 容器封装应用
- 支持 Docker Compose 编排多 Agent 服务
- 便于迁移和扩展

## 3.3 核心模块设计

### 3.3.1 ReadingConcierge（Leader Agent）

ReadingConcierge 是系统的协调器，负责任务编排和结果整合。

**模块路径**: `reading_concierge/reading_concierge.py`

**核心职责**:
1. **用户意图解析**: 分析用户查询，识别场景类型（Warm/Cold/Explore）
2. **任务编排**: 创建子任务并分发给 Partner Agents
3. **并行调度**: ReaderProfile 和 BookContent 可并行执行
4. **结果整合**: 融合各 Agent 输出，生成最终推荐列表
5. **会话管理**: 维护用户会话状态，支持 LRU 缓存（默认 200 会话）

**关键配置**:
```python
BOOK_RETRIEVAL_TOP_K = 8          # 图书检索返回数量
BOOK_RETRIEVAL_CANDIDATE_POOL = 30 # 候选池大小
OPENAI_MODEL = "qwen3.5-27b"      # LLM 模型
MAX_SESSIONS = 200                # 最大会话数
```

**API 端点**:
- `POST /user_api`: 用户查询接口
- `GET /acs`: Agent 能力描述（ACS）
- `GET /demo/status`: 服务状态检查

### 3.3.2 ReaderProfile Agent（Partner）

ReaderProfile Agent 负责用户偏好分析。

**模块路径**: `agents/reader_profile_agent/profile_agent.py`

**核心职责**:
1. **历史行为分析**: 分析用户历史评分和书评
2. **偏好向量生成**: 生成用户偏好向量（类型、主题、难度、语言等）
3. **情感分析**: 提取用户评论中的情感倾向
4. **冷启动处理**: 为新用户提供默认偏好先验

**输入**: 用户历史评分、书评、查询上下文

**输出**: 
- `profile_vector`: 用户偏好向量
- `sentiment_summary`: 情感分析摘要
- `scenario`: 场景类型（warm/cold/explore）

**关键配置**:
```python
LLM_MODEL = "Doubao-pro-32k"           # 或从环境变量继承
EMBEDDING_VERSION = "reader_profile_v1"
DEFAULT_SCENARIO = "warm"
DEFAULT_GENRE_PRIORS = "fiction:0.25,science_fiction:0.2,..."
```

### 3.3.3 BookContent Agent（Partner）

BookContent Agent 负责图书内容理解。

**模块路径**: `agents/book_content_agent/book_content_agent.py`

**核心职责**:
1. **图书元数据分析**: 处理书名、作者、出版社、类型等信息
2. **语义嵌入生成**: 使用嵌入模型生成图书语义向量
3. **知识图谱增强**: 查询知识图谱获取关联信息（作者 - 书籍、出版社 - 书籍等）
4. **标签提取**: 提取图书主题、风格、难度等标签

**输入**: 候选图书 ID 列表、查询上下文

**输出**:
- `content_vectors`: 图书内容向量
- `kg_refs`: 知识图谱引用
- `tags`: 图书标签集合

**关键配置**:
```python
LLM_MODEL = "qwen3.5-27b"
EMBEDDING_VERSION = "book_content_v1"
```

### 3.3.4 RecRanking Agent（Partner）

RecRanking Agent 负责多因子融合排序。

**模块路径**: `agents/rec_ranking_agent/rec_ranking_agent.py`

**核心职责**:
1. **协同过滤评分**: 基于用户 - 物品矩阵计算协同过滤分数
2. **语义相似度计算**: 计算用户偏好与图书内容的语义相似度
3. **知识图谱增强**: 利用知识图谱关系增强评分
4. **多样性计算**: 确保推荐结果的多样性
5. **多因子融合**: 按场景权重融合各因子分数
6. **解释生成**: 为每个推荐生成自然语言解释

**输入**: 用户偏好向量、图书内容向量、候选图书列表

**输出**:
- `ranking`: 排序后的图书列表（含综合分数）
- `explanations`: 每本书的推荐解释
- `metrics_snapshot`: 评估指标快照

**评分权重**（场景自适应）:
| 场景 | 协同过滤 | 语义相似度 | 知识图谱 | 多样性 |
|------|---------|-----------|---------|--------|
| Warm Start | 25% | 35% | 20% | 20% |
| Cold Start | 10% | 45% | 25% | 20% |
| Explore | 15% | 25% | 20% | 40% |

### 3.3.5 服务层模块

服务层提供通用功能模块：

**model_backends.py** (`services/model_backends.py`)
- 嵌入模型后端管理
- 支持 DashScope API 和本地 sentence-transformers
- 向量缓存和复用

**kg_client.py** (`services/kg_client.py`)
- 知识图谱客户端
- 支持作者 - 书籍、出版社 - 书籍等关系查询
- 图遍历和关联发现

**book_retrieval.py** (`services/book_retrieval.py`)
- 图书检索服务
- 支持基于查询的图书召回
- 候选池管理

**evaluation_metrics.py** (`services/evaluation_metrics.py`)
- 推荐评估指标计算（Precision@K, Recall@K, NDCG@K, Diversity, Novelty）
- 消融实验报告生成
- 基准对比分析

**performance_chart_generator.py** (`services/performance_chart_generator.py`)
- 性能图表生成
- 支持 PNG 和 SVG 格式
- 可视化指标对比、雷达图、延迟分析等

**baseline_rankers.py** (`services/baseline_rankers.py`)
- 基线排序器实现
- 用于基准对比实验

**baseline_recommenders.py** (`services/baseline_recommenders.py`)
- 基线推荐器实现（Traditional Hybrid, LLM Only 等）
- 用于基准对比实验

### 3.3.6 ACPS 协议实现

ACPS 协议是 Agent 间通信的基础。

**模块路径**: `acps_aip/`

**核心组件**:
- `aip_base_model.py`: 基础数据模型（Message, Task, TaskState, Product 等）
- `aip_rpc_server.py`: RPC 服务器实现（TaskManager, CommandHandlers）
- `aip_rpc_client.py`: RPC 客户端实现

**消息格式**（基于 JSON-RPC 2.0）:
```json
{
  "jsonrpc": "2.0",
  "method": "StartTask",
  "params": {
    "taskId": "uuid",
    "taskName": "profile_enrichment",
    "sessionId": "session-uuid",
    "subQuery": { ... },
    "context": { ... },
    "acceptanceCriteria": { ... }
  },
  "id": 1
}
```

**任务状态机**:
```
Pending → Accepted → Working → AwaitingCompletion → Completed
                          ↓
                       Failed
```

**安全机制**:
- mTLS 双向认证（可选）
- API Key 认证（LLM 调用）
- 证书管理（`certs/` 目录）

## 3.4 数据结构设计

### 3.4.1 图书数据集

图书数据集包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| book_id | INTEGER | 图书 ID（主键） |
| title | TEXT | 书名 |
| authors | TEXT[] | 作者列表 |
| genres | TEXT[] | 类型列表 |
| description | TEXT | 简介 |
| average_rating | FLOAT | 平均评分 |
| num_ratings | INTEGER | 评分数量 |
| embedding | FLOAT[] | 嵌入向量（384 维） |

**数据来源**: Amazon Books / Goodreads / Amazon Kindle 合并数据集

**数据规模**: 约 119,345 册图书

### 3.4.2 用户数据集

用户数据集包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | INTEGER | 用户 ID（主键） |
| historical_ratings | JSON | 历史评分记录 |
| historical_reviews | JSON | 历史书评记录 |
| preference_vector | FLOAT[] | 偏好向量 |
| scenario | TEXT | 场景类型（warm/cold/explore） |

### 3.4.3 实验数据

实验数据包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| experiment_id | TEXT | 实验 ID |
| method | TEXT | 方法名称 |
| user_id | INTEGER | 用户 ID |
| precision | FLOAT | Precision@5 |
| recall | FLOAT | Recall@5 |
| ndcg | FLOAT | NDCG@5 |
| diversity | FLOAT | 多样性分数 |
| novelty | FLOAT | 新颖性分数 |
| latency_ms | FLOAT | 延迟（毫秒） |
| timestamp | DATETIME | 实验时间 |

### 3.4.4 知识图谱

知识图谱包含以下关系类型：

| 关系类型 | 说明 | 示例 |
|---------|------|------|
| author-book | 作者 - 书籍 | "刘慈欣" → "三体" |
| publisher-book | 出版社 - 书籍 | "科幻世界" → "三体" |
| genre-book | 类型 - 书籍 | "科幻" → "三体" |
| series-book | 系列 - 书籍 | "地球往事三部曲" → "三体" |
| book-book | 书籍关联 | "三体" → "黑暗森林" |

## 3.5 本章小结

本章进行了系统需求分析和架构设计，主要内容包括：

1. **功能性需求和非功能性需求分析**: 明确了图书推荐、多 Agent 协作、嵌入模型集成、数据管理等核心功能需求

2. **Leader-Partner 架构设计**: 采用三层架构（应用层、业务层、服务层），ReadingConcierge 作为 Leader 协调三个 Partner Agents

3. **核心模块设计**: 详细描述了 ReadingConcierge、ReaderProfile、BookContent、RecRanking 四个核心模块的职责、输入输出和配置

4. **服务层模块设计**: 描述了 model_backends、kg_client、book_retrieval、evaluation_metrics 等服务模块

5. **ACPS 协议设计**: 基于 JSON-RPC 2.0 实现 Agent 间通信，支持 mTLS 双向认证

6. **数据结构设计**: 定义了图书数据集、用户数据集、实验数据和知识图谱的结构


---



