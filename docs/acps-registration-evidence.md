# ACPs Registration Evidence

This document tracks objective evidence for P3 (official registration and trust hardening).

## Evidence Status

- Current state: in progress
- Last updated: 2026-03-27
- Owner: engineering
- Status tags:
  - `PARTIAL_LOCAL_PLACEHOLDER`: ACS placeholders and local IDs/cert paths exist.
  - `READY_FOR_IOA_PUB`: submission package/runbook prepared.
  - `BLOCKED_BY_IOA_PUB`: official real AIC/cert/registry/discovery evidence.

## Agent Identity and ACS Evidence

| Agent | ACS File | Registry Registration | Registry Lookup Verified | Notes |
| --- | --- | --- | --- | --- |
| 1.2.156.3088.0001.00001.U3IBA8.JI874M.1.03Y1 | reading_concierge/reading_concierge.json | completed | pending | `DONE (local)` |
| 1.2.156.3088.0001.00001.FRMFWE.LBOY6M.1.1EGZ | partners/online/reader_profile_agent/acs.json | completed | pending | `DONE (local)` |
| 1.2.156.3088.0001.00001.BPRK2Q.JLWHSY.1.06P9 | partners/online/book_content_agent/acs.json | completed | pending | `DONE (local)` |
| 1.2.156.3088.0001.00001.09RLA8.91R7Z2.1.01CM | partners/online/rec_ranking_agent/acs.json | completed | pending | `DONE (local)` |

## Trust Material Evidence (ATR/AIA)

| Item | Status | Evidence Reference |
| --- | --- | --- |
| ATR issuance for all agents | `READY_FOR_IOA_PUB` | `scripts/phase3_issue_real_certs.sh` |
| mTLS cert-chain validation | local dev complete, production pending | cert generation logs + production evidence pending |
| AIA mutual-auth handshake across all RPC links | `READY_FOR_IOA_PUB` | run mTLS startup + e2e calls after official cert issuance |

## Discovery and ADP Mode

- Selected mode: `Mode B` (approved static endpoint binding in runtime)
- Mode evidence: runtime diagnostics expose `adp_mode=Mode B` and `adp_discovery_enabled` in `/demo/status`
- Discovery verification output: local runtime verified; production ADP endpoint verification pending
- DSP sync execution helper: `scripts/phase3_dsp_sync_verify.sh` (`READY_FOR_IOA_PUB`)

## AIP Conformance Evidence

- Local command/state conformance tests: implemented
- Test file: `tests/test_aip_conformance.py`
- Current result: `DONE (local)` for local unit-level conformance

## Open Gaps

1. Archive registry responses and lookup outputs.
2. Capture production-grade mTLS handshake evidence across all inter-agent calls.
3. Finalize ADP operating mode declaration and verification artifact.

## Command Checklist (ACPsProtocolGuide-Aligned)

1. Install real CA client (official package) and run:
   - `bash scripts/phase3_issue_real_certs.sh`
2. Enable mTLS and validate AIA paths end-to-end.
3. Trigger DSP sync + ADP verification:
   - `bash scripts/phase3_dsp_sync_verify.sh`
4. Attach generated artifacts from `artifacts/phase3/` to this document.
