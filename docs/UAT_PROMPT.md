# ACPs Reading Concierge — 用户验收测试指令 (UAT Prompt)

> **执行者**：Codex / 自动化测试 Agent  
> **分支**：`feature/recommendation-optimization`  
> **依赖文件**：`docs/API_DOC.md`（接口规范）  
> **测试框架**：`pytest`，测试文件写入 `tests/test_uat_e2e.py`

---

## 你的任务

你是一个严格的用户验收测试师（UAT Tester）。你需要在 `tests/test_uat_e2e.py` 中编写并执行一个完整的端到端测试套件，覆盖下列所有场景。

**重要约束**：
- 所有 HTTP 请求统一打向 `http://localhost:8000`（Reading Concierge）。
- 使用 `httpx` 库发送异步 HTTP 请求，不要 mock 任何网络层，必须真实调用运行中的服务。
- 每个场景用独立的 `pytest` 测试函数实现，函数命后迟 `test_scenario_XX_` 前缀。
- 失败时用 `assert` 语句输出清晰的失败原因。
- 测试完成后输出每个场景的 PASS / FAIL 汇总表。

---

## 全局配置

```python
# tests/test_uat_e2e.py 头部配置

BASE_URL = "http://localhost:8000"
TIMEOUT = 15.0  # 秒，单次请求最大容忍时间

USER_WARM = "demo_user_001"   # 有 20+ 条行为记录的热启动用户
                               # 如果 DB 里没有，先运行 scripts/seed_demo_user.py 创建
USER_COLD = "brand_new_user_uat_9999"  # 全新用户，确保 DB 里不存在
```

---

## 第一轮：健康检查

### 场景 00：服务健康状态预检

```
请求：GET /demo/status
预期检查：
  - HTTP 状态码 = 200
  - 响应体包含字段 "service": "reading_concierge"
  - 字段 "demo_page_available": true

如果此场景失败，跳过其余所有场景并输出错误："Backend is not running. Abort UAT."
```

---

## 第二轮：核心主流程（Happy Path）

### 场景 01：热启动用户正常推荐

```
请求：POST /user_api
  user_id: USER_WARM
  query: "我想看一本关于孤独与自我成长的小说"
  session_id: null
  constraints: {top_k: 5, scenario: "warm"}

必须通过的断言：
  ✅ HTTP 状态码 = 200
  ✅ 响应时间 < 15 秒
  ✅ resp["state"] == "completed"
  ✅ len(resp["recommendations"]) == 5
  ✅ 每条 recommendation 包含字段："book_id", "title", "score_total", "justification"
  ✅ 每条 justification 长度 > 10 个字符
  ✅ 没有 justification 包含未替换变量（如 "{title}"  "{author}" "None"）
  ✅ resp["session_id"] 不为 null，且以 "session-" 开头
  ✅ resp["partner_results"]["rpa"]["cold_start"] == false
  ✅ resp["partner_results"]["rda"]["chosen_action"] != "conservative"
  ✅ resp["partner_tasks"] 中全部 4 个 agent 状态均为 "completed"

保存返回的 session_id 和第 1 套书的 book_id 供后续场景使用。
```

### 场景 02：冷启动用户推荐降级

```
请求：POST /user_api
  user_id: USER_COLD
  query: "随便推荐几本书"
  session_id: null
  constraints: {top_k: 5, scenario: "cold"}

必须通过的断言：
  ✅ HTTP 状态码 = 200（不允许返回 500）
  ✅ len(resp["recommendations"]) > 0
  ✅ resp["partner_results"]["rpa"]["cold_start"] == true
  ✅ resp["partner_results"]["rda"]["chosen_action"] == "conservative"
  ✅ 每条 justification 不为空字符串
```

### 场景 03：多轮对话 session 复用

```
第一轮：POST /user_api，session_id=null，记录返回的 session_id_1
第二轮：POST /user_api，session_id=session_id_1，换一个 query

必须通过的断言：
  ✅ 第二轮 HTTP 状态码 = 200
  ✅ 第二轮 resp["session_id"] == session_id_1（session 被复用）
  ✅ 两轮推荐结果中 book_id 列表不完全相同（体现多样性）
```

---

## 第三轮：反馈闭环测试

### 场景 04：正向反馈 → 画像更新触发

