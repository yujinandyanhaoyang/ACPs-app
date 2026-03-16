# 第 4 章 系统实现与关键技术

## 4.1 开发环境与工具

### 4.1.1 开发环境配置

本系统基于 Python 3.10+ 开发，开发环境配置如下：

**操作系统**: Ubuntu 20.04 LTS  
**Python 版本**: 3.10.12  
**开发工具**: VS Code  
**版本控制**: Git 2.34+

**虚拟环境**:
```bash
cd /root/ACPs-app
python3 -m venv venv
source venv/bin/activate
```

**依赖安装**:
```bash
pip install -r requirements.txt
```

**requirements.txt 核心依赖**:
```
fastapi>=0.100.0
uvicorn>=0.23.0
pydantic>=2.0.0
python-dotenv>=1.0.0
requests>=2.28.0
aiohttp>=3.9.0
scikit-learn>=1.5.0
scipy>=1.11.0
networkx>=3.0
sentence-transformers>=3.0.0
pytest>=7.0.0
httpx>=0.24.0
tiktoken>=0.5.0
```

### 4.1.2 项目目录结构

实际项目目录结构如下：

```
ACPs-app/
├── reading_concierge/              # Leader Agent（编排器）
│   ├── __init__.py
│   ├── reading_concierge.py        # 主服务入口
│   └── reading_concierge.json      # ACS 配置
├── agents/                         # Partner Agents
│   ├── __init__.py
│   ├── reader_profile_agent/
│   │   ├── __init__.py
│   │   ├── profile_agent.py        # ReaderProfile Agent 实现
│   │   └── config.example.json
│   ├── book_content_agent/
│   │   ├── __init__.py
│   │   ├── book_content_agent.py   # BookContent Agent 实现
│   │   └── config.example.json
│   └── rec_ranking_agent/
│       ├── __init__.py
│       ├── rec_ranking_agent.py    # RecRanking Agent 实现
│       └── config.example.json
├── acps_aip/                       # ACPS 协议实现
│   ├── aip_base_model.py           # 基础数据模型
│   ├── aip_rpc_server.py           # RPC 服务器
│   └── aip_rpc_client.py           # RPC 客户端
├── services/                       # 服务层
│   ├── __init__.py
│   ├── model_backends.py           # 嵌入模型后端
│   ├── kg_client.py                # 知识图谱客户端
│   ├── book_retrieval.py           # 图书检索服务
│   ├── evaluation_metrics.py       # 评估指标计算
│   ├── performance_chart_generator.py  # 图表生成
│   ├── baseline_rankers.py         # 基线排序器
│   └── baseline_recommenders.py    # 基线推荐器
├── scripts/                        # 脚本工具
│   ├── phase4_benchmark.py         # 基准测试脚本
│   ├── phase4_optimizer.py         # 优化脚本
│   └── gen_dev_certs.sh            # 证书生成脚本
├── experiments/                    # 实验数据
│   ├── charts/                     # 图表输出
│   ├── embedding_model_comparison/ # 嵌入模型对比数据
│   └── ablation_run_20260315.log   # 消融实验日志
├── web_demo/                       # Web 界面
│   └── index.html                  # 单页应用
├── tests/                          # 测试
│   └── test_aliyun_config.py       # 配置测试
├── certs/                          # mTLS 证书
│   ├── ca.crt/ca.key               # CA 证书
│   └── *.crt/*.key                 # 服务证书
├── docs/                           # 文档
│   ├── thesis/                     # 论文
│   └── *.md                        # 技术文档
├── .env                            # 环境变量配置
├── .env.example                    # 环境变量示例
├── requirements.txt                # 依赖列表
├── README.md                       # 项目说明
└── AGENT_SPEC.md                   # Agent 规范
```

### 4.1.3 配置管理

系统使用环境变量和 `.env` 文件进行配置管理：

