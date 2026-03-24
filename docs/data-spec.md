# Data Spec (Phase 2 Pre)

## Goal
Provide a minimal, real-book dataset contract that unblocks Phase 2 retrieval work in `DEBUG_PLAN.md`.

## Source strategy
- Phase 2 Tier A selected source: Goodreads interaction-focused subset + Open Library metadata enrichment.
- See `docs/dataset-decision.md` for the decision matrix and rollout plan.
- Raw data is resolved from `RAW_DATA_ROOT` and defaults to `data/raw/` only when the env override is absent.
- `RAW_DATA_ROOT/books_min_sample.jsonl` is retained for smoke tests only and is not a production evaluation dataset.

## Required fields
Each normalized book record must include:
- `book_id` (string, unique)
- `title` (string, non-empty)
- `author` (string, may be `"Unknown"` when missing)
- `description` (string, may be empty)
- `genres` (array of lowercase strings; can be empty)

## Recommended optional fields
- `publisher` (string)
- `published_year` (int)
- `source` (string, dataset provenance)

## Storage layout
- Raw sample input: `RAW_DATA_ROOT/books_min_sample.jsonl`
- Processed output: `data/processed/books_min.jsonl`

## Quality checks
- Drop rows with empty `title`
- Ensure `book_id` uniqueness (deduplicate by first seen)
- Normalize `genres` to lowercase snake-case tokens
- Normalize text whitespace for `title`, `author`, `description`

## Build command
Run preprocessing:

```bash
venv/Scripts/python.exe scripts/build_books_min_dataset.py
```

## Retrieval fallback expectation
`services/book_retrieval.py` must be able to return non-empty candidate sets for common queries such as:
- `science fiction space`
- `history civilization`
- `business startup`

---

## KG Schema (Knowledge Graph — Phase P1)

### Build command
```bash
venv/Scripts/python.exe scripts/build_knowledge_graph.py
```

### Output files
| File | Description |
|---|---|
| `data/processed/knowledge_graph.json` | Full NetworkX node-link JSON (undirected Graph) |
| `data/processed/kg_author_index.json` | `{author_node_id: [book_node_id, ...]}` lookup table |
| `data/processed/kg_genre_index.json` | `{genre_node_id: [book_node_id, ...]}` lookup table |

### Node types
| type | ID format | Key attributes |
|---|---|---|
| `book` | `book:gr_2767052` | `book_id`, `title` |
| `author` | `author:suzanne_collins` | `name` |
| `genre` | `genre:young_adult` | `name` |
| `publisher` | `publisher:scholastic_press` | `name` |

### Edge types
| type attribute | connects | meaning |
|---|---|---|
| `written_by` | book ─ author | book was written by this author |
| `has_genre` | book ─ genre | book belongs to this genre |
| `published_by` | book ─ publisher | book was published by this publisher (sparse) |

### Genre filtering
Goodreads user-shelf tags (`to_read`, `favorites`, `currently_reading`, `owned`, etc.) are excluded from genre nodes. Only genre-like tokens are kept. The full exclusion list is in `scripts/build_knowledge_graph.py::_SHELF_TAGS`.

### Access pattern
Use `services/kg_client.LocalKGClient` to query the graph:
```python
from services.kg_client import LocalKGClient
client = LocalKGClient()
ctx = client.get_book_context("book:gr_2767052")
# {"authors": ["author:suzanne_collins"], "genres": ["genre:young_adult", ...], "co_genre_books": [...]}
signals = client.compute_kg_signal(["book:gr_2767052", "book:gr_3"])
# {"book:gr_2767052": 0.82, "book:gr_3": 1.0}
```

---

## CF Model (Phase P2)

### Build command
```bash
venv/Scripts/python.exe scripts/build_cf_model.py --components 50
```

### Input
| File | Description |
|---|---|
| `data/processed/goodreads/interactions_train.jsonl` | User-book interactions with `user_id`, `book_id`, `rating` |

### Output files
| File | Description |
|---|---|
| `data/processed/cf_item_factors.npy` | Item latent vectors (rows aligned to `cf_book_id_index.json`) |
| `data/processed/cf_user_factors.npy` | User latent vectors (rows aligned to `cf_user_id_index.json`) |
| `data/processed/cf_book_id_index.json` | `{book_id: row_index_in_item_factors}` mapping |
| `data/processed/cf_user_id_index.json` | `{user_id: row_index_in_user_factors}` mapping |

### Runtime loading contract
- `services.model_backends.load_cf_item_vectors()` loads `cf_item_factors.npy` + `cf_book_id_index.json` on first call and caches `{book_id: latent_vector}` in memory.
- Optional env overrides:
	- `CF_ITEM_FACTORS_PATH`
	- `CF_BOOK_INDEX_PATH`
- `estimate_collaborative_scores_with_svd()` now uses this pre-factored store first (`backend=pretrained-svd`) and falls back to overlap/SVD only for uncovered candidates (`backend=pretrained-svd+overlap-fallback`).

---

## Runtime Persistence Schema (Phase P4)

### Migration Command

```bash
python scripts/migrate_db.py
```

### Default Runtime DB

- URL: `sqlite:///data/recommendation_runtime.db`
- Override env: `RECSYS_DB_URL`

### Core Tables

- `users`
- `user_events`
- `user_profiles`
- `books`
- `book_features`
- `recommendation_runs`
- `recommendations`
- `agent_task_logs`
- `schema_migrations`

### Backfill Commands

```bash
python scripts/backfill_user_events.py --legacy-db data/user_profile_store.db
python scripts/backfill_book_features.py --books-jsonl data/processed/merged/books_master_merged.jsonl --limit 2000
```

### Runtime Write Contract

- Lifecycle events and profile snapshots are mirrored from `services/user_profile_store.py` into repository-backed persistence.
- Recommendation orchestration writes:
  - run-level metadata (`recommendation_runs`)
  - per-item score/explanation rows (`recommendations`)
  - partner task-state lineage (`agent_task_logs`)
