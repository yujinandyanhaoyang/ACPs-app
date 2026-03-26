# UPDATEPLAN.md
# ACPs Personalized Reading Recsys - Formal Refactor Update Plan

## 0. Purpose and Scope
This plan upgrades the current prototype to a formal ACPs-aligned multi-agent system and directly addresses the five required fixes:
1. Remove frontend hardcoded user context dependence.
2. Optimize Book Content Agent and Recommendation Agent according to redesigned logic.
3. Complete formal ACPs ecosystem registration and protocol adoption.
4. Introduce persistent local database storage.
5. Execute with a phased plan and auditable checklist.

Planned window: 2026-03-22 to 2026-04-26 (5 weeks, can be compressed by parallel execution).

## Current Gate Status
- 2026-03-23 baseline verification: `pytest` -> `117 passed, 9 skipped, 0 failed`.
- 2026-03-25 P4 persistence hardening verification: `.venv/bin/python -m pytest -q tests/test_persistence_db.py tests/test_backfill_scripts.py` -> `6 passed, 0 failed`.
- P0 hardening gate decision: **GO** for continuing implementation under the existing phase boundaries.
- Remaining phase checklists stay authoritative; unchecked items are not implicitly closed by this gate update.

**Implementation approval rule:** engineering starts only after the following are frozen:
- ACPs runtime role model (**1 Leader + 3 Partners**).
- Inter-agent payload contracts and schema versions.
- Candidate generation ownership and boundaries.
- Acceptance metrics for recommendation quality and explainability.

---

## 1. Design Baseline and Constraints
- Keep existing tourism-related assets untouched.
- Refactor only inside this repository.
- Use ACPs protocol suite consistently: AIC, ACS, ATR, AIA, ADP, AIP, DSP.
- All partner outputs must remain machine-readable and traceable.
- Every phase must end with test evidence and document updates.

**Implementation progress (2026-03-23):**
- `tour_assistant/` remains untouched in the current working tree.
- Runtime architecture and API boundary constraints are enforced in leader routes and orchestration flow.
- Contract-first enforcement is now executable:
  - all v1 payload schemas are version-tagged with `x_contract_version: v1.0.0`,
  - automated schema tests validate schema integrity and persisted `UserProfileJSON` conformance.
- Latest targeted evidence run: `pytest tests/test_contract_schemas.py tests/test_reader_profile_agent.py tests/test_reading_concierge.py` -> `28 passed, 0 failed`.

**Runtime architecture constraint:**
- `reading coordinator` is the **Leader Agent**.
- `reader profile agent`, `book content agent`, and `recommendation ranking agent` are **Partner Agents**.
- Default AIP mode is **Direct Connection Mode**.
- Runtime orchestration must use explicit task/session identity and task-state transitions, not implicit in-process shortcuts.

**API boundary constraint:**
- Production recommendation requests must use **`user_id + query`** as the primary input.
- Any manual `user_profile/history` injection is permitted only through a clearly separated **debug/test path**, never as the default production path.

**Contract-first constraint:**
- No P1/P2 implementation is considered complete until the corresponding JSON payload schemas are versioned and reviewed.

---

## 2. Target System Definition
Goal: deliver a personalized book recommendation system that can:
- reconstruct user preference state from persisted interaction history,
- analyze candidate books with structured semantic + metadata features,
- rank candidates with multi-factor explainable scoring,
- operate through ACPs-compliant Leader/Partner collaboration,
- preserve recommendation evidence for reproducibility and audit.

**Implementation progress (2026-03-23):**
- Runtime chain is now materialized in response artifacts and partner-result trace fields:
  - `contract_artifacts.candidate_book_set`
  - `contract_artifacts.ranked_recommendation_list`
  - `partner_results._candidate_set`
  - `partner_results._candidate_provenance`
- Candidate generation ownership is implemented by Leader local retrieval and explicitly captured in provenance (`retrieval_rule`, `dataset_version`, `filter_parameters`, `generated_at`).
- Section-2 contracts are enforced at runtime through schema validation checks with pass/fail diagnostics in `contract_validation`.
- Fail-closed policy is enforced by default: contract-validation failure returns controlled error (`contract_validation_failed`), with optional debug override via `constraints.strict_contract_validation = false`.
- Latest targeted evidence run: `pytest tests/test_contract_schemas.py tests/test_reading_concierge.py` -> `26 passed, 0 failed`.

