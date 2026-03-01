## Plan: Dual Chinese-English Dataset Support (Phase-0 First, Implementation-Specific)

### Objective
Deliver reliable bilingual recommendations (Chinese + English) by fixing core retrieval foundations first, then introducing dual-corpus routing and fusion.

### Non-Negotiable Rule
Do **not** start Chinese dataset expansion until Phase 0 passes all gates.

### Immediate Actions (Execution Starts Here)
1. Validate dataset sources and obtain legal clearance for Chinese data usage.
2. Baseline current English-only system performance with broader evaluation coverage.
3. Prototype minimal Chinese support by testing tokenization/language detection on Chinese queries over existing English corpus.

---

## Phase -1 (1 week): Dataset Research & Licensing (Pre-Implementation)

### -1.1 Source validation and legal clearance
Deliverables:
- Candidate source matrix for Chinese datasets (license type, allowed use, redistribution constraints).
- Approved source list signed off for development/testing usage.
- Fallback source list if primary source fails legal review.

### -1.2 Data governance baseline
Deliverables:
- `docs/data-license.md` with source URLs, terms summary, acquisition timestamp, and checksum rules.
- Compliance checklist that must pass before ingestion jobs can run in CI.

Exit gate:
- At least one Chinese dataset source approved for planned usage scope.

---

## Phase 0 (1 week): Foundation Fixes (Blocking)

### 0.1 Chinese-safe tokenization (blocking)
**Target file:** `services/book_retrieval.py`

Implement language-aware tokenization:
- Unicode normalize (`NFKC`), lowercase for Latin segments, trim punctuation.
- If query contains CJK chars:
	- Prefer `jieba` segmentation (or equivalent) for Chinese words.
	- Keep mixed tokens (Chinese + alnum), discard stop tokens and 1-char noise except meaningful Chinese single-char entities if configured.
- If non-CJK dominant:
	- Keep current regex tokenization behavior for English.

Deliverables:
- `_tokenize_multilingual(text, lang_hint=None)`
- Unit tests for Chinese/English/mixed query token outputs.

Acceptance gate:
- Chinese query samples produce `>= 5` meaningful tokens in 90%+ of test cases.

### 0.2 Query language detection
**Target files:** `services/book_retrieval.py`, `reading_concierge/reading_concierge.py`

Implement deterministic language detection (no LLM dependency):
- Character ratio heuristic:
	- `cjk_ratio = cjk_chars / total_letters`
	- `latin_ratio = latin_chars / total_letters`
- Rule:
	- if `cjk_ratio >= 0.25` => `zh`
	- elif `latin_ratio >= 0.5` => `en`
	- else => `mixed`
- Return confidence (ratio margin).

Deliverables:
- `detect_query_language(query) -> {language, confidence, stats}`
- Route diagnostics added to response traces.

Acceptance gate:
- 95%+ accuracy on curated bilingual detection set.

### 0.3 Encoding integrity (end-to-end)
**Target files:** ingestion scripts + API response path

Requirements:
- All file IO explicitly UTF-8.
- Response JSON uses `ensure_ascii=False` where applicable in debug/export scripts.
- Add smoke test for Chinese title round-trip (ingest -> retrieval -> API -> UI text).

Acceptance gate:
- No mojibake in 100 sampled Chinese titles.

### 0.4 Multilingual embedding model evaluation
**Target files:** `services/model_backends.py`, evaluation scripts under `scripts/`

Evaluate at least one Chinese-capable embedding option and one multilingual option against current default backend.

Deliverables:
- Short benchmark report (quality + latency + cost) on bilingual query set.
- Recommended default embedding backend by language (`zh`, `en`, `mixed`).

Acceptance gate:
- Selected embedding backend demonstrates non-regressive English quality and improved Chinese retrieval relevance.

---

## Phase 1 (2 weeks): Data Contract + Chinese Pipeline

### 1.1 Data contract update (exact fields)
**Target file:** `docs/data-spec.md`

Required fields for bilingual master records:
- `book_id` (string, globally unique)
- `canonical_work_id` (string, cross-language dedup anchor)
- `title` (string)
- `language` (`zh` | `en` | `mixed`)
- `source` (`goodreads` | `douban` | ...)
- `author` (string)
- `description` (string)
- `genres` (array[string])

Optional but strongly recommended:
- `original_title`
- `translated_titles` (array)
- `aliases` (array)
- `publisher`, `published_year`
- `isbn10`, `isbn13`
- `script` (`hans`, `hant`, `latin`)

### 1.2 Chinese ingestion
**Target folder:** `scripts/`

