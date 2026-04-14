#!/bin/bash
set -e
cd /root/WORK/ACPs-app
source .venv/bin/activate

# Pre-flight check
echo "[start] checking FAISS index..."
ls -lh /root/WORK/DATA/processed/books_index.faiss
ls -lh /root/WORK/DATA/processed/books_index_meta.jsonl

echo "[start] launching reading_concierge on 0.0.0.0:8210 ..."
exec .venv/bin/python -m uvicorn \
    reading_concierge.reading_concierge:app \
    --host 0.0.0.0 \
    --port 8210 \
    --workers 1 \
    --timeout-keep-alive 300 \
    --log-level info
