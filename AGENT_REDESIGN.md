# AGENT_REDESIGN.md
# Personalized Book Recommendation System - ACPs-Compliant Multi-Agent Design

> Protocol Version: ACPs v2.0 (March 2026)
> Reference Spec: ACPsProtocolGuide.md
> Design Version: v1.0

---

## Overview

This document defines the ACPs-compliant multi-agent design for a personalized book recommendation system. The system decomposes recommendation into three specialized Partner Agents coordinated by one Leader Agent, and adopts the full ACPs protocol suite:

- AIC (Agent Identity Code)
- ACS (Agent Capability Description)
- ATR (Agent Trusted Registration)
- AIA (Agent Identity Authentication)
- ADP (Agent Discovery Protocol)
- AIP (Agent Interaction Protocol)
- DSP (Data Synchronization Protocol)

---

## 1. System Architecture

```text
┌───────────────────────────────────────────────────────────┐
│                        Client / UI                        │
└───────────────────────────┬───────────────────────────────┘
                            │ User Request
                            ▼
┌───────────────────────────────────────────────────────────┐
│            Leader Agent: Recommendation Orchestrator      │
│   (task parsing, subtask dispatch, result aggregation)    │
└───────┬──────────────────┬───────────────────┬────────────┘
        │ AIP Direct       │ AIP Direct        │ AIP Direct
        ▼                  ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────────┐
│ Partner A     │  │ Partner B     │  │ Partner C         │
│ User Profile  │  │ Book Content  │  │ Recommendation    │
│ Analyst Agent │  │ Analyst Agent │  │ Decision Agent    │
└───────────────┘  └───────────────┘  └───────────────────┘

         ↕ ADP (Discovery)   ↕ ATR (Registration)   ↕ DSP (Sync)
    ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
    │ Registry     │   │ CA Server    │   │ Discovery Server │
    │ Server :8001 │◀──│ :8003        │──▶│ :8005            │
    └──────────────┘   └──────────────┘   └──────────────────┘
```

Interaction mode: Direct Connection Mode (AIP). The task chain is fixed and sequential. Leader dispatches subtasks point-to-point to each Partner and aggregates final results.

---

## 2. Agent Identity Codes (AIC)

Each agent holds a globally unique AIC issued after ATR trusted registration at https://ioa.pub/registry-web/.

| Agent Role | AIC Placeholder | Port |
| --- | --- | --- |
| Recommendation Orchestrator (Leader) | `1.2.156.3088.1.BOOK.000001.L001.1.xxxx` | 8010 |
| User Profile Analyst (Partner A) | `1.2.156.3088.1.BOOK.000002.P001.1.xxxx` | 8011 |
| Book Content Analyst (Partner B) | `1.2.156.3088.1.BOOK.000003.P002.1.xxxx` | 8012 |
| Recommendation Decision (Partner C) | `1.2.156.3088.1.BOOK.000004.P003.1.xxxx` | 8013 |

Replace `xxxx` with real check-code segments issued by ATR registration.

---

## 3. ACS Capability Description Files

Every agent must expose a valid `acs.json`. Templates below define minimal production-ready ACS descriptors.

### 3.1 Leader Agent - Recommendation Orchestrator

```json
{
  "aic": "1.2.156.3088.1.BOOK.000001.L001.1.xxxx",
  "active": true,
  "lastModifiedTime": "2026-03-22T00:00:00+08:00",
  "protocolVersion": "01.00",
  "name": "Book Recommendation Orchestrator",
  "description": "Leader agent for personalized book recommendations. Receives user requests, decomposes tasks, dispatches subtasks to profile/content/ranking partners, and aggregates final explainable recommendations.",
  "version": "1.0.0",
  "provider": { "organization": "BookRec System", "url": "https://your-org.com" },
  "securitySchemes": {
    "mtls": { "type": "mutualTLS", "x-caChallengeBaseUrl": "http://your-ca-server:8004/acps-atr-v2" }
  },
  "endPoints": [
    { "url": "http://leader-host:8010/leader/rpc", "transport": "HTTP", "security": [{"mtls": []}] }
  ],
  "capabilities": { "streaming": false, "notification": false, "messageQueue": [] },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "orchestrator.recommend_books",
      "name": "Personalized Book Recommendation",
      "description": "Accepts user ID and optional preference hints; orchestrates profile analysis, content analysis, ranking, and explainable output.",
      "version": "1.0.0",
      "tags": ["book", "recommendation", "personalized", "orchestration"],
      "examples": [
        "Recommend books for user U001 who likes science fiction",
        "Give me 10 recommendations based on my reading history"
      ],
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"]
    }
  ]
}
```

