#!/usr/bin/env bash
set -euo pipefail

# Phase 3 DSP synchronization and ADP discovery verification helper.

DISCOVERY_BASE_URL="${DISCOVERY_BASE_URL:-http://127.0.0.1:8005}"
QUERY="${QUERY:-personalized reading recommendation agent}"
TOP_K="${TOP_K:-5}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$PROJECT_ROOT/artifacts/phase3"
mkdir -p "$ARTIFACT_DIR"

TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
SYNC_OUT="$ARTIFACT_DIR/dsp-sync-$TIMESTAMP.json"
SEARCH_OUT="$ARTIFACT_DIR/adp-search-$TIMESTAMP.json"
SUMMARY_OUT="$ARTIFACT_DIR/dsp-adp-summary-$TIMESTAMP.json"

echo "[phase3] trigger DSP sync: $DISCOVERY_BASE_URL/admin/drc/sync"
curl -fsS -X POST "$DISCOVERY_BASE_URL/admin/drc/sync" \
  -H "Content-Type: application/json" \
  -o "$SYNC_OUT"

echo "[phase3] verify ADP search: $DISCOVERY_BASE_URL/api/discovery/search"
curl -fsS -X POST "$DISCOVERY_BASE_URL/api/discovery/search" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"$QUERY\",\"top_k\":$TOP_K}" \
  -o "$SEARCH_OUT"

python3 - <<PY
import json
from pathlib import Path

sync_path = Path("$SYNC_OUT")
search_path = Path("$SEARCH_OUT")
summary_path = Path("$SUMMARY_OUT")

def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_parse_error": str(e), "_raw_path": str(path)}

sync_data = load(sync_path)
search_data = load(search_path)

result_count = 0
if isinstance(search_data, dict):
    if isinstance(search_data.get("results"), list):
        result_count = len(search_data["results"])
    elif isinstance(search_data.get("data"), list):
        result_count = len(search_data["data"])

summary = {
    "status": "DONE (local)",
    "dsp_sync_output": str(sync_path),
    "adp_search_output": str(search_path),
    "discovery_result_count": result_count,
}
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

echo "[phase3] evidence written to: $SUMMARY_OUT"
