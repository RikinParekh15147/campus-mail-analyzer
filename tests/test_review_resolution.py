from campusmail.store import Store
from campusmail.engine import Engine
from campusmail.personalization import Personalizer


def test_explicit_event_choice_closes_matching_question(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    msg = store.put(
        owner,
        "message",
        {
            "subject": "Python Workshop",
            "text": "Python Workshop will be held on 25 October 2026.",
        },
        "m",
    )
    engine.process(owner, msg)
    event = store.list(owner, "event")[0]
    Personalizer(store).feedback(owner, event["id"], "participation", "confirmed")
    assert not any(
        q["status"] == "open" and q.get("record_id") == event["id"]
        for q in store.list(owner, "review")
    )


def test_confirmed_enrollment_resolves_obsolete_question(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    msg = store.put(
        owner,
        "message",
        {
            "subject": "NLP201 Assignment 2",
            "text": "NLP201 Assignment 2 must submit by 25 October 2026.",
        },
        "m",
    )
    engine.process(owner, msg)
    engine.fact(owner, "enrollment:NLP201", True, "timetable", True)
    engine.process(owner, msg)
    assert not any(
        q["status"] == "open" and q.get("field") == "relevance"
        for q in store.list(owner, "review")
    )
