# ACPs-app Agent 通信指南

**版本**: v2.0  
**最后更新**: 2026-03-11  
**维护者**: Code7 (Coordinator)

---

## 📋 目录

1. [概述](#概述)
2. [Agent 架构](#agent 架构)
3. [通信机制](#通信机制)
4. [消息格式](#消息格式)
5. [任务生命周期](#任务生命周期)
6. [实际示例](#实际示例)
7. [故障排查](#故障排查)

---

## 概述

### ACPs-app Agent 团队

ACPs-app 采用 **Leader-Partner 架构**，包含 4 个 Agent：

| Agent | 角色 | 端口 | 职责 |
|-------|------|------|------|
| **ReadingConcierge** | 👑 Leader | 8100 | 编排协调所有 Partner Agent |
| **ReaderProfile** | 🎯 Partner | 8211 | 读者画像分析 |
| **BookContent** | 📖 Partner | 8212 | 书籍内容分析 |
| **RecRanking** | 📊 Partner | 8213 | 推荐排序决策 |

### 通信特点

- ✅ **基于 AIP 协议** - Agent Interoperability Protocol
- ✅ **JSON-RPC 2.0** - 标准 RPC 通信协议
- ✅ **mTLS 安全** - 双向 SSL 认证（可选）
- ✅ **异步通信** - 支持并行调用
- ✅ **任务驱动** - 每个请求都有唯一的 Task ID

---

## Agent 架构

### Leader-Partner 模式

```
┌─────────────────────────────────────────────────────────┐
│                    User Query                           │
│              "推荐一些科幻小说"                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │  ReadingConcierge      │  ← Leader Agent
        │  (reading_concierge)   │     - 接收用户请求
        │  Port: 8100            │     - 协调 Partner Agent
        └──────────┬─────────────┘     - 汇总结果
                   │
         ┌─────────┼──────────┬──────────────┐
         │         │          │              │
         ▼         ▼          ▼              ▼
┌─────────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐
│ReaderProfile│ │BookContent│ │RecRanking│ │  其他   │  ← Partner Agents
│  Port: 8211 │ │ Port: 8212│ │Port: 8213│ │         │
│  画像分析   │ │ 内容分析  │ │ 排序决策  │ │         │
└─────────────┘ └──────────┘ └──────────┘ └─────────┘
```

### 通信流程

**典型推荐请求的通信流程**：

```
1. User → ReadingConcierge
   "推荐一些科幻小说"

2. ReadingConcierge → ReaderProfile (并行)
   - 分析用户阅读偏好
   - 生成偏好向量

3. ReadingConcierge → BookContent (并行)
   - 获取候选书籍向量
   - 提取书籍特征

4. ReadingConcierge → RecRanking
   - 输入：偏好向量 + 书籍向量
   - 输出：排序后的推荐列表

5. ReadingConcierge → User
   - 返回最终推荐结果
```

---

## 通信机制

### 1. RPC 端点配置

每个 Agent 都暴露一个 RPC 端点：

```python
# ReaderProfile Agent
READER_PROFILE_RPC_URL = "http://localhost:8211/reader-profile/rpc"

# BookContent Agent
BOOK_CONTENT_RPC_URL = "http://localhost:8212/book-content/rpc"

# RecRanking Agent
REC_RANKING_RPC_URL = "http://localhost:8213/rec-ranking/rpc"
```

**环境变量配置**（`.env` 文件）：

```bash
# Leader Agent 配置
READING_CONCIERGE_ID=reading_concierge_001
READING_CONCIERGE_BASE_URL=http://localhost:8100

# Partner Agent RPC 端点
READER_PROFILE_RPC_URL=http://localhost:8211/reader-profile/rpc
BOOK_CONTENT_RPC_URL=http://localhost:8212/book-content/rpc
REC_RANKING_RPC_URL=http://localhost:8213/rec-ranking/rpc

# mTLS 配置（可选）
AGENT_MTLS_ENABLED=true
AGENT_MTLS_CERT_DIR=/path/to/certs
```

### 2. AipRpcClient 使用

Leader Agent 使用 `AipRpcClient` 与 Partner 通信：

```python
from acps_aip.aip_rpc_client import AipRpcClient
from acps_aip.aip_base_model import Message, TaskCommand

# 初始化客户端
client = AipRpcClient(
    partner_url="http://localhost:8211/reader-profile/rpc",
    leader_id="reading_concierge_001"
)

# 启动任务
task = await client.start_task(
    session_id="session-123",
    user_input='{"history": [...], "query": "科幻"}'
)

# 继续任务（如果需要多轮对话）
task = await client.continue_task(
    task_id=task.id,
    session_id="session-123",
    user_input='{"additional_prefs": {...}}'
)

# 获取任务状态
task = await client.get_task(
    task_id=task.id,
    session_id="session-123"
)

# 完成任务
task = await client.complete_task(
    task_id=task.id,
    session_id="session-123"
)

# 关闭客户端
await client.close()
```

### 3. 并行调用示例

ReadingConcierge 并行调用多个 Partner：

```python
import asyncio

async def call_all_partners(user_input):
    # 创建多个客户端
    profile_client = AipRpcClient(
        partner_url=os.getenv("READER_PROFILE_RPC_URL"),
        leader_id=LEADER_ID
    )
    content_client = AipRpcClient(
        partner_url=os.getenv("BOOK_CONTENT_RPC_URL"),
        leader_id=LEADER_ID
    )
    ranking_client = AipRpcClient(
        partner_url=os.getenv("REC_RANKING_RPC_URL"),
        leader_id=LEADER_ID
    )
    
    try:
        # 并行调用
        profile_task, content_task = await asyncio.gather(
            profile_client.start_task(session_id, user_input),
            content_client.start_task(session_id, user_input)
        )
        
        # 使用结果调用 Ranking
        ranking_input = {
            "profile_vector": profile_task.products[0].data,
            "content_vectors": content_task.products[0].data
        }
        ranking_task = await ranking_client.start_task(
            session_id,
            json.dumps(ranking_input)
        )
        
        return ranking_task
        
    finally:
        # 关闭所有客户端
        await asyncio.gather(
            profile_client.close(),
            content_client.close(),
            ranking_client.close()
        )
```

---

## 消息格式

### AIP 消息结构

```python
from acps_aip.aip_base_model import Message, TextDataItem, TaskCommand
from datetime import datetime, timezone
import uuid

# 完整消息示例
message = Message(
    id=f"msg-{uuid.uuid4()}",                          # 唯一消息 ID
    sentAt=datetime.now(timezone.utc).isoformat(),     # 发送时间（UTC）
    senderRole="leader",                                # 发送者角色
    senderId="reading_concierge_001",                   # 发送者 ID
    command=TaskCommand.Start,                          # 命令类型
    taskId=f"task-{uuid.uuid4()}",                      # 任务 ID
    sessionId="session-123",                            # 会话 ID
    dataItems=[                                         # 数据项列表
        TextDataItem(text='{"query": "科幻", "top_k": 5}')
    ],
    commandParams={                                     # 可选命令参数
        "top_k": 5,
        "novelty_threshold": 0.45
    }
)
```

### 命令类型

| 命令 | 用途 | 方向 | 说明 |
|------|------|------|------|
| `Start` | 启动新任务 | Leader → Partner | 创建新任务 |
| `Continue` | 继续任务 | Leader → Partner | 多轮对话 |
| `Get` | 获取状态 | Leader → Partner | 查询任务进度 |
| `Complete` | 完成任务 | Leader → Partner | 标记任务完成 |
| `Cancel` | 取消任务 | Leader → Partner | 取消进行中任务 |

### 任务结构

```python
from acps_aip.aip_base_model import Task, TaskState, Product

task = Task(
    id="task-123",
    sessionId="session-123",
    status=TaskStatus(
        state=TaskState.Completed,  # 任务状态
        stateChangedAt=datetime.now(timezone.utc)
    ),
    messageHistory=[...],           # 消息历史
    statusHistory=[...],            # 状态历史
    products=[                      # 输出产品
        Product(
            id="product-123",
            name="reader-profile-analysis",
            description="读者偏好分析结果",
            dataItems=[
                StructuredDataItem(data={
                    "preference_vector": {...},
                    "sentiment_summary": {...}
                }),
                TextDataItem(text="Top genres: fiction, sci-fi")
            ]
        )
    ]
)
```

### 任务状态

```python
from acps_aip.aip_base_model import TaskState

# 任务状态流转
TaskState.Working        # 进行中
TaskState.Completed      # 已完成
TaskState.Failed         # 失败
TaskState.AwaitingInput  # 等待输入
TaskState.Canceled       # 已取消
TaskState.Rejected       # 已拒绝
```

---

## 任务生命周期

### 完整任务流程

```
┌─────────────┐
│   Start     │ ← Leader 发送 Start 命令
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Working   │ ← Partner 处理任务
└──────┬──────┘
       │
       ├──────────────┐
       │              │
       ▼              ▼
┌─────────────┐ ┌──────────────┐
│  Completed  │ │AwaitingInput │ ← 需要更多输入
└─────────────┘ └──────┬───────┘
                       │
                       │ Continue
                       ▼
                 ┌─────────────┐
                 │   Working   │
                 └──────┬──────┘
                        │
                        ▼
                  ┌─────────────┐
                  │  Completed  │
                  └─────────────┘
```

### 实际示例：读者画像分析

**步骤 1: Leader 发送 Start 命令**

```python
# ReadingConcierge → ReaderProfile
message = Message(
    id="msg-001",
    sentAt="2026-03-11T12:00:00Z",
    senderRole="leader",
    senderId="reading_concierge_001",
    command=TaskCommand.Start,
    taskId="task-profile-001",
    sessionId="session-123",
    dataItems=[
        TextDataItem(text=json.dumps({
            "user_profile": {"age": 25, "occupation": "engineer"},
            "history": [
                {"title": "三体", "rating": 5, "genres": ["科幻"]},
                {"title": "流浪地球", "rating": 4, "genres": ["科幻"]}
            ],
            "query": "推荐更多科幻小说"
        }))
    ]
)
```

**步骤 2: Partner 处理并响应**

```python
# ReaderProfile 内部处理
async def handle_start(message, existing_task):
    task = TaskManager.create_task(message, initial_state=TaskState.Working)
    
    # 解析输入
    payload = _parse_payload(message)
    
    # 分析偏好
    preference_vector = {
        "genres": {"科幻": 0.8, "历史": 0.2},
        "themes": {"太空": 0.6, "未来": 0.4},
        "difficulty": {"advanced": 0.7}
    }
    
    # 生成结果
    result = {
        "preference_vector": preference_vector,
        "sentiment_summary": {"label": "positive", "score": 0.8}
    }
    
    # 完成任务
    return _finalize_task(task.id, result)
```

**步骤 3: 返回完成状态**

```python
# ReaderProfile → ReadingConcierge
response = RpcResponse(
    id="msg-001",
    result=Task(
        id="task-profile-001",
        status=TaskStatus(state=TaskState.Completed),
        products=[
            Product(
                name="reader-profile-analysis",
                dataItems=[
                    StructuredDataItem(data=result)
                ]
            )
        ]
    )
)
```

---

## 实际示例

### 示例 1: 简单推荐请求

**用户输入**: "推荐一些科幻小说"

**通信序列**:

```python
# 1. User → ReadingConcierge
POST http://localhost:8100/user_api
{
  "session_id": "session-123",
  "query": "推荐一些科幻小说"
}

# 2. ReadingConcierge → ReaderProfile (并行)
POST http://localhost:8211/reader-profile/rpc
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "params": {
    "message": {
      "command": "Start",
      "taskId": "task-profile-001",
      "sessionId": "session-123",
      "dataItems": [{"text": "{\"query\": \"科幻\"}"}]
    }
  }
}

# 3. ReadingConcierge → BookContent (并行)
POST http://localhost:8212/book-content/rpc
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "params": {
    "message": {
      "command": "Start",
      "taskId": "task-content-001",
      "sessionId": "session-123",
      "dataItems": [{"text": "{\"query\": \"科幻\", \"top_k\": 30}"}]
    }
  }
}

# 4. ReadingConcierge → RecRanking
POST http://localhost:8213/rec-ranking/rpc
{
  "jsonrpc": "2.0",
  "id": "req-003",
  "params": {
    "message": {
      "command": "Start",
      "taskId": "task-ranking-001",
      "sessionId": "session-123",
      "dataItems": [{
        "text": "{\"profile_vector\": {...}, \"candidates\": [...]}"
      }]
    }
  }
}

# 5. ReadingConcierge → User
{
  "session_id": "session-123",
  "recommendations": [
    {"book_id": "1", "title": "三体", "score": 0.95},
    {"book_id": "2", "title": "流浪地球", "score": 0.88},
    {"book_id": "3", "title": "球状闪电", "score": 0.82}
  ]
}
```

### 示例 2: 多轮对话

**第一轮**:

```python
# User → ReadingConcierge
{
  "session_id": "session-123",
  "query": "我想看科幻书"
}

# ReadingConcierge → Partners
# ... (并行调用)

# ReadingConcierge → User
{
  "recommendations": [...],
  "follow_up_question": "您更喜欢硬科幻还是软科幻？"
}
```

**第二轮**:

```python
# User → ReadingConcierge
{
  "session_id": "session-123",
  "query": "硬科幻，类似三体"
}

# ReadingConcierge → Partners (Continue 命令)
{
  "command": "Continue",
  "taskId": "task-profile-001",  # 继续使用之前的任务
  "sessionId": "session-123",
  "dataItems": [{"text": "{\"preference\": \"硬科幻\"}"}]
}

# ReadingConcierge → User
{
  "recommendations": [
    {"title": "三体", "score": 0.98},
    {"title": "球状闪电", "score": 0.92}
  ]
}
```

---

## 故障排查

### 常见问题

#### 1. 连接失败

**错误**: `Connection refused`

**原因**: Partner Agent 未启动

**解决方案**:
```bash
# 检查端口
lsof -i :8211

# 启动 Partner
python -m agents.reader_profile_agent.profile_agent

# 查看日志
tail -f reading_concierge.log
```

#### 2. mTLS 认证失败

**错误**: `SSL: CERTIFICATE_VERIFY_FAILED`

**原因**: 证书配置错误

**解决方案**:
```bash
# 检查证书
ls -la /path/to/certs/

# 验证配置
echo $AGENT_MTLS_ENABLED
echo $AGENT_MTLS_CERT_DIR

# 重新生成证书
bash scripts/gen_dev_certs.sh
```

#### 3. 任务超时

**错误**: `TimeoutError`

**原因**: Partner 处理时间过长

**解决方案**:
```python
# 增加超时时间
client = AipRpcClient(
    partner_url=...,
    timeout=60.0  # 默认 30 秒
)
```

#### 4. 消息格式错误

**错误**: `ValidationError`

**原因**: 消息字段不符合规范

**解决方案**:
```python
# 验证消息
from acps_aip.aip_base_model import Message

try:
    message = Message(**data)
except ValidationError as e:
    print(f"验证失败：{e}")
```

---

### 日志分析

**启用详细日志**:

```bash
# .env 文件
READING_CONCIERGE_LOG_LEVEL=DEBUG
READER_PROFILE_LOG_LEVEL=DEBUG
BOOK_CONTENT_LOG_LEVEL=DEBUG
REC_RANKING_LOG_LEVEL=DEBUG
```

**查看日志**:

```bash
# 实时查看
tail -f reading_concierge.log | grep "event="

# 搜索错误
grep "ERROR" reading_concierge.log | tail -20

# 查看 RPC 调用
grep "rpc_call" reading_concierge.log
```

**典型日志输出**:

```
2026-03-11 12:00:00+0800 | INFO | agent.reading_concierge | event=rpc_call_start partner=reader_profile task_id=task-001
2026-03-11 12:00:01+0800 | INFO | agent.reading_concierge | event=rpc_call_success partner=reader_profile latency_ms=150
2026-03-11 12:00:02+0800 | INFO | agent.reading_concierge | event=ranking_complete items=5 avg_score=0.85
```

---

## 附录

### A. 端口汇总

| Agent | 端口 | 协议 | 用途 |
|-------|------|------|------|
| ReadingConcierge | 8100 | HTTP | Web Demo + User API |
| ReadingConcierge | 8100 | JSON-RPC | Leader RPC |
| ReaderProfile | 8211 | JSON-RPC | 画像分析 RPC |
| BookContent | 8212 | JSON-RPC | 内容分析 RPC |
| RecRanking | 8213 | JSON-RPC | 排序决策 RPC |

### B. 环境变量汇总

```bash
# Leader Agent
READING_CONCIERGE_ID=reading_concierge_001
READING_CONCIERGE_BASE_URL=http://localhost:8100
READING_PARTNER_MODE=auto  # auto, profile, content, ranking

# Partner RPC URLs
READER_PROFILE_RPC_URL=http://localhost:8211/reader-profile/rpc
BOOK_CONTENT_RPC_URL=http://localhost:8212/book-content/rpc
REC_RANKING_RPC_URL=http://localhost:8213/rec-ranking/rpc

# mTLS (可选)
AGENT_MTLS_ENABLED=true
AGENT_MTLS_CERT_DIR=/path/to/certs
```

### C. 相关文档

- [ACPS 协议详细说明](ACPS_PROTOCOL_DETAILED.md)
- [mTLS 配置指南](MTLS_SETUP.md)
- [故障排查手册](TROUBLESHOOTING.md)

---

**文档版本**: v2.0  
**最后更新**: 2026-03-11  
**维护者**: Code7 (Coordinator)