### 3.2 Partner A - User Profile Analyst Agent

```json
{
  "aic": "1.2.156.3088.1.BOOK.000002.P001.1.xxxx",
  "active": true,
  "lastModifiedTime": "2026-03-22T00:00:00+08:00",
  "protocolVersion": "01.00",
  "name": "User Profile Analyst Agent",
  "description": "Analyzes user history and demographics to produce structured multi-dimensional user profile vectors. Does not perform ranking.",
  "version": "1.0.0",
  "provider": { "organization": "BookRec System", "url": "https://your-org.com" },
  "securitySchemes": {
    "mtls": { "type": "mutualTLS", "x-caChallengeBaseUrl": "http://your-ca-server:8004/acps-atr-v2" }
  },
  "endPoints": [
    { "url": "http://partner-a-host:8011/partners/user_profile_analyst/rpc", "transport": "HTTP", "security": [{"mtls": []}] }
  ],
  "capabilities": { "streaming": false, "notification": false, "messageQueue": [] },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "user_profile_analyst.build_user_profile",
      "name": "Build User Profile Vector",
      "description": "Extracts explicit and implicit reading preferences and returns structured UserProfileJSON.",
      "version": "1.0.0",
      "tags": ["user profile", "preference extraction", "NLP", "history"],
      "examples": [
        "Build profile for user U001 using ratings and reviews",
        "Analyze implicit preferences from review text"
      ],
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"]
    }
  ]
}
```

### 3.3 Partner B - Book Content Analyst Agent

```json
{
  "aic": "1.2.156.3088.1.BOOK.000003.P002.1.xxxx",
  "active": true,
  "lastModifiedTime": "2026-03-22T00:00:00+08:00",
  "protocolVersion": "01.00",
  "name": "Book Content Analyst Agent",
  "description": "Analyzes book metadata and review aggregates to produce semantic vectors, KG-enriched context, and multi-dimensional tags. Does not rank.",
  "version": "1.0.0",
  "provider": { "organization": "BookRec System", "url": "https://your-org.com" },
  "securitySchemes": {
    "mtls": { "type": "mutualTLS", "x-caChallengeBaseUrl": "http://your-ca-server:8004/acps-atr-v2" }
  },
  "endPoints": [
    { "url": "http://partner-b-host:8012/partners/book_content_analyst/rpc", "transport": "HTTP", "security": [{"mtls": []}] }
  ],
  "capabilities": { "streaming": false, "notification": false, "messageQueue": [] },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "book_content_analyst.analyze_books",
      "name": "Analyze Book Content Features",
      "description": "Generates semantic vectors, KG context, and labels (theme/style/difficulty/audience) for candidate books.",
      "version": "1.0.0",
      "tags": ["book analysis", "semantic vector", "knowledge graph", "tags"],
      "examples": [
        "Analyze features for candidate books B001-B500",
        "Extract theme and difficulty labels for sci-fi novels"
      ],
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"]
    }
  ]
}
```

### 3.4 Partner C - Recommendation Decision Agent

```json
{
  "aic": "1.2.156.3088.1.BOOK.000004.P003.1.xxxx",
  "active": true,
  "lastModifiedTime": "2026-03-22T00:00:00+08:00",
  "protocolVersion": "01.00",
  "name": "Recommendation Decision Agent",
  "description": "Fuses profile and book feature signals into a multi-factor recommendation score and returns ranked explainable output.",
  "version": "1.0.0",
  "provider": { "organization": "BookRec System", "url": "https://your-org.com" },
  "securitySchemes": {
    "mtls": { "type": "mutualTLS", "x-caChallengeBaseUrl": "http://your-ca-server:8004/acps-atr-v2" }
  },
  "endPoints": [
    { "url": "http://partner-c-host:8013/partners/recommendation_decision/rpc", "transport": "HTTP", "security": [{"mtls": []}] }
  ],
  "capabilities": { "streaming": false, "notification": false, "messageQueue": [] },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "recommendation_decision.rank_and_explain",
      "name": "Rank Books and Generate Explanations",
      "description": "Computes composite scores across collaborative/content/KG/diversity factors and returns ranked explainable recommendations.",
      "version": "1.0.0",
      "tags": ["ranking", "collaborative filtering", "explainability", "diversity"],
      "examples": [
        "Rank 500 candidates for user U001 and explain top 10",
        "Generate a diverse recommendation list for a mystery reader"
      ],
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"]
    }
  ]
}
```

