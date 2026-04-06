#!/usr/bin/env bash
set -euo pipefail

# Phase 3 DSP synchronization and ADP discovery verification helper.
# 6.3 goal: verify DSP registration and ADP discoverability.
# Note: in official public DSP, same-type agents from other teams may be returned.
# Final runtime should combine DSP availability checks with local AIC-pinned routing.

DISCOVERY_BASE_URL="${DISCOVERY_BASE_URL:-http://127.0.0.1:8005}"
QUERY="${QUERY:-personalized reading recommendation agent}"
TOP_K="${TOP_K:-20}"
EXPECTED_AGENTS="${EXPECTED_AGENTS:-6}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$PROJECT_ROOT/artifacts/phase3"
mkdir -p "$ARTIFACT_DIR"

TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
SYNC_OUT="$ARTIFACT_DIR/dsp-sync-$TIMESTAMP.json"
SEARCH_OUT="$ARTIFACT_DIR/adp-search-$TIMESTAMP.json"
SUMMARY_OUT="$ARTIFACT_DIR/dsp-adp-summary-$TIMESTAMP.json"

echo "[phase3] trigger DSP sync: $DISCOVERY_BASE_URL/admin/drc/sync"
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  curl --noproxy '*' -fsS -X POST "$DISCOVERY_BASE_URL/admin/drc/sync" \
    -H "Content-Type: application/json" \
    -o "$SYNC_OUT"

echo "[phase3] verify ADP search: $DISCOVERY_BASE_URL/api/discovery/search"
SEARCH_PATHS=(
  "/api/discovery/search"
  "/acps-adp-v2/discover"
  "/acps-adp-v2/discover/v1"
)
SEARCH_OK=0
SEARCH_USED_PATH=""
for path in "${SEARCH_PATHS[@]}"; do
  if env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
      curl --noproxy '*' -fsS -X POST "$DISCOVERY_BASE_URL$path" \
        -H "Content-Type: application/json" \
        -d "{\"query\":\"$QUERY\",\"top_k\":$TOP_K}" \
        -o "$SEARCH_OUT"; then
    SEARCH_OK=1
    SEARCH_USED_PATH="$path"
    break
  fi
done
if [ "$SEARCH_OK" -ne 1 ]; then
  echo "[phase3] ADP search failed on all known paths." >&2
  exit 22
fi
echo "[phase3] ADP search path used: $SEARCH_USED_PATH"

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

def get_results(payload):
    if isinstance(payload, dict):
        if isinstance(payload.get("results"), list):
            return payload["results"]
        if isinstance(payload.get("data"), list):
            return payload["data"]
        result = payload.get("result")
        if isinstance(result, dict):
            if isinstance(result.get("results"), list):
                return result["results"]
            acs_map = result.get("acsMap")
            if isinstance(acs_map, dict):
                return list(acs_map.values())
    return []

def skill_ids(item):
    if not isinstance(item, dict):
        return []
    skills = item.get("skills")
    if not isinstance(skills, list):
        card = item.get("agent_card")
        if isinstance(card, dict):
            skills = card.get("skills")
    ids = []
    if isinstance(skills, list):
        for sk in skills:
            if isinstance(sk, dict) and sk.get("id"):
                ids.append(str(sk["id"]))
            elif isinstance(sk, str):
                ids.append(sk)
    return ids

results = get_results(search_data)
result_count = len(results)

expected_skill_ids = {
    "reading.orchestrate",
    "uma.build_profile",
    "bca.build_content_proposal",
    "rda.arbitrate",
    "engine.dispatch",
    "fa.process_event",
}
found_skill_ids = set()
for item in results:
    found_skill_ids.update(skill_ids(item))

missing_skill_ids = sorted(expected_skill_ids - found_skill_ids)
status = "PASS" if (result_count >= int("$EXPECTED_AGENTS") and not missing_skill_ids) else "PARTIAL"

summary = {
    "status": status,
    "dsp_sync_output": str(sync_path),
    "adp_search_output": str(search_path),
    "adp_search_path_used": "$SEARCH_USED_PATH",
    "discovery_result_count": result_count,
    "expected_agents": int("$EXPECTED_AGENTS"),
    "missing_skill_ids": missing_skill_ids,
    "found_skill_ids": sorted(found_skill_ids),
}
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

echo "[phase3] evidence written to: $SUMMARY_OUT"