Outputs:
- `data/processed/books_master_zh.jsonl`
- `data/processed/interactions_train_zh.jsonl`
- `data/processed/interactions_valid_zh.jsonl`
- `data/processed/interactions_test_zh.jsonl`

Constraints:
- Same schema and validation behavior as existing Goodreads pipeline.
- Source/license audit entry required before model training.

### 1.3 Cross-language deduplication
**Target folder:** `scripts/`

Dedup strategy priority:
1. Exact ISBN match.
2. `canonical_work_id` match.
3. Normalized title+author fuzzy match above threshold.

Output artifacts:
- `book_canonical_map.json` (`book_id -> canonical_work_id`)
- `books_master_merged.jsonl`

Acceptance gate:
- Duplicate translation pairs in same top-k results `< 5%`.

---

## Phase 2 (2 weeks): Runtime Retrieval + Fusion (Metadata-First)

### 2.0 Metadata fusion first (before full corpus fusion)
Start with low-risk fusion based on normalized metadata fields (`language`, `aliases`, `canonical_work_id`, `source`) while keeping retrieval storage physically separate.

Stage 1:
- Fuse candidate metadata and dedup logic first.
- Keep corpus retrieval independent; combine after scoring.

Stage 2:
- Enable full corpus-level fusion once Stage 1 stability/quality gates pass.

### 2.1 Dual-corpus retrieval routing
**Target file:** `services/book_retrieval.py`

Inputs:
- `BOOK_RETRIEVAL_DATASET_PATH_EN`
- `BOOK_RETRIEVAL_DATASET_PATH_ZH`
- routing mode: `strict|soft|agnostic` (default `soft`)

Routing behavior (`soft`):
- Detect query language.
- Retrieve from primary corpus first (`zh` query -> zh corpus, `en` query -> en corpus).
- Retrieve fallback candidates from secondary corpus.

### 2.2 Fusion algorithm (explicit)
For each candidate:

`final_score = 0.35 * lexical + 0.35 * semantic + 0.20 * language_boost + 0.10 * popularity - dedup_penalty`

Where:
- `language_boost = 1.0` same language, `0.4` mixed, `0.0` mismatch.
- `dedup_penalty = 0.25` if same `canonical_work_id` already selected.
- Weights configurable via env.

Fallback trigger:
- If primary-corpus relevant results `< min_primary_hits` (default 5), inject fallback corpus.

### 2.3 Concierge diagnostics
**Target file:** `reading_concierge/reading_concierge.py`

Add trace fields:
- `detected_query_language`, `language_confidence`
- `primary_corpus`, `fallback_used`
- candidate counts per corpus
- fusion component averages

---

## Phase 3 (1 week): Validation + Release Gates

### 3.1 Automated tests
**Target files:** `tests/test_book_retrieval.py`, `tests/test_reading_concierge.py`

Add:
- Chinese tokenization unit tests.
- Language detection accuracy tests.
- Opposite-intent Chinese pair tests (low overlap).
- Cross-language fallback behavior tests.
- Dedup-in-topk tests.

### 3.2 Quantitative release gates
- Language detection accuracy `>= 95%`
- Chinese NDCG@5 `>= 0.60`
- Cross-language fallback trigger rate `< 30%` on Chinese set
- p95 latency increase `< 100ms`
- Duplicate items in result set `< 5%`

### 3.3 Qualitative audit
- 20 Chinese + 20 English manual query checks.
- Verify topical fit, language appropriateness, and explanation consistency.

### 3.4 A/B testing infrastructure
Add controlled experiment support for retrieval/routing variants.

Deliverables:
- Variant flags for at least: `baseline`, `metadata-first-fusion`, `full-fusion`.
- Experiment logging schema (variant, query language, metrics snapshot, latency).
- A/B summary script for comparing relevance and latency across variants.

Acceptance gate:
- New variant beats baseline on Chinese relevance without unacceptable regression on English metrics/latency.

---

## Risks and Mitigations
- **Chinese dataset licensing risk:** define fallback source pipeline and block training until compliance checklist passes.
- **Cost/latency risk:** cache embeddings by `(book_id, language, model)`; enable batch embedding jobs.
- **Model mismatch risk:** support Chinese-friendly embedding backend selection separately from English.

---

## Execution Order (Strict)
1. Phase -1 licensing/research gates pass.
2. Phase 0 all foundation gates pass.
3. Phase 1 data ingestion + dedup.
4. Phase 2 runtime integration (metadata-first, then full fusion).
5. Phase 3 validation, A/B testing, and rollout.

If Phase 0 fails, stop and iterate before any new data onboarding.
