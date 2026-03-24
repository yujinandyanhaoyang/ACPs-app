# BUPT ACPs Protocol Quick Start Guide

> **Document Goal**: Help you quickly understand what BUPT ACPs is, its components, and how to connect a new Agent to an existing system.  
> **Original Repository**: [AIP-PUB/Agent-Interconnection-Protocol-Project](https://github.com/AIP-PUB/Agent-Interconnection-Protocol-Project)  
> **Current Version**: v2.0 (March 2026)

---

## 1. What is ACPs

**ACPs (Agent Collaboration Protocols)** is an open protocol suite developed by Beijing University of Posts and Telecommunications (BUPT) in collaboration with the China Electronics Standardization Institute. Its goal is to solve the problem of "how Agents from different frameworks and vendors can interconnect and collaborate securely, reliably, and efficiently".

Analogy:  
- The Internet has the TCP/IP protocol suite, enabling interconnection between different machines  
- ACPs is the protocol suite for the "Agent Internet", enabling interconnection between different Agents

Compared with protocols such as IBM ACP and Google A2A, ACPs is characterized by **full-link coverage**: from assigning an ID to an Agent to registration, authentication, discovery, interaction, and data synchronization, each link has corresponding sub-specifications.

---

## 2. 7 Sub-protocols of ACPs

```
ACPs Protocol Suite
├── AIC  Agent Identity Code Specification  ← Assign a globally unique ID to each Agent (analogous to ID card number)
├── ACS  Agent Capability Description Specification  ← Describe what the Agent can do (analogous to resume)
├── ATR  Agent Trusted Registration Specification  ← Agent completes trusted registration of identity + capabilities with the registry
├── AIA  Agent Identity Authentication Specification  ← Mutual identity verification between Agents (mTLS + TLS 1.3 recommended)
├── ADP  Agent Discovery Protocol Specification  ← How to find Agents capable of completing a subtask in the network
├── AIP  Agent Interaction Protocol Specification  ← How Agents send tasks, transmit context, and collaborate to complete tasks
└── DSP  Data Synchronization Protocol Specification  ← How registration/capability information is kept synchronized between services
```

---

## 3. Core Concept Overview

### 3.1 AIC (Agent Identity Code)

Each Agent has a globally unique AIC, example format:

```
1.2.156.3088.1.34C2.478BDF.3GF546.1.0SEN
```

| Segment | Meaning |
|---|---|
| `1.2.156` | ISO → National Member Body → China |
| `3088` | Dedicated node for Agent interconnection |
| `1` | Registration service provider serial number |
| `34C2` | Agent supplier serial number |
| `478BDF` | Agent ontology serial number |
| `3GF546` | Agent instance serial number |
| `1` | Version number |
| `0SEN` | Check code |

---

### 3.2 ACS (Agent Capability Description)

ACS is a JSON file that describes "who the Agent is, what it can do, and how to call it". Every Agent must have an ACS file.

```json
{
  "aic": "1.2.156.3088.1.34C2.478BDF.3GF546.1.0SEN",
  "name": "Beijing Food Recommendation Agent",
  "description": "Recommend Beijing restaurants and food based on user preferences",
  "version": "1.0.0",
  "provider": {
    "organization": "Your Organization Name"
  },
  "securitySchemes": {
    "mtls": {
      "type": "mutualTLS",
      "x-caChallengeBaseUrl": "http://your-challenge-server:8004/acps-atr-v2"
    }
  },
  "endPoints": [
    {
      "url": "http://your-agent-host:8011/partners/your_agent/rpc",
      "transport": "HTTP"
    }
  ],
  "capabilities": {
    "streaming": false,
    "notification": false,
    "messageQueue": []
  },
  "skills": [
    {
      "id": "your_agent.skill_name",
      "name": "Skill Name",
      "description": "Detailed description of the skill, the more specific the better, for semantic matching by the discovery service",
      "tags": ["Tag1", "Tag2"],
      "examples": ["Example User Input 1", "Example User Input 2"]
    }
  ]
}
```

---

### 3.3 AIP Interaction Roles and Modes

AIP defines two roles:

| Role | Description |
|---|---|
| **Leader** | Receives user requests, disassembles tasks, schedules multiple Partners |
| **Partner** | Accepts subtasks from Leader, executes them and returns results |

Three interaction modes:

| Mode | Characteristics | Applicable Scenarios |
|---|---|---|
| **Direct Connection Mode** | Leader communicates point-to-point with each Partner | Clear task chain, fixed members |
| **Group Mode** | All Agents broadcast via RabbitMQ message queue | Concurrent collaboration of multiple Agents |
| **Hybrid Mode** | Direct connection + group mode used simultaneously | Flexible response to complex scenarios |

---

### 3.4 Task State Machine

```
           Start
             │
        ┌────▼────┐
        │Accepted │  ← Partner accepted the task
        └────┬────┘
             │
        ┌────▼────┐
        │ Working │  ← Task in execution
        └──┬──┬───┘
           │  │
    ┌──────▼┐ └──────────┐
    │Await  │            │Await
    │Input  │            │Completion
    └──┬────┘            └──┬────────┐
       │(Continue)          │(Complete)
       └──────────────┐     │
                   ┌──▼─────▼──┐
                   │ Completed │ ← Final State
                   └───────────┘

Other Final States: Failed、Canceled、Rejected
```

---

## 4. System Architecture: Relationship Between Services

```
┌─────────────────────────────────────────────┐
│              Your Existing System           │
│                                             │
│  ┌──────────┐    ┌──────────────────────┐  │
│  │  UI      │───▶│  Leader Agent         │  │
│  └──────────┘    │  (Task Parsing + Scheduling)│  │
│                  └──────┬───────────────┘  │
│                         │ AIP (Direct/Group) │
│           ┌─────────────┼──────────────┐   │
│     ┌─────▼───┐   ┌─────▼───┐  ┌──────▼─┐ │
│     │Partner A│   │Partner B│  │Partner C│ │
│     └─────────┘   └─────────┘  └────────┘ │
└─────────────────────────────────────────────┘

        ↕ ADP (Discovery)  ↕ ATR (Registration)  ↕ DSP (Synchronization)

┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│Registry      │  │CA Server     │  │Discovery     │
│Server        │◀─│(Certificate Issuance)│  │Server        │
│(Registry)    │──▶│              │  │(Discovery Service)│
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## 5. Adding a New Agent to an Existing System: Complete Steps

### Step 1: Write the ACS Capability Description File

Create `acs.json` in your Agent directory:

```json
{
  "aic": "",
  "active": true,
  "lastModifiedTime": "2026-01-01T00:00:00+08:00",
  "protocolVersion": "01.00",
  "name": "Your Agent Name",
  "description": "Detailed description of what this Agent can and cannot do (the more specific the better)",
  "version": "1.0.0",
  "provider": {
    "organization": "Your Organization",
    "url": "https://your-org.com"
  },
  "securitySchemes": {
    "mtls": {
      "type": "mutualTLS",
      "x-caChallengeBaseUrl": "http://your-challenge-server:8004/acps-atr-v2"
    }
  },
  "endPoints": [
    {
      "url": "http://your-agent-host:port/partners/agent_name/rpc",
      "transport": "HTTP",
      "security": [{ "mtls": [] }]
    }
  ],
  "capabilities": {
    "streaming": false,
    "notification": false,
    "messageQueue": []
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "agent_name.skill_id",
      "name": "Skill Name",
      "description": "Specific description of the skill, used by the discovery service for semantic matching",
      "version": "1.0.0",
      "tags": ["tag1", "tag2"],
      "examples": [
        "Example user input 1",
        "Example user input 2"
      ],
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"]
    }
  ]
}
```

---

### Step 2: Trusted Registration (Obtain AIC and Certificate)

> You can use the public registration service provided by BUPT [ioa.pub](https://ioa.pub/registry-web/), or build your own registration server.

**2.1 Install Tools**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install acps_ca_challenge-2.0.0-py3-none-any.whl
pip install acps_ca_client-2.0.0-py3-none-any.whl
```

