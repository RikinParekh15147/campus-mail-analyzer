"""FIX-04 cancellation must affect only the named entity."""

from datetime import date, datetime

from campusmail.briefings import Reminders
from campusmail.calendar import Calendar
from campusmail.engine import Engine
from campusmail.personalization import Personalizer
from campusmail.store import Store


def setup(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store)
    engine.fact(owner, "enrollment:NLP201", True, "confirmed", True)
    return store, owner, engine


def send(store, owner, engine, key, text, day, subject=""):
    message = store.put(owner, "message", {
        "subject": subject, "text": text,
        "sent_at": f"2026-10-{day}T09:00:00+05:30",
    }, key)
    engine.process(owner, message)
    return message


def assignment_statuses(store, owner):
    return {item["assignment_number"]: item["status"]
            for item in store.list(owner, "assignment")}


def test_clause_local_assignment_cancellation_leaves_other_open_and_replays(tmp_path):
    store, owner, engine = setup(tmp_path)
    initial = send(store, owner, engine, "initial",
                   "NLP201 Assignment 1 must submit by 25 October 2026. "
                   "NLP201 Assignment 2 must submit by 26 October 2026.", "01")
    cancellation = send(store, owner, engine, "cancel",
                        "NLP201 Assignment 1 is cancelled, NLP201 Assignment 2 remains active.",
                        "02")
    assert assignment_statuses(store, owner) == {"1": "cancelled", "2": "open"}
    assert not [row for row in store.list(owner, "review")
                if row["source_key"].startswith("assignment-cancel:")]
    engine.process(owner, store.get(owner, initial["id"]))
    engine.process(owner, store.get(owner, cancellation["id"]))
    assert assignment_statuses(store, owner) == {"1": "cancelled", "2": "open"}
    assert len(Calendar(store).entries(owner, date(2026, 10, 25), date(2026, 10, 26))) == 1


def test_negated_first_cancellation_and_positive_second_are_separate(tmp_path):
    store, owner, engine = setup(tmp_path)
    send(store, owner, engine, "initial",
         "NLP201 Assignment 1 due 25 October 2026. NLP201 Assignment 2 due 26 October 2026.",
         "01")
    send(store, owner, engine, "update",
         "NLP201 Assignment 1 is not cancelled but NLP201 Assignment 2 is cancelled.",
         "02")
    assert assignment_statuses(store, owner) == {"1": "open", "2": "cancelled"}


def test_hedged_cancellation_waits_for_review(tmp_path):
    store, owner, engine = setup(tmp_path)
    send(store, owner, engine, "initial",
         "NLP201 Assignment 2 due 26 October 2026.", "01")
    send(store, owner, engine, "possible",
         "NLP201 Assignment 2 may be cancelled.", "02")
    assert assignment_statuses(store, owner) == {"2": "open"}
    assert any(row["status"] == "open" and row["source_key"].startswith("assignment-cancel:")
               for row in store.list(owner, "review"))


def test_assignment_number_list_needs_review_without_mass_cancellation(tmp_path):
    store, owner, engine = setup(tmp_path)
    send(store, owner, engine, "initial",
         "NLP201 Assignment 1 due 25 October 2026. NLP201 Assignment 2 due 26 October 2026.",
         "01")
    update = send(store, owner, engine, "ambiguous", "NLP201 Assignment 1 and 2 cancelled.", "02")
    assert assignment_statuses(store, owner) == {"1": "open", "2": "open"}
    questions = [row for row in store.list(owner, "review")
                 if row["status"] == "open" and row["source_key"].startswith("assignment-cancel:")]
    assert len(questions) == 1
    Personalizer(store).answer(owner, questions[0]["id"], "cancelled")
    engine.process(owner, store.get(owner, update["id"]))
    assert assignment_statuses(store, owner) == {"1": "cancelled", "2": "open"}


def test_generic_unnumbered_assignment_cancellation_requires_target_review(tmp_path):
    store, owner, engine = setup(tmp_path)
    send(store, owner, engine, "generic", "The assignment is cancelled.", "02",
         "Course work")
    items = store.list(owner, "assignment")
    assert len(items) == 1 and items[0]["status"] == "open"
    assert any(row["status"] == "open" and row["source_key"].startswith("assignment-cancel:")
               for row in store.list(owner, "review"))