**核心配置项**（`.env`）:
```bash
# 嵌入模型配置
HF_ENDPOINT=https://hf-mirror.com
DASHSCOPE_API_KEY=
DASHSCOPE_EMBED_MODEL=all-MiniLM-L6-v2

# LLM 配置（阿里云百炼）
OPENAI_MODEL=qwen3.5-27b
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 应用配置
PORT=8100
LOG_LEVEL=INFO
DATASET_ROOT=/root/DataSet

# Agent 配置
READING_CONCIERGE_ID=reading_concierge_001
READER_PROFILE_AGENT_ID=reader_profile_agent_001
BOOK_CONTENT_AGENT_ID=book_content_agent_001
REC_RANKING_AGENT_ID=rec_ranking_agent_001
```

**配置加载**（使用 python-dotenv）:
```python
from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "qwen3.5-27b")
DATASET_ROOT = os.getenv("DATASET_ROOT", "/root/DataSet")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
```

## 4.2 核心功能实现

### 4.2.1 ReadingConcierge 实现

ReadingConcierge 是系统的 Leader Agent，负责任务编排和结果整合。

**核心代码结构**（`reading_concierge/reading_concierge.py`）:

```python
from fastapi import FastAPI
from typing import Any, Dict, List, OrderedDict
from collections import OrderedDict

from base import call_openai_chat, register_acs_route
from services.book_retrieval import load_books, retrieve_books_by_query
from services.model_backends import load_cf_item_vectors
from agents.reader_profile_agent import profile_agent as reader_profile
from agents.book_content_agent import book_content_agent as book_content
from agents.rec_ranking_agent import rec_ranking_agent as rec_ranking

app = FastAPI(title="Reading Concierge")

# 会话管理（LRU 缓存）
MAX_SESSIONS = int(os.getenv("READING_CONCIERGE_MAX_SESSIONS", "200"))
sessions: OrderedDict[str, Dict[str, Any]] = OrderedDict()

def _lru_session_get(session_id: str) -> Dict[str, Any]:
    """获取或创建会话，超出容量时淘汰最旧会话"""
    if session_id in sessions:
        sessions.move_to_end(session_id)
        return sessions[session_id]
    
    if len(sessions) >= MAX_SESSIONS:
        sessions.popitem(last=False)
    
    sessions[session_id] = {
        'created_at': datetime.now().isoformat(),
        'messages': [],
        'context': {}
    }
    return sessions[session_id]

@app.post("/user_api")
async def handle_user_query(request: UserQueryRequest):
    """处理用户查询"""
    session = _lru_session_get(request.session_id)
    
    # 1. 场景识别
    scenario = detect_scenario(session['context'])
    
    # 2. 图书检索（召回候选）
    candidates = retrieve_books_by_query(
        request.query, 
        top_k=BOOK_RETRIEVAL_TOP_K,
        candidate_pool=BOOK_RETRIEVAL_CANDIDATE_POOL
    )
    
    # 3. 并行调用 Partner Agents
    profile_task = asyncio.create_task(
        reader_profile.analyze_user_profile(
            user_history=session['context'].get('history', []),
            scenario=scenario
        )
    )
    content_task = asyncio.create_task(
        book_content.analyze_book_content(candidates)
    )
    
    # 4. 等待结果
    profile_result = await profile_task
    content_result = await content_task
    
    # 5. 调用 RecRanking 进行排序
    ranking_result = await rec_ranking.rank(
        profile_vector=profile_result['profile_vector'],
        content_vectors=content_result['content_vectors'],
        candidates=candidates,
        scenario=scenario
    )
    
    # 6. 生成解释并返回
    response = generate_response(ranking_result, profile_result)
    return response
```

**关键实现要点**:

1. **会话管理**: 使用 `OrderedDict` 实现 LRU 缓存，默认最大 200 会话
2. **并行调度**: 使用 `asyncio.create_task` 并行调用 ReaderProfile 和 BookContent
3. **场景识别**: 根据用户历史数据丰富程度判断场景类型（Warm/Cold/Explore）
4. **结果整合**: 融合各 Agent 输出，生成自然语言解释

### 4.2.2 ReaderProfile Agent 实现

