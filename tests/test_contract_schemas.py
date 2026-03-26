from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import reading_concierge.reading_concierge as concierge


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONTRACT_DIR = _PROJECT_ROOT / "docs" / "contracts"


@pytest.mark.parametrize(
    "schema_name",
    [
        "user_profile.schema.json",
        "candidate_book_set.schema.json",
        "book_feature_map.schema.json",
        "ranked_recommendation_list.schema.json",
    ],
)
def test_contract_schema_has_version_and_is_valid(schema_name: str):
    path = _CONTRACT_DIR / schema_name
    assert path.exists(), f"missing schema file: {path}"

    schema = json.loads(path.read_text(encoding="utf-8"))
    assert str(schema.get("x_contract_version") or "").startswith("v1"), "schema must carry v1 contract marker"
    Draft202012Validator.check_schema(schema)


@pytest.mark.usefixtures("patch_openai")
def test_user_profile_snapshot_conforms_to_contract_schema(client_reading_concierge):
    schema_path = _CONTRACT_DIR / "user_profile.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    user_id = "contract-user-001"
    payload = {
        "user_id": user_id,
        "query": "recommend science books for me",
        "user_profile": {"preferred_language": "en"},
        "history": [
            {
                "title": "A Brief History of Time",
                "genres": ["science", "nonfiction"],
                "rating": 4,
                "language": "en",
            }
        ],
        "constraints": {"debug_payload_override": True},
    }

    resp = client_reading_concierge.post("/user_api", json=payload)
    assert resp.status_code == 200

    snapshot = concierge.profile_store.get_latest_profile(user_id)
    assert snapshot, "profile snapshot should be persisted after successful orchestration"

    errors = sorted(validator.iter_errors(snapshot), key=lambda err: list(err.path))
    assert not errors, "schema validation errors: " + "; ".join(error.message for error in errors)


@pytest.mark.usefixtures("patch_openai")
def test_target_runtime_artifacts_conform_to_contract_schemas(client_reading_concierge):
    candidate_schema = json.loads((_CONTRACT_DIR / "candidate_book_set.schema.json").read_text(encoding="utf-8"))
    book_feature_schema = json.loads((_CONTRACT_DIR / "book_feature_map.schema.json").read_text(encoding="utf-8"))
    ranked_schema = json.loads((_CONTRACT_DIR / "ranked_recommendation_list.schema.json").read_text(encoding="utf-8"))
    candidate_validator = Draft202012Validator(candidate_schema)
    book_feature_validator = Draft202012Validator(book_feature_schema)
    ranked_validator = Draft202012Validator(ranked_schema)

    payload = {
        "user_id": "contract-runtime-001",
        "query": "recommend diverse science and history books",
        "user_profile": {"preferred_language": "en"},
        "history": [
            {
                "title": "Sapiens",
                "genres": ["history", "nonfiction"],
                "rating": 4,
                "language": "en",
            }
        ],
        "books": [
            {
                "book_id": "runtime-b1",
                "title": "Foundation",
                "author": "Isaac Asimov",
                "description": "Future civilizations and psychohistory",
                "genres": ["science_fiction"],
            },
            {
                "book_id": "runtime-b2",
                "title": "The Silk Roads",
                "author": "Peter Frankopan",
                "description": "Global history and trade routes",
                "genres": ["history"],
            },
        ],
        "constraints": {"debug_payload_override": True, "top_k": 2},
    }

    resp = client_reading_concierge.post("/user_api", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    artifacts = body.get("contract_artifacts") or {}
    candidate_set = artifacts.get("candidate_book_set") or {}
    book_feature_map = artifacts.get("book_feature_map") or {}
    ranked_list = artifacts.get("ranked_recommendation_list") or {}

    candidate_errors = sorted(candidate_validator.iter_errors(candidate_set), key=lambda err: list(err.path))
    book_feature_errors = sorted(book_feature_validator.iter_errors(book_feature_map), key=lambda err: list(err.path))
    ranked_errors = sorted(ranked_validator.iter_errors(ranked_list), key=lambda err: list(err.path))

    assert not candidate_errors, "candidate schema errors: " + "; ".join(e.message for e in candidate_errors)
    assert not book_feature_errors, "book feature schema errors: " + "; ".join(e.message for e in book_feature_errors)
    assert not ranked_errors, "ranked schema errors: " + "; ".join(e.message for e in ranked_errors)

    contract_validation = body.get("contract_validation") or {}
    assert contract_validation.get("candidate_book_set", {}).get("passed") is True
    assert contract_validation.get("book_feature_map", {}).get("passed") is True
    assert contract_validation.get("ranked_recommendation_list", {}).get("passed") is True
