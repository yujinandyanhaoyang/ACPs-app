# 第 3 章 系统需求分析与架构设计

## 3.1 需求分析

### 3.1.1 功能性需求

本系统是一个基于 ACPS 协议的多 Agent 协作推荐系统，主要功能需求包括：

**F1: 图书推荐功能**
- F1.1: 支持基于协同过滤的推荐
- F1.2: 支持基于内容的推荐
- F1.3: 支持混合推荐策略
- F1.4: 支持多因子排序（RecRanking）

**F2: 多 Agent 协作功能**
- F2.1: 支持四种角色（技术主管、Advisor、Coordinator、博士）
- F2.2: 支持任务分配与追踪
- F2.3: 支持 Agent 间通信
- F2.4: 支持任务审查与反馈

**F3: 嵌入模型集成功能**
- F3.1: 支持 DashScope 多模态嵌入 API
- F3.2: 支持 3 层 fallback 机制
- F3.3: 支持嵌入向量缓存

**F4: 数据管理功能**
- F4.1: 支持图书数据导入与管理
- F4.2: 支持用户数据存储
- F4.3: 支持推荐记录追踪
- F4.4: 支持实验数据导出

### 3.1.2 非功能性需求

**性能需求**
- NFR1: 推荐响应时间 < 500ms（P95）
- NFR2: 嵌入模型调用延迟 < 300ms（P95）
- NFR3: 支持并发用户数 ≥ 100
- NFR4: 系统可用性 ≥ 99%

**安全需求**
- NFR5: 支持 API Key 认证
- NFR6: 支持 mTLS 双向认证（可选）
- NFR7: 敏感数据加密存储
- NFR8: 防止 SQL 注入和 XSS 攻击

**可维护性需求**
- NFR9: 代码注释覆盖率 ≥ 80%
- NFR10: 单元测试覆盖率 ≥ 70%
- NFR11: 支持 Docker 容器化部署
- NFR12: 支持日志记录与监控

**可扩展性需求**
- NFR13: 支持水平扩展
- NFR14: 支持插件式算法扩展
- NFR15: 支持多数据源接入

### 3.1.3 用户需求分析

**目标用户群体**
- 图书爱好者：获取个性化图书推荐
- 研究人员：了解多 Agent 协作系统实现
- 开发者：学习推荐系统开发实践
- 学生：参考本科毕业设计案例

**用户场景**
1. **场景 1: 图书发现**
   - 用户输入查询（如"科幻小说 太空歌剧"）
   - 系统返回相关图书推荐
   - 用户浏览并选择感兴趣的图书

2. **场景 2: 论文撰写**
   - 博士角色接收论文撰写任务
   - 查阅相关文献和资料
   - 撰写论文并提交审查

3. **场景 3: 代码开发**
   - Coordinator 接收编码任务
   - 实现功能模块
   - 提交代码并请求审查

## 3.2 系统架构设计

### 3.2.1 整体架构

本系统采用分层架构设计，自底向上分为四层：

```
┌─────────────────────────────────────────┐
│           应用层 (Application)          │
│  - Web 界面  - API 接口  - 任务管理     │
├─────────────────────────────────────────┤
│           业务层 (Business)             │
│  - 推荐引擎  - Agent 协作  - 任务调度   │
├─────────────────────────────────────────┤
│           服务层 (Service)              │
│  - 嵌入服务  - 数据服务  - 认证服务     │
├─────────────────────────────────────────┤
│           数据层 (Data)                 │
│  - SQLite  - 文件系统  - 缓存           │
└─────────────────────────────────────────┘
```

**应用层**: 提供用户交互界面和 API 接口，处理 HTTP 请求和响应。

**业务层**: 实现核心业务逻辑，包括推荐算法、Agent 协作、任务调度等。

**服务层**: 提供通用服务，如嵌入模型调用、数据访问、安全认证等。

**数据层**: 负责数据持久化，包括 SQLite 数据库、文件系统、缓存等。

### 3.2.2 技术选型

**开发语言与框架**
- Python 3.8+: 主要开发语言
- Flask/FastAPI: Web API 框架
- SQLAlchemy: ORM 框架

**数据存储**
- SQLite: 关系型数据库（用户数据、推荐记录）
- JSON/CSV: 实验数据导出格式
- Redis（可选）: 缓存层

**AI 与嵌入**
- DashScope SDK: 多模态嵌入 API
- sentence-transformers: 本地嵌入模型
- scikit-learn: 机器学习工具

**多 Agent 协作**
- OpenClaw: Agent 编排层
- 自定义 ACPS 协议：Agent 通信协议

**开发工具**
- Git: 版本控制
- pytest: 单元测试
- Black/flake8: 代码格式化与检查

### 3.2.3 部署架构

系统支持多种部署方式：

**单机部署**
- 适用于开发和测试环境
- 所有组件运行在同一台服务器
- 配置简单，成本低

**容器化部署**
- 使用 Docker 容器封装应用
- 支持 Docker Compose 编排
- 便于迁移和扩展

