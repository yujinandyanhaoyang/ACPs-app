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

    def list_recommendation_runs(self, *, user_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        query = """
            SELECT
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
            FROM recommendation_runs
        """
        params: List[Any] = []
        if str(user_id or "").strip():
            query += " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY run_timestamp DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with transaction(self.db_url) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        result: List[Dict[str, Any]] = []
        for row in rows:
            try:
                candidate_provenance = json.loads(row["candidate_provenance_json"] or "{}")
            except Exception:
                candidate_provenance = {}
            try:
                policy_snapshot = json.loads(row["weights_or_policy_snapshot_json"] or "{}")
            except Exception:
                policy_snapshot = {}
            result.append(
                {
                    "run_id": row["run_id"],
                    "user_id": row["user_id"],
                    "query": row["query"],
                    "profile_version": row["profile_version"],
                    "candidate_set_version_or_hash": row["candidate_set_version_or_hash"],
                    "candidate_provenance": candidate_provenance,
                    "book_feature_version_or_hash": row["book_feature_version_or_hash"],
                    "ranking_policy_version": row["ranking_policy_version"],
                    "weights_or_policy_snapshot": policy_snapshot,
                    "run_timestamp": row["run_timestamp"],
                    "created_at": row["created_at"],
                }
            )
        return result

    def get_run_with_recommendations(self, run_id: str) -> Dict[str, Any]:
        if not str(run_id or "").strip():
            return {}
        with transaction(self.db_url) as conn:
            run_row = conn.execute(
                """
                SELECT
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
                FROM recommendation_runs
                WHERE run_id = ?
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            rec_rows = conn.execute(
                """
                SELECT
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
                FROM recommendations
                WHERE run_id = ?
                ORDER BY rank_position ASC
                """,
                (run_id,),
            ).fetchall()
        if not run_row:
            return {}

        try:
            candidate_provenance = json.loads(run_row["candidate_provenance_json"] or "{}")
        except Exception:
            candidate_provenance = {}
        try:
            policy_snapshot = json.loads(run_row["weights_or_policy_snapshot_json"] or "{}")
        except Exception:
            policy_snapshot = {}

        recommendations: List[Dict[str, Any]] = []
        for row in rec_rows:
            try:
                refs = json.loads(row["explanation_evidence_refs_json"] or "[]")
                if not isinstance(refs, list):
                    refs = []
            except Exception:
                refs = []
            recommendations.append(
                {
                    "rank_position": int(row["rank_position"] or 0),
                    "book_id": row["book_id"],
                    "score_total": float(row["score_total"] or 0.0),
                    "score_cf": float(row["score_cf"] or 0.0),
                    "score_content": float(row["score_content"] or 0.0),
                    "score_kg": float(row["score_kg"] or 0.0),
                    "score_diversity": float(row["score_diversity"] or 0.0),
                    "scenario_policy": row["scenario_policy"],
                    "explanation": row["explanation"] or "",
                    "explanation_evidence_refs": refs,
                    "created_at": row["created_at"],
                }
            )

        return {
            "run_id": run_row["run_id"],
            "user_id": run_row["user_id"],
            "query": run_row["query"],
            "profile_version": run_row["profile_version"],
            "candidate_set_version_or_hash": run_row["candidate_set_version_or_hash"],
            "candidate_provenance": candidate_provenance,
            "book_feature_version_or_hash": run_row["book_feature_version_or_hash"],
            "ranking_policy_version": run_row["ranking_policy_version"],
            "weights_or_policy_snapshot": policy_snapshot,
            "run_timestamp": run_row["run_timestamp"],
            "created_at": run_row["created_at"],
            "recommendations": recommendations,
        }

    def prune_old_runs(self, *, keep_latest_per_user: int = 100) -> int:
        keep = max(1, int(keep_latest_per_user))
        with transaction(self.db_url) as conn:
            rows = conn.execute(
                """
                SELECT run_id
                FROM (
                    SELECT
                        run_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY user_id
                            ORDER BY run_timestamp DESC, created_at DESC
                        ) AS rn
                    FROM recommendation_runs
                )
                WHERE rn > ?
                """,
                (keep,),
            ).fetchall()
            run_ids = [str(row["run_id"]) for row in rows if str(row["run_id"] or "").strip()]
            if not run_ids:
                return 0
            placeholders = ",".join("?" for _ in run_ids)
            conn.execute(
                f"DELETE FROM recommendation_runs WHERE run_id IN ({placeholders})",
                tuple(run_ids),
            )
            return len(run_ids)
