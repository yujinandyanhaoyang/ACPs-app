# Phase IV Benchmark Report (Compact)

## Run Summary
- Generated at: 2026-03-01T14:16:54Z
- Case count: 8
- Winner method: multi_agent_proxy
- Winner objective score: 0.7388
- Method count: 4
- NDCG@k range across methods: 0.2500 ~ 0.7891 (span=0.5391)

## ACPs Quality
- Precision@k: 0.4167
- Recall@k: 0.6250
- NDCG@k: 0.5688

## ACPs Efficiency
- Latency mean (ms): 20361.1468

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
- Ranking quality is below target (NDCG@k=0.5688).
- Average latency is high (mean=20361.1468 ms).
- Fallback dependency is elevated (fallback_rate=0.2500).
- Strict-mode failures are notable (strict_failure_rate=0.1250).
- Remote success signal is limited (remote_success_rate=0.1250).

### Recommendations
- Prioritize scoring and candidate-quality optimization before deployment.
- Reduce model/runtime overhead or increase async parallelism to lower latency.
- Improve remote endpoint stability and discovery quality to reduce fallback frequency.
- Harden remote infra path (timeout/retry/availability checks) before strict-mode rollout.
- Add more remote-healthy scenarios to validate non-fallback execution confidence.

## Method Comparison
| Method | Objective | NDCG@k | Precision@k | Recall@k | Latency mean (ms) |
|---|---:|---:|---:|---:|---:|
| multi_agent_proxy | 0.7388 | 0.7891 | 0.5625 | 1.0000 | 23535.3034 |
| acps_multi_agent | 0.5002 | 0.5688 | 0.4167 | 0.6250 | 20361.1468 |
| traditional_hybrid | 0.2125 | 0.2500 | 0.0833 | 0.2500 | 1679.7912 |
| llm_only | 0.2083 | 0.2500 | 0.0833 | 0.2500 | 1567.0124 |
