# ACPs Registration Evidence

This document tracks objective evidence for P3 (official registration and trust hardening).

## Evidence Status

- Current state: in progress
- Last updated: 2026-03-26
- Owner: engineering
- Status tags:
  - `PARTIAL_LOCAL_PLACEHOLDER`: ACS placeholders and local IDs/cert paths exist.
  - `READY_FOR_IOA_PUB`: submission package/runbook prepared.
  - `BLOCKED_BY_IOA_PUB`: official real AIC/cert/registry/discovery evidence.

## Agent Identity and ACS Evidence

| Agent | ACS File | Registry Registration | Registry Lookup Verified | Notes |
| --- | --- | --- | --- | --- |
| reading_concierge_001 | reading_concierge/reading_concierge.json | pending | pending | `PARTIAL_LOCAL_PLACEHOLDER` |
| reader_profile_agent_001 | partners/online/reader_profile_agent/acs.json | pending | pending | `PARTIAL_LOCAL_PLACEHOLDER` |
| book_content_agent_001 | partners/online/book_content_agent/acs.json | pending | pending | `PARTIAL_LOCAL_PLACEHOLDER` |
| rec_ranking_agent_001 | partners/online/rec_ranking_agent/acs.json | pending | pending | `PARTIAL_LOCAL_PLACEHOLDER` |

## Trust Material Evidence (ATR/AIA)

| Item | Status | Evidence Reference |
| --- | --- | --- |
| ATR issuance for all agents | pending | to be attached |
| mTLS cert-chain validation | local dev complete, production pending | cert generation logs + production evidence pending |
| AIA mutual-auth handshake across all RPC links | pending | to be attached |

## Discovery and ADP Mode

- Selected mode: `Mode B` (approved static endpoint binding in runtime)
- Mode evidence: runtime diagnostics expose `adp_mode=Mode B` and `adp_discovery_enabled` in `/demo/status`
- Discovery verification output: local runtime verified; production ADP endpoint verification pending

## AIP Conformance Evidence

- Local command/state conformance tests: implemented
- Test file: `tests/test_aip_conformance.py`
- Current result: `DONE (local)` for local unit-level conformance

## Open Gaps

1. Replace placeholder local AIC values with officially registered ioa.pub identities.
2. Archive registry responses and lookup outputs.
3. Capture production-grade mTLS handshake evidence across all inter-agent calls.
4. Finalize ADP operating mode declaration and verification artifact.
