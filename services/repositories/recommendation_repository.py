from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services.db import transaction, utc_now
from .profile_repository import ProfileRepository


class RecommendationRepository:
    def __init__(self, db_url: Optional[str] = None) -> None:
        self.db_url = db_url
        self.profile_repo = ProfileRepository(db_url=db_url)

    def create_recommendation_run(
        self,
        *,
        run_id: str,
        user_id: str,
        query: str,
        profile_version: Optional[str],
        candidate_set_version_or_hash: Optional[str],
        candidate_provenance: Optional[Dict[str, Any]],
        book_feature_version_or_hash: Optional[str],
        ranking_policy_version: Optional[str],
        weights_or_policy_snapshot: Optional[Dict[str, Any]],
        run_timestamp: Optional[str] = None,
    ) -> None:
        if not str(run_id or "").strip() or not str(user_id or "").strip() or not str(query or "").strip():
            return
        self.profile_repo.upsert_user(user_id)
        now = utc_now()
        with transaction(self.db_url) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO recommendation_runs (
                    run_id,
                    user_id,
                    query,
                    profile_version,
                    candidate_set_version_or_hash,
                    candidate_provenance_json,
                    book_feature_version_or_hash,
                    ranking_policy_version,
                    weights_or_policy_snapshot_json,
                    run_timestamp,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    user_id,
                    query,
                    profile_version,
                    candidate_set_version_or_hash,
                    json.dumps(candidate_provenance or {}, ensure_ascii=False),
                    book_feature_version_or_hash,
                    ranking_policy_version,
                    json.dumps(weights_or_policy_snapshot or {}, ensure_ascii=False),
                    run_timestamp or now,
                    now,
                ),
            )

    def save_recommendations(
        self,
        *,
        run_id: str,
        recommendations: List[Dict[str, Any]],
        scenario_policy: Optional[str] = None,
    ) -> None:
        if not str(run_id or "").strip() or not isinstance(recommendations, list):
            return
        now = utc_now()
        with transaction(self.db_url) as conn:
            conn.execute("DELETE FROM recommendations WHERE run_id = ?", (run_id,))
            for idx, row in enumerate(recommendations, start=1):
                if not isinstance(row, dict):
                    continue
                book_id = str(row.get("book_id") or "").strip()
                if not book_id:
                    continue
                evidence_refs = row.get("explanation_evidence_refs")
                if not isinstance(evidence_refs, list):
                    evidence_refs = []
                rank_position = int(row.get("rank_position") or row.get("rank") or idx)
                conn.execute(
                    """
                    INSERT INTO recommendations (
                        run_id,
                        rank_position,
                        book_id,
                        score_total,
                        score_cf,
                        score_content,
                        score_kg,
                        score_diversity,
                        scenario_policy,
                        explanation,
                        explanation_evidence_refs_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        rank_position,
                        book_id,
                        float(row.get("score_total") or 0.0),
                        float(row.get("score_cf") or 0.0),
                        float(row.get("score_content") or 0.0),
                        float(row.get("score_kg") or 0.0),
                        float(row.get("score_diversity") or 0.0),
                        str(row.get("scenario_policy") or scenario_policy or "unknown"),
                        str(row.get("explanation") or ""),
                        json.dumps(evidence_refs, ensure_ascii=False),
                        now,
                    ),
                )
