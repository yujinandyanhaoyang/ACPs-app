# 第 2 章 相关技术与理论基础

## 2.1 推荐系统基础

### 2.1.1 协同过滤算法

协同过滤（Collaborative Filtering, CF）是推荐系统中最经典、应用最广泛的算法之一。其核心思想是：具有相似历史行为的用户在未来也可能有相似的偏好；被相似用户喜欢的物品也可能相互相似。

**User-based 协同过滤**

User-based CF 通过计算用户之间的相似度，找到与目标用户相似的用户群体，然后推荐这些相似用户喜欢但目标用户尚未接触的物品。用户相似度通常采用余弦相似度或皮尔逊相关系数计算：

$$
sim(u, v) = \frac{\sum_{i \in I_{uv}} (r_{ui} - \bar{r}_u)(r_{vi} - \bar{r}_v)}{\sqrt{\sum_{i \in I_{uv}} (r_{ui} - \bar{r}_u)^2} \sqrt{\sum_{i \in I_{uv}} (r_{vi} - \bar{r}_v)^2}}
$$

其中，$I_{uv}$ 表示用户 $u$ 和用户 $v$ 共同评分过的物品集合，$r_{ui}$ 表示用户 $u$ 对物品 $i$ 的评分，$\bar{r}_u$ 表示用户 $u$ 的平均评分。

**Item-based 协同过滤**

Item-based CF 通过计算物品之间的相似度，推荐与用户历史喜欢物品相似的其他物品。物品相似度计算与用户相似度类似，但基于物品 - 用户矩阵的列向量。

Item-based CF 的优势在于物品相似度相对稳定，可以预先计算并缓存，适合物品数量远小于用户数量的场景。

**矩阵分解方法**

矩阵分解（Matrix Factorization）将用户 - 物品评分矩阵分解为两个低维矩阵的乘积，分别表示用户隐因子矩阵和物品隐因子矩阵：

$$
R \approx U \times V^T
$$

其中，$R$ 是 $m \times n$ 的评分矩阵，$U$ 是 $m \times k$ 的用户隐因子矩阵，$V$ 是 $n \times k$ 的物品隐因子矩阵，$k$ 是隐因子维度。

SVD++ 是矩阵分解的经典算法，在 Netflix Prize 竞赛中取得了优异成绩。其目标函数为：

$$
\min_{U,V} \sum_{(u,i) \in K} (r_{ui} - \mu - b_u - b_i - u_u^T v_i)^2 + \lambda(||U||^2 + ||V||^2)
$$

其中，$\mu$ 是全局平均评分，$b_u$ 和 $b_i$ 分别是用户和物品的偏置项，$\lambda$ 是正则化参数。

### 2.1.2 内容推荐算法

内容推荐（Content-based Recommendation）通过分析物品的内容特征和用户的历史偏好，推荐与用户历史喜欢物品内容相似的其他物品。

**特征提取**

对于图书推荐场景，物品的内容特征包括：
- 元数据：书名、作者、出版社、出版年份
- 分类信息： genres、主题、标签
- 文本内容：简介、目录、章节摘要
- 嵌入向量：通过嵌入模型生成的语义表示

**相似度计算**

内容推荐的核心是计算物品之间的内容相似度。常用方法包括：
- 余弦相似度：适用于向量表示的特征
- Jaccard 相似度：适用于集合表示的特征（如标签）
- TF-IDF：适用于文本特征

**用户画像构建**

内容推荐需要构建用户画像，表示用户的兴趣偏好。用户画像可以表示为特征权重的向量：

$$
Profile(u) = \{w_{u1}, w_{u2}, ..., w_{un}\}
$$

其中，$w_{ui}$ 表示用户 $u$ 对特征 $i$ 的偏好权重，可以通过用户历史行为的加权平均计算。

### 2.1.3 混合推荐策略

混合推荐（Hybrid Recommendation）结合多种推荐算法的优势，以获得更好的推荐效果。常见的混合策略包括：

**加权融合**

将不同推荐算法的预测结果按权重融合：