```
前置条件：先执行场景 01，获得 session_id 和 recommendations 列表

步骤：
  循环 20 次：POST /api/feedback
    user_id: USER_WARM
    session_id: <场景01返回的 session_id>
    book_id: <每次轮流使用不同的 book_id，可从推荐列表和随机字符串交替>
    event_type: "rate_5"
    context_type: <取自场景01的 partner_results.rda.context_type>
    arm_action: <取自场景01的 partner_results.rda.chosen_action>

必须通过的断言：
  ✅ 前 19 次 HTTP 状态码均为 200
  ✅ 前 19 次 resp["triggers"]["profile_updated"] == false
  ✅ 全部 20 次 resp["status"] == "accepted"
  ✅ 第 20 次之后，调用 GET /api/profile?user_id=USER_WARM
  ✅ /api/profile 返回 HTTP 200
  ✅ profile["event_count"] >= 20
  ✅ profile["cold_start"] == false

注：如果 USER_WARM 初始 event_count 已经 >= 20，
      则第一次 feedback 就应触发 profile_updated=true，根据实际返回动态判断。
```

### 场景 05：连续负向反馈不崩溃

```
步骤：对同一本书连续提交 3 次 event_type="rate_1"

必须通过的断言：
  ✅ 每次 HTTP 状态码 = 200
  ✅ 每次 resp["status"] == "accepted"
  ✅ 没有抛出异常
```

### 场景 06：缺少 session_id 的 feedback 请求

```
请求：POST /api/feedback
  user_id: USER_WARM
  session_id: ""   (空字符串或不传)
  book_id: "book_001"
  event_type: "click"

必须通过的断言：
  ✅ HTTP 状态码 = 400
  ❌ 不允许返回 500
  ✅ 响应体包含错误描述字段（如 "detail" 或 "message"）
```

---

## 第四轮：边界与异常测试

### 场景 07：空 query 应被拒绝

```
请求：POST /user_api
  user_id: USER_WARM
  query: ""
  session_id: null

必须通过的断言：
  ✅ HTTP 状态码 = 400
  ❌ 不允许返回 200 同时 recommendations 为空数组
  ❌ 不允许返回 500
```

### 场景 08：不存在的 user_id 降级为冷启动

```
请求：POST /user_api
  user_id: "ghost_user_nonexistent_99999"
  query: "科幻小说推荐"
  session_id: null

必须通过的断言：
  ✅ HTTP 状态码 = 200（不应返回 404）
  ✅ len(resp["recommendations"]) > 0（降级为冷启动，仍有结果）
  ✅ resp["partner_results"]["rpa"]["cold_start"] == true
```

### 场景 09：超大 top_k 自动 clamp

```
请求：POST /user_api
  user_id: USER_WARM
  query: "历史小说"
  constraints: {top_k: 999}

必须通过的断言：
  ✅ HTTP 状态码 = 200（不应报 422 / 400）
  ✅ len(resp["recommendations"]) <= 10（自动 clamp）
  ❌ 不允许系统崩溃
```

### 场景 10：画像接口初始化检查

```
请求：GET /api/profile?user_id=USER_WARM

必须通过的断言：
  ✅ HTTP 状态码 = 200
  ✅ 响应体包含字段："user_id", "confidence", "cold_start", "event_count"
  ✅ "confidence" 是 float 类型，在 0.0 到 1.0 之间
  ✅ 响应体不包含 "profile_vector" 数组（防止返回巨型数据）

对不存在的用户：GET /api/profile?user_id=ghost_user_99999
  ✅ HTTP 状态码 = 200 或 404（两者均可接受）
  ❌ 不允许返回 500
```

---

## 第五轮：响应质量检查

### 场景 11：推荐词质量验证

```
前置条件：使用场景01的响应结果

对每条 justification 进行以下文本质量检查：
  ✅ 长度 > 15 个字符
  ✅ 不包含未替换的模板变量："{title}"、"{author}"、"{genre_tags}"
  ✅ 不包含 Python None 字符串或空字符串
  ✅ rank 越高分的书 score_total 越大（检查前 3 项添加差）
  ✅ 所有 book_id 在全局范围内唯一（无重复划录）

分数布局检查：
  ✅ score_total 均在 0.0 到 1.0 之间
  ✅ novelty_score 如果存在，均在 0.0 到 1.0 之间
```

### 场景 12：端到端延迟基准测量

