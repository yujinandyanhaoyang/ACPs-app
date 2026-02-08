# ACPs Personalized Reading Recsys – Working Plan

## 1. Context Recap
- Goal: Build a multi-agent, ACPs-compliant personalized reading recommender by adapting the existing tourism-planning ACPs stack.
- Inputs: Prior analysis in README_DEVELOPER.md, strategic milestones in plan.md, reusable protocol/runtime assets across the repo.
- Constraints: Keep core tourism code untouched; do all new work under `ACPs-personalized-reading-recsys`.

## 2. Target Architecture
1. **Leader agent (Reading Concierge)**
   - FastAPI service orchestrating workflow, mirroring `tour_assistant` with domain-specific prompts.
   - Responsibilities: session mgmt, user intent parsing, partner dispatch, result synthesis, evaluation metrics logging.
2. **Partner agents** (initial set)
   - `reader_profile_agent`: builds user preference vectors, sentiment summaries, cold-start heuristics.
   - `book_content_agent`: enriches book metadata via knowledge graph hooks + NLP tagging.
   - `rec_ranking_agent`: fuses collaborative filtering, semantic similarity, and diversity scoring to output ranked lists with rationales.
   - Optional stubs for `data_curator_agent` (ETL/graph maintenance) and `evaluation_agent` (offline metrics) to keep architecture extensible.
3. **Shared ACPs runtime**
   - Reuse `acps_aip` RPC server/client, `base.call_openai_chat`, mTLS loader, logging helpers.
   - Standardize ACS descriptors for each agent + leader, enabling future registry integration.
4. **Pipelines & Storage**
   - Data preprocessing scripts (dataset ingest, knowledge graph export, vector store hydration).
   - Config-driven connectors for Goodreads/Amazon-like datasets.

## 3. Workstreams & Sequencing
| Phase | Focus | Key Tasks | Outputs |
| --- | --- | --- | --- |
| P1 | Environment + Scaffolding | Copy reusable runtime code, set up virtual env, baseline configs, stub services/tests | Shared libs, `.env.example`, stub FastAPI apps |
| P2 | Data Layer | Implement dataset loaders, preprocessing pipelines, graph schema adapters | `/data` scripts, processed samples, KG schema docs |
| P3 | Agent Implementations | Flesh out profile, content, ranking agents using ACPs handlers; unit tests per agent | Agent services + ACS JSON + pytest suites |
| P4 | Leader Orchestration | Adapt tourism leader logic for reading domain: prompts, dispatch rules, integration; add evaluation hooks | `reading_concierge` FastAPI app + scenario tests |
| P5 | End-to-End + Frontend | Minimal UI/API demo, e2e pytest harness, notebooks for analysis | `/web_app` variant, e2e results, demo instructions |
| P6 | Optimization & Research | Iterate on scoring, add knowledge graph RAG, measure metrics (Precision@k etc.), document findings | Metrics dashboard, ablation scripts |

## 4. Immediate Action Items (Next Sprint)
1. Mirror `base.py`, `acps_aip/`, and representative agent + leader directories into the new workspace for reference and reuse.
2. Define repo skeleton (`agents/`, `data/`, `services/`, `tests/`, `docs/`).
3. Draft ACS JSON templates and `.env.example` tailored to reading domain.
4. Specify dataset contract (fields required, preprocessing expectations) and document in `/docs/data-spec.md`.
5. Stand up pytest + lint config copied from existing repo.

## 5. Risks & Mitigations
- **Dataset licensing/availability**: Prepare fallback open datasets (e.g., Book-Crossing) and abstract loaders.
- **Model cost/latency**: Support local embeddings models via modular provider interface.
- **Protocol drift**: Keep ACPs message schemas identical to tourism stack; add smoke tests comparing enums/states.
- **Testing complexity**: Use synthetic fixtures to avoid heavy external calls in CI.

## 6. Success Criteria
- Feature parity with tourism leader regarding ACPs lifecycle, logging, and security.
- Reusable shared library powering both tourism and reading systems.
- Documented E2E demo capable of producing book recommendations with traceable agent reasoning.
- Clear roadmap for extending to production datasets and evaluation pipelines.