$$
score_{final}(u, i) = \alpha \cdot score_{CF}(u, i) + (1 - \alpha) \cdot score_{CB}(u, i)
$$

其中，$\alpha$ 是融合权重，可以通过交叉验证优化。

**切换策略**

根据场景动态选择推荐算法：
- 冷启动场景：使用内容推荐（不依赖历史行为）
- 温启动场景：使用协同过滤（有足够历史数据）
- 探索场景：使用多样性优先的策略

**特征增强**

将一种算法的输出作为另一种算法的输入特征。例如，将协同过滤的隐因子作为内容推荐模型的输入特征。

### 2.1.4 推荐系统评估指标

推荐系统的评估指标分为准确性指标和多样性指标两大类。

**准确性指标**

- **Precision@K**: 推荐列表中相关物品的比例
  $$
  Precision@K = \frac{|R(u) \cap T(u)|}{|R(u)|}
  $$
  其中，$R(u)$ 是推荐给用户的 K 个物品，$T(u)$ 是用户实际喜欢的物品。

- **Recall@K**: 用户实际喜欢的物品中被推荐的比例
  $$
  Recall@K = \frac{|R(u) \cap T(u)|}{|T(u)|}
  $$

- **NDCG@K** (Normalized Discounted Cumulative Gain): 考虑排名位置的准确性指标
  $$
  NDCG@K = \frac{DCG@K}{IDCG@K} = \frac{\sum_{i=1}^{K} \frac{rel_i}{\log_2(i+1)}}{IDCG@K}
  $$
  其中，$rel_i$ 是第 $i$ 个推荐物品的相关性得分，$IDCG@K$ 是理想排序下的 DCG 值。

**多样性指标**

- **Diversity**: 推荐列表中物品之间的差异性
  $$
  Diversity@K = 1 - \frac{\sum_{i,j \in R(u)} sim(i, j)}{K(K-1)/2}
  $$

- **Novelty**: 推荐物品的意外程度，通常用物品的流行度倒数衡量
  $$
  Novelty@K = -\frac{1}{K} \sum_{i \in R(u)} \log_2 P(i)
  $$
  其中，$P(i)$ 是物品 $i$ 的流行度（被用户交互的概率）。

- **Coverage**: 推荐系统能够推荐的物品占总物品库的比例
  $$
  Coverage = \frac{|\bigcup_{u} R(u)|}{|I|}
  $$
  其中，$I$ 是物品全集。

## 2.2 多 Agent 协作系统

### 2.2.1 Agent 基本概念与特性

Agent 是能够感知环境、自主决策并执行行动的計算实体。根据 Wooldridge 和 Jennings（1995）的定义，Agent 具有以下核心特性：

1. **自主性（Autonomy）**: Agent 能够在没有人类或其他 Agent 直接干预的情况下自主决策和行动
2. **社会性（Social Ability）**: Agent 能够通过通信语言与其他 Agent 或人类进行交互
3. **反应性（Reactivity）**: Agent 能够感知环境变化并及时做出响应
4. **主动性（Pro-activeness）**: Agent 能够主动采取行动以实现目标，而非仅对环境做出被动响应

**Agent 的分类**

根据功能和应用场景，Agent 可以分为：
- **反应式 Agent**: 基于条件 - 行动规则进行决策
- **认知式 Agent**: 具有内部状态和推理能力
- **混合式 Agent**: 结合反应式和认知式的优势
- **LLM Agent**: 基于大语言模型的智能 Agent，具有自然语言理解和推理能力

### 2.2.2 多 Agent 系统架构

多 Agent 系统（Multi-Agent System, MAS）由多个相互作用的 Agent 组成，通过协作或竞争实现复杂目标。MAS 的架构设计决定了 Agent 之间的组织方式和交互模式。

**集中式架构**

存在一个中央协调器（Coordinator），负责任务分配、资源调度、冲突解决等。优点是协调效率高，缺点是存在单点故障风险。

**分布式架构**

Agent 之间平等协作，通过协商达成共识。优点是鲁棒性强，缺点是协调成本高，可能出现死锁或活锁。

