# ACPs Reading Recommender Agent Specification

This document elaborates on the coordinator (main agent) and cooperative agents described in `plan.md`, translating the high-level roadmap into concrete ACPs-ready responsibilities, payloads, and registration requirements.

## 1. Coordinator Agent — Reading Concierge

### 1.1 Mission & Scope
- Acts as the ACPs workflow owner, mirroring the tourism `tour_assistant` but focusing on book journeys.
- Accepts user intents (queries, reading goals, constraints) via REST/JSON-RPC and decomposes them into parallel subtasks for downstream agents.
- Maintains session state, task dependency graphs, and evaluation metrics.
- Produces the final ranked recommendation list plus natural-language explanations tailored to user personas.

### 1.2 ACPs Registration Checklist
- **ACS file**: `reading_concierge/reading_concierge.json` with accurate `aic`, `skills`, `transport`, `capabilities` entries.
- **mTLS config**: JSON mapping to cert/key pair under `certs/` (align with ATR/AIA requirements).
- **Discovery hooks**: optional `DISCOVERY_BASE_URL` env var plus fallback to local ACS files, same strategy as tourism leader.
- **Command set**: coordinator exposes `/user_api` for clients and consumes partner RPC endpoints via `StartTask`, `ContinueTask`, `CompleteTask`, `CancelTask`.

### 1.3 Core Responsibilities
1. **User intent parsing**
   - Segment queries into four working dimensions referenced in `plan.md`: user profile enrichment, content analysis, candidate retrieval/filtering, ranking/explanation.
   - Detect scenario type: cold start, warm personalization, exploration/newness.
2. **Task orchestration**
   - Build `required_agents` array, assign priorities, dispatch tasks concurrently.
   - Handle partner states (`Accepted`, `Working`, `AwaitingInput`, `AwaitingCompletion`, `Completed`).
3. **Result integration**
   - Fuse vectors/summaries from cooperative agents, run scoring heuristics, craft final response.
4. **Governance & logging**
   - Persist ACPs audit logs, metrics (Precision@k, Recall@k, NDCG@k, diversity), and experiment tags for ablation tests noted in `plan.md`.

### 1.4 Coordinator RPC Payload Contract (Outbound)
| Field | Type | Description |
| --- | --- | --- |
| `task_id` | string | UUID per partner task |
| `task_name` | string | Human-readable descriptor (e.g., `profile_enrichment`) |
| `session_id` | string | Conversation/session tracker |
| `sub_query` | object | Agent-specific instructions, includes scenario flags |
| `context` | object | Shared data (user metadata, candidate set IDs, KG pointers) |
| `acceptance_criteria` | object | Definition of success for `AwaitingCompletion` auto-approval |

### 1.5 Return Payload Expectations (Inbound)
- `state`: ACPs task state.
- `outputs.profile_vector` (from profile agent) and `outputs.content_graph` (from content agent).
- `outputs.ranking` (from recommendation agent) with top-k list, scores, explanation tokens.
- `diagnostics`: timing, model usage, warnings (used for optimization per plan).

## 2. Cooperative Agents

### 2.1 User Profile Analysis Agent
- **Origin in plan**: "用户画像分析智能体".
- **Inputs**: historical ratings, reviews, demographics, session context.
- **Outputs**:
  - Normalized preference vector (genre, theme, difficulty, language, pacing, length).
  - Sentiment summary and latent intent keywords derived via BERT-based NLP.
  - Cold-start heuristics (e.g., popularity priors) when data sparse.
- **Key ACPs fields**:
  - ACS `skills`: `profile.extract`, `preference.embedding`, `sentiment.analysis`.
  - Task `sub_query.profile_goal`: {`mode`: `cold|warm|explore`, `time_window`: days, `required_signals`: list}.
  - Response `outputs.embedding_version` to support future migrations.
- **Dependencies**: Access to cleaned dataset/feature store and tokenizer configs defined in data workstream of `plan.md`.

