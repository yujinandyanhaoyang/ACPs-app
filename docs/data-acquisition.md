# Data Acquisition Guide

## Goal

Acquire larger book datasets that can be normalized into this repo's existing schema for retrieval, recommendation, and offline evaluation.

Raw third-party files should live under the directory configured by `RAW_DATA_ROOT` in `.env`.

## Recommended Sources

### 1. Goodreads Book Reviews

- Source page: https://cseweb.ucsd.edu/~jmcauley/datasets/goodreads.html
- Why it fits:
  - Book-specific interactions
  - Ratings and review behavior
  - Large item/user coverage
- Best use in this repo:
  - Collaborative filtering signals
  - Baseline retrieval/evaluation
  - Core `books_master.jsonl` candidate pool

### 2. Amazon Review Data 2018 or 2023

- 2018 page: https://nijianmo.github.io/amazon/index.html
- 2023 page: https://amazon-reviews-2023.github.io/
- Best categories for this repo:
  - `Kindle Store` for initial testing and implementation
  - `Books` later for scale-up
- Why it fits:
  - Very large review volume
  - Rich metadata and descriptions
  - Useful for scaling inference candidate pools

### 3. Open Library Dumps / Metadata APIs

- Source page: https://openlibrary.org/developers/dumps
- Why it fits:
  - Good metadata enrichment
  - Lower compliance risk than scraped mirrors
  - Useful to backfill descriptions, authors, publishers, and subjects
- Best use in this repo:
  - Enrichment layer for Goodreads/Amazon items
  - Metadata completion for sparse records

## Recommended Acquisition Strategy

### Tier A

- Goodreads interactions + metadata as the primary recommendation dataset.
- Open Library for metadata enrichment.

### Tier B

- Amazon `Kindle Store` first for manageable initial testing.
- Amazon `Books` later as the scale-up dataset for a larger retrieval pool.

## Expected Raw File Layout

### Goodreads

Place files under:

`RAW_DATA_ROOT/goodreads/`

Expected files for the existing Goodreads preprocessor:

- `books.csv`
- `ratings.csv`
- `book_tags.csv`
- `tags.csv`

### Amazon Books / Kindle Store

Place files under:

`RAW_DATA_ROOT/amazon_books/`

- `meta_Kindle_Store.json.gz`
- `Kindle_Store_5.json.gz`

Optional scale-up alternatives:

- `meta_Books.json.gz`
- `Books_5.json.gz`

## Preprocessing Commands

### Goodreads

```powershell
venv\Scripts\python.exe scripts\preprocess_goodreads.py
```

Outputs:

- `data/processed/goodreads/books_master.jsonl`
- `data/processed/goodreads/interactions_train.jsonl`
- `data/processed/goodreads/interactions_valid.jsonl`
- `data/processed/goodreads/interactions_test.jsonl`

### Amazon Kindle Store

Default initial-testing command:

```powershell
venv\Scripts\python.exe scripts\preprocess_amazon_books.py
```

This uses:

- `meta_Kindle_Store.json.gz`
- `Kindle_Store_5.json.gz`
- output dir `data/processed/amazon_kindle`

### Amazon Books

```powershell
venv\Scripts\python.exe scripts\preprocess_amazon_books.py --metadata-file meta_Books.json.gz --reviews-file Books_5.json.gz --source amazon-books-2018 --out-dir data/processed/amazon_books
```

Outputs:

- `data/processed/amazon_kindle/books_master.jsonl`
- `data/processed/amazon_kindle/interactions_train.jsonl`
- `data/processed/amazon_kindle/interactions_valid.jsonl`
- `data/processed/amazon_kindle/interactions_test.jsonl`

## Inference Integration Options

### Fastest option

Point retrieval to one processed dataset with:

```powershell
$env:BOOK_RETRIEVAL_DATASET_PATH = "data/processed/amazon_kindle/books_master.jsonl"
```

### Better option

Merge Goodreads and Amazon normalized outputs into a unified `books_master_merged.jsonl` and use that as the retrieval corpus.

```powershell
venv\Scripts\python.exe scripts\merge_book_corpora.py --merge-interactions
```

This writes:

- `data/processed/merged/books_master_merged.jsonl`
- `data/processed/merged/interactions_merged.jsonl`

### Open Library enrichment

After merging, enrich sparse metadata with Open Library:

```powershell
venv\Scripts\python.exe scripts\enrich_books_openlibrary.py --input data/processed/merged/books_master_merged.jsonl --output data/processed/merged/books_master_merged_enriched.jsonl
```

Then point retrieval to the enriched merged corpus:

```powershell
$env:BOOK_RETRIEVAL_DATASET_PATH = "data/processed/merged/books_master_merged_enriched.jsonl"
```

## Practical Notes

- Start with smaller category slices before attempting full Amazon dumps.
- Prefer 5-core Amazon subsets first if local disk or preprocessing time is limited.
- Goodreads links are directly downloadable; Amazon 2018 per-category Kindle Store and Books files may require the dataset access form from the source page.
- Record source URLs, acquisition dates, and any usage restrictions before training or redistribution.
- Do not commit raw third-party dumps into git.
- Set `RAW_DATA_ROOT` before running preprocessors if your raw data is stored outside the repo.

## Next Recommended Step

1. Download Goodreads raw files into `RAW_DATA_ROOT/goodreads/`.
2. Download Amazon `Kindle Store` files into `RAW_DATA_ROOT/amazon_books/` for the first pass.
3. Run both preprocessors.
4. Merge normalized outputs for a larger retrieval pool.