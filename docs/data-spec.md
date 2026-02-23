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
