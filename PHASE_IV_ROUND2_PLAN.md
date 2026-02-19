# Phase (IV) Round-2 Plan (Detailed)

## Goal
Complete the remaining high-priority tasks in PLAN.md Phase (IV):
- 对标测试（traditional hybrid / multi-agent-style proxy baselines）
- stronger system evaluation coverage and comparable optimization outputs
- demo-ready reproducible benchmark report artifact

## Required Workflow
This round is executed strictly as:
`Plan → Code → Code Review → Test → Feedback → Update → Matching Requirements`

## 1) Plan
1. Define baseline methods for benchmarking:
   - `traditional_hybrid` (content + popularity + history overlap)
   - `multi_agent_proxy` (diversity-aware policy proxy for MACRec/ARAG-style comparison lane)
2. Define unified benchmark report schema:
   - per-method per-case metrics,
   - aggregate metrics,
   - objective score,
   - method ranking table.
3. Expand benchmark cases to improve scenario coverage across cold/warm/explore.

## 2) Code
1. Add `services/baseline_rankers.py`:
   - canonical candidate normalization,
   - two baseline rankers returning ranked items with score parts.
2. Add `services/phase4_benchmark.py`:
   - metric computation wrapper,
   - per-method aggregation,
   - method ranking helper.
3. Add `scripts/phase4_benchmark_compare.py`:
   - run ACPs method through coordinator,
   - run baselines locally,
   - output benchmark comparison JSON report.
4. Update `scripts/phase4_cases.json` with additional representative cases.

## 3) Code Review
1. Static diagnostics for new/updated files.
2. Validate no breaking changes to existing API/test assumptions.
3. Confirm fallback-safe behavior for missing fields in cases.

## 4) Test
1. Add `tests/test_baseline_rankers.py`.
2. Add `tests/test_phase4_benchmark.py`.
3. Run focused regression: new tests + existing coordinator tests.

## 5) Feedback
1. Compare ACPs vs baselines on aggregate metrics and objective score.
2. Identify where ACPs underperforms/overperforms and next tuning targets.

## 6) Update
1. Update worklog with complete round-2 cycle evidence.
2. Keep benchmark scripts reusable for future phase iterations.

## 7) Matching Requirements (PLAN.md Phase IV)
- 单体测试: add unit tests for baseline/benchmark services.
- 集成测试: retain coordinator regression.
- 系统评估: benchmark report includes Precision/Recall/NDCG/diversity/novelty/latency.
- 消融研究: keep prior ablation path; benchmark output references it.
- 对标测试: deliver ACPs vs baseline comparison pipeline.
- 演示系统: benchmark report artifact + runnable scripts for demo.
