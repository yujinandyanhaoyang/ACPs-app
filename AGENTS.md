# Repository Guidelines

## Project Structure & Module Organization
This repository implements a multi-agent book recommendation system built on ACPs/AIP.
- `reading_concierge/`: Leader service, orchestration API, session handling.
- `partners/online/`: partner agents such as `reader_profile_agent/`, `book_content_agent/`, `recommendation_decision_agent/`, `recommendation_engine_agent/`, and `feedback_agent/`.
- `acps_aip/`: protocol models and RPC utilities.
- `services/`: shared business logic, repositories, metrics, retrieval, and model backends.
- `scripts/`: dataset prep, indexing, benchmarking, ablation, and operational helpers.
- `tests/`: unit, contract, and E2E tests (`test_*.py`).
- `docs/`, `data/`, `migrations/`, `certs/`: documentation, datasets, SQL schema, and TLS artifacts.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create and activate a local environment.
- `pip install -r requirements.txt`: install runtime and test dependencies.
- `python -m pytest -q`: run the full test suite.
- `python -m pytest tests/test_reading_concierge.py -q`: run a focused module.
- `python -m reading_concierge.reading_concierge`: start the Leader service locally.
- `python scripts/migrate_db.py`: apply SQLite migrations in `migrations/`.
- `python scripts/demo_reading_workflow.py --pretty`: run a local workflow smoke test.

## Coding Style & Naming Conventions
Use Python 4-space indentation, `snake_case` for functions/variables, `PascalCase` for classes, and `UPPER_CASE` for constants. Keep modules focused and place reusable logic in `services/` rather than duplicating it across agents. Preserve existing type hints and dataclass/pydantic patterns. Name new tests and scripts descriptively, for example `test_book_content_agent.py` or `build_index_parallel.py`.

## Testing Guidelines
`pytest` is the standard framework. Prefer deterministic offline tests and reuse fixtures from `tests/conftest.py`. Add or update tests when changing protocol schemas, persistence, agent RPC state transitions, or ranking logic. Run a targeted test first, then broader coverage before merging.

## Commit & Pull Request Guidelines
Keep commits task-scoped and concise; the history uses short Chinese summaries and occasional prefixes like `feat:`. PRs should include the goal, affected modules, commands run, and any schema/data impact. Attach screenshots or request/response examples when behavior changes.

## Security & Configuration Tips
Do not commit secrets. Use `.env` for local configuration, and keep mTLS settings in each agent’s `config.toml`. Client certificates live under each agent’s `certs/` directory. For local development, set `AGENT_MTLS_ENABLED=false` when appropriate.
