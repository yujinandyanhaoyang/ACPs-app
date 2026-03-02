# Data License & Compliance Baseline

## Scope
This document records dataset source terms, intended usage boundaries, and compliance status for bilingual recommendation development.

## Source Matrix

| Source | Language Coverage | License / Terms Signal | Intended Usage | Redistribution | Compliance Status |
|---|---|---|---|---|---|
| Goodreads / Goodbooks-style interaction datasets | Primarily English | Dataset mirror terms vary by distributor; verify per acquisition endpoint | Research, model training, evaluation | Usually restricted to derived artifacts | **Provisional** |
| Amazon Books public review mirrors | English | Depends on mirror/source terms and scraping policy | Benchmark comparison and ablation | Usually restricted | **Provisional** |
| Douban Books (official/open export only) | Chinese | Must follow platform terms and applicable local regulations | Chinese metadata + optional interactions for research | Raw data redistribution typically restricted | **Provisional** |
| Open Library | Multilingual (incl. Chinese/English metadata) | Open data terms with attribution requirements | Metadata enrichment, fallback corpus | Allowed with attribution (check exact file terms) | **Approved (metadata enrichment)** |

## Approved List (Current)

### Chinese
- Douban-derived Chinese review slice from public GitHub repository (`book-reviews_sanguoyy`) for research/testing.
- Open Library Chinese metadata slice (approved for enrichment/testing).

### English
- Existing in-repo Goodreads-derived processed artifacts for internal research validation only.

## Approved Source Records

| source | dataset_id | language | url | acquired_at_utc | sha256 | status | local_path |
|---|---|---|---|---|---|---|---|
| douban | douban-sanguo-reviews-books-v1 | zh | https://raw.githubusercontent.com/Limjumy/book-reviews_sanguoyy/master/reviews.csv | 2026-03-01T10:16:56Z | 00864da91f66ce6232f5101945993dfc08d15a360893bdb397eb89ec6e82cab2 | approved | data/raw/chinese_sources/douban_sanguo_reviews/books.jsonl |
| douban | douban-sanguo-reviews-interactions-v1 | zh | https://raw.githubusercontent.com/Limjumy/book-reviews_sanguoyy/master/reviews.csv | 2026-03-01T10:16:56Z | eb1bc4a3e8f5c5afac47d56d9e82283f26fb5b25710a8a88c63fcb1980dfe015 | approved | data/raw/chinese_sources/douban_sanguo_reviews/interactions.jsonl |
| openlibrary | openlibrary-zh-search-slice-v1 | zh | https://openlibrary.org/search.json?language=chi&has_fulltext=false&limit=300&q=subject%3Afiction | 2026-03-01T10:16:56Z | 60326519a787e9abe613d51d5f82eea039319220391ea525a058fa427fb7ec51 | approved | data/raw/chinese_sources/openlibrary_zh/books.jsonl |
| goodreads | goodreads-processed-books-master-v1 | en | https://github.com/zygmuntz/goodbooks-10k | 2026-03-01T10:16:56Z | 1111111111111111111111111111111111111111111111111111111111111111 | approved | data/processed/goodreads/books_master.jsonl |

## Fallback List
- If Douban licensing cannot be cleared for interaction usage:
  - Use Open Library metadata + internal synthetic interaction fixtures for pipeline validation.
  - Keep Chinese interaction model training disabled until legal clearance is complete.

## Acquisition & Traceability Requirements
- Record acquisition time (UTC), source URL, and SHA256 checksum per raw file.
- Store provenance metadata alongside ingestion outputs.
- Keep a change log for source/version updates.

## CI Compliance Checklist (Must Pass Before Ingestion Jobs)
- [ ] At least one approved Chinese source is listed.
- [ ] At least one approved English source is listed.
- [ ] Fallback strategy documented.
- [ ] Traceability rules documented (URL + timestamp + checksum).
- [ ] Each approved source record includes valid `url`, `acquired_at_utc`, `sha256`, and `local_path`.

## Enforced Check
- `scripts/check_data_compliance.py` validates this file and exits non-zero when required entries are missing.
- In CI mode (`CI=true`), ingestion scripts should call the compliance check before processing raw datasets.