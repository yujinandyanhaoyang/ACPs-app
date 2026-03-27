# Demo System Launch Guide

This guide describes launch and verification for the reading recommender demo after P3/P4/P5 hardening.

## Status Scope

- `DONE (local)`: all commands in this runbook are for local verification.
- `PARTIAL_LOCAL_PLACEHOLDER`: local ACS/AIC/cert metadata may use placeholders.
- `BLOCKED_BY_IOA_PUB`: official registry identity/certificate validation is outside this local runbook.

## 1) Prerequisites

- Python environment available (for example `.venv`)
- Dependencies installed from `requirements.txt`
- Working directory at repository root

## 2) Apply DB migrations

```bash
python scripts/migrate_db.py
```

Optional historical backfill:

```bash
python scripts/backfill_user_events.py --legacy-db data/user_profile_store.db
python scripts/backfill_book_features.py --books-jsonl data/processed/merged/books_master_merged.jsonl --limit 2000
```

## 3) Start service (HTTP)

```bash
export AGENT_MTLS_ENABLED=false
python -m reading_concierge.reading_concierge
```

## 4) Verify runtime status

```bash
python - <<'PY'
import requests
r = requests.get('http://127.0.0.1:8100/demo/status', timeout=10)
print(r.status_code)
print(r.json())
PY
```

Expected status fields include:

- `service`
- `leader_id`
- `partner_mode`
- `adp_mode`
- `adp_discovery_enabled`

## 5) Run demo request (production path)

```bash
python scripts/demo_reading_workflow.py --base-url http://127.0.0.1:8100 --check-db --pretty
```

This sends `user_id + query` to `/user_api` and prints DB evidence counters.

## 6) Run demo request (debug payload path)

```bash
python scripts/demo_reading_workflow.py --base-url http://127.0.0.1:8100 --debug --check-db --pretty
```

This calls `/user_api_debug` and injects explicit profile/history/books payloads for nonproduction diagnostics.

## 7) mTLS launch (optional)

```bash
bash scripts/gen_dev_certs.sh
export AGENT_MTLS_ENABLED=true
export AGENT_MTLS_CERT_DIR="$PWD/certs"
python -m reading_concierge.reading_concierge
```

## 8) Targeted verification tests

```bash
python -m pytest tests/test_aip_conformance.py tests/test_acs_conformance.py tests/test_persistence_db.py tests/test_reading_workflow_e2e.py -q
```

## 9) Audit and replay evidence from DB

```bash
curl "http://127.0.0.1:8100/demo/audit/runs?user_id=demo_user_001&limit=5"
curl "http://127.0.0.1:8100/demo/audit/runs/<run_id>"
```

## 10) Retention pruning (optional)

```bash
python scripts/prune_runtime_data.py --keep-runs-per-user 100 --keep-logs-per-task 200
```

## 11) Phase 3 Officialization Commands (post-AIC)

When running against official ACPs infrastructure per `ACPsProtocolGuide.md`:

```bash
source .venv/bin/activate
# Install official ca-client package first
pip install acps_ca_client-2.0.0-py3-none-any.whl

# Issue ATR certificates for all 4 AICs
export CHALLENGE_SERVER_BASE_URL=http://<your-ip>:8004/acps-atr-v2
bash scripts/phase3_issue_real_certs.sh

# Trigger DSP sync and verify ADP search
export DISCOVERY_BASE_URL=http://<discovery-host>:8005
bash scripts/phase3_dsp_sync_verify.sh
```