ReaderProfile Agent 负责用户偏好分析。

**核心代码结构**（`agents/reader_profile_agent/profile_agent.py`）:

```python
from fastapi import FastAPI
from acps_aip.aip_base_model import Message, Task, TaskState
from acps_aip.aip_rpc_server import add_aip_rpc_router, TaskManager

from base import extract_text_from_message, call_openai_chat

app = FastAPI(title="Reader Profile Agent")

_PROFILE_CONTEXT: dict[str, Dict[str, Any]] = {}

def _parse_payload(message: Message) -> Dict[str, Any]:
    """解析消息负载"""
    params = getattr(message, "commandParams", None) or {}
    payload = params.get("payload") if isinstance(params, dict) else None
    if isinstance(payload, dict):
        return payload
    # 尝试从文本解析 JSON
    text = extract_text_from_message(message)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}

def _build_preference_vector(history: List[Dict], reviews: List[str]) -> Dict:
    """构建用户偏好向量"""
    # 分析历史评分，提取类型偏好
    genre_distribution = analyze_genre_distribution(history)
    
    # 分析书评，提取情感倾向和主题偏好
    sentiment_summary = analyze_sentiment(reviews)
    theme_keywords = extract_theme_keywords(reviews)
    
    # 生成结构化偏好向量
    return {
        'genre_weights': genre_distribution,
        'sentiment_profile': sentiment_summary,
        'theme_preferences': theme_keywords,
        'difficulty_preference': infer_difficulty(history),
        'language_preference': 'zh'  # 默认中文
    }

async def analyze_user_profile(
    user_history: List[Dict],
    scenario: str = "warm"
) -> Dict[str, Any]:
    """分析用户画像"""
    if not user_history and scenario == "cold":
        # 冷启动：使用默认先验
        return {
            'profile_vector': get_default_prior_vector(),
            'scenario': 'cold',
            'confidence': 0.3
        }
    
    # 构建偏好向量
    profile_vector = _build_preference_vector(
        history=user_history.get('ratings', []),
        reviews=user_history.get('reviews', [])
    )
    
    return {
        'profile_vector': profile_vector,
        'scenario': scenario,
        'confidence': 0.8 if len(user_history) > 5 else 0.5
    }
```

**关键实现要点**:

1. **偏好向量结构**: 包含类型权重、情感分析、主题偏好、难度偏好等维度
2. **冷启动处理**: 为新用户提供默认先验分布
3. **置信度评估**: 根据历史数据量评估偏好向量的置信度

### 4.2.3 BookContent Agent 实现

BookContent Agent 负责图书内容理解。

**核心代码结构**（`agents/book_content_agent/book_content_agent.py`）:

```python
from fastapi import FastAPI
from services.model_backends import generate_text_embeddings
from services.kg_client import query_knowledge_graph

app = FastAPI(title="Book Content Agent")

async def analyze_book_content(
    candidates: List[Dict]
) -> Dict[str, Any]:
    """分析图书内容"""
    book_ids = [book['book_id'] for book in candidates]
    
    # 1. 生成图书内容文本（标题 + 作者 + 简介 + 类型）
    content_texts = [
        f"{book['title']} by {', '.join(book['authors'])}. "
        f"{book.get('description', '')}. "
        f"Genres: {', '.join(book.get('genres', []))}"
        for book in candidates
    ]
    
    # 2. 生成嵌入向量
    embeddings, meta = generate_text_embeddings(content_texts)
    
    # 3. 查询知识图谱增强
    kg_refs = []
    for book in candidates:
        kg_info = query_knowledge_graph(book['book_id'])
        if kg_info:
            kg_refs.append({
                'book_id': book['book_id'],
                'author_links': kg_info.get('authors', []),
                'publisher_links': kg_info.get('publishers', []),
                'series_links': kg_info.get('series', [])
            })
    
    # 4. 提取标签
    tags = extract_book_tags(candidates)
    
    return {
        'content_vectors': embeddings,
        'kg_refs': kg_refs,
        'tags': tags,
        'embedding_meta': meta
    }

def extract_book_tags(candidates: List[Dict]) -> Dict[str, List[str]]:
    """提取图书标签"""
    tags = {}
    for book in candidates:
        book_tags = []
        # 从类型提取
        book_tags.extend(book.get('genres', []))
        # 从简介提取关键词
        if book.get('description'):
            keywords = extract_keywords(book['description'])
            book_tags.extend(keywords[:5])
        tags[book['book_id']] = list(set(book_tags))
    return tags
```

