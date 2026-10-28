"""FIX-07 source replay and downstream consistency checks."""

from datetime import datetime
import base64

from campusmail.briefings import Reminders
from campusmail.application import Application
from campusmail.engine import Engine
from campusmail.external_calendar import CalendarSync
from campusmail.personalization import Personalizer
from campusmail.ingestion import GmailSync
from campusmail.store import Store


def setup(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    return store, owner, Engine(store, blob_dir=tmp_path / "blobs")


def test_identical_attachment_bytes_keep_parent_occurrences_and_dates(tmp_path):
    store, owner, engine = setup(tmp_path)
    parents = [
        store.put(owner, "message", {
            "subject": "Assignment 2", "text": "See attached instructions.",
            "thread_id": "thread-" + key,
            "sent_at": "2026-10-" + day + "T09:00:00+05:30",
        }, key)
        for key, day in (("a", "01"), ("b", "03"))
    ]
    content = b"Assignment 2 must submit by tomorrow."
    first = engine.attach(owner, content, "instructions.txt", parents[0]["id"])
    second = engine.attach(owner, content, "instructions.txt", parents[1]["id"])
    assert first["id"] == second["id"]
    assert len(store.list(owner, "resource")) == 1
    assert len(store.list(owner, "assignment")) == 2
    assert {item["due_date"] for item in store.list(owner, "assignment")} == {
        "2026-10-02", "2026-10-04"
    }
    analysis_ids = second["analysis_message_ids"]
    assert len(analysis_ids) == 2
    assert {store.get(owner, item_id)["parent_record_id"] for item_id in analysis_ids} == {
        parent["id"] for parent in parents
    }
    engine.attach(owner, content, "instructions.txt", parents[0]["id"])
    assert len(store.list(owner, "assignment")) == 2
    assert len(store.list(owner, "message")) == 4


def test_same_blob_keeps_distinct_provider_items_under_one_parent(tmp_path):
    store, owner, engine = setup(tmp_path)
    parent = store.put(owner, "message", {
        "subject": "Assignment 2", "text": "See both files.",
        "sent_at": "2026-10-01T09:00:00+05:30",
    }, "parent")
    content = b"Assignment 2 must submit by tomorrow."
    first = engine.attach(owner, content, "first.txt", parent["id"], "item-a")
    second = engine.attach(owner, content, "second.txt", parent["id"], "item-b")
    assert first["id"] == second["id"]
    children = [store.get(owner, item_id) for item_id in second["analysis_message_ids"]]
    assert {(child["source_filename"], child["attachment_occurrence_id"])
            for child in children} == {("first.txt", "item-a"),
                                      ("second.txt", "item-b")}
    engine.attach(owner, content, "first.txt", parent["id"], "item-a")
    assert len(store.list(owner, "message")) == 3
    assert len(store.list(owner, "resource")) == 1


def test_invalid_attachment_parent_creates_no_blob_or_resource(tmp_path):
    store, owner, engine = setup(tmp_path)
    from campusmail.store import NotFound
    import pytest

    with pytest.raises(NotFound):
        engine.attach(owner, b"Must submit by tomorrow.", "notice.txt", "missing")
    assert not store.list(owner, "resource")
    assert not (tmp_path / "blobs" / owner).exists()


def test_rescheduled_assignment_replay_cancels_old_pending_reminders(tmp_path):
    store, owner, engine = setup(tmp_path)
    engine.fact(owner, "enrollment:NLP201", True, "confirmed", True)
    original = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2",
        "text": "NLP201 Assignment 2 must submit by 25 October 2026.",
        "sent_at": "2026-10-01T09:00:00+05:30",
    }, "original")
    update = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2",
        "text": "NLP201 Assignment 2 deadline extended to 28 October 2026.",
        "sent_at": "2026-10-02T09:00:00+05:30",
    }, "update")
    clock = datetime.fromisoformat("2026-10-01T09:00:00+05:30")
    reminders = Reminders(store)
    engine.process(owner, original)
    reminders.refresh(owner, clock)
    assert {r["target_date"] for r in store.list(owner, "reminder") if r["status"] == "pending"} == {"2026-10-25"}
    engine.process(owner, update)
    engine.process(owner, original)
    reminders.refresh(owner, clock)
    pending = [r for r in store.list(owner, "reminder") if r["status"] == "pending"]
    assert {r["target_date"] for r in pending} == {"2026-10-28"}
    assert all(r["status"] == "cancelled" for r in store.list(owner, "reminder")
               if r["target_date"] == "2026-10-25")
    reminders.refresh(owner, clock)
    assert len([r for r in store.list(owner, "reminder") if r["status"] == "pending"]) == len(pending)


