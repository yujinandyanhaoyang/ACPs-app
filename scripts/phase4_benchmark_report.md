# Phase IV Benchmark Report (Compact)

## Run Summary
- Generated at: 2026-04-06T04:02:45Z
- Case count: 40
- Winner method: acps_multi_agent
- Winner objective score: 0.6445
- Method count: 4
- NDCG@k range across methods: 0.5536 ~ 0.8629 (span=0.3093)

## ACPs Quality
- Precision@k: 0.1667
- Recall@k: 1.0000
- NDCG@k: 0.5795
- Explain coverage: 1.0000
- Intra-list diversity: 0.0000

## P2 Acceptance Gate
- Overall passed: False
- Precision@k: actual=0.1667, target=0.4000
- Recall@k: actual=1.0000, target=0.6000
- NDCG@k: actual=0.5795, target=0.6000
- Diversity: actual=1.0000, target=0.3500
- Novelty: actual=1.0000, target=0.3500

## ACPs Efficiency
- Latency mean (ms): 245.1429

## ACPs Reliability Dashboard
### Strict Mode
- Case count: 2
- Failure case count: 0
- Failure rate: 0.0000

### Fallback Mode
- Case count: 38
- Fallback observed case count: 0
- Fallback observed rate: 0.0000

### Overall
- Remote attempt rate: 0.0000
- Fallback rate: 0.0000
- Remote success rate: 0.0000
- Strict failure rate: 0.0000

## Findings & Recommendations
### Findings
- Ranking quality is below target (NDCG@k=0.5795).
- Latency is within current threshold (mean=245.1429 ms).
- Fallback dependency remains controlled (fallback_rate=0.0000).
- Strict-mode failure rate is low (strict_failure_rate=0.0000).
- Remote success signal is limited (remote_success_rate=0.0000).

### Recommendations
- Prioritize scoring and candidate-quality optimization before deployment.
- Add more remote-healthy scenarios to validate non-fallback execution confidence.

## Method Comparison
| Method | Objective | NDCG@k | Precision@k | Recall@k | Latency mean (ms) |
|---|---:|---:|---:|---:|---:|
| acps_multi_agent | 0.6445 | 0.5795 | 0.1667 | 1.0000 | 245.1429 |
| traditional_hybrid_cf_cb | 0.6109 | 0.8629 | 0.1667 | 1.0000 | 8611.5728 |
| macrec | 0.5353 | 0.8390 | 0.1667 | 1.0000 | 101.0508 |
| arag | 0.4854 | 0.5536 | 0.1667 | 1.0000 | 8097.5371 |