**关键实现要点**:

1. **内容文本构建**: 组合标题、作者、简介、类型等信息生成完整内容描述
2. **嵌入生成**: 使用本地 sentence-transformers 模型生成 384 维向量
3. **知识图谱增强**: 查询作者、出版社、系列等关联信息

### 4.2.4 RecRanking Agent 实现

RecRanking Agent 负责多因子融合排序。

**核心代码结构**（`agents/rec_ranking_agent/rec_ranking_agent.py`）:

```python
from fastapi import FastAPI
from services.evaluation_metrics import compute_recommendation_metrics
import numpy as np

app = FastAPI(title="Rec Ranking Agent")

# 场景自适应权重
SCENARIO_WEIGHTS = {
    'warm': {'cf': 0.25, 'semantic': 0.35, 'kg': 0.20, 'diversity': 0.20},
    'cold': {'cf': 0.10, 'semantic': 0.45, 'kg': 0.25, 'diversity': 0.20},
    'explore': {'cf': 0.15, 'semantic': 0.25, 'kg': 0.20, 'diversity': 0.40}
}

async def rank(
    profile_vector: Dict,
    content_vectors: List[List[float]],
    candidates: List[Dict],
    scenario: str = "warm"
) -> Dict[str, Any]:
    """多因子融合排序"""
    weights = SCENARIO_WEIGHTS.get(scenario, SCENARIO_WEIGHTS['warm'])
    
    # 1. 计算协同过滤分数
    cf_scores = compute_cf_scores(profile_vector, candidates)
    
    # 2. 计算语义相似度分数
    semantic_scores = compute_semantic_scores(profile_vector, content_vectors)
    
    # 3. 计算知识图谱增强分数
    kg_scores = compute_kg_scores(profile_vector, candidates)
    
    # 4. 计算多样性分数
    diversity_scores = compute_diversity_scores(candidates)
    
    # 5. 多因子融合
    final_scores = []
    for i, book in enumerate(candidates):
        score = (
            weights['cf'] * cf_scores[i] +
            weights['semantic'] * semantic_scores[i] +
            weights['kg'] * kg_scores[i] +
            weights['diversity'] * diversity_scores[i]
        )
        final_scores.append(score)
    
    # 6. 排序
    sorted_indices = np.argsort(final_scores)[::-1]
    ranked_books = [candidates[i] for i in sorted_indices]
    ranked_scores = [final_scores[i] for i in sorted_indices]
    
    # 7. 生成解释
    explanations = generate_explanations(ranked_books, profile_vector)
    
    return {
        'ranking': list(zip(ranked_books, ranked_scores)),
        'explanations': explanations,
        'scores': {
            'cf': cf_scores,
            'semantic': semantic_scores,
            'kg': kg_scores,
            'diversity': diversity_scores
        }
    }

def compute_semantic_scores(
    profile_vector: Dict,
    content_vectors: List[List[float]]
) -> List[float]:
    """计算语义相似度分数"""
    from sklearn.metrics.pairwise import cosine_similarity
    
    # 将偏好向量转换为嵌入（简化实现）
    profile_embedding = profile_vector_to_embedding(profile_vector)
    
    # 计算余弦相似度
    similarities = cosine_similarity(
        [profile_embedding],
        content_vectors
    )[0]
    
    # 归一化到 [0, 1]
    return (similarities - similarities.min()) / (similarities.max() - similarities.min() + 1e-8)
```

**关键实现要点**:

