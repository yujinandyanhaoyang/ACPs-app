# ACPs Compliance Gap Matrix (P0 Baseline)

Date: 2026-03-22
Scope: reading coordinator + 3 partner agents + web demo
Reference: ACPsProtocolGuide.md, AGENT_REDESIGN.md.md

## Summary
- Overall status: Partially compliant prototype.
- Main blockers: frontend-driven user context, missing persistent profile lifecycle, placeholder identity registration, incomplete official ACPs registration evidence, no formal local DB layer.

## Gap Matrix
| Domain | Current State | Gap | Severity | Required Fix | Validation Evidence |
| --- | --- | --- | --- | --- | --- |
| User profile acquisition | Frontend manually submits profile/history JSON | Violates agent-owned profiling lifecycle; no autonomous ingestion from interaction history | Critical | Move profile assembly into reader_profile_agent and ingest from platform interaction data | API accepts user_id + query only and reconstructs profile |
| User profile persistence | In-memory task context only in reader_profile_agent | No lifecycle management across restarts | Critical | Add persistent profile store with versioning and update strategy | DB records persisted and reused after restart |
| Book content agent alignment | Core vector/tag/KG path exists but contract not fully standardized to redesigned schema | Partial mismatch vs redesign contract and evidence fields | High | Normalize schema and enrich metadata lineage and fallback behavior | Contract tests and benchmark report pass |
| Ranking agent alignment | Multi-factor ranking exists but needs redesign-targeted constraints and explainability guarantees | Partial mismatch for scenario policy and strict explainability fields | High | Enforce scenario policy, factor trace, and deterministic fallback constraints | Ranking contract tests and explanation checks pass |
| AIC/ACS officialization | Uses local IDs and example ACS files | Not officially registered in ioa.pub with real AIC identities | Critical | Register all agents and replace placeholders with issued AIC values | Registry lookup and archived registration evidence |
| ATR/AIA trust chain | Local dev cert generation available | No evidence of official ATR issuance + production trust chain | Critical | Complete ATR issuance workflow and enforce mTLS in production mode | mTLS handshake matrix and cert inventory |
| ADP discovery | Auto-mode discovery hooks exist | Discovery readiness depends on real registry/discovery integration | Medium | Wire official endpoints and verify partner resolution | Discovery test report with resolved partners |
| AIP lifecycle conformance | Core AIP handling implemented | Need stricter conformance tests for all terminal states and edge transitions | Medium | Add state-machine conformance tests across leader/partners | Expanded AIP conformance tests pass |
| DSP synchronization | No explicit sync operation evidence package | Missing operational proof of ACS sync lifecycle | Medium | Add DSP sync runbook and verification checks | Sync logs and documented replay steps |
| Persistent database layer | Service logic mostly file/in-memory oriented | No formal database schema/migrations/repositories | Critical | Add DB engine, migrations, repositories, and backfill scripts | Migration + persistence integration tests pass |

## File-Level Baseline Findings
- Web demo requires manual profile/history input before request dispatch.
  - web_demo/index.html
- Coordinator request model still includes direct user_profile/history payload as primary path.
  - reading_concierge/reading_concierge.py
- Reader profile agent validates presence of user_profile and history/reviews and stores merged context in memory map.
  - agents/reader_profile_agent/profile_agent.py
- Book content and ranking agents contain substantial logic but need redesign-contracted schema tightening and standardized outputs.
  - agents/book_content_agent/book_content_agent.py
  - agents/rec_ranking_agent/rec_ranking_agent.py

## Phase Mapping
- P1 closes: user profile acquisition + persistence gaps.
- P2 closes: content/ranking redesign alignment gaps.
- P3 closes: AIC, ACS, ATR, AIA, ADP, DSP operationalization gaps.
- P4 closes: persistent DB foundation gaps.
- P5 closes: integration evidence and release readiness.

## Exit Conditions for P0
- Gap matrix reviewed and accepted.
- Baseline test and benchmark artifacts captured.
- P1 implementation tickets created directly from critical and high gaps.
