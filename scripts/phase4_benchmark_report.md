# Phase IV Benchmark Report (Compact)

## Run Summary
- Generated at: 2026-02-19T13:42:32Z
- Case count: 8
- Winner method: traditional_hybrid
- Winner objective score: 0.7106

## ACPs Quality
- Precision@k: 0.5000
- Recall@k: 0.8750
- NDCG@k: 0.8188

## ACPs Efficiency
- Latency mean (ms): 8569.9303

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
- Ranking quality is strong (NDCG@k=0.8188).
- Average latency is high (mean=8569.9303 ms).
- Fallback dependency is elevated (fallback_rate=0.2500).
- Strict-mode failures are notable (strict_failure_rate=0.1250).
- Remote success signal is limited (remote_success_rate=0.1250).

### Recommendations
- Reduce model/runtime overhead or increase async parallelism to lower latency.
- Improve remote endpoint stability and discovery quality to reduce fallback frequency.
- Harden remote infra path (timeout/retry/availability checks) before strict-mode rollout.
- Add more remote-healthy scenarios to validate non-fallback execution confidence.