1. **场景自适应权重**: 根据 Warm/Cold/Explore 场景动态调整各因子权重
2. **多因子融合**: 线性加权融合协同过滤、语义相似度、知识图谱、多样性四个因子
3. **解释生成**: 为每个推荐生成自然语言解释，说明推荐理由

## 4.3 ACPS 协议实现

### 4.3.1 基础数据模型

ACPS 协议基于 JSON-RPC 2.0，定义以下基础数据模型（`acps_aip/aip_base_model.py`）:

```python
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from enum import Enum

class TaskState(str, Enum):
    """任务状态枚举"""
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    WORKING = "Working"
    AWAITING_INPUT = "AwaitingInput"
    AWAITING_COMPLETION = "AwaitingCompletion"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"

class Message(BaseModel):
    """ACPS 消息"""
    taskId: str = Field(..., description="任务 ID")
    sessionId: str = Field(..., description="会话 ID")
    state: TaskState = Field(..., description="任务状态")
    outputs: Dict[str, Any] = Field(default_factory=dict, description="输出数据")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="诊断信息")

class Task(BaseModel):
    """ACPS 任务"""
    taskId: str
    taskName: str
    sessionId: str
    subQuery: Dict[str, Any]
    context: Dict[str, Any]
    acceptanceCriteria: Dict[str, Any]
    state: TaskState = TaskState.PENDING
```

### 4.3.2 RPC 服务器实现

RPC 服务器实现（`acps_aip/aip_rpc_server.py`）:

```python
from fastapi import FastAPI, APIRouter
from pydantic import BaseModel

class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.task_handlers: Dict[str, callable] = {}
    
    def register_handler(self, task_name: str, handler: callable):
        """注册任务处理器"""
        self.task_handlers[task_name] = handler
    
    async def start_task(self, task: Task) -> Task:
        """启动任务"""
        task.state = TaskState.ACCEPTED
        self.tasks[task.taskId] = task
        
        # 异步执行任务
        handler = self.task_handlers.get(task.taskName)
        if handler:
            asyncio.create_task(self._execute_task(task, handler))
        
        return task
    
    async def _execute_task(self, task: Task, handler: callable):
        """执行任务"""
        try:
            task.state = TaskState.WORKING
            result = await handler(task)
            task.outputs = result
            task.state = TaskState.AWAITING_COMPLETION
        except Exception as e:
            task.state = TaskState.FAILED
            task.diagnostics['error'] = str(e)

def add_aip_rpc_router(app: FastAPI, task_manager: TaskManager):
    """添加 RPC 路由到 FastAPI 应用"""
    router = APIRouter()
    
    @router.post("/rpc/start")
    async def start_task(task: Task):
        return await task_manager.start_task(task)
    
    @router.get("/rpc/status/{task_id}")
    async def get_task_status(task_id: str):
        task = task_manager.tasks.get(task_id)
        return task if task else {"error": "Task not found"}
    
    app.include_router(router)
```

### 4.3.3 ACS（Agent Capability Specification）

每个 Agent 都有 ACS 配置文件，描述其能力和技能：

**ReadingConcierge ACS** (`reading_concierge/reading_concierge.json`):
```json
{
  "agentId": "reading_concierge_001",
  "agentName": "Reading Concierge",
  "description": "Coordinator for book recommendation workflow",
  "skills": [
    "workflow.orchestrate",
    "result.integrate",
    "session.manage"
  ],
  "transport": {
    "type": "http",
    "baseUrl": "http://localhost:8100"
  },
  "capabilities": {
    "maxConcurrentTasks": 10,
    "supportedScenarios": ["warm", "cold", "explore"]
  }
}
```

**ReaderProfile ACS** (`agents/reader_profile_agent/config.example.json`):
```json
{
  "agentId": "reader_profile_agent_001",
  "agentName": "Reader Profile Agent",
  "description": "Analyzes user preferences for book recommendations",
  "skills": [
    "profile.extract",
    "preference.embedding",
    "sentiment.analysis"
  ],
  "transport": {
    "type": "http",
    "baseUrl": "http://localhost:8211"
  }
}
```

