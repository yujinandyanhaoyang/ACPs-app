#!/bin/bash
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate

export UAT_BASE_URL="${UAT_BASE_URL:-http://8.146.235.243:8210}"

python - <<'PY'
import os
import sys

import httpx

base_url = str(os.getenv("UAT_BASE_URL") or "http://8.146.235.243:8210").rstrip("/")
try:
    response = httpx.get(f"{base_url}/demo/status", timeout=10.0, trust_env=False)
    if response.status_code != 200:
        raise RuntimeError(f"unexpected HTTP {response.status_code}")
except Exception:
    print("ABORT: Production server at 8.146.235.243:8210 is not reachable.")
    raise SystemExit(1)
PY

python -m pytest tests/test_uat_production.py -v --tb=short
