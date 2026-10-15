from campusmail.store import Store
from campusmail.engine import Engine


def test_old_mail_replay_does_not_undo_a_deadline_extension(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    old = store.put(
        owner,
        "message",
        {
            "subject": "NLP201 Assignment 2",
            "text": "NLP201 Assignment 2 must submit by 25 October 2026.",
            "sent_at": "2026-10-01T09:00:00+00:00",
        },
        "old",
    )
    update = store.put(
        owner,
        "message",
        {
            "subject": "NLP201 Assignment 2",
            "text": "NLP201 Assignment 2 deadline extended to 28 October 2026.",
            "sent_at": "2026-10-02T09:00:00+00:00",
        },
        "new",
    )
    engine.process(owner, old)
    engine.process(owner, update)
    engine.process(owner, old)
    assert store.list(owner, "assignment")[0]["due_date"] == "2026-10-28"


def test_complete_enrollment_filters_other_course_obligations(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    engine.fact(owner, "enrollment_complete", True, "confirmed", True)
    engine.fact(owner, "enrollment:NLP201", True, "confirmed", True)
    msg = store.put(
        owner,
        "message",
        {
            "subject": "MEC201 Assignment 2",
            "text": "MEC201 Assignment 2 must submit by 25 October 2026.",
        },
        "m",
    )
    engine.process(owner, msg)
    assert store.list(owner, "assignment")[0]["relevance"] == "unrelated"
    assert not any(q["field"] == "relevance" for q in store.list(owner, "review"))


def test_recurring_event_title_does_not_merge_separate_offerings(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    for key, day in [("one", "25"), ("two", "28")]:
        m = store.put(
            owner,
            "message",
            {
                "subject": "Python Workshop",
                "text": f"Python Workshop will be held on {day} October 2026.",
            },
            key,
        )
        engine.process(owner, m)
    assert len(store.list(owner, "event")) == 2