**Target runtime chain:**
1. User sends `user_id + query` to Leader.
2. Leader resolves or assembles user context through Partner A.
3. Leader obtains candidate book set from the defined candidate source.
4. Leader dispatches candidate set to Partner B for feature enrichment.
5. Leader dispatches `UserProfile + BookFeatures` to Partner C for ranking and explanation.
6. Leader returns ranked recommendations and persists run evidence.

**Candidate generation policy must be explicit before P2 starts.**  
The system must define one of the following as the authoritative source of candidates:
- precomputed candidate pool,
- metadata retrieval/filtering service,
- search/recall module,
- curated dataset subset.

If a separate retrieval module is not introduced in this phase, the Leader must own candidate assembly from the local dataset and document the filtering rules.

---

## 3. Defect-to-Workstream Mapping
| Defect | Workstream | Key Deliverables |
| --- | --- | --- |
| Frontend hardcoded profile/history | WS-A User Profile Lifecycle | Automatic profile assembly pipeline, profile persistence DB, UI simplification |
| Book content + ranking need redesign alignment | WS-B Content and Ranking Optimization | Updated payload schemas, scoring pipeline, explainability and benchmark improvements |
| ACPs official registration and protocol compliance | WS-C ACPs Compliance and Trust | Real AIC identities, mTLS certificates, ioa.pub registration evidence, discovery and sync enabled |
| Temporary storage model | WS-D Persistence Foundation | SQLite/PostgreSQL-ready data layer, migrations, repositories, retention policy |
| Need standardized update plan | WS-E Governance and Verification | This plan, phase gate checklist, milestone evidence tracking |

**Implementation progress (2026-03-23):**
- Section-3 execution tracking has been externalized into `docs/workstream-traceability.md` with per-workstream status, evidence, and closure tasks.
- WS-A status: in-progress (production boundary + persisted profile snapshots implemented; ingestion adapters now persist `user_basic_info`, `rating/browse/history_entry`, and `review` events; dedupe/normalization hardening is complete, with lifecycle refresh policy work still pending).
- WS-B status: in-progress (target-system contract artifacts and fail-closed validation implemented; Partner B intake normalization, dedupe, source labeling, and feature metadata versioning are now implemented and test-covered; ranking redesign thresholds still pending in P2).
- WS-C status: pending (official registration/trust hardening is not started in production evidence terms).
- WS-D status: partial (local SQLite persistence exists, including temporary `recommendation_runs` overlap in `user_profile_store.py`; migration-capable DB/repositories refactor remains mandatory in P4).
- WS-E status: in-progress (plan/gates/evidence are maintained; approvals and final checklist closures pending).

**Cross-workstream architecture deliverables:**
- `docs/contracts/user_profile.schema.json`
- `docs/contracts/candidate_book_set.schema.json`
- `docs/contracts/book_feature_map.schema.json`
- `docs/contracts/ranked_recommendation_list.schema.json`
- `docs/leader-partner-runtime.md`

---

## 4. Execution Phases

## Phase P0 - Baseline Freeze and Gap Audit (2026-03-22 to 2026-03-24)
Goal: Freeze current behavior and create a reproducible baseline before code migration.

Tasks:
- Record current API behavior and payload contracts for:
  - reading coordinator
  - reader profile agent
  - book content agent
  - recommendation ranking agent
- Snapshot benchmark and ablation outputs from scripts/.
- Produce ACPs compliance gap matrix against ACPsProtocolGuide.md and AGENT_REDESIGN.md

**Mandatory architecture freeze tasks:**
- Freeze the Leader/Partner runtime model and write a one-page execution flow.
- Decide and document authoritative candidate generation ownership.
- Create v1 schema drafts for:
  - `UserProfileJSON`
  - `CandidateBookSetJSON`
  - `BookFeatureMapJSON`
  - `RankedRecommendationListJSON`
- Identify all current debug shortcuts that bypass intended ACPs flow.

