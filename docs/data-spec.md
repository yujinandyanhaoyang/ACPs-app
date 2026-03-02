# Data Spec (Phase 1 Bilingual Contract)

## Goal
Define a bilingual (Chinese + English) normalized contract that supports ingestion, cross-language deduplication, and merged-catalog retrieval without changing ACP orchestration semantics.

## Source strategy
- English: Goodreads-style interactions + metadata enrichment.
- Chinese: approved Chinese source(s) with provenance and license checks documented in `docs/data-license.md`.
- Fallback and compliance requirements are defined in `docs/dataset-decision.md` and enforced by `scripts/check_data_compliance.py` in CI.

## Required fields (master records)
Each normalized book record in `books_master*.jsonl` must include:
- `book_id` (string, globally unique)
- `canonical_work_id` (string, cross-language dedup anchor)
- `title` (string, non-empty)
- `language` (`zh` | `en` | `mixed`)
- `source` (string, e.g. `goodreads`, `douban`, `openlibrary`)
- `author` (string, `"Unknown"` allowed when missing)
- `description` (string, empty allowed)
- `genres` (array[string], normalized tokens)

## Optional fields (recommended)
- `original_title` (string)
- `translated_titles` (array[string])
- `aliases` (array[string])
- `publisher` (string)
- `published_year` (int)
- `isbn10` (string)
- `isbn13` (string)
- `script` (`hans` | `hant` | `latin`)
- `source_book_id` (string)

## Interaction fields
Each record in `interactions_*.jsonl` must include:
- `user_id` (string)
- `book_id` (string, must exist in corresponding master dataset)
- `rating` (float)
- `source` (string)

Optional:
- `timestamp` (string or null)
- `review_text` (string)

## Storage layout (Phase 1)
- English master: `data/processed/goodreads/books_master.jsonl`
- Chinese master: `data/processed/books_master_zh.jsonl`
- Chinese interactions:
	- `data/processed/interactions_train_zh.jsonl`
	- `data/processed/interactions_valid_zh.jsonl`
	- `data/processed/interactions_test_zh.jsonl`
- Cross-language artifacts:
	- `data/processed/book_canonical_map.json`
	- `data/processed/books_master_merged.jsonl`

## Quality checks
- Drop rows with empty `title`.
- Enforce `book_id` uniqueness per source dataset.
- Normalize `language` to `zh`/`en`/`mixed`.
- Normalize `genres` and text whitespace.
- Keep UTF-8 encoding for all reads/writes.
- For interactions, drop rows with missing `user_id`/`book_id` or unknown `book_id`.

## Build commands
```bash
venv/Scripts/python.exe scripts/prepare_chinese_sources.py --inputs-dir data/raw/chinese_sources
venv/Scripts/python.exe scripts/preprocess_goodreads.py
venv/Scripts/python.exe scripts/preprocess_chinese_dataset.py
venv/Scripts/python.exe scripts/build_cross_language_canonical_map.py
```

## Retrieval expectation
`services/book_retrieval.py` should be able to consume merged bilingual records and return non-empty results for both Chinese and English intents.

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
