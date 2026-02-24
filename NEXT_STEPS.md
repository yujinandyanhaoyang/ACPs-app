# NEXT_STEPS.md — Remaining PLAN.md Work, Priority-Ordered

> **Date created**: 2026-02-24  
> **Scope**: All remaining gaps identified in the 2026-02-24 full audit against `PLAN.md`.  
> **Active tasks are ordered by dependency** — each priority level unlocks the work in the next.  
> Update this file's checkboxes as items are completed; log outcomes in `WORKLOG_DEV.md`.

---

## Quick-reference gap table

| PLAN.md Section | Score | Open gaps |
|---|---|---|
| (一) Data | 3/4 | Knowledge graph not built |
| (二) Agent implementation | 6/10 | KG RAG absent; CF is content-based not user-item; BERT not used; hash-fallback degrades semantics |
| (三) Architecture & integration | 5/7 | Registry/mTLS stubs; ACS `endPoints` empty |
| (四) Testing & optimization | 5/7 | Ablation is algebraic not empirical; baselines are heuristic stubs; test split unused |

---

## P1 — Knowledge Graph Construction *(Critical — unblocks KG scoring)*

**PLAN.md coverage**: §(一).3, §(二) content-agent KG RAG, §(二) ranking-agent knowledge dimension

**Implementation choice**: **NetworkX in-memory** graph only. This runs entirely locally with no server dependencies, which is appropriate for a research/demo context with limited hardware. A future Neo4j migration path remains possible through the `kg_endpoint` + `use_remote_kg` config already present in the system, but is outside the scope of this project.

**Why first**: The `knowledge` scoring dimension in the ranking agent is always near-zero because `_extract_kg_refs()` returns stub URL strings derived from book IDs. Building a real graph is the prerequisite for meaningful knowledge-enhanced ranking and for demonstrating graph RAG as required by PLAN.md.

### P1a — Define graph schema and build it from the Goodreads dataset
- [x] Create `scripts/build_knowledge_graph.py`
  - Load `data/processed/goodreads/books_master.jsonl`
  - Extract three edge types: `author → book`, `publisher → book`, `genre → book`
  - Build a `networkx.Graph` object; also persist as `data/processed/knowledge_graph.json` (node-link format via `networkx.node_link_data`) for caching and reproducibility
  - Also write `data/processed/kg_author_index.json` and `kg_genre_index.json` for O(1) node lookups without loading the full graph
- [x] Add a `KGSchema` section to `docs/data-spec.md` documenting node types (`book`, `author`, `publisher`, `genre`), edge types, and field contracts
- [x] Add `networkx` to `requirements.txt`

### P1b — Create `services/kg_client.py` (NetworkX local client)
- [x] Implement `LocalKGClient` using NetworkX:
  - `load()` — reads `knowledge_graph.json` once; builds an in-memory `networkx.Graph`; cached at module level
  - `get_neighbors(node_id, edge_type=None) -> List[str]` — returns adjacent node IDs, optionally filtered by edge type
  - `get_book_context(book_id) -> Dict[str, List[str]]` — returns `{"authors": [...], "genres": [...], "co_genre_books": [...]}` for a given book node
  - `compute_kg_signal(book_ids: List[str]) -> Dict[str, float]` — for each book, returns a normalized connectivity score with soft floor (pool-minimum connected books score ≥ 0.1; disconnected books score 0.0)
- [x] Add `tests/test_kg_client.py` with a 5-node fixture graph covering: load, `get_neighbors`, `get_book_context`, `compute_kg_signal` (33 tests, all passing)

### P1c — Integrate `LocalKGClient` into `book_content_agent`
- [x] Rewrite `_extract_kg_refs()` in `agents/book_content_agent/book_content_agent.py`:
  - Call `LocalKGClient.get_book_context(book_id)` for each input book
  - Return the union of connected node IDs (author nodes + genre nodes)
  - Replace stub URL strings with real graph node identifiers (e.g., `"author:Isaac_Asimov"`, `"genre:science_fiction"`)
- [x] Update `_analyze_content()` to call `LocalKGClient.compute_kg_signal(book_ids)` and embed the result into each book's `kg_signal` field in each content vector entry
- [x] Fix `_build_ranking_candidates()` in `reading_concierge/reading_concierge.py`: changed global constant formula to `row.get("kg_signal", 0.2)` so each candidate reads its own per-book signal
- [x] `kg_signal` now reflects genuine graph connectivity depth (81/81 tests pass, 5 HTTP e2e skipped)