**2.2 Configure and Start the Challenge Server** (for verification during certificate issuance)

```bash
# Create configuration file
cat > .env << EOF
UVICORN_HOST=0.0.0.0
UVICORN_PORT=8004
UVICORN_RELOAD=false
BASE_URL=/acps-atr-v2
CHALLENGE_DIR=./challenges
LOG_LEVEL=INFO
EOF

# Start challenge server
challenge-server
```

**2.3 Submit ACS on the Registration Platform**

Go to [ioa.pub](https://ioa.pub/registry-web/) to fill in your ACS JSON, and obtain the **AIC** (your Agent's globally unique identity code) after approval.  
Fill the obtained AIC back into the `"aic"` field of your `acs.json`.

**2.4 Apply for Digital Certificate**

```bash
# Create ca-client configuration
cat > ca-client.conf << EOF
CA_SERVER_BASE_URL = http://bupt.ioa.pub:8003/acps-atr-v2
CHALLENGE_SERVER_BASE_URL = http://your-IP:8004/acps-atr-v2
ACCOUNT_KEY_PATH = ./private/account.key
CERTS_DIR = ./certs
PRIVATE_KEYS_DIR = ./private
CSR_DIR = ./csr
TRUST_BUNDLE_PATH = ./certs/trust-bundle.pem
EOF

# Apply for certificate (replace with the real AIC you obtained)
ca-client new-cert --aic 1.2.156.3088.x.xxxx.xxxxxxx.xxxxxxx.1.xxxx
```

After successful execution, your Agent certificate will be saved in the `./certs/` directory.

---

### Step 3: Implement Agent Business Logic (Partner-side Code)

Install the SDK:

```bash
pip install acps_sdk
```

Create your Agent service file `my_agent.py`:

```python
from fastapi import FastAPI
from acps_sdk.aip import (
    TaskCommand, TaskResult, TaskStatus, TaskState,
    TaskCommandType, TextDataItem, Product
)
from acps_sdk.aip.aip_rpc_model import RpcRequest, RpcResponse
from datetime import datetime, timezone
import uuid

app = FastAPI()
tasks = {}  # Store task status

def make_result(command, state, message=None, products=None):
    return TaskResult(
        id=f"msg-{uuid.uuid4()}",
        sentAt=datetime.now(timezone.utc).isoformat(),
        senderRole="partner",
        senderId="Your AIC",          # ← Fill in your AIC
        taskId=command.taskId,
        sessionId=command.sessionId,
        status=TaskStatus(
            state=state,
            stateChangedAt=datetime.now(timezone.utc).isoformat(),
            dataItems=[TextDataItem(text=message)] if message else None,
        ),
        products=products,
    )

@app.post("/partners/your_agent/rpc", response_model=RpcResponse)
async def handle_rpc(request: RpcRequest):
    command = request.params.command
    task_id = command.taskId

    # ---- Start: Accept Task ----
    if command.command == TaskCommandType.Start:
        user_input = command.dataItems[0].text if command.dataItems else ""

        # 【Add your business judgment logic here】
        # For example: Determine if the request is within the capability scope of this Agent
        if "out-of-scope keyword" in user_input:
            result = make_result(command, TaskState.Rejected, "Out of the service scope of this Agent")
        else:
            # Call your business logic
            answer = f"Hello, I received: {user_input}, this is my processing result."  # ← Replace with real business logic
            product = Product(
                id=f"prod-{uuid.uuid4()}",
                name="Processing Result",
                dataItems=[TextDataItem(text=answer)]
            )
            result = make_result(command, TaskState.AwaitingCompletion, products=[product])

        tasks[task_id] = result
        return RpcResponse(id=request.id, result=result)

    # ---- Complete: Leader Confirms Completion ----
    elif command.command == TaskCommandType.Complete:
        task = tasks.get(task_id)
        if task and task.status.state == TaskState.AwaitingCompletion:
            task.status = TaskStatus(
                state=TaskState.Completed,
                stateChangedAt=datetime.now(timezone.utc).isoformat(),
            )
        return RpcResponse(id=request.id, result=tasks.get(task_id))

    # ---- Get: Query Task Status ----
    elif command.command == TaskCommandType.Get:
        return RpcResponse(id=request.id, result=tasks.get(task_id))

    # ---- Cancel: Cancel Task ----
    elif command.command == TaskCommandType.Cancel:
        task = tasks.get(task_id)
        if task:
            task.status = TaskStatus(
                state=TaskState.Canceled,
                stateChangedAt=datetime.now(timezone.utc).isoformat(),
            )
        return RpcResponse(id=request.id, result=tasks.get(task_id))

    return RpcResponse(id=request.id, result=tasks.get(task_id))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011)
```

**Start the Agent Service:**

```bash
python my_agent.py
# Agent service runs at http://0.0.0.0:8011
```

---

### Step 4: Configuration File Structure (Standard Directory)

In accordance with ACPs specifications, it is recommended to organize your Agent directory as follows:

```
partners/online/your_agent/
├── acs.json          # Capability description created in Step 1, with AIC filled in
├── config.toml       # Runtime configuration (LLM interface, port, logs, etc.)
├── prompts.toml      # Prompt templates (business logic prompts)
└── certs/            # Certificate files applied for in Step 2
    ├── agent.crt
    └── agent.key
```

Example `config.toml`:

```toml
[server]
host = "0.0.0.0"
port = 8011

[llm]
api_key = "your-api-key"
base_url = "https://api.openai.com/v1"
model = "gpt-4o"

[discovery]
url = "http://discovery-server:8005/api/discovery"

[log]
level = "INFO"
```

---

### Step 5: Register the New Agent to the Discovery Server

If a Discovery Server is deployed in your environment, it will automatically synchronize your ACS information from the Registry Server via the DSP protocol, no manual operation required.

If you need to trigger synchronization manually, you can call the management interface of the Discovery Server:

```bash
# Trigger manual synchronization (Discovery Server pulls the latest data from Registry Server)
curl -X POST http://discovery-server:8005/admin/drc/sync
```

After synchronization is completed, other Agents can find your new Agent through the semantic search interface of the Discovery Server:

```bash
# Test: Find Agents capable of completing a certain type of task using natural language
curl -X POST http://discovery-server:8005/api/discovery/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Recommend food in Beijing", "top_k": 5}'
```

---

## 6. Quick Deployment of Three Infrastructure Services

> Skip this section if these services are already available in your environment.  
> For a new setup, deploy in the following order: Registry → CA Server → Discovery.

### 6.1 Registry Server (Registry, Port 8001)

```bash
git clone https://github.com/AIP-PUB/ACPs-Registry-Server
cd ACPs-Registry-Server/registry-server
python3.13 -m venv venv && source venv/bin/activate
pip install poetry && poetry install
cp .env.example .env  # Edit .env, fill in database connection, etc.
alembic upgrade head   # Initialize database
./run.sh               # Start
# Verification: http://localhost:8001/docs
```

### 6.2 CA Server (Certificate Authority Server, Port 8003)

```bash
git clone https://github.com/AIP-PUB/ACPs-CA-Server
cd ACPs-CA-Server
python3 -m venv venv && source venv/bin/activate
pip install poetry && poetry install
cp .env.example .env  # Fill in DATABASE_URL, CA_CERT_PATH, AGENT_REGISTRY_URL, etc.
alembic upgrade head
uvicorn main:app --reload --port 8003
# Verification: http://localhost:8003/health
```

### 6.3 Discovery Server (Discovery Service, Port 8005)

```bash
git clone https://github.com/AIP-PUB/ACPs-Discovery-Server
cd ACPs-Discovery-Server
python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill in DRC_BASE_URL (pointing to Registry), OPENAI_API_KEY, etc.
alembic upgrade head
./start.sh
# Verification: http://localhost:8005/docs
```

### 6.4 Message Queue (Required for Group Mode, Optional)

```bash
# Install and start RabbitMQ
sudo apt update && sudo apt install -y erlang-nox rabbitmq-server
sudo systemctl start rabbitmq-server
sudo systemctl enable rabbitmq-server
sudo systemctl status rabbitmq-server  # Confirm it is running normally
```

---

## 7. Complete Process Summary

```
Complete process for adding a new Agent to an existing system:

[1] Write acs.json
      ↓
[2] Start the challenge server (challenge-server)
      ↓
[3] Submit ACS on ioa.pub → Approval → Obtain AIC
      ↓
[4] Apply for digital certificate with ca-client
      ↓
[5] Fill AIC into acs.json, place certificates in certs/ directory
      ↓
[6] Implement Agent business logic (implement /rpc interface)
      ↓
[7] Start the Agent service
      ↓
[8] Discovery Server synchronizes automatically, other Agents can discover you
      ↓
[9] Leader Agent calls your Agent via AipRpcClient
```

---

## 8. Common Error Code Reference

| Error Code | Name | Description |
|---|---|---|
| -32700 | Parse error | JSON format error |
| -32600 | Invalid Request | Invalid JSON-RPC request |
| -32601 | Method not found | Method does not exist |
| -32602 | Invalid params | Invalid parameters |
| -32603 | Internal error | Internal error |
| -32001 | TaskNotFoundError | Task does not exist |
| -32002 | TaskNotCancelableError | Task cannot be canceled |
| -32007 | GroupNotSupportedError | Group function not supported |

---

## 9. Reference Resources

| Resource | Address |
|---|---|
| Protocol Main Repository | [github.com/AIP-PUB/Agent-Interconnection-Protocol-Project](https://github.com/AIP-PUB/Agent-Interconnection-Protocol-Project) |
| Demo Project | [github.com/aip-pub/ACPs-Demo-Project](https://github.com/aip-pub/ACPs-Demo-Project) |
| Registration Platform | [ioa.pub](https://ioa.pub/registry-web/) |
| Registry Server | [github.com/AIP-PUB/ACPs-Registry-Server](https://github.com/AIP-PUB/ACPs-Registry-Server) |
| Discovery Server | [github.com/AIP-PUB/ACPs-Discovery-Server](https://github.com/AIP-PUB/ACPs-Discovery-Server) |
| CA Server | [github.com/AIP-PUB/ACPs-CA-Server](https://github.com/AIP-PUB/ACPs-CA-Server) |