from __future__ import annotations


def _assert_descriptor_shape(body: dict):
    assert isinstance(body, dict)
    assert isinstance(body.get("aic"), str) and body["aic"].strip()
    assert isinstance(body.get("protocolVersion"), str) and body["protocolVersion"].strip()

    endpoints = body.get("endPoints")
    assert isinstance(endpoints, list) and endpoints, "endPoints must be a non-empty list"
    for endpoint in endpoints:
        assert isinstance(endpoint, dict)
        assert isinstance(endpoint.get("url"), str) and endpoint["url"].strip()

    skills = body.get("skills")
    assert isinstance(skills, list) and skills, "skills must be a non-empty list"

    skill_ids = []
    for skill in skills:
        if isinstance(skill, dict):
            skill_ids.append(str(skill.get("id") or skill.get("name") or "").strip())
        elif isinstance(skill, str):
            skill_ids.append(skill.strip())
    assert skill_ids and all(skill_ids), "all skill IDs must be non-empty strings"


def _assert_acs(client):
    response = client.get("/acs")
    assert response.status_code == 200
    _assert_descriptor_shape(response.json())


def test_reader_profile_acs_conformance(client_reader_profile):
    _assert_acs(client_reader_profile)


def test_book_content_acs_conformance(client_book_content):
    _assert_acs(client_book_content)


def test_rec_ranking_acs_conformance(client_rec_ranking):
    _assert_acs(client_rec_ranking)


def test_reading_concierge_acs_conformance(client_reading_concierge):
    _assert_acs(client_reading_concierge)