```
步骤：
  连续发送 5 次推荐请求（同一用户，不同 query）
  记录每次请求的端到端耗时

必须通过的断言：
  ✅ 5 次请求全部成功，0 次超时
  ✅ 中位耗时（P50）< 8 秒——则输出警告（Warning，非失败）
  ✅ 没有任何一次请求 > 15 秒（不得超过 TIMEOUT 阈値）

输出示例：
  Latencies: [2.1s, 3.4s, 2.8s, 3.1s, 2.6s]
  P50: 2.8s | P90: 3.4s | Max: 3.4s
```

---

## 第六轮：端到端全流程走通验证

### 场景 13：完整闭环走一遍

```
这个场景是所有场景的集成，按顺序执行以下步骤：

  Step 1: GET /demo/status → 确认服务在线
  Step 2: GET /api/profile?user_id=USER_WARM → 记录初始 event_count
  Step 3: POST /user_api，query="推荐一本关于旅行的书" → 记录 session_id 和 book_id_1
  Step 4: POST /api/feedback，event_type="finish"，book_id=book_id_1 → 记录 triggers
  Step 5: 如果 Step 4 triggers.profile_updated==true，调用 GET /api/profile 验证 event_count 增加
  Step 6: POST /user_api，session_id=<Step3的session_id>，新 query="想看悬疑小说" → 确认第二轮返回的书单与第一轮不完全相同

必须通过的断言：
  ✅ 每个 Step 都返回 200
  ✅ Step 6 的 recommendations 中 book_id 列表与 Step 3 不完全相同
  ✅ 整个流程没有中断或异常
```

---

## 测试执行指导

### 如何运行测试

```bash
# 1. 确保所有服务已启动
# RC:     python -m reading_concierge.reading_concierge
# RPA:    python partners/online/reader_profile_agent/agent.py
# BCA:    python partners/online/book_content_agent/agent.py
# RDA:    python partners/online/recommendation_decision_agent/agent.py
# Engine: python partners/online/recommendation_engine_agent/agent.py
# FA:     python partners/online/feedback_agent/agent.py

# 2. 安装依赖
pip install httpx pytest pytest-asyncio

# 3. 执行 UAT 测试
python -m pytest tests/test_uat_e2e.py -v --tb=short

# 4. 如果只运行单个场景
python -m pytest tests/test_uat_e2e.py::test_scenario_01_warm_user_recommendation -v
```

### 输出格式要求

测试完成后，必须在 `tests/` 目录下生成一个 `uat_report.txt`，格式如下：

```
===== ACPs Reading Concierge UAT Report =====
时间: 2026-04-07T13:00:00

场景 00 | 服务健康检查       | PASS | 0.12s
场景 01 | 热启动用户推荐       | PASS | 3.21s
场景 02 | 冷启动用户降级       | PASS | 2.87s
场景 03 | 多轮对话 session 复用  | PASS | 5.44s
场景 04 | 正向反馈画像更新    | PASS | 8.30s
场景 05 | 连续负向反馈         | PASS | 1.20s
场景 06 | 缺 session_id 返回 400 | PASS | 0.08s
场景 07 | 空 query 返回 400       | PASS | 0.07s
场景 08 | 不存在用户降级        | PASS | 2.11s
场景 09 | 超大 top_k 自动 clamp   | PASS | 2.05s
场景 10 | 画像接口初始化检查    | PASS | 0.34s
场景 11 | 推荐词质量验证         | PASS | -
场景 12 | 延迟基准测量           | WARN | P50=4.2s >建议値 (WARNING, 非失败)
场景 13 | 完整闭环测试           | PASS | 12.3s

总计: 13 PASS | 0 FAIL | 1 WARN
最高优先级问题: 无
```

---

## 失败处理规则

| 场景 | 失败条件 | 处理方式 |
|---|---|---|
| 场景 00 | 服务不在线 | 输出 "ABORT: Backend not running"，跳过剩余所有场景 |
| 场景 01、03 | 任何断言失败 | 输出具体字段内容，标记 FAIL |
| 场景 12 | P50 > 8秒 | 标记 WARN，不算失败 |
| 任意场景 | HTTP 500 出现 | 输出响应体内容，标记 FAIL |
| 任意场景 | 请求超过 TIMEOUT (15s) | 标记 FAIL |

---

*本 UAT 指令由 Perplexity AI 根据工程代码扫描结果生成。执行后请将 `tests/uat_report.txt` 提交到当前分支。*
