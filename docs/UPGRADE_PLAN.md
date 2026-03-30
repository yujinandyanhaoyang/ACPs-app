# System Upgrade Plan
## ACPs-Based Multi-Agent Personalized Book Recommendation System

**Repository**: [ACPs-app / feature/recommendation-optimization](https://github.com/yujinandyanhaoyang/ACPs-app/tree/feature/recommendation-optimization)  
**Target Architecture**: 1 Leader + 7 Partners (8 Agents total)  
**Document Version**: 2026-03-30  
**Academic Framework**: Agent Coordination Protocol Standard (ACPs)

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
│   └── rec_ranking_agent/          ← To be deprecated and split
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
| Architecture | Only 3 Partners; missing RDA, Recall, RankingPolicy, Explanation, Feedback Agents | 🔴 Blocking |
| Architecture | `agents/` and `partners/online/` directories overlap in responsibility | 🟡 Cleanup required |
| Business Logic | `reading_concierge.py` contains no arbitration logic, no GroupMgmt broadcast, no dynamic weight generation | 🔴 Blocking |
| Business Logic | `reader_profile_agent` has no PostgreSQL persistence, no decay-weighted encoding | 🔴 Blocking |
| Business Logic | `book_content_agent` uses 12-dimensional vectors; missing projection matrix and alignment validation interface | 🔴 Blocking |
| Business Logic | `rec_ranking_agent` uses a pseudo-SVD implementation; to be split and deprecated | 🔴 Blocking |
| Configuration | All Agent `config.toml` and `prompts.toml` files are empty (0 bytes) | 🔴 Blocking |
| Database | `001_initial_schema.sql` lacks `user_behavior_events` and `user_profiles` tables | 🔴 Blocking |
| ACPs Compliance | All AICs are placeholders; ATR formal registration not completed | 🟡 Required |
| Certificates | `certs/` contains dev self-signed certificates, not ATR-issued CAI certificates | 🟡 Required |

---

## 2. Target Architecture Design

### 2.1 System Layering

```
┌─────────────────────────────────────────────────────┐
│  Layer 0: User Interaction Layer                     │
│  Web Demo / API Entry Point                          │
└─────────────────────────┬───────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────┐
│  Layer 1: Negotiation & Coordination Layer           │
│  Reading Concierge       (port 8210, Organizer)      │
│  Recommendation Decision Agent (port 8213, Mediator) │
└──────────────┬──────────────────────┬───────────────┘
               ↓                      ↓
┌──────────────────────┐  ┌──────────────────────────┐
│  Layer 2: Proposal   │  │  Layer 2: Proposal       │
│  Negotiation Layer   │  │  Negotiation Layer       │
│  Reader Profile Agent│  │  Book Content Agent      │
│  (port 8211)         │  │  (port 8212)             │
└──────────────────────┘  └──────────────────────────┘
                           ↓ (arbitration result dispatched)
┌─────────────────────────────────────────────────────┐
│  Layer 3: Execution & Evaluation Layer               │
│  Recall Agent (8214) / Ranking Policy Agent (8215) / │
│  Explanation Agent (8216)                            │
└─────────────────────────┬───────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────┐
│  Layer 4: Feedback & Perception Layer                │
│  Feedback Agent (port 8217)                          │
└─────────────────────────────────────────────────────┘
```

### 2.2 Complete Interaction Sequence

```
t0   User request → Reading Concierge
       LLM parses intent → structured task parameters
       GroupMgmt broadcast → Reader Profile Agent + Book Content Agent (parallel)

t1   [Parallel execution]
     Reader Profile Agent:
       Load behavior sequence from PostgreSQL (90-day window, decay-weighted)
       Encode → profile_vector (256-dim) + confidence score
       Proposal A: {profile_vector, confidence, behavior_genres, strategy_suggestion}

     Book Content Agent:
       Encode via sentence-transformers → book_vectors (384-dim)
       Project to 256-dim user space; compute JS divergence
       Proposal B: {alignment_report, divergence_score, weight_suggestion}
       [If divergence > 0.4: proactively emit reject-proposal to RDA]

t2   RC aggregates both proposals → forwards to Recommendation Decision Agent

t3   Recommendation Decision Agent (Contextual Bandit arbitration):
       Identify context type: f(confidence, divergence) → one of 4 context classes
       UCB selection: UCB(a) = r̄(a) + c·√(ln N / n(a)), c = 1.41
       [If information insufficient: proactively issue query-if to proposal agents]
       [Multi-round negotiation: max 3 rounds; fallback to historical mean if not converged]
       Output: final_weights + strategy + mmr_lambda
       Dispatch differentiated execution instructions:
         → Recall Agent:          {ann_weight, cf_weight, strategy}
         → Ranking Policy Agent:  {weights, mmr_lambda, penalty_params}
         → Explanation Agent:     {min_coverage, required_evidence_types}

t4   Recall Agent:
       ANN path: Faiss HNSW retrieval, ef_search=100, top_k=200 (recall_source="ann")
       CF path:  ALS model recommendation, top_k=100 (recall_source="cf")
       Merge and deduplicate → candidates[] (~250 books)

t5   Ranking Policy Agent (Round 1):
       Four-dimensional scoring (content / cf / novelty / recency)
       → preliminary_ranked_list (top-50)

t6   Explanation Agent (assessment phase):
       Heuristic evaluation of explainability confidence per candidate
       → confidence_list {book_id: float}

t7   Ranking Policy Agent (Round 2):
       Apply EA penalty (confidence < 0.6 → score × 0.7)
       MMR re-ranking → final_ranked_list (top-20)
       MMR(dᵢ) = λ·Rel(dᵢ) − (1−λ)·max_{dⱼ∈S} cos(d⃗ᵢ, d⃗ⱼ)

t8   Explanation Agent (generation phase):
       LLM generates personalized recommendation rationales (gpt-4o)
       → explanations {book_id: text}

t9   Reading Concierge assembles response → returns to user

[Asynchronous feedback loop]
t10  User behavior events → DSP Webhook → Feedback Agent
       Compute reward signal rₜ
       → mention → Reader Profile Agent (profile update; threshold: 20 events/user)
       → mention → Recall Agent (CF model retrain; threshold: 500 rating events globally)
       → mention → RDA (update contextual bandit arm record with reward signal)
```

### 2.3 Agent Specification Summary

| Agent | Port | Role | Private Objective | LLM | prompts.toml |
|---|---|---|---|---|---|
| Reading Concierge | 8210 | Organizer | Maintain negotiation order | ✅ Intent parsing | Required |
| Reader Profile Agent | 8211 | Proposal Party A | Maximize user behavioral consistency | ✅ Semantic preference induction | Required |
| Book Content Agent | 8212 | Proposal Party B | Maximize semantic coverage diversity | ❌ | Not required |
| Recommendation Decision Agent | 8213 | Neutral Mediator | Minimize long-term recommendation regret | ❌ | Not required |
| Recall Agent | 8214 | Reactive Execution Agent | — | ❌ | Not required |
| Ranking Policy Agent | 8215 | Instrumental Evaluation Agent | — | ❌ | Not required |
| Explanation Agent | 8216 | Instrumental Evaluation Agent | — | ✅ Rationale generation | Required |
| Feedback Agent | 8217 | Environment Perception Agent | — | ❌ | Not required |

### 2.4 Academic Justification for Multi-Agent Collaboration

The system's claim to be a genuine Multi-Agent System (MAS) rests on the following arguments:

**Argument 1 — Externally grounded goal conflict.** The opposing objectives of Reader Profile Agent (maximizing accuracy) and Book Content Agent (maximizing diversity) correspond to the well-established Filter Bubble problem (Pariser, 2011) and the Accuracy-Diversity Dilemma (Kunaver & Požrl, 2017). These conflicts exist prior to and independently of the system design.

**Argument 2 — Non-deterministic negotiation outcomes.** Proposals from RPA and BCA are generated independently and are mutually opaque. RDA's UCB arbitration depends on its historical arm records, so identical conflict inputs at different points in time yield different arbitration results. This violates the referential transparency property of function calls.

**Argument 3 — Proactive inter-agent communication.** BCA's `reject-proposal` signal is initiated by BCA's own internal computation, not triggered by any external call. RDA's multi-round negotiation broadcast is proactively initiated based on RDA's internal uncertainty assessment.

**Argument 4 — ACPs protocol-layer identity.** All Agent-to-Agent communication passes through mTLS mutual authentication (AIA layer), dynamic endpoint discovery (ADP layer), and structured performative messaging (AIP layer). This is architecturally incompatible with intra-process function calls.

---

## 3. Phase 1 — Data Infrastructure Layer

> **Prerequisite**: None  
> **Gate condition for Phase 2**: Database migrations applied; Faiss index and ALS model files present and loadable.

### 3.1 Database Migration

- [ ] Create `migrations/002_user_behavior_events.sql`

```sql
CREATE TABLE user_behavior_events (
    id           BIGSERIAL PRIMARY KEY,
    user_id      VARCHAR(64) NOT NULL,
    book_id      VARCHAR(64) NOT NULL,
    event_type   VARCHAR(16) NOT NULL,  -- view/click/finish/rate/skip
    weight       FLOAT       NOT NULL,
    rating       SMALLINT,
    duration_sec INT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON user_behavior_events(user_id, created_at DESC);
CREATE INDEX ON user_behavior_events(book_id);
```

- [ ] Create `migrations/003_user_profiles.sql`

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

- [ ] Apply migrations; verify table structures and indexes

### 3.2 Offline Data Preparation

- [ ] Execute `scripts/backfill_book_features.py` — confirm book feature data persisted
- [ ] Execute `scripts/backfill_user_events.py` — confirm user behavior data persisted
- [ ] Create `scripts/build_book_faiss_index.py`
  - Batch encode all books via `sentence-transformers` (all-MiniLM-L6-v2), 384-dim output
  - Write to `Faiss IndexHNSWFlat`; persist index file
- [ ] Execute `scripts/build_cf_model.py` — output ALS model file and Hnswlib user similarity index
- [ ] Execute `scripts/build_knowledge_graph.py` — confirm KG data available

### 3.3 Legacy Directory Cleanup

- [ ] Add `agents/README.md`: mark as legacy reference code, not runtime entry point
- [ ] Mark `partners/online/rec_ranking_agent/` as deprecated; remove from service startup scripts

### Phase 1 Completion Checklist

```
✅ Table user_behavior_events exists and contains data
✅ Table user_profiles exists
✅ book_faiss.index file present and loadable
✅ als_model.npz file present and loadable
✅ Hnswlib user similarity index present and loadable
```

---

## 4. Phase 2 — Negotiation & Coordination Layer Refactoring

> **Prerequisite**: Phase 1 complete  
> **Gate condition for Phase 3**: RC can broadcast tasks; RPA/BCA can generate proposals; RDA can complete arbitration and output `final_weights`.

### 4.1 Reader Profile Agent Refactoring

**Directory**: `partners/online/reader_profile_agent/` (refactor in place, do not rename)

- [ ] Rewrite `agent.py`
  - PostgreSQL connection; `load_behavior_sequence(user_id, window=90 days)`
  - Decay-weighted encoding: $w_t = e^{-\lambda(T-t)}$, λ=0.05
  - Output: `profile_vector` (256-dim) + `confidence` ∈ [0, 1]
  - Cold-start guard: if event count < 5 → force `confidence ≤ 0.25`, `cold_start = true`
  - Negotiation interfaces: `uma.build_profile`, `uma.validate_consistency`, `uma.update_profile`
  - Inbound mention handler: receive Feedback Agent trigger → incremental profile update
- [ ] Rewrite `acs.json` — update skills declaration, AIC placeholder
- [ ] Populate `config.toml`

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

- [ ] Populate `prompts.toml` — semantic preference induction prompt (LLM lifts discrete behavior sequences to semantic space)

### 4.2 Book Content Agent Refactoring

**Directory**: `partners/online/book_content_agent/` (refactor in place, do not rename)

- [ ] Rewrite `agent.py`
  - Encode via `sentence-transformers` (all-MiniLM-L6-v2) → 384-dim book vectors
  - Load `proj_matrix.npy` (256×384); project book vectors to user space
  - Compute JS divergence between declared preferences and behavioral genres → `AlignmentReport`
  - Negotiation interface: `bca.encode_books`, `bca.validate_alignment`
  - If `divergence > MISMATCH_THRESHOLD`: proactively `mention(RDA, performative="reject-proposal")`
- [ ] Rewrite `acs.json` — update skills declaration
- [ ] Populate `config.toml`

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

- [ ] Generate `proj_matrix.npy` (256×384; initialized via PCA or random projection)
- [ ] Confirm `prompts.toml` not required (no LLM calls in BCA)

### 4.3 Recommendation Decision Agent (New)

**Directory**: `partners/online/recommendation_decision_agent/` (create new)

- [ ] Create `agent.py`
  - Receive proposals from RPA and BCA
  - Map proposals to context type: $f(\text{confidence},\ \text{divergence}) \rightarrow \{$`high_conf_low_div`, `low_conf_high_div`, `low_conf_low_div`, `high_conf_high_div`$\}$
  - UCB arbitration: $\text{UCB}(a) = \bar{r}(a) + c\sqrt{\frac{\ln N}{n(a)}}$, $c = 1.41$
  - Cold-start guard: if `trials < 20` → apply conservative prior
  - Multi-round negotiation protocol: max 3 rounds; fallback to historical arm mean if not converged
  - Proactive behaviors:
    - If information insufficient → `mention(RPA/BCA, performative="query-if")`
    - Broadcast preliminary equilibrium → collect feedback → iterate
  - On convergence: dispatch differentiated execution instructions to RA, RankingPA, EA
  - Inbound mention handler: receive Feedback Agent reward signal → update contextual arm record
  - Persist arm records in Redis
- [ ] Create `acs.json`
- [ ] Create `config.toml`

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

- [ ] Refactor `reading_concierge.py`
  - **Remove**: all arbitration logic, weight computation, divergence detection
  - **Retain**: LLM intent parsing, GroupMgmt broadcast, inter-agent message routing, response assembly
  - **Add**: aggregate proposals from RPA and BCA → forward to RDA; receive arbitration result → route to downstream agents
- [ ] Create `reading_concierge/session_store.py` — Redis session context wrapper
- [ ] Populate `config.toml`

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

- [ ] Populate `prompts.toml` — user intent parsing prompt
- [ ] Update `acs.json` — remove arbitration-related skills

### Phase 2 Completion Checklist

```
✅ RPA generates profile_vector + confidence; negotiation interfaces callable
✅ BCA generates book_vectors; computes JS divergence; emits reject-proposal when divergence > 0.4
✅ RDA receives both proposals; completes UCB arbitration; outputs final_weights
✅ RC broadcasts tasks; aggregates proposals; forwards to RDA; routes arbitration result downstream
✅ Full negotiation pipeline validated end-to-end (mock data acceptable)
```

---

## 5. Phase 3 — Execution & Perception Layer Implementation

> **Prerequisite**: Phase 2 complete  
> **Gate condition for Phase 4**: All 8 Agents running; complete recommendation pipeline returns top-20 results with explanations.

### 5.1 Recall Agent (New)

**Directory**: `partners/online/recall_agent/`

- [ ] Create `agent.py`
  - **ANN path**: Faiss HNSW retrieval, `ef_search=100`, `top_k=200`, tag `recall_source="ann"`
  - **CF path**: Hnswlib finds top-50 similar users; ALS inference, `top_k=100`, tag `recall_source="cf"`
  - Merge and deduplicate: weighted by `ann_weight` / `cf_weight` dispatched from RDA; assign `recall_source="both"` for overlapping candidates (take higher score)
  - Inbound mention handler: receive Feedback Agent trigger → invoke `build_cf_model.py` for incremental retraining
- [ ] Create `acs.json`
- [ ] Create `config.toml`

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
```

### 5.2 Ranking Policy Agent (New)

**Directory**: `partners/online/ranking_policy_agent/`

- [ ] Create `agent.py`
  - Four-dimensional scoring (content / cf / novelty / recency; weights dispatched from RDA)
  - **Round 1**: Score all candidates → `preliminary_ranked_list` (top-50)
  - Receive `confidence_list` from EA; apply penalty: `score × 0.7` if `confidence < threshold`
  - **Round 2**: MMR re-ranking → `final_ranked_list` (top-20)

$$\text{MMR}(d_i) = \lambda \cdot \text{Rel}(d_i) - (1-\lambda) \cdot \max_{d_j \in S} \cos(\vec{d}_i,\ \vec{d}_j)$$

- [ ] Create `acs.json`
- [ ] Create `config.toml`

```toml
[server]
port = 8215

[server.mtls]
cert = "certs/<AIC>.pem"
key  = "certs/<AIC>.key"
ca   = "certs/trust-bundle.pem"
verify_client = true

[ranking]
CONFIDENCE_PENALTY_THRESHOLD = 0.6
PENALTY_MULTIPLIER           = 0.7
DEFAULT_MMR_LAMBDA           = 0.5
```

### 5.3 Explanation Agent (New)

**Directory**: `partners/online/explanation_agent/`

- [ ] Create `agent.py`
  - **Phase 1 — Heuristic Assessment** (no LLM): compute `explain_confidence` per candidate
    - `content_sim > 0.5` → +0.30
    - `cf_neighbors` present → +0.30
    - `matched_prefs` non-empty → +0.20
    - `kg_features` present → +0.20
  - **Phase 2 — Rationale Generation** (LLM): generate personalized explanation for `final_ranked_list` (gpt-4o, temperature=0.4, max_tokens=300)
- [ ] Create `acs.json`
- [ ] Create `config.toml`

```toml
[server]
port = 8216

[server.mtls]
cert = "certs/<AIC>.pem"
key  = "certs/<AIC>.key"
ca   = "certs/trust-bundle.pem"
verify_client = true

[llm]
model       = "gpt-4o"
temperature = 0.4
max_tokens  = 300

[quality]
DEFAULT_MIN_COVERAGE = 0.6
```

- [ ] Create `prompts.toml`

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

### 5.4 Feedback Agent (New)

**Directory**: `partners/online/feedback_agent/`

- [ ] Create `agent.py`
  - `POST /feedback/webhook`: receive DSP behavior events; map to reward weights; enqueue in Redis
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
    - Per-user event count ≥ 20 → `mention(RPA, performative="inform", trigger="update_profile")`
    - Global rating event count ≥ 500 → `mention(RecallAgent, performative="inform", trigger="retrain_cf")`
    - After every completed recommendation session → `mention(RDA, performative="inform", reward=rₜ, context_type=ctx, action=action)`

- [ ] Create `acs.json`
- [ ] Create `config.toml`

```toml
[server]
port = 8217

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
RECALL_AIC = "<AIC-RECALL>"
RDA_AIC    = "<AIC-RDA>"
```

### 5.5 End-to-End Integration Testing

- [ ] Start all 8 Agents; verify no port conflicts
- [ ] End-to-end test: given a real user ID, validate the complete pipeline from RC receiving a request to returning top-20 recommendations with explanations
- [ ] Verify FA Webhook receives behavior events and correctly writes reward signals to RDA's arm records
- [ ] Manually validate at least 10 complete recommendation sessions

### Phase 3 Completion Checklist

```
✅ All 8 Agents start successfully with no port conflicts
✅ End-to-end recommendation pipeline returns top-20 book list + personalized rationales
✅ FA Webhook receives events; reward signals correctly written to RDA arm records
✅ At least 10 complete recommendation sessions manually validated
```

---

## 6. Phase 4 — ACPs Protocol Compliance

> **Prerequisite**: Phase 3 complete  
> **Gate condition for Phase 5**: All 8 Agents hold ATR-issued formal CAI certificates; mTLS communication passes verification; DSP registration status normal for all Agents.

### 6.1 ATR Registration

- [ ] Refer to `scripts/register_agents_ioa_pub.md`; submit ATR registration for all 8 Agents at [ioa.pub](https://ioa.pub)
- [ ] Obtain a formal AIC code for each Agent (format: `1.2.156.3088.xxxx.xxxxx.xxxxx.xxxxx.x.xxxx`)
- [ ] Replace all AIC placeholders in every `acs.json` with formal AIC codes

### 6.2 CAI Certificate Issuance

- [ ] Verify `scripts/phase3_issue_real_certs.sh` logic is consistent with the ACPs official `manage-certs.sh`
- [ ] Execute certificate issuance for all 8 Agents:

```bash
./scripts/phase3_issue_real_certs.sh new reading_concierge
./scripts/phase3_issue_real_certs.sh new reader_profile_agent
./scripts/phase3_issue_real_certs.sh new book_content_agent
./scripts/phase3_issue_real_certs.sh new recommendation_decision_agent
./scripts/phase3_issue_real_certs.sh new recall_agent
./scripts/phase3_issue_real_certs.sh new ranking_policy_agent
./scripts/phase3_issue_real_certs.sh new explanation_agent
./scripts/phase3_issue_real_certs.sh new feedback_agent
```

- [ ] Verify each Agent's `config.toml [server.mtls]` certificate paths are auto-updated correctly
- [ ] Remove dev self-signed certificates from `certs/`

### 6.3 ADP Registration Verification

- [ ] Confirm each Agent registers its endpoint and skills in DSP on startup
- [ ] Execute `scripts/phase3_dsp_sync_verify.sh`; verify all 8 Agents show normal DSP registration status
- [ ] Confirm RC discovers Partners by skill name, not hardcoded endpoints

### 6.4 AIP Message Compliance Verification

Verify all inter-agent messages contain the required AIP fields: `from`, `to`, `performative`, `conversation_id`.

| Message Scenario | Performative | Sender → Receiver |
|---|---|---|
| RC broadcasts task | `request` | RC → RPA, BCA |
| RPA submits proposal | `propose` | RPA → RDA |
| BCA emits veto | `reject-proposal` | BCA → RDA |
| RDA requests supplementary info | `query-if` | RDA → RPA / BCA |
| RDA broadcasts preliminary equilibrium | `propose` | RDA → RPA, BCA |
| RDA dispatches execution instructions | `inform` | RDA → RA / RankingPA / EA |
| FA sends reward signal | `inform` | FA → RDA |
| FA triggers profile update | `inform` | FA → RPA |
| FA triggers CF retraining | `inform` | FA → Recall Agent |

- [ ] Validate BCA's `reject-proposal` correctly triggers the multi-round negotiation branch in RDA
- [ ] Validate FA's mention messages are correctly routed and handled by RPA, RA, and RDA

### Phase 4 Completion Checklist

```
✅ All 8 Agents hold formal AIC codes (no placeholders)
✅ All 8 Agents hold valid ATR-issued CAI certificates; mTLS mutual authentication passes
✅ DSP registration verification script passes for all 8 Agents
✅ Packet capture of any inter-agent message confirms complete AIP fields
```

---

## 7. Phase 5 — Experimental Evaluation

> **Prerequisite**: Phase 4 complete  
> **Gate condition for Phase 6**: Full experimental dataset available; baseline comparison and ablation study results complete; visualizations ready.

### 7.1 Update Experimental Scripts

- [ ] Update `scripts/phase4_benchmark_compare.py`
  - Update system call path to new architecture (RC → RPA/BCA → RDA → RA → RankingPA → EA)
  - Add new evaluation metrics: `explain_coverage` (proportion of results with valid rationales), `intra_list_diversity` (ILD)

- [ ] Update `scripts/run_ablation.py` — add five ablation modules:

| Ablation Group | Removed Component | Contribution Being Validated |
|---|---|---|
| `-CF` | CF path in Recall Agent; ANN only | Collaborative filtering contribution to recall coverage |
| `-Alignment` | Lateral negotiation ① (BCA does not compute JS divergence; RDA uses fixed weights) | Contribution of declared preference correction to personalization |
| `-ExplainConstraint` | Lateral negotiation ② (skip EA confidence filtering) | Impact of explainability constraints on recommendation quality |
| `-MMR` | MMR re-ranking; rank directly by score | Diversity re-ranking contribution to genre concentration reduction |
| `-Feedback` | Feedback Agent disabled; no profile updates; RDA arm records not updated | Online learning contribution to long-term recommendation accuracy |

### 7.2 Baseline Comparison Experiment

- [ ] Implement comparison baselines:
  - Traditional hybrid recommender (fixed-weight CF + CB)
  - MACRec (multi-agent recommendation baseline)
  - ARAG (agent-based retrieval-augmented generation)

- [ ] Run evaluation on test set for the full system and all baselines; collect metrics:
  - Precision@10, Recall@10, NDCG@10
  - Intra-List Diversity (ILD), Novelty
  - Explain Coverage

- [ ] Compile results; generate comparison charts

### 7.3 Ablation Study

- [ ] Run evaluation for all 5 ablation groups with identical metrics
- [ ] Compute per-module contribution (Δ metric = full system − ablation group)
- [ ] Generate ablation bar charts

### 7.4 Online Learning Validation

- [ ] Simulate user behavior sequences (≥ 1,000 recommendation–feedback cycles)
- [ ] Record evolution of RDA contextual arm records (`avg_reward` vs. `trials` curve)
- [ ] Validate upward trend in recommendation quality over time

### Phase 5 Completion Checklist

```
✅ Baseline comparison data complete; system outperforms baselines on primary metrics
✅ Five ablation group data complete; per-module contributions quantified
✅ RDA online learning curve data present; avg_reward shows upward trend with trials
✅ All charts generated in thesis-ready format
```

---

## 8. Phase 6 — Thesis Writing & Defense Preparation

> **Prerequisite**: Phase 5 complete

### 8.1 Thesis Writing

- [ ] **Abstract & Introduction**: research background (Filter Bubble problem), research motivation, contribution overview
- [ ] **Related Work**: survey of recommendation systems, multi-agent recommendation systems, ACPs protocol
- [ ] **System Design**: layered architecture, 8-Agent specifications, ACPs compliance design, negotiation protocol details
- [ ] **Academic Argumentation**: Agent classification rationale, theoretical grounding for goal conflicts, argument that negotiation outcomes cannot be replaced by function calls
- [ ] **Experiments**: dataset description, metric definitions, baseline comparison results, ablation study results, online learning validation
- [ ] **Conclusion & Future Work**

### 8.2 Defense Preparation

- [ ] Prepare defense presentation (recommended 20–25 slides):
  - System architecture diagram (layered diagram + sequence diagram)
  - Four-Agent negotiation workflow diagram
  - RDA Contextual Bandit arbitration illustration
  - Experimental results comparison charts

- [ ] Prepare responses to five categories of anticipated expert challenges:

| Challenge | Core Response |
|---|---|
| "Most of your Agents are just functional modules, not real Agents." | Collaboration occurs among 4 Agents with distinct roles; the other 4 serve as execution/perception infrastructure — a legitimate division in MAS literature. |
| "Your negotiation is just conditional branching — that's a function call." | RDA's UCB arbitration depends on its historical arm records; identical inputs at different times produce different outputs, violating the referential transparency of function calls. |
| "Your private objectives are artificially assigned to justify the design." | RPA and BCA's objectives correspond to the Accuracy-Diversity Dilemma (Kunaver, 2017) and the Filter Bubble problem (Pariser, 2011) — conflicts that exist independently of this system design. |
| "This is just inter-process communication, not genuine Agent communication." | All communication passes through ATR-issued CAI certificates (AIA), DSP dynamic discovery (ADP), and performative-structured messages (AIP) — architecturally incompatible with function calls. |
| "RDA's arbitration is just a fixed rule set." | RDA uses a Contextual Bandit (UCB) algorithm; its arm records are updated by real user behavior signals, making its behavior evolve over time in a way no static rule set can replicate. |

- [ ] Run a complete end-to-end demo dry-run; confirm stable execution for live demonstration at defense

### Phase 6 Completion Checklist

```
✅ Thesis full draft complete; all chapters internally consistent
✅ Defense presentation complete; timed at 15–20 minutes
✅ End-to-end demo runs stably
✅ All five anticipated challenge categories have complete defense responses
```

---

## 9. Phase Dependency Overview

```
Phase 1          Phase 2          Phase 3          Phase 4          Phase 5          Phase 6
Data             Negotiation &    Execution &      ACPs Protocol    Experimental     Thesis &
Infrastructure   Coordination     Perception       Compliance       Evaluation       Defense
Layer            Layer            Layer
   │                │                │                │                │                │
   └──────────────► └──────────────► └──────────────► └──────────────► └──────────────► │
   DB migrations    DB + indexes     Full pipeline    All Agents       Compliance +      Experimental
   + indexes +      + negotiation    running          ACPs-compliant   full pipeline     data complete
   model files      pipeline OK      end-to-end                        required
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
partners/online/recall_agent/agent.py
partners/online/recall_agent/acs.json
partners/online/recall_agent/config.toml
partners/online/ranking_policy_agent/agent.py
partners/online/ranking_policy_agent/acs.json
partners/online/ranking_policy_agent/config.toml
partners/online/explanation_agent/agent.py
partners/online/explanation_agent/acs.json
partners/online/explanation_agent/config.toml
partners/online/explanation_agent/prompts.toml
partners/online/feedback_agent/agent.py
partners/online/feedback_agent/acs.json
partners/online/feedback_agent/config.toml
reading_concierge/session_store.py
agents/README.md
```

### Rewrite / Refactor

```
reading_concierge/reading_concierge.py         # Remove arbitration; pure coordinator
reading_concierge/acs.json                     # Update skills declaration
reading_concierge/config.toml                  # Populate (currently 0 bytes)
reading_concierge/prompts.toml                 # Populate (intent parsing prompt)
partners/online/reader_profile_agent/agent.py  # Rewrite (PostgreSQL + decay encoding + negotiation)
partners/online/reader_profile_agent/acs.json  # Update skills
partners/online/reader_profile_agent/config.toml   # Populate
partners/online/reader_profile_agent/prompts.toml  # Populate (semantic preference induction)
partners/online/book_content_agent/agent.py    # Rewrite (384-dim + projection + JS div + negotiation)
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
partners/online/rec_ranking_agent/    # Split into recall_agent + ranking_policy_agent
agents/                               # Legacy reference only; not runtime entry point
```

---

*End of Document*
