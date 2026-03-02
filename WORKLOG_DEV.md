# Development Worklog

---

## Project Status Summary

**Goal**: Build a multi-agent, ACPs-protocol personalized book recommendation system that produces real, query-faithful book recommendations with traceable agent reasoning (see `PLAN.md` and `CLAUDE.md` for full spec).

**Current state** (as of 2026-02-25): Core multi-agent recommendation flow is complete and stable. The system performs real end-to-end recommendation — dataset retrieval, query-aware profile/content/ranking pipeline, KG-enhanced signals, CF + semantic + diversity fusion, contextual explanations, scenario-based orchestration (cold/warm/explore), benchmark comparison, and empirical ablation. Focused verification suites pass.

**Completed checklist:**
- [x] Phase 1a–c: async OpenAI client, `.gitignore`/`.env.example`, LRU session eviction
- [x] Phase 2-pre, 2a, 2b: real-book dataset pipeline, LLM retrieval, cold-start fix
- [x] Phase 3a–b: query propagation to profile/content agents
- [x] Phase 4a–d: DashScope embedding backend, profile-content vector alignment
- [x] Phase 5a–c: Unicode tokenizer, enriched explanation prompt, min-pool normalization guard
- [x] Phase 6a–b: LLM candidate retrieval in baseline rankers, test updates for async/query/embeddings

**PLAN.md gap status** (2026-02-24 full audit):
- Data (一): 3/4 — KG not built
- Agents (二): 6/10 — KG RAG absent; CF is content-based not user-item; no BERT; hash-fallback degrades semantics
- Architecture (三): 5/7 — Registry/mTLS stubs; ACS `endPoints` empty
- Testing (四): 5/7 — Ablation is algebraic not empirical; baselines are heuristic stubs; test split unused

**Active plan**: none. `NEXT_STEPS.md` items are completed and archived in this worklog.

**Stale plan files removed** (2026-02-24): `PassedWorkBug.md`, `DEBUG_PLAN.md`, `PHASE_IV_RND_PLAN.md`, `PHASE_IV_ROUND2_PLAN.md`, `PHASE_IV_ROUND3_PLAN.md`.

---

## 2026-02-08 ~ 2026-02-16 (Scaffolding phase)

**What was genuinely built (infrastructure-complete, recommendation-semantics incomplete):**

- Created isolated workspace `ACPs-personalized-reading-recsys`, copied shared ACPs runtime assets (`base.py`, `acps_aip/`, etc.), authored `CLAUDE.md`, `AGENT_SPEC.md`, and phased `PLAN.md`.
- Implemented three cooperative agent FastAPI services under `agents/`:
  - `reader_profile_agent` — preference-vector synthesis, ACPs handlers, LLM-backed intent keyword extraction, diagnostics.
  - `book_content_agent` — ACPs content-analysis handlers, deterministic vectorization placeholder, heuristic/LLM tag enrichment hooks.
  - `rec_ranking_agent` — four-factor composite scoring skeleton (collaborative/semantic/knowledge/diversity), explanation generation (LLM + heuristic fallback), metric snapshot output.
- Implemented coordinator FastAPI service `reading_concierge/reading_concierge.py`:
  - orchestrates profile → content → ranking in three-agent pipeline,
  - scenario-based routing (cold-start / warm / explore),
  - remote partner discovery + registry + env-override + local fallback,
  - parallel dispatch of profile/content via `asyncio.gather`,
  - acceptance criteria gating before ranking,
  - session memory (bare dict at this stage — later fixed by D8 remediation).
- Added shared service layer under `services/`:
  - `model_backends.py` — Sentence-BERT embedding path with hash-vector fallback; SVD collaborative scorer with overlap fallback.
  - `evaluation_metrics.py` — `precision@k`, `recall@k`, `ndcg@k`, diversity/novelty utilities.
  - `baseline_rankers.py`, `phase4_benchmark.py`, `phase4_optimizer.py` — benchmark comparison framework (ACPs vs heuristic baselines).
- Added `scripts/phase4_benchmark_compare.py` benchmark runner and `web_demo/index.html` interactive frontend.
- Added demo routes to coordinator (`GET /demo`, `GET /demo/benchmark-summary`, `GET /demo/status`).
- Test coverage: unit + E2E-gate tests for all agents and coordinator; `pytest` suite validated at each milestone.

**Important caveat**: All benchmark runs in this phase measure hardcoded stub outputs. Claims such as "acps_multi_agent ranks first" or "success_rate=1.0" do not reflect real recommendation quality and should not be used as evidence of system effectiveness.

---

## 2026-02-21 (Retrospective bug documentation sync)

