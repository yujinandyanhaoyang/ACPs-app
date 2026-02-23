# Dataset Decision Matrix (Phase 2)

## Decision Summary
For the current phase, use:

- **Tier A (now):** Goodreads interaction-focused subset + Open Library metadata enrichment
- **Tier B (next):** Larger Goodreads/Amazon Books slice for full offline evaluation

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
- **Primary interactions:** public Goodreads interaction split (ratings/reviews + user/book IDs)
- **Metadata completion:** Open Library dumps/APIs for title/author/subjects/publisher/year backfill
- **Output target:** unified normalized files under `data/processed/`:
  - `books_master.jsonl`
  - `interactions_train.jsonl`
  - `interactions_valid.jsonl`
  - `interactions_test.jsonl`

### Why this exact choice
1. Provides collaborative filtering signal immediately (user-item interactions).
2. Supports content retrieval/explanations after metadata merge.
3. Enables KG construction from author/publisher/subject relations.
4. Keeps Phase 2 delivery speed reasonable versus full Amazon ingestion.

## Minimum Field Contract

### `books_master.jsonl`
- `book_id`
- `title`
- `author`
- `description`
- `genres` (or subjects mapped to genres)
- `publisher` (optional)
- `published_year` (optional)
- `source`

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
- Remove interactions whose `book_id` is absent from `books_master`

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