---

## 4. Standard Directory Structure

```text
partners/online/
├── recommendation_orchestrator/
│   ├── acs.json
│   ├── config.toml
│   ├── prompts.toml
│   ├── leader_agent.py
│   └── certs/
│       ├── agent.crt
│       └── agent.key
├── user_profile_analyst/
│   ├── acs.json
│   ├── config.toml
│   ├── prompts.toml
│   ├── agent.py
│   └── certs/
├── book_content_analyst/
│   ├── acs.json
│   ├── config.toml
│   ├── prompts.toml
│   ├── agent.py
│   └── certs/
└── recommendation_decision/
    ├── acs.json
    ├── config.toml
    ├── prompts.toml
    ├── agent.py
    └── certs/
```

---

## 5. AIP Interaction Flow (Direct Connection Mode)

### 5.1 Task State Machine

```text
           Start
             │
        ┌────▼────┐
        │Accepted │
        └────┬────┘
             │
        ┌────▼────┐
        │ Working │
        └──┬──┬───┘
           │  │
    ┌──────▼┐ └──────────────────┐
    │Await  │                    │AwaitingCompletion
    │Input  │                    │(result ready, awaiting Leader confirm)
    └──┬────┘                    └──┬──────────────┐
       │(Continue)                  │(Complete cmd)
       └────────────────────┐       ▼
                         ┌──▼─────────────┐
                         │   Completed    │
                         └────────────────┘
Other terminal states: Failed | Canceled | Rejected
```

### 5.2 End-to-End Workflow

```text
User -> Leader (Orchestrator)
  -> Start Partner A (User Profile Analyst)
     -> Product: UserProfileJSON
  -> Start Partner B (Book Content Analyst)
     -> Product: BookFeatureMapJSON
  -> Start Partner C (Recommendation Decision)
     -> Product: RankedRecommendationListJSON
  -> Complete A/B/C
  -> Final response to user
```

### 5.3 Standard AIP Message Structures

Leader -> Partner (Start):

```python
TaskCommand(
    id=f"msg-{uuid4()}",
    sentAt=datetime.now(timezone.utc).isoformat(),
    senderRole="leader",
    senderId="1.2.156.3088.1.BOOK.000001.L001.1.xxxx",
    taskId=f"task-{uuid4()}",
    sessionId=f"session-{uuid4()}",
    command=TaskCommandType.Start,
    dataItems=[TextDataItem(text=json.dumps(payload))],
)
```

Partner -> Leader (AwaitingCompletion with Product):

```python
TaskResult(
    id=f"msg-{uuid4()}",
    sentAt=datetime.now(timezone.utc).isoformat(),
    senderRole="partner",
    senderId="<Partner AIC>",
    taskId=command.taskId,
    sessionId=command.sessionId,
    status=TaskStatus(
        state=TaskState.AwaitingCompletion,
        stateChangedAt=datetime.now(timezone.utc).isoformat(),
    ),
    products=[
        Product(
            id=f"prod-{uuid4()}",
            name="AgentProduct",
            dataItems=[TextDataItem(text=json.dumps(result_payload))],
        )
    ],
)
```

Leader -> Partner (Complete):

```python
TaskCommand(
    command=TaskCommandType.Complete,
    taskId=original_task_id,
    sessionId=original_session_id,
    dataItems=[],
)
```

---

## 6. Data Schemas

### 6.1 Input/Output Per Agent

| Agent | Input | Output (Product Payload) |
| :-- | :-- | :-- |
| Partner A - User Profile Analyst | `user_id`, `history[]`, `demographics{}` | `UserProfileJSON`: `{user_id, explicit_prefs, implicit_prefs, feature_vector}` |
| Partner B - Book Content Analyst | `candidate_book_ids[]`, metadata, review aggregates | `BookFeatureMapJSON`: `{book_id -> {semantic_vector, kg_context, tags}}` |
| Partner C - Recommendation Decision | `UserProfileJSON`, `BookFeatureMapJSON` | `RankedRecommendationListJSON`: `[{book_id, score_total, score_cf, score_content, score_kg, score_diversity, explanation}]` |

### 6.2 Scoring Formula (Partner C)