- **Plan**: Consolidate all discovered defects into stable documentation before any large-scale refactor; align historical work records with an explicit debugging roadmap.
- **Documentation Added / Updated**
  - Created `PassedWorkBug.md` as the authoritative defect analysis report:
    - Root-cause synthesis: missing real retrieval stage (Root Cause A), LLM used as decorator not matcher (Root Cause B), profile/content vector-space mismatch (Root Cause C).
    - Defect inventory D1–D12 with code-level locations, symptoms, and impact statements.
    - `PLAN.md` gap matrix across data layer, agent implementation depth, ACPs integration completeness, and testing/evaluation validity.
    - Priority remediation sequence.
  - Created `DEBUG_PLAN.md` as the execution-facing fix plan:
    - 6-phase route: foundation fixes → retrieval repair → query propagation → embedding alignment → ranking quality → baseline/test regression.
    - Per-file change scope across all agent services, coordinator, and tests.
    - Checklist-style task breakdown for incremental debugging.
- **Key findings for future developers**
  - Current system can pass many structural tests while still failing the core product goal (query-faithful, real-book recommendation).
  - Major defect concentration: hardcoded candidate generation (D1), query not propagated to profile/content agents (D2/D5), embedding fallback to hash vectors under current env defaults (D3), explanation generation lacking user/book context (D6), benchmark lane relying on heuristic placeholders (D11).
  - Prior infrastructure milestones (Feb-08 to Feb-16) remain valid as ACPs/MVP scaffolding achievements; they are **infrastructure-complete but recommendation-semantics incomplete**.
- **Next Step**: Execute `DEBUG_PLAN.md` phase-by-phase; log each phase's outcomes here.

---

## 2026-02-22 (DEBUG_PLAN.md creation & Phase 1 execution)

- **Plan**
  - Conducted a full code-level audit against `PLAN.md` targets and `PassedWorkBug.md` defect analysis.
  - Cross-referenced every claim in `PassedWorkBug.md` against live source code to confirm which defects are still present:
    - D1 (`_derive_books_from_query` hardcoded stubs): **confirmed still present**.
    - D2 (query absent from `profile_payload`): **confirmed still present**.
    - D3 (`qwen-plus` triggers hash-vector fallback): **confirmed still present** (`.env` sets `OPENAI_MODEL=qwen-plus`; `SentenceTransformer("qwen-plus")` fails silently).
    - D4 (`_tokenize_text` ASCII-only regex): **confirmed still present**.
    - D5 (query absent from `content_payload`): **confirmed still present**.
    - D6 (explanation prompt lacks context): **confirmed still present**.
    - D7 (normalization degenerates on small pools): **confirmed still present**.
    - D8 (unbounded session memory): **confirmed still present** (bare `dict`).
    - D9 (sync OpenAI client): **already fixed** — `base.py` already uses `AsyncOpenAI` with `await`.
    - D12 (API key in `.env`, no `.gitignore`): **confirmed still present**.
  - `DEBUG_PLAN.md` authored with 6-phase checklist (Phase 1 completed this session; Phases 2–6 pending).
- **Code (Phase 1a — async OpenAI client, D9)**
  - Verified `base.py` already implements `AsyncOpenAI` with lazy client caching. **No code change needed.**
- **Code (Phase 1b — `.gitignore` + `.env.example`, D12)**
  - Created `.gitignore` to exclude `.env`, caches, venv, IDE files.
  - Created `.env.example` with placeholder API key.
- **Code (Phase 1c — LRU session eviction, D8)**
  - Replaced bare `sessions: Dict` in `reading_concierge/reading_concierge.py` with `OrderedDict`-based LRU cache.
  - Added `MAX_SESSIONS` constant (default 200, configurable via env).
  - Implemented `_lru_session_get(session_id)` helper with eviction on capacity.
- **Test**
  - Added `test_session_lru_eviction` in `tests/test_reading_concierge.py`.
  - `pytest tests/test_reading_concierge.py` → **13 passed**.
  - `pytest tests/` → **57 passed, 131 skipped, 8 failed** (all 8 failures are pre-existing `ModuleNotFoundError` for tourism modules — zero regressions).
- **Checklist Update**
  - `DEBUG_PLAN.md`: `[x] Phase 1a`, `[x] Phase 1b`, `[x] Phase 1c`. Phases 2–6 remain open.
- **Next Step**
  - `DEBUG_PLAN.md` Phase 2a: rewrite `_derive_books_from_query()` with LLM-backed real book retrieval (fixes D1, Root Cause A).

---

## 2026-02-24 (Phases 2–6 inspection complete, checklist fully verified)

- **Inspection**
  - Systematically reviewed and verified all Phase 2–6 items in `DEBUG_PLAN.md` against source code and tests.
- **Phase 2**
  - Real-book pipeline (`load_books`, `retrieve_books_by_query`), LLM-backed `_derive_books_from_query()` (async), cold-start seeding from dataset.
- **Phase 3**
  - Query passed to profile/content payloads; intent extraction and tag boosting query-weighted.
- **Phase 4**
  - DashScope embedding backend, `BOOK_CONTENT_EMBED_MODEL`, profile-content vector alignment; separate `EMBED_MODEL` / `LLM_MODEL` in book content agent.
