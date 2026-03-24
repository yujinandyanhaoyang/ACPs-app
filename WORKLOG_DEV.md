# Weekly Development Report

## Project Snapshot

- Goal: build an ACPs-based personalized reading recommendation system with query-faithful retrieval, explainable ranking, and stable end-to-end orchestration.
- Current state as of 2026-03-07: the system runs on a merged multi-source corpus built from Goodreads, Amazon Kindle Store, and Amazon Books. Retrieval defaults now prefer the merged corpus, collaborative filtering and knowledge-graph artifacts have been rebuilt from merged data, and runtime startup logs report the active retrieval corpus.
- Current operational decision: data volume is sufficient for the current stage. Open Library enrichment is optional and deferred.

## Week 1: 2026-02-08 to 2026-02-16

- Established the new project workspace and copied shared ACPs runtime assets.
- Implemented the three core agents:
  - `reader_profile_agent`
  - `book_content_agent`
  - `rec_ranking_agent`
- Implemented `reading_concierge` as the leader/coordinator service.
- Added shared service modules for embeddings, scoring, benchmarks, and evaluation.
- Added demo routes and the initial frontend page.
- Result: infrastructure-complete MVP, but recommendation semantics were still incomplete and several behaviors were still stubbed.

## Week 2: 2026-02-17 to 2026-02-23

- Consolidated defect findings into `PassedWorkBug.md` and created the execution plan in `DEBUG_PLAN.md`.
- Audited the codebase against `PLAN.md` and confirmed the main gaps:
  - hardcoded retrieval behavior
  - query propagation missing in profile/content flow
  - weak embedding path defaults
  - explanation context gaps
  - unbounded session memory
- Completed Phase 1 stabilization:
  - `.gitignore` and `.env.example`
  - LRU session eviction
  - async OpenAI client validation
- Validation:
  - `pytest tests/test_reading_concierge.py` passed at checkpoint.

## Week 3: 2026-02-24 to 2026-03-01

- Completed and verified the remaining `DEBUG_PLAN` phases.
- Delivered the real recommendation path:
  - dataset-backed retrieval
  - query propagation through profile/content/ranking
  - embedding alignment
  - Unicode tokenization
  - richer explanation context
  - baseline retrieval updates
- Audited `PLAN.md`, retired completed planning files, and cleaned stale generated artifacts.
- Verification during this period included focused conformance, benchmark, and ablation checks.
- Result: end-to-end recommendation flow became operational and stable enough for broader data expansion.

## Week 4: 2026-03-01 to 2026-03-07

### Data expansion

- Confirmed Goodreads as the base processed corpus.
- Added Amazon Kindle Store as the first supplemental dataset for practical-scale expansion.
- Added Amazon Books as the second supplemental dataset.
- Normalized new raw files into:
  - `data/processed/amazon_kindle/`
  - `data/processed/amazon_books/`
- Rebuilt merged corpora:
  - `data/processed/merged/books_master_merged.jsonl`
  - `data/processed/merged/interactions_merged.jsonl`

### Merged corpus size

- Merged books: `991,409`
- Merged interactions: `3,994,868`
- Source coverage in merged books:
  - Goodreads: `10,000`
  - Kindle: `485,013`
  - Amazon Books: `496,593`

### Data tooling

- Added `scripts/preprocess_amazon_books.py`.
- Added `scripts/merge_book_corpora.py`.
- Added `scripts/enrich_books_openlibrary.py`.
- Added `docs/data-acquisition.md`.
- Moved raw third-party dataset resolution behind `RAW_DATA_ROOT` so raw files can live outside the repo.

### Reliability fixes

- Fixed large interaction merge failure caused by in-memory accumulation and dedupe state.
- Updated `scripts/merge_book_corpora.py` to use streaming interaction writes for real large merges.
- Enforced merged-corpus retrieval preference in `services/book_retrieval.py`.

### Runtime and defaults

- Retrieval now prefers these corpora in order:
  1. `data/processed/merged/books_master_merged_enriched.jsonl`
  2. `data/processed/merged/books_master_merged.jsonl`
  3. `data/processed/goodreads/books_master.jsonl`
  4. `data/processed/books_min.jsonl`
- `reading_concierge` startup now logs which retrieval corpus is active.
- Downstream builders now target merged data by default:
  - CF from merged interactions
  - KG from merged books

