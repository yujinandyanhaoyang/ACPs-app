# Rec Ranking Agent – Development Plan

## 1. Purpose & Scope
- Implements the "推荐决策智能体" from `plan.md` and `AGENT_SPEC.md`.
- Provides ACPs-compliant JSON-RPC handling for `StartTask`, `ContinueTask`, and `CancelTask`.
- Consumes fused profile/content signals and returns ranked recommendations with explanations and metric snapshots.

## 2. Functional Requirements
1. **Task handling**
   - Accept `profile_vector`, `content_vectors` (or `candidates`) and optional `svd_factors`, `constraints`, `scoring_weights`.
   - Return `AwaitingInput` when mandatory fields are missing.
2. **Multi-factor ranking**
   - Compute four-dimensional composite scores:
     - collaborative filtering (`ranking.svd`),
     - semantic similarity,
     - knowledge enhancement,
     - diversity bonus (`ranking.multifactor`).
   - Respect `top_k`, novelty threshold, and minimum new-item constraints when provided.
3. **Explanation generation**
   - Produce explanation bundle per ranked item (`explanation.llm`) using LLM path when API key exists, with deterministic fallback text otherwise.
4. **Monitoring outputs**
   - Return `outputs.metric_snapshot` containing diversity and novelty metrics.
   - Include diagnostics for latency, model/version, and environment health.

## 3. Deliverables (Current Iteration)
| Artifact | Path |
| --- | --- |
| Agent implementation | `agents/rec_ranking_agent/rec_ranking_agent.py` |
| Config sample | `agents/rec_ranking_agent/config.example.json` |
| Unit + E2E-style tests | `tests/test_rec_ranking_agent.py` |
| Live HTTP E2E skeleton | `tests/test_rec_ranking_agent_e2e.py` |

## 4. Implementation Steps
1. Scaffold module and ACPs router integration.
2. Implement payload parsing/merge/validation.
3. Implement four-factor scoring and ranking output assembly.
4. Implement explanation generation (LLM + fallback).
5. Implement metrics snapshot and diagnostics.
6. Code review for AGENT_SPEC compliance.
7. Add tests and run iterative pytest until stable.

## 5. Acceptance Checklist
- [ ] Returns ranked list with four-factor composite scores.
- [ ] Includes explanation bundle for each recommendation.
- [ ] Includes `outputs.metric_snapshot` with diversity/novelty indicators.
- [ ] Handles missing fields with `AwaitingInput`.
- [ ] All rec-ranking tests pass under pytest.