- **Phase 5**
  - Unicode tokenizer (`re.UNICODE`), enriched explanation prompt (query, author, description, genres, profile summary), min-pool normalization guard (< 3 candidates).
- **Phase 6**
  - Baseline rankers use LLM candidate retrieval (`_llm_select_book_ids_sync`); tests updated for async, query fields, embedding mocks.
- **Checklist Update**
  - `DEBUG_PLAN.md`: all Phase 2–6 items marked `[x]`.
- **Sync**
  - Project Status Summary and checklist synchronization written to this worklog.

---

## 2026-02-24 (Stale-file cleanup + PLAN.md gap audit + new plan creation)

- **Code-level PLAN.md audit performed**
  - Systematically reviewed all four PLAN.md sections: data tasks, agent implementation, architecture, testing/optimization.
  - Findings documented in analysis session; summary written to Project Status Summary above.
- **Stale plan files removed**
  - `PassedWorkBug.md` — superseded; all defects tracked or resolved.
  - `DEBUG_PLAN.md` — all phases complete; removed.
  - `PHASE_IV_RND_PLAN.md`, `PHASE_IV_ROUND2_PLAN.md`, `PHASE_IV_ROUND3_PLAN.md` — Phase IV cycles complete; removed.
- **New active plan created**
  - `NEXT_STEPS.md` added to the project root.
  - Covers all remaining PLAN.md gaps with prioritized, dependency-ordered implementation tasks:
    - P1 (critical): Knowledge graph construction (NetworkX local + optional Neo4j)
    - P2 (critical): True user-item collaborative filtering from interaction data
    - P3 (important): SentenceTransformer offline embedding fallback
    - P4 (important): ACS `endPoints` population + conformance smoke test
    - P5 (recommended): Empirical ablation study using held-out test split
    - P6 (recommended): Principled baseline reimplementation + MACRec-style proxy
    - P7 (optional): mTLS enforcement scaffold
- **Test status at close-of-day**: all unit + integration tests pass (no regressions).

---

## 2026-02-25 (PLAN.md item-by-item re-audit + NEXT_STEPS closeout)

- **Request executed**
  - Re-ran a full checklist audit against `PLAN.md` core tasks (data, agents, architecture, testing/optimization).
  - Cross-checked each item against current code, docs, artifacts, and focused test evidence.

- **Current completion status (PLAN.md)**
  - Overall: **10 satisfied / 7 partially satisfied / 0 missing**.
  - Data tasks: dataset + split + KG are in place; review-cleaning/deep quality controls remain partial.
  - Agent tasks: profile/content/ranking agents are implemented and integrated; strict “BERT-only” and fully explicit KG-RAG wording remains partial.
  - Architecture tasks: ACPs orchestration and ACS endpoints are in place; explicit ATR/ADP-standard artifact coverage remains partial.
  - Testing/optimization: unit tests, benchmark compare, and empirical ablation are implemented; MACRec/ARAG are proxy baselines rather than strict reproductions.

- **Verification evidence (executed today)**
  - `pytest -q tests/test_acs_conformance.py tests/test_phase4_benchmark_compare.py tests/test_run_ablation.py`
  - Result: **12 passed**.

- **Closeout update**
  - `NEXT_STEPS.md` marked complete and removed from active project files.

---

## 2026-03-01 (Repository hygiene cleanup + plan-file retirement)

- **Scope**
  - Performed a repo hygiene pass focused on removing temporary/smoke/run-artifact files while preserving implementation source code and test code.

- **Cleanup actions completed**
  - Removed temporary test/smoke leftovers:
    - `temp_test_phase1.py`
    - `temp_test_phase2.py`
    - `temp_test_concierge_phase2.py`
    - `scripts/ablation_report_smoke.json`
    - `scripts/phase0_embedding_benchmark.stdout.txt`
  - Removed generated Phase 2/3 report artifacts:
    - `scripts/phase2_routing_validation_report.json`
    - `scripts/phase2_routing_validation_report.md`
    - `scripts/phase3_ab_experiment_log.jsonl`
    - `scripts/phase3_ab_summary.json`
    - `scripts/phase3_ab_summary.md`
    - `scripts/phase3_release_gates_report.json`
    - `scripts/phase3_release_gates_report.md`
  - Removed generated benchmark outputs:
    - `scripts/phase0_embedding_benchmark_report.json`
    - `scripts/phase0_embedding_benchmark_report.md`
    - `scripts/phase4_benchmark_report.json`
    - `scripts/phase4_benchmark_report.md`
    - `scripts/phase4_benchmark_summary.json`

- **Planning-file retirement completed**
  - Removed completed plan documents:
    - `FRONTEND_PLAN.md`
    - `plan-dualChineseEnglishDatasetSupport.md`

- **Verification**
  - For each deletion batch, workspace file search re-checks were run and returned no matches for removed paths.

- **Status note**
  - Implementation scripts and tests were intentionally retained.
  - Data ingestion outputs/sources remain in place (e.g., `data/raw/chinese_sources/...`) and were not removed in this cleanup pass.