**云部署**
- 部署到云服务器（如阿里云 ECS）
- 使用云数据库（如 RDS）
- 支持自动扩缩容

## 3.3 核心模块设计

### 3.3.1 推荐引擎模块

推荐引擎是系统的核心模块，负责生成个性化推荐。

**模块结构**
```
recommender/
├── __init__.py
├── collaborative_filtering.py  # 协同过滤
├── content_based.py            # 内容推荐
├── hybrid.py                   # 混合推荐
├── ranking.py                  # 多因子排序
└── evaluator.py                # 评估指标
```

**核心类设计**
- `RecommenderBase`: 推荐器基类，定义接口
- `CollaborativeFilteringRecommender`: 协同过滤推荐器
- `ContentBasedRecommender`: 内容推荐器
- `HybridRecommender`: 混合推荐器
- `RecRanking`: 多因子排序实现

**推荐流程**
1. 接收用户查询或 ID
2. 召回候选物品（基于 CF 或内容）
3. 计算推荐分数
4. 多因子排序
5. 返回 Top-K 推荐结果

### 3.3.2 多 Agent 协作模块

多 Agent 协作模块实现 ACPs-app 系统内部的 Agent 角色协作。

**角色定义**（推荐系统场景）
- `UserAgent`: 用户代理，代表用户兴趣和偏好
- `BookAgent`: 图书代理，代表图书特征和属性
- `RecommenderAgent`: 推荐代理，负责生成推荐
- `EvaluatorAgent`: 评估代理，负责评估推荐质量

**任务状态机**
```
Pending → Assigned → Running → Completed → Reviewed
                ↓           ↓
            Rejected   Failed
```

**通信机制**
- 基于 ACPS 协议的 JSON 消息
- 支持异步通信
- 消息持久化到数据库

### 3.3.3 嵌入模型集成模块

嵌入模型集成模块实现 3 层 fallback 机制。

**模块结构**
```
services/
├── model_backends.py          # 嵌入模型后端
├── experiment_data_collector.py  # 实验数据采集
└── performance_chart_generator.py # 图表生成
```

**Fallback 流程**
```
1. DashScope qwen3-vl-embedding (订阅制)
   ↓ 失败
2. 本地 sentence-transformers
   ↓ 失败
3. Hash fallback (SHA256)
```

**核心函数**
- `generate_text_embeddings()`: 主入口函数
- `_resolve_dashscope_multimodal_embeddings()`: DashScope 调用
- `_resolve_sentence_transformer()`: 本地模型加载
- `hash_embedding()`: Hash fallback 实现

### 3.3.4 数据存储模块

数据存储模块负责数据持久化。

**数据库表设计**

**用户表 (users)**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| username | TEXT | 用户名 |
| created_at | DATETIME | 创建时间 |

**图书表 (books)**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| title | TEXT | 书名 |
| authors | TEXT | 作者列表 |
| genres | TEXT | 类型列表 |
| description | TEXT | 简介 |
| embedding | BLOB | 嵌入向量 |

**推荐记录表 (recommendations)**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| user_id | INTEGER | 用户 ID |
| book_ids | TEXT | 推荐图书列表 |
| query | TEXT | 查询文本 |
| created_at | DATETIME | 创建时间 |

**任务表 (tasks)**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| task_id | TEXT | 任务 ID（唯一） |
| role | TEXT | 执行角色 |
| description | TEXT | 任务描述 |
| status | TEXT | 状态 |
| created_at | DATETIME | 创建时间 |
| completed_at | DATETIME | 完成时间 |

## 3.4 数据库设计

### 3.4.1 ER 图

```
┌──────────┐       ┌──────────────┐       ┌──────────────┐
│  users   │       │    books     │       │recommendations│
├──────────┤       ├──────────────┤       ├──────────────┤
│ id (PK)  │       │ id (PK)      │       │ id (PK)      │
│ username │       │ title        │       │ user_id (FK) │
│ ...      │       │ authors      │       │ book_ids     │
└──────────┘       │ genres       │       │ query        │
     │             │ description  │       │ created_at   │
     │             │ embedding    │       └──────────────┘
     │             └──────────────┘
     │                    │
     │                    │
     └────────────────────┘
          (推荐关系)
```

### 3.4.2 索引设计

为提高查询性能，设计以下索引：
- `books.title`: 书名搜索
- `books.genres`: 类型筛选
- `recommendations.user_id`: 用户推荐记录查询
- `recommendations.created_at`: 时间范围查询

### 3.4.3 数据迁移

使用 Alembic 管理数据库迁移：
```bash
alembic init migrations
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

## 3.5 本章小结

本章进行了系统需求分析和架构设计，主要内容包括：
1. 功能性需求和非功能性需求分析
2. 分层架构设计（应用层、业务层、服务层、数据层）
3. 核心模块设计（推荐引擎、多 Agent 协作、嵌入模型集成、数据存储）
4. 数据库表结构和索引设计

下一章将基于这些设计，详细描述系统的实现过程和关键技术。

---

**第 3 章 完成** ✅

**字数统计**: 约 3,800 字

**下一步**: 第 4 章 系统实现与关键技术
