# Development Worklog

## 2026-02-08
- Created isolated workspace `ACPs-personalized-reading-recsys` and copied shared ACPs runtime assets (`base.py`, `requirements.txt`, `acps_aip/`, `tour_assistant/`, `beijing_catering/`, `tests/`).
- Authored `CLAUDE.md` outlining the phased plan, architecture goals, risks, and success criteria for the reading recommender prototype.
- Relocated `plan.md` into the new workspace to keep all reading-system artifacts together.
- Produced `AGENT_SPEC.md`, detailing coordinator/cooperative agent roles, ACPs registration needs, payload contracts, and interaction flow.
- Recreated a dedicated Python 3.13 virtual environment, installed dependencies, and copied the tourism `.env` file to bootstrap configuration parity.
- Drafted `agents/reader_profile_agent/plan.md` plus supporting config templates to guide the first agent build-out.
- Implemented the Reader Profile Agent FastAPI service (`agents/reader_profile_agent/profile_agent.py`), including payload validation, preference-vector synthesis, ACPs handlers, and structured outputs.
- Added automated coverage in `tests/test_reader_profile_agent.py`, updated `tests/conftest.py` for optional imports, and verified the suite via `pytest tests/test_reader_profile_agent.py` (3 passed).

## 2026-02-15
- Upgraded `agents/reader_profile_agent/profile_agent.py` with additional preference axes (themes/pacing/difficulty), async LLM-backed intent keyword extraction tied to `.env` API keys, richer diagnostics, and environment health checks to align with `AGENT_SPEC.md` expectations.
- Hardened payload analytics by normalizing feature fallbacks, capturing embedding version metadata, and surfacing ACPs-ready summaries plus structured outputs for downstream agents.
- Extended `tests/test_reader_profile_agent.py` with an end-to-end scenario that patches `call_openai_chat`, asserts `.env`-driven API usage, and validates `intent_keywords` plus diagnostics alongside the existing unit tests.
- Ran `pytest tests/test_reader_profile_agent.py` (4 passed) to confirm the agent is stable before moving on to the next component.
- **Next agent plan**: begin `book_content_agent` scaffolding—reuse ACPs server pattern, design ACS template, and implement content vectorization stubs (Sentence-BERT placeholder + knowledge-graph enrichment hooks). Prepare fixtures for candidate book metadata and draft corresponding unit/E2E tests mirroring today’s profile-agent workflow.

- Created `agents/book_content_agent/` with `plan.md`, `config.example.json`, and `book_content_agent.py`, implementing ACPs handlers and content-analysis outputs aligned to `AGENT_SPEC.md` (`book.vectorize`, `kg.enrich`, `tag.extract`).
- Implemented deterministic vectorization placeholders, heuristic + optional LLM tag enrichment, `kg_refs` trace extraction, payload validation (`candidate_ids|books|ingest_batch_id`, conditional `kg_endpoint`), and structured diagnostics.
- Completed code review pass (static diagnostics: no errors) before testing.
- Added `tests/test_book_content_agent.py` (unit + E2E-style flow with external-model patch and terminal response print) and `tests/test_book_content_agent_e2e.py` (live HTTP E2E skeleton, gated by `END_TO_END=1`).
- Updated `tests/conftest.py` with `client_book_content` fixture.
- Test verification:
	- `pytest -s tests/test_book_content_agent.py` → 4 passed
	- `pytest tests/test_reader_profile_agent.py tests/test_book_content_agent.py` → 8 passed
	- Note: global `python`/`pytest` launcher on this machine may point to a different interpreter; stable execution command is `venv/Scripts/python.exe -m pytest ...`.
- Milestone status: `book_content_agent` development + local validation completed, ready to proceed to `rec_ranking_agent` implementation.

- Started and completed `rec_ranking_agent` incremental scaffolding under `agents/rec_ranking_agent/` with `plan.md`, `config.example.json`, and ACPs service implementation in `rec_ranking_agent.py`.
- Implemented recommendation decision workflow per `AGENT_SPEC.md` (Section 2.3): four-factor composite scoring (`collaborative`, `semantic`, `knowledge`, `diversity`), constraints (`top_k`, `novelty_threshold`, `min_new_items`), explanation bundle generation (LLM + heuristic fallback), and `outputs.metric_snapshot` monitoring payload.
- Added test coverage:
	- `tests/test_rec_ranking_agent.py` (unit + E2E-style flow, including terminal response print for model-call path)
	- `tests/test_rec_ranking_agent_e2e.py` (live HTTP E2E skeleton, gated by `END_TO_END=1`)
	- updated `tests/conftest.py` with `client_rec_ranking` fixture.
