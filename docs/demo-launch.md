# Demo System Launch Guide

This guide describes launch and verification for the reading recommender demo after P3/P4/P5 hardening.

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