### 2.2 Book Content Analysis Agent
- **Origin in plan**: "图书内容分析智能体".
- **Inputs**: book metadata, aggregated community reviews, knowledge graph edges.
- **Outputs**:
  - Sentence-BERT vectors for each candidate book.
  - Tag sets: topics, style, difficulty, mood, diversity indicators.
  - Knowledge graph context (author-publisher-category relations) for RAG.
- **ACPs requirements**:
  - ACS `skills`: `book.vectorize`, `kg.enrich`, `tag.extract`.
  - Task payload must include `candidate_ids` or `ingest_batch_id` and `kg_endpoint` info if remote retrieval needed.
  - Response should expose `outputs.kg_refs` (list of node IDs) to support traceability during registration/approval.

### 2.3 Recommendation Decision Agent
- **Origin in plan**: "推荐决策智能体".
- **Inputs**: profile vector, content vectors, optional collaborative filtering matrices (SVD factors), exploration constraints.
- **Outputs**:
  - Ranked list with composite scores across four dimensions noted in `plan.md`: collaborative filtering, semantic similarity, knowledge enhancement, diversity.
  - Explanation bundle for each item (bullet summary + justification string for UI and ATR auditing).
  - Diversity/novelty metrics for monitoring.
- **ACPs hooks**:
  - ACS `skills`: `ranking.svd`, `ranking.multifactor`, `explanation.llm`.
  - Task payload should provide scoring weights, novelty thresholds, and evaluation slices (e.g., `top_k`, `min_new_items`).
  - Response includes `outputs.metric_snapshot` to feed Phase 3/4 evaluation tasks.

### 2.4 Optional Supporting Agents
While not mandatory for the initial sprint, the plan's data/test focus suggests preparing stubs for:
1. **Data Curator Agent**: orchestrates dataset ingest, cleansing, KG refreshes (ties to "数据相关任务").
2. **Evaluation Agent**: automates metric computation, ablation toggles, baseline comparisons (ties to "测试与优化任务").
Both should share the same registration boilerplate so they can enter the ACPs registry later without rework.

## 3. Interaction Blueprint
1. **User query arrival** → Coordinator validates payload, tags scenario (cold/hot/explore).
2. **Parallel dispatch** → `StartTask` for profile and content agents with shared `session_id`.
3. **Candidate synthesis** → Coordinator merges results, optionally triggers data curator for missing coverage.
4. **Ranking request** → `StartTask` for recommendation agent with fused payload plus constraints.
5. **Completion cycle** → Coordinator polls via `ContinueTask`, evaluates `AwaitingCompletion` responses using rubric derived from acceptance criteria, issues `CompleteTask` once satisfied.
6. **Response assembly** → Deliver recommendations + explanations + metrics to client; persist logs for evaluation agent.

## 4. Preparation for Registration & Communication
- **ACS Templates**: create `acs_templates/reading_profile.json`, `reading_content.json`, `reading_recommendation.json`, mirroring tourism ACS schema but with updated `skills` and transport ports.
- **mTLS Configs**: align certificate subject names with new AIC codes; use `mtls_config.py` helpers copied earlier.
- **Environment Variables**:
  - `READING_DATA_ROOT`, `KG_URI`, `EMBED_MODEL`, `SVD_MODEL_PATH` for cooperative agents.
  - Per-agent `OPENAI_MODEL` overrides for explanation workloads.
- **Testing Hooks**: extend `tests/` to include unit specs for each agent's RPC handler plus integration tests simulating the flow above, matching the "单体测试" and "集成测试" tasks.

## 5. Next Implementation Steps
1. Scaffold directories: `reading_concierge/`, `agents/profile_agent/`, `agents/content_agent/`, `agents/recommendation_agent/`, `acs_templates/`, `configs/`.
2. Draft ACS + mTLS JSONs and register provisional AIC codes (can reuse demo registry until production ready).
3. Adapt `tour_assistant` FastAPI app into `reading_concierge`, replacing prompts and dimension mappings per plan.
4. Stub partner FastAPI apps that import shared `acps_aip` server utilities and expose domain-specific handlers.
5. Prepare synthetic fixtures (sample user/book data, KG edges) to unblock development before full dataset ingest.

This specification provides the detail necessary to implement ACPs-compliant registration, messaging, and orchestration for the personalized reading recommender prototype.
