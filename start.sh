#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"
source .venv/bin/activate
export READING_DISCOVERY_ENABLED=false

# Pre-flight checks
echo "[start] checking data assets..."
ls -lh /root/WORK/DATA/processed/books_index_v2.faiss
ls -lh /root/WORK/DATA/processed/books_index_meta_v2.jsonl
ls -lh /root/WORK/DATA/processed/cf_item_factors_v2.npy

# Kill any stale partner processes on ports 8211-8214
echo "[start] cleaning up stale processes..."
for port in 8211 8212 8213 8214; do
  pid=$(lsof -ti tcp:$port 2>/dev/null || true)
  [ -n "$pid" ] && kill -9 $pid 2>/dev/null \
    && echo "  killed stale pid=$pid on port=$port" || true
done

# Start 4 partner agents in background
echo "[start] launching reader_profile_agent on :8211 ..."
nohup .venv/bin/python -m partners.online.reader_profile_agent.agent \
  > /tmp/acps_rpa.log 2>&1 &

echo "[start] launching book_content_agent on :8212 ..."
nohup .venv/bin/python -m partners.online.book_content_agent.agent \
  > /tmp/acps_bca.log 2>&1 &

echo "[start] launching recommendation_decision_agent on :8213 ..."
nohup .venv/bin/python \
  -m partners.online.recommendation_decision_agent.agent \
  > /tmp/acps_rda.log 2>&1 &

echo "[start] launching recommendation_engine_agent on :8214 ..."
nohup .venv/bin/python \
  -m partners.online.recommendation_engine_agent.agent \
  > /tmp/acps_engine.log 2>&1 &

echo "[start] waiting 18s for partner agents to initialize..."
sleep 18

# Verify all 4 partner ports are listening before starting concierge
echo "[start] checking partner ports..."
all_ok=true
for port in 8211 8212 8213 8214; do
  if lsof -ti tcp:$port > /dev/null 2>&1; then
    echo "  port $port: OK"
  else
    echo "  port $port: NOT LISTENING — check /tmp/acps_*.log"
    all_ok=false
  fi
done
if [ "$all_ok" = false ]; then
  echo "[start] WARNING: one or more partner agents failed to start."
  echo "[start] Proceeding anyway — concierge will use local fallback."
fi

# Start concierge in foreground (blocks; logs to stdout)
echo "[start] launching reading_concierge on 0.0.0.0:8210 ..."
exec .venv/bin/python -m uvicorn \
  reading_concierge.reading_concierge:app \
  --host 0.0.0.0 \
  --port 8210 \
  --workers 1 \
  --timeout-keep-alive 300 \
  --log-level info
