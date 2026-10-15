from datetime import datetime, timezone
from campusmail.store import Store
from campusmail.trackers import Conversations
from campusmail.personalization import Personalizer
from campusmail.briefings import Briefings
from campusmail.ingestion import GmailSync


def test_manual_reply_resolution_survives_thread_reanalysis(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    store.put(
        owner, "message", {"text": "Can you send the report?", "thread_id": "t"}, "m"
    )
    tracker = Conversations(store)
    record = tracker.analyze(owner, "t")[0]
    Personalizer(store).feedback(owner, record["id"], "status", "resolved")
    assert tracker.analyze(owner, "t")[0]["state"] == "resolved"


def test_briefing_date_uses_personal_timezone(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    store.put(owner, "settings", {"timezone": "America/New_York"}, "settings")
    clock = datetime(2026, 10, 15, 1, tzinfo=timezone.utc)
    assert Briefings(store).generate(owner, clock)["date"] == "2026-10-14"


def test_older_context_search_is_bounded_and_keeps_label_scope(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    calls = []

    class API:
        def get(self, path, params=None):
            calls.append((path, params))
            if path == "messages":
                return {"messages": []}
            raise AssertionError(path)

    GmailSync(store, owner, API(), scope={"labels": ["College"]}).search_context(
        "NLP201 Assignment 2", limit=10
    )
    assert calls[0][1]["labelIds"] == ["College"]
    assert calls[0][1]["maxResults"] == 10