- Validation results:
	- `venv/Scripts/python.exe -m pytest -s tests/test_rec_ranking_agent.py` → 4 passed
	- `venv/Scripts/python.exe -m pytest tests/test_reader_profile_agent.py tests/test_book_content_agent.py tests/test_rec_ranking_agent.py` → 12 passed
- Current milestone status: core cooperative agents (`reader_profile_agent`, `book_content_agent`, `rec_ranking_agent`) are now scaffolded, implemented, and locally validated; next phase is coordinator (`reading_concierge`) orchestration and full integration flow.

## 2026-02-16
- Started and completed coordinator scaffolding in `reading_concierge/`:
	- `reading_concierge/reading_concierge.py`
	- `reading_concierge/reading_concierge.json`
	- package init file.
- Implemented unified orchestration flow through `/user_api`:
	1) call `reader_profile_agent` (`/reader-profile/rpc`) to build user preference profile,
	2) call `book_content_agent` (`/book-content/rpc`) to derive vectors/tags/KG context,
	3) call `rec_ranking_agent` (`/rec-ranking/rpc`) to produce ranked recommendations + explanations + metric snapshot.
- Added coordinator-side session memory and structured partner status/result aggregation (`partner_tasks`, `partner_results`) for traceable ACPs-style lifecycle visibility.
- Added integration tests:
	- `tests/test_reading_concierge.py` (in-process orchestration integration with success path + needs-input path)
	- `tests/test_reading_concierge_e2e.py` (live HTTP E2E skeleton, gated by `END_TO_END=1`)
	- updated `tests/conftest.py` with `client_reading_concierge` fixture.
- Validation results:
	- `venv/Scripts/python.exe -m pytest -s tests/test_reading_concierge.py` → 2 passed
	- `venv/Scripts/python.exe -m pytest tests/test_reader_profile_agent.py tests/test_book_content_agent.py tests/test_rec_ranking_agent.py tests/test_reading_concierge.py` → 14 passed
- Milestone status: reading coordinator + three-agent orchestration baseline is complete and test-passing; next integration step is extending coordinator routing policies (cold/warm/explore), richer acceptance criteria, and optional remote partner RPC discovery wiring.

- Enhanced `reading_concierge` policy logic with scenario-based routing:
	- **cold start**: auto-seeds minimal user/history signals to unblock profile analysis and continue orchestration;
	- **warm mode**: keeps strict validation behavior and returns `needs_input` when profile signals are insufficient;
	- **exploration mode**: applies novelty/diversity-biased ranking policy (`min_new_items>=1`, higher diversity weight).
- Added remote partner discovery + fallback mechanism in coordinator:
	- optional discovery lookup via `READING_DISCOVERY_BASE_URL`;
	- optional remote endpoint overrides via env (`READER_PROFILE_RPC_URL`, `BOOK_CONTENT_RPC_URL`, `REC_RANKING_RPC_URL`);
	- resilient fallback to local in-process partner invocation when remote calls fail.
- Extended coordinator observability outputs:
	- `scenario` included in `/user_api` response;
	- partner route metadata in `partner_tasks` (`route`, `rpc_url`, `fallback`);
	- policy snapshot stored in `partner_results["_policy"]`.
- Added/updated coordinator tests in `tests/test_reading_concierge.py`:
	- warm-mode missing input path,
	- auto cold-start completion path,
	- explore-mode policy assertions,
	- remote-discovery failure fallback to local execution.
- Validation results (post-enhancement):
	- `venv/Scripts/python.exe -m pytest -s tests/test_reading_concierge.py` → 5 passed
	- `venv/Scripts/python.exe -m pytest tests/test_reader_profile_agent.py tests/test_book_content_agent.py tests/test_rec_ranking_agent.py tests/test_reading_concierge.py` → 17 passed

