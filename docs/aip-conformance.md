# AIP Conformance Notes

This document records AIP lifecycle conformance coverage for the reading recommender multi-agent runtime.

## Status

- `DONE (local)`: local command/state conformance baseline and regression tests.
- `READY_FOR_IOA_PUB`: evidence bundle structure (test file, run commands, expected assertions) is ready for official replay.
- `BLOCKED_BY_IOA_PUB`: official identity-bound evidence (real AIC + official ATR/AIA chain + registry runtime path).

## Scope

- Runtime implementation: `acps_aip/aip_rpc_server.py`
- Agent RPC endpoints:
  - `/reader-profile/rpc`
  - `/book-content/rpc`
  - `/rec-ranking/rpc`
  - `/user_api` (leader)

## Command Coverage

Validated commands:

- `Start`
- `Get`
- `Continue`
- `Complete`
- `Cancel`

Reference test: `tests/test_aip_conformance.py`

## State Coverage

Validated states in tests:

- `Accepted`
- `Working`
- `AwaitingInput`
- `AwaitingCompletion`
- `Completed`
- `Failed`
- `Canceled`
- `Rejected`

Behavior expectations:

- `Start` creates a task when not existing and is idempotent on existing task.
- `Get` returns current snapshot for existing task and returns not-found error for unknown task.
- `Continue` appends lineage message and remains no-op by default unless agent business logic advances state.
- `Complete` transitions only when current state is `AwaitingCompletion`.
- `Cancel` is idempotent and must not overwrite terminal states.
- Handler exceptions transition task state to `Failed` with explicit diagnostic data item.

## Identity and Lineage Fields

The conformance checks verify presence and consistency of:

- `taskId`
- `sessionId`
- `senderId`

These fields are validated in request/response lifecycle tests and are expected to be preserved in runtime logs and persisted traces.

## How To Run

```bash
.venv/bin/python -m pytest tests/test_aip_conformance.py -q
```

## Outstanding Items

1. `DONE (local)`: unit-level command/state coverage in `tests/test_aip_conformance.py`.
2. `READY_FOR_IOA_PUB`: replay the same lifecycle checks against ioa.pub-issued identities and official endpoints.
3. `BLOCKED_BY_IOA_PUB`: attach production-grade evidence snapshots after official identity/certificate rollout.


## ADP Runtime Mode

- Current declaration: `Mode B`
- Meaning: ADP compatibility/readiness is preserved while runtime endpoint resolution uses approved static partner bindings.
- Runtime visibility: `GET /demo/status` includes `adp_mode` and `adp_discovery_enabled`.