def test_other_clause_cancellation_does_not_turn_new_unknown_course_task_into_update(tmp_path):
    store, owner, engine = setup(tmp_path)
    old = store.put(owner, "message", {
        "text": "Assignment 2 must submit by 25 October 2026.",
        "thread_id": "older-thread", "sent_at": "2026-10-01T09:00:00+05:30",
    }, "old")
    engine.process(owner, old)
    newer = store.put(owner, "message", {
        "text": "Assignment 1 is cancelled, Assignment 2 must submit by 26 October 2026.",
        "thread_id": "new-thread", "sent_at": "2026-10-02T09:00:00+05:30",
    }, "new")
    engine.process(owner, newer)
    second_tasks = [item for item in store.list(owner, "assignment")
                    if item["assignment_number"] == "2"]
    assert len(second_tasks) == 2
    assert {item["due_date"] for item in second_tasks} == {"2026-10-25", "2026-10-26"}


def test_named_event_cancellation_uses_its_own_clause(tmp_path):
    store, owner, engine = setup(tmp_path)
    send(store, owner, engine, "python",
         "Python Workshop will be held on 25 October 2026.", "01", "Python Workshop")
    send(store, owner, engine, "robotics",
         "Robotics Seminar will be held on 26 October 2026.", "01", "Robotics Seminar")
    send(store, owner, engine, "update",
         "Python Workshop remains active, Robotics Seminar is cancelled.", "02")
    events = {item["title"]: item for item in store.list(owner, "event")}
    assert events["Python Workshop"]["status"] == "active"
    assert events["Robotics Seminar"]["status"] == "cancelled"
    assert not [row for row in store.list(owner, "review")
                if row["source_key"].startswith("event-cancel:")]


def test_two_named_events_in_one_unsplit_clause_require_review(tmp_path):
    store, owner, engine = setup(tmp_path)
    send(store, owner, engine, "python",
         "Python Workshop will be held on 25 October 2026.", "01", "Python Workshop")
    send(store, owner, engine, "robotics",
         "Robotics Seminar will be held on 26 October 2026.", "01", "Robotics Seminar")
    send(store, owner, engine, "ambiguous",
         "Python Workshop and Robotics Seminar are cancelled.", "02")
    assert {item["status"] for item in store.list(owner, "event")} == {"active"}
    questions = [row for row in store.list(owner, "review")
                 if row["status"] == "open" and row["source_key"].startswith("event-cancel:")]
    assert len(questions) == 2


def test_negated_named_event_is_not_cancelled_or_reprompted(tmp_path):
    store, owner, engine = setup(tmp_path)
    send(store, owner, engine, "python",
         "Python Workshop will be held on 25 October 2026.", "01", "Python Workshop")
    send(store, owner, engine, "robotics",
         "Robotics Seminar will be held on 26 October 2026.", "01", "Robotics Seminar")
    send(store, owner, engine, "update",
         "Python Workshop is not cancelled, Robotics Seminar is canceled.", "02")
    events = {item["title"]: item for item in store.list(owner, "event")}
    assert events["Python Workshop"]["status"] == "active"
    assert events["Robotics Seminar"]["status"] == "cancelled"
    assert not [row for row in store.list(owner, "review")
                if row["source_key"].startswith("event-cancel:")]


def test_generic_event_cancellation_stays_reviewable_and_decision_survives_replay(tmp_path):
    store, owner, engine = setup(tmp_path)
    first = send(store, owner, engine, "first",
                 "Python Workshop will be held on 25 October 2026.", "01", "Python Workshop")
    event = store.list(owner, "event")[0]
    Personalizer(store).feedback(owner, event["id"], "participation", "confirmed")
    clock = datetime.fromisoformat("2026-10-01T09:00:00+05:30")
    reminders = Reminders(store)
    reminders.refresh(owner, clock)
    assert any(row["status"] == "pending" and row.get("record_id") == event["id"]
               for row in store.list(owner, "reminder"))
    cancellation = send(store, owner, engine, "generic",
                        "This event is cancelled.", "02", "Python Workshop")
    event = store.get(owner, event["id"])
    assert event["status"] == "active"
    questions = [row for row in store.list(owner, "review")
                 if row["status"] == "open" and row["source_key"].startswith("event-cancel:")]
    assert len(questions) == 1 and questions[0]["record_id"] == event["id"]
    Personalizer(store).answer(owner, questions[0]["id"], "cancelled")
    engine.process(owner, store.get(owner, first["id"]))
    engine.process(owner, store.get(owner, cancellation["id"]))
    assert store.get(owner, event["id"])["status"] == "cancelled"
    assert Calendar(store).entries(owner, date(2026, 10, 25), date(2026, 10, 25)) == []
    reminders.refresh(owner, clock)
    assert not [row for row in store.list(owner, "reminder")
                if row["status"] == "pending" and row.get("record_id") == event["id"]]
    assert any(row["status"] == "cancelled" and row.get("record_id") == event["id"]
               for row in store.list(owner, "reminder"))
