# Repository Guidelines

## Project Structure & Module Organization
Core runtime code is organized by responsibility:
- `reading_concierge/`: leader service entrypoint and orchestration API.
- `agents/reader_profile_agent/`, `agents/book_content_agent/`, `agents/rec_ranking_agent/`: ACP sub-agents with their own `config.toml`, `prompts.toml`, and service modules.
- `services/`: shared business logic (retrieval, ranking, DB, repositories, metrics, model backends).
- `acps_aip/`: AIP/ACPs protocol models and RPC utilities.
- `scripts/`: operational tooling (migration, backfill, preprocessing, benchmarking, ablation).
- `tests/`: unit, contract, and E2E tests (`test_*.py`).
- `docs/`, `migrations/`, `data/`, `certs/`: design docs, SQL schema, local datasets, and dev TLS artifacts.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)
- `pip install -r requirements.txt`: install runtime and test dependencies.
- `python -m pytest -q`: run full test suite.
- `python -m pytest tests/test_reading_concierge.py -q`: run a focused test module.
- `python -m reading_concierge.reading_concierge`: start leader service locally.
- `python scripts/migrate_db.py`: apply SQLite migrations (`migrations/001_initial_schema.sql`).
- `python scripts/demo_reading_workflow.py --pretty`: run a local workflow smoke request.

## Coding Style & Naming Conventions
- Python style: 4-space indentation, `snake_case` for functions/variables, `PascalCase` for classes, UPPER_CASE for constants.
- Preserve existing type-hint usage and datamodel patterns in `acps_aip/` and `services/`.
- Keep modules focused; place shared logic in `services/` instead of duplicating across agents.
- Name tests and scripts descriptively: `test_<behavior>.py`, `<verb>_<object>.py`.

## Testing Guidelines
- Framework: `pytest` with fixtures in `tests/conftest.py`.
- Prefer offline-deterministic tests; existing fixtures patch external model calls.
- Add tests with every behavior change, especially for contract schemas, persistence flows, and agent RPC state transitions.
- Run targeted tests first, then `python -m pytest -q` before opening a PR.

## Commit & Pull Request Guidelines
- Follow concise, task-scoped commit subjects (history shows short Chinese summaries and occasional Conventional Commit prefixes like `feat:`).
- One commit should represent one logical change set; avoid mixing refactor + feature + data churn.
- PRs should include: objective, affected modules, test evidence (commands run), migration/data impact, and API/contract changes.
- Link related issue or plan item (for example from `UPDATEPLAN.md`) and include request/response examples when behavior changes.
