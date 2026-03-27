# Defect-to-Workstream Traceability

Date: 2026-03-23
Scope: Execution tracking for section 3 in UPDATEPLAN.md.

## Status Legend
- in-progress: active implementation and verification underway
- pending: planned but not yet started in implementation
- partial: foundational implementation exists but full phase exit criteria not met

## Traceability Matrix
| Defect | Workstream | Current Status | Implemented Evidence | Pending to Close |
| --- | --- | --- | --- | --- |
| Frontend hardcoded profile/history | WS-A User Profile Lifecycle | in-progress | `/user_api` requires `user_id + query`; debug override is isolated. Profile snapshots are persisted with version progression. Ingestion adapters now persist raw `user_basic_info`, `rating/browse/history_entry`, and `review` events so Leader can rebuild context from DB logs; dedupe/normalization hardening is implemented and test-covered. Files: `reading_concierge/reading_concierge.py`, `web_demo/index.html`, `services/user_profile_store.py`, `docs/profile-lifecycle.md`, `tests/test_reading_concierge.py` | Complete lifecycle refresh policy and expanded replay coverage |
| Book content + ranking redesign alignment | WS-B Content and Ranking Optimization | in-progress | Contract artifacts and fail-closed validation are implemented in Leader runtime (`contract_artifacts`, `contract_validation`). Partner B now includes strict candidate intake normalization/dedupe, source labeling, and feature metadata versioning in outputs. Files: `reading_concierge/reading_concierge.py`, `agents/book_content_agent/book_content_agent.py`, `tests/test_contract_schemas.py`, `tests/test_book_content_agent.py` | Complete Partner C ranking redesign acceptance gates (deterministic explanation completeness and benchmark thresholds in P2) |
| ACPs official registration and protocol adoption | WS-C ACPs Compliance and Trust | in-progress | Real AICs integrated in ACS descriptors; ADP mode diagnostics and remote fallback hooks exist. Added execution scripts for official ATR/AIA and DSP workflows: `scripts/phase3_issue_real_certs.sh`, `scripts/phase3_dsp_sync_verify.sh`. | Execute real CA-client issuance, capture AIA handshake evidence, run DSP sync against official discovery, archive production artifacts |
| Temporary storage model | WS-D Persistence Foundation | in-progress | Migration-backed runtime DB + repository layer are active (`services/db.py`, `services/repositories/*`). Recovery/restart and retention hooks are test-covered (`tests/test_persistence_db.py`), and audit replay endpoints are available (`/demo/audit/runs`, `/demo/audit/runs/{run_id}`). Backfill scripts are validated by automated tests (`tests/test_backfill_scripts.py`). | Add migration down-path verification and PostgreSQL adapter wiring |
| Need standardized update plan | WS-E Governance and Verification | in-progress | Plan and gates are actively maintained with evidence updates. Files: `UPDATEPLAN.md`, `docs/acps-gap-matrix.md`, `docs/leader-partner-runtime.md` | Complete owner approvals and checklists, then close each phase gate with final artifacts |

## Cross-Workstream Deliverable Check
- `docs/contracts/user_profile.schema.json`: present, versioned, validated
- `docs/contracts/candidate_book_set.schema.json`: present, versioned, validated
- `docs/contracts/book_feature_map.schema.json`: present, versioned, validated
- `docs/contracts/ranked_recommendation_list.schema.json`: present, versioned, validated
- `docs/leader-partner-runtime.md`: present

## Verification Snapshot
- Contract and orchestration checks:
  - `pytest tests/test_contract_schemas.py tests/test_reading_concierge.py`
- DB-log reconstruction check:
  - `tests/test_reading_concierge.py::test_user_id_only_request_rebuilds_profile_from_db_logs`
- Ingestion dedupe check:
  - `tests/test_reading_concierge.py::test_ingestion_dedup_prevents_duplicate_history_and_reviews`
- Book-content normalization check:
  - `tests/test_book_content_agent.py::test_book_content_intake_dedup_and_normalization`
- Full regression baseline after section-2 strict validation changes:
  - `pytest` -> `117 passed, 9 skipped`
- P4 persistence hardening additions:
  - `.venv/bin/python -m pytest -q tests/test_persistence_db.py tests/test_backfill_scripts.py`
  - `6 passed`

## Next Workstream Moves
1. WS-A: complete ingestion adapters and lifecycle refresh policies.
2. WS-B: complete content/ranking redesign acceptance thresholds and benchmark evidence.
3. WS-C: start registration + certificate issuance runbook execution for real identities.
4. WS-D: scaffold migration-capable DB layer and repository abstraction.
5. WS-E: close owner approvals and phase checkboxes with artifact links.