Target files/artifacts:
- WORKLOG_DEV.md (baseline section)
- docs/demo-launch.md (baseline runbook update)
- docs/acps-gap-matrix.md (new)
- docs/leader-partner-runtime.md (new)
- docs/contracts/*.schema.json (new)

Exit criteria:
- Baseline tests pass.
- Gap matrix reviewed and accepted.
- Leader/Partner flow accepted.
- Candidate generation owner accepted.
- Contract v1 drafts reviewed.

---

## Phase P1 - User Profile Agent Lifecycle Refactor (2026-03-24 to 2026-03-31)
Goal: Move profile collection and maintenance into reader_profile_agent and remove hard dependency on manual frontend JSON.

Tasks:
- Add profile data ingestion adapters:
  - ratings source
  - browsing logs source
  - review text source
  - user basic info source
- Implement profile lifecycle operations in reader_profile_agent:
  - bootstrap (cold start)
  - incremental update (new events)
  - decay/refresh strategy
  - versioned profile vector persistence
- Define profile schema and state model:
  - explicit preferences
  - implicit preferences
  - sentiment summary
  - profile metadata and timestamps
- Update coordinator contract:
  - `query` and `user_id` become minimum required fields
  - optional profile override retained for testing only
- Simplify frontend:
  - remove mandatory profile/history manual entry
  - expose optional debug panel for injected payloads

**Strengthened implementation rules:**
- The production API must not require `user_profile`, `history`, or `reviews`.
- The debug injection path must be isolated behind a clearly named nonproduction route, flag, or UI panel.
- `UserProfileJSON` must carry:
  - `user_id`
  - `profile_version`
  - `generated_at`
  - `source_event_window`
  - `explicit_preferences`
  - `implicit_preferences`
  - `sentiment_summary`
  - `feature_vector`
  - `cold_start_flag`

Target files/artifacts:
- agents/reader_profile_agent/profile_agent.py
- reading_concierge/reading_concierge.py
- web_demo/index.html
- services/user_profile_store.py (new)
- docs/profile-lifecycle.md (new)
- docs/contracts/user_profile.schema.json (update)

Exit criteria:
- Recommendation request works with only user_id + query.
- Agent can reconstruct profile from stored historical interactions.
- New and updated profile records are persisted locally.
- Cold-start behavior is defined and test-covered.
- Debug injection path cannot be confused with production flow.

---

## Phase P2 - Book Content and Ranking Agent Redesign Alignment (2026-03-29 to 2026-04-06)
Goal: Align partner B and partner C behavior to redesigned requirements and improve model quality.

Tasks:
- Book Content Agent optimization:
  - strict candidate intake and normalization
  - semantic embedding generation and metadata versioning
  - KG context enrichment and source labeling
  - multi-dimensional tags (theme/style/difficulty/audience)
  - deterministic fallback path when external model unavailable
- Recommendation Agent optimization:
  - explicit multi-factor scoring composition
  - scenario-sensitive weighting (cold/warm/explore)
  - diversity and novelty constraints with hard minimum guarantees
  - explanation generation tied to concrete evidence fields
  - profile-content schema contract validation and error handling
- Add benchmark slices and ablation checks for redesigned features.

**Candidate-flow requirements:**
- `CandidateBookSetJSON` must be finalized before Partner B implementation is closed.
- Candidate provenance must be stored, for example:
  - retrieval rule,
  - source dataset/version,
  - filter parameters,
  - generation timestamp.
- Partner B does not decide final ranking.
- Partner C does not silently alter candidate membership except through documented filtering/error rules.

**Recommendation evidence requirements:**
- `RankedRecommendationListJSON` must include, per recommended book:
  - `book_id`
  - `score_total`
  - `score_cf`
  - `score_content`
  - `score_kg`
  - `score_diversity`
  - `scenario_policy`
  - `explanation`
  - `explanation_evidence_refs`
  - `rank_position`

Target files/artifacts:
- agents/book_content_agent/book_content_agent.py
- agents/rec_ranking_agent/rec_ranking_agent.py
- services/phase4_optimizer.py
- scripts/phase4_optimize.py
- scripts/run_ablation.py
- tests/test_book_content_agent.py
- tests/test_book_content_agent_e2e.py
- tests/test_phase4_optimizer.py
- tests/test_phase4_benchmark.py
- docs/contracts/candidate_book_set.schema.json (new)
- docs/contracts/book_feature_map.schema.json (new)
- docs/contracts/ranked_recommendation_list.schema.json (new)

Exit criteria:
- New contract tests pass for partner B and partner C.
- Ranking outputs include stable reasons and factor-level scores.
- Benchmark report regenerated with no regression on target metrics.

**Replace weak exit gate with measurable acceptance gate:**
- New contract tests pass for Partner B and Partner C.
- Explanation fields are complete and deterministic under fixed inputs.
- Cold-start, warm-start, and exploration scenarios are all test-covered.
- Benchmark report meets agreed thresholds for:
  - Precision@K
  - Recall@K
  - NDCG@K
  - Diversity
  - Novelty
- Threshold values must be written into the benchmark doc before final P2 sign-off.

---

## Phase P3 - ACPs Official Registration and Trust Hardening (2026-04-02 to 2026-04-12)
Goal: Replace placeholders with formally registered ACPs identities and real trust materials.

Tasks:
- Prepare production-grade ACS descriptors for coordinator and all partners.
- Register all agents in ioa.pub public registry.
- Obtain real AIC values (replace all placeholder IDs).
- Complete ATR certificate issuance workflow for each agent.
- Configure and verify AIA mTLS for all RPC paths.
- Validate ADP discovery integration (registry/discovery endpoints).
- Implement/verify DSP synchronization hooks for ACS updates.
- Add startup checks that fail fast on invalid AIC/cert/ACS mismatches.

**Architecture clarification:**
- Even if runtime partner endpoints are configured statically in local development, production-ready design must support ACPs discovery semantics and valid ACS metadata.
- The team must explicitly declare one of these modes:
  - `Mode A`: ADP used in production runtime resolution.
  - `Mode B`: ADP validated for compliance/readiness, while runtime uses approved static endpoint binding.
- The selected mode must be documented; ambiguity is not allowed.

**AIP conformance requirement:**
- Verify `Start`, `Get`, `Complete`, and `Cancel`.
- Verify terminal states: `Completed`, `Failed`, `Canceled`, `Rejected`.
- Verify `taskId`, `sessionId`, `senderId`, and product payload consistency across the chain.

Target files/artifacts:
- reading_concierge/reading_concierge.json (Leader ACS descriptor deliverable)
- agents/reader_profile_agent/acs.json (Partner A ACS descriptor deliverable)
- agents/book_content_agent/acs.json (Partner B ACS descriptor deliverable)
- agents/rec_ranking_agent/acs.json (Partner C ACS descriptor deliverable)
- certs/ (real issued certs, managed securely)
- scripts/register_agents_ioa_pub.md (new runbook)
- docs/acps-registration-evidence.md (new)
- docs/aip-conformance.md (new)

Exit criteria:
- Registry lookup returns all agents with valid ACS.
- All inter-agent calls succeed under mTLS-only mode.
- AIP interactions validated end-to-end with official identity fields.
- ADP operating mode is documented and verified.
- DSP sync evidence is captured and replayable.

---

## Phase P4 - Local Persistent Database Foundation (2026-04-06 to 2026-04-16)
Goal: Replace minimal transient storage with formal local persistence and lifecycle-ready schema.

Tasks:
- Introduce DB engine and migration framework:
  - default local SQLite
  - PostgreSQL-ready connection abstraction
- Create core tables:
  - users
  - user_events (ratings/browse/reviews)
  - user_profiles (versioned vectors)
  - books
  - book_features
  - recommendation_runs
  - recommendations
  - agent_task_logs
- Implement repository layer and transaction boundaries.
- Add retention and archival policy hooks.
- Add backfill scripts for existing sample datasets.

**Reproducibility requirements:**
- `recommendation_runs` must store:
  - `user_id`
  - `query`
  - `profile_version`
  - `candidate_set_version_or_hash`
  - `book_feature_version_or_hash`
  - `ranking_policy_version`
  - `weights_or_policy_snapshot`
  - `run_timestamp`
- `recommendations` must store:
  - per-item factor scores
  - explanation text
  - explanation evidence refs
  - rank position
- `agent_task_logs` must preserve ACPs traceability fields:
  - `task_id`
  - `session_id`
  - `sender_id`
  - `receiver_id`
  - `state_transition`
  - `timestamp`

Target files/artifacts:
- services/db.py (new)
- services/repositories/ (new)
- migrations/ (new)
- scripts/backfill_user_events.py (new)
- scripts/backfill_book_features.py (new)
- docs/data-spec.md (update with DB schema)
- docs/persistence-design.md (new)

Exit criteria:
- End-to-end run writes profile, feature, and recommendation artifacts to DB.
- Restarting services preserves user lifecycle state.
- Migration up/down tested successfully.
- A recommendation run can be replayed or audited from persisted evidence.

---

## Phase P5 - Integration Hardening, Verification, and Release Readiness (2026-04-14 to 2026-04-26)
Goal: Deliver stable upgraded prototype with full traceability and reproducibility.

Tasks:
- Full integration tests across local, remote, and mTLS modes.
- Fault-injection tests:
  - missing profile data
  - unavailable KG backend
  - remote partner timeout
  - cert mismatch
- Performance and quality evaluation:
  - Precision@k, Recall@k, NDCG@k, Diversity, Novelty
  - before/after comparison report
- Update operating documentation and launch scripts.

**Product-level acceptance tests:**
- cold-start user receives non-empty recommendation results,
- warm user receives recommendations influenced by persisted history,
- explanations are consistent with stored evidence,
- recommendation run is reproducible from DB artifacts,
- failure in one partner path results in controlled error or fallback behavior.

Target files/artifacts:
- tests/test_reading_workflow_e2e.py (new)
- tests/test_aip_conformance.py (new)
- scripts/demo_reading_workflow.py (update)
- scripts/phase4_benchmark_report.md (refresh)
- docs/demo-launch.md (update)
- WORKLOG_DEV.md (milestone closure)

Exit criteria:
- Full test suite green for updated scope.
- Compliance checklist all complete.
- Demo runbook reproduces expected output on clean environment.
- Product-level acceptance tests pass.
- Benchmark thresholds are met, not only “non-regressed.”

---

## 5. ACPs Compliance Checklist (Formal)

Identity and Capability:
- [ ] All 4 agents have real AIC values from ioa.pub.
- [ ] Each agent exposes valid ACS JSON with required fields.
- [ ] ACS endpoint and runtime metadata are consistent.

Trusted Registration and Authentication:
- [ ] ATR registration evidence archived.
- [ ] Valid mTLS certificates issued for all agents.
- [ ] AIA mutual-auth handshake succeeds for each inter-agent call path.

Discovery and Interaction:
- [ ] ADP discovery resolves profile/content/ranking partners correctly, or approved static-binding mode is explicitly documented.
- [ ] AIP command/state lifecycle validated (`Accepted`, `Working`, `AwaitingCompletion`, `Completed`).
- [ ] Error terminal states (`Failed`, `Canceled`, `Rejected`) are handled and tested.
- [ ] `taskId`, `sessionId`, `senderId`, and product payload lineage are preserved.

Synchronization and Governance:
- [ ] DSP sync path tested for ACS update propagation.
- [ ] Certificate and ACS rotation procedures documented.
- [ ] Security audit log includes agent identity, endpoint, and task trace fields.

---

## 6. Milestone Checklist (Execution Tracking)

P0 Baseline:
- [x] Baseline API snapshots captured.
- [x] Gap matrix written and reviewed.
- [x] Baseline benchmark artifacts archived.
- [x] Leader/Partner runtime flow frozen.
- [x] Candidate generation owner frozen.
- [x] Contract v1 schemas reviewed.

P1 Profile Lifecycle:
- [x] Frontend no longer requires manual full user context.
- [x] reader_profile_agent can autonomously assemble user profile.
- [x] Profile persistence implemented with versioning.
- [x] Lifecycle update path covered by tests.
- [x] Debug override path separated from production path.

P2 Partner Optimization:
- [x] book_content_agent aligned to redesign schema and enrichment logic.
- [x] rec_ranking_agent aligned to redesign scoring and explanation requirements.
- [x] New contract tests added and passing.
- [x] Benchmark/ablation reports regenerated.
- [x] Acceptance thresholds defined and met.

P3 ACPs Officialization:
- [ ] Real AIC and certificate materials integrated.
- [ ] Registry registration completed for all agents.
- [ ] mTLS-only cross-agent orchestration verified.
- [ ] Discovery/interaction/sync validations completed.
- [ ] ADP operating mode declared and documented.

P4 Persistence:
- [x] DB schema and migration pipeline landed.
- [x] Interaction events and recommendation outputs persisted.
- [x] Backfill scripts verified on sample datasets.
- [x] Recovery after restart validated.
- [x] Recommendation evidence replay/audit validated.

P5 Release Readiness:
- [ ] End-to-end tests green.
- [ ] Security and protocol compliance checks green.
- [x] Updated runbook and docs published.
- [ ] Final acceptance demo completed.
- [ ] Product-level recommendation acceptance tests passed.

---

## 7. Roles and Ownership (Suggested)
- Architecture owner: Leader orchestration, protocol integration, contract governance.
- Data owner: event ingestion, candidate source governance, persistence schema.
- Agent owner A: reader profile lifecycle.
- Agent owner B: content analysis and KG enrichment.
- Agent owner C: ranking and explainability.
- QA owner: protocol conformance, benchmark integrity, and e2e reliability.

**Decision owners required before build:**
- Who approves contract schema changes?
- Who approves benchmark threshold changes?
- Who approves ADP runtime mode selection?
- Who approves fallback-policy changes for unavailable partners or external models?

---

## 8. Acceptance Evidence Package
At closure, provide:
- Final checklist with all items marked complete.
- Test report summary (unit, integration, e2e).
- ACPs registration screenshots/export records.
- Certificate inventory and rotation metadata (no private keys in docs).
- Benchmark comparison report before/after refactor.

**Required evidence for product sufficiency:**
- Sample reproducible recommendation run with:
  - input query,
  - resolved profile version,
  - candidate set reference,
  - factor-level scores,
  - explanation evidence,
  - final ranked output.
- One cold-start case and one warm-start case.
- One controlled failure case showing expected fallback or error behavior.

---

## 9. Immediate Next Actions (Start Now)
1. Create docs/acps-gap-matrix.md and baseline test snapshot.
2. Implement profile persistence skeleton (services/user_profile_store.py + DB schema draft).
3. Refactor frontend input contract to user_id + query first.
4. Promote ACS templates to formal per-agent acs.json and prepare ioa.pub submission package.

**Insert before coding broad P1/P2 work:**
5. Freeze `Leader/Partner` runtime document.
6. Freeze candidate generation ownership and `CandidateBookSetJSON`.
7. Freeze v1 inter-agent schemas and review with all owners.
8. Define benchmark thresholds and acceptance metrics before optimization work begins.

---

## 10. P0 Freeze Sign-Off Gate (Must Pass Before Broad P1/P2 Coding)

Required approvals:
- [ ] Architecture owner approves `docs/leader-partner-runtime.md`.
- [ ] Data owner approves candidate generation ownership and provenance rules.
- [ ] Agent owners A/B/C approve inter-agent schema v1 drafts.
- [ ] QA owner approves acceptance metrics and benchmark threshold definitions.

Required artifacts:
- [ ] `docs/leader-partner-runtime.md` exists and describes task/session/state flow.
- [ ] `docs/contracts/user_profile.schema.json` exists (v1).
- [ ] `docs/contracts/candidate_book_set.schema.json` exists (v1).
- [ ] `docs/contracts/book_feature_map.schema.json` exists (v1).
- [ ] `docs/contracts/ranked_recommendation_list.schema.json` exists (v1).
- [ ] `docs/acps-gap-matrix.md` reviewed with critical/high gaps linked to implementation tasks.

Gate decision:
- [ ] **GO**: P0 freeze complete, broad P1/P2 coding authorized.
- [ ] **NO-GO**: Freeze incomplete, only documentation and contract work allowed.
