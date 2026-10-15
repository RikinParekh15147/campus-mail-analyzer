from fastapi.testclient import TestClient
from campusmail.api import create_app
from campusmail.engine import Engine
from campusmail.personalization import Personalizer
from campusmail.store import Store


def test_confirmed_profile_endpoint_and_marks(tmp_path):
    app = create_app(tmp_path, bootstrap_key="secret")
    with TestClient(app) as client:
        token = client.post(
            "/profiles", json={"name": "A"}, headers={"X-Bootstrap-Key": "secret"}
        ).json()["token"]
        headers = {"Authorization": "Bearer " + token}
        response = client.post(
            "/profile/facts",
            json={"field": "roll_number", "value": "23BIT044"},
            headers=headers,
        )
        assert response.status_code == 200
        marks = client.post(
            "/marks/extract",
            json={"course": "NLP201", "assessment": "Quiz 1", "text": "23BIT044 8/10"},
            headers=headers,
        )
        assert marks.status_code == 200 and marks.json()[0]["earned"] == 8


def test_date_review_changes_underlying_assignment(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    message = store.put(
        owner,
        "message",
        {
            "subject": "NLP201 Assignment 2",
            "text": "NLP201 Assignment 2 must submit by 25 October.",
        },
        "message",
    )
    engine.process(owner, message)
    question = next(r for r in store.list(owner, "review") if r.get("field") == "date")
    Personalizer(store).answer(
        owner, question["id"], {"date": "2026-10-25", "role": "assignment_deadline"}
    )
    engine.process(owner, store.get(owner, message["id"]))
    assert store.list(owner, "assignment")[0]["due_date"] == "2026-10-25"


def test_manual_reply_resolution_changes_dashboard_state(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    item = store.put(
        owner,
        "reply_request",
        {"title": "Please send report", "state": "needs_reply"},
        "request",
    )
    Personalizer(store).feedback(owner, item["id"], "status", "resolved")
    assert store.get(owner, item["id"])["state"] == "resolved"
