# Recommendation Service Smoke Work Summary (2026-04-14)

## Scope
This document compresses the latest smoke-test work, findings, and open issues to guide next steps.

## Changes Made
- Updated `.env` with CF path variables:
  - `DATASET_ROOT=/root/WORK/DATA`
  - `CF_ITEM_FACTORS_PATH=/root/WORK/DATA/processed/cf_item_factors.npy`
  - `CF_BOOK_INDEX_PATH=/root/WORK/DATA/processed/cf_book_id_index.json`
- Added a fast ANN shortcut to `services/book_retrieval.py`:
  - `retrieve_books_by_query()` now attempts:
    1) `generate_text_embeddings(query)`  
    2) `retrieve_books_by_vector(embedding)`
  - Falls back to full keyword scan only if vector recall fails or returns empty.

## Path & Artifact Verification
Resolved paths (via `services.data_paths`):
- `processed_data_root` → `/root/WORK/DATA/processed`
- `books_master_merged.jsonl` → `/root/WORK/DATA/processed/books_master_merged.jsonl`
- `books_index.faiss` → `/root/WORK/DATA/processed/books_index.faiss`
- `CF_ITEM_FACTORS_PATH` → `/root/WORK/DATA/processed/cf_item_factors.npy`
- `CF_BOOK_INDEX_PATH` → `/root/WORK/DATA/processed/cf_book_id_index.json`

All 4 files exist.

## Embedding Backend Check
- Model: `/root/WORK/all-MiniLM-L6-v2`
- Backend: `sentence-transformers`
- Vector dim: `384`

## Offline ANN (FAISS) Recall Results
Using `retrieve_books_by_vector()` with generated query embeddings:
- `mystery detective thriller`: **0 results**, ~6.5s
- `science fiction space exploration`: **0 results**, ~20ms
- `historical romance 19th century`: **0 results**, ~19ms

## HTTP /user_api POST Results
Endpoints tested on `reading_concierge` (uvicorn on 127.0.0.1:8765):

- `POST /user_api_debug` with `{}`  
  → `{"detail":"query is required"}`

- `POST /user_api` with `{ "user_id": "gr_u_26334", "topk": 5 }`  
  → `{"detail":"query is required"}`

- `POST /user_api` with `{ "query": "...", "topk": 5 }`  
  → `{"detail":"user_id is required for /user_api"}`

- `POST /user_api` with `{ "user_id": "gr_u_26334", "query": "...", "topk": 5 }`  
  → `{"detail":"user_id is required for /user_api"}` (body rejected)

## Latency Benchmark (20 POST requests)
`/user_api` with `{ user_id, query, topk }`:
- 0/20 succeeded
- Errors: `timed out`, `HTTP Error 502: Bad Gateway`

## Server Log Warnings (latest)
- `redis_connect_failed` (localhost:6379/1 and /2)
- `partner_discovery_miss` for `rda` AIC

## Open Issues (Priority)
1. **Blocking — FAISS returns 0 results**  
   Likely embedding/index mismatch or index load failure.  
   Action: validate index dimensionality and rebuild `books_index.faiss` using the same embedding model.

2. **Blocking — /user_api rejects valid POST bodies**  
   Requests with both `user_id` and `query` still return “user_id required.”  
   Action: audit request parsing in `reading_concierge` and the POST schema; ensure JSON body is read correctly.

3. **Non-blocking — Redis not running**  
   Service falls back to local/memory stores; logs are noisy.  
   Action: start Redis or set config to disable Redis explicitly.

## Next Steps Proposal
1. Validate FAISS index load path and embedding dimension alignment.
2. Inspect `/user_api` request body handling and required fields.
3. Re-run HTTP smoke tests after fixes; confirm:
   - `/user_api` accepts JSON POST payloads
   - Hybrid requests return `recommendations`
   - Latency recovers (< 500ms P95)
