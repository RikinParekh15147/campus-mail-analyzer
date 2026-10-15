from campusmail.store import Store
from campusmail.engine import Engine


def test_assignment_without_number_is_still_a_task(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    message = store.put(
        owner,
        "message",
        {
            "subject": "NLP201 Lab assignment",
            "text": "Please submit your lab assignment by 25 October 2026.",
        },
        "m",
    )
    engine.process(owner, message)
    task = store.list(owner, "assignment")[0]
    assert task["title"] == "NLP201 Lab assignment"
    assert task["due_date"] == "2026-10-25"


def test_two_assignments_keep_their_own_dates_and_courses(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    text = "NLP201 Assignment 1 must submit by 25 October 2026. DBMS301 Assignment 1 must submit by 28 October 2026."
    m = store.put(owner, "message", {"subject": "Assignments", "text": text}, "m")
    engine.process(owner, m)
    tasks = {t["course"]: t for t in store.list(owner, "assignment")}
    assert len(tasks) == 2
    assert tasks["NLP201"]["due_date"] == "2026-10-25"
    assert tasks["DBMS301"]["due_date"] == "2026-10-28"


def test_timetable_course_alias_is_recognized(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    engine.fact(owner, "enrollment:NLP", True, "timetable", True)
    message = store.put(
        owner,
        "message",
        {
            "subject": "NLP Assignment 2",
            "text": "NLP Assignment 2 must submit by 25 October 2026.",
        },
        "m",
    )
    engine.process(owner, message)
    assert store.list(owner, "assignment")[0]["relevance"] == "applicable"
