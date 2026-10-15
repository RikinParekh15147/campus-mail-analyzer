from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from campusmail.api import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path, bootstrap_key="test-bootstrap", worker=False)


def profile(client, name="Student"):
    response = client.post(
        "/profiles", json={"name": name}, headers={"X-Bootstrap-Key": "test-bootstrap"}
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


def test_api_requires_session_and_bootstrap(app):
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/dashboard").status_code == 401
        assert client.post("/profiles", json={"name": "Intruder"}).status_code == 401


def test_full_local_workflow_and_private_accounts(app):
    with TestClient(app) as client:
        a, b = profile(client), profile(client, "Other")
        response = client.post(
            "/ingest",
            headers=a,
            json={
                "subject": "NLP201 Assignment 2",
                "text": "NLP201 Assignment 2 must submit by 25 October 2026. Instructions: https://example.edu/assignment.pdf",
            },
        )
        assert response.status_code == 200
        tasks = client.get("/records/assignment", headers=a).json()
        assert len(tasks) == 1
        assert client.get("/records/assignment", headers=b).json() == []
        item = tasks[0]
        assert (
            client.get("/records/" + item["id"] + "/detail", headers=b).status_code
            == 404
        )
        assert (
            client.post(
                "/feedback",
                headers=a,
                json={
                    "record_id": item["id"],
                    "field": "relevance",
                    "value": "applicable",
                    "expected_revision": item["revision"],
                },
            ).status_code
            == 200
        )
        assert client.get(
            "/calendar?start=2026-10-25&end=2026-10-25", headers=a
        ).json()[0]["due_marker"]
        assert client.get("/dashboard", headers=a).json()["counts"]["assignments"] == 1
        assert client.get("/summary", headers=a).status_code == 200
        assert client.get("/prompts/timetable", headers=a).json()["schema"][
            "properties"
        ]["student_context"]


def test_upload_readability_and_path_isolation(app):
    with TestClient(app) as client:
        a = profile(client)
        r = client.post(
            "/attachments",
            headers=a,
            files={"file": ("notes.txt", b"Course notes for NLP201", "text/plain")},
        )
        assert r.status_code == 200
        resource = r.json()
        assert resource["status"] == "readable"
        assert (
            client.get("/resources/" + resource["id"] + "/download", headers=a).content
            == b"Course notes for NLP201"
        )


def test_settings_and_review_are_persistent(app):
    with TestClient(app) as client:
        a = profile(client)
        assert (
            client.put(
                "/settings",
                headers=a,
                json={"timezone": "Asia/Kolkata", "sync_minutes": 10},
            ).status_code
            == 200
        )
        assert client.get("/settings", headers=a).json()["sync_minutes"] == 10
        assert client.get("/connections", headers=a).status_code == 200


def test_unknown_external_service_is_rejected(app):
    with TestClient(app) as client:
        a = profile(client)
        assert (
            client.post("/connections/unknown/connect", headers=a, json={}).status_code
            == 422
        )
