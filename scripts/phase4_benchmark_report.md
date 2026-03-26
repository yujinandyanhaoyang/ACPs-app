# Phase IV Benchmark Report (Compact)

## Run Summary
- Generated at: 2026-03-25T13:53:43Z
- Case count: 8
- Winner method: acps_multi_agent
- Winner objective score: 0.6574
- Method count: 4
- NDCG@k range across methods: 0.2500 ~ 0.7891 (span=0.5391)

## ACPs Quality
- Precision@k: 0.5000
- Recall@k: 0.8750
- NDCG@k: 0.7727

## P2 Acceptance Gate
- Overall passed: True
- Precision@k: actual=0.5000, target=0.4000
- Recall@k: actual=0.8750, target=0.6000
- NDCG@k: actual=0.7727, target=0.6000
- Diversity: actual=0.4340, target=0.3500
- Novelty: actual=0.4354, target=0.3500

## ACPs Efficiency
- Latency mean (ms): 106398.1120

## ACPs Reliability Dashboard
### Strict Mode
- Case count: 1
- Failure case count: 1
- Failure rate: 1.0000

### Fallback Mode
- Case count: 7
- Fallback observed case count: 2
- Fallback observed rate: 0.2857

### Overall
- Remote attempt rate: 0.3750
- Fallback rate: 0.2500
- Remote success rate: 0.1250
- Strict failure rate: 0.1250

## Findings & Recommendations
### Findings
- Ranking quality is acceptable but improvable (NDCG@k=0.7727).
- Average latency is high (mean=106398.1120 ms).
- Fallback dependency is elevated (fallback_rate=0.2500).
- Strict-mode failures are notable (strict_failure_rate=0.1250).
- Remote success signal is limited (remote_success_rate=0.1250).

### Recommendations
- Tune semantic/collaborative weights for marginal quality gains.
- Reduce model/runtime overhead or increase async parallelism to lower latency.
- Improve remote endpoint stability and discovery quality to reduce fallback frequency.
- Harden remote infra path (timeout/retry/availability checks) before strict-mode rollout.
- Add more remote-healthy scenarios to validate non-fallback execution confidence.

## Method Comparison
| Method | Objective | NDCG@k | Precision@k | Recall@k | Latency mean (ms) |
|---|---:|---:|---:|---:|---:|
| acps_multi_agent | 0.6574 | 0.7727 | 0.5000 | 0.8750 | 106398.1120 |
| multi_agent_proxy | 0.6168 | 0.7891 | 0.5625 | 1.0000 | 146213.1353 |
| traditional_hybrid | 0.2125 | 0.2500 | 0.0833 | 0.2500 | 33096.3607 |
| llm_only | 0.2083 | 0.2500 | 0.0833 | 0.2500 | 33058.9575 |
