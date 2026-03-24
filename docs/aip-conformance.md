# AIP Conformance Notes

This document records AIP lifecycle conformance coverage for the reading recommender multi-agent runtime.

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
- `Complete`
- `Cancel`

Reference test: `tests/test_aip_conformance.py`

## State Coverage

Validated terminal-state behavior:

- `Completed`
- `Failed`
- `Canceled`
- `Rejected`

Behavior expectations:

- `Start` creates a task when not existing and is idempotent on existing task.
- `Get` returns current snapshot for existing task and returns not-found error for unknown task.
- `Complete` transitions only when current state is `AwaitingCompletion`.
- `Cancel` is idempotent and must not overwrite terminal states.

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

1. Add integration-level AIP conformance checks that run through all partner services in mTLS-only mode.
2. Attach production evidence snapshots after official ioa.pub identity and certificate rollout.


## ADP Runtime Mode

- Current declaration: `Mode B`
- Meaning: ADP compatibility/readiness is preserved while runtime endpoint resolution uses approved static partner bindings.
- Runtime visibility: `GET /demo/status` includes `adp_mode` and `adp_discovery_enabled`.