### 4.3.4 mTLS 双向认证

系统支持 mTLS 双向认证用于 Agent 间通信安全：

**证书生成** (`scripts/gen_dev_certs.sh`):
```bash
#!/bin/bash
# 生成 CA 证书
openssl genrsa -out ca.key 2048
openssl req -new -x509 -days 365 -key ca.key -out ca.crt \
  -subj "/CN=ACPs-Dev-CA"

# 生成服务证书
for service in reading_concierge reader_profile book_content rec_ranking; do
  openssl genrsa -out ${service}.key 2048
  openssl req -new -key ${service}.key -out ${service}.csr \
    -subj "/CN=${service}"
  openssl x509 -req -days 365 -in ${service}.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out ${service}.crt
done
```

**mTLS 配置**（环境变量）:
```bash
AGENT_MTLS_ENABLED=true
AGENT_MTLS_CERT_DIR=/root/ACPs-app/certs
READING_CONCIERGE_MTLS_CONFIG_PATH=/root/ACPs-app/certs/reading_concierge.json
```

## 4.4 嵌入模型集成

### 4.4.1 本地 sentence-transformers 集成

系统使用本地 sentence-transformers 模型生成嵌入向量：

**模型配置**（`services/model_backends.py`）:
```python
from sentence_transformers import SentenceTransformer
import os

# 本地模型配置
EMBED_MODEL_NAME = os.getenv("DASHSCOPE_EMBED_MODEL", "all-MiniLM-L6-v2")
_model_cache = {}

def get_embedding_model():
    """获取嵌入模型（单例缓存）"""
    if EMBED_MODEL_NAME not in _model_cache:
        _model_cache[EMBED_MODEL_NAME] = SentenceTransformer(EMBED_MODEL_NAME)
    return _model_cache[EMBED_MODEL_NAME]

def generate_text_embeddings(
    texts: List[str],
    model_name: str = None
) -> Tuple[List[List[float]], Dict[str, Any]]:
    """生成文本嵌入"""
    model = get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    
    return (
        embeddings.tolist(),
        {
            'backend': 'sentence-transformers',
            'model': EMBED_MODEL_NAME,
            'vector_dim': embeddings.shape[1],  # 384
            'normalized': True
        }
    )
```

**模型特点**:
- **模型名称**: all-MiniLM-L6-v2
- **向量维度**: 384
- **优势**: 轻量高效，离线运行，零成本
- **延迟**: ~50ms/请求

### 4.4.2 协同过滤向量加载

协同过滤功能使用预计算的用户 - 物品矩阵：

```python
# services/model_backends.py
import numpy as np
import os

def load_cf_item_vectors() -> np.ndarray:
    """加载协同过滤物品向量"""
    cf_path = os.path.join(
        os.getenv("DATASET_ROOT", "/root/DataSet"),
        "cf_item_vectors.npy"
    )
    if os.path.exists(cf_path):
        return np.load(cf_path)
    return None
```

## 4.5 服务层实现

### 4.5.1 知识图谱客户端

知识图谱客户端实现（`services/kg_client.py`）:

```python
import networkx as nx
import json
import os

class KnowledgeGraphClient:
    """知识图谱客户端"""
    
    def __init__(self, kg_path: str = None):
        kg_path = kg_path or os.path.join(
            os.getenv("DATASET_ROOT"),
            "knowledge_graph.json"
        )
        self.graph = self._load_graph(kg_path)
    
    def _load_graph(self, path: str) -> nx.Graph:
        """加载知识图谱"""
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return nx.node_link_graph(data)
        return nx.Graph()
    
    def query_authors(self, book_id: str) -> List[str]:
        """查询图书作者"""
        return list(self.graph.neighbors(book_id))
    
    def query_related_books(self, book_id: str, relation_type: str = None) -> List[str]:
        """查询关联图书"""
        neighbors = list(self.graph.neighbors(book_id))
        if relation_type:
            # 按关系类型过滤
            return [n for n in neighbors 
                    if self.graph[book_id][n].get('type') == relation_type]
        return neighbors
```

