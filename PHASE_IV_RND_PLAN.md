# Phase (IV) R&D Plan

## 0) Scope and objective
- Objective: deliver a complete, demo-ready ACPs-based multi-agent book recommendation prototype and then optimize it by measurable metrics.
- Workflow constraint: strictly execute `Plan → Code → Code Review → Test → Feedback → Update → Matching Requirements`.
- Baseline reference: existing coordinator + 3 partner agents + evaluation block in `/user_api`.

## 1) Definition of done for Phase (IV)
1. **Prototype completeness**
   - End-to-end flow is reproducible (cold/warm/explore scenarios).
   - Remote/local partner routing remains stable and observable.
2. **Metrics-driven optimization loop**
   - Batch evaluation produces aggregate `Precision@k`, `Recall@k`, `NDCG@k`, diversity, novelty, success-rate, latency stats.
   - Weight-search or policy-search can suggest improved ranking settings.
3. **Engineering quality**
   - Targeted tests pass and include optimization-path coverage.
   - Demo script and optimization script are executable and documented.

## 2) Execution plan (required workflow)

### A. Plan
- A1. Finalize benchmark case format and objective function.
- A2. Freeze metric schema for both per-case and aggregate outputs.
- A3. Define optimization search space for ranking weights and constraints.

### B. Code
- B1. Build `services/phase4_optimizer.py`:
  - aggregate metrics helper;
  - weighted objective scorer;
  - best-config selector over experiment runs.
- B2. Build `scripts/phase4_optimize.py`:
  - run benchmark scenarios against `reading_concierge`;
  - evaluate candidate weight sets;
  - export report JSON with best config and leaderboard.
- B3. Add scenario fixture `scripts/phase4_cases.json` for reproducible runs.

### C. Code Review
- C1. Static diagnostics on changed files.
- C2. Verify typing consistency and fallback behavior.
- C3. Confirm no breaking API changes for existing tests.

### D. Test
- D1. Add `tests/test_phase4_optimizer.py` for aggregator/objective/selector.
- D2. Run focused pytest suite for new modules and coordinator integration compatibility.

### E. Feedback
- E1. Compare best config vs baseline config (delta by key metrics).
- E2. Identify bottlenecks (accuracy vs diversity trade-off; latency impact).

### F. Update
- F1. Update scripts/report format and defaults based on feedback.
- F2. Update `WORKLOG_DEV.md` with exact outcomes.

### G. Matching Requirements
- G1. Map outputs to PLAN.md Phase (IV) items:
  - unit/integration testability,
  - system evaluation,
  - ablation/optimization readiness,
  - demo reproducibility.

## 3) Immediate iteration target (this development pass)
- Deliver B1 + B2 + B3 + D1 and run focused tests.
- Keep modifications minimal and compatible with current architecture.

## 4) Risks and mitigations
- Risk: overfitting to tiny synthetic cases.
  - Mitigation: keep multiple scenarios and report per-scenario metrics.
- Risk: optimization objective may bias novelty over relevance.
  - Mitigation: configurable objective coefficients.
- Risk: remote mode instability affects reproducibility.
  - Mitigation: default local ASGI execution for optimization script.
