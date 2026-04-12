# ACPs Reading Concierge — 前后端接口文档 v1.0

> **适用分支**：`feature/recommendation-optimization`  
> **最后更新**：2026-04-06  
> **状态**：✅ 规范稿，以此为准进行前后端对齐改造

---

## 设计原则

- **UI 只传用户意图**：前端只负责传 `user_id`、`query`、`constraints`，所有历史行为、候选书目、画像向量均由后端自行从数据库 / 索引读取。
- **反馈走统一 Webhook**：所有用户行为事件统一经过 `POST /api/feedback` 进入 Feedback Agent，格式标准化。
- **画像独立可查**：前端可以主动拉取用户画像快照，不依赖每次推荐响应才能刷新画像展示。
- **会话复用**：`session_id` 由后端首次生成并返回，前端后续复用，支持多轮对话。

---

## 服务端口规划

| 服务 | 默认端口 | 对外暴露 | 说明 |
|---|---|---|---|
| Reading Concierge (RC) | 8000 | ✅ 唯一对外网关 | 前端所有请求统一打这里 |
| Reader Profile Agent (RPA) | 8211 | ❌ 内部 | RC 内部调用 |
| Book Content Agent (BCA) | 8212 | ❌ 内部 | RC 内部调用 |
| Recommendation Decision Agent (RDA) | 8213 | ❌ 内部 | RC 内部调用 |
| Recommendation Engine Agent (Engine) | 8214 | ❌ 内部 | RC 内部调用 |
| Feedback Agent (FA) | 8215 | ❌ 内部 | RC 转发 |

> 前端的 `API_BASE` 统一指向 RC（`http://localhost:8000`），所有接口均由 RC 路由和转发。

---

## 接口总览

| 方法 | 路径 | 调用方 | 说明 |
|---|---|---|---|
| `POST` | `/user_api` | Web Demo | 获取书籍推荐（主流程） |
| `GET` | `/api/profile` | Web Demo | 获取用户画像快照 |
| `POST` | `/api/feedback` | Web Demo | 提交用户行为反馈 |
| `GET` | `/demo/status` | Web Demo | 服务健康检查 |

---

## 接口详情

---

### 1. `POST /user_api` — 获取书籍推荐

**调用方**：Web Demo 点击"Get recommendations"  
**处理方**：Reading Concierge → RPA + BCA（并行）→ RDA → Engine

#### Request Body

