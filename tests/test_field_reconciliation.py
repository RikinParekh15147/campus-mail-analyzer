"""FIX-06 field-specific source order and personal override boundaries."""

from campusmail.engine import Engine
from campusmail.calendar import Calendar
from campusmail.personalization import Personalizer
from campusmail.store import Store


def setup(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    return store, owner, Engine(store)


def send(store, owner, key, text, sent_at, subject=""):
    return store.put(owner, "message", {
        "subject": subject, "text": text, "sent_at": sent_at,
    }, key)


def test_intermediate_assignment_correction_survives_later_info_and_replay(tmp_path):
    store, owner, engine = setup(tmp_path)
    first = send(store, owner, "first", "NLP201 Assignment 2 must submit by 25 October 2026.",
                 "2026-10-01T09:00:00+00:00")
    info = send(store, owner, "info", "NLP201 Assignment 2 rubric is available.",
                "2026-10-03T09:00:00+00:00")
    correction = send(store, owner, "correction",
                      "NLP201 Assignment 2 deadline extended to 28 October 2026.",
                      "2026-10-02T09:00:00+00:00")
    for item in (first, info, correction, first):
        engine.process(owner, item)
    assignment = store.list(owner, "assignment")[0]
    assert assignment["due_date"] == "2026-10-28"
    assert assignment["field_source_at"]["due_date"] == correction["sent_at"]
    evidence = assignment["field_evidence"]["due_date"]
    assert evidence["evidence"]["document_id"] == correction["id"]
    assert evidence["value"] == assignment["due_date"]


def test_event_manual_date_and_status_survive_replay_with_conflict(tmp_path):
    store, owner, engine = setup(tmp_path)
    first = send(store, owner, "first",
                 "Python Workshop will be held on 25 October 2026.",
                 "2026-10-01T09:00:00+00:00", "Python Workshop")
    engine.process(owner, first)
    event = store.list(owner, "event")[0]
    personalizer = Personalizer(store)
    personalizer.feedback(owner, event["id"], "date", "2026-10-27")
    personalizer.feedback(owner, event["id"], "status", "cancelled")
    personalizer.feedback(owner, event["id"], "relevance", "unrelated")
    update = send(store, owner, "update",
                  "Python Workshop is rescheduled for 28 October 2026.",
                  "2026-10-02T09:00:00+00:00", "Python Workshop")
    engine.process(owner, update)
    engine.process(owner, first)
    resolved = store.get(owner, event["id"])
    assert resolved["date"] == "2026-10-27"
    assert resolved["status"] == "cancelled"
    assert resolved["relevance"] == "unrelated"
    assert resolved["field_evidence"]["date"] == {
        "origin": "user_confirmed", "record_id": event["id"],
        "value": "2026-10-27",
    }
    assert any(q.get("field") == "date" and q.get("status") == "open"
               for q in store.list(owner, "review"))


def test_intermediate_event_correction_survives_later_info(tmp_path):
    store, owner, engine = setup(tmp_path)
    first = send(store, owner, "first",
                 "Python Workshop will be held on 25 October 2026.",
                 "2026-10-01T09:00:00+00:00", "Python Workshop")
    info = send(store, owner, "info", "Python Workshop agenda is available.",
                "2026-10-03T09:00:00+00:00", "Python Workshop")
    correction = send(store, owner, "correction",
                      "Python Workshop is rescheduled for 28 October 2026.",
                      "2026-10-02T09:00:00+00:00", "Python Workshop")
    for item in (first, info, correction, first):
        engine.process(owner, item)
    event = store.list(owner, "event")[0]
    assert event["date"] == "2026-10-28"
    assert event["field_source_at"]["date"] == correction["sent_at"]
    evidence = event["field_evidence"]["date"]
    assert evidence["evidence"]["document_id"] == correction["id"]
    assert evidence["value"] == event["date"]


def test_manual_date_moves_stored_times_and_calendar_day(tmp_path):
    store, owner, engine = setup(tmp_path)
    event = store.put(owner, "event", {
        "title": "Python Workshop", "date": "2026-10-25",
        "start": "2026-10-25T10:00:00+05:30",
        "end": "2026-10-25T11:00:00+05:30",
        "date_precision": "datetime", "participation": "confirmed",
        "status": "active", "relevance": "applicable",
    }, "event")
    updated = Personalizer(store).feedback(owner, event["id"], "date", "2026-10-27")
    assert updated["start"] == "2026-10-27T10:00:00+05:30"
    assert updated["end"] == "2026-10-27T11:00:00+05:30"
    assert Calendar(store).entries(owner, "2026-10-25", "2026-10-25") == []
    assert [e["id"] for e in Calendar(store).entries(owner, "2026-10-27", "2026-10-27")] == [event["id"]]


def test_assignment_manual_date_moves_due_time_and_survives_replay(tmp_path):
    store, owner, engine = setup(tmp_path)
    first = send(store, owner, "first",
                 "NLP201 Assignment 2 must submit by 25 October 2026 at 17:00.",
                 "2026-10-01T09:00:00+00:00")
    engine.process(owner, first)
    assignment = store.list(owner, "assignment")[0]
    assert assignment["due_at"] is not None
    corrected = Personalizer(store).feedback(owner, assignment["id"], "due_date", "2026-10-27")
    assert corrected["due_at"][:10] == "2026-10-27"
    engine.process(owner, first)
    assert store.get(owner, assignment["id"])["due_at"][:10] == "2026-10-27"


def test_legacy_record_backfills_field_time_without_losing_override(tmp_path):
    store, owner, engine = setup(tmp_path)
    legacy = store.put(owner, "assignment", {
        "title": "NLP201 Assignment 2", "course": "NLP201",
        "assignment_number": "2", "academic_term": None,
        "due_date": "2026-10-27", "status": "complete",
        "overrides": {"due_date": "2026-10-27", "status": "complete"},
        "latest_source_at": "2026-10-01T09:00:00+00:00",
        "evidence_ids": [],
    }, "NLP201:assignment:2")
    notice = send(store, owner, "notice",
                  "NLP201 Assignment 2 deadline extended to 28 October 2026.",
                  "2026-10-02T09:00:00+00:00")
    engine.process(owner, notice)
    current = store.get(owner, legacy["id"])
    assert current["due_date"] == "2026-10-27"
    assert current["status"] == "complete"
    assert current["field_source_at"]["due_date"] == notice["sent_at"]
    conflicts = [q for q in store.list(owner, "review") if q.get("field") == "due_date"]
    assert conflicts and conflicts[0]["choices"] == ["2026-10-27", "2026-10-28"]
    Personalizer(store).answer(owner, conflicts[0]["id"], "2026-10-28")
    assert store.get(owner, legacy["id"])["due_date"] == "2026-10-28"
    engine.process(owner, notice)
    assert store.get(owner, legacy["id"])["due_date"] == "2026-10-28"


def test_intermediate_event_time_and_cancellation_survive_later_info(tmp_path):
    store, owner, engine = setup(tmp_path)
    first = send(store, owner, "first",
                 "Python Workshop will be held on 25 October 2026 from 10:00 to 11:00.",
                 "2026-10-01T09:00:00+00:00", "Python Workshop")
    info = send(store, owner, "info", "Python Workshop agenda is available.",
                "2026-10-04T09:00:00+00:00", "Python Workshop")
    correction = send(store, owner, "correction",
                      "Python Workshop is rescheduled for 28 October 2026 from 12:00 to 13:00.",
                      "2026-10-02T09:00:00+00:00", "Python Workshop")
    cancellation = send(store, owner, "cancellation",
                        "Python Workshop is cancelled.",
                        "2026-10-03T09:00:00+00:00", "Python Workshop")
    for item in (first, info, correction, cancellation, first):
        engine.process(owner, item)
    event = store.list(owner, "event")[0]
    assert event["date"] == "2026-10-28"
    assert event["start"][:16] == "2026-10-28T12:00"
    assert event["end"][:16] == "2026-10-28T13:00"
    assert event["status"] == "cancelled"
    assert event["field_source_at"]["status"] == cancellation["sent_at"]