def test_reverse_order_event_import_converges_after_replay(tmp_path):
    outcomes = []
    for name, order in (("forward", ("original", "update")),
                        ("reverse", ("update", "original", "update"))):
        store, owner, engine = setup(tmp_path / name)
        messages = {
            "original": store.put(owner, "message", {
                "subject": "Python Workshop",
                "text": "Python Workshop will be held on 25 October 2026.",
                "sent_at": "2026-10-01T09:00:00+05:30",
            }, "original"),
            "update": store.put(owner, "message", {
                "subject": "Python Workshop",
                "text": "Python Workshop is rescheduled for 28 October 2026.",
                "sent_at": "2026-10-02T09:00:00+05:30",
            }, "update"),
        }
        for key in order:
            engine.process(owner, store.get(owner, messages[key]["id"]))
        events = store.list(owner, "event")
        assert len(events) == 1
        outcomes.append((events[0]["date"], sorted(
            store.get(owner, item_id)["source_key"]
            for item_id in events[0]["evidence_ids"]
        )))
        assert not [q for q in store.list(owner, "review")
                    if q.get("field") == "occurrence" and q["status"] == "open"]
    assert outcomes[0] == outcomes[1]


def test_managed_calendar_removes_ineligible_items_and_restores_on_retry(tmp_path):
    class API:
        def __init__(self):
            self.events = {}
            self.creates = 0
            self.deletes = 0

        def get(self, path, params=None):
            if path not in self.events:
                raise LookupError(path)
            return self.events[path]

        def post(self, path, json):
            self.creates += 1
            key = path + "/" + json["id"]
            self.events[key] = {**json, "updated": "v1"}
            return self.events[key]

        def patch(self, path, json):
            self.events[path].update(json)
            return self.events[path]

        def delete(self, path):
            self.deletes += 1
            if path not in self.events:
                raise LookupError(path)
            del self.events[path]

    store, owner, _ = setup(tmp_path)
    api = API()
    sync = CalendarSync(store, owner, api)
    event = store.put(owner, "event", {
        "title": "Python Workshop", "date": "2026-10-25",
        "participation": "confirmed", "status": "active",
    }, "workshop")
    assignment = store.put(owner, "assignment", {
        "title": "NLP201 Assignment 2", "due_date": "2026-10-28",
        "due_at": "2026-10-28T17:00:00+05:30",
        "relevance": "applicable", "status": "open",
    }, "assignment")
    sync.reconcile_managed(store.list(owner), "managed")
    assert len(api.events) == 2
    assert api.creates == 2
    remote_due = next(value for value in api.events.values()
                      if value["extendedProperties"]["private"]["campusmail_source"] == assignment["id"])
    assert remote_due["start"] == {"dateTime": "2026-10-28T17:00:00+05:30"}
    assert remote_due["end"] == {"dateTime": "2026-10-28T17:01:00+05:30"}
    assert remote_due["transparency"] == "transparent"
    store.patch(owner, event["id"], {"date": "2026-10-26"})
    sync.reconcile_managed(store.list(owner), "managed")
    remote_event = next(value for value in api.events.values()
                        if value["extendedProperties"]["private"]["campusmail_source"] == event["id"])
    assert remote_event["start"] == {"date": "2026-10-26"}
    assert remote_event["end"] == {"date": "2026-10-27"}
    assert api.creates == 2
    store.patch(owner, event["id"], {"participation": "declined"})
    store.patch(owner, assignment["id"], {"relevance": "unrelated"})
    sync.reconcile_managed(store.list(owner), "managed")
    assert api.events == {}
    assert api.deletes == 2
    assert {m["status"] for m in store.list(owner, "calendar_mapping")} == {"deleted"}
    sync.reconcile_managed(store.list(owner), "managed")
    assert api.deletes == 2
    store.patch(owner, event["id"], {"participation": "confirmed"})
    sync.reconcile_managed(store.list(owner), "managed")
    assert len(api.events) == 1
    assert api.creates == 3
    remote_path, remote_event = next(iter(api.events.items()))
    remote_event["updated"] = "v2"
    store.patch(owner, event["id"], {"date": "2026-10-29"})
    sync.reconcile_managed(store.list(owner), "managed")
    assert api.events[remote_path]["start"] == {"date": "2026-10-26"}
    review = next(q for q in store.list(owner, "review")
                  if q["source_key"].startswith("remote-edit:"))
    assert review["choices"] == ["keep_remote", "replace_remote"]
    Personalizer(store).answer(owner, review["id"], "replace_remote")
    sync.reconcile_managed(store.list(owner), "managed")
    assert api.events[remote_path]["start"] == {"date": "2026-10-29"}
    store.patch(owner, event["id"], {"status": "cancelled"})
    sync.reconcile_managed(store.list(owner), "managed")
    assert api.events == {}
    assert api.deletes == 3


