# System Upgrade Plan
## ACPs-Based Multi-Agent Personalized Book Recommendation System

**Repository**: [ACPs-app / feature/recommendation-optimization](https://github.com/yujinandyanhaoyang/ACPs-app/tree/feature/recommendation-optimization)  
**Target Architecture**: 1 Leader + 5 Partners (6 Agents total)  
**Document Version**: 2026-03-31 (v2 — Architecture Simplified)  
**Academic Framework**: Agent Coordination Protocol Standard (ACPs)

---

## Revision Notes (v2)

| Change | Detail |
|---|---|
| Agent count | 8 → **6 Agents** |
| RDA layer correction | RDA was incorrectly placed in Layer 1 alongside RC. Corrected: **RDA is a Partner (Neutral Mediator) in Layer 2** |
| Execution layer merger | Recall Agent (8214) + Ranking Policy Agent (8215) + Explanation Agent (8216) merged into **Recommendation Engine Agent (port 8214)** with three internal modules |
| Feedback Agent port | 8217 → **8215** (renumbered after merger) |
| FA config | `RECALL_AIC` → `ENGINE_AIC` |
| Phase 3 scope | Sections 5.1–5.3 rewritten; 5.4 renumbered to 5.2 |

---

## Table of Contents

1. [Current System Status](#1-current-system-status)
2. [Target Architecture Design](#2-target-architecture-design)
3. [Phase 1 — Data Infrastructure Layer](#3-phase-1--data-infrastructure-layer)
4. [Phase 2 — Negotiation & Coordination Layer Refactoring](#4-phase-2--negotiation--coordination-layer-refactoring)
5. [Phase 3 — Execution & Perception Layer Implementation](#5-phase-3--execution--perception-layer-implementation)
6. [Phase 4 — ACPs Protocol Compliance](#6-phase-4--acps-protocol-compliance)
7. [Phase 5 — Experimental Evaluation](#7-phase-5--experimental-evaluation)
8. [Phase 6 — Thesis Writing & Defense Preparation](#8-phase-6--thesis-writing--defense-preparation)
9. [Phase Dependency Overview](#9-phase-dependency-overview)
10. [File Operation Checklist](#10-file-operation-checklist)

---

## 1. Current System Status

### 1.1 Repository Structure

```
ACPs-app/
├── reading_concierge/              ← Leader; acs.json present (2.8 KB);
│   │                                 config.toml and prompts.toml are empty (0 bytes)
│   └── reading_concierge.py        ← 54 KB; core logic exists but requires refactoring
├── agents/                         ← Legacy codebase; reference only, not runtime entry
│   ├── book_content_agent/
│   ├── reader_profile_agent/
│   └── rec_ranking_agent/
├── partners/online/                ← ACPs standard directory; currently 3 Partners only
│   ├── book_content_agent/         ← acs.json present; config/prompts empty
│   ├── reader_profile_agent/       ← acs.json present; config/prompts empty
│   └── rec_ranking_agent/          ← To be deprecated; merged into recommendation_engine_agent
├── migrations/
│   └── 001_initial_schema.sql      ← Present; missing behavior-event and profile tables
├── scripts/
│   ├── build_cf_model.py           ← Present
│   ├── build_knowledge_graph.py    ← Present
│   ├── merge_book_corpora.py       ← Present
│   ├── backfill_book_features.py   ← Present
│   ├── backfill_user_events.py     ← Present
│   ├── phase4_benchmark_compare.py ← Present (requires update for new architecture)
│   ├── run_ablation.py             ← Present (requires new ablation modules)
│   ├── phase3_issue_real_certs.sh  ← Present (certificate issuance workflow)
│   ├── phase3_dsp_sync_verify.sh   ← Present (ADP registration verification)
│   └── register_agents_ioa_pub.md  ← Present (ATR registration instructions)
├── base.py                         ← Present (9.2 KB; AIP RPC base class)
├── acps_aip/                       ← Present (protocol implementation layer)
├── certs/                          ← Present (dev self-signed certs; to be replaced)
└── requirements.txt                ← Present
```

### 1.2 Critical Issues

| Category | Issue | Severity |
|---|---|---|
| Architecture | Only 3 Partners; missing RDA, Recommendation Engine Agent, Feedback Agent | 🔴 Blocking |
| Architecture | `agents/` and `partners/online/` directories overlap in responsibility | 🟡 Cleanup required |
| Business Logic | `reading_concierge.py` contains no arbitration routing, no GroupMgmt broadcast | 🔴 Blocking |
| Business Logic | `reader_profile_agent` has no PostgreSQL persistence, no decay-weighted encoding | 🔴 Blocking |
| Business Logic | `book_content_agent` uses 12-dimensional vectors; missing projection matrix and alignment validation | 🔴 Blocking |
| Business Logic | `rec_ranking_agent` uses pseudo-SVD; to be deprecated and merged into Recommendation Engine Agent | 🔴 Blocking |
| Configuration | All Agent `config.toml` and `prompts.toml` files are empty (0 bytes) | 🔴 Blocking |
| Database | `001_initial_schema.sql` lacks `user_behavior_events` and `user_profiles` tables | 🔴 Blocking |
| ACPs Compliance | All AICs are placeholders; ATR formal registration not completed | 🟡 Required |
| Certificates | `certs/` contains dev self-signed certificates, not ATR-issued CAI certificates | 🟡 Required |

---

## 2. Target Architecture Design

### 2.1 System Layering (v2 — 6 Agents)

```
┌────────────────────────────────────────────────────────────┐
│  Layer 0: User Interaction Layer                           │
│  Web Demo / API Entry Point                                │
└──────────────────────────┬─────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│  Layer 1: Coordination Layer                               │
│  Reading Concierge  (port 8210)  ★ ONLY Leader            │
└──────────────────────────┬─────────────────────────────────┘
             ↓ GroupMgmt broadcast
┌────────────────────────────────────────────────────────────┐
│  Layer 2: Proposal & Arbitration Layer  (all Partners)     │
│  Reader Profile Agent         (port 8211)  Proposal Party A│
│  Book Content Agent           (port 8212)  Proposal Party B│
│  Recommendation Decision Agent (port 8213) Neutral Mediator│
└──────────────────────────┬─────────────────────────────────┘
             ↓ Arbitration Result → RC → dispatch
┌────────────────────────────────────────────────────────────┐
│  Layer 3: Execution Layer                                  │
│  Recommendation Engine Agent  (port 8214)                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ RecallModule      Faiss HNSW (ANN) + ALS (CF)      │   │
│  │ RankingModule     4-dim scoring + MMR re-ranking    │   │
│  │ ExplanationModule Heuristic confidence + LLM rationale│ │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────────┬─────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│  Layer 4: Feedback & Perception Layer                      │
│  Feedback Agent  (port 8215)                               │
└────────────────────────────────────────────────────────────┘
```

### 2.2 Complete Interaction Sequence

```
t0   User request → Reading Concierge
       LLM parses intent → structured task parameters
       GroupMgmt broadcast → Reader Profile Agent + Book Content Agent (parallel)
       RC also notifies RDA to stand by for incoming proposals

t1   [Parallel execution]
     Reader Profile Agent:
       Load behavior sequence from PostgreSQL (90-day window, decay-weighted)
       Decay encoding: w_t = e^{-λ(T-t)}, λ = 0.05
       Encode → profile_vector (256-dim) + confidence score
       Cold-start guard: event_count < 5 → force confidence ≤ 0.25, cold_start = true
       → Profile Proposal to RDA: {profile_vector, confidence, behavior_genres, strategy_suggestion}

     Book Content Agent:
       Encode via sentence-transformers → book_vectors (384-dim)
       Project to 256-dim user space; compute JS divergence
       → Content Proposal to RDA: {divergence_score, alignment_status, weight_suggestion, coverage_report}
       [If divergence > 0.4: proactively send Counter-Proposal to RDA]

t2   RDA receives both proposals → Proposal Quality Assessment
       [If quality insufficient: issue Evidence Request (request, supplement_proposal) to RPA/BCA]
       [Max 3 rounds; fallback to conservative prior if not converged]

t3   RDA UCB Arbitration:
       Map context: f(confidence, divergence) → one of 4 context classes
       UCB(a) = r̄(a) + c·√(ln N / n(a)), c = 1.41
       Generate Arbitration Result: {action, final_weights, mmr_lambda, strategy, ...}
       → Return Arbitration Result to Reading Concierge

t4   Reading Concierge routes dispatch to Recommendation Engine Agent:
       {profile_vector, ann_weight, cf_weight, score_weights, mmr_lambda,
        confidence_penalty_threshold, min_coverage, required_evidence_types}

t5   Recommendation Engine Agent — Internal Pipeline:
     RecallModule:
       ANN path: Faiss HNSW, ef_search=100, top_k=200 (recall_source="ann")
       CF  path: Hnswlib top-50 similar users → ALS inference, top_k=100 (recall_source="cf")
       Merge and deduplicate → candidates[] (~250 books)

     RankingModule Round 1:
       Four-dimensional scoring (content / cf / novelty / recency)
       → preliminary_ranked_list (top-50)

     ExplanationModule Phase 1 (heuristic, no LLM):
       Compute explain_confidence per candidate
       → confidence_list {book_id: float}

     RankingModule Round 2:
       Apply confidence penalty (score × 0.7 if confidence < threshold)
       MMR re-ranking → final_ranked_list (top-5)

     ExplanationModule Phase 2 (LLM — gpt-4o, temp=0.4):
       Generate personalized rationale for each book in final_ranked_list
       → explanations {book_id: text}

     → inform Reading Concierge: {recommendations[], engine_meta{}}

t6   Reading Concierge assembles response → returns top-5 + rationales to User

[Asynchronous feedback loop]
t7   User behavior events → DSP Webhook → Feedback Agent
       Compute reward signal r_t
       → inform → RDA: {context_type, action, reward=r_t}   (every completed session)
       → inform → RPA: {trigger: update_profile}             (threshold: ≥20 events/user)
       → inform → Recommendation Engine Agent: {trigger: retrain_cf}  (threshold: ≥500 ratings globally)
```

### 2.3 Agent Specification Summary

| Agent | Port | Role | Private Objective | LLM | prompts.toml |
|---|---|---|---|---|---|
| Reading Concierge | 8210 | Leader / Organizer | Maintain negotiation order | ✅ Intent parsing | Required |
| Reader Profile Agent | 8211 | Partner / Proposal Party A | Maximize user behavioral consistency | ✅ Preference induction | Required |
| Book Content Agent | 8212 | Partner / Proposal Party B | Maximize semantic coverage diversity | ❌ | Not required |
| Recommendation Decision Agent | 8213 | Partner / Neutral Mediator | Minimize long-term recommendation regret | ❌ | Not required |
| Recommendation Engine Agent | 8214 | Partner / Reactive Execution | — | ✅ Rationale generation (ExplanationModule) | Required |
| Feedback Agent | 8215 | Partner / Environment Perception | — | ❌ | Not required |

### 2.4 Academic Justification for Multi-Agent Collaboration

**Argument 1 — Externally grounded goal conflict.** The opposing objectives of Reader Profile Agent (maximizing accuracy) and Book Content Agent (maximizing diversity) correspond to the Filter Bubble problem (Pariser, 2011) and the Accuracy-Diversity Dilemma (Kunaver & Požrl, 2017). These conflicts exist prior to and independently of the system design.

**Argument 2 — Non-deterministic negotiation outcomes.** RDA's UCB arbitration depends on its historical arm records. Identical conflict inputs at different times yield different arbitration results, violating the referential transparency property of function calls.

**Argument 3 — Proactive inter-agent communication.** BCA's Counter-Proposal is initiated by BCA's own internal computation, not triggered by any external call. RDA's Evidence Request is proactively initiated based on RDA's internal quality assessment.

**Argument 4 — ACPs protocol-layer identity.** All Agent-to-Agent communication passes through mTLS mutual authentication (AIA), dynamic endpoint discovery (ADP), and structured performative messaging (AIP).

**Argument 5 — Merger strengthens the MAS claim.** The merged Recall/Ranking/Explanation modules were deterministic pipeline steps with no private objectives and no proactive communication — they did not satisfy any Agent autonomy criterion. Post-merger, all 5 non-Engine Agents have clear autonomous behaviors or feedback responsibilities.

---

## 3. Phase 1 — Data Infrastructure Layer

> **Prerequisite**: None  
> **Gate condition for Phase 2**: Database migrations applied; Faiss index and ALS model files present and loadable.

### 3.1 Database Migration

- [x] Create `migrations/002_user_behavior_events.sql`

```sql
CREATE TABLE user_behavior_events (
    id           BIGSERIAL PRIMARY KEY,
    user_id      VARCHAR(64) NOT NULL,
    book_id      VARCHAR(64) NOT NULL,
    event_type   VARCHAR(16) NOT NULL,
    weight       FLOAT       NOT NULL,
    rating       SMALLINT,
    duration_sec INT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON user_behavior_events(user_id, created_at DESC);
CREATE INDEX ON user_behavior_events(book_id);
```

- [x] Create `migrations/003_user_profiles.sql`

```sql
CREATE TABLE user_profiles (
    user_id        VARCHAR(64) PRIMARY KEY,
    profile_vector FLOAT[]    NOT NULL,
    confidence     FLOAT      NOT NULL DEFAULT 0.2,
    event_count    INT        NOT NULL DEFAULT 0,
    cold_start     BOOLEAN    NOT NULL DEFAULT TRUE,
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);
```

- [x] Apply migrations; verify table structures and indexes

### 3.2 Offline Data Preparation

- [x] Execute `scripts/backfill_book_features.py`
- [x] Execute `scripts/backfill_user_events.py`
- [x] Create `scripts/build_book_faiss_index.py`
  - Batch encode all books via `sentence-transformers` (all-MiniLM-L6-v2), 384-dim output
  - Write to `Faiss IndexHNSWFlat`; persist index file
- [x] Execute `scripts/build_cf_model.py` — output ALS model and Hnswlib user similarity index
- [x] Execute `scripts/build_knowledge_graph.py`

### 3.3 Legacy Directory Cleanup

- [x] Add `agents/README.md`: mark as legacy reference code, not runtime entry point
- [x] Mark `partners/online/rec_ranking_agent/` as deprecated; remove from service startup scripts

### Phase 1 Completion Checklist

```
✅ Table user_behavior_events exists and contains data
✅ Table user_profiles exists
✅ book_faiss.index present and loadable
✅ als_model.npz present and loadable
✅ Hnswlib user similarity index present and loadable
```

---

## 4. Phase 2 — Negotiation & Coordination Layer Refactoring

> **Prerequisite**: Phase 1 complete  
> **Gate condition for Phase 3**: RC can broadcast tasks; RPA/BCA can generate proposals; RDA can complete UCB arbitration and return Arbitration Result to RC.

### 4.1 Reader Profile Agent Refactoring

**Directory**: `partners/online/reader_profile_agent/` (refactor in place)

- [x] Rewrite `agent.py`
  - PostgreSQL connection; `load_behavior_sequence(user_id, window=90 days)`
  - Decay-weighted encoding: w_t = e^{-λ(T-t)}, λ = 0.05
  - Output: `profile_vector` (256-dim) + `confidence` ∈ [0, 1]
  - Cold-start guard: event_count < 5 → force `confidence ≤ 0.25`, `cold_start = true`
  - Negotiation interfaces: `uma.build_profile`, `uma.validate_consistency`, `uma.update_profile`
  - Respond to RDA Evidence Request: supplement `{demographic_prior, adjusted_confidence, profile_vector_updated}`
  - Inbound mention handler: receive Feedback Agent trigger → incremental profile update
- [x] Rewrite `acs.json` — update skills declaration, AIC placeholder
- [x] Populate `config.toml`

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

- [x] Populate `prompts.toml` — semantic preference induction prompt

### 4.2 Book Content Agent Refactoring

**Directory**: `partners/online/book_content_agent/` (refactor in place)

- [x] Rewrite `agent.py`
  - Encode via `sentence-transformers` (all-MiniLM-L6-v2) → 384-dim vectors
  - Load `proj_matrix.npy` (256×384); project book vectors to user space
  - Compute JS divergence → `AlignmentReport`
  - If `divergence > MISMATCH_THRESHOLD`: proactively send Counter-Proposal to RDA
  - Respond to RDA Evidence Request: supplement `{fallback_strategy, exploration_budget}`
- [x] Rewrite `acs.json`
- [x] Populate `config.toml`

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

- [x] Generate `proj_matrix.npy` (256×384)
- [x] Confirm `prompts.toml` not required

### 4.3 Recommendation Decision Agent (New)

**Directory**: `partners/online/recommendation_decision_agent/` (create new)

> **Layer clarification**: RDA is a **Partner Agent in Layer 2**, not a second Leader. RC is the sole Leader. RDA receives proposals from RPA and BCA, performs UCB arbitration, and returns the Arbitration Result to RC — RC then routes the execution dispatch.

- [x] Create `agent.py`
  - Receive Profile Proposal from RPA and Content Proposal from BCA
  - Proposal Quality Assessment: trigger Evidence Request if quality insufficient
    - `confidence < 0.3` → request supplementary evidence from RPA
    - `weight_suggestion` or `coverage_report` is null → request from BCA
    - `divergence > 0.7` AND `confidence > 0.6` → request extended evidence from both
    - Counter-Proposal received without `counter_proposal` field → request fallback from BCA
  - Max 3 Evidence Request rounds; fallback to conservative prior if not converged
  - Context identification: f(confidence, divergence) → 4 context classes
  - UCB arbitration: UCB(a) = r̄(a) + c√(ln N / n(a)), c = 1.41
  - Return Arbitration Result to RC (not direct dispatch to execution agents)
  - Inbound mention handler: receive Feedback Agent reward signal → update arm record
  - Persist arm records in Redis DB 1
- [x] Create `acs.json`
- [x] Create `config.toml`

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

### 4.4 Reading Concierge Refactoring

**Directory**: `reading_concierge/`

- [x] Refactor `reading_concierge.py`
  - **Remove**: all arbitration logic, weight computation, divergence detection
  - **Retain**: LLM intent parsing, GroupMgmt broadcast, inter-agent message routing, response assembly
  - **Add**:
    - Notify RDA to stand by on session start
    - Aggregate proposals from RPA and BCA → forward to RDA
    - Receive Arbitration Result from RDA → compose dispatch → send to Recommendation Engine Agent
    - Receive Engine Agent results → assemble final response → return to user
- [x] Create `reading_concierge/session_store.py` — Redis session context wrapper
- [x] Populate `config.toml`

```toml
[server]
port = 8210

[server.mtls]
cert = "certs/<AIC>.pem"
key  = "certs/<AIC>.key"
ca   = "certs/trust-bundle.pem"
verify_client = true

[redis]
url = "redis://localhost:6379/0"

[llm]
model = "gpt-4o"
temperature = 0.3
max_tokens = 512
```

- [x] Populate `prompts.toml` — user intent parsing prompt
- [x] Update `acs.json` — remove arbitration-related skills; add `rc.route_dispatch`

### Phase 2 Completion Checklist

```
✅ RPA generates profile_vector + confidence; responds to Evidence Request
✅ BCA generates book_vectors; computes JS divergence; sends Counter-Proposal when divergence > 0.4
✅ RDA receives both proposals; completes UCB arbitration; returns Arbitration Result to RC
✅ RC broadcasts tasks; aggregates proposals; forwards to RDA; routes dispatch to Engine Agent
✅ Full negotiation pipeline validated end-to-end (mock data acceptable)
```

---

## 5. Phase 3 — Execution & Perception Layer Implementation

> **Prerequisite**: Phase 2 complete  
> **Gate condition for Phase 4**: All 6 Agents running; complete recommendation pipeline returns top-5 results with explanations.

### 5.1 Recommendation Engine Agent (New)

**Directory**: `partners/online/recommendation_engine_agent/`

- [x] Create `agent.py` — ACPs interface entry point
  - Receive `request` from RC: `{profile_vector, ann_weight, cf_weight, score_weights, mmr_lambda, confidence_penalty_threshold, min_coverage, required_evidence_types}`
  - Execute internal pipeline: `RecallModule → RankingModule → ExplanationModule → RankingModule → ExplanationModule`
  - Return `inform` to RC: `{recommendations[], engine_meta{}}`
  - Inbound mention handler: receive Feedback Agent `{trigger: retrain_cf}` → invoke `build_cf_model.py`

- [x] Create `modules/recall.py`
  - **ANN path**: Faiss HNSW, `ef_search=100`, `top_k=200`, tag `recall_source="ann"`
  - **CF path**: Hnswlib finds top-50 similar users → ALS inference, `top_k=100`, tag `recall_source="cf"`
  - Merge and deduplicate: weight by `ann_weight`/`cf_weight`; assign `recall_source="both"` for overlapping candidates

- [x] Create `modules/ranking.py`
  - `score_round1(candidates, score_weights)`: four-dimensional scoring (content / cf / novelty / recency) → top-50
  - `rerank_round2(preliminary_list, confidence_list, mmr_lambda)`:
    - Apply confidence penalty: `score × penalty_multiplier` if `confidence < threshold`
    - MMR: MMR(dᵢ) = λ·Rel(dᵢ) − (1−λ)·max_{dⱼ∈S} cos(d⃗ᵢ, d⃗ⱼ) → top-5

- [x] Create `modules/explanation.py`
  - `assess_confidence(preliminary_list)` — heuristic, no LLM:
    - `content_sim > 0.5` → +0.30
    - `cf_neighbors` present → +0.30
    - `matched_prefs` non-empty → +0.20
    - `kg_features` present → +0.20
    - → `confidence_list {book_id: float}`
  - `generate_rationale(final_list)` — LLM (gpt-4o, temperature=0.4, max_tokens=300)

- [x] Create `acs.json`
- [x] Create `config.toml`

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

- [x] Create `prompts.toml`

```toml
[explanation_main]
template = """
You are a professional book recommendation assistant.
Given the following evidence, generate a concise and personalized recommendation rationale (2–3 sentences).

Book: {title} by {author}
Genres: {genre_tags}
Content similarity to user profile: {content_similarity:.2f}
Collaborative filtering evidence: {cf_evidence}
Matched user preferences: {matched_preferences}

Rationale:
"""

[explanation_fallback]
template = """
Based on your reading history and the characteristics of this book,
we believe "{title}" by {author} may be of interest to you.
"""
```

### 5.2 Feedback Agent (New)

**Directory**: `partners/online/feedback_agent/`

- [x] Create `agent.py`
  - `POST /feedback/webhook`: receive DSP behavior events; map to reward weights; enqueue in Redis DB 2
  - Event weight mapping:

| Event | Weight |
|---|---|
| finish / rate_5 | +1.0 |
| rate_4 | +0.8 |
| rate_3 / click | +0.3 |
| view | +0.1 |
| rate_2 | −0.3 |
| skip | −0.5 |
| rate_1 | −0.8 |

  - Accumulation triggers:
    - After every completed session → `inform(RDA, reward=r_t, context_type=ctx, action=action)`
    - Per-user event count ≥ 20 → `inform(RPA, trigger="update_profile")`
    - Global rating event count ≥ 500 → `inform(RecommendationEngineAgent, trigger="retrain_cf")`

- [x] Create `acs.json`
- [x] Create `config.toml`

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

### 5.3 End-to-End Integration Testing

- [ ] Start all 6 Agents; verify no port conflicts
  - Validation note (2026-04-01): configured ports are unique (`8210`–`8215`) and no static conflicts in config; direct listener/startup verification is blocked in current sandbox (`socket permission_denied`).
- [x] End-to-end test: given a real user ID, validate the complete pipeline:
  `RC → (RPA + BCA) → RDA → RC → Engine Agent → RC → User`
- [x] Verify FA Webhook receives behavior events and correctly writes reward signals to RDA's arm records
- [x] Validate at least 10 complete recommendation sessions (scripted integration run)
  - Evidence: `scripts/phase3_e2e_integration.py` and `scripts/phase3_e2e_integration_report.json`

### Phase 3 Completion Checklist

```
✅ All 6 Agents start successfully with no port conflicts
✅ End-to-end pipeline returns top-5 book list + personalized rationales
✅ FA Webhook receives events; reward signals correctly written to RDA arm records
✅ At least 10 complete recommendation sessions manually validated
```

---

## 6. Phase 4 — ACPs Protocol Compliance

> **Prerequisite**: Phase 3 complete  
> **Gate condition for Phase 5**: All 6 Agents hold ATR-issued formal CAI certificates; mTLS communication passes; DSP registration normal.

### 6.1 ATR Registration

- [x] Refer to `scripts/register_agents_ioa_pub.md`; submit ATR registration for all 6 Agents at [ioa.pub](https://ioa.pub)
- [x] Obtain a formal AIC code for each Agent
- [x] Replace all AIC placeholders in every `acs.json`

### 6.2 CAI Certificate Issuance

- [x] Verify `scripts/phase3_issue_real_certs.sh` logic
- [x] Execute certificate issuance for all 6 Agents:

```bash
./scripts/phase3_issue_real_certs.sh new reading_concierge
./scripts/phase3_issue_real_certs.sh new reader_profile_agent
./scripts/phase3_issue_real_certs.sh new book_content_agent
./scripts/phase3_issue_real_certs.sh new recommendation_decision_agent
./scripts/phase3_issue_real_certs.sh new recommendation_engine_agent
./scripts/phase3_issue_real_certs.sh new feedback_agent
```

- [x] Verify each Agent's `config.toml [server.mtls]` certificate paths are correct
- [x] Remove dev self-signed certificates from `certs/`

### 6.3 ADP Registration Verification

- [ ] Confirm each Agent registers its endpoint and skills in DSP on startup
- [ ] Execute `scripts/phase3_dsp_sync_verify.sh`; verify all 6 Agents show normal DSP registration status
- [x] Confirm RC discovers Partners by skill name, not hardcoded endpoints

### 6.4 AIP Message Compliance Verification

| Message Scenario | Performative | Sender → Receiver |
|---|---|---|
| RC broadcasts task | `request` | RC → RPA, BCA |
| RC notifies RDA to stand by | `request` | RC → RDA |
| RPA submits profile proposal | `propose` | RPA → RDA |
| BCA submits content proposal | `propose` | BCA → RDA |
| BCA emits counter-proposal | `reject-proposal` | BCA → RDA |
| RDA requests supplementary evidence | `request` | RDA → RPA / BCA |
| RPA/BCA returns supplementary data | `inform` | RPA/BCA → RDA |
| RDA returns arbitration result | `inform` | RDA → RC |
| RC dispatches execution | `request` | RC → Engine Agent |
| Engine Agent returns results | `inform` | Engine Agent → RC |
| FA sends reward signal | `inform` | FA → RDA |
| FA triggers profile update | `inform` | FA → RPA |
| FA triggers CF retraining | `inform` | FA → Engine Agent |

- [ ] Validate BCA's Counter-Proposal correctly triggers Evidence Request branch in RDA
- [ ] Validate FA's inform messages are correctly routed and handled by RDA, RPA, and Engine Agent

### Phase 4 Completion Checklist

```
✅ All 6 Agents hold formal AIC codes (no placeholders)
✅ All 6 Agents hold valid ATR-issued CAI certificates; mTLS passes
✅ DSP registration verification script passes for all 6 Agents
✅ Packet capture of any inter-agent message confirms complete AIP fields
```

---

## 7. Phase 5 — Experimental Evaluation

> **Prerequisite**: Phase 4 complete  
> **Gate condition for Phase 6**: Full experimental dataset available; baseline comparison and ablation study results complete.

### 7.1 Update Experimental Scripts

- [ ] Update `scripts/phase4_benchmark_compare.py`
  - Update system call path: `RC → RPA/BCA → RDA → RC → Engine Agent`
  - Add metrics: `explain_coverage`, `intra_list_diversity`

- [ ] Update `scripts/run_ablation.py` — add five ablation modules:

| Ablation Group | Removed Component | Contribution Being Validated |
|---|---|---|
| `-CF` | CF path in RecallModule; ANN only | Collaborative filtering contribution to recall coverage |
| `-Alignment` | BCA does not compute JS divergence; RDA uses fixed weights | Declared preference correction contribution |
| `-ExplainConstraint` | ExplanationModule confidence scoring disabled | Explainability constraints' impact on quality |
| `-MMR` | MMR re-ranking disabled; rank by score only | Diversity re-ranking contribution to ILD |
| `-Feedback` | Feedback Agent disabled; RDA arm records frozen | Online learning contribution |

### 7.2 Baseline Comparison Experiment

- [ ] Implement baselines: Traditional hybrid CF+CB / MACRec / ARAG
- [ ] Run evaluation on test set; collect metrics:
  - Precision@10, Recall@10, NDCG@10
  - Intra-List Diversity (ILD), Novelty, Explain Coverage
- [ ] Compile results; generate comparison charts

### 7.3 Ablation Study

- [ ] Run evaluation for all 5 ablation groups with identical metrics
- [ ] Compute per-module contribution (Δ metric = full system − ablation group)
- [ ] Generate ablation bar charts

### 7.4 Online Learning Validation

- [ ] Simulate ≥1,000 recommendation–feedback cycles
- [ ] Record RDA arm record evolution (`avg_reward` vs. `trials`)
- [ ] Validate upward trend in recommendation quality over time

### Phase 5 Completion Checklist

```
✅ Baseline comparison data complete; system outperforms baselines on primary metrics
✅ Five ablation group data complete; per-module contributions quantified
✅ RDA online learning curve data present; avg_reward shows upward trend
✅ All charts in thesis-ready format
```

---

## 8. Phase 6 — Thesis Writing & Defense Preparation

> **Prerequisite**: Phase 5 complete

### 8.1 Thesis Writing

- [ ] Abstract & Introduction: Filter Bubble problem, research motivation, contribution overview
- [ ] Related Work: recommendation systems, multi-agent recommendation, ACPs protocol
- [ ] System Design: 6-Agent layered architecture, Agent specifications, ACPs compliance, negotiation protocol
- [ ] Academic Argumentation: Agent classification rationale, goal conflict grounding, why negotiation cannot be replaced by function calls, why 6-Agent design is more rigorous than the original 8-Agent design
- [ ] Experiments: dataset, metrics, baseline comparison, ablation study, online learning validation
- [ ] Conclusion & Future Work

### 8.2 Defense Preparation

- [ ] Prepare defense presentation (20–25 slides):
  - 6-Agent layered architecture diagram
  - Layer 2 negotiation workflow (RPA ↔ BCA ↔ RDA)
  - RDA Contextual Bandit arbitration illustration
  - Experimental results comparison charts

- [ ] Prepare responses to anticipated challenges:

| Challenge | Core Response |
|---|---|
| "You reduced to 6 Agents — isn't the system simpler?" | The simplification strengthens the MAS claim. The 3 merged modules had no private objectives and no proactive communication — they did not satisfy any Agent autonomy criterion. The 6-Agent design is architecturally more rigorous. |
| "Most Agents are just functional modules." | RC (organizer), RPA (accuracy advocate), BCA (diversity advocate), RDA (neutral mediator), FA (environment perceiver) all satisfy specific autonomy criteria. Engine Agent is a legitimate reactive execution component. |
| "Your negotiation is just conditional branching." | RDA's UCB arbitration depends on historical arm records; identical inputs at different times yield different outputs — violating referential transparency. |
| "Private objectives are artificially assigned." | RPA and BCA's objectives correspond to pre-existing research problems (Kunaver, 2017; Pariser, 2011). |
| "Evidence Request is just a query." | It is the conditional re-solicitation step of an Iterated Contract Net Protocol, triggered by RDA's internal quality assessment — not by external instruction. |
| "RDA's arbitration is a fixed rule set." | UCB arm records are updated by real user behavior signals; RDA's behavior evolves over time. |

- [ ] Run complete end-to-end demo dry-run; confirm stable execution

### Phase 6 Completion Checklist

```
✅ Thesis full draft complete; all chapters internally consistent
✅ Defense presentation complete; timed at 15–20 minutes
✅ End-to-end demo runs stably
✅ All anticipated challenge categories have complete responses
```

---

## 9. Phase Dependency Overview

```
Phase 1      Phase 2          Phase 3          Phase 4          Phase 5      Phase 6
Data         Negotiation &    Execution &      ACPs Protocol    Experimental Thesis &
Infra        Coordination     Perception       Compliance       Evaluation   Defense
   │              │                │                │                │           │
   └────────────► └──────────────► └──────────────► └──────────────► └─────────► │
   DB + indexes   Negotiation      6 Agents         ACPs-compliant   Exp data    Draft
   + model files  pipeline OK      end-to-end       6 Agents         complete    complete
```

**Critical dependency rule**: No phase may begin until all completion checklist items of the preceding phase are verified.

---

## 10. File Operation Checklist

### New Files

```
migrations/002_user_behavior_events.sql
migrations/003_user_profiles.sql
scripts/build_book_faiss_index.py
partners/online/recommendation_decision_agent/agent.py
partners/online/recommendation_decision_agent/acs.json
partners/online/recommendation_decision_agent/config.toml
partners/online/recommendation_engine_agent/agent.py
partners/online/recommendation_engine_agent/acs.json
partners/online/recommendation_engine_agent/config.toml
partners/online/recommendation_engine_agent/prompts.toml
partners/online/recommendation_engine_agent/modules/recall.py
partners/online/recommendation_engine_agent/modules/ranking.py
partners/online/recommendation_engine_agent/modules/explanation.py
partners/online/feedback_agent/agent.py
partners/online/feedback_agent/acs.json
partners/online/feedback_agent/config.toml
reading_concierge/session_store.py
agents/README.md
```

### Rewrite / Refactor

```
reading_concierge/reading_concierge.py         # Remove arbitration; add RDA routing; pure coordinator
reading_concierge/acs.json                     # Update skills; add rc.route_dispatch
reading_concierge/config.toml                  # Populate (currently 0 bytes)
reading_concierge/prompts.toml                 # Populate (intent parsing prompt)
partners/online/reader_profile_agent/agent.py  # Rewrite (PostgreSQL + decay + negotiation + Evidence Request handler)
partners/online/reader_profile_agent/acs.json  # Update skills
partners/online/reader_profile_agent/config.toml   # Populate
partners/online/reader_profile_agent/prompts.toml  # Populate
partners/online/book_content_agent/agent.py    # Rewrite (384-dim + projection + JS div + Counter-Proposal + Evidence Request handler)
partners/online/book_content_agent/acs.json    # Update skills
partners/online/book_content_agent/config.toml # Populate
partners/online/book_content_agent/proj_matrix.npy  # New artifact
```

### Update (Existing Scripts)

```
scripts/phase4_benchmark_compare.py   # Update call path; add explain_coverage metric
scripts/run_ablation.py               # Add five ablation modules
```

### Deprecate (Retain Code; Remove from Runtime)

```
partners/online/rec_ranking_agent/    # Merged into recommendation_engine_agent; not runtime entry
agents/                               # Legacy reference only
```

---

*End of Document — Version 2026-03-31 (v2)*
```