### 4.5.2 图书检索服务

图书检索服务实现（`services/book_retrieval.py`）:

```python
import os
import json
from typing import List, Dict

_books_cache = None

def load_books() -> List[Dict]:
    """加载图书数据集"""
    global _books_cache
    if _books_cache is not None:
        return _books_cache
    
    dataset_path = os.path.join(
        os.getenv("DATASET_ROOT", "/root/DataSet"),
        "books_cleaned.json"
    )
    
    with open(dataset_path, 'r', encoding='utf-8') as f:
        _books_cache = json.load(f)
    
    return _books_cache

def retrieve_books_by_query(
    query: str,
    top_k: int = 8,
    candidate_pool: int = 30
) -> List[Dict]:
    """基于查询检索图书"""
    books = load_books()
    
    # 简单关键词匹配（实际实现使用嵌入相似度）
    query_terms = query.lower().split()
    scored_books = []
    
    for book in books[:candidate_pool * 2]:  # 限制扫描范围
        score = 0
        title_lower = book.get('title', '').lower()
        for term in query_terms:
            if term in title_lower:
                score += 1
        
        if score > 0:
            scored_books.append((score, book))
    
    # 按分数排序
    scored_books.sort(key=lambda x: x[0], reverse=True)
    
    return [book for _, book in scored_books[:top_k]]
```

### 4.5.3 评估指标计算

评估指标计算实现（`services/evaluation_metrics.py`）:

```python
import numpy as np
from typing import List, Dict

def compute_recommendation_metrics(
    recommended: List[str],
    relevant: List[str],
    k: int = 5
) -> Dict[str, float]:
    """计算推荐评估指标"""
    rec_set = set(recommended[:k])
    rel_set = set(relevant)
    
    # Precision@K
    precision = len(rec_set & rel_set) / k if k > 0 else 0.0
    
    # Recall@K
    recall = len(rec_set & rel_set) / len(rel_set) if rel_set else 0.0
    
    # NDCG@K
    dcg = 0.0
    for i, book_id in enumerate(recommended[:k]):
        if book_id in rel_set:
            dcg += 1.0 / np.log2(i + 2)
    
    idcg = sum(1.0 / np.log2(i + 2) for i in range(min(len(rel_set), k)))
    ndcg = dcg / idcg if idcg > 0 else 0.0
    
    return {
        'precision': precision,
        'recall': recall,
        'ndcg': ndcg
    }
```

### 4.5.4 图表生成

性能图表生成实现（`services/performance_chart_generator.py`）:

```python
import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, List

class ChartGenerator:
    """图表生成器"""
    
    def __init__(self, output_dir: str = "experiments/charts"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_metrics_comparison(
        self,
        methods: List[str],
        metrics: Dict[str, List[float]]
    ) -> str:
        """生成指标对比柱状图"""
        x = np.arange(len(methods))
        width = 0.2
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        for i, (metric_name, values) in enumerate(metrics.items()):
            ax.bar(x + i * width, values, width, label=metric_name)
        
        ax.set_xlabel('Method')
        ax.set_ylabel('Score')
        ax.set_title('Recommendation Metrics Comparison')
        ax.set_xticks(x + width * 1.5)
        ax.set_xticklabels(methods)
        ax.legend()
        
        output_path = os.path.join(self.output_dir, "01_metrics_comparison.png")
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return output_path
```

## 4.6 Web Demo 实现

### 4.6.1 单页应用

Web Demo 使用纯 HTML + JavaScript 实现（`web_demo/index.html`）:

**核心功能**:
- 用户查询输入
- 推荐结果展示
- Agent 协作状态可视化
- 性能指标展示

**API 调用**:
```javascript
async function submitQuery(query) {
    const response = await fetch('/user_api', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            query: query,
            session_id: getSessionId()
        })
    });
    return await response.json();
}
```

### 4.6.2 服务状态端点

系统提供服务状态检查端点：

