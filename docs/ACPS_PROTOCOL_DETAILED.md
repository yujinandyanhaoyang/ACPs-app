# ACPS 协议详细说明

**版本**: v2.0  
**最后更新**: 2026-03-11  
**维护者**: Code7 (Coordinator)  
**协议版本**: AIP v1.0 (Agent Interoperability Protocol)

---

## 📋 目录

1. [协议概述](#协议概述)
2. [架构设计](#架构设计)
3. [消息格式详解](#消息格式详解)
4. [任务管理](#任务管理)
5. [RPC 通信](#rpc 通信)
6. [安全机制](#安全机制)
7. [错误处理](#错误处理)
8. [最佳实践](#最佳实践)

---

## 协议概述

### 什么是 ACPS？

**ACPS** (Agent Collaboration Protocol System) 是一个用于多 Agent 协作的标准化协议系统，基于 **AIP** (Agent Interoperability Protocol) 构建。

**设计目标**:
- ✅ **互操作性** - 不同 Agent 之间可以无缝通信
- ✅ **可扩展性** - 支持动态添加新 Agent
- ✅ **可靠性** - 完整的错误处理和重试机制
- ✅ **安全性** - 支持 mTLS 双向认证
- ✅ **可追溯性** - 完整的任务和消息历史

### 协议栈

```
┌─────────────────────────────────────┐
│         应用层 (Application)         │  ← Agent 业务逻辑
├─────────────────────────────────────┤
│         AIP (Agent Protocol)         │  ← 任务、消息、产品
├─────────────────────────────────────┤
│      JSON-RPC 2.0 (Transport)        │  ← RPC 通信协议
├─────────────────────────────────────┤
│         HTTP/HTTPS (Network)         │  ← 网络传输
├─────────────────────────────────────┤
│           TCP/IP (Link)              │  ← 物理连接
└─────────────────────────────────────┘
```

### 核心概念

| 概念 | 说明 | 示例 |
|------|------|------|
| **Agent** | 独立的智能体 | ReadingConcierge, ReaderProfile |
| **Leader** | 协调者 Agent | ReadingConcierge |
| **Partner** | 服务提供者 Agent | ReaderProfile, BookContent |
| **Task** | 工作单元 | 读者画像分析任务 |
| **Message** | 通信单元 | Start 命令消息 |
| **Product** | 输出产物 | 偏好向量、推荐列表 |
| **Session** | 会话上下文 | 用户的一次完整对话 |

---

## 架构设计

### Leader-Partner 架构

```
┌──────────────────────────────────────────────────┐
│                  User Interface                   │
│              (Web Demo / API Client)              │
└────────────────────┬─────────────────────────────┘
                     │ HTTP/REST
                     ▼
        ┌────────────────────────┐
        │   Leader Agent         │
        │   (ReadingConcierge)   │
        │   - 接收用户请求        │
        │   - 协调 Partner        │
        │   - 汇总结果            │
        └──────────┬─────────────┘
                   │ AIP over JSON-RPC
         ┌─────────┼──────────┬────────────┐
         │         │          │            │
         ▼         ▼          ▼            ▼
┌─────────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐
│ Partner 1   │ │ Partner 2│ │ Partner 3│ │ Partner │
│ (Profile)   │ │(Content) │ │(Ranking) │ │   ...   │
└─────────────┘ └──────────┘ └──────────┘ └─────────┘
```

### 组件职责

#### Leader Agent

**职责**:
- ✅ 接收用户请求
- ✅ 创建和管理 Task
- ✅ 协调 Partner Agent
- ✅ 汇总和格式化结果
- ✅ 管理会话状态

**实现位置**: `reading_concierge/reading_concierge.py`

#### Partner Agent

**职责**:
- ✅ 提供专业服务
- ✅ 处理 Leader 的 RPC 请求
- ✅ 执行特定任务
- ✅ 返回结构化结果

**实现位置**: `agents/*/agent.py`

#### TaskManager

**职责**:
- ✅ 创建任务
- ✅ 更新任务状态
- ✅ 管理消息历史
- ✅ 生成产品

**实现位置**: `acps_aip/aip_rpc_server.py`

---

## 消息格式详解

### Message 对象

```python
from acps_aip.aip_base_model import Message, TextDataItem, TaskCommand
from datetime import datetime, timezone

message = Message(
    # 必填字段
    id: str = "msg-uuid-123",                    # 唯一消息 ID
    sentAt: str = "2026-03-11T12:00:00Z",        # 发送时间（ISO 8601）
    senderRole: str = "leader",                  # 发送者角色：leader 或 partner
    senderId: str = "reading_concierge_001",     # 发送者 ID
    command: TaskCommand = TaskCommand.Start,    # 命令类型
    taskId: str = "task-uuid-123",               # 任务 ID
    sessionId: str = "session-123",              # 会话 ID
    
    # 可选字段
    dataItems: List[DataItem] = [...],           # 数据项列表
    commandParams: Dict = {...},                 # 命令参数
    correlationId: str = "corr-123"              # 关联 ID（用于追踪）
)
```

### DataItem 类型

#### TextDataItem

用于传输文本数据：

```python
from acps_aip.aip_base_model import TextDataItem

item = TextDataItem(
    text='{"query": "科幻", "top_k": 5}',  # JSON 字符串
    mimeType="application/json"              # 可选，默认 text/plain
)
```

#### StructuredDataItem

用于传输结构化数据：

```python
from acps_aip.aip_base_model import StructuredDataItem

item = StructuredDataItem(
    data={
        "preference_vector": {
            "genres": {"科幻": 0.8, "历史": 0.2},
            "themes": {"太空": 0.6}
        },
        "sentiment_summary": {
            "label": "positive",
            "score": 0.85
        }
    }
)
```

### TaskCommand 类型

```python
from enum import Enum

class TaskCommand(str, Enum):
    Start = "Start"          # 启动新任务
    Continue = "Continue"    # 继续任务（多轮对话）
    Get = "Get"              # 获取任务状态
    Complete = "Complete"    # 完成任务
    Cancel = "Cancel"        # 取消任务
```

### 命令详解

#### Start 命令

**用途**: 创建并启动新任务

**示例**:
```python
message = Message(
    command=TaskCommand.Start,
    taskId="task-new-001",  # 新任务 ID
    sessionId="session-123",
    dataItems=[
        TextDataItem(text='{"query": "推荐科幻小说"}')
    ]
)
```

**处理流程**:
1. Partner 检查 taskId 是否已存在
2. 如果不存在，创建新任务
3. 如果已存在，返回现有任务（幂等性）
4. 开始执行任务

#### Continue 命令

**用途**: 继续执行中的任务（多轮对话）

**示例**:
```python
message = Message(
    command=TaskCommand.Continue,
    taskId="task-existing-001",  # 已存在的任务 ID
    sessionId="session-123",
    dataItems=[
        TextDataItem(text='{"additional_pref": "硬科幻"}')
    ]
)
```

**处理流程**:
1. Partner 检查 taskId 是否存在
2. 如果不存在，返回错误
3. 如果存在，合并新输入
4. 继续执行任务

#### Get 命令

**用途**: 获取任务当前状态（增量同步）

**示例**:
```python
message = Message(
    command=TaskCommand.Get,
    taskId="task-001",
    sessionId="session-123",
    commandParams={
        "lastMessageSentAt": "2026-03-11T12:00:00Z",
        "lastStateChangedAt": "2026-03-11T12:00:00Z"
    }
)
```

**增量过滤**:
- 只返回 `lastMessageSentAt` 之后的消息
- 只返回 `lastStateChangedAt` 之后的状态变化

#### Complete 命令

**用途**: 标记任务为完成

**示例**:
```python
message = Message(
    command=TaskCommand.Complete,
    taskId="task-001",
    sessionId="session-123"
)
```

**处理流程**:
1. Partner 检查任务状态
2. 如果不是终端状态，标记为 Completed
3. 清理临时资源
4. 返回最终任务快照

#### Cancel 命令

**用途**: 取消任务

**示例**:
```python
message = Message(
    command=TaskCommand.Cancel,
    taskId="task-001",
    sessionId="session-123"
)
```

**幂等性**:
- 如果任务已完成/已取消，不执行任何操作
- 如果任务进行中，标记为 Canceled

---

## 任务管理

### Task 对象

```python
from acps_aip.aip_base_model import Task, TaskStatus, TaskState, Product

task = Task(
    # 基本信息
    id: str = "task-uuid-123",
    sessionId: str = "session-123",
    
    # 状态
    status: TaskStatus = TaskStatus(
        state: TaskState = TaskState.Working,
        stateChangedAt: str = "2026-03-11T12:00:00Z"
    ),
    
    # 历史
    messageHistory: List[Message] = [...],
    statusHistory: List[TaskStatus] = [...],
    
    # 输出
    products: List[Product] = [...]
)
```

### TaskState 流转

```
                 ┌─────────────┐
                 │   Working   │
                 └──────┬──────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌─────────────┐ ┌──────────────┐ ┌─────────────┐
│  Completed  │ │AwaitingInput │ │   Failed    │
└─────────────┘ └──────┬───────┘ └─────────────┘
                       │
                       │ Continue
                       ▼
                 ┌─────────────┐
                 │   Working   │
                 └─────────────┘
```

### 状态说明

| 状态 | 说明 | 可转移状态 |
|------|------|------------|
| `Working` | 任务进行中 | Completed, Failed, AwaitingInput, Canceled |
| `Completed` | 任务完成 | - (终端状态) |
| `Failed` | 任务失败 | - (终端状态) |
| `AwaitingInput` | 等待用户输入 | Working (通过 Continue) |
| `Canceled` | 任务已取消 | - (终端状态) |
| `Rejected` | 任务已拒绝 | - (终端状态) |

### Product 对象

**Product** 是任务的输出产物：

```python
from acps_aip.aip_base_model import Product, StructuredDataItem, TextDataItem

product = Product(
    id: str = "product-uuid-123",
    name: str = "reader-profile-analysis",
    description: str = "读者偏好分析结果",
    dataItems: List[DataItem] = [
        StructuredDataItem(data={
            "preference_vector": {...},
            "sentiment_summary": {...}
        }),
        TextDataItem(text="Top genres: fiction, sci-fi")
    ]
)
```

---

## RPC 通信

### JSON-RPC 2.0 格式

#### 请求格式

```json
{
  "jsonrpc": "2.0",
  "id": "req-uuid-123",
  "method": "aip.rpc",
  "params": {
    "message": {
      "id": "msg-uuid-123",
      "sentAt": "2026-03-11T12:00:00Z",
      "senderRole": "leader",
      "senderId": "reading_concierge_001",
      "command": "Start",
      "taskId": "task-uuid-123",
      "sessionId": "session-123",
      "dataItems": [
        {
          "type": "TextDataItem",
          "text": "{\"query\": \"科幻\"}"
        }
      ]
    }
  }
}
```

#### 响应格式（成功）

```json
{
  "jsonrpc": "2.0",
  "id": "req-uuid-123",
  "result": {
    "id": "task-uuid-123",
    "sessionId": "session-123",
    "status": {
      "state": "Working",
      "stateChangedAt": "2026-03-11T12:00:00Z"
    },
    "messageHistory": [...],
    "products": [...]
  }
}
```

#### 响应格式（错误）

```json
{
  "jsonrpc": "2.0",
  "id": "req-uuid-123",
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": {
      "details": "Missing required field: taskId"
    }
  }
}
```

### RPC 错误码

| 错误码 | 说明 |
|--------|------|
| `-32600` | Invalid Request - 请求格式错误 |
| `-32601` | Method Not Found - 方法不存在 |
| `-32602` | Invalid Params - 参数错误 |
| `-32603` | Internal Error - 内部错误 |
| `-32000` | Server Error - 服务器错误 |
| `-32001` | Task Not Found - 任务不存在 |
| `-32002` | Invalid State - 状态无效 |

### HTTP 端点

每个 Agent 暴露一个 RPC 端点：

```python
# ReaderProfile
POST http://localhost:8211/reader-profile/rpc

# BookContent
POST http://localhost:8212/book-content/rpc

# RecRanking
POST http://localhost:8213/rec-ranking/rpc
```

**请求头**:
```
Content-Type: application/json
```

**响应头**:
```
Content-Type: application/json
```

---

## 安全机制

### mTLS (双向 SSL 认证)

#### 证书结构

```
certs/
├── ca.crt                     # CA 根证书
├── ca.key                     # CA 私钥
├── reading_concierge.crt      # Leader 证书
├── reading_concierge.key      # Leader 私钥
├── reader_profile.crt         # Partner 1 证书
├── reader_profile.key         # Partner 1 私钥
├── book_content.crt           # Partner 2 证书
└── book_content.key           # Partner 2 私钥
```

#### 启用 mTLS

**服务端配置**:
```python
import uvicorn
from acps_aip.mtls_config import load_mtls_context

ssl_context = load_mtls_context(
    config_path="config.json",
    purpose="server",
    cert_dir="certs/"
)

uvicorn.run(
    "agent:app",
    host="0.0.0.0",
    port=8211,
    ssl_keyfile="certs/reader_profile.key",
    ssl_certfile="certs/reader_profile.crt",
    ssl_ca_certs="certs/ca.crt",
    ssl_cert_reqs=ssl.CERT_REQUIRED  # 强制客户端证书
)
```

**客户端配置**:
```python
import httpx
import ssl

# 创建 SSL 上下文
ssl_context = ssl.create_default_context(
    purpose=ssl.Purpose.SERVER_AUTH,
    cafile="certs/ca.crt"
)

# 加载客户端证书
ssl_context.load_cert_chain(
    certfile="certs/reading_concierge.crt",
    keyfile="certs/reading_concierge.key"
)

# 创建 HTTP 客户端
client = httpx.AsyncClient(verify=ssl_context)
```

#### 证书生成

```bash
# 生成 CA
openssl genrsa -out ca.key 2048
openssl req -new -x509 -days 365 -key ca.key -out ca.crt

# 生成服务端证书
openssl genrsa -out reader_profile.key 2048
openssl req -new -key reader_profile.key -out reader_profile.csr
openssl x509 -req -days 365 -in reader_profile.csr -CA ca.crt -CAkey ca.key -out reader_profile.crt

# 生成客户端证书
openssl genrsa -out reading_concierge.key 2048
openssl req -new -key reading_concierge.key -out reading_concierge.csr
openssl x509 -req -days 365 -in reading_concierge.csr -CA ca.crt -CAkey ca.key -out reading_concierge.crt
```

### 环境变量

```bash
# 启用 mTLS
AGENT_MTLS_ENABLED=true

# 证书目录
AGENT_MTLS_CERT_DIR=/path/to/certs

# 可选：自定义配置路径
READING_CONCIERGE_MTLS_CONFIG_PATH=/path/to/config.json
```

---

## 错误处理

### 错误类型

#### 1. 验证错误 (ValidationError)

**原因**: 消息格式不符合规范

**处理**:
```python
from pydantic import ValidationError

try:
    message = Message(**data)
except ValidationError as e:
    logger.error(f"消息验证失败：{e}")
    return create_error_response(-32602, str(e))
```

#### 2. 连接错误 (ConnectionError)

**原因**: Partner 不可达

**处理**:
```python
try:
    task = await client.start_task(session_id, user_input)
except httpx.ConnectError as e:
    logger.error(f"连接失败：{e}")
    # 重试逻辑
    for attempt in range(3):
        try:
            task = await client.start_task(session_id, user_input)
            break
        except Exception:
            if attempt == 2:
                raise
            await asyncio.sleep(1)
```

#### 3. 任务错误 (TaskError)

**原因**: 任务执行失败

**处理**:
```python
async def handle_start(message, existing_task):
    try:
        result = await _analyze_profile(payload)
        return _finalize_task(task.id, result)
    except Exception as exc:
        logger.exception(f"任务失败：{exc}")
        return _fail_task(task.id, f"analysis failed: {exc}")
```

### 错误响应格式

```json
{
  "jsonrpc": "2.0",
  "id": "req-123",
  "error": {
    "code": -32000,
    "message": "Server error",
    "data": {
      "error_type": "TaskExecutionError",
      "error_message": "analysis failed: connection timeout",
      "task_id": "task-123",
      "timestamp": "2026-03-11T12:00:00Z"
    }
  }
}
```

### 重试策略

```python
import asyncio
from functools import wraps

def retry(max_attempts=3, delay=1.0, backoff=2.0):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(f"重试 {attempt+1}/{max_attempts}: {e}")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator

@retry(max_attempts=3, delay=1.0)
async def call_partner(client, session_id, user_input):
    return await client.start_task(session_id, user_input)
```

---

## 最佳实践

### 1. 幂等性设计

**Start 命令幂等性**:
```python
async def handle_start(message, existing_task):
    if existing_task:
        # 任务已存在，返回现有任务（幂等）
        TaskManager.add_message_to_history(task.id, message)
        return existing_task
    
    # 创建新任务
    task = TaskManager.create_task(message)
    # ...
```

### 2. 超时控制

```python
# 设置合理的超时时间
client = AipRpcClient(
    partner_url="http://localhost:8211/reader-profile/rpc",
    timeout=30.0  # 30 秒超时
)

# 或者使用 asyncio.wait_for
try:
    task = await asyncio.wait_for(
        client.start_task(session_id, user_input),
        timeout=30.0
    )
except asyncio.TimeoutError:
    logger.error("RPC 调用超时")
```

### 3. 资源管理

```python
# 使用上下文管理器
async with AipRpcClient(partner_url, leader_id) as client:
    task = await client.start_task(session_id, user_input)
    # 自动关闭

# 或者手动关闭
client = AipRpcClient(partner_url, leader_id)
try:
    task = await client.start_task(session_id, user_input)
finally:
    await client.close()  # 确保关闭
```

### 4. 日志记录

```python
# 结构化日志
logger.info(
    "event=rpc_call_start "
    "partner=%s "
    "task_id=%s "
    "command=%s",
    partner_name,
    task_id,
    command
)

# 错误日志
logger.exception(
    "event=rpc_call_failed "
    "partner=%s "
    "error=%s",
    partner_name,
    str(e)
)
```

### 5. 性能优化

**并行调用**:
```python
# 使用 asyncio.gather 并行调用
profile_task, content_task = await asyncio.gather(
    profile_client.start_task(session_id, input),
    content_client.start_task(session_id, input),
    return_exceptions=True
)
```

**连接池**:
```python
# 复用 HTTP 客户端
class AgentPool:
    def __init__(self):
        self.clients = {}
    
    def get_client(self, partner_url):
        if partner_url not in self.clients:
            self.clients[partner_url] = AipRpcClient(partner_url, leader_id)
        return self.clients[partner_url]
    
    async def close_all(self):
        for client in self.clients.values():
            await client.close()
```

---

## 附录

### A. 完整示例

#### Leader Agent 调用示例

```python
from acps_aip.aip_rpc_client import AipRpcClient
from acps_aip.aip_base_model import TaskCommand, Message, TextDataItem
import asyncio
import json

async def recommend_books(user_query, user_history):
    # 初始化客户端
    profile_client = AipRpcClient(
        os.getenv("READER_PROFILE_RPC_URL"),
        "reading_concierge_001"
    )
    content_client = AipRpcClient(
        os.getenv("BOOK_CONTENT_RPC_URL"),
        "reading_concierge_001"
    )
    ranking_client = AipRpcClient(
        os.getenv("REC_RANKING_RPC_URL"),
        "reading_concierge_001"
    )
    
    session_id = f"session-{uuid.uuid4()}"
    
    try:
        # 1. 并行调用 Profile 和 Content
        profile_input = json.dumps({
            "history": user_history,
            "query": user_query
        })
        
        content_input = json.dumps({
            "query": user_query,
            "top_k": 30
        })
        
        profile_task, content_task = await asyncio.gather(
            profile_client.start_task(session_id, profile_input),
            content_client.start_task(session_id, content_input)
        )
        
        # 2. 提取结果
        profile_vector = profile_task.products[0].data["preference_vector"]
        candidates = content_task.products[0].data["candidates"]
        
        # 3. 调用 Ranking
        ranking_input = json.dumps({
            "profile_vector": profile_vector,
            "candidates": candidates,
            "top_k": 5
        })
        
        ranking_task = await ranking_client.start_task(
            session_id,
            ranking_input
        )
        
        # 4. 返回结果
        recommendations = ranking_task.products[0].data["ranking"]
        return recommendations
        
    finally:
        # 5. 关闭所有客户端
        await asyncio.gather(
            profile_client.close(),
            content_client.close(),
            ranking_client.close()
        )
```

### B. 相关文档

- [Agent 通信指南](AGENT_COMMUNICATION_GUIDE.md)
- [mTLS 配置指南](MTLS_SETUP.md)
- [故障排查手册](TROUBLESHOOTING.md)

### C. 参考资源

- JSON-RPC 2.0 规范：https://www.jsonrpc.org/specification
- AIP 协议源码：`/root/WORK/SCHOOL/ACPs-app/acps_aip/`
- 示例代码：`/root/WORK/SCHOOL/ACPs-app/agents/`

---

**文档版本**: v2.0  
**最后更新**: 2026-03-11  
**维护者**: Code7 (Coordinator)  
**协议版本**: AIP v1.0
