from campusmail.store import Store
from campusmail.engine import Engine
from campusmail.trackers import Grades


def test_same_text_in_different_files_is_flagged_without_losing_originals(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    first = engine.resource(
        owner,
        {"text": "NLP201 assignment instructions", "filename": "one.pdf"},
        "file-one",
    )
    second = engine.resource(
        owner,
        {"text": "NLP201  assignment\n instructions", "filename": "two.docx"},
        "file-two",
    )
    assert first["id"] != second["id"]
    assert second["duplicate_of"] == first["id"]
    assert second["redundancy"] == "same_text"


def test_multi_assessment_marks_row_requires_column_review(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    engine = Engine(store)
    engine.fact(owner, "roll_number", "23BIT044", "user", True)
    assert (
        Grades(store).extract(
            owner, "23BIT044 80/100 90/100", "NLP201", "Midsem", "source"
        )
        == []
    )
    assert store.list(owner, "review")