**混合架构**

结合集中式和分布式的优势，部分决策由协调器集中处理，部分决策由 Agent 分布式执行。本研究采用的 VennCLAW 系统即属于混合架构。

### 2.2.3 Agent 通信语言与协议

Agent 之间的有效协作依赖于标准化的通信语言和协议。

**FIPA ACL**

FIPA（Foundation for Intelligent Physical Agents）定义的 Agent 通信语言（Agent Communication Language, ACL）是经典的标准：

```
(request
  :sender agent-1
  :receiver agent-2
  :content (action book-search)
  :ontology book-ontology
  :protocol fipa-request-protocol
)
```

ACL 消息包含发送者、接收者、内容、本体、协议等字段，支持请求、告知、确认等多种言语行为。

**ACPS 协议**

本研究设计的 ACPS（Agent Collaboration and Protocol System）协议是面向推荐系统场景的轻量级协作协议，具有以下特点：
- 基于 JSON 的消息格式，易于解析和扩展
- 支持 mTLS 双向认证，确保通信安全
- 定义四种标准角色：技术主管、Advisor、Coordinator、博士
- 支持任务拆解、分配、执行、审查的完整流程

ACPS 协议的详细设计将在第 3 章中阐述。

### 2.2.4 协作机制与任务分配

多 Agent 协作的核心是任务分配机制，即将复杂任务拆解为子任务并分配给合适的 Agent 执行。

**合同网协议**

合同网协议（Contract Net Protocol）是经典的任务分配机制：
1. 管理者发布任务公告
2. Agent 提交投标
3. 管理者选择最优投标者
4. 中标者执行任务并汇报结果

**基于角色的分配**

根据 Agent 的角色和能力进行任务分配。本研究的 ACPs-app 推荐系统采用此策略：
- **UserAgent**: 用户偏好建模、查询理解
- **BookAgent**: 图书特征提取、相似度计算
- **RecommenderAgent**: 推荐算法执行、结果生成
- **EvaluatorAgent**: 推荐质量评估、反馈收集

**LLM 驱动的动态分配**

利用 LLM 理解任务语义，自动选择最合适的 Agent 执行。这是当前研究的热点方向。

## 2.3 ACPS 协议

### 2.3.1 ACPS 协议设计原则

ACPS（Agent Collaboration and Protocol System）协议是本研究设计的多 Agent 协作协议，遵循以下设计原则：

1. **简洁性**: 消息格式基于 JSON，易于理解和实现
2. **可扩展性**: 支持自定义字段和消息类型
3. **安全性**: 支持 mTLS 双向认证和 API Key 验证
4. **可靠性**: 支持任务状态追踪和失败重试机制
5. **效率**: 最小化通信开销，支持批量操作

### 2.3.2 消息格式与通信流程

**消息格式**

ACPS 消息采用 JSON 格式，基本结构如下：

```json
{
  "message_id": "msg_xxx",
  "message_type": "task_assign",
  "sender": "tech_lead",
  "receiver": "coordinator",
  "timestamp": "2026-03-12T08:00:00Z",
  "content": {
    "task_id": "task_xxx",
    "description": "任务描述",
    "priority": "high",
    "deadline": "2026-03-13T24:00:00Z"
  },
  "metadata": {
    "project": "ACPs-app",
    "branch": "feat/xxx"
  }
}
```

**通信流程**

典型的任务分配与执行流程：
1. 技术主管 → Coordinator: 任务分配消息
2. Coordinator → 技术主管: 任务确认消息
3. Coordinator → 技术主管: 进度更新消息
4. Coordinator → 技术主管: 任务完成消息
5. 技术主管 → Advisor: 审查请求消息
6. Advisor → 技术主管: 审查结果消息

### 2.3.3 安全认证机制

ACPS 协议支持多层次的安全认证：

**mTLS 双向认证**

通信双方通过 TLS 证书相互验证身份，防止中间人攻击。

**API Key 验证**

每次请求携带 API Key，服务端验证 Key 的有效性。

**消息签名**

