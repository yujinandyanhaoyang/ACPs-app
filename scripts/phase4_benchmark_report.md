# Phase IV Benchmark Report (Compact)

## Run Summary
- Generated at: 2026-02-25T11:27:18Z
- Case count: 8
- Winner method: multi_agent_proxy
- Winner objective score: 0.7330
- Method count: 4
- NDCG@k range across methods: 0.2500 ~ 0.7727 (span=0.5227)

## ACPs Quality
- Precision@k: 0.4167
- Recall@k: 0.6250
- NDCG@k: 0.5688

## ACPs Efficiency
- Latency mean (ms): 3091.5268

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
- Latency is within current threshold (mean=3091.5268 ms).
- Fallback dependency is elevated (fallback_rate=0.2500).
- Strict-mode failures are notable (strict_failure_rate=0.1250).
- Remote success signal is limited (remote_success_rate=0.1250).

### Recommendations
- Prioritize scoring and candidate-quality optimization before deployment.
- Improve remote endpoint stability and discovery quality to reduce fallback frequency.
- Harden remote infra path (timeout/retry/availability checks) before strict-mode rollout.
- Add more remote-healthy scenarios to validate non-fallback execution confidence.

## Method Comparison
| Method | Objective | NDCG@k | Precision@k | Recall@k | Latency mean (ms) |
|---|---:|---:|---:|---:|---:|
| multi_agent_proxy | 0.7330 | 0.7727 | 0.5625 | 1.0000 | 2560.9052 |
| acps_multi_agent | 0.5002 | 0.5688 | 0.4167 | 0.6250 | 3091.5268 |
| traditional_hybrid | 0.2145 | 0.2500 | 0.0833 | 0.2500 | 192.2386 |
| llm_only | 0.2083 | 0.2500 | 0.0833 | 0.2500 | 193.7028 |
