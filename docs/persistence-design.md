# Persistence Design (Phase P4)

## Scope

This document describes the local persistent database foundation for the reading recommendation runtime.

## Runtime Backend

- Default backend: SQLite
- Connection URL source: `RECSYS_DB_URL` (fallback: `DATABASE_URL`, then local default)
- Current local default: `sqlite:///data/recommendation_runtime.db`
- Migration runner: `services/db.py::run_migrations`

## Schema Modules

The migration `migrations/001_initial_schema.sql` defines:

1. `users`
2. `user_events`
3. `user_profiles`
4. `books`
5. `book_features`
6. `recommendation_runs`
7. `recommendations`
8. `agent_task_logs`
9. `schema_migrations`

## Repository Layer

Implemented repository classes:

- `services/repositories/profile_repository.py`
- `services/repositories/recommendation_repository.py`
- `services/repositories/task_log_repository.py`

These repositories isolate SQL writes for user lifecycle state, recommendation artifacts, and ACPs task-trace logs.

## Runtime Integration

- Legacy compatibility remains in `services/user_profile_store.py`.
- New behavior now mirrors lifecycle writes into repository-backed persistence:
  - user events
  - profile snapshots
  - recommendation runs
  - recommendation items
  - agent task log entries

## Migration/Backfill Tooling

- Apply migrations:
  - `python scripts/migrate_db.py`
- Backfill historical user lifecycle artifacts:
  - `python scripts/backfill_user_events.py --legacy-db data/user_profile_store.db`
- Backfill books and features:
  - `python scripts/backfill_book_features.py --books-jsonl data/processed/merged/books_master_merged.jsonl --limit 2000`

## Reproducibility Fields

`recommendation_runs` stores:

- `user_id`
- `query`
- `profile_version`
- `candidate_set_version_or_hash`
- `book_feature_version_or_hash`
- `ranking_policy_version`
- `weights_or_policy_snapshot_json`
- `candidate_provenance_json`
- `run_timestamp`

`recommendations` stores per-item evidence:

- `book_id`
- factor-level scores (`score_cf`, `score_content`, `score_kg`, `score_diversity`)
- `score_total`
- `scenario_policy`
- `explanation`
- `explanation_evidence_refs_json`
- `rank_position`

`agent_task_logs` stores ACPs traceability fields:

- `task_id`
- `session_id`
- `sender_id`
- `receiver_id`
- `state_transition`
- `timestamp`

## Next Expansion

- Add PostgreSQL runtime adapter implementation behind the existing DB URL abstraction.
- Add migration down scripts and CI migration up/down verification.
- Add retention and archival job hooks for old runs and task logs.
