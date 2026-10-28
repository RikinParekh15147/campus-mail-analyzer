"""OPS-03 queue lease recovery boundaries."""

from time import sleep
from datetime import datetime
import base64

from campusmail.application import Application
from campusmail.engine import Engine
from campusmail.external_calendar import CalendarSync
from campusmail.ingestion import GmailSync
from campusmail.jobs import Queue
from campusmail.store import Store


def setup(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    return store, owner, Queue(store)


def test_running_legacy_job_without_lease_is_reclaimed_once(tmp_path):
    store, owner, queue = setup(tmp_path)
    job = queue.enqueue(owner, "count", {"value": 1}, "legacy")
    store.patch(owner, job["id"], {"status": "running", "lease_until": None})
    calls = []
    assert Queue(Store(store.path)).run_once({"count": lambda _, p: calls.append(p["value"])}) == 1
    assert calls == [1]
    assert queue.run_once({"count": lambda *_: calls.append(2)}) == 0
    assert calls == [1]


def test_old_worker_cannot_complete_after_lease_is_reclaimed(tmp_path):
    store, owner, queue = setup(tmp_path)
    job = queue.enqueue(owner, "count", {}, "reclaimed")

    def handler(_, __):
        current = store.get(owner, job["id"])
        store.patch(owner, job["id"], {
            "status": "running", "lease_until": "9999-01-01T00:00:00+00:00",
        }, current["revision"])

    assert queue.run_once({"count": handler}) == 0
    current = store.get(owner, job["id"])
    assert current["status"] == "running"
    assert current["attempts"] == 0
    assert current["lease_until"] == "9999-01-01T00:00:00+00:00"


def test_long_handler_renews_lease_and_completes_once(tmp_path):
    store, owner, _ = setup(tmp_path)
    queue = Queue(store, lease_seconds=0.2, heartbeat_seconds=0.04)
    job = queue.enqueue(owner, "long", {}, "long")
    observed = []

    def handler(_, __):
        sleep(0.26)
        observed.append(Queue(Store(store.path)).run_once({"long": lambda *_: None}))

    assert queue.run_once({"long": handler}) == 1
    assert observed == [0]
    current = store.get(owner, job["id"])
    assert current["status"] == "complete"
    assert current["revision"] > job["revision"] + 2


def test_failure_after_heartbeat_uses_latest_lease_revision(tmp_path):
    store, owner, _ = setup(tmp_path)
    queue = Queue(store, lease_seconds=0.2, heartbeat_seconds=0.04)
    job = queue.enqueue(owner, "failing", {}, "failing")

    def handler(_, __):
        sleep(0.12)
        raise RuntimeError("transient")

    assert queue.run_once({"failing": handler}) == 0
    current = store.get(owner, job["id"])
    assert current["status"] == "pending"
    assert current["attempts"] == 1
    assert current["revision"] > job["revision"] + 2


def test_reprocess_failure_then_restart_converges_entities_and_reminders(tmp_path):
    data_dir = tmp_path / "app"
    app = Application(data_dir)
    owner = app.store.create_user("Student")["id"]
    app.engine.fact(owner, "enrollment:NLP201", True, "confirmed", True)
    for key, day, stamp, wording in (
        ("old", "25", "01", "must submit by"),
        ("update", "28", "02", "deadline extended to"),
    ):
        app.store.put(owner, "message", {
            "subject": "NLP201 Assignment 2",
            "text": f"NLP201 Assignment 2 {wording} {day} October 2026.",
            "sent_at": f"2026-10-{stamp}T09:00:00+05:30",
        }, key)
    job = app.queue.enqueue(owner, "reprocess", {}, "reprocess-once")
    clock = datetime.fromisoformat("2026-10-01T09:00:00+05:30")

    def fail_after_first(account, payload):
        app.process(account, app.store.list(account, "message")[0])
        app.reminders.refresh(account, clock)
        raise RuntimeError("injected failure")

    assert app.queue.run_once({"reprocess": fail_after_first}) == 0
    assert app.store.get(owner, job["id"])["status"] == "pending"
    assert {r["target_date"] for r in app.store.list(owner, "reminder")
            if r["status"] == "pending"} == {"2026-10-25"}
    app.store.patch(owner, job["id"], {"run_after": "2026-01-01T00:00:00+00:00"})
    restarted = Application(data_dir)
    assert restarted.queue.run_once({"reprocess": restarted.reprocess}) == 1
    restarted.reminders.refresh(owner, clock)
    assignments = restarted.store.list(owner, "assignment")
    assert len(assignments) == 1
    assert assignments[0]["due_date"] == "2026-10-28"
    assert len(assignments[0]["evidence_ids"]) == 2
    reminders = restarted.store.list(owner, "reminder")
    assert {r["target_date"] for r in reminders if r["status"] == "pending"} == {"2026-10-28"}
    assert all(r["status"] == "cancelled" for r in reminders
               if r["target_date"] == "2026-10-25")


def test_gmail_partial_ingest_retries_without_advancing_checkpoint(tmp_path):
    store, owner, _ = setup(tmp_path)

    def raw(key, number):
        body = f"NLP201 Assignment {number} must submit by 25 October 2026."
        return {
            "id": key, "labelIds": ["INBOX"], "threadId": None,
            "internalDate": "1790834400000",
            "payload": {
                "headers": [{"name": "Subject", "value": f"NLP201 Assignment {number}"}],
                "mimeType": "text/plain",
                "body": {"data": base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")},
            },
        }

    class API:
        def get(self, path, params=None):
            if path == "profile":
                return {"historyId": "10"}
            if path == "messages":
                return {"messages": [{"id": "m1"}, {"id": "m2"}]}
            if path == "history":
                return {"historyId": "10", "history": []}
            return {"messages/m1": raw("m1", 1), "messages/m2": raw("m2", 2)}[path]

    engine = Engine(store)
    calls = []

    def interrupt(account, message):
        engine.process(account, message)
        calls.append(message["id"])
        if len(calls) == 1:
            raise RuntimeError("after first message")

    try:
        GmailSync(store, owner, API(), on_message=interrupt).run()
    except RuntimeError:
        pass
    else:
        raise AssertionError("Injected failure did not occur")
    assert store.list(owner, "sync_state") == []
    GmailSync(Store(store.path), owner, API(), on_message=Engine(Store(store.path)).process).run()
    assert len(store.list(owner, "message")) == 2
    assert len(store.list(owner, "assignment")) == 2
    assert store.list(owner, "sync_state")[0]["history_id"] == "10"


def test_calendar_create_response_failure_recovers_existing_remote_id(tmp_path):
    store, owner, _ = setup(tmp_path)

    class API:
        def __init__(self):
            self.events = {}
            self.creates = 0

        def get(self, path, params=None):
            if path not in self.events:
                raise LookupError(path)
            return self.events[path]

        def post(self, path, json):
            self.creates += 1
            key = path + "/" + json["id"]
            self.events[key] = {**json, "updated": "v1"}
            raise RuntimeError("response lost after remote create")

        def patch(self, path, json):
            self.events[path].update(json)
            return self.events[path]

    api = API()
    item = store.put(owner, "event", {
        "title": "Python Workshop", "date": "2026-10-25",
        "participation": "confirmed", "status": "active",
    }, "workshop")
    sync = CalendarSync(store, owner, api)
    try:
        sync.export(item, "managed")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Injected response failure did not occur")
    assert store.list(owner, "calendar_mapping") == []
    sync.export(item, "managed")
    assert api.creates == 1
    assert len(api.events) == 1
    assert store.list(owner, "calendar_mapping")[0]["status"] == "active"


def test_direct_ingest_crash_is_recovered_after_message_lease_expires(tmp_path):
    data_dir = tmp_path / "app"
    app = Application(data_dir)
    owner = app.store.create_user("Student")["id"]
    app.engine.fact(owner, "enrollment:NLP201", True, "confirmed", True)
    original_process = app.engine.process

    def crash_after_entity_write(account, message):
        original_process(account, message)
        raise RuntimeError("injected process crash")

    app.engine.process = crash_after_entity_write
    try:
        app.ingest(
            owner, "NLP201 Assignment 2 must submit by 25 November 2026.",
            "NLP201 Assignment 2", "2026-10-28T09:00:00+05:30", "direct",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Injected failure did not occur")
    message = app.store.list(owner, "message")[0]
    assert message["processing_status"] == "pending"
    assert len(app.store.list(owner, "assignment")) == 1
    restarted = Application(data_dir)
    assert restarted.run_jobs() == 0
    restarted.store.patch(owner, message["id"], {
        "processing_lease_until": "2026-01-01T00:00:00+00:00",
    })
    assert restarted.run_jobs() == 1
    assert restarted.store.get(owner, message["id"])["processing_status"] == "complete"
    assert len(restarted.store.list(owner, "assignment")) == 1
    assert {r["target_date"] for r in restarted.store.list(owner, "reminder")
            if r["status"] == "pending"} == {"2026-11-25"}
    assert restarted.run_jobs() == 0
    again = restarted.engine.process

    def crash_again(account, record):
        again(account, record)
        raise RuntimeError("second process crash")

    restarted.engine.process = crash_again
    try:
        restarted.process(owner, restarted.store.get(owner, message["id"]))
    except RuntimeError:
        pass
    else:
        raise AssertionError("Second injected failure did not occur")
    restarted.store.patch(owner, message["id"], {
        "processing_lease_until": "2026-01-01T00:00:00+00:00",
    })
    recovered_again = Application(data_dir)
    assert recovered_again.run_jobs() == 1
    assert len(recovered_again.store.list(owner, "assignment")) == 1
    assert recovered_again.store.get(owner, message["id"])["processing_status"] == "complete"
