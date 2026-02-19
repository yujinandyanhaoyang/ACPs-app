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

	## 2026-02-16 (Phase IV kickoff)
	- **Plan**
		- Added `PHASE_IV_RND_PLAN.md` to formalize Phase (IV) execution under required workflow: `Plan → Code → Code Review → Test → Feedback → Update → Matching Requirements`.
		- Defined immediate target as metrics-driven optimization loop over full ACPs multi-agent prototype.
	- **Code**
		- Added `services/phase4_optimizer.py` with:
			- experiment-run aggregation (`success_rate`, `precision@k`, `recall@k`, `ndcg@k`, `diversity`, `novelty`, `latency mean/p95`),
			- objective scoring with latency penalty,
			- best-configuration selector.
		- Added `scripts/phase4_optimize.py` to run local ASGI benchmark against `/user_api` over multiple ranking configs and export a report.
		- Added reproducible scenario set `scripts/phase4_cases.json` (warm / explore / cold).
		- Added optimizer unit tests in `tests/test_phase4_optimizer.py`.
	- **Code Review**
		- Static diagnostics for new files: no errors.
		- Fixed one runtime issue in optimization script (`ModuleNotFoundError: reading_concierge`) by adding project-root `sys.path` bootstrap.
	- **Test**
		- `venv/Scripts/python.exe -m pytest tests/test_phase4_optimizer.py tests/test_reading_concierge.py` → **8 passed**.
		- `venv/Scripts/python.exe scripts/phase4_optimize.py --pretty` executed successfully and produced optimization report.
	- **Feedback**
		- Early benchmark snapshot: all tested configs achieved `success_rate=1.0`; objective function selected `semantic_plus` as best under current latency-penalized weighting.
		- Observation: metric differentiation is currently dominated by `ndcg`/latency on a small case set; scenario scale should be expanded next.
	- **Update**
		- Optimization runner is now executable as a repeatable Phase (IV) loop entry point.
		- Next update target: expand benchmark cases and add baseline-comparison lane for stronger contrast in objective ranking.
	- **Matching Requirements (PLAN.md Phase IV)**
		1. 单体测试：**in progress (optimizer unit tests landed)**.
		2. 集成测试：**in progress (coordinator regression included; remote true-e2e still pending)**.
		3. 系统评估：**in progress (batch report includes Precision/Recall/NDCG/多样性/新颖性 + latency)**.
		4. 消融研究：**available foundation (existing ablation in response + optimizer loop), further experiment expansion pending**.
		5. 对标测试：**pending (traditional hybrid / MACRec / ARAG comparison lane not yet implemented)**.
		6. 演示系统：**partially ready (demo + optimization scripts present; UI polish/packaging pending)**.

	## 2026-02-19 (Phase IV Round-2)
	- **Plan**
		- Added `PHASE_IV_ROUND2_PLAN.md` to formalize remaining Phase (IV) target completion with required workflow.
		- Prioritized pending high-gap items from `PLAN.md`: 对标测试 + stronger benchmark coverage.
	- **Code**
		- Added baseline comparison services:
			- `services/baseline_rankers.py` (`traditional_hybrid`, `multi_agent_proxy`).
			- `services/phase4_benchmark.py` (method-case evaluation, method-run aggregation, leaderboard ranking).
		- Added comparison runner:
			- `scripts/phase4_benchmark_compare.py` to benchmark `acps_multi_agent` against baselines and export JSON report.
		- Expanded benchmark set in `scripts/phase4_cases.json` from 3 to 5 scenarios (cold/warm/explore coverage improved).
		- Added unit tests:
			- `tests/test_baseline_rankers.py`
			- `tests/test_phase4_benchmark.py`
		- Updated benchmark objective to include dual scores:
			- `objective_score` (quality-first, no latency penalty)
			- `objective_score_latency_aware` (light latency penalty)
		  for fair ACPs vs heuristic baseline interpretation.
	- **Code Review**
		- Static diagnostics across all new Round-2 files: no errors.
	- **Test**
		- `venv/Scripts/python.exe -m pytest tests/test_baseline_rankers.py tests/test_phase4_benchmark.py tests/test_reading_concierge.py` → **11 passed**.
		- `venv/Scripts/python.exe -m pytest tests/test_phase4_benchmark.py tests/test_baseline_rankers.py` (post objective update) → **6 passed**.
		- `venv/Scripts/python.exe scripts/phase4_benchmark_compare.py --pretty` executed successfully and produced benchmark report.
	- **Feedback**
		- On quality-first objective, `acps_multi_agent` ranks first on current 5-case benchmark.
		- On latency-aware objective, ACPs remains competitive but shows expected runtime overhead vs heuristic baselines.
		- Insight: benchmark now distinguishes **quality leadership** and **efficiency trade-off** simultaneously.
	- **Update**
		- Round-2 pipeline now supports repeatable ACPs-vs-baseline evaluation, enabling subsequent optimization and论文对标章节素材输出.
		- Next update focus: add remote-deployment E2E lane and additional external baselines for stronger对标有效性.
	- **Matching Requirements (PLAN.md Phase IV)**
		1. 单体测试：**progressed** (new baseline/benchmark unit tests added).
		2. 集成测试：**progressed** (coordinator regression retained; benchmark uses real `/user_api` local ASGI calls).
		3. 系统评估：**progressed** (expanded 5-case benchmark + aggregate metrics + leaderboard).
		4. 消融研究：**foundation retained** (existing ablation path + benchmark objective decomposition).
		5. 对标测试：**implemented initial lane** (ACPs vs traditional_hybrid vs multi_agent_proxy).
		6. 演示系统：**improved** (new runnable benchmark comparison script + report artifact workflow).

	## 2026-02-19 (Phase IV Round-3 kickoff)
	- **Plan**
		- Added `PHASE_IV_ROUND3_PLAN.md` with confirmed scope decisions:
			- remote E2E reliability first,
			- synthetic benchmark cases retained,
			- fallback-to-local behavior retained as default safety policy.
		- Locked required lifecycle: `Plan → Code → Code Review → Test → Feedback → Update → Matching Requirements`.
	- **Code**
		- Updated coordinator observability in `reading_concierge/reading_concierge.py`:
			- added `remote_attempted` and `route_outcome` metadata for each partner task,
			- kept existing fallback-safe behavior and backward-compatible `route`/`fallback` fields.
		- Updated benchmark compare runner `scripts/phase4_benchmark_compare.py`:
			- added per-case route reliability fields (`remote_attempt_rate`, `fallback_rate`, `remote_success_rate`) and counts.
		- Updated benchmark aggregation service `services/phase4_benchmark.py`:
			- method-level summaries now include remote/fallback rates,
			- leaderboard rows now expose the same observability dimensions.
		- Updated tests:
			- `tests/test_reading_concierge.py`
			- `tests/test_phase4_benchmark.py`
	- **Code Review**
		- Static diagnostics on all changed files: no errors.
	- **Test**
		- `venv/Scripts/python.exe -m pytest tests/test_reading_concierge.py tests/test_phase4_benchmark.py tests/test_phase4_optimizer.py` → **11 passed**.
		- `venv/Scripts/python.exe scripts/phase4_benchmark_compare.py --pretty` executed successfully and generated updated report.
	- **Feedback**
		- New report confirms route reliability fields are emitted and aggregated.
		- Under current local ASGI run, remote-attempt and fallback rates are `0.0` as expected, establishing a clean baseline for upcoming remote-lane experiments.
	- **Update**
		- Round-3 observability foundation is now in place for remote E2E validation without breaking default safe behavior.
		- Next update target: add explicit remote-stress synthetic cases to drive non-zero fallback/remote-attempt evidence lanes.
	- **Matching Requirements (PLAN.md Phase IV)**
		1. 单体测试：**progressed** (benchmark aggregation observability fields validated).
		2. 集成测试：**progressed** (coordinator fallback path now exposes explicit route outcomes).
		3. 系统评估：**progressed** (benchmark reports include reliability dimensions beyond relevance/latency).
		4. 消融研究：**retained** (existing ablation path unchanged and compatible).
		5. 对标测试：**retained + enhanced** (baseline comparison preserved with additional route reliability context).
		6. 演示系统：**progressed** (traceability improved for demo/report explanation).

	## 2026-02-19 (Phase IV Round-3 remote-stress lane)
	- **Plan**
		- Continued the next confirmed Round-3 task: add synthetic remote-stress cases to produce non-zero fallback evidence while keeping fallback-safe policy unchanged.
	- **Code**
		- Updated `scripts/phase4_benchmark_compare.py` with per-case remote-stress patching:
			- for `constraints.remote_stress=true`, partner resolution is forced to synthetic remote URLs and remote RPC invocation is forced to fail,
			- coordinator then exercises real fallback path and emits route/fallback telemetry.
		- Expanded `scripts/phase4_cases.json` from 5 to 7 cases by adding:
			- `remote_stress_warm`
			- `remote_stress_cold`
		- Added `tests/test_phase4_benchmark_compare.py` to validate that ACPs benchmark summary includes non-zero `remote_attempt_rate` and `fallback_rate` for stress-injected runs.
	- **Code Review**
		- Static diagnostics for changed files: no errors.
	- **Test**
		- `venv/Scripts/python.exe -m pytest tests/test_phase4_benchmark_compare.py tests/test_phase4_benchmark.py tests/test_reading_concierge.py` → **9 passed**.
		- `venv/Scripts/python.exe scripts/phase4_benchmark_compare.py --pretty` executed successfully with updated 7-case report.
	- **Feedback**
		- Report now contains non-zero remote reliability evidence for ACPs method:
			- case-level stress runs show `remote_attempt_rate=1.0` and `fallback_rate=1.0`,
			- ACPs method summary shows aggregated non-zero values (`remote_attempt_rate=0.2857`, `fallback_rate=0.2857`).
	- **Update**
		- Round-3 remote E2E lane is now fully exercised in synthetic benchmark mode with reproducible fallback metrics.
	- **Matching Requirements (PLAN.md Phase IV)**
		1. 单体测试：**progressed** (new benchmark-compare stress test added).
		2. 集成测试：**progressed** (fallback path exercised through coordinator during stress runs).
		3. 系统评估：**progressed** (report now includes non-zero remote reliability dimensions).
		4. 消融研究：**retained** (no regression to existing ablation path).
		5. 对标测试：**retained + strengthened** (ACPs-vs-baseline report now contains route reliability contrasts).
		6. 演示系统：**progressed** (demo report now clearly demonstrates remote failure recovery behavior).

	## 2026-02-19 (Phase IV Round-3 second development cycle: strict remote lane)
	- **Plan**
		- Started second Round-3 cycle to advance PLAN.md completion by adding optional strict remote-validation behavior while preserving default fallback-safe policy.
	- **Code**
		- Updated `reading_concierge/reading_concierge.py`:
			- added optional `constraints.strict_remote_validation` handling,
			- in strict mode, remote failure no longer falls back to local and returns failed partner state with explicit `route_outcome` (`remote_failed_strict` / `remote_unavailable_strict`),
			- default mode remains unchanged (`remote_failed_local_fallback`).
		- Updated benchmark pipeline:
			- `scripts/phase4_benchmark_compare.py` now records `strict_remote_validation` and `strict_failure` per ACPs run,
			- `services/phase4_benchmark.py` now aggregates `strict_failure_rate` into method summaries and leaderboard rows.
		- Expanded `scripts/phase4_cases.json` from 7 to 8 cases by adding strict scenario `remote_strict_warm`.
		- Updated tests:
			- `tests/test_reading_concierge.py` (strict mode disables fallback test),
			- `tests/test_phase4_benchmark_compare.py` (strict stress benchmark assertions),
			- `tests/test_phase4_benchmark.py` (strict failure aggregation assertion).
	- **Code Review**
		- Static diagnostics on changed files: no errors.
	- **Test**
		- `venv/Scripts/python.exe -m pytest tests/test_phase4_benchmark_compare.py tests/test_phase4_benchmark.py tests/test_reading_concierge.py tests/test_phase4_optimizer.py` → **14 passed**.
		- `venv/Scripts/python.exe scripts/phase4_benchmark_compare.py --pretty` executed successfully and produced updated 8-case report.
	- **Feedback**
		- Report confirms strict lane is distinguishable from fallback lane:
			- strict case `remote_strict_warm` shows `strict_failure=1.0` with `fallback_rate=0.0`,
			- method summary reports non-zero `strict_failure_rate=0.125` and retained non-zero fallback evidence from stress-fallback cases.
	- **Update**
		- Round-3 now supports two reliability evaluation modes in one benchmark: safe fallback recovery and strict infra validation.
	- **Matching Requirements (PLAN.md Phase IV)**
		1. 单体测试：**progressed** (strict-lane unit assertions added to benchmark aggregation).
		2. 集成测试：**progressed** (coordinator strict remote behavior validated end-to-end in local ASGI pipeline).
		3. 系统评估：**progressed** (report adds strict failure dimension in addition to quality/latency/reliability metrics).
		4. 消融研究：**retained** (existing ablation path unaffected).
		5. 对标测试：**strengthened** (comparison now includes robustness-vs-strictness interpretation axis for ACPs lane).
		6. 演示系统：**progressed** (demo report can now explain both recovery capability and strict validation outcomes).

	## 2026-02-19 (Phase IV Round-3 next coding phase: reliability dashboard + compact demo artifact)
	- **Plan**
		- Started next coding phase to improve demo-readiness and evaluation readability: add side-by-side reliability dashboard and compact summary output.
	- **Code**
		- Updated `scripts/phase4_benchmark_compare.py`:
			- added `reliability_dashboard` section in main benchmark report with ACPs strict-mode vs fallback-mode side-by-side signals,
			- added compact summary builder and `--summary-out` support (default: `scripts/phase4_benchmark_summary.json`).
		- Dashboard dimensions include:
			- strict mode (`case_count`, `failure_case_count`, `failure_rate`),
			- fallback mode (`case_count`, `fallback_observed_case_count`, `fallback_observed_rate`),
			- overall (`remote_attempt_rate`, `fallback_rate`, `remote_success_rate`, `strict_failure_rate`).
		- Updated `tests/test_phase4_benchmark_compare.py` with dashboard and compact-summary assertions.
	- **Code Review**
		- Static diagnostics on changed files: no errors.
	- **Test**
		- `venv/Scripts/python.exe -m pytest tests/test_phase4_benchmark_compare.py tests/test_phase4_benchmark.py tests/test_reading_concierge.py` → **12 passed**.
		- `venv/Scripts/python.exe scripts/phase4_benchmark_compare.py --pretty` executed successfully and generated both report files.
	- **Feedback**
		- `scripts/phase4_benchmark_report.json` now includes `reliability_dashboard` with explicit strict/fallback side-by-side view.
		- `scripts/phase4_benchmark_summary.json` provides compact demo-facing snapshot (winner, ACPs quality, efficiency, reliability).
	- **Update**
		- Next-phase demo and analysis can consume lightweight summary directly without parsing full benchmark payload.
	- **Matching Requirements (PLAN.md Phase IV)**
		1. 单体测试：**progressed** (benchmark compare unit assertions expanded for dashboard/summary fields).
		2. 集成测试：**retained** (coordinator path unchanged; prior strict/fallback integration validations remain valid).
		3. 系统评估：**strengthened** (report now supports clearer reliability interpretation).
		4. 消融研究：**retained** (no ablation-path changes).
		5. 对标测试：**strengthened** (comparison output now easier to interpret across reliability modes).
		6. 演示系统：**strengthened** (compact summary artifact directly supports demo/presentation consumption).

	## 2026-02-19 (Phase IV Round-3 next coding phase: lightweight markdown report generator)
	- **Plan**
		- Added a lightweight Markdown report deliverable to further align with PLAN.md demo/output objectives.
	- **Code**
		- Updated `scripts/phase4_benchmark_compare.py`:
			- added Markdown builder `_build_markdown_report(report, summary)`,
			- added CLI argument `--md-out` (default: `scripts/phase4_benchmark_report.md`),
			- markdown output now generated together with existing JSON report + compact summary.
		- Markdown sections include:
			- run summary,
			- ACPs quality,
			- ACPs efficiency,
			- ACPs reliability dashboard (strict mode / fallback mode / overall).
		- Updated `tests/test_phase4_benchmark_compare.py` with markdown section assertions.
	- **Code Review**
		- Static diagnostics on changed files: no errors.
	- **Test**
		- `venv/Scripts/python.exe -m pytest tests/test_phase4_benchmark_compare.py tests/test_phase4_benchmark.py tests/test_reading_concierge.py` → **13 passed**.
		- `venv/Scripts/python.exe scripts/phase4_benchmark_compare.py --pretty` executed successfully and generated markdown artifact.
	- **Feedback**
		- New deliverable `scripts/phase4_benchmark_report.md` is concise and presentation-ready.
	- **Update**
		- Benchmark workflow now emits three artifact layers for different audiences:
			- full analysis JSON,
			- compact summary JSON,
			- lightweight Markdown report.
	- **Matching Requirements (PLAN.md Phase IV)**
		1. 单体测试：**progressed** (markdown generator behavior covered by tests).
		2. 集成测试：**retained** (no coordinator behavior regression).
		3. 系统评估：**strengthened** (evaluation outputs now easier to consume and review).
		4. 消融研究：**retained** (no change to ablation logic).
		5. 对标测试：**retained + improved readability** (comparison findings now directly human-readable).
		6. 演示系统：**strengthened** (markdown report directly supports deliverable/demo narrative).

	## 2026-02-19 (Phase IV Round-3 next refinement: auto findings & recommendations)
	- **Plan**
		- Added threshold-rule based narrative generation to further refine demo/report deliverables in line with PLAN.md objectives.
	- **Code**
		- Updated `scripts/phase4_benchmark_compare.py`:
			- added default threshold rules for quality/latency/reliability,
			- added `_build_findings_and_recommendations(summary, thresholds=None)`,
			- extended markdown builder to auto-generate `Findings & Recommendations` section.
		- Findings now evaluate:
			- quality (`NDCG@k`),
			- efficiency (`latency_ms_mean`),
			- reliability (`fallback_rate`, `strict_failure_rate`, `remote_success_rate`).
		- Recommendations are produced automatically when thresholds indicate risk or improvement opportunities.
		- Updated `tests/test_phase4_benchmark_compare.py`:
			- markdown section assertions for findings/recommendations,
			- rule-engine output assertions.
	- **Code Review**
		- Static diagnostics on changed files: no errors.
	- **Test**
		- `venv/Scripts/python.exe -m pytest tests/test_phase4_benchmark_compare.py tests/test_phase4_benchmark.py tests/test_reading_concierge.py` → **14 passed**.
		- `venv/Scripts/python.exe scripts/phase4_benchmark_compare.py --pretty` executed successfully and regenerated markdown artifact.
	- **Feedback**
		- `scripts/phase4_benchmark_report.md` now includes concise, auto-generated findings and actionable recommendations.
	- **Update**
		- Benchmark markdown output is now not only descriptive but also interpretive, improving direct usability for review and demo narration.
	- **Matching Requirements (PLAN.md Phase IV)**
		1. 单体测试：**progressed** (rule-engine and markdown section coverage added).
		2. 集成测试：**retained** (orchestration path unchanged; regression tests still pass).
		3. 系统评估：**strengthened** (automatic interpretation layer added to evaluation deliverables).
		4. 消融研究：**retained** (no ablation logic changes).
		5. 对标测试：**retained + easier interpretation** (report now surfaces key comparative risk signals directly).
		6. 演示系统：**strengthened** (markdown includes ready-to-present findings and recommendations).

	## 2026-02-19 (Phase IV demo setup: MVP frontend page)
	- **Plan**
		- Started demo-system setup to satisfy PLAN.md “搭建演示系统” objective with a directly usable local interactive frontend.
	- **Code**
		- Added frontend page `web_demo/index.html`:
			- interactive form for `/user_api` inputs (query/scenario/top_k/strict mode/JSON fields),
			- recommendation table + evaluation + partner task snapshots,
			- raw response panel for debugging,
			- benchmark summary loader for performance snapshot checks.
		- Updated `reading_concierge/reading_concierge.py` with demo routes:
			- `GET /` and `GET /demo` to serve frontend page,
			- `GET /demo/benchmark-summary` to expose compact benchmark summary,
			- `GET /demo/status` for runtime availability/status checks.
		- Updated `tests/test_reading_concierge.py` with route-level checks for new demo endpoints.
	- **Code Review**
		- Static diagnostics on changed files: no errors.
	- **Test**
		- `venv/Scripts/python.exe -m pytest tests/test_reading_concierge.py tests/test_phase4_benchmark_compare.py tests/test_phase4_benchmark.py` → **17 passed**.
	- **Feedback**
		- Local prototype is now directly viewable in browser via service root/demo route and supports interactive end-to-end validation.
	- **Update**
		- Current system now has a presentable MVP demo interface to inspect completed modules before planning the next work package.
	- **Matching Requirements (PLAN.md Phase IV)**
		1. 单体测试：**progressed** (new demo endpoint behavior covered).
		2. 集成测试：**progressed** (interactive UI now drives full coordinator flow locally).
		3. 系统评估：**retained** (benchmark summary is directly viewable from demo page).
		4. 消融研究：**retained** (no regression to ablation path).
		5. 对标测试：**retained** (existing benchmark compare outputs unchanged and consumable).
		6. 演示系统：**implemented MVP prototype** (interactive local frontend + service endpoints + report linkage).