重要消息可附加数字签名，确保消息完整性和不可否认性。

## 2.4 嵌入模型技术

### 2.4.1 嵌入模型基础理论

嵌入（Embedding）是将离散对象映射到连续向量空间的技术，使得语义相似的对象在向量空间中距离更近。

**词嵌入**

Word2Vec（Mikolov 等人，2013）是经典的词嵌入模型，通过预测上下文（Skip-gram）或预测中心词（CBOW）学习词向量。

**句子嵌入**

Sentence-BERT（Reimers 和 Gurevych，2019）在 BERT 基础上添加池化层，生成固定长度的句子向量，适用于语义相似度计算。

**多模态嵌入**

多模态嵌入模型能够处理文本、图像、音频等多种模态的输入，生成统一的向量表示。DashScope 的 qwen3-vl-embedding 即属于此类。

### 2.4.2 DashScope 多模态嵌入 API

DashScope 是阿里云提供的 AI 服务平台，其多模态嵌入 API 支持以下功能：

**支持模型**
- qwen3-vl-embedding：多模态嵌入模型，支持文本和图像输入
- text-embedding-v3：纯文本嵌入模型（按量计费）

**API 调用方式**

```python
import dashscope

response = dashscope.MultiModalEmbedding.call(
    model="qwen3-vl-embedding",
    input=[{"text": "这本书很好看"}]
)
embedding = response.output["embeddings"][0]["embedding"]
```

**向量维度**: 2560 维  
**支持语言**: 中文、英文等  
**最大输入长度**: 根据模型而定

### 2.4.3 嵌入模型在推荐系统中的应用

嵌入模型在推荐系统中有着广泛应用：

**物品表示学习**

将物品的文本描述（书名、简介、标签等）通过嵌入模型转换为向量，用于：
- 内容推荐：计算物品之间的语义相似度
- 冷启动：新物品无需历史行为即可生成表示
- 跨域推荐：统一不同领域的物品表示

**用户表示学习**

将用户的历史行为、偏好描述等通过嵌入模型转换为用户向量，用于：
- 用户相似度计算
- 用户聚类分析
- 个性化推荐

**召回与排序**

- 召回阶段：使用嵌入向量进行近似最近邻搜索（ANN），快速筛选候选物品
- 排序阶段：将用户和物品向量拼接，输入排序模型进行精排

### 2.4.4 费用控制策略

嵌入模型的调用方式直接影响使用成本：

**云端 API（按量计费）**
- 优点：高质量、免维护
- 缺点：按 token 计费，大规模使用成本高
- 适用场景：小规模测试、关键任务

**订阅制 API**
- 优点：固定月费，成本可控
- 缺点：可能有调用限制
- 适用场景：持续开发、生产环境

**本地模型**
- 优点：一次性部署，无后续费用
- 缺点：需要计算资源，质量可能略低
- 适用场景：离线环境、成本敏感场景

**Fallback 机制**

本研究的 3 层 fallback 机制：
1. **优先**: DashScope qwen3-vl-embedding（订阅制，已付费）
2. **降级**: 本地 sentence-transformers（离线模型）
3. **保底**: Hash 嵌入（确定性算法，零成本）

这一设计确保系统在任何环境下都能稳定运行，同时控制成本。

## 2.5 本章小结

本章介绍了推荐系统、多 Agent 协作系统、ACPS 协议、嵌入模型等理论基础，为后续的系统设计与实现提供了理论支撑。

**核心要点**:
1. 推荐系统从协同过滤发展到深度学习，嵌入模型成为关键技术
2. 多 Agent 系统通过协作机制实现复杂任务，LLM 驱动的 Agent 是研究热点
3. ACPS 协议是面向推荐系统场景的轻量级协作协议
4. 嵌入模型的集成需要考虑费用控制，fallback 机制确保系统稳定性

下一章将基于这些理论基础，进行系统需求分析和架构设计。

---

**第 2 章 完成** ✅

**字数统计**: 约 4,200 字

**下一步**: 第 3 章 系统需求分析与架构设计
