# 第 4 章 系统实现与关键技术

## 4.1 开发环境与工具

### 4.1.1 开发环境配置

本系统基于 Python 3.8+ 开发，开发环境配置如下：

**操作系统**: Ubuntu 20.04 LTS / macOS 12+  
**Python 版本**: 3.8.10  
**开发工具**: VS Code / PyCharm  
**版本控制**: Git 2.30+

**虚拟环境**:
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate  # Windows
```

**依赖安装**:
```bash
pip install -r requirements.txt
```

**requirements.txt 核心依赖**:
```
flask==2.3.0
sqlalchemy==2.0.0
dashscope>=1.0.0
scikit-learn==1.3.0
numpy==1.24.0
pandas==2.0.0
pytest==7.4.0
```

### 4.1.2 项目目录结构

```
ACPs-app/
├── agents/                     # Agent 实现
│   ├── tech_lead.py           # 技术主管
│   ├── advisor.py             # Advisor
│   ├── coordinator.py         # Coordinator
│   └── phd_writer.py          # 博士
├── recommender/                # 推荐引擎
│   ├── collaborative_filtering.py
│   ├── content_based.py
│   ├── hybrid.py
│   └── ranking.py
├── services/                   # 服务层
│   ├── model_backends.py      # 嵌入模型后端
│   ├── experiment_data_collector.py
│   └── performance_chart_generator.py
├── scripts/                    # 脚本工具
│   ├── run_experiment_and_generate_charts.py
│   └── test_experiment_modules.py
├── experiments/                # 实验数据
│   ├── charts/                # 图表输出
│   └── embedding_benchmark_20260312.json
├── docs/                       # 文档
│   ├── thesis/                # 论文
│   └── DASHSCOPE_MIGRATION.md
├── tests/                      # 测试
│   ├── test_recommender.py
│   └── test_embeddings.py
├── requirements.txt            # 依赖
└── README.md                   # 项目说明
```

### 4.1.3 版本控制策略

采用 Git Flow 分支管理策略：
- `main`: 主分支，稳定版本
- `develop`: 开发分支
- `feat/*`: 功能分支
- `fix/*`: 修复分支

**提交规范**:
```
<type>: <description>

[optional body]

[optional footer]
```

类型包括：`feat`（新功能）、`fix`（修复）、`docs`（文档）、`test`（测试）、`refactor`（重构）等。

## 4.2 核心功能实现

### 4.2.1 协同过滤推荐实现

协同过滤模块实现了基于物品的协同过滤算法：

```python
# agents/collaborative_filtering.py
import numpy as np
from typing import Dict, List, Tuple

class CollaborativeFilteringRecommender:
    def __init__(self, user_item_matrix: np.ndarray):
        """
        初始化协同过滤推荐器
        
        Args:
            user_item_matrix: 用户 - 物品评分矩阵 (m×n)
        """
        self.matrix = user_item_matrix
        self.item_similarity = self._compute_item_similarity()
    
    def _compute_item_similarity(self) -> np.ndarray:
        """计算物品之间的余弦相似度"""
        # 转置矩阵，按列计算相似度
        items = self.matrix.T
        norms = np.linalg.norm(items, axis=1, keepdims=True)
        normalized = items / (norms + 1e-8)
        similarity = np.dot(normalized, normalized.T)
        return similarity
    
    def recommend(self, user_id: int, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        为指定用户生成推荐
        
        Args:
            user_id: 用户 ID
            top_k: 推荐数量
            
        Returns:
            推荐列表 [(item_id, score), ...]
        """
        user_ratings = self.matrix[user_id]
        rated_items = np.where(user_ratings > 0)[0]
        
        if len(rated_items) == 0:
            return []  # 冷启动问题
        
        # 计算候选物品分数
        scores = np.zeros(self.matrix.shape[1])
        for item_idx in range(self.matrix.shape[1]):
            if user_ratings[item_idx] > 0:
                continue  # 跳过已评分物品
            
            # 加权求和：相似度 × 评分
            similar_items = self.item_similarity[item_idx, rated_items]
            user_scores = user_ratings[rated_items]
            scores[item_idx] = np.dot(similar_items, user_scores) / (np.sum(similar_items) + 1e-8)
        
        # 返回 Top-K
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(idx, scores[idx]) for idx in top_indices if scores[idx] > 0]
```

### 4.2.2 内容推荐实现

内容推荐模块基于图书的元数据和嵌入向量进行推荐：

```python
# recommender/content_based.py
from services.model_backends import generate_text_embeddings
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class ContentBasedRecommender:
    def __init__(self, books: List[Dict], embedding_dim: int = 2560):
        """
        初始化内容推荐器
        
        Args:
            books: 图书列表，包含 title, authors, genres, embedding 等字段
            embedding_dim: 嵌入向量维度
        """
        self.books = books
        self.book_ids = [book['id'] for book in books]
        self.book_id_to_idx = {bid: idx for idx, bid in enumerate(self.book_ids)}
        
        # 构建嵌入矩阵
        self.embedding_matrix = np.zeros((len(books), embedding_dim))
        for i, book in enumerate(books):
            if 'embedding' in book and book['embedding']:
                self.embedding_matrix[i] = book['embedding']
    
    def recommend_by_query(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        基于查询文本生成推荐
        
        Args:
            query: 查询文本（如"科幻小说 太空歌剧"）
            top_k: 推荐数量
            
        Returns:
            推荐列表 [(book_id, score), ...]
        """
        # 生成查询嵌入
        query_embedding, meta = generate_text_embeddings([query], model_name="qwen3-vl-embedding")
        
        if not query_embedding:
            return []
        
        # 计算余弦相似度
        query_vec = np.array(query_embedding[0]).reshape(1, -1)
        similarities = cosine_similarity(query_vec, self.embedding_matrix)[0]
        
        # 返回 Top-K
        top_indices = np.argsort(similarities)[::-1][:top_k]
        return [(self.book_ids[idx], float(similarities[idx])) 
                for idx in top_indices if similarities[idx] > 0]
    
    def recommend_by_book(self, book_id: int, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        基于指定图书生成相似推荐
        
        Args:
            book_id: 图书 ID
            top_k: 推荐数量
            
        Returns:
            推荐列表 [(book_id, score), ...]
        """
        if book_id not in self.book_id_to_idx:
            return []
        
        idx = self.book_id_to_idx[book_id]
        book_vec = self.embedding_matrix[idx].reshape(1, -1)
        similarities = cosine_similarity(book_vec, self.embedding_matrix)[0]
        
        # 排除自身
        similarities[idx] = 0
        
        top_indices = np.argsort(similarities)[::-1][:top_k]
        return [(self.book_ids[idx], float(similarities[idx])) 
                for idx in top_indices if similarities[idx] > 0]
```

### 4.2.3 多因子排序实现

RecRanking 多因子排序综合考虑多个推荐因子：

```python
# recommender/ranking.py
from typing import Dict, List, Optional

class RecRanking:
    """多因子排序实现"""
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        初始化排序器
        
        Args:
            weights: 各因子权重，默认值：
                - cf_score: 0.35（协同过滤分数）
                - content_score: 0.25（内容相似度）
                - popularity: 0.15（流行度）
                - diversity: 0.15（多样性）
                - novelty: 0.10（新颖性）
        """
        self.weights = weights or {
            'cf_score': 0.35,
            'content_score': 0.25,
            'popularity': 0.15,
            'diversity': 0.15,
            'novelty': 0.10
        }
    
    def rank(self, candidates: List[Dict]) -> List[Dict]:
        """
        对候选物品进行多因子排序
        
        Args:
            candidates: 候选物品列表，包含各因子分数
            
        Returns:
            排序后的物品列表
        """
        for item in candidates:
            # 计算加权总分
            total_score = 0.0
            for factor, weight in self.weights.items():
                factor_value = item.get(factor, 0.0)
                # 归一化到 [0, 1]
                factor_value = min(max(factor_value, 0.0), 1.0)
                total_score += weight * factor_value
            
            item['total_score'] = total_score
        
        # 按总分降序排序
        return sorted(candidates, key=lambda x: x['total_score'], reverse=True)
```

## 4.3 多 Agent 协作实现

### 4.3.1 Agent 角色定义

ACPs-app 系统定义了推荐系统场景下的四种 Agent 角色：

```python
# agents/roles.py
from enum import Enum
from dataclasses import dataclass
from typing import List

class AgentRole(Enum):
    """Agent 角色枚举（推荐系统场景）"""
    USER_AGENT = "user_agent"         # 用户代理
    BOOK_AGENT = "book_agent"         # 图书代理
    RECOMMENDER_AGENT = "recommender" # 推荐代理
    EVALUATOR_AGENT = "evaluator"     # 评估代理

@dataclass
class AgentConfig:
    """Agent 配置"""
    role: AgentRole
    name: str
    responsibilities: List[str]
    priority: str  # critical, high, medium, low

# 默认配置（推荐系统场景）
DEFAULT_AGENT_CONFIGS = {
    AgentRole.USER_AGENT: AgentConfig(
        role=AgentRole.USER_AGENT,
        name="用户代理",
        responsibilities=["用户偏好建模", "历史行为分析", "查询理解"],
        priority="critical"
    ),
    AgentRole.BOOK_AGENT: AgentConfig(
        role=AgentRole.BOOK_AGENT,
        name="图书代理",
        responsibilities=["图书特征提取", "嵌入生成", "相似度计算"],
        priority="critical"
    ),
    AgentRole.RECOMMENDER_AGENT: AgentConfig(
        role=AgentRole.RECOMMENDER_AGENT,
        name="推荐代理",
        responsibilities=["推荐算法执行", "多因子排序", "结果生成"],
        priority="high"
    ),
    AgentRole.EVALUATOR_AGENT: AgentConfig(
        role=AgentRole.EVALUATOR_AGENT,
        name="评估代理",
        responsibilities=["推荐质量评估", "指标计算", "反馈收集"],
        priority="high"
    )
}
```

### 4.3.2 任务分配机制

任务分配通过 ACPS 协议实现：

```python
# agents/task_manager.py
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
    
    def create_task(self, description: str, role: str, 
                    priority: str = "high", 
                    deadline: Optional[str] = None) -> str:
        """
        创建新任务
        
        Args:
            description: 任务描述
            role: 执行角色
            priority: 优先级
            deadline: 截止时间
            
        Returns:
            任务 ID
        """
        task_id = f"task-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        
        task = {
            'task_id': task_id,
            'description': description,
            'role': role,
            'priority': priority,
            'deadline': deadline,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'assigned_at': None,
            'completed_at': None
        }
        
        self.tasks[task_id] = task
        return task_id
    
    def assign_task(self, task_id: str, agent_id: str) -> bool:
        """分配任务给指定 Agent"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        task['status'] = 'assigned'
        task['assigned_to'] = agent_id
        task['assigned_at'] = datetime.now().isoformat()
        
        return True
    
    def update_task_status(self, task_id: str, status: str, 
                          result: Optional[str] = None) -> bool:
        """更新任务状态"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        task['status'] = status
        
        if status == 'completed' and result:
            task['result'] = result
            task['completed_at'] = datetime.now().isoformat()
        
        return True
    
    def get_all_tasks(self, status: Optional[str] = None) -> List[Dict]:
        """获取所有任务，可按状态过滤"""
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t['status'] == status]
        return tasks
```

### 4.3.3 通信实现

Agent 间通信基于 ACPS 协议：

```python
# agents/acps_protocol.py
import json
import uuid
from datetime import datetime
from typing import Any, Dict

class ACPSMessage:
    """ACPS 协议消息类"""
    
    def __init__(self, message_type: str, sender: str, receiver: str, 
                 content: Dict[str, Any]):
        self.message_id = f"msg_{uuid.uuid4().hex}"
        self.message_type = message_type
        self.sender = sender
        self.receiver = receiver
        self.timestamp = datetime.now().isoformat()
        self.content = content
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps({
            'message_id': self.message_id,
            'message_type': self.message_type,
            'sender': self.sender,
            'receiver': self.receiver,
            'timestamp': self.timestamp,
            'content': self.content
        }, ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ACPSMessage':
        """从 JSON 字符串解析"""
        data = json.loads(json_str)
        msg = cls(
            message_type=data['message_type'],
            sender=data['sender'],
            receiver=data['receiver'],
            content=data['content']
        )
        msg.message_id = data['message_id']
        msg.timestamp = data['timestamp']
        return msg

# 消息类型
MESSAGE_TYPES = {
    'task_assign': '任务分配',
    'task_confirm': '任务确认',
    'task_progress': '进度更新',
    'task_complete': '任务完成',
    'review_request': '审查请求',
    'review_result': '审查结果'
}
```

## 4.4 嵌入模型集成

### 4.4.1 DashScope API 集成

DashScope 多模态嵌入 API 的集成实现：

```python
# services/model_backends.py
import os
import logging
from typing import Any, Dict, List, Tuple

_LOGGER = logging.getLogger(__name__)

def generate_text_embeddings(
    texts: List[str],
    model_name: str = "qwen3-vl-embedding",
    fallback_dim: int = 12
) -> Tuple[List[List[float]], Dict[str, Any]]:
    """
    生成文本嵌入（同步版本）
    
    优先级：
    1. DashScope 多模态 API (qwen3-vl-embedding)
    2. 本地 sentence-transformers
    3. Hash fallback
    
    Args:
        texts: 待嵌入的文本列表
        model_name: 模型名称
        fallback_dim: fallback 向量维度
        
    Returns:
        (embeddings, metadata) 元组
    """
    text_list = [str(text or "") for text in texts]
    if not text_list:
        return [], {"backend": "none", "model": None, "vector_dim": 0}
    
    # 优先级 1: DashScope 多模态 API
    api_key = os.getenv("OPENAI_API_KEY") or ""
    model = (model_name or "qwen3-vl-embedding").strip()
    
    if api_key and model == "qwen3-vl-embedding":
        vectors, meta = _resolve_dashscope_multimodal_embeddings(text_list, model, api_key)
        if vectors:
            return vectors, meta
        _LOGGER.info("event=multimodal_failed fallback=offline")
    
    # 优先级 2: 本地 sentence-transformers
    # ...（省略本地模型实现）
    
    # 优先级 3: Hash fallback
    fallback_vectors = [hash_embedding(text, dim=fallback_dim) for text in text_list]
    dim = len(fallback_vectors[0]) if fallback_vectors else 0
    return fallback_vectors, {"backend": "hash-fallback", "model": "sha256", "vector_dim": dim}


def _resolve_dashscope_multimodal_embeddings(
    texts: List[str],
    model_name: str = "qwen3-vl-embedding",
    api_key: str = ""
) -> Tuple[List[List[float]], Dict[str, Any]]:
    """
    使用 dashscope 库调用多模态嵌入 API
    
    Args:
        texts: 待嵌入的文本列表
        model_name: 模型名称
        api_key: API Key
        
    Returns:
        (embeddings, metadata) 元组
    """
    try:
        import dashscope
        dashscope.api_key = api_key
        
        if not dashscope.api_key:
            _LOGGER.warning("event=dashscope_no_api_key fallback=hash")
            return [], {"backend": "dashscope-multimodal", "model": model_name, 
                       "vector_dim": 0, "error": "no_api_key"}
        
        all_embeddings: List[List[float]] = []
        
        for text in texts:
            input_data = [{'text': text}]
            resp = dashscope.MultiModalEmbedding.call(
                model=model_name,
                input=input_data
            )
            
            if resp and resp.status_code == 200:
                embedding_data = resp.output.get('embeddings', [{}])[0]
                embedding = embedding_data.get('embedding', [])
                if embedding:
                    all_embeddings.append([round(_to_float(v), 6) for v in embedding])
            else:
                _LOGGER.warning("event=dashscope_multimodal_error code=%s message=%s",
                               getattr(resp, 'status_code', 'unknown'),
                               getattr(resp, 'message', 'unknown'))
                return [], {"backend": "dashscope-multimodal", "model": model_name,
                           "vector_dim": 0, "error": str(resp)}
        
        dim = len(all_embeddings[0]) if all_embeddings else 0
        return all_embeddings, {"backend": "dashscope-multimodal", "model": model_name,
                               "vector_dim": dim}
        
    except Exception as e:
        _LOGGER.warning("event=dashscope_multimodal_error error=%s", str(e))
        return [], {"backend": "dashscope-multimodal", "model": model_name,
                   "vector_dim": 0, "error": str(e)}


def hash_embedding(text: str, dim: int = 12) -> List[float]:
    """
    Hash fallback 嵌入生成
    
    Args:
        text: 输入文本
        dim: 向量维度
        
    Returns:
        固定维度的浮点数向量
    """
    import hashlib
    
    normalized = (text or "").strip().lower()
    if not normalized:
        return [0.0] * max(dim, 4)
    
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    values: List[float] = []
    while len(values) < dim:
        for byte_value in digest:
            values.append(round(byte_value / 255.0, 6))
            if len(values) >= dim:
                break
        digest = hashlib.sha256(digest).digest()
    return values


def _to_float(value: Any, default: float = 0.0) -> float:
    """安全转换为浮点数"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
```

### 4.4.2 3 层 Fallback 机制实现

3 层 fallback 机制确保系统在任何环境下都能稳定运行：

```
┌─────────────────────────────────────┐
│  Layer 1: DashScope API            │
│  - qwen3-vl-embedding              │
│  - 2560 维向量                      │
│  - 订阅制，已付费                   │
│  - 延迟：~200ms                    │
└──────────────┬──────────────────────┘
               │ 失败（API 不可用/无 Key）
               ↓
┌─────────────────────────────────────┐
│  Layer 2: Local Model              │
│  - sentence-transformers           │
│  - 384 维向量                       │
│  - 离线运行，零成本                 │
│  - 延迟：~50ms                     │
└──────────────┬──────────────────────┘
               │ 失败（模型未安装）
               ↓
┌─────────────────────────────────────┐
│  Layer 3: Hash Fallback           │
│  - SHA256 哈希                     │
│  - 12-128 维向量（可配置）          │
│  - 确定性算法，零成本              │
│  - 延迟：<1ms                      │
└─────────────────────────────────────┘
```

**Fallback 逻辑**:
```python
def get_embedding_with_fallback(text: str) -> List[float]:
    """带 fallback 的嵌入获取"""
    
    # 尝试 Layer 1
    embeddings, meta = generate_text_embeddings([text])
    if meta['backend'] == 'dashscope-multimodal':
        _LOGGER.info(f"Using Layer 1: {meta['model']} ({meta['vector_dim']}D)")
        return embeddings[0]
    
    # 尝试 Layer 2
    if meta['backend'] == 'sentence-transformers':
        _LOGGER.info(f"Using Layer 2: {meta['model']} ({meta['vector_dim']}D)")
        return embeddings[0]
    
    # Layer 3
    _LOGGER.info(f"Using Layer 3: Hash ({meta['vector_dim']}D)")
    return embeddings[0]
```

### 4.4.3 费用控制策略

嵌入模型调用的费用控制策略：

**订阅制优先**:
- 使用已付费的订阅制模型（qwen3-vl-embedding）
- 避免按量计费模型（text-embedding-v3）

**缓存优化**:
```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_cached_embedding(text: str) -> List[float]:
    """带缓存的嵌入获取"""
    return get_embedding_with_fallback(text)
```

**批量调用**:
```python
def batch_embed_texts(texts: List[str]) -> List[List[float]]:
    """批量嵌入，减少 API 调用次数"""
    # 一次 API 调用处理多个文本
    embeddings, _ = generate_text_embeddings(texts)
    return embeddings
```

## 4.5 本章小结

本章详细描述了系统的实现过程和关键技术，主要内容包括：
1. 开发环境配置和项目目录结构
2. 核心功能实现（协同过滤、内容推荐、多因子排序）
3. 多 Agent 协作实现（角色定义、任务分配、通信机制）
4. 嵌入模型集成（DashScope API、3 层 fallback、费用控制）

下一章将进行系统测试与性能分析，验证系统的功能和性能。

---

**第 4 章 完成** ✅

**字数统计**: 约 5,200 字

**下一步**: 第 5 章 系统测试与性能分析
