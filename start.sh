#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
WORK_DIR="$(cd "$PROJECT_ROOT/../.." && pwd)"
cd "$PROJECT_ROOT"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif [ -x "$WORK_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$WORK_DIR/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi
export READING_DISCOVERY_ENABLED=false
export BOOK_CONTENT_EMBED_MODEL_PATH="${BOOK_CONTENT_EMBED_MODEL_PATH:-$WORK_DIR/shared_runtime_assets/all-MiniLM-L6-v2}"
export BOOK_RETRIEVAL_DATASET_PATH="${BOOK_RETRIEVAL_DATASET_PATH:-$WORK_DIR/DATA/experiment/common/5core/books_master_merged_5core.jsonl}"
export FAISS_INDEX_PATH="${FAISS_INDEX_PATH:-$WORK_DIR/DATA/experiment/common/5core/books_index_5core.faiss}"
export FAISS_INDEX_META_PATH="${FAISS_INDEX_META_PATH:-$WORK_DIR/DATA/experiment/common/5core/books_index_meta_5core.jsonl}"
export CF_ITEM_FACTORS_PATH="${CF_ITEM_FACTORS_PATH:-$WORK_DIR/DATA/experiment/common/5core/cf_item_factors.npy}"
export CF_USER_FACTORS_PATH="${CF_USER_FACTORS_PATH:-$WORK_DIR/DATA/experiment/common/5core/cf_user_factors.npy}"
export CF_BOOK_INDEX_PATH="${CF_BOOK_INDEX_PATH:-$WORK_DIR/DATA/experiment/common/5core/cf_book_id_index.json}"
export CF_USER_INDEX_PATH="${CF_USER_INDEX_PATH:-$WORK_DIR/DATA/experiment/common/5core/cf_user_id_index.json}"
export ALS_MODEL_PATH="${ALS_MODEL_PATH:-$WORK_DIR/DATA/experiment/common/5core/cf_als_model_5core.npz}"
export HNSWLIB_PATH="${HNSWLIB_PATH:-$WORK_DIR/DATA/experiment/common/5core/cf_user_similarity_5core.bin}"

# Pre-flight checks
echo "[start] checking data assets..."
ls -lh "$BOOK_CONTENT_EMBED_MODEL_PATH"
ls -lh "$BOOK_RETRIEVAL_DATASET_PATH"
ls -lh "$FAISS_INDEX_PATH"
ls -lh "$FAISS_INDEX_META_PATH"
ls -lh "$CF_ITEM_FACTORS_PATH"

# Kill any stale partner processes on ports 8211-8214
echo "[start] cleaning up stale processes..."
for port in 8211 8212 8213 8214; do
  pid=$(lsof -ti tcp:$port 2>/dev/null || true)
  [ -n "$pid" ] && kill -9 $pid 2>/dev/null \
    && echo "  killed stale pid=$pid on port=$port" || true
done

# Start 4 partner agents in background
echo "[start] launching reader_profile_agent on :8211 ..."
nohup "$PYTHON_BIN" -m partners.online.reader_profile_agent.agent \
  > /tmp/acps_rpa.log 2>&1 &

echo "[start] launching book_content_agent on :8212 ..."
nohup "$PYTHON_BIN" -m partners.online.book_content_agent.agent \
  > /tmp/acps_bca.log 2>&1 &

echo "[start] launching recommendation_decision_agent on :8213 ..."
nohup "$PYTHON_BIN" \
  -m partners.online.recommendation_decision_agent.agent \
  > /tmp/acps_rda.log 2>&1 &

echo "[start] launching recommendation_engine_agent on :8214 ..."
nohup "$PYTHON_BIN" \
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
exec "$PYTHON_BIN" -m uvicorn \
  reading_concierge.reading_concierge:app \
  --host 0.0.0.0 \
  --port 8210 \
  --workers 1 \
  --timeout-keep-alive 300 \
  --log-level info
