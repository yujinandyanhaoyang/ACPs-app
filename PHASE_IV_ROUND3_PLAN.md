# Phase (IV) Round-3 Plan (Remote E2E Reliability First)

## Goal
Complete the next high-priority gap in PLAN.md Phase (IV) by prioritizing remote E2E reliability and observability while preserving the current safe fallback behavior.

## Confirmed Scope Decisions
- Priority: **Remote E2E first**
- Data strategy: **Keep synthetic benchmark cases** for this round
- Remote behavior: **Keep local fallback enabled** when remote partner invocation fails

## Required Workflow
This round is executed strictly as:
`Plan → Code → Code Review → Test → Feedback → Update → Matching Requirements`

## 1) Plan
1. Define Round-3 acceptance criteria around remote routing transparency:
   - each partner call must expose route provenance (`remote` / `local_fallback` / `local`),
   - benchmark outputs must summarize fallback frequency.
2. Keep existing benchmark/optimization pipelines reusable; avoid architectural rewrites.
3. Keep backward compatibility with current `/user_api` response structure and tests.

## 2) Code
1. Update coordinator observability in `reading_concierge/reading_concierge.py`:
   - preserve fallback-safe partner invocation,
   - add explicit route outcome metadata for each partner task/result.
2. Extend benchmark runner in `scripts/phase4_benchmark_compare.py`:
   - collect route provenance and fallback counters per case/method.
3. Keep synthetic scenario coverage in `scripts/phase4_cases.json` and add one remote-stress synthetic case if needed.

## 3) Code Review
1. Static diagnostics on changed files.
2. Verify no breaking API behavior for existing coordinator and benchmark flows.
3. Confirm fallback-safe behavior remains default.

## 4) Test
1. Extend `tests/test_reading_concierge.py` for route provenance + fallback observability assertions.
2. Extend `tests/test_phase4_benchmark.py` for aggregate route/fallback reporting checks.
3. Run focused regression:
   - `tests/test_reading_concierge.py`
   - `tests/test_phase4_benchmark.py`
   - `tests/test_phase4_optimizer.py`

## 5) Feedback
1. Compare remote-attempt vs fallback outcomes from benchmark output.
2. Identify highest-frequency fallback causes and prioritize next hardening target.

## 6) Update
1. Update `WORKLOG_DEV.md` with full round cycle evidence.
2. Keep scripts and report schema reusable for subsequent rounds.

## 7) Matching Requirements (PLAN.md Phase IV)
- 单体测试: extend unit-level checks for benchmark aggregation fields.
- 集成测试: strengthen coordinator remote-lane observability checks.
- 系统评估: keep quality metrics and add route/fallback evidence in report outputs.
- 消融研究: retain existing ablation foundation; no regression in this round.
- 对标测试: preserve Round-2 baseline lane and augment with route reliability signals.
- 演示系统: improve demo trustworthiness via traceable remote/fallback execution details.

## Deliverables
- `PHASE_IV_ROUND3_PLAN.md` (this document)
- Updated coordinator and benchmark reporting for route/fallback observability
- Updated tests + passing focused regression results
- Worklog entry mapped to required workflow and PLAN.md requirements