def test_application_duplicate_ingest_and_restart_preserve_reviewed_date(tmp_path):
    app = Application(tmp_path / "app")
    owner = app.store.create_user("Student")["id"]
    text = "NLP201 Assignment 2 must submit by 25 October 2026."
    first = app.ingest(owner, text, "NLP201 Assignment 2",
                       "2026-10-01T09:00:00+05:30", "source-1")
    start = first["analysis"]["dates"][0]["start"]
    correction = {str(start): {"date": "2026-10-27", "role": "assignment_deadline"}}
    app.store.patch(owner, first["id"], {"date_corrections": correction})
    app.reprocess(owner, {})
    app.ingest(owner, text, "NLP201 Assignment 2",
               "2026-10-01T09:00:00+05:30", "source-1")
    restarted = Application(tmp_path / "app")
    restarted.reprocess(owner, {})
    assignments = restarted.store.list(owner, "assignment")
    assert len(assignments) == 1
    assert assignments[0]["due_date"] == "2026-10-27"
    assert restarted.store.get(owner, first["id"])["date_corrections"] == correction


def test_duplicate_attachment_preserves_reviewed_date_correction(tmp_path):
    app = Application(tmp_path / "app")
    owner = app.store.create_user("Student")["id"]
    parent = app.ingest(owner, "See attached instructions.", "NLP201 Assignment 2",
                        "2026-10-01T09:00:00+05:30", "parent")
    content = b"NLP201 Assignment 2 must submit by 25 October 2026."
    resource = app.attach(owner, content, "instructions.txt", parent["id"])
    child = app.store.get(owner, resource["analysis_message_id"])
    start = child["analysis"]["dates"][0]["start"]
    correction = {str(start): {"date": "2026-10-27", "role": "assignment_deadline"}}
    app.store.patch(owner, child["id"], {"date_corrections": correction})
    app.reprocess(owner, {})
    app.attach(owner, content, "instructions.txt", parent["id"])
    assert app.store.get(owner, child["id"])["date_corrections"] == correction
    assert len(app.store.list(owner, "assignment")) == 1
    assert app.store.list(owner, "assignment")[0]["due_date"] == "2026-10-27"


def test_body_attachment_equal_time_deadlines_require_review(tmp_path):
    store, owner, engine = setup(tmp_path)
    parent = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2",
        "text": "NLP201 Assignment 2 must submit by 25 October 2026.",
        "sent_at": "2026-10-01T09:00:00+05:30",
    }, "parent")
    engine.process(owner, parent)
    resource = engine.attach(
        owner, b"NLP201 Assignment 2 must submit by 28 October 2026.",
        "instructions.txt", parent["id"],
    )
    assignment = store.list(owner, "assignment")[0]
    assert assignment["due_date"] == "2026-10-25"
    assert len(assignment["evidence_ids"]) == 2
    assert resource["id"] in assignment["resource_ids"]
    questions = [q for q in store.list(owner, "review")
                 if q.get("field") == "due_date" and q["status"] == "open"]
    assert len(questions) == 1
    assert questions[0]["choices"] == ["2026-10-25", "2026-10-28"]
    Personalizer(store).answer(owner, questions[0]["id"], "2026-10-28")
    engine.process(owner, store.get(owner, parent["id"]))
    engine.process(owner, store.get(owner, resource["analysis_message_id"]))
    assert store.list(owner, "assignment")[0]["due_date"] == "2026-10-28"


def test_equal_time_event_reschedule_requires_date_review(tmp_path):
    store, owner, engine = setup(tmp_path)
    stamp = "2026-10-01T09:00:00+05:30"
    original = store.put(owner, "message", {
        "subject": "Python Workshop",
        "text": "Python Workshop will be held on 25 October 2026.",
        "sent_at": stamp,
    }, "original")
    update = store.put(owner, "message", {
        "subject": "Python Workshop",
        "text": "Python Workshop is rescheduled for 28 October 2026.",
        "sent_at": stamp,
    }, "update")
    engine.process(owner, original)
    engine.process(owner, update)
    events = store.list(owner, "event")
    assert len(events) == 1
    assert events[0]["date"] == "2026-10-25"
    assert [q for q in store.list(owner, "review")
            if q.get("field") == "date" and q["status"] == "open"]


def test_duplicate_gmail_fetch_preserves_reviewed_date(tmp_path):
    store, owner, engine = setup(tmp_path)
    text = "NLP201 Assignment 2 must submit by 25 October 2026."
    raw = {
        "id": "gmail-1", "labelIds": ["INBOX"],
        "internalDate": str(int(datetime.fromisoformat(
            "2026-10-01T09:00:00+00:00").timestamp() * 1000)),
        "payload": {
            "headers": [{"name": "Subject", "value": "NLP201 Assignment 2"}],
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")},
        },
    }
    sync = GmailSync(store, owner, api=None, on_message=engine.process)
    sync.ingest(raw)
    message = store.list(owner, "message")[0]
    start = message["analysis"]["dates"][0]["start"]
    correction = {str(start): {"date": "2026-10-27", "role": "assignment_deadline"}}
    store.patch(owner, message["id"], {"date_corrections": correction})
    sync.ingest(raw)
    assert len(store.list(owner, "message")) == 1
    assert store.get(owner, message["id"])["date_corrections"] == correction
    assert store.list(owner, "assignment")[0]["due_date"] == "2026-10-27"
