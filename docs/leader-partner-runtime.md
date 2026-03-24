# Leader-Partner Runtime Flow (P0 Freeze)

## Purpose
This document freezes runtime behavior for the ACPs personalized reading system before broad P1/P2 implementation.

## Runtime Roles
- Leader: `reading_concierge`
- Partner A: `reader_profile_agent`
- Partner B: `book_content_agent`
- Partner C: `rec_ranking_agent`

## Interaction Mode
- Default mode: AIP Direct Connection Mode
- Leader dispatches point-to-point partner calls with explicit task/session identities.

## Production API Boundary
- Production input: `user_id` + `query`
- Manual `user_profile/history/reviews` injection is debug-only and must be explicitly enabled.

## Authoritative Candidate Ownership (P0 Decision)
- Owner: Leader (`reading_concierge`)
- Candidate source: local retrieval pipeline using `services/book_retrieval.py`
- Candidate policy:
  - Use lexical retrieval over active corpus.
  - Prefer CF-covered items where available.
  - Select top-k candidate IDs via deterministic fallback plus optional LLM refinement.
  - Persist candidate provenance for audit.

## Chain of Execution
1. Client submits `user_id`, `query`, and optional constraints.
2. Leader loads persisted profile/event context for user.
3. Leader resolves scenario policy (`cold`, `warm`, `explore`).
4. Leader assembles candidate set and provenance.
5. Leader sends Start to Partner A with profile context payload.
6. Partner A returns `UserProfileJSON` product.
7. Leader sends Start to Partner B with candidate set payload.
8. Partner B returns `BookFeatureMapJSON` product.
9. Leader sends Start to Partner C with profile + features + policy payload.
10. Partner C returns `RankedRecommendationListJSON` product.
11. Leader finalizes response and persists run evidence.

## AIP Command and State Requirements
- Commands: `Start`, `Get`, `Complete`, `Cancel`
- Required states: `Accepted`, `Working`, `AwaitingInput`, `AwaitingCompletion`, `Completed`
- Error terminal states: `Failed`, `Canceled`, `Rejected`

## Identity and Traceability Fields
Every chain must preserve and validate:
- `taskId`
- `sessionId`
- `senderId`
- product payload lineage

## Debug Shortcuts (Allowed but Isolated)
- Debug payload override flag: `constraints.debug_payload_override = true`
- If flag is false, Leader ignores manual profile/history/reviews payloads and uses persisted user context.
- Debug path must not be the default UI or default API behavior.

## P0 Freeze Acceptance
- Leader/Partner chain approved.
- Candidate ownership and policy approved.
- Contract schemas aligned with this runtime flow.
