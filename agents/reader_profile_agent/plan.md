# Reader Profile Agent – Development Plan

## 1. Purpose & Scope
- Implements the "用户画像分析智能体" from `plan.md`, responsible for translating user history and context into a normalized preference vector plus sentiment and cold-start heuristics.
- Exposes an ACPs-compliant JSON-RPC server (FastAPI + `acps_aip.aip_rpc_server`) to handle `StartTask`, `ContinueTask`, and `CompleteTask` lifecycle events initiated by the Reading Concierge.
- Reuses shared utilities (`base.py`, `acps_aip`) while keeping domain-specific logic in `agents/reader_profile_agent`.

## 2. Functional Requirements
1. **Task Handling**
   - Accept `StartTask` payloads containing `user_profile`, `history`, `reviews`, `scenario` metadata.
   - Produce outputs:
     - `preference_vector`: normalized weights for genre, theme, tone, pacing, difficulty, format, language.
     - `sentiment_summary`: aggregate sentiment + key phrases extracted via LLM helper.
     - `cold_start_hints`: fallback list when interaction data insufficient.
   - Support `AwaitingInput` when mandatory fields missing, otherwise mark `Completed`.
2. **Processing Pipeline**
   - Lightweight feature extractor using heuristics + optional embedding calls through `base.call_openai_chat` (mockable for tests).
   - Deterministic normalization to keep outputs consistent for unit tests.
3. **Observability**
   - Structured logging via `get_agent_logger`.
   - Diagnostics block with timing + data-quality notes.
4. **Configuration**
   - Reads environment variables (`PROFILE_EMBED_MODEL`, `DEFAULT_GENRE_PRIORS`, etc.) with sane fallbacks.
   - Loads ACS + mTLS configs from dedicated JSON files to be added later.

## 3. Deliverables This Iteration
| Artifact | Path |
| --- | --- |
| FastAPI service | `agents/reader_profile_agent/profile_agent.py` |
| Module init | `agents/reader_profile_agent/__init__.py` (optional placeholder) |
| Config sample | `agents/reader_profile_agent/config.example.json` (stubs for future use) |
| pytest module | `tests/test_reader_profile_agent.py` (unit tests using mock payloads) |
| Documentation | Update `WORKLOG_DEV.md` with progress |

## 4. Implementation Steps
1. **Skeleton Setup**
   - Create module files, copy structure from `beijing_catering` (router setup, task manager, FastAPI app).
   - Define Pydantic models for request/response payloads.
2. **Core Logic**
   - Implement `analyze_user_profile()` to compute preference scores and sentiment summary.
   - Integrate with `TaskManager` handler for `StartTask` → call analysis function, populate outputs, return `TaskState.Completed`.
3. **Testing**
   - Write unit tests that feed synthetic user histories and assert preference vector normalization + state transitions.
   - Mock `call_openai_chat` to avoid network calls.
4. **Run & Verify**
   - Execute pytest to ensure passing.
   - (Optional) launch FastAPI app locally for manual sanity.

## 5. Open Questions / Future Enhancements
- Hooking into actual embeddings/ML models once dataset preprocessing is ready.
- Extending diagnostics with feature importance and cold-start reasoning traces.
- Integrating with Knowledge Graph for richer attribute coverage.
