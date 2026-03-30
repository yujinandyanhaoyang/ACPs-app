# Project Context
## ACPs-Based Multi-Agent Personalized Book Recommendation System

**Repository**: [ACPs-app / feature/recommendation-optimization](https://github.com/yujinandyanhaoyang/ACPs-app/tree/feature/recommendation-optimization)  
**ACPs Reference Implementation**: [AIP-PUB/ACPs-Demo-Project](https://github.com/AIP-PUB/ACPs-Demo-Project)  
**Document Version**: 2026-03-30  
**Status**: Active Development — System Refactoring in Progress

---

## Table of Contents

1. [Research Overview](#1-research-overview)
2. [Current Repository Status](#2-current-repository-status)
3. [Target System Architecture](#3-target-system-architecture)
4. [Agent Specifications](#4-agent-specifications)
5. [ACPs Protocol Compliance Design](#5-acps-protocol-compliance-design)
6. [Academic Argumentation Framework](#6-academic-argumentation-framework)
7. [Ablation Study Design](#7-ablation-study-design)
8. [Persistent Storage Architecture](#8-persistent-storage-architecture)

---

## 1. Research Overview

**Research Topic**: Design and Implementation of a Multi-Agent Personalized Book Recommendation System Based on the Agent Coordination Protocol Standard (ACPs)

**Core Research Problem**: Traditional personalized recommendation systems suffer from the Filter Bubble problem (Pariser, 2011) — behavior-based collaborative filtering inherently reinforces users' existing preferences, leading to information cocoons. Simultaneously, recommendation systems face the Accuracy-Diversity Dilemma (Kunaver & Požrl, 2017): maximizing personalization accuracy conflicts with maintaining semantic diversity in the recommendation list. These two opposing forces cannot be resolved within a single-objective optimization framework.

**Proposed Solution**: Explicitly model these two conflicting research directions as opposing objectives held by two independent agents — Reader Profile Agent (maximizing behavioral consistency, representing the accuracy side) and Book Content Agent (maximizing semantic coverage, representing the diversity side). A neutral mediator agent, the Recommendation Decision Agent, resolves the conflict through a Contextual Bandit-based arbitration mechanism. The system achieves dynamic, per-request weight balancing through multi-round inter-agent negotiation governed by the ACPs protocol.

**Key Contributions**:
1. A four-agent negotiation architecture (Organizer + Two Proposal Parties + Neutral Mediator) grounded in Mediator-Based Negotiation theory (Jennings et al., 1998)
2. A Contextual Bandit arbitration mechanism (UCB; Auer et al., 2002) that learns from historical recommendation feedback, enabling decision quality to improve over time
3. Full ACPs protocol compliance across three layers — AIA (identity authentication), ADP (dynamic discovery), and AIP (message semantics) — ensuring all inter-agent communication is cryptographically authenticated and semantically structured
4. A closed-loop online learning system driven by the Feedback Agent, enabling continuous model updates without periodic offline retraining

---

## 2. Current Repository Status

### 2.1 Directory Structure

```
ACPs-app/
├── reading_concierge/              ← Leader; acs.json present (2.8 KB)
│   │                                 config.toml and prompts.toml: 0 bytes (empty)
│   └── reading_concierge.py        ← 54 KB; core logic present but requires refactoring
├── agents/                         ← Legacy codebase; reference only, not runtime entry
│   ├── book_content_agent/
│   ├── reader_profile_agent/
│   └── rec_ranking_agent/
├── partners/online/                ← ACPs standard directory; currently 3 Partners only
│   ├── book_content_agent/         ← acs.json present; config/prompts: 0 bytes
│   ├── reader_profile_agent/       ← acs.json present; config/prompts: 0 bytes
│   └── rec_ranking_agent/          ← To be deprecated and split
├── migrations/
│   └── 001_initial_schema.sql      ← Present; missing behavior-event and profile tables
├── scripts/
│   ├── build_cf_model.py           ← Present
│   ├── build_knowledge_graph.py    ← Present
│   ├── merge_book_corpora.py       ← Present
│   ├── backfill_book_features.py   ← Present
│   ├── backfill_user_events.py     ← Present
│   ├── phase4_benchmark_compare.py ← Present (23.8 KB; requires update for new architecture)
│   ├── run_ablation.py             ← Present (12.8 KB; requires new ablation modules)
│   ├── phase3_issue_real_certs.sh  ← Present (certificate issuance workflow)
│   ├── phase3_dsp_sync_verify.sh   ← Present (ADP registration verification)
│   └── register_agents_ioa_pub.md  ← Present (ATR registration instructions)
├── base.py                         ← Present (9.2 KB; AIP RPC base class)
├── acps_aip/                       ← Present (protocol implementation layer)
├── certs/                          ← Present (dev self-signed certs; to be replaced)
├── services/                       ← Present
├── web_demo/                       ← Present (front-end interface)
└── requirements.txt                ← Present (360 B)
```

### 2.2 Critical Issues Summary

| Category | Issue | Severity |
|---|---|---|
| Architecture | Only 3 Partners present; missing RDA, Recall, RankingPolicy, Explanation, Feedback Agents | 🔴 Blocking |
| Architecture | `agents/` and `partners/online/` overlap in responsibility; roles unclear | 🟡 Cleanup required |
| Business Logic | `reading_concierge.py`: no arbitration logic, no GroupMgmt broadcast, no dynamic weight generation | 🔴 Blocking |
| Business Logic | `reader_profile_agent`: no PostgreSQL persistence, no decay-weighted encoding | 🔴 Blocking |
| Business Logic | `book_content_agent`: 12-dim vectors (target: 384-dim); no projection matrix; no alignment validation interface | 🔴 Blocking |
| Business Logic | `rec_ranking_agent`: pseudo-SVD implementation; to be split and deprecated | 🔴 Blocking |
| Configuration | All `config.toml` and `prompts.toml` files are empty (0 bytes) | 🔴 Blocking |
| Database | `001_initial_schema.sql` lacks `user_behavior_events` and `user_profiles` tables | 🔴 Blocking |
| ACPs Compliance | All AICs are placeholders; ATR formal registration not completed | 🟡 Required |
| Certificates | `certs/` contains dev self-signed certificates, not ATR-issued CAI certificates | 🟡 Required |

---

## 3. Target System Architecture

### 3.1 System Layering

```
┌─────────────────────────────────────────────────────┐
│  Layer 0: User Interaction Layer                     │
│  Web Demo / API Entry Point                          │
└─────────────────────────┬───────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────┐
│  Layer 1: Negotiation & Coordination Layer           │
│  Reading Concierge       (port 8210)  — Organizer    │
│  Recommendation Decision Agent (port 8213) — Mediator│
└──────────────┬──────────────────────┬───────────────┘
               ↓                      ↓
┌──────────────────────┐  ┌──────────────────────────┐
│  Layer 2: Proposal   │  │  Layer 2: Proposal        │
│  Negotiation Layer   │  │  Negotiation Layer        │
│  Reader Profile Agent│  │  Book Content Agent       │
│  (port 8211)         │  │  (port 8212)              │
└──────────────────────┘  └──────────────────────────┘
                           ↓ (arbitration result dispatched)
┌─────────────────────────────────────────────────────┐
│  Layer 3: Execution & Evaluation Layer               │
│  Recall Agent (8214)                                 │
│  Ranking Policy Agent (8215)                         │
│  Explanation Agent (8216)                            │
└─────────────────────────┬───────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────┐
│  Layer 4: Feedback & Perception Layer                │
│  Feedback Agent (port 8217)                          │
└─────────────────────────────────────────────────────┘
```

### 3.2 Complete Interaction Sequence

```
t0   User request → Reading Concierge
       LLM parses user intent → structured task parameters
       GroupMgmt broadcast → Reader Profile Agent + Book Content Agent (parallel)

t1   [Parallel execution]
     Reader Profile Agent:
       Load behavior sequence from PostgreSQL (90-day window, decay-weighted)
       Encode → profile_vector (256-dim) + confidence ∈ [0, 1]
       Cold-start guard: event_count < 5 → force confidence ≤ 0.25, cold_start = true
       Proposal A: {profile_vector, confidence, behavior_genres, strategy_suggestion}

     Book Content Agent:
       Encode via sentence-transformers (all-MiniLM-L6-v2) → book_vectors (384-dim)
       Project to 256-dim user space via proj_matrix.npy
       Compute JS divergence between declared preferences and behavioral genres
       Proposal B: {alignment_report, divergence_score, weight_suggestion}
       [If divergence > 0.4: proactively mention(RDA, performative="reject-proposal")]

t2   RC aggregates both proposals → forwards to Recommendation Decision Agent

t3   Recommendation Decision Agent (Contextual Bandit arbitration):
       Map context: f(confidence, divergence) → one of 4 context classes
       UCB selection: UCB(a) = r̄(a) + c·√(ln N / n(a)),  c = 1.41
       [If information insufficient: proactively mention(RPA/BCA, performative="query-if")]
       [Multi-round negotiation: max 3 rounds; fallback to historical arm mean if not converged]
       Output: final_weights + strategy + mmr_lambda
       Differentiated dispatch:
         → Recall Agent:         {ann_weight, cf_weight, strategy}
         → Ranking Policy Agent: {weights, mmr_lambda, penalty_params}
         → Explanation Agent:    {min_coverage, required_evidence_types}

t4   Recall Agent:
       ANN path: Faiss HNSW, ef_search=100, top_k=200, recall_source="ann"
       CF  path: ALS model, top_k=100, recall_source="cf"
       Merge and deduplicate → candidates[] (~250 books)

t5   Ranking Policy Agent (Round 1):
       Four-dimensional scoring (content / cf / novelty / recency)
       → preliminary_ranked_list (top-50)

t6   Explanation Agent (assessment phase):
       Heuristic evaluation of explain_confidence per candidate (no LLM)
       → confidence_list {book_id: float}

t7   Ranking Policy Agent (Round 2):
       Apply EA penalty: score × 0.7 if confidence < threshold
       MMR re-ranking → final_ranked_list (top-20)
       MMR(dᵢ) = λ·Rel(dᵢ) − (1−λ)·max_{dⱼ∈S} cos(d⃗ᵢ, d⃗ⱼ)

t8   Explanation Agent (generation phase):
       LLM generates personalized recommendation rationales (gpt-4o)
       → explanations {book_id: text}

t9   Reading Concierge assembles response → returns to user

[Asynchronous feedback loop]
t10  User behavior events → DSP Webhook → Feedback Agent
       Compute reward signal rₜ
       → mention → Reader Profile Agent  (profile update; threshold: 20 events/user)
       → mention → Recall Agent          (CF retrain; threshold: 500 rating events globally)
       → mention → RDA                   (update contextual bandit arm record)
```

### 3.3 Persistent Storage Architecture

| Storage | Technology | Owner Agent | Purpose |
|---|---|---|---|
| Relational DB | PostgreSQL | Reader Profile Agent | User behavior sequences and profile vectors |
| Vector Index | Faiss HNSW | Book Content Agent (write) / Recall Agent (read) | Book semantic vector retrieval |
| User Similarity Index | Hnswlib | Recall Agent | Collaborative filtering user similarity |
| Session Store | Redis DB 0 | Reading Concierge | Per-session context |
| Bandit Arm Records | Redis DB 1 | Recommendation Decision Agent | Contextual bandit state persistence |
| Feedback Queue | Redis DB 2 | Feedback Agent | Behavior event buffer |

---

## 4. Agent Specifications

### 4.1 Reading Concierge

| Property | Value |
|---|---|
| Port | 8210 |
| ACPs Role | `leader` |
| Academic Classification | Cognitive Agent — Organizer |
| Private Objective | Maintain negotiation order; ensure user intent is accurately conveyed |
| LLM Calls | ✅ Intent parsing: natural language → structured task parameters |
| `prompts.toml` | Required |
| Skills | `rc.parse_intent`, `rc.broadcast_task`, `rc.assemble_response` |

**Responsibilities**:
- Parse user natural language request via LLM → structured task parameters
- GroupMgmt broadcast to RPA and BCA (parallel)
- Route `mention` messages between agents; maintain negotiation order
- Aggregate proposals from RPA and BCA → forward to RDA
- Receive RDA arbitration result → route execution instructions to downstream agents
- Assemble final recommendation response → return to user

**Explicitly does NOT**:
- Perform arbitration or generate recommendation weights
- Access user profile database or book vector index directly
- Take sides on any proposal

**`config.toml` key parameters**:
```toml
[server]
port = 8210

[llm]
model = "gpt-4o"
temperature = 0.3
max_tokens = 512

[redis]
url = "redis://localhost:6379/0"
```

---

### 4.2 Reader Profile Agent

| Property | Value |
|---|---|
| Port | 8211 |
| ACPs Role | `partner-rpa` |
| Academic Classification | Cognitive Agent — Proposal Party A |
| Private Objective | Maximize user behavioral consistency (personalization accuracy; Filter Bubble accuracy side) |
| LLM Calls | ✅ Semantic preference induction: lift discrete behavior sequences to semantic space |
| `prompts.toml` | Required |
| Skills | `uma.build_profile`, `uma.validate_consistency`, `uma.update_profile` |

**Core Logic**:
- Load behavior sequence from PostgreSQL (90-day window, up to 500 events)
- Decay-weighted encoding: $w_t = e^{-\lambda(T-t)}$, $\lambda = 0.05$
- LLM semantic induction → preference description text → `sentence-transformers` encode → `profile_vector` (256-dim)
- Compute `confidence` ∈ [0, 1]
- Cold-start guard: event_count < 5 → force `confidence ≤ 0.25`, `cold_start = true`
- Submit Proposal A to RDA; respond to RDA `query-if` with cold-start prior distribution
- Receive Feedback Agent trigger → incremental profile update

**`config.toml` key parameters**:
```toml
[server]
port = 8211

[database]
dsn = "postgresql://user:pass@localhost:5432/acps"

[model]
LAMBDA = 0.05
WARM_THRESHOLD = 20
VECTOR_DIM = 256
```

---

### 4.3 Book Content Agent

| Property | Value |
|---|---|
| Port | 8212 |
| ACPs Role | `partner-bca` |
| Academic Classification | Cognitive Agent — Proposal Party B |
| Private Objective | Maximize semantic coverage diversity of the recommendation list (Filter Bubble diversity side) |
| LLM Calls | ❌ Uses `sentence-transformers`; no LLM dependency |
| `prompts.toml` | Not required |
| Skills | `bca.encode_books`, `bca.validate_alignment` |

**Core Logic**:
- Encode books via `sentence-transformers` (all-MiniLM-L6-v2) → 384-dim vectors
- Project to 256-dim user space via `proj_matrix.npy` (256×384; initialized via PCA or random projection)
- Compute JS divergence between user's declared preferences and behavioral genre distribution → `AlignmentReport`
- Submit Proposal B to RDA
- If `divergence > MISMATCH_THRESHOLD (0.4)`: proactively `mention(RDA, performative="reject-proposal")` with counter-proposal

**Design rationale for no LLM**: BCA uses mathematical vector operations rather than LLM calls, demonstrating that LLM should only be used where semantic understanding is genuinely required. This avoids over-reliance on LLM, which would reduce system interpretability and increase inference cost — a deliberate architectural decision.

**`config.toml` key parameters**:
```toml
[server]
port = 8212

[model]
ENCODER_MODEL = "all-MiniLM-L6-v2"
PROJ_MATRIX_PATH = "proj_matrix.npy"
MISMATCH_THRESHOLD = 0.4
```

---

### 4.4 Recommendation Decision Agent

| Property | Value |
|---|---|
| Port | 8213 |
| ACPs Role | `partner-rda` |
| Academic Classification | Cognitive Agent — Neutral Mediator |
| Private Objective | Minimize long-term recommendation regret (Regret Minimization; Auer et al., 2002) |
| LLM Calls | ❌ |
| `prompts.toml` | Not required |
| Skills | `rda.arbitrate`, `rda.dispatch` |

**Core Logic**:

**Step 1 — Context Identification**

Map the two proposals to a context class:

$$\text{context} = f(\text{confidence},\ \text{divergence}) \in \{\texttt{high\_conf\_low\_div},\ \texttt{low\_conf\_high\_div},\ \texttt{low\_conf\_low\_div},\ \texttt{high\_conf\_high\_div}\}$$

**Step 2 — UCB Arbitration**

Query contextual arm records for the identified context class; select the action with the highest UCB value:

$$\text{UCB}(a) = \bar{r}(a) + c\sqrt{\frac{\ln N}{n(a)}}, \quad c = 1.41$$

Where $\bar{r}(a)$ is the historical mean reward for action $a$, $N$ is total trial count, and $n(a)$ is trial count for action $a$.

**Step 3 — Multi-Round Negotiation (when triggered)**

```
Round 1: Receive initial proposals from both parties
          Compute preliminary equilibrium W₀
          Broadcast W₀ to both parties: "Evaluate this proposal against your objective function"

Round 2: RPA replies: {objective_score, adjustment_suggestion}
          BCA replies: {objective_score, adjustment_suggestion}

Round 3: Integrate feedback → compute new equilibrium W₁
          Verify both parties' objective functions exceed their respective thresholds
          → Converged: output W₁
          [If max rounds exceeded: fallback to historical arm mean]
```

**Step 4 — Differentiated Dispatch**

On convergence, proactively dispatch customized execution instructions to each downstream agent:

```json
→ Recall Agent:
  {"ann_weight": 0.65, "cf_weight": 0.35, "strategy": "exploit", "diversity_boost": false}

→ Ranking Policy Agent:
  {"weights": {"content": 0.62, "cf": 0.20, "novelty": 0.12, "recency": 0.06},
   "mmr_lambda": 0.55, "confidence_penalty_threshold": 0.6, "penalty_multiplier": 0.7}

→ Explanation Agent:
  {"min_coverage": 0.6, "required_evidence_types": ["content_sim", "cf_neighbors"]}
```

**Step 5 — Reward Signal Update**

Receive Feedback Agent `inform` message → update the `(context_type, action)` arm record:

```
arm_record[context_type][action].trials += 1
arm_record[context_type][action].avg_reward = (
    (avg_reward × (trials - 1) + r_t) / trials
)
```

**Why RDA is a genuine Agent and not a function module**:
- Its arbitration behavior is determined jointly by the current input **and** its historical arm records (internal private state)
- Identical conflict inputs at different points in time yield different arbitration results (arm records evolve over time)
- It proactively initiates `query-if` and multi-round negotiation broadcasts — behaviors not triggered by any external call
- These properties violate referential transparency, which is the defining characteristic of function calls

**`config.toml` key parameters**:
```toml
[server]
port = 8213

[redis]
url = "redis://localhost:6379/1"

[bandit]
UCB_C = 1.41
MAX_ROUNDS = 3
MIN_TRIALS_FOR_CONFIDENCE = 20
```

---

### 4.5 Recall Agent

| Property | Value |
|---|---|
| Port | 8214 |
| ACPs Role | `partner-recall` |
| Academic Classification | Reactive Agent — Execution Layer |
| Private Objective | None (sense-act mapping) |
| LLM Calls | ❌ |
| `prompts.toml` | Not required |
| Skills | `recall.execute`, `recall.retrain` |

**Core Logic**:
- **ANN path**: Faiss HNSW retrieval, `ef_search=100`, `top_k=200`, tag `recall_source="ann"`
- **CF path**: Hnswlib finds top-50 similar users; ALS inference, `top_k=100`, tag `recall_source="cf"`
- Merge and deduplicate: weight by `ann_weight`/`cf_weight` from RDA; `recall_source="both"` for overlapping candidates (take higher score)
- Inbound mention handler: receive Feedback Agent trigger → invoke `scripts/build_cf_model.py` for incremental ALS retraining

**`config.toml` key parameters**:
```toml
[server]
port = 8214

[index]
FAISS_INDEX_PATH = "data/book_faiss.index"
ALS_MODEL_PATH   = "data/als_model.npz"
HNSWLIB_PATH     = "data/user_sim.bin"
```

---

### 4.6 Ranking Policy Agent

| Property | Value |
|---|---|
| Port | 8215 |
| ACPs Role | `partner-ranking` |
| Academic Classification | Instrumental Agent — Evaluation Layer |
| Private Objective | None (provides ranking expertise for the negotiation process) |
| LLM Calls | ❌ |
| `prompts.toml` | Not required |
| Skills | `ranking.score`, `ranking.rerank` |

**Core Logic**:
- Receive `weights` and `mmr_lambda` from RDA
- **Round 1**: Four-dimensional scoring (content / cf / novelty / recency) → `preliminary_ranked_list` (top-50)
- Receive `confidence_list` from Explanation Agent; apply penalty: `score × penalty_multiplier` if `confidence < threshold`
- **Round 2**: MMR re-ranking → `final_ranked_list` (top-20)

$$\text{MMR}(d_i) = \lambda \cdot \text{Rel}(d_i) - (1-\lambda) \cdot \max_{d_j \in S} \cos(\vec{d}_i,\ \vec{d}_j)$$

**`config.toml` key parameters**:
```toml
[server]
port = 8215

[ranking]
CONFIDENCE_PENALTY_THRESHOLD = 0.6
PENALTY_MULTIPLIER           = 0.7
DEFAULT_MMR_LAMBDA           = 0.5
```

---

### 4.7 Explanation Agent

| Property | Value |
|---|---|
| Port | 8216 |
| ACPs Role | `partner-ea` |
| Academic Classification | Instrumental Agent — Evaluation Layer |
| Private Objective | None (provides explainability evaluation for the negotiation process) |
| LLM Calls | ✅ Phase 2 only: personalized rationale generation |
| `prompts.toml` | Required |
| Skills | `ea.assess_confidence`, `ea.generate_explanation` |

**Core Logic**:

**Phase 1 — Heuristic Assessment** (no LLM; fast path):

Compute `explain_confidence` for each candidate in `preliminary_ranked_list`:

| Evidence Field | Condition | Contribution |
|---|---|---|
| `content_sim` | > 0.5 | +0.30 |
| `cf_neighbors` | present | +0.30 |
| `matched_prefs` | non-empty | +0.20 |
| `kg_features` | present | +0.20 |

Output: `confidence_list {book_id: float}` → forwarded to Ranking Policy Agent

**Phase 2 — Rationale Generation** (LLM; slow path):

Generate personalized explanation for each book in `final_ranked_list`:
- Model: gpt-4o, temperature=0.4, max_tokens=300
- Template variables: `{title}`, `{author}`, `{genre_tags}`, `{content_similarity}`, `{cf_evidence}`, `{matched_preferences}`
- Fallback template activated when evidence is insufficient

**`config.toml` key parameters**:
```toml
[server]
port = 8216

[llm]
model       = "gpt-4o"
temperature = 0.4
max_tokens  = 300

[quality]
DEFAULT_MIN_COVERAGE = 0.6
```

---

### 4.8 Feedback Agent

| Property | Value |
|---|---|
| Port | 8217 |
| ACPs Role | `partner-fa` |
| Academic Classification | Environment Agent — Perception Layer |
| Private Objective | None (closes the system feedback loop) |
| LLM Calls | ❌ |
| `prompts.toml` | Not required |
| Skills | `fa.receive_event`, `fa.compute_reward` |

**Academic positioning**: Feedback Agent satisfies the broadest Agent definition per Russell & Norvig — "an agent is anything that perceives its environment through sensors and acts upon it through actuators." FA's sensors are the DSP Webhook (user behavior events) and its actuators are the `mention` mechanism (internal system trigger signals). Its academic value lies not in negotiation capability, but in transforming the system from an **open-loop** to a **closed-loop** recommender — without FA, the system cannot learn from user behavior.

**Core Logic**:
- `POST /feedback/webhook`: receive DSP behavior events; map to reward weights; enqueue in Redis
- Event weight mapping:

| Event Type | Reward Weight |
|---|---|
| `finish` / `rate_5` | +1.0 |
| `rate_4` | +0.8 |
| `rate_3` / `click` | +0.3 |
| `view` | +0.1 |
| `rate_2` | −0.3 |
| `skip` | −0.5 |
| `rate_1` | −0.8 |

- Accumulation triggers:
  - Per-user event count ≥ 20 → `mention(RPA, performative="inform", trigger="update_profile")`
  - Global rating event count ≥ 500 → `mention(RecallAgent, performative="inform", trigger="retrain_cf")`
  - After every completed recommendation session → `mention(RDA, performative="inform", reward=rₜ, context_type=ctx, action=action)`

**`config.toml` key parameters**:
```toml
[server]
port = 8217

[redis]
url = "redis://localhost:6379/2"

[trigger]
USER_UPDATE_THRESHOLD  = 20
CF_RETRAIN_THRESHOLD   = 500

[agents]
RPA_AIC    = "<AIC-RPA>"
RECALL_AIC = "<AIC-RECALL>"
RDA_AIC    = "<AIC-RDA>"
```

---

### 4.9 Agent Summary Table

| Agent | Port | Role | Academic Class | Private Objective | LLM | `prompts.toml` |
|---|---|---|---|---|---|---|
| Reading Concierge | 8210 | Leader / Organizer | Cognitive Agent | Negotiation order | ✅ Intent parsing | Required |
| Reader Profile Agent | 8211 | Proposal Party A | Cognitive Agent | Maximize accuracy | ✅ Preference induction | Required |
| Book Content Agent | 8212 | Proposal Party B | Cognitive Agent | Maximize diversity | ❌ | Not required |
| Recommendation Decision Agent | 8213 | Neutral Mediator | Cognitive Agent | Minimize regret | ❌ | Not required |
| Recall Agent | 8214 | Execution | Reactive Agent | — | ❌ | Not required |
| Ranking Policy Agent | 8215 | Evaluation | Instrumental Agent | — | ❌ | Not required |
| Explanation Agent | 8216 | Evaluation | Instrumental Agent | — | ✅ Rationale generation | Required |
| Feedback Agent | 8217 | Perception | Environment Agent | — | ❌ | Not required |

---

## 5. ACPs Protocol Compliance Design

### 5.1 Three-Layer Protocol Satisfaction

| ACPs Layer | Requirement | Satisfaction Method | Evidence |
|---|---|---|---|
| **AIA** (Identity Authentication) | Each Agent holds ATR-issued CAI certificate; all communication uses mTLS mutual authentication | 8 Agents each hold independent AIC + CAI certificate; `verify_client = true` | `phase3_issue_real_certs.sh`; `[server.mtls]` in each `config.toml` |
| **ADP** (Discovery Protocol) | Agents discover each other via DSP; no hardcoded endpoints | Each Agent registers its endpoint and skills in DSP on startup; RC discovers Partners by skill name | `phase3_dsp_sync_verify.sh`; `acps_aip/dsp_client.py` |
| **AIP** (Interaction Protocol) | Messages carry `performative` semantics; multi-round negotiation tracked by `conversation_id` | All messages contain `from`, `to`, `performative`, `conversation_id` | `base.py` AIP message encapsulation; `mention()` implementations in each Agent |

### 5.2 AIP Message Semantics Table

| Message Scenario | Performative | Sender → Receiver |
|---|---|---|
| RC broadcasts task | `request` | RC → RPA, BCA |
| RPA submits proposal | `propose` | RPA → RDA |
| BCA emits veto signal | `reject-proposal` | BCA → RDA |
| RDA requests supplementary info | `query-if` | RDA → RPA / BCA |
| RDA broadcasts preliminary equilibrium | `propose` | RDA → RPA, BCA |
| RDA dispatches execution instructions | `inform` | RDA → RA / RankingPA / EA |
| FA sends reward signal | `inform` | FA → RDA |
| FA triggers profile update | `inform` | FA → RPA |
| FA triggers CF retraining | `inform` | FA → Recall Agent |

### 5.3 Standard Agent Directory Structure

Each Agent under `partners/online/<agent_name>/`:

```
partners/online/<agent_name>/
├── agent.py           # Business logic
├── acs.json           # ACS definition: AIC, capability declaration, endpoint, skills, description
├── config.toml        # Runtime config: LLM, port, [server.mtls] cert paths, business params
├── prompts.toml       # Prompt templates (RC / RPA / EA only)
├── <AIC>.pem          # CAI certificate (ATR-issued)
├── <AIC>.key          # Private key
└── trust-bundle.pem   # CA trust bundle
```

### 5.4 Why ACPs Communication Is Not Equivalent to Inter-Process Function Calls

1. **Identity layer**: Every message is preceded by a mTLS handshake in which both parties present ATR-issued certificates. A function call has no concept of caller identity verification.

2. **Discovery layer**: RC does not know the address of RPA at design time. It discovers the endpoint at runtime via DSP by querying `skill="uma.build_profile"`. This location transparency is architecturally impossible with function calls.

3. **Semantics layer**: Messages carry `performative` values such as `propose`, `reject-proposal`, and `query-if`. These semantics — proposal, veto, counter-proposal — cannot be expressed in a function's input-output model. A function call can only return a value; it cannot "reject" its caller's premise.

4. **Asynchrony**: FA's `mention` to RDA is asynchronous — FA continues processing the next event without waiting for RDA's response. Standard function calls are synchronous and blocking.

---

## 6. Academic Argumentation Framework

### 6.1 Why This System Constitutes Genuine Multi-Agent Collaboration

**Core claim**: The recommendation result is an emergent output produced by negotiation among multiple autonomous entities with opposing objectives — not the deterministic output of any single module.

**Argument 1 — Externally grounded goal conflict**

The opposing objectives of RPA (accuracy) and BCA (diversity) are not artificially assigned to justify the design. They correspond to independently established research problems:
- Filter Bubble problem (Pariser, 2011): behavior-based personalization reinforces existing preferences
- Accuracy-Diversity Dilemma (Kunaver & Požrl, 2017): precision and diversity are structurally in tension

The system makes this pre-existing conflict explicit by instantiating the two sides as separate agents.

**Argument 2 — Non-deterministic negotiation outcomes**

Proposals from RPA and BCA are generated independently and are mutually opaque. RDA's UCB arbitration depends on its historical arm records (internal private state). Identical conflict inputs at different times yield different arbitration results because the arm records evolve continuously. This violates referential transparency — the defining property of function calls — and satisfies Wooldridge's autonomy criterion.

**Argument 3 — Proactive inter-agent communication**

BCA's `reject-proposal` is initiated by BCA's own computation upon detecting `divergence > 0.4`. It is not triggered by any external call. RDA's multi-round negotiation broadcast is proactively initiated when RDA's internal uncertainty assessment deems the information insufficient. Both behaviors originate from agents' internal states, not from the orchestration logic of a calling function.

**Argument 4 — Mediator-Based Negotiation architecture**

The four-agent collaboration structure (Organizer + Proposal Party A + Proposal Party B + Neutral Mediator) directly instantiates the Mediator-Based Negotiation model (Jennings et al., 1998). The mediator's neutrality is structurally guaranteed: RDA holds no stake in either the accuracy or the diversity objective.

### 6.2 Agent Classification Rationale

| Agent | Classification | Justification |
|---|---|---|
| Reading Concierge | Cognitive Agent — Organizer | Holds explicit system-level goal; maintains negotiation order; exercises judgment in message routing |
| Reader Profile Agent | Cognitive Agent — Proposal Party | Holds private objective externally grounded in accuracy research; private state evolves over time; proactively submits proposals |
| Book Content Agent | Cognitive Agent — Proposal Party | Holds private objective externally grounded in diversity research; proactively emits veto signals based on its own computation |
| Recommendation Decision Agent | Cognitive Agent — Mediator | Holds private objective (regret minimization); internal state (arm records) evolves from experience; proactively initiates multi-round negotiation |
| Recall Agent | Reactive Agent | Legitimate sense-act mapping role in MAS execution layer; responds to RDA instructions and FA retraining triggers |
| Ranking Policy Agent | Instrumental Agent | Provides ranking expertise as an objective third-party evaluation tool for the negotiation process |
| Explanation Agent | Instrumental Agent | Provides explainability evaluation as an objective third-party evaluation tool for the negotiation process |
| Feedback Agent | Environment Agent | Satisfies Russell & Norvig's broadest Agent definition; transforms the system from open-loop to closed-loop |

### 6.3 Anticipated Defense Challenges and Responses

| Challenge | Response |
|---|---|
| "Most Agents are just functional modules, not real Agents." | The collaboration claim rests on the four-Agent negotiation core (RC, RPA, BCA, RDA). The other four Agents serve execution and perception roles — a legitimate heterogeneous composition in MAS literature (Ferber, 1999). |
| "Your negotiation is just conditional branching — that's a function call." | RDA's UCB arbitration depends on its historical arm records. Identical inputs at different times yield different outputs. This violates referential transparency and satisfies Wooldridge's autonomy criterion. |
| "Your private objectives are invented to justify the design." | RPA and BCA's objectives correspond to the Accuracy-Diversity Dilemma (Kunaver, 2017) and the Filter Bubble problem (Pariser, 2011) — conflicts that exist independently of this system design and are cited extensively in the recommendation systems literature. |
| "This is just inter-process communication, not genuine Agent communication." | All communication passes through ATR-issued CAI certificates (AIA), DSP dynamic discovery (ADP), and performative-structured messages (AIP). The `reject-proposal` and `query-if` performatives express semantics that cannot be represented in a function's input-output model. |
| "RDA's arbitration is just a fixed rule set." | RDA uses the UCB algorithm (Auer et al., 2002); its arm records are updated by real user behavior reward signals after every session. Its behavior evolves over time — early sessions and later sessions facing identical inputs may produce different arbitration results. No static rule set can replicate this. |
| "Your Explanation and Ranking agents have no private objectives — how are they Agents?" | They are classified as Instrumental Agents that provide objective third-party evaluation dimensions for the negotiation process. Their academic value lies not in autonomous goal-pursuit but in supplying evaluative inputs (explainability scores, ranking quality) that inform RDA's arbitration. |

---

## 7. Ablation Study Design

| Ablation Group | Removed Component | Contribution Being Validated |
|---|---|---|
| `-CF` | CF path in Recall Agent; ANN only | Collaborative filtering's contribution to recall coverage and cold-start performance |
| `-Alignment` | Lateral negotiation ①: BCA does not compute JS divergence; RDA uses fixed weights | Declared preference correction's contribution to personalization accuracy |
| `-ExplainConstraint` | Lateral negotiation ②: skip EA confidence filtering in Ranking Policy Agent | Explainability constraints' impact on recommendation quality and explain coverage |
| `-MMR` | MMR re-ranking in Ranking Policy Agent; rank directly by score | Diversity re-ranking's contribution to reducing genre concentration (intra-list diversity) |
| `-Feedback` | Feedback Agent disabled; no profile updates; RDA arm records frozen | Online learning's contribution to long-term recommendation accuracy improvement |

**Evaluation metrics** (applied to all ablation groups and the full system):
- Precision@10, Recall@10, NDCG@10
- Intra-List Diversity (ILD)
- Novelty
- Explain Coverage

---

## 8. Persistent Storage Architecture

### 8.1 PostgreSQL Schema

```sql
-- User behavior events (migrations/002_user_behavior_events.sql)
CREATE TABLE user_behavior_events (
    id           BIGSERIAL    PRIMARY KEY,
    user_id      VARCHAR(64)  NOT NULL,
    book_id      VARCHAR(64)  NOT NULL,
    event_type   VARCHAR(16)  NOT NULL,  -- view/click/finish/rate/skip
    weight       FLOAT        NOT NULL,
    rating       SMALLINT,
    duration_sec INT,
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX ON user_behavior_events(user_id, created_at DESC);
CREATE INDEX ON user_behavior_events(book_id);

-- User profiles (migrations/003_user_profiles.sql)
CREATE TABLE user_profiles (
    user_id        VARCHAR(64)  PRIMARY KEY,
    profile_vector FLOAT[]      NOT NULL,
    confidence     FLOAT        NOT NULL DEFAULT 0.2,
    event_count    INT          NOT NULL DEFAULT 0,
    cold_start     BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at     TIMESTAMPTZ  DEFAULT NOW()
);
```

### 8.2 Redis Key Namespace

| DB | Key Pattern | Owner | Content |
|---|---|---|---|
| 0 | `session:{conversation_id}` | Reading Concierge | Per-session structured context |
| 1 | `bandit:{context_type}:{action_hash}` | RDA | `{trials, avg_reward}` |
| 2 | `fa:queue:{user_id}` | Feedback Agent | Behavior event buffer |
| 2 | `fa:global_rating_count` | Feedback Agent | Global rating event counter |

### 8.3 Offline Index Files

| File | Generator Script | Consumer Agent | Description |
|---|---|---|---|
| `data/book_faiss.index` | `build_book_faiss_index.py` | Recall Agent | Faiss HNSW book vector index |
| `data/als_model.npz` | `build_cf_model.py` | Recall Agent | ALS collaborative filtering model |
| `data/user_sim.bin` | `build_cf_model.py` | Recall Agent | Hnswlib user similarity index |
| `partners/online/book_content_agent/proj_matrix.npy` | Generated at BCA init | Book Content Agent | 256×384 projection matrix |

---

*End of Document*
