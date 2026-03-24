# Profile Lifecycle (P1 Start)

## Scope
This document defines the initial P1 implementation for profile lifecycle behavior in the reading system.

## Production Input Boundary
- Production endpoint: /user_api
- Required request fields: user_id, query
- Manual profile/history/reviews injection is only allowed through explicit debug override behavior.

## Lifecycle Modes
- bootstrap:
  - Triggered when scenario is cold or no historical signals are available.
  - Uses priors and query/review heuristics to build a valid profile snapshot.
- incremental:
  - Triggered when history/reviews exist or a previous profile_version is provided.
  - Updates preferences using recency-weighted event signals.

## Ingestion Adapters (Current)
The reader profile pipeline accepts the following normalized sources from payload context:
- user basic info: user_profile
- ratings/history events: history entries with rating/title/genres/language/format
- browse-like signals: history entries without strong rating signal but with metadata fields
- review text: reviews entries with text and optional rating

## Decay and Weighting
- Strategy ID: recency_weighted_v1
- Event score combines:
  - rating strength (default fallback if absent)
  - sequence recency (newer events weighted higher)
  - time decay (exponential attenuation for old timestamps)

## Persisted Snapshot Contract
Each profile snapshot saved by the leader contains:
- user_id
- profile_version
- generated_at
- source_event_window
- explicit_preferences
- implicit_preferences
- sentiment_summary
- feature_vector
- cold_start_flag
- lifecycle metadata

## Versioning
- Profile versions follow <user_id>-vN.
- The leader enforces monotonic progression based on latest persisted snapshot.
- Recommendation runs reference the persisted profile_version used during orchestration.
