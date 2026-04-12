# ACPs Personalized Reading Recsys

A multi-agent book recommendation system built on the AIP (Agent Interaction Protocol) framework.

## Recommendation Pipeline

```text
reader_profile_agent          (port 8211)
      ↓ user profile: preferred_genres, reading_history, profile_vector
recommendation_engine_agent   (port 8214)
      ↓ ~100 candidate books recalled via FAISS vector search
book_content_agent            (port 8212)
      ↓ embedding + alignment score (uses title / genres / description)
rec_ranking_agent             (port 8216)
      ↓ MMR reranking → top-50 → top-5
recommendation_decision_agent  (port 8213)
      ↓ final decision
recommendation_engine_agent    (explanation module, same process)
      ↓ personalized justification text (LLM-generated)
feedback_agent                (port 8215)
      ↑ incremental profile update from user feedback
```

## Project Structure

```text
ACPs-app/
├── partners/online/
│   ├── reader_profile_agent/          # Builds user profile from behavior events
│   ├── recommendation_engine_agent/   # Recall + ranking + explanation
│   ├── book_content_agent/            # Embedding generation + alignment scoring
│   ├── rec_ranking_agent/             # MMR diversity reranking
│   ├── recommendation_decision_agent/ # Final decision logic
│   └── feedback_agent/                # Incremental profile update from feedback
├── services/
│   └── book_retrieval.py              # FAISS index lookup, dataset access
├── scripts/
│   ├── build_index.py                 # Build full FAISS index (~8h for 1.37M records)
│   └── test_pipeline_e2e.py           # End-to-end pipeline smoke test
└── data/
    └── processed/
        ├── books_master_merged.jsonl  # Primary dataset (1,378,470 records)
        ├── books_enriched.jsonl       # LLM-enriched subset (do not overwrite)
        ├── books_index.faiss          # FAISS IndexFlatIP (384-dim)
        └── books_index_meta.jsonl      # Metadata for FAISS index entries
```

## Setup

1. Configure environment

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY and verify dataset paths
```

2. Build the FAISS index

The full index build covers 1,378,470 records and takes about 8 hours.
Run it in the background:

```bash
nohup python scripts/build_index.py > /root/WORK/build_index.log 2>&1 &
```

A 10,000-record validation index is pre-built at `data/processed/books_index.faiss` and can be used for pipeline testing while the full build runs.

3. Start agents

Each agent is a standalone FastAPI service. Start them from the project root using the current entrypoints for each agent package.

4. mTLS (production)

mTLS is configured per-agent in `partners/online/<agent>/config.toml` under `[server.mtls]`.
Client certificates live in each agent's `certs/` directory. For local development set `AGENT_MTLS_ENABLED=false` in `.env`.

## Dataset

| Field | Description |
| --- | --- |
| `book_id` | Unique identifier (source-prefixed) |
| `title` | Book title |
| `author` | Author name |
| `genres` | List of genre strings |
| `description` | Text description (>= 50 chars) |
| `rating` | Float or null (Goodreads source) |
| `rating_source` | `goodreads` or null |
| `description_source` | `original` or `llm_generated` |
| `source` | `amazon` or `goodreads` |

Total records: 1,378,470

Embedding model: `all-MiniLM-L6-v2` (384-dim), projected to 256-dim via `book_content_agent/proj_matrix.npy`

FAISS index type: `IndexFlatIP` (inner-product / cosine similarity)

## LLM Configuration

All LLM calls use the Alibaba DashScope OpenAI-compatible endpoint.
Model selection is controlled per-agent via environment variables.
See `.env.example` for the complete list.