---

## P2 — True User-Item Collaborative Filtering *(Critical — fixes CF scoring dimension)*

**PLAN.md coverage**: §(二) ranking-agent SVD/matrix-factorization

**Why second**: The current `estimate_collaborative_scores_with_svd()` builds a term-frequency matrix over genre tokens — this is content-based dimensionality reduction, not collaborative filtering. `interactions_train.jsonl` (72k+ ratings) exists but is never loaded by any agent.

### P2a — Build a pre-factored user-item matrix
- [ ] Create `scripts/build_cf_model.py`
  - Parse `data/processed/goodreads/interactions_train.jsonl`
  - Build a sparse user × book rating matrix (use `scipy.sparse.csr_matrix`)
  - Apply `sklearn.decomposition.TruncatedSVD` (k=50 components)
  - Serialize latent factors: `data/processed/cf_item_factors.npy` (book latent vectors) + `data/processed/cf_user_factors.npy`
  - Also write `data/processed/cf_book_id_index.json` (book_id → matrix column index)
- [ ] Document the offline build in `docs/data-spec.md` under a "CF Model" section

### P2b — Load pre-factored item vectors in the ranking agent
- [ ] In `services/model_backends.py`, add `load_cf_item_vectors() -> Dict[str, List[float]]`:
  - Reads `cf_item_factors.npy` + `cf_book_id_index.json` at first call; caches result
  - Returns `{book_id: latent_vector}` for all indexed books
- [ ] Modify `estimate_collaborative_scores_with_svd()` to check the pre-factored store first:
  - If a candidate's `book_id` is in the CF index, use its pre-factored vector for cosine similarity against the user's weighted-history estimate
  - Fall back to the current genre-overlap SVD path only for books not in the index
- [ ] Add `test_cf_model.py` with: load → lookup known book_id → verify latent vector dimensionality

**Acceptance criteria**: `collaborative_backend` in ranking output is `"pretrained-svd"` for at least 50% of candidates when the Goodreads dataset is present.

---

## P3 — Offline SentenceTransformer Embedding Fallback *(Important — fixes silent semantic degradation)*

**PLAN.md coverage**: §(二) content-agent Sentence-BERT vectorization

**Why third**: When `OPENAI_API_KEY` or `OPENAI_BASE_URL` is not set, all vector operations silently fall back to `hash_embedding()` (SHA-256 → float array). Cosine similarity over these vectors is meaningless. The system must produce semantically valid embeddings offline for reproducible demos and CI.

### P3a — Add a named offline SentenceTransformer model
- [ ] In `services/model_backends.py`, change the default offline model from `"qwen-plus"` to `"all-MiniLM-L6-v2"` (22 MB download, 384-d output)
- [ ] In `.env.example`, document:
  ```
  # Local offline embedding model (no API key required)
  BOOK_CONTENT_EMBED_MODEL=all-MiniLM-L6-v2
  ```
- [ ] Add `sentence-transformers` to `requirements.txt` (it is already a soft dependency; make it explicit)

### P3b — Align profile-side vector space when using offline model
- [ ] In `rec_ranking_agent`, `_profile_to_embedding()` already calls `generate_text_embeddings_async` with the same model. Verify that `EMBED_MODEL` in rec_ranking_agent reads `BOOK_CONTENT_EMBED_MODEL` (it does — confirm no config drift).
- [ ] Add a test fixture to `tests/conftest.py` that patches `generate_text_embeddings_async` with deterministic 384-d vectors instead of the current 12-d hash fallback, so unit tests exercise the correct vector size code paths.

### P3c — Suppress noisy fallback warning
- [ ] In `model_backends.py`, when `SentenceTransformer` fails to load the given model name, log a `WARNING` with the model name and fallback type (currently silent). This exposes misconfigured environments immediately.

**Acceptance criteria**: Running the demo with no API keys but with `sentence-transformers` installed produces semantically non-trivial cosine similarities; `embedding_backend` in ranking output is `"sentence-transformers"`.

---

## P4 — ACS Descriptor Completion + ACPs Conformance Test *(Important — architecture correctness)*

**PLAN.md coverage**: §(三) AIC/ATR/ADP/ACS standards compliance