```python
@app.get("/demo/status")
async def get_status():
    """获取服务状态"""
    return {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'sessions_active': len(sessions),
        'agents': {
            'reading_concierge': 'running',
            'reader_profile': 'running',
            'book_content': 'running',
            'rec_ranking': 'running'
        }
    }
```

## 4.7 实验系统实现

### 4.7.1 基准测试脚本

基准测试脚本实现（`scripts/phase4_benchmark.py`）:

```python
#!/usr/bin/env python3
"""Phase 4: Benchmark comparison of 4 recommendation methods"""

import json
import os
from services.baseline_recommenders import (
    ACPSMultiAgentRecommender,
    TraditionalHybridRecommender,
    MultiAgentProxyRecommender,
    LLMOnlyRecommender
)
from services.evaluation_metrics import compute_recommendation_metrics

def run_benchmark(test_cases: List[Dict]) -> Dict:
    """运行基准测试"""
    methods = {
        'acps_multi_agent': ACPSMultiAgentRecommender(),
        'traditional_hybrid': TraditionalHybridRecommender(),
        'multi_agent_proxy': MultiAgentProxyRecommender(),
        'llm_only': LLMOnlyRecommender()
    }
    
    results = {method: [] for method in methods}
    
    for test_case in test_cases:
        user_history = test_case['user_history']
        candidates = test_case['candidates']
        relevant = test_case['relevant']
        
        for method_name, recommender in methods.items():
            recommended = recommender.recommend(user_history, candidates)
            metrics = compute_recommendation_metrics(recommended, relevant)
            results[method_name].append(metrics)
    
    # 计算平均值
    summary = {}
    for method_name, method_results in results.items():
        summary[method_name] = {
            'precision': np.mean([r['precision'] for r in method_results]),
            'recall': np.mean([r['recall'] for r in method_results]),
            'ndcg': np.mean([r['ndcg'] for r in method_results])
        }
    
    return summary
```

### 4.7.2 消融实验实现

消融实验实现（`scripts/phase4_optimizer.py`）:

```python
#!/usr/bin/env python3
"""Phase 4: Ablation study"""

from services.model_backends import SCENARIO_WEIGHTS

def run_ablation(users: List[Dict], ablation_configs: List[Dict]) -> Dict:
    """运行消融实验"""
    results = {config['name']: [] for config in ablation_configs}
    
    for user in users:
        for config in ablation_configs:
            # 临时修改权重
            original_weights = SCENARIO_WEIGHTS[config['scenario']].copy()
            SCENARIO_WEIGHTS[config['scenario']] = config['weights']
            
            # 运行推荐
            recommender = ACPSMultiAgentRecommender()
            recommended = recommender.recommend(user['history'], user['candidates'])
            metrics = compute_recommendation_metrics(recommended, user['relevant'])
            
            results[config['name']].append(metrics['ndcg'])
            
            # 恢复权重
            SCENARIO_WEIGHTS[config['scenario']] = original_weights
    
    # 计算平均 NDCG
    summary = {
        name: np.mean(scores)
        for name, scores in results.items()
    }
    
    return summary
```

## 4.8 本章小结

本章详细描述了 ACPs-app 系统的实现过程和关键技术，主要内容包括：

1. **开发环境配置**: Python 3.10+、FastAPI、sentence-transformers 等核心依赖

2. **项目目录结构**: reading_concierge（Leader）、agents（Partners）、services（服务层）、acps_aip（协议实现）

3. **核心 Agent 实现**:
   - ReadingConcierge：任务编排和结果整合
   - ReaderProfile：用户偏好分析
   - BookContent：图书内容理解
   - RecRanking：多因子融合排序

4. **ACPS 协议实现**: 基于 JSON-RPC 2.0 的通信协议，支持 mTLS 双向认证

5. **嵌入模型集成**: 本地 sentence-transformers（all-MiniLM-L6-v2, 384 维）

6. **服务层实现**: 知识图谱客户端、图书检索、评估指标计算、图表生成

7. **实验系统实现**: 基准测试脚本、消融实验脚本


---