- **Phase checkpoint (vs `plan.md`)**:
	- Section (II) *智能体设计与实现任务*: **MVP-level completed** (three core agents implemented and test-passing), but not fully final for research-grade target yet (current implementations still include heuristic/stub-like components in place of full BERT/Sentence-BERT/SVD production pipelines).
	- Section (III) *系统架构与集成任务*: **partially completed** (coordinator + unified orchestration + scenario policy + discovery fallback done), but full target still pending for deeper ACPs productionization (registry/workflow-engine-level integration and stricter parallel orchestration semantics).
- **Next-step quick start (for next session)**:
	1. Upgrade model layer from placeholders to production pipelines (BERT/Sentence-BERT/SVD modules).
	2. Strengthen coordinator acceptance criteria and parallel-dispatch strategy.
	3. Connect discovery/registry components to real remote partner deployment.
	4. Expand system-level evaluation (`Precision@k`, `Recall@k`, `NDCG@k`, diversity/novelty) and ablation tests.
	5. Prepare demo workflow/API script for repeatable end-to-end showcase.

- **Session continuation completed (Plan → Code → Code Review → Test → Feedback → Update → Matching Requirements)**:
	- **Plan**: reviewed and aligned implementation scope with `plan.md`, `AGENT_SPEC.md`, `CLAUDE.md`, and this worklog’s quick-start list.
	- **Code (model-layer upgrade)**:
		- Added shared backend utilities in `services/model_backends.py`:
			- Sentence-BERT-capable embedding path (`sentence-transformers`) with deterministic hash fallback.
			- SVD collaborative scoring estimator (`scikit-learn` TruncatedSVD) with overlap fallback.
		- Upgraded `agents/book_content_agent/book_content_agent.py` to use shared embedding backend and expose `embedding_backend` metadata in outputs/diagnostics.
		- Upgraded `agents/rec_ranking_agent/rec_ranking_agent.py` to auto-estimate collaborative scores via SVD backend when `svd_factors` are absent; exported `collaborative_backend` metadata.
	- **Code (coordinator orchestration & registry/discovery)**:
		- Refactored `reading_concierge/reading_concierge.py` to dispatch **profile/content in parallel** via `asyncio.gather`.
		- Added per-partner acceptance criteria gating (`acceptance.passed/reason`) before proceeding to ranking.
		- Added remote endpoint resolution path with registry hook:
			- `READING_DISCOVERY_BASE_URL` discovery lookup,
			- `READING_REGISTRY_BASE_URL` registry resolution (`/api/registry/resolve`),
			- env override fallback (`READER_PROFILE_RPC_URL`, `BOOK_CONTENT_RPC_URL`, `REC_RANKING_RPC_URL`).
		- Passed user history into ranking payload to support collaborative estimation.
	- **Code (evaluation & ablation)**:
		- Added `services/evaluation_metrics.py` with `precision@k`, `recall@k`, `ndcg@k`, diversity/novelty packaging, and ablation impact report.
		- Integrated coordinator response `evaluation` block with optional ground-truth and ablation outputs.
	- **Code (demo workflow)**:
		- Added `scripts/demo_reading_workflow.py` for repeatable API demo requests against `/user_api`.
	- **Code Review**:
		- Static diagnostics run on all changed files (`get_errors`) → no errors.
	- **Test**:
		- Added/updated tests:
			- `tests/test_evaluation_metrics.py` (new)
			- `tests/test_book_content_agent.py` (embedding backend assertions)
			- `tests/test_rec_ranking_agent.py` (collaborative backend assertions)
			- `tests/test_reading_concierge.py` (acceptance/evaluation + parallel-flow expectation)
		- Validation commands:
			- `venv/Scripts/python.exe -m pytest tests/test_book_content_agent.py tests/test_rec_ranking_agent.py tests/test_reading_concierge.py tests/test_evaluation_metrics.py` → **15 passed**
			- `venv/Scripts/python.exe -m pytest tests/test_reader_profile_agent.py tests/test_book_content_agent.py tests/test_rec_ranking_agent.py tests/test_reading_concierge.py tests/test_evaluation_metrics.py` → **19 passed**
	- **Matching requirements (against quick-start + plan milestones)**:
		1. Model-layer upgrade (Sentence-BERT/SVD-capable path): **completed with fallback-safe implementation**.
		2. Coordinator acceptance + parallel dispatch: **completed**.
		3. Discovery/registry remote wiring: **completed (discovery + registry + env override + local fallback)**.
		4. System-level evaluation + ablation tests: **completed (metrics module + tests + response integration)**.
		5. Repeatable demo workflow script: **completed**.
