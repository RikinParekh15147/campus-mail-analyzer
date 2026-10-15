from datetime import date
from fastapi.testclient import TestClient
from campusmail.api import create_app
from campusmail.calendar import Calendar
from campusmail.store import Store


def test_calendar_local_date_follows_profile_timezone(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    store.put(owner, "settings", {"timezone": "Asia/Kolkata"}, "settings")
    store.put(
        owner,
        "calendar_item",
        {
            "title": "Early meeting",
            "start": "2026-10-24T23:00:00+00:00",
            "end": "2026-10-25T00:00:00+00:00",
        },
        "meeting",
    )
    entries = Calendar(store).entries(owner, date(2026, 10, 25), date(2026, 10, 25))
    assert entries[0]["date"] == "2026-10-25"


def test_personal_block_uses_profile_timezone_for_local_input(tmp_path):
    app = create_app(tmp_path, bootstrap_key="secret")
    with TestClient(app) as client:
        token = client.post(
            "/profiles", headers={"X-Bootstrap-Key": "secret"}, json={"name": "A"}
        ).json()["token"]
        headers = {"Authorization": "Bearer " + token}
        r = client.post(
            "/calendar/items",
            headers=headers,
            json={
                "title": "Study",
                "start": "2026-10-25T09:00",
                "end": "2026-10-25T10:00",
                "flexible": True,
            },
        )
        assert r.status_code == 200
        assert r.json()["start"] == "2026-10-25T09:00:00+05:30"
