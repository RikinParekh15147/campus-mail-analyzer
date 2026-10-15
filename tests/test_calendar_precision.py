from datetime import date
from campusmail.store import Store
from campusmail.engine import Engine
from campusmail.calendar import Calendar
from campusmail.trackers import Grades


def test_assignment_time_is_preserved_without_becoming_a_busy_block(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    engine.fact(owner, "enrollment:NLP201", True, "user", True)
    m = store.put(
        owner,
        "message",
        {
            "subject": "NLP201 Assignment 2",
            "text": "NLP201 Assignment 2 must submit by 25 October 2026 at 5:00 PM.",
        },
        "m",
    )
    engine.process(owner, m)
    item = store.list(owner, "assignment")[0]
    assert item["due_at"] == "2026-10-25T17:00:00+05:30"
    assert (
        Calendar(store).entries(owner, date(2026, 10, 25), date(2026, 10, 25))[0][
            "blocks_time"
        ]
        is False
    )


def test_iso_date_is_supported():
    from campusmail.nlp import analyze

    dates = analyze("Please submit by 2026-10-25.")["dates"]
    assert dates[0]["normalized"] == "2026-10-25"


def test_marks_wait_for_confirmation_of_inferred_roll(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    engine.fact(owner, "roll_number", "23BIT044", "inference-one")
    engine.fact(owner, "roll_number", "23BIT044", "inference-two")
    assert (
        Grades(store).extract(owner, "23BIT044 80/100", "NLP201", "Quiz", "source")
        == []
    )
