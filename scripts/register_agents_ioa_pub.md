# ACPs Agent Registration Runbook (ioa.pub)

This runbook defines the reproducible process for registering the reading recommender agents in the ioa.pub registry.

## Scope

- Leader: `1.2.156.3088.0001.00001.U3IBA8.JI874M.1.03Y1`
- Partner A: `1.2.156.3088.0001.00001.FRMFWE.LBOY6M.1.1EGZ`
- Partner B: `1.2.156.3088.0001.00001.BPRK2Q.JLWHSY.1.06P9`
- Partner C: `1.2.156.3088.0001.00001.09RLA8.91R7Z2.1.01CM`

## Inputs

- ACS descriptors:
  - `reading_concierge/reading_concierge.json`
  - `partners/online/reader_profile_agent/acs.json`
  - `partners/online/book_content_agent/acs.json`
  - `partners/online/rec_ranking_agent/acs.json`
- ATR-issued identity and trust material for each agent
- Registry account and API credentials for ioa.pub

## Preflight Checklist

- Confirm each ACS JSON has non-empty `aic`, `protocolVersion`, `skills`, and `endPoints`.
- Confirm endpoint URLs in ACS match deployed runtime URLs.
- Confirm certificates and ACS subject binding are consistent.
- Confirm all agents pass local `/acs` conformance tests.

## Registration Steps

1. Authenticate to ioa.pub registry with the project service account.
2. Register Leader ACS descriptor.
3. Register Partner A ACS descriptor.
4. Register Partner B ACS descriptor.
5. Register Partner C ACS descriptor.
6. Capture the registry response for each registration.
7. Verify registry lookup for each `aic` returns the expected ACS payload.
8. Verify ADP discovery response includes all intended endpoints.

## Post-Registration Validation

1. Run mTLS-only startup for all services.
2. Execute an end-to-end recommendation request.
3. Validate AIP identity lineage fields in logs:
   - `taskId`
   - `sessionId`
   - `senderId`
4. Save evidence links and command output hashes in `docs/acps-registration-evidence.md`.

## ATR/AIA Certificate Issuance (Real CA-Client)

Follow ACPsProtocolGuide Step 2.4 with the official CA client:

```bash
source .venv/bin/activate
pip install acps_ca_client-2.0.0-py3-none-any.whl
export CHALLENGE_SERVER_BASE_URL=http://<your-ip>:8004/acps-atr-v2
bash scripts/phase3_issue_real_certs.sh
```

After issuance:
- move or map generated cert/key assets into production cert inventory.
- update ACS trust status fields (`x_ioa_pub_cert_status`) from placeholder to official status.
- record issuance log path under evidence.

## DSP Sync Verification

Run DSP-trigger + ADP search verification according to ACPsProtocolGuide Step 5:

```bash
export DISCOVERY_BASE_URL=http://<discovery-host>:8005
bash scripts/phase3_dsp_sync_verify.sh
```

Expected evidence output:
- `artifacts/phase3/dsp-sync-*.json`
- `artifacts/phase3/adp-search-*.json`
- `artifacts/phase3/dsp-adp-summary-*.json`

## Evidence Capture Template

- Registry environment:
- Registration timestamp:
- Operator:
- Agent registrations:
  - Leader: request id / response id / lookup id
  - Partner A: request id / response id / lookup id
  - Partner B: request id / response id / lookup id
  - Partner C: request id / response id / lookup id
- ADP mode declaration (`Mode A` or `Mode B`):
- mTLS validation result:
- E2E AIP chain validation result:

## Notes

- Keep private keys outside repository and never include them in evidence files.
- If registry metadata and runtime metadata diverge, fail the deployment and re-register.
