# Book Content Agent – Development Plan

## 1. Purpose & Scope
- Implements the "图书内容分析智能体" from `plan.md` and `AGENT_SPEC.md`.
- Provides ACPs-compliant JSON-RPC handling for `StartTask`, `ContinueTask`, and `CancelTask`.
- Converts candidate book payloads into structured outputs for downstream ranking:
  - semantic content vectors (Sentence-BERT placeholder),
  - multi-dimensional tags (topic/style/difficulty/mood/diversity),
  - knowledge-graph trace references (`kg_refs`).

## 2. Functional Requirements
1. **Task handling**
   - Accept payload with `candidate_ids` or `books` or `ingest_batch_id`.
   - Require `kg_endpoint` only when remote KG retrieval is requested (`use_remote_kg=true`).
   - Return `AwaitingInput` when required fields are missing; otherwise finish with `Completed` and products.
2. **Content analysis pipeline**
   - Deterministic vectorization placeholder (`book.vectorize`) to keep tests reproducible.
   - Heuristic tag extraction (`tag.extract`) from metadata/reviews.
   - Optional LLM enrichment (`OPENAI_API_KEY` present) for latent tags/intents.
3. **Knowledge-graph enrichment**
   - Build `kg_refs` from provided IDs/edges; generate endpoint trace refs when remote KG mode is enabled (`kg.enrich`).
4. **Observability & protocol fit**
   - Structured diagnostics: latency, counts, API-key presence, model/version.
   - ACPs product format with one structured data item and one text summary item.

## 3. Deliverables (Current Iteration)
| Artifact | Path |
| --- | --- |
| Agent implementation | `agents/book_content_agent/book_content_agent.py` |
| Config sample | `agents/book_content_agent/config.example.json` |
| Unit + local E2E-like tests | `tests/test_book_content_agent.py` |
| Live HTTP E2E skeleton (optional run) | `tests/test_book_content_agent_e2e.py` |

## 4. Implementation Steps
1. Scaffold module and ACPs router integration.
2. Implement payload parsing/merge/validation with clear missing-field responses.
3. Implement vectorization, tag extraction, and KG reference enrichment.
4. Implement start/continue/cancel handlers and task finalization.
5. Self-review for AGENT_SPEC compliance (`book.vectorize`, `kg.enrich`, `tag.extract`, `kg_refs` outputs).
6. Add tests for missing input, normal completion, continue recovery, and API-key/LLM path.
7. Run pytest; iterate until green.

## 5. Acceptance Checklist
- [ ] Returns `Completed` with structured outputs for valid payloads.
- [ ] Returns `AwaitingInput` when mandatory payload fields are absent.
- [ ] Exposes `kg_refs` and content vectors in output payload.
- [ ] Tests pass with deterministic behavior and external-model path coverage.