**Why fourth**: `reading_concierge/reading_concierge.json` has `"endPoints": []`. Any service registry or discovery service cannot locate the leader. Partner agent `config.example.json` files have endpoints, but the leader descriptor is missing its RPC URL.

### P4a — Populate `endPoints` in `reading_concierge.json`
- [ ] Update `reading_concierge/reading_concierge.json`:
  ```json
  "endPoints": [
    {
      "transport": "JSONRPC",
      "url": "http://localhost:8100/user_api",
      "description": "Primary orchestration endpoint"
    }
  ]
  ```
- [ ] Add an env variable `READING_CONCIERGE_BASE_URL` (default `http://localhost:8100`) read at startup to dynamically regenerate the endpoint URL in the ACS response

### P4b — Expose `/acs` descriptor endpoint on all agents
- [ ] Each FastAPI app (`reading_concierge`, `reader_profile_agent`, `book_content_agent`, `rec_ranking_agent`) should expose a `GET /acs` route returning its JSON descriptor
- [ ] Implement a shared helper in `base.py`: `register_acs_route(app, json_path)` — reads the ACS JSON file and mounts the route

### P4c — ACPs conformance smoke test
- [ ] Create `tests/test_acs_conformance.py`:
  - For each agent app: call `GET /acs` → assert response contains required fields (`aic`, `skills`, `endPoints`, `protocolVersion`)
  - Assert `endPoints` is a non-empty list
  - Assert all skill IDs are non-empty strings

**Acceptance criteria**: All four `GET /acs` routes return valid, non-empty descriptors; conformance test passes with zero failures.

---

## P5 — Empirical Ablation Study Against Held-Out Test Split *(Recommended — evaluation validity)*

**PLAN.md coverage**: §(四) ablation study, §(四) system evaluation with Precision@k / Recall@k / NDCG@k

**Why fifth**: `build_ablation_report()` computes algebraic decomposition (component mean × weight), not a true ablation. `interactions_test.jsonl` exists but is unused. PLAN.md requires measuring actual impact when components are removed.

### P5a — Load the held-out test split into the evaluation harness
- [ ] In `services/evaluation_metrics.py`, add `load_test_interactions(n: int = 100) -> List[Dict]`:
  - Reads `data/processed/goodreads/interactions_test.jsonl`
  - Returns up to `n` interactions with fields: `user_id`, `book_id`, `rating`
- [ ] Build a mini evaluation runner in `scripts/run_ablation.py`:
  - For each test user: derive a minimal profile from `interactions_train.jsonl`, run the full pipeline, compare ranked output against held-out book IDs from `interactions_test.jsonl`
  - Compute `Precision@5`, `Recall@5`, `NDCG@5`

### P5b — True ablation: re-run with each scoring component zeroed out
- [ ] In `scripts/run_ablation.py`, run the evaluation four times, each time setting one `scoring_weights` component to `0.0` and renormalizing the rest
- [ ] Report delta NDCG@5 for each ablated component
- [ ] Write results to `scripts/ablation_report.json`

### P5c — Update `build_ablation_report()` docstring
- [ ] Clarify in the function docstring that it returns algebraic decomposition, not an empirical ablation, and point to `scripts/run_ablation.py` for empirical results

**Acceptance criteria**: `ablation_report.json` contains four rows (CF ablated, semantic ablated, knowledge ablated, diversity ablated) each with numeric NDCG@5 delta vs. full model; at least two components show non-zero delta.

---

## P6 — Principled Baseline Reimplementation + MACRec Proxy *(Recommended — benchmark validity)*

**PLAN.md coverage**: §(四) benchmark against traditional hybrid / MACRec / ARAG

**Why sixth**: `traditional_hybrid_rank()` in `services/baseline_rankers.py` uses magic-number weights. The comparison results in Phase IV benchmarks have no external validity. Neither MACRec nor ARAG is implemented.

### P6a — Reimplment `traditional_hybrid_rank` using real data signals
- [ ] Replace the heuristic with popularity (rating count from `interactions_train.jsonl`) × content similarity (token overlap with query):
  - Popularity score: `log(1 + rating_count)` normalized over the candidate pool
  - Content similarity: existing `retrieve_books_by_query` overlap score
  - Hybrid: 0.5 × popularity + 0.5 × content
- [ ] Ensure the same real candidate pool (from `load_books()`) is used, matching the ACPs pipeline

