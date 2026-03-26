# ACPs Agent Registration Runbook (ioa.pub)

This runbook defines the reproducible process for registering the reading recommender agents in the ioa.pub registry.

## Scope

- Leader: `reading_concierge_001`
- Partner A: `reader_profile_agent_001`
- Partner B: `book_content_agent_001`
- Partner C: `rec_ranking_agent_001`

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
