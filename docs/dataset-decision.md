# Dataset Decision Matrix (Phase 1/2)

## Decision Summary
For current implementation phases, use:

- **Tier A (now):** Goodreads interaction-focused subset + approved Chinese source + Open Library metadata enrichment
- **Tier B (next):** Larger Goodreads/Amazon Books slice and expanded Chinese interactions for full offline evaluation

This is the fastest path to satisfy `PLAN.md` requirements while avoiding hardcoded recommendation behavior.

## Candidate Comparison

| Candidate | Interaction signal (ratings/reviews) | Metadata richness | Preprocessing cost | License/compliance risk | Fit for current phase |
|---|---:|---:|---:|---:|---:|
| Goodreads subset + Open Library | High | High (after merge) | Medium | Medium (must verify source terms) | **Best** |
| Amazon Books reviews/metadata | High | Medium-High | High | Medium (depends on mirror/source terms) | Good (fallback/expansion) |
| Open Library only | Low (no user-item behavior) | High | Medium | Low-Medium | Not enough alone |
| Current `books_min_sample.jsonl` | None | Low | Low | Low | Smoke tests only |

## Selected Exact Source Strategy

### Tier A (implement first)
- **Primary interactions (EN):** public Goodreads interaction split (ratings/reviews + user/book IDs)
- **Primary metadata (ZH):** approved Chinese metadata + optional interactions from approved source
- **Metadata completion:** Open Library dumps/APIs for title/author/subjects/publisher/year backfill
- **Output target:** normalized files under `data/processed/`:
  - `goodreads/books_master.jsonl`
  - `goodreads/interactions_train.jsonl`
  - `goodreads/interactions_valid.jsonl`
  - `goodreads/interactions_test.jsonl`
  - `books_master_zh.jsonl`
  - `interactions_train_zh.jsonl`
  - `interactions_valid_zh.jsonl`
  - `interactions_test_zh.jsonl`
  - `book_canonical_map.json`
  - `books_master_merged.jsonl`

### Why this exact choice
1. Provides collaborative filtering signal immediately (user-item interactions).
2. Supports content retrieval/explanations after metadata merge.
3. Enables KG construction from author/publisher/subject relations.
4. Keeps Phase 2 delivery speed reasonable versus full Amazon ingestion.

## Minimum Field Contract

### `books_master*.jsonl`
- `book_id`
- `canonical_work_id`
- `title`
- `language` (`zh` | `en` | `mixed`)
- `author`
- `description`
- `genres` (or subjects mapped to genres)
- `source`
- `publisher` (optional)
- `published_year` (optional)
- `isbn10` / `isbn13` (optional)
- `script` (optional)

### `interactions_*.jsonl`
- `user_id`
- `book_id`
- `rating`
- `timestamp` (optional)
- `review_text` (optional)
- `source`

## Split Policy
- Random split by interaction rows: **80/10/10** (train/valid/test)
- Enforce no empty `book_id`/`user_id`
- Remove interactions whose `book_id` is absent from corresponding source master files

## Compliance Checklist (must pass before model training)
- Record exact download source and license terms in `docs/data-license.md`
- Record acquisition timestamp and checksum for reproducibility
- Confirm redistribution constraints for derived artifacts

## Immediate Execution Plan
1. Add raw ingestion adapters for Goodreads interactions and Open Library metadata.
2. Build merge+normalize pipeline to produce `books_master.jsonl`.
3. Build interaction cleaner and 80/10/10 splitter.
4. Switch retrieval to `books_master.jsonl` (already no hardcoded fallback).
5. Add data integrity tests (non-empty, schema-valid, split-size sanity checks).
