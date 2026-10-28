"""FIX-02 source-aligned ranges and unsupported temporal cues."""

import pytest

from campusmail.engine import Engine
from campusmail.nlp import analyze
from campusmail.store import Store


@pytest.mark.parametrize("expression", [
    "October 25-27, 2026", "25-27 October 2026", "Oct 25 to 27 2026",
])
def test_compact_same_month_range_has_one_candidate_without_single_date_overlap(expression):
    text = f"Workshop runs from {expression}."
    result = analyze(text)
    assert result["dates"] == []
    assert len(result["date_ranges"]) == 1
    item = result["date_ranges"][0]
    assert text[item["start"]:item["end"]] == expression
    assert (item["start_date"], item["end_date"]) == ("2026-10-25", "2026-10-27")
    assert item["needs_review"] and result["needs_review"]


@pytest.mark.parametrize("expression", [
    "October 25-27", "October 30-32, 2026",
    "October 30 to November 2, 2026",
    "25 October 2026 to 27 November 2026",
])
def test_missing_invalid_or_cross_month_range_remains_unresolved(expression):
    text = f"Workshop runs {expression}."
    result = analyze(text)
    assert result["dates"] == []
    assert len(result["date_ranges"]) == 1
    item = result["date_ranges"][0]
    assert item["start_date"] is None and item["end_date"] is None
    assert item["needs_review"]


def test_engine_does_not_commit_range_endpoint_as_assignment_deadline(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store)
    message = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2",
        "text": "NLP201 Assignment 2 submissions are open October 25-27, 2026.",
    }, "range")
    engine.process(owner, message)
    assignment = store.list(owner, "assignment")[0]
    assert assignment.get("due_date") is None
    analyzed = store.get(owner, message["id"])["analysis"]
    assert analyzed["dates"] == []
    assert analyzed["date_ranges"][0]["end_date"] == "2026-10-27"
    questions = [row for row in store.list(owner, "review")
                 if row["status"] == "open" and row["source_key"].startswith("temporal:")]
    assert len(questions) == 1
    assert questions[0]["context"]["text"] == "October 25-27, 2026"
    assert questions[0]["field"] is None
    engine.process(owner, store.get(owner, message["id"]))
    assert len([row for row in store.list(owner, "review")
                if row["source_key"].startswith("temporal:")]) == 1


def test_subject_range_and_unsupported_relative_cue_create_review(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store)
    message = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2: October 25-27, 2026",
        "text": "NLP201 Assignment 2 must submit by next Friday.",
    }, "subject-range")
    engine.process(owner, message)
    result = store.get(owner, message["id"])["analysis"]
    assert result["subject_dates"] == []
    assert result["subject_date_ranges"][0]["field"] == "subject"
    assert result["temporal_warnings"][0]["text"] == "next Friday"
    assert store.list(owner, "assignment")[0].get("due_date") is None
    questions = [row for row in store.list(owner, "review")
                 if row["status"] == "open" and row["source_key"].startswith("temporal:")]
    assert len(questions) == 2


def test_ambiguous_time_range_is_not_used_as_a_due_time():
    text = "NLP201 Assignment 2 deadline 10-11 AM on 25 October 2026."
    result = analyze(text)
    assert result["times"] == []
    assert result["dates"][0]["normalized"] == "2026-10-25"
    assert result["temporal_warnings"][0]["reason"] == "Time range needs explicit endpoint meridiems"
    assert result["needs_review"]


def test_time_only_deadline_needs_calendar_date():
    result = analyze("NLP201 Assignment 2 is due at 5 PM.")
    assert result["dates"] == []
    assert result["times"][0]["time"] == "17:00:00"
    assert result["temporal_warnings"][0]["reason"] == "Time has no calendar date"
    assert result["needs_review"]


def test_month_first_date_and_mixed_time_formats_keep_source_offsets():
    text = ("NLP201 Assignment 2 due October 25, 2026 at 5:30 PM. "
            "Workshop starts at 14:00 on 26 October 2026.")
    result = analyze(text)
    assert [(item["text"], item["normalized"]) for item in result["dates"]] == [
        ("October 25, 2026", "2026-10-25"),
        ("26 October 2026", "2026-10-26"),
    ]
    assert [(item["text"], item["time"]) for item in result["times"]] == [
        ("5:30 PM", "17:30:00"), ("14:00", "14:00:00"),
    ]
    for item in result["dates"] + result["times"]:
        assert text[item["start"]:item["end"]] == item["text"]


def test_time_before_date_and_subject_only_date_are_applied_singly(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store)
    first = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2",
        "text": "NLP201 Assignment 2 must submit by 5:30 PM on 25 October 2026.",
    }, "time-before")
    engine.process(owner, first)
    assert store.list(owner, "assignment")[0]["due_at"] == "2026-10-25T17:30:00+05:30"
    second = store.put(owner, "message", {
        "subject": "NLP201 Assignment 3 due on October 25, 2026",
        "text": "Please submit the assignment.",
    }, "subject-only")
    engine.process(owner, second)
    item = next(row for row in store.list(owner, "assignment")
                if row["assignment_number"] == "3")
    assert item["due_date"] == "2026-10-25"
    result = store.get(owner, second["id"])["analysis"]
    assert result["dates"] == []
    assert len(result["subject_dates"]) == 1
    assert result["subject_dates"][0]["field"] == "subject"


def test_single_month_first_date_without_year_is_unresolved():
    result = analyze("NLP201 Assignment 2 due October 25.")
    assert result["dates"][0]["normalized"] is None
    assert result["dates"][0]["reason"] == "Missing year"


@pytest.mark.parametrize("cue", ["by Friday", "within 3 days", "EOD", "end of week"])
def test_unsupported_relative_deadline_wording_is_flagged(cue):
    result = analyze(f"NLP201 Assignment 2 must submit {cue}.")
    assert result["dates"] == []
    assert result["needs_review"]
    assert any(item["text"] == cue for item in result["temporal_warnings"])
