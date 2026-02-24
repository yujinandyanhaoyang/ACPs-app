# Data Spec (Phase 2 Pre)

## Goal
Provide a minimal, real-book dataset contract that unblocks Phase 2 retrieval work in `DEBUG_PLAN.md`.

## Source strategy
- Phase 2 Tier A selected source: Goodreads interaction-focused subset + Open Library metadata enrichment.
- See `docs/dataset-decision.md` for the decision matrix and rollout plan.
- `data/raw/books_min_sample.jsonl` is retained for smoke tests only and is not a production evaluation dataset.

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
- Raw sample input: `data/raw/books_min_sample.jsonl`
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