The composite score for book $b$ given user $u$ is:

$$
S(u, b) = w_1 \cdot \text{CF}(u,b) + w_2 \cdot \text{CSS}(u,b) + w_3 \cdot \text{KG}(u,b) + w_4 \cdot \text{DIV}(b)
$$

Where $w_1 + w_2 + w_3 + w_4 = 1$.

---

## 7. Agent Implementation Template (Partner-Side)

All three Partner Agents share the same `/rpc` interface shape. Replace business logic in the Start handler.

```python
from fastapi import FastAPI
from acps_sdk.aip import (
    TaskCommand,
    TaskResult,
    TaskStatus,
    TaskState,
    TaskCommandType,
    TextDataItem,
    Product,
)
from acps_sdk.aip.aip_rpc_model import RpcRequest, RpcResponse
from datetime import datetime, timezone
import uuid
import json

app = FastAPI()
tasks = {}

AGENT_AIC = "1.2.156.3088.1.BOOK.000002.P001.1.xxxx"


def make_result(command, state, message=None, products=None):
    return TaskResult(
        id=f"msg-{uuid.uuid4()}",
        sentAt=datetime.now(timezone.utc).isoformat(),
        senderRole="partner",
        senderId=AGENT_AIC,
        taskId=command.taskId,
        sessionId=command.sessionId,
        status=TaskStatus(
            state=state,
            stateChangedAt=datetime.now(timezone.utc).isoformat(),
            dataItems=[TextDataItem(text=message)] if message else None,
        ),
        products=products,
    )


@app.post("/partners/<agent_name>/rpc", response_model=RpcResponse)
async def handle_rpc(request: RpcRequest):
    command = request.params.command
    task_id = command.taskId

    if command.command == TaskCommandType.Start:
        try:
            input_data = json.loads(command.dataItems[0].text) if command.dataItems else {}
            # Replace with agent-specific business logic
            result_payload = {}
            product = Product(
                id=f"prod-{uuid.uuid4()}",
                name="AgentResult",
                dataItems=[TextDataItem(text=json.dumps(result_payload))],
            )
            result = make_result(command, TaskState.AwaitingCompletion, products=[product])
        except Exception as exc:
            result = make_result(command, TaskState.Failed, message=str(exc))
        tasks[task_id] = result
        return RpcResponse(id=request.id, result=result)

    if command.command == TaskCommandType.Complete:
        task = tasks.get(task_id)
        if task and task.status.state == TaskState.AwaitingCompletion:
            task.status = TaskStatus(
                state=TaskState.Completed,
                stateChangedAt=datetime.now(timezone.utc).isoformat(),
            )
        return RpcResponse(id=request.id, result=tasks.get(task_id))

    if command.command == TaskCommandType.Get:
        return RpcResponse(id=request.id, result=tasks.get(task_id))

    if command.command == TaskCommandType.Cancel:
        task = tasks.get(task_id)
        if task:
            task.status = TaskStatus(
                state=TaskState.Canceled,
                stateChangedAt=datetime.now(timezone.utc).isoformat(),
            )
        return RpcResponse(id=request.id, result=tasks.get(task_id))

    return RpcResponse(id=request.id, result=tasks.get(task_id))
```

---

## 8. Registration and Deployment Checklist

1. Create `acs.json` for each agent.
2. Start challenge server (`challenge-server`) on port 8004.
3. Submit ACS at https://ioa.pub/registry-web/ and obtain AIC.
4. Fill AIC values into each `acs.json`.
5. Apply for mTLS certificates using `ca-client new-cert --aic <AIC>`.
6. Place issued cert/key in each agent `certs/` directory.
7. Start services (Leader + all Partners).
8. Trigger Discovery sync if needed (`POST /admin/drc/sync`).
9. Validate ADP search resolution (`POST /api/discovery/search`).
10. Run end-to-end AIP flow from Leader to all Partners.

---

## 9. Design Compliance Summary

| ACPs Sub-Protocol | Coverage in This Design |
| :-- | :-- |
| AIC | Each agent has unique AIC; used as `senderId` in AIP messages |
| ACS | Full ACS descriptors for Leader and all Partners |
| ATR | Registration workflow and certificate issuance included |
| AIA | mTLS mutual authentication defined in ACS |
| ADP | Discovery integration and semantic partner lookup defined |
| AIP | Leader/Partner role model and command/state flow defined |
| DSP | Discovery synchronization path defined |