```json
{
  "user_id": "demo_user_001",
  "query": "我想看节奏快的科幻悬疑，不要太硬核的理论",
  "session_id": null,
  "constraints": {
    "top_k": 5,
    "scenario": "warm"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `user_id` | string | ✅ | 用户唯一标识，不能为空 |
| `query` | string | ✅ | 自然语言查询，不能为空 |
| `session_id` | string \| null | ❌ | 首次传 `null`，后续复用后端返回的值 |
| `constraints.top_k` | int | ❌ | 返回推荐数量，默认 `5`，最大 `10` |
| `constraints.scenario` | string | ❌ | `cold` / `warm` / `explore`，影响召回与多样性策略 |

> ⛔ **已废弃、不再接收的字段**：`history`、`reviews`、`books`、`candidate_ids`、`user_profile`。  
> 后端需在 RC 的 Pydantic 模型里将这些字段标记为 `deprecated` 并忽略，以保持向后兼容。

#### Response Body

```json
{
  "session_id": "session-xxxxxxxx-xxxx",
  "user_id": "demo_user_001",
  "leader_id": "reading_concierge_001",
  "state": "completed",
  "intent": {
    "intent": "recommend_books",
    "preferred_genres": ["science_fiction", "suspense"],
    "scenario_hint": "fast_paced",
    "response_style": "concise",
    "constraints": {}
  },
  "recommendations": [
    {
      "rank": 1,
      "book_id": "book_001",
      "title": "The Andromeda Evolution",
      "genres": ["science_fiction", "suspense"],
      "score_total": 0.87,
      "novelty_score": 0.62,
      "diversity_score": 0.55,
      "recall_source": "ann",
      "score_parts": {
        "content": 0.45,
        "cf": 0.28,
        "novelty": 0.14
      },
      "justification": "该书节奏紧凑，融合了科幻与悬疑元素，与你近期阅读偏好高度吻合。"
    }
  ],
  "explanations": [
    {
      "book_id": "book_001",
      "justification": "该书节奏紧凑，融合了科幻与悬疑元素，与你近期阅读偏好高度吻合。",
      "evidence_types": ["semantic_match", "cf_signal"]
    }
  ],
  "partner_tasks": {
    "rpa": { "state": "completed", "route": "local" },
    "bca": { "state": "completed", "route": "local" },
    "rda": { "state": "completed", "route": "local" },
    "engine": { "state": "completed", "route": "local" }
  },
  "partner_results": {
    "rpa": {
      "confidence": 0.74,
      "behavior_genres": ["science_fiction", "thriller"],
      "strategy_suggestion": "exploit",
      "cold_start": false,
      "event_count": 42
    },
    "rda": {
      "strategy": "profile_dominant",
      "context_type": "high_conf_low_div",
      "chosen_action": "profile_dominant",
      "final_weights": {
        "ann_weight": 0.7,
        "cf_weight": 0.3
      },
      "score_weights": {
        "content": 0.45,
        "cf": 0.35,
        "novelty": 0.10,
        "recency": 0.10
      },
      "mmr_lambda": 0.35,
      "converged": true
    }
  }
}
```

| 字段 | 说明 |
|---|---|
| `session_id` | 本次会话 ID，前端必须存下来供后续请求和 feedback 复用 |
| `state` | `completed` 有推荐结果；`needs_input` 无法生成结果 |
| `recommendations[].justification` | LLM 生成的推荐理由，直接在卡片上展示 |
| `partner_results.rpa` | 画像摘要，供前端 Profile 面板展示 |
| `partner_results.rda.context_type` | 供 feedback 请求原样回传 |
| `partner_results.rda.chosen_action` | 供 feedback 请求原样回传 |

---

### 2. `GET /api/profile` — 获取用户画像快照

**调用方**：Web Demo "Load profile" / "Refresh profile" 按钮，以及 feedback 触发画像更新后自动刷新  
**处理方**：RC 内部调用 RPA 的 `uma.build_profile`，返回最新画像摘要

> ⚠️ **当前状态**：RC 尚未实现此路由，需要新增。

#### Request

```
GET /api/profile?user_id=demo_user_001
```

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `user_id` | string | ✅ | 查询目标用户 |

#### Response Body

```json
{
  "user_id": "demo_user_001",
  "confidence": 0.74,
  "cold_start": false,
  "event_count": 42,
  "behavior_genres": ["science_fiction", "thriller", "history"],
  "strategy_suggestion": "exploit",
  "profile_vector_dim": 256,
  "model": {
    "lambda_decay": 0.05,
    "vector_dim": 256,
    "warm_threshold": 20
  }
}
```

> ℹ️ `profile_vector`（256 维浮点数组）**不返回给前端**，只返回维度数 `profile_vector_dim`，避免传输大体积无用数据。

---

### 3. `POST /api/feedback` — 提交用户行为反馈

**调用方**：Web Demo 推荐卡片上的反馈按钮（📖 👍 👀 😐 👎 ❌）  
**处理方**：RC 接收后转发给 Feedback Agent 的 `/feedback/webhook`，再将 `triggers` 返回给前端

> ⚠️ **当前状态**：  
> - RC 尚未实现此路由，需要新增；  
> - 原前端调用的是 `/api/feedback`，但参数格式与 FA 的 `BehaviorEvent` 不匹配，需同步修改前端。

#### Request Body

```json
{
  "user_id": "demo_user_001",
  "session_id": "session-xxxxxxxx-xxxx",
  "book_id": "book_001",
  "event_type": "rate_5",
  "context_type": "high_conf_low_div",
  "arm_action": "profile_dominant",
  "reward_override": null,
  "metadata": {
    "rank": 1,
    "query": "我想看节奏快的科幻悬疑"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `user_id` | string | ✅ | 用户标识 |
| `session_id` | string | ✅ | 从 `/user_api` 响应里拿到的 `session_id` |
| `book_id` | string | ✅ | 被反馈的书籍 ID |
| `event_type` | string | ✅ | 见下方映射表 |
| `context_type` | string | ❌ | 从上次推荐响应的 `partner_results.rda.context_type` 中取 |
| `arm_action` | string | ❌ | 从上次推荐响应的 `partner_results.rda.chosen_action` 中取 |
| `reward_override` | float \| null | ❌ | 如果传值，会覆盖 `event_type` 的默认 reward |
| `metadata` | object | ❌ | 附加信息，如排名、查询词 |

#### event_type 与前端按钮映射

| 前端按钮 | `event_type` | 默认 reward |
|---|---|---|
| 📖 读完了 | `finish` | `+1.0` |
| 👍 强烈推荐 | `rate_5` | `+1.0` |
| 👀 点击查看 | `click` | `+0.3` |
| 😐 一般 | `rate_3` | `+0.3` |
| 👎 跳过 | `skip` | `-0.5` |
| ❌ 不感兴趣 | `rate_1` | `-0.8` |

#### Response Body

```json
{
  "status": "accepted",
  "event_id": "evt-xxxxxxxx-xxxx",
  "counters": {
    "user_event_count": 21,
    "global_rating_count": 102
  },
  "triggers": {
    "profile_updated": false,
    "cf_retrain_triggered": false,
    "rda_reward_updated": true
  }
}
```

| 字段 | 说明 |
|---|---|
| `triggers.profile_updated` | `true` 时前端应立即调用 `GET /api/profile` 刷新画像面板 |
| `triggers.cf_retrain_triggered` | `true` 时前端可展示"模型正在更新"提示 |
| `triggers.rda_reward_updated` | `true` 时表示 UCB arm 已更新 |

---

### 4. `GET /demo/status` — 服务健康检查

**调用方**：Web Demo 页面加载时，用于顶部"Backend"状态 pill  
**处理方**：RC 直接响应，无需转发（已实现）

#### Request

```
GET /demo/status
```

#### Response Body

```json
{
  "service": "reading_concierge",
  "leader_id": "reading_concierge_001",
  "partner_mode": "auto",
  "redis_url": "redis://localhost:6379/0",
  "llm_model": "qwen3.5-122b-a10b",
  "demo_page_available": true
}
```

---

## 改造清单

### 后端（RC）需要新增的路由

| 路由 | 实现要点 |
|---|---|
| `GET /api/profile` | 调用 RPA `uma.build_profile(user_id)`，将 `profile_vector` 裁剪为维度数后返回 |
| `POST /api/feedback` | 将请求体转换为 `BehaviorEvent` 格式，调用 FA `/feedback/webhook`，提取 `triggers` 字段后回传 |

### 后端（FA）需要修改

- `_process_event` 返回值中新增 `triggers` 字段：

```python
return {
    "status": "accepted",
    "event": row,
    "counters": { ... },
    "informs": informs,
    "triggers": {
        "profile_updated": profile_update_triggered,   # bool
        "cf_retrain_triggered": cf_retrain_triggered,  # bool
        "rda_reward_updated": rda_informed,            # bool
    }
}
```

### 前端（web_demo/index.html）需要修改

#### 1. `buildPayload()` — 移除 `books` 等废弃字段

```javascript
// ❌ 修改前
function buildPayload() {
  return {
    user_id: state.userId,
    query: el('query').value.trim(),
    books: DEFAULT_BOOKS,          // 删除
    user_profile: { ... },         // 删除
    history: [ ... ],              // 删除
    constraints: { ... },
  };
}

// ✅ 修改后
function buildPayload() {
  return {
    user_id: state.userId,
    query: el('query').value.trim(),
    session_id: state.sessionId || null,
    constraints: {
      top_k: state.topK,
      scenario: state.scenario,
    },
  };
}
```

#### 2. `sendFeedback()` — 对齐 `/api/feedback` 接口格式

```javascript
// ✅ 修改后
function rewardToEventType(reward) {
  if (reward >= 1.0) return 'finish';
  if (reward >= 0.8) return 'rate_5';
  if (reward >= 0.3) return 'click';
  if (reward >= 0.1) return 'rate_3';
  if (reward >= -0.3) return 'skip';
  return 'rate_1';
}

async function sendFeedback(bookId, reward, rank) {
  const rda = state.latestResponse?.partner_results?.rda || {};
  const payload = {
    user_id: state.userId,
    session_id: state.sessionId,
    book_id: bookId,
    event_type: rewardToEventType(reward),
    context_type: rda.context_type || null,
    arm_action: rda.chosen_action || null,
    metadata: { rank, query: el('query').value.trim() },
  };

  try {
    const resp = await fetchJson(`${API_BASE}/api/feedback`, {
      method: 'POST',
      body: JSON.stringify(payload),
      timeout: 8000,
    });
    if (!resp.ok) throw new Error(`Feedback request failed: ${resp.status}`);
    const data = await resp.json();

    // 根据 triggers 决定后续动作
    if (data.triggers?.profile_updated) {
      await refreshProfile();
      showToast('用户画像已更新。', 'success');
    }
    if (data.triggers?.cf_retrain_triggered) {
      showToast('协同过滤模型正在后台重训。', 'warning');
    }
    applyFeedbackLocally(bookId, reward);
    showToast('反馈已提交。', 'success');
  } catch (err) {
    applyFeedbackLocally(bookId, reward);
    showToast('反馈已本地记录（服务不可用）。', 'warning');
  }
}
```

#### 3. `refreshProfile()` — 对齐 `GET /api/profile` 新响应格式

```javascript
// ✅ 修改后：按新的响应字段渲染画像面板
async function refreshProfile() {
  const userId = el('userId').value.trim() || state.userId;
  try {
    const resp = await fetchJson(
      `${API_BASE}/api/profile?user_id=${encodeURIComponent(userId)}`,
      { method: 'GET', timeout: 8000 }
    );
    if (!resp.ok) throw new Error(`Profile endpoint returned ${resp.status}`);
    const profile = await resp.json();
    // profile.profile_vector_dim 替代原来的 profile.profile_vector.length
    renderProfile(profile);
    showToast('画像已从服务端加载。', 'success');
  } catch (err) {
    const cached = loadCachedProfile(userId);
    if (cached) {
      renderProfile(cached);
      showToast('已加载本地缓存画像。', 'warning');
    } else {
      renderPlaceholderProfile();
    }
  }
}
```

---

## 交互时序

```
用户输入 query
      │
      ▼
POST /user_api ──────────────────────────────→ RC
                                                ├─ parallel ──→ RPA (DB 读行为 → 画像向量)
                                                │           ──→ BCA (书库读内容特征)
                                                ├─ RDA (UCB 仲裁 → 决定权重策略)
                                                └─ Engine (召回 → 排序 → LLM 解释)
      ◀── {session_id, recommendations, partner_results} ──────
      │
用户点击反馈按钮
      │
      ▼
POST /api/feedback ──→ RC ──→ FA /feedback/webhook
                                  ├─ 更新 Redis 事件计数
                                  ├─ (达阈值) inform RDA → 更新 UCB arm reward
                                  ├─ (达阈值) inform RPA → 画像增量更新
                                  └─ (达阈值) inform Engine → 触发 CF 重训
      ◀── {status, counters, triggers} ──────────────────────
      │
      │  若 triggers.profile_updated = true
      ▼
GET /api/profile ──→ RC ──→ RPA (读最新 DB 数据 → 返回画像摘要)
      ◀── {confidence, behavior_genres, strategy_suggestion, ...} ──
      │
      ▼
前端 Profile 面板实时更新
```

---

## 错误码规范

| HTTP 状态码 | 含义 | 前端处理建议 |
|---|---|---|
| `200` | 成功 | 正常渲染 |
| `400` | 请求参数错误（如 `user_id` 为空） | Toast 显示错误信息 |
| `404` | 用户不存在或画像为空 | 降级展示 Cold Start 占位画像 |
| `500` | 后端内部错误 | Toast 错误提示，Pipeline Trace 标记 Error |
| `503` | 某个内部 Agent 不可用 | Toast 警告，尝试降级（如跳过 BCA） |
| 网络超时 | — | 降级为 localStorage 缓存或本地 Demo 模式 |

---

*文档由 Perplexity AI 根据代码扫描结果自动生成，如有字段变更请同步更新此文档。*