### Downstream rebuilds

- Rebuilt collaborative filtering artifacts from merged interactions:
  - users: `937,764`
  - books: `119,345`
  - interactions: `3,994,868`
  - components: `50`
- Rebuilt knowledge-graph artifacts from merged books:
  - books: `991,409`
  - authors: `488,002`
  - genres: `792`
  - edges: `1,020,740`

### Evaluation defaults

- Reduced empirical ablation default from `100` requested users to `10` for development iteration.
- Reason: `100` users implied roughly `500` sequential recommendation runs across five ablation scenarios and made iteration too slow.
- Larger runs remain possible through CLI override.

### Validation

- Dataset and merge validation:
  - `pytest -q tests/test_preprocess_amazon_books.py tests/test_merge_and_enrich_books.py tests/test_real_dataset_smoke.py`
- Retrieval and merged-data validation:
  - `pytest -q tests/test_book_retrieval.py` → `6 passed`
  - `pytest -q tests/test_book_retrieval.py tests/test_real_dataset_smoke.py tests/test_phase4_optimizer.py tests/test_phase4_benchmark.py` → `16 passed`
- Downstream artifact validation:
  - `pytest -q tests/test_cf_model.py tests/test_kg_client.py` → `36 passed`
- Merge validation after streaming fix:
  - `pytest -q tests/test_merge_and_enrich_books.py tests/test_real_dataset_smoke.py` → `8 passed`

### Repository publishing

- To publish `feature/recommendation-optimization` without oversized payloads, rewrote local branch history to exclude `data/` artifacts from committed content.
- Added `data/` to `.gitignore` to prevent future accidental commits of raw/processed datasets.
- Re-committed code/docs/config-only changes as `92567ef` (`feat: keep recommendation optimization code without data artifacts`).
- Successfully pushed branch to GitHub:
  - `origin/feature/recommendation-optimization`
- Safety step preserved before rewrite:
  - `backup/feature-recommendation-optimization-before-rewrite`

## Current Status Summary

- Core system status: stable on merged multi-source data.
- Retrieval status: defaults point to merged corpus automatically.
- Data status: sufficient for the current project stage.
- Reporting status: empirical ablation and benchmark paths exist, but development defaults now favor faster runs.
- Deferred work: Open Library enrichment and deeper semantic/KG-RAG improvements remain optional future tasks.
## Week 5: 2026-03-24 (P3/P4/P5 execution advance)

### P3 compliance and trust hardening progress

- Added formal partner ACS descriptors:
  - `agents/reader_profile_agent/acs.json`
  - `agents/book_content_agent/acs.json`
  - `agents/rec_ranking_agent/acs.json`
- Added startup fail-fast validation for ACS/runtime/cert consistency via `acps_aip/mtls_config.py::validate_startup_identity`.
- Wired startup trust checks into all service `__main__` entrypoints.
- Declared ADP runtime operating mode (`Mode B`) and exposed diagnostics in `/demo/status` (`adp_mode`, `adp_discovery_enabled`).

### P4 persistence foundation progress

- Added migration-capable DB module: `services/db.py`.
- Added initial schema migration: `migrations/001_initial_schema.sql`.
- Added repository layer:
  - `services/repositories/profile_repository.py`
  - `services/repositories/recommendation_repository.py`
  - `services/repositories/task_log_repository.py`
- Added migration/backfill scripts:
  - `scripts/migrate_db.py`
  - `scripts/backfill_user_events.py`
  - `scripts/backfill_book_features.py`
- Added persistence integration bridge in `services/user_profile_store.py` so runtime writes mirror to the new schema.

### P5 verification and demo readiness progress

- Added workflow-level persistence verification test: `tests/test_reading_workflow_e2e.py`.
- Added persistence unit/integration checks: `tests/test_persistence_db.py`.
- Refreshed demo script: `scripts/demo_reading_workflow.py` with production/debug modes and DB evidence output.
- Updated launch and design docs:
  - `docs/demo-launch.md`
  - `docs/data-spec.md`
  - `docs/persistence-design.md`

### Validation evidence

- `pytest tests/test_aip_conformance.py tests/test_acs_conformance.py -q` -> passed
- `pytest tests/test_persistence_db.py tests/test_reading_workflow_e2e.py -q` -> passed
