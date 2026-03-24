# Execution TODO (Phase 4)

Date: 2026-03-23
Purpose: Personal step-by-step execution list aligned with UPDATEPLAN section 4.

## Active Queue
- [x] 1. Baseline phase status reconciliation
- [x] 2. Complete WS-A adapter hardening (dedupe + normalization rules)
- [x] 3. Implement WS-B content redesign
- [ ] 4. Implement WS-B ranking redesign
- [ ] 5. Add P2 contract acceptance tests
- [ ] 6. Define benchmark thresholds document
- [ ] 7. Scaffold WS-C registration artifacts
- [ ] 8. Prepare WS-D migration skeleton

## Notes
- Treat `services/user_profile_store.py` as stepping-stone storage until WS-D migration/repository refactor.
- Enforce user_id-only replay behavior through leader-side DB event reconstruction tests.
