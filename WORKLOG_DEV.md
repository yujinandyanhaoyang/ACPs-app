# Development Worklog (Monthly Compressed)

## Active Upgrade Guidance (Effective 2026-03-31)

The system upgrade plan is now guided by the following documents:
- `PROJECT_CONTEXT.md`
- `UPGRADE_PLAN.md`
- `ACPsProtocolGuide.md`

Legacy planning/design documents have been retired from active use.

## 2026-02 (Foundation + Core Path Stabilization)

### Scope
- Built ACPs-based personalized reading recommendation system skeleton and core runtime topology.
- Established leader-partner orchestration pattern and shared service layer.

### Major Deliveries
- Implemented core agents:
  - `agents/reader_profile_agent/`
  - `agents/book_content_agent/`
  - `agents/rec_ranking_agent/`
- Implemented leader service:
  - `reading_concierge/`
- Added shared business modules in `services/` for retrieval, scoring, evaluation, and model-path integration.
- Completed core recommendation-path hardening:
  - dataset-backed retrieval
  - query propagation across profile/content/ranking flow
  - embedding-path alignment
  - Unicode tokenization support
  - richer recommendation explanation context
  - bounded session memory (LRU eviction)

### Validation
- Focused orchestration checkpoint test passed:
  - `pytest tests/test_reading_concierge.py`

### Outcome
- MVP evolved from infra-complete to operational end-to-end recommendation flow with stable baseline behavior.

## 2026-03 (Data Scale-Up + P3/P4/P5 Execution Advance)

### Scope
- Expanded dataset scale and made merged corpus the runtime default.
- Advanced ACPs protocol compliance/trust hardening (P3), persistence architecture (P4), and verification/demo readiness (P5).

### Data Expansion and Retrieval Defaults
- Added and normalized supplemental datasets:
  - Amazon Kindle Store
  - Amazon Books
- Produced merged corpora:
  - `data/processed/merged/books_master_merged.jsonl`
  - `data/processed/merged/interactions_merged.jsonl`
- Merged corpus scale:
  - books: `991,409`
  - interactions: `3,994,868`
- Source coverage in merged books:
  - Goodreads: `10,000`
  - Kindle: `485,013`
  - Amazon Books: `496,593`
- Retrieval fallback priority standardized to merged-first strategy.
- Startup logs now report active retrieval corpus.
- CF/KG builders switched to merged data defaults.

### Tooling and Reliability
- Added data tooling:
  - `scripts/preprocess_amazon_books.py`
  - `scripts/merge_book_corpora.py`
  - `scripts/enrich_books_openlibrary.py`
- Added/updated data docs:
  - `docs/data-acquisition.md`
- Fixed large interaction merge memory pressure by switching to streaming write path.
- Reduced default empirical ablation run size from 100 users to 10 users for faster iteration.

### P3 (Protocol Compliance and Trust Hardening)
- Added formal ACS descriptors and partner material standardization.
- Added startup fail-fast identity checks:
  - `acps_aip/mtls_config.py::validate_startup_identity`
- Wired trust checks into service startup entrypoints.
- Added ADP mode diagnostics surfaced in `/demo/status`.
- Replaced placeholder AICs with ioa.pub-issued real AIC values in descriptors.
- Added execution scripts:
  - `scripts/phase3_issue_real_certs.sh`
  - `scripts/phase3_dsp_sync_verify.sh`
- Current external dependency status:
  - local preflight: completed
  - official ATR/AIA issuance + DSP/ADP online evidence: blocked by upstream service availability window

### P4 (Persistence Foundation)
- Added migration-capable DB module:
  - `services/db.py`
- Added initial schema migration:
  - `migrations/001_initial_schema.sql`
- Added repositories:
  - `services/repositories/profile_repository.py`
  - `services/repositories/recommendation_repository.py`
  - `services/repositories/task_log_repository.py`
- Added migration/backfill scripts:
  - `scripts/migrate_db.py`
  - `scripts/backfill_user_events.py`
  - `scripts/backfill_book_features.py`
- Integrated runtime write-through persistence bridge in:
  - `services/user_profile_store.py`

### P5 (Verification and Demo Readiness)
- Added persistence and workflow tests:
  - `tests/test_persistence_db.py`
  - `tests/test_reading_workflow_e2e.py`
- Refreshed demo runner and evidence flow:
  - `scripts/demo_reading_workflow.py`
- Updated design/launch docs:
  - `docs/demo-launch.md`
  - `docs/data-spec.md`
  - `docs/persistence-design.md`

### Validation Evidence (March)
- `pytest tests/test_aip_conformance.py tests/test_acs_conformance.py -q` -> passed
- `pytest tests/test_persistence_db.py tests/test_reading_workflow_e2e.py -q` -> passed
- `pytest -q tests/test_preprocess_amazon_books.py tests/test_merge_and_enrich_books.py tests/test_real_dataset_smoke.py` -> passed
- `pytest -q tests/test_book_retrieval.py` -> `6 passed`
- `pytest -q tests/test_book_retrieval.py tests/test_real_dataset_smoke.py tests/test_phase4_optimizer.py tests/test_phase4_benchmark.py` -> `16 passed`
- `pytest -q tests/test_cf_model.py tests/test_kg_client.py` -> `36 passed`
- `pytest -q tests/test_merge_and_enrich_books.py tests/test_real_dataset_smoke.py` -> `8 passed`

### Outcome
- System operates stably on merged multi-source corpus with improved retrieval defaults, persistence foundation, and stronger ACPs trust/compliance posture.
- Remaining externally blocked protocol evidence tasks are ready to execute immediately after official service recovery.
