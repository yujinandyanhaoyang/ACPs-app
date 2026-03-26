# Local vs ioa.pub Status Matrix

This document separates local completion from official ioa.pub-dependent completion.

## Status Tag Definitions

- `DONE (local)`: implemented and verified in local environment.
- `READY_FOR_IOA_PUB`: artifact/package is prepared and waiting for official submission/verification.
- `BLOCKED_BY_IOA_PUB`: cannot be completed without ioa.pub-issued identity/cert/registry operations.
- `PARTIAL_LOCAL_PLACEHOLDER`: local placeholder exists and is intentionally not official.

## Current Matrix

| Work Item | Status | Evidence |
| --- | --- | --- |
| Leader + 3 Partners frozen architecture | `DONE (local)` | `docs/leader-partner-runtime.md`, `reading_concierge/reading_concierge.py` |
| Production entry `user_id + query` | `DONE (local)` | `/user_api` contract and tests |
| AIP local command/state conformance baseline | `DONE (local)` | `tests/test_aip_conformance.py`, `docs/aip-conformance.md` |
| P4 local persistence schema/repository/migration | `DONE (local)` | `services/db.py`, `migrations/001_initial_schema.sql`, `services/repositories/*` |
| Traceability replay/audit endpoints | `DONE (local)` | `/demo/audit/runs`, `/demo/audit/runs/{run_id}` |
| ACS descriptors with local AIC/cert metadata | `PARTIAL_LOCAL_PLACEHOLDER` | `reading_concierge/reading_concierge.json`, `partners/online/*/acs.json` |
| ACPs-standard partner material layout (`acs.json`, `config.toml`, `prompts.toml`, `certs/agent.crt`, `certs/agent.key`) | `DONE (local)` | `partners/online/reader_profile_agent/*`, `partners/online/book_content_agent/*`, `partners/online/rec_ranking_agent/*` |
| ioa.pub real AIC replacement | `BLOCKED_BY_IOA_PUB` | pending official issuance |
| Official ATR certificate issuance | `BLOCKED_BY_IOA_PUB` | pending official workflow |
| Official registry registration verification | `BLOCKED_BY_IOA_PUB` | pending ioa.pub review |
| Official AIA mTLS verification evidence | `BLOCKED_BY_IOA_PUB` | pending official cert and environment |
| Official ADP/DSP production evidence | `BLOCKED_BY_IOA_PUB` | pending official endpoint/process |
| ACS + registration submission package | `READY_FOR_IOA_PUB` | `scripts/register_agents_ioa_pub.md`, `docs/acps-registration-evidence.md` |
