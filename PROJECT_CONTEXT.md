# Project Context
## ACPs-Based Multi-Agent Personalized Book Recommendation System

**Repository**: [ACPs-app / feature/recommendation-optimization](https://github.com/yujinandyanhaoyang/ACPs-app/tree/feature/recommendation-optimization)  
**ACPs Reference Implementation**: [AIP-PUB/ACPs-Demo-Project](https://github.com/AIP-PUB/ACPs-Demo-Project)  
**Document Version**: 2026-03-31 (v2 — Architecture Simplified)  
**Status**: Active Development — System Refactoring in Progress

---

## Revision Notes (v2)

| Change | Detail |
|---|---|
| Agent count | 8 → **6 Agents** |
| RDA layer correction | RDA was incorrectly placed in Layer 1 alongside RC. Corrected: **RDA is a Partner (Neutral Mediator) in Layer 2**, not a second Leader |
| Execution layer merger | Recall Agent (8214) + Ranking Policy Agent (8215) + Explanation Agent (8216) merged into a single **Recommendation Engine Agent (port 8214)** with three internal functional modules |
| ACPs config scope | Only Agents with genuine cross-agent ACPs communication require `acs.json` + CAI certificate. Internal pipeline steps within Recommendation Engine Agent are intra-process module calls, not ACPs messages |
| Negotiation terminology | `query-if` performative replaced with `request (supplement_proposal)` for multi-round Evidence Request, which more accurately reflects FIPA ACL semantics |

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
1. A four-role negotiation architecture (Organizer + Two Proposal Parties + Neutral Mediator) grounded in Mediator-Based Negotiation theory (Jennings et al., 1998), implemented across **6 ACPs-compliant Agents**
2. A Contextual Bandit arbitration mechanism (UCB; Auer et al., 2002) that learns from historical recommendation feedback, enabling decision quality to improve over time
3. Full ACPs protocol compliance across three layers — AIA (identity authentication), ADP (dynamic discovery), and AIP (message semantics) — ensuring all inter-agent communication is cryptographically authenticated and semantically structured
4. A closed-loop online learning system driven by the Feedback Agent, enabling continuous model updates without periodic offline retraining
5. An Iterated Contract Net Protocol with Conditional Re-solicitation for multi-round negotiation: RDA issues `request (supplement_proposal)` Evidence Requests to RPA/BCA when proposal quality is insufficient, with a hard cap of 3 rounds

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
│   └── rec_ranking_agent/          ← To be deprecated; merged into recommendation_engine_agent
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
| Architecture | Only 3 Partners present; missing RDA, Recommendation Engine, Feedback Agents | 🔴 Blocking |
| Architecture | `agents/` and `partners/online/` overlap in responsibility; roles unclear | 🟡 Cleanup required |
| Business Logic | `reading_concierge.py`: no arbitration routing, no GroupMgmt broadcast, no dynamic weight generation | 🔴 Blocking |
| Business Logic | `reader_profile_agent`: no PostgreSQL persistence, no decay-weighted encoding | 🔴 Blocking |
| Business Logic | `book_content_agent`: 12-dim vectors (target: 384-dim); no projection matrix; no alignment validation | 🔴 Blocking |
| Business Logic | `rec_ranking_agent`: pseudo-SVD; to be deprecated and merged into Recommendation Engine Agent | 🔴 Blocking |
| Configuration | All `config.toml` and `prompts.toml` files are empty (0 bytes) | 🔴 Blocking |
| Database | `001_initial_schema.sql` lacks `user_behavior_events` and `user_profiles` tables | 🔴 Blocking |
| ACPs Compliance | All AICs are placeholders; ATR formal registration not completed | 🟡 Required |
| Certificates | `certs/` contains dev self-signed certificates, not ATR-issued CAI certificates | 🟡 Required |

---

## 3. Target System Architecture

### 3.1 System Layering (v2 — 6 Agents)

```
┌──────────────────────────────────────────────────────────┐
│  Layer 0: User Interaction Layer                          │
│  Web Demo / API Entry Point                               │
└───────────────────────────┬──────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────┐
│  Layer 1: Coordination Layer                              │
│  Reading Concierge  (port 8210)  ★ ONLY Leader           │
└────────────┬──────────────────────────────────────────────┘
             ↓ GroupMgmt broadcast
┌──────────────────────────────────────────────────────────┐
│  Layer 2: Proposal & Arbitration Layer  (all Partners)    │
│  Reader Profile Agent      (port 8211)  Proposal Party A  │
│  Book Content Agent        (port 8212)  Proposal Party B  │
│  Recommendation Decision Agent (port 8213) Neutral Mediator│
│                                                           │
│  ◀── Lateral Negotiation: Profile Proposal / Content     │
│       Proposal / Counter-Proposal / Evidence Request /   │
│       Supplementary Inform ──▶                           │
└───────────────────────────┬──────────────────────────────┘
                             ↓ Arbitration Result → RC → dispatch
┌──────────────────────────────────────────────────────────┐
│  Layer 3: Execution Layer                                 │
│  Recommendation Engine Agent  (port 8214)                 │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ RecallModule      Faiss HNSW (ANN) + ALS (CF)       │ │
│  │ RankingModule     4-dim scoring + MMR re-ranking     │ │
│  │ ExplanationModule Heuristic confidence + LLM rationale│ │
│  └─────────────────────────────────────────────────────┘ │
└───────────────────────────┬──────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────┐
│  Layer 4: Feedback & Perception Layer                     │
│  Feedback Agent  (port 8215)                              │
└──────────────────────────────────────────────────────────┘
```

**Design rationale for merging Recall / Ranking / Explanation into a single Agent**:

The boundary criterion for an independent ACPs Agent is whether the entity requires **autonomous negotiation capability** — i.e., private objectives, proactive communication, and internal state that evolves independently. Recall, Ranking, and Explanation modules satisfy none of these criteria:
- They hold no private objectives
- They do not initiate any inter-agent communication
- They execute a deterministic pipeline: input → processing → output

All three are therefore functional modules within the Recommendation Engine Agent's internal pipeline, communicating via intra-process function calls rather than ACPs messages. This eliminates three unnecessary `acs.json` configurations, three CAI certificates, and three DSP registrations, reducing ACPs protocol overhead and improving system stability.

### 3.2 Agent Communication Map

```
User
 │
 │ natural language request
 ▼
Reading Concierge (Leader, port 8210)
 │
 ├─ GroupMgmt broadcast (request) ──────────────────────────────┐
 │                                                               │
 ▼                                                               ▼
Reader Profile Agent (port 8211)              Book Content Agent (port 8212)
 │ Profile Proposal                            │ Content Proposal
 │ {profile_vector, confidence,                │ {divergence_score, weight_suggestion,
 │  strategy_suggestion}                       │  coverage_report}
 │                                             │
 │  [if divergence > 0.4]                      │ Counter-Proposal
 │                                             │ {reason, counter_strategy}
 │                                             │
 └─────────────────────► Recommendation Decision Agent (port 8213) ◄──┘
                          │
                          │ [if confidence < θ or fields missing]
                          │ Evidence Request (request supplement_proposal)
                          │ ─────────────────────────────────────────────►  RPA / BCA
                          │                                                    │
                          │ Supplementary Inform (inform)                      │
                          │ ◄─────────────────────────────────────────────────┘
                          │
                          │ Arbitration Result
                          │ {action, final_weights, mmr_lambda, strategy}
                          ▼
                    Reading Concierge (routes downstream)
                          │
                          │ request: {profile_vector, weights, mmr_lambda, ...}
                          ▼
                    Recommendation Engine Agent (port 8214)
                          │
                          │  [Internal pipeline — intra-process, not ACPs]
                          │  RecallModule → RankingModule ↔ ExplanationModule → RankingModule
                          │
                          │ inform: {recommendations[], explanations{}}
                          ▼
                    Reading Concierge → User: top-5 + rationales

[Asynchronous feedback loop]
User behavior events ──► Feedback Agent (port 8215)
                          │
                          ├─ inform ──► RDA: reward signal rₜ
                          ├─ inform ──► RPA: profile update (≥20 events/user)
                          └─ inform ──► Recommendation Engine Agent: CF retrain (≥500 ratings)
```

### 3.3 Complete Interaction Sequence (v2)

```
t0   User request → Reading Concierge
       LLM parses user intent → structured task parameters
       GroupMgmt broadcast → Reader Profile Agent + Book Content Agent (parallel)
       RC also notifies RDA to stand by for incoming proposals

t1   [Parallel execution]
     Reader Profile Agent:
       Load behavior sequence from PostgreSQL (90-day window, decay-weighted)
       Decay encoding: wₜ = e^{-λ(T-t)}, λ = 0.05
       Encode → profile_vector (256-dim) + confidence ∈ [0, 1]
       Cold-start guard: event_count < 5 → force confidence ≤ 0.25, cold_start = true
       → Profile Proposal to RDA: {profile_vector, confidence, behavior_genres, strategy_suggestion}

     Book Content Agent:
       Encode via sentence-transformers (all-MiniLM-L6-v2) → book_vectors (384-dim)
       Project to 256-dim user space via proj_matrix.npy
       Compute JS divergence between declared preferences and behavioral genres
       → Content Proposal to RDA: {divergence_score, alignment_status, weight_suggestion, coverage_report}
       [If divergence > 0.4: proactively send Counter-Proposal to RDA]
         Counter-Proposal: {reason: "preference divergence", counter_strategy: "explore", mmr_lambda: 0.65}

t2   RDA receives Profile Proposal + Content Proposal (+ optional Counter-Proposal)
     → Proposal Quality Assessment:
         Trigger Evidence Request if ANY of:
           - confidence < 0.3  (cold-start / inactive user)
           - weight_suggestion or coverage_report is null  (BCA incomplete)
           - divergence > 0.7 AND confidence > 0.6  (extreme misalignment)
           - Counter-Proposal received but no counter_proposal field  (veto without alternative)

t3   [If Evidence Request triggered — Iterated Contract Net Protocol]
     RDA → RPA: request {action: supplement_proposal, required_fields: [cold_start_prior, adjusted_confidence]}
     RDA → BCA: request {action: supplement_proposal, required_fields: [fallback_strategy, exploration_budget]}
     RPA → RDA: inform {adjusted_confidence, demographic_prior, profile_vector_updated}
     BCA → RDA: inform {fallback_strategy, exploration_budget}
     → Re-assess proposal quality; repeat up to max 3 rounds
     [If round = 3 and still insufficient: force convergence using best available data + conservative prior]

t4   RDA Contextual Bandit Arbitration (UCB):
       Map context: f(confidence, divergence) → one of 4 context classes
       Query Redis arm records for current context class
       UCB(a) = r̄(a) + c·√(ln N / n(a)),  c = 1.41
       Tie-breaking: if |UCB_best − UCB_second| ≤ 0.05 → adopt RPA's strategy_suggestion
       Generate Arbitration Result: {action, final_weights, mmr_lambda, strategy, min_coverage, ...}
       → Return Arbitration Result to Reading Concierge

t5   Reading Concierge routes dispatch to Recommendation Engine Agent:
       {profile_vector, ann_weight, cf_weight, score_weights, mmr_lambda,
        confidence_penalty_threshold, min_coverage, required_evidence_types}

t6   Recommendation Engine Agent — Internal Pipeline:
     RecallModule:
       ANN path: Faiss HNSW, ef_search=100, top_k=200, recall_source="ann"
       CF  path: Hnswlib top-50 similar users → ALS inference, top_k=100, recall_source="cf"
       Merge and deduplicate → candidates[] (~250 books)

     RankingModule Round 1:
       Four-dimensional scoring (content / cf / novelty / recency)
       → preliminary_ranked_list (top-50)

     ExplanationModule Phase 1 (heuristic, no LLM):
       Compute explain_confidence per candidate:
         content_sim > 0.5      → +0.30
         cf_neighbors present   → +0.30
         matched_prefs non-empty → +0.20
         kg_features present    → +0.20
       → confidence_list {book_id: float}

     RankingModule Round 2:
       Apply EA penalty: score × 0.7 if confidence < threshold
       MMR re-ranking: MMR(dᵢ) = λ·Rel(dᵢ) − (1−λ)·max_{dⱼ∈S} cos(d⃗ᵢ, d⃗ⱼ)
       → final_ranked_list (top-5)

     ExplanationModule Phase 2 (LLM — gpt-4o, temp=0.4):
       Generate personalized rationale for each book in final_ranked_list
       → explanations {book_id: text}

     → inform Reading Concierge: {recommendations[], engine_meta{}}

t7   Reading Concierge assembles response → returns top-5 + rationales to User

[Asynchronous feedback loop]
t8   User behavior events → DSP Webhook → Feedback Agent
       Map event types to reward weights
       → inform → RDA: {context_type, action, reward=rₜ, conversation_id}
         RDA updates arm_record[context_type][action]
       → inform → RPA: {trigger: update_profile}  (threshold: ≥20 events/user)
       → inform → Recommendation Engine Agent: {trigger: retrain_cf}  (threshold: ≥500 rating events globally)
```

### 3.4 Persistent Storage Architecture

| Storage | Technology | Owner Agent | Purpose |
|---|---|---|---|
| Relational DB | PostgreSQL | Reader Profile Agent | User behavior sequences and profile vectors |
| Vector Index | Faiss HNSW | Recommendation Engine Agent (RecallModule) | Book semantic vector retrieval |
| User Similarity Index | Hnswlib | Recommendation Engine Agent (RecallModule) | CF user similarity lookup |
| Session Store | Redis DB 0 | Reading Concierge | Per-session context |
| Bandit Arm Records | Redis DB 1 | Recommendation Decision Agent | Contextual bandit state persistence |
| Feedback Queue | Redis DB 2 | Feedback Agent | Behavior event buffer and global counters |

---

## 4. Agent Specifications

### 4.1 Agent Summary Table (v2 — 6 Agents)

| Agent | Port | ACPs Role | Layer | Private Objective | LLM | `acs.json` + CAI Cert |
|---|---|---|---|---|---|---|
| Reading Concierge | 8210 | `leader` | 1 | Maintain negotiation order | ✅ Intent parsing | ✅ Required |
| Reader Profile Agent | 8211 | `partner-rpa` | 2 | Maximize accuracy | ✅ Preference induction | ✅ Required |
| Book Content Agent | 8212 | `partner-bca` | 2 | Maximize diversity | ❌ | ✅ Required |
| Recommendation Decision Agent | 8213 | `partner-rda` | 2 | Minimize long-term regret | ❌ | ✅ Required |
| Recommendation Engine Agent | 8214 | `partner-engine` | 3 | — (execution) | ✅ Rationale (ExplanationModule) | ✅ Required |
| Feedback Agent | 8215 | `partner-fa` | 4 | — (perception) | ❌ | ✅ Required |

> **Note**: All 6 Agents require `acs.json` + CAI certificate because all 6 participate in ACPs inter-agent communication. The Recommendation Engine Agent communicates with RC (receives dispatch request, returns results) and with Feedback Agent (receives CF retrain trigger) — both are genuine ACPs messages. The internal Recall/Ranking/Explanation pipeline within the Engine Agent are intra-process module calls and do not require separate ACPs identities.

---

### 4.2 Reading Concierge

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
- Notify RDA to stand by for incoming proposals
- Aggregate proposals and forward to RDA for arbitration
- Receive Arbitration Result from RDA → route execution dispatch to Recommendation Engine Agent
- Receive Engine Agent results → assemble final response → return to user

**Explicitly does NOT**:
- Perform arbitration or generate recommendation weights
- Access user profile database or book vector index directly
- Take sides on any proposal

**`config.toml` key parameters**:
```toml
[server]
port = 8210

[server.mtls]
cert = "certs/<AIC>.pem"
key  = "certs/<AIC>.key"
ca   = "certs/trust-bundle.pem"
verify_client = true

[llm]
model = "gpt-4o"
temperature = 0.3
max_tokens = 512

[redis]
url = "redis://localhost:6379/0"
```

---

### 4.3 Reader Profile Agent

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
- LLM semantic induction → preference description → `sentence-transformers` encode → `profile_vector` (256-dim)
- Compute `confidence` ∈ [0, 1] based on event count, recency distribution, behavioral diversity
- Cold-start guard: event_count < 5 → force `confidence ≤ 0.25`, `cold_start = true`

**Negotiation interface**:
- Send **Profile Proposal** to RDA: `{profile_vector, confidence, cold_start, behavior_genres, recent_authors, strategy_suggestion, evidence_summary}`
- Respond to RDA **Evidence Request**: supplement `{demographic_prior, declared_interests, adjusted_confidence, profile_vector_updated}`
- Receive Feedback Agent trigger → incremental profile update

**`config.toml` key parameters**:
```toml
[server]
port = 8211

[server.mtls]
cert = "certs/<AIC>.pem"
key  = "certs/<AIC>.key"
ca   = "certs/trust-bundle.pem"
verify_client = true

[database]
dsn = "postgresql://user:pass@localhost:5432/acps"

[model]
LAMBDA = 0.05
WARM_THRESHOLD = 20
VECTOR_DIM = 256
```

---

### 4.4 Book Content Agent

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
- Project to 256-dim user space via `proj_matrix.npy` (256×384)
- Compute JS divergence between user's declared preferences and behavioral genre distribution → `AlignmentReport`

**Negotiation interface**:
- Send **Content Proposal** to RDA: `{divergence_score, alignment_status, declared_genres, behavior_genres, weight_suggestion, coverage_report}`
- If `divergence > 0.4`: proactively send **Counter-Proposal** to RDA: `{reason, divergence_score, counter_proposal: {strategy, mmr_lambda}}`
- Respond to RDA **Evidence Request**: supplement `{fallback_strategy, exploration_budget, popularity_fallback}`

**`config.toml` key parameters**:
```toml
[server]
port = 8212

[server.mtls]
cert = "certs/<AIC>.pem"
key  = "certs/<AIC>.key"
ca   = "certs/trust-bundle.pem"
verify_client = true

[model]
ENCODER_MODEL = "all-MiniLM-L6-v2"
PROJ_MATRIX_PATH = "proj_matrix.npy"
MISMATCH_THRESHOLD = 0.4
```

---

### 4.5 Recommendation Decision Agent

| Property | Value |
|---|---|
| Port | 8213 |
| ACPs Role | `partner-rda` |
| Academic Classification | Cognitive Agent — Neutral Mediator |
| Private Objective | Minimize long-term recommendation regret (Regret Minimization; Auer et al., 2002) |
| LLM Calls | ❌ |
| `prompts.toml` | Not required |
| Skills | `rda.arbitrate`, `rda.request_evidence` |

**Why RDA is in Layer 2 (not Layer 1)**:
RDA is a **Partner Agent**, not a Leader. It holds no authority over the system's task flow. RC (the sole Leader) organizes the negotiation; RDA participates as a neutral third party that arbitrates between RPA and BCA proposals. RDA's arbitration result is returned to RC, which then routes the execution dispatch — this preserves the Leader's routing authority.

**Arbitration Protocol (Iterated Contract Net with Conditional Re-solicitation)**:

**Step 1 — Proposal Quality Assessment**

Trigger **Evidence Request** (`request`, `action: supplement_proposal`) if ANY condition holds:
- `confidence < 0.3` → RDA → RPA: `{required_fields: [cold_start_prior, adjusted_confidence]}`
- `weight_suggestion` or `coverage_report` is null → RDA → BCA: `{required_fields: [complete_weight_suggestion]}`
- `divergence > 0.7` AND `confidence > 0.6` → RDA → both: `{required_fields: [extended_evidence]}`
- Counter-Proposal received without `counter_proposal` field → RDA → BCA: `{required_fields: [fallback_strategy]}`

Max rounds: 3. After round 3, force convergence.

**Step 2 — Context Identification**

$$\text{context} = f(\text{confidence},\ \text{divergence}) \in \{\texttt{high\_conf\_low\_div},\ \texttt{low\_conf\_high\_div},\ \texttt{low\_conf\_low\_div},\ \texttt{high\_conf\_high\_div}\}$$

**Step 3 — UCB Arbitration**

$$\text{UCB}(a) = \bar{r}(a) + c\sqrt{\frac{\ln N}{n(a)}}, \quad c = 1.41$$

- Query `arm_records[context_type]` from Redis DB 1
- Select action with highest UCB value
- Tie-breaking (|UCB_best − UCB_second| ≤ 0.05): adopt RPA's `strategy_suggestion` (accuracy side priority)
- Cold-start guard: if `trials < 20` for all arms → apply conservative prior (balanced weights)

**Step 4 — Generate Arbitration Result**

```json
{
  "performative": "inform",
  "to": "leader-rc",
  "content": {
    "action": "balanced",
    "final_weights": {
      "ann_weight": 0.58, "cf_weight": 0.42,
      "content_score_weight": 0.50, "cf_score_weight": 0.25,
      "novelty_weight": 0.15, "recency_weight": 0.10
    },
    "mmr_lambda": 0.55,
    "strategy": "balanced",
    "confidence_penalty_threshold": 0.6,
    "min_explain_coverage": 0.6,
    "required_evidence_types": ["content_sim", "cf_neighbors"]
  }
}
```

**Step 5 — Reward Signal Update** (from Feedback Agent)

```
arm_record[context_type][action].trials += 1
arm_record[context_type][action].avg_reward =
    (avg_reward × (trials − 1) + r_t) / trials
```

**`config.toml` key parameters**:
```toml
[server]
port = 8213

[server.mtls]
cert = "certs/<AIC>.pem"
key  = "certs/<AIC>.key"
ca   = "certs/trust-bundle.pem"
verify_client = true

[redis]
url = "redis://localhost:6379/1"

[bandit]
UCB_C = 1.41
MAX_ROUNDS = 3
MIN_TRIALS_FOR_CONFIDENCE = 20
```

---

### 4.6 Recommendation Engine Agent

| Property | Value |
|---|---|
| Port | 8214 |
| ACPs Role | `partner-engine` |
| Academic Classification | Reactive Agent — Execution Layer |
| Private Objective | None (deterministic execution pipeline) |
| LLM Calls | ✅ ExplanationModule Phase 2 only (gpt-4o) |
| `prompts.toml` | Required (ExplanationModule rationale template) |
| Skills | `engine.recommend`, `engine.retrain_cf` |

**ACPs Interface**:
- Receive `request` from RC: `{profile_vector, ann_weight, cf_weight, score_weights, mmr_lambda, confidence_penalty_threshold, min_coverage, required_evidence_types}`
- Return `inform` to RC: `{recommendations[], engine_meta{}}`
- Receive `inform` from Feedback Agent: `{trigger: retrain_cf}` → invoke `build_cf_model.py`

**Internal Pipeline (intra-process module calls — not ACPs)**:

```
RecallModule.run(profile_vector, ann_weight, cf_weight)
    ANN:  Faiss HNSW, ef_search=100, top_k=200
    CF:   Hnswlib top-50 similar users → ALS inference, top_k=100
    Merge → candidates[] (~250)
         ↓
RankingModule.score_round1(candidates, score_weights)
    → preliminary_ranked_list (top-50)
         ↓
ExplanationModule.assess_confidence(preliminary_ranked_list)
    Heuristic scoring (no LLM):
      content_sim > 0.5       → +0.30
      cf_neighbors present    → +0.30
      matched_prefs non-empty → +0.20
      kg_features present     → +0.20
    → confidence_list {book_id: float}
         ↓
RankingModule.rerank_round2(preliminary_ranked_list, confidence_list, mmr_lambda)
    EA penalty: score × 0.7 if confidence < threshold
    MMR: MMR(dᵢ) = λ·Rel(dᵢ) − (1−λ)·max_{dⱼ∈S} cos(d⃗ᵢ, d⃗ⱼ)
    → final_ranked_list (top-5)
         ↓
ExplanationModule.generate_rationale(final_ranked_list)
    LLM: gpt-4o, temperature=0.4, max_tokens=300
    → explanations {book_id: text}
```

**`config.toml` key parameters**:
```toml
[server]
port = 8214

[server.mtls]
cert = "certs/<AIC>.pem"
key  = "certs/<AIC>.key"
ca   = "certs/trust-bundle.pem"
verify_client = true

[index]
FAISS_INDEX_PATH = "data/book_faiss.index"
ALS_MODEL_PATH   = "data/als_model.npz"
HNSWLIB_PATH     = "data/user_sim.bin"

[llm]
model       = "gpt-4o"
temperature = 0.4
max_tokens  = 300

[ranking]
CONFIDENCE_PENALTY_THRESHOLD = 0.6
PENALTY_MULTIPLIER           = 0.7
DEFAULT_MMR_LAMBDA           = 0.5

[quality]
DEFAULT_MIN_COVERAGE = 0.6
```

---

### 4.7 Feedback Agent

| Property | Value |
|---|---|
| Port | 8215 |
| ACPs Role | `partner-fa` |
| Academic Classification | Environment Agent — Perception Layer |
| Private Objective | None (closes the system feedback loop) |
| LLM Calls | ❌ |
| `prompts.toml` | Not required |
| Skills | `fa.receive_event`, `fa.compute_reward` |

**Academic positioning**: Feedback Agent satisfies Russell & Norvig's broadest Agent definition — sensors are the DSP Webhook (user behavior events); actuators are the `inform` messages to RDA, RPA, and Recommendation Engine Agent. Its value lies in transforming the system from an **open-loop** to a **closed-loop** recommender.

**Core Logic**:
- `POST /feedback/webhook`: receive DSP behavior events; map to reward weights; enqueue in Redis DB 2
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
  - After every completed session → `inform(RDA, reward=rₜ, context_type=ctx, action=action)`
  - Per-user event count ≥ 20 → `inform(RPA, trigger="update_profile")`
  - Global rating event count ≥ 500 → `inform(RecommendationEngineAgent, trigger="retrain_cf")`

**`config.toml` key parameters**:
```toml
[server]
port = 8215

[server.mtls]
cert = "certs/<AIC>.pem"
key  = "certs/<AIC>.key"
ca   = "certs/trust-bundle.pem"
verify_client = true

[redis]
url = "redis://localhost:6379/2"

[trigger]
USER_UPDATE_THRESHOLD  = 20
CF_RETRAIN_THRESHOLD   = 500

[agents]
RPA_AIC    = "<AIC-RPA>"
ENGINE_AIC = "<AIC-ENGINE>"
RDA_AIC    = "<AIC-RDA>"
```

---

## 5. ACPs Protocol Compliance Design

### 5.1 Three-Layer Protocol Satisfaction

| ACPs Layer | Requirement | Satisfaction Method |
|---|---|---|
| **AIA** (Identity Authentication) | Each Agent holds ATR-issued CAI certificate; all communication uses mTLS mutual authentication | 6 Agents each hold independent AIC + CAI certificate; `verify_client = true` |
| **ADP** (Discovery Protocol) | Agents discover each other via DSP; no hardcoded endpoints | Each Agent registers its endpoint and skills in DSP on startup; RC performs DSP discovery then applies local pre-configured AIC pinning to ensure stable routing in mixed public index results |
| **AIP** (Interaction Protocol) | Messages carry `performative` semantics; multi-round negotiation tracked by `conversation_id` | All messages contain `from`, `to`, `performative`, `conversation_id` |

### 5.2 AIP Message Semantics Table (v2)

| Message Scenario | Performative | Sender → Receiver | Label on Architecture Diagram |
|---|---|---|---|
| RC broadcasts task | `request` | RC → RPA, BCA | GroupMgmt broadcast |
| RC notifies RDA to stand by | `request` | RC → RDA | Prepare for proposals |
| RPA submits user profile evidence | `propose` | RPA → RDA | **Profile Proposal** |
| BCA submits content alignment evidence | `propose` | BCA → RDA | **Content Proposal** |
| BCA emits divergence veto | `reject-proposal` | BCA → RDA | **Counter-Proposal** |
| RDA requests supplementary evidence | `request` | RDA → RPA / BCA | **Evidence Request** |
| RPA/BCA returns supplementary data | `inform` | RPA/BCA → RDA | **Supplementary Inform** |
| RDA returns arbitration result to RC | `inform` | RDA → RC | **Arbitration Result** |
| RC dispatches execution to Engine | `request` | RC → Engine Agent | Execution dispatch |
| Engine Agent returns results | `inform` | Engine → RC | Recommendations + explanations |
| FA sends reward signal | `inform` | FA → RDA | reward signal |
| FA triggers profile update | `inform` | FA → RPA | profile update |
| FA triggers CF retraining | `inform` | FA → Engine Agent | CF retrain |

### 5.3 Standard Agent Directory Structure

Each Agent under `partners/online/<agent_name>/`:

```
partners/online/<agent_name>/
├── agent.py           # Business logic
├── acs.json           # ACS definition: AIC, capability declaration, endpoint, skills
├── config.toml        # Runtime config: LLM, port, [server.mtls] cert paths, business params
├── prompts.toml       # Prompt templates (RC / RPA / Engine only)
├── <AIC>.pem          # CAI certificate (ATR-issued)
├── <AIC>.key          # Private key
└── trust-bundle.pem   # CA trust bundle
```

### 5.4 Why ACPs Communication Is Not Equivalent to Inter-Process Function Calls

1. **Identity layer**: Every message is preceded by a mTLS handshake with ATR-issued certificates. A function call has no concept of caller identity verification.

2. **Discovery layer**: RC uses DSP for runtime discovery and synchronization, then applies local AIC pinning for the six in-system agents to avoid nondeterministic same-type hits in the public index. This protocol-level location resolution remains architecturally impossible with pure function calls.

3. **Semantics layer**: Messages carry `performative` values: `propose`, `reject-proposal`, `request (supplement_proposal)`. These semantics — proposal, veto, evidence request — cannot be expressed in a function's input-output model.

4. **Asynchrony**: FA's `inform` to RDA is asynchronous — FA continues processing the next event without waiting for RDA's response.

---

## 6. Academic Argumentation Framework

### 6.1 Why This System Constitutes Genuine Multi-Agent Collaboration

**Core claim**: The recommendation result is an emergent output produced by negotiation among multiple autonomous entities with opposing objectives — not the deterministic output of any single module.

**Argument 1 — Externally grounded goal conflict**

The opposing objectives of RPA (accuracy) and BCA (diversity) correspond to independently established research problems:
- Filter Bubble problem (Pariser, 2011)
- Accuracy-Diversity Dilemma (Kunaver & Požrl, 2017)

**Argument 2 — Non-deterministic negotiation outcomes**

RDA's UCB arbitration depends on its historical arm records (internal private state). Identical conflict inputs at different times yield different arbitration results because arm records evolve continuously. This violates referential transparency — the defining property of function calls.

**Argument 3 — Proactive inter-agent communication**

BCA's `Counter-Proposal` is initiated by BCA's own computation upon detecting `divergence > 0.4`, not triggered by any external call. RDA's `Evidence Request` is proactively initiated when RDA's internal quality assessment deems proposals insufficient.

**Argument 4 — Mediator-Based Negotiation architecture**

The four-role collaboration structure (Organizer + Proposal Party A + Proposal Party B + Neutral Mediator) directly instantiates the Mediator-Based Negotiation model (Jennings et al., 1998). RDA's neutrality is structurally guaranteed: it holds no stake in either accuracy or diversity.

**Argument 5 — Merger of execution modules strengthens the MAS claim**

The simplification of Recall/Ranking/Explanation into a single Engine Agent concentrates the MAS claim precisely on the agents that genuinely satisfy the autonomy criterion. This eliminates a potential challenge: "most of your agents are just pipeline steps." Post-merger, the 5 non-Engine Agents (RC, RPA, BCA, RDA, FA) all have clear autonomous behaviors, private states, or feedback responsibilities.

### 6.2 Anticipated Defense Challenges and Responses

| Challenge | Response |
|---|---|
| "You reduced to 6 Agents — isn't the system simpler than claimed?" | The simplification strengthens the MAS claim. The 3 merged modules were deterministic pipeline steps with no private objectives, no proactive communication, and no evolving internal state — they did not satisfy any Agent autonomy criterion. The 6-Agent design is architecturally more rigorous. |
| "Most Agents are just functional modules, not real Agents." | RC (organizer), RPA (accuracy advocate), BCA (diversity advocate), RDA (neutral mediator), and FA (environment perceiver) all satisfy specific autonomy criteria. The Engine Agent is a reactive execution component — a legitimate role in MAS execution layers (Ferber, 1999). |
| "Your negotiation is just conditional branching — that's a function call." | RDA's UCB arbitration depends on its historical arm records. Identical inputs at different times yield different outputs. This violates referential transparency and satisfies Wooldridge's autonomy criterion. |
| "Your private objectives are invented to justify the design." | RPA and BCA's objectives correspond to the Accuracy-Diversity Dilemma (Kunaver, 2017) and the Filter Bubble problem (Pariser, 2011) — conflicts that exist independently of this system design. |
| "Evidence Request is just a query — that's not negotiation." | Evidence Request is the conditional re-solicitation step of an Iterated Contract Net Protocol. It is triggered by RDA's internal quality assessment, not by any external instruction. Its purpose is to obtain sufficient evidence for a well-grounded arbitration decision — a canonical step in formal negotiation protocols. |
| "RDA's arbitration is just a fixed rule set." | RDA uses the UCB algorithm; its arm records are updated by real user behavior reward signals after every session. Its behavior evolves over time — early and late sessions facing identical inputs may produce different arbitration results. No static rule set can replicate this. |

---

## 7. Ablation Study Design

| Ablation Group | Removed Component | Contribution Being Validated |
|---|---|---|
| `-CF` | CF path in RecallModule; ANN only | Collaborative filtering's contribution to recall coverage and cold-start performance |
| `-Alignment` | BCA does not compute JS divergence; RDA uses fixed weights (no Counter-Proposal) | Declared preference correction's contribution to personalization accuracy |
| `-ExplainConstraint` | ExplanationModule confidence scoring disabled; RankingModule uses raw scores only | Explainability constraints' impact on recommendation quality and explain coverage |
| `-MMR` | MMR re-ranking disabled; rank directly by composite score | Diversity re-ranking's contribution to reducing genre concentration (intra-list diversity) |
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

| File | Generator Script | Consumer | Description |
|---|---|---|---|
| `data/book_faiss.index` | `build_book_faiss_index.py` | Engine Agent (RecallModule) | Faiss HNSW book vector index |
| `data/als_model.npz` | `build_cf_model.py` | Engine Agent (RecallModule) | ALS collaborative filtering model |
| `data/user_sim.bin` | `build_cf_model.py` | Engine Agent (RecallModule) | Hnswlib user similarity index |
| `partners/online/book_content_agent/proj_matrix.npy` | Generated at BCA init | Book Content Agent | 256×384 projection matrix |

---

*End of Document — Version 2026-03-31 (v2)*