### P6b — Implement a `multi_agent_sequential_rank` proxy
- [ ] Replace the current `multi_agent_proxy_rank` stub with a sequential (non-parallel) version of the same three-agent pipeline
- [ ] This approximates a naive "call agents one-by-one" design; the ACPs pipeline's speedup via `asyncio.gather` is then quantifiable

### P6c — Add MACRec-style LLM-only baseline
- [ ] Add `llm_only_rank(case_payload, top_k) -> List[Dict]` to `baseline_rankers.py`:
  - Single LLM call: "Given the user history and query, select the top-k books from these candidates"
  - No vector math, no SVD — pure LLM retrieval
  - This is the closest approximation to MACRec/ARAG's LLM-centric approach

### P6d — Re-run Phase IV benchmark with real baselines
- [ ] Re-run `scripts/phase4_benchmark_compare.py` with the new baselines
- [ ] Generate `scripts/phase4_benchmark_report.md` with updated rankings and analysis

**Acceptance criteria**: `phase4_benchmark_report.md` contains at least three methods with real (not stub) implementations; NDCG@5 values span a meaningful range.

---

## P7 — mTLS Enforcement Scaffold *(Optional — production security)*

**PLAN.md coverage**: §(三) security / mTLS inter-agent communication

**Why last**: The `acps_aip/mtls_config.py` module and `config.example.json` certs paths are defined but never applied. This is the lowest operational priority, required only for deployment beyond localhost.

### P7a — Wire mTLS loader into agent startup
- [ ] In `acps_aip/mtls_config.py`, verify `load_mtls_context()` returns an `ssl.SSLContext`
- [ ] In each agent's `main()` or uvicorn startup, if cert files are present, pass the SSL context to uvicorn
- [ ] Gate behind an env flag `AGENT_MTLS_ENABLED=false` (default disabled) so local development is unaffected

### P7b — Generate local self-signed development certificates
- [ ] Add `scripts/gen_dev_certs.sh` (Linux/Mac) and `scripts/gen_dev_certs.ps1` (Windows) to generate a local CA + per-agent cert/key pair for development use
- [ ] Document cert generation in `README.md` (or create one)

**Acceptance criteria**: Agents can start with `AGENT_MTLS_ENABLED=true` using the generated dev certs; HTTPS endpoints respond to curl with the dev CA.

---

## Implementation Timeline Suggestion

| Sprint | Dates | Items | Deliverable |
|---|---|---|---|
| Sprint 1 | 2026-03-02 ~ 03-13 | P1 (KG construction + integration) | Working `kg_signal` dimension, real graph traversal |
| Sprint 2 | 2026-03-16 ~ 03-27 | P2 (CF model) + P3 (ST offline) | Pre-trained CF scores, reproducible offline embeddings |
| Sprint 3 | 2026-03-30 ~ 04-10 | P4 (ACS conformance) + P5 (ablation) | Valid system evaluation, conformance tests passing |
| Sprint 4 | 2026-04-13 ~ 04-24 | P6 (real baselines) + P7 (optional mTLS) | Publication-grade benchmark, demo hardening |
| Sprint 5 | 2026-04-27 ~ 05-08 | Paper writing + thesis defense | Thesis, presentation deck |

---

## Dependencies Map

```
P1 (KG — NetworkX local)
  └─► builds on: data/processed/goodreads/books_master.jsonl  ✅ exists
  └─► adds dependency: networkx (pip install)
  └─► enables: P5 (kg_signal non-trivial in ablation)

P2 (CF)
  └─► builds on: data/processed/goodreads/interactions_train.jsonl  ✅ exists
  └─► enables: P5 (pretrained CF scores used in ablation), P6 (real baseline comparison)

P3 (SentenceTransformer)
  └─► builds on: sentence-transformers package (pip install)
  └─► enables: P5 (semantic dimension non-trivial in ablation)

P4 (ACS conformance)
  └─► standalone, no hard dependencies
  └─► enables: eventual real service-registry integration

P5 (Ablation)
  └─► depends on: P2 (real CF needed for meaningful CF ablation)
  └─► depends on: P1 or P3 (at least one non-trivial dimension needed for delta to be measurable)

P6 (Baselines)
  └─► depends on: P2 (real popularity counts for traditional hybrid)

P7 (mTLS)
  └─► standalone, can be done any time
```
