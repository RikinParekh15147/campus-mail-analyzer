"""PIPE-01 evidence boundary regressions."""

import pytest

from campusmail.candidates import Evidence, FieldAssertion, adapt_legacy_analysis
from campusmail.engine import Engine
from campusmail.personalization import Personalizer
from campusmail.store import Store


def test_legacy_adapter_checks_exact_body_and_subject_spans():
    body = "Submit by 25 October 2026."
    subject = "Assignment 2 due 26 October 2026"
    analysis = {
        "dates": [{"start": 10, "end": 25, "text": "25 October 2026",
                   "normalized": "2026-10-25", "role": "assignment_deadline"}],
        "subject_dates": [{"start": 17, "end": 32, "text": "26 October 2026",
                           "normalized": "2026-10-26", "role": "assignment_deadline"}],
    }
    adapted = adapt_legacy_analysis("message-1", body, subject, analysis)
    assert adapted["dates"] == analysis["dates"]
    assert {a["evidence"]["field"] for a in adapted["field_assertions"]} == {
        "body", "subject"
    }
    analysis["dates"][0]["start"] = 11
    with pytest.raises(ValueError, match="span"):
        adapt_legacy_analysis("message-1", body, subject, analysis)


def test_unvalidated_rule_confidence_is_rejected():
    evidence = Evidence("message-1", "body", 0, 6, "Submit")
    with pytest.raises(ValueError, match="calibrated"):
        FieldAssertion("actions.status", "required", evidence,
                       "local_rules", "v1", calibrated_score=0.99).validate(
                           {"body": "Submit"})
    with pytest.raises(ValueError, match="JSON-compatible"):
        FieldAssertion("actions.status", {"bad"}, evidence,
                       "local_rules", "v1").validate({"body": "Submit"})


def test_engine_persists_corrected_date_assertion_with_source_evidence(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    message = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2",
        "text": "NLP201 Assignment 2 must submit by 25 October 2026.",
        "sent_at": "2026-10-01T09:00:00+05:30",
        "date_corrections": {"35": {"date": "2026-10-27",
                                    "role": "assignment_deadline"}},
    }, "notice")
    Engine(store).process(owner, message)
    analysis = store.get(owner, message["id"])["analysis"]
    date_assertion = next(a for a in analysis["field_assertions"]
                          if a["field"] == "dates.normalized")
    assert date_assertion["value"] == "2026-10-27"
    assert date_assertion["method"] == "user_confirmed"
    assert date_assertion["method_version"] == "personal-review-v1"
    evidence = date_assertion["evidence"]
    assert evidence["document_id"] == message["id"]
    assert message["text"][evidence["start"]:evidence["end"]] == evidence["text"]


def test_cancelled_statuses_keep_target_clause_evidence(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store)
    notices = [
        ("assignment", "NLP201 Assignment 2 is cancelled."),
        ("event", "Python Workshop is cancelled."),
    ]
    for key, body in notices:
        if key == "event":
            original = store.put(owner, "message", {
                "subject": "Python Workshop",
                "text": "Python Workshop will be held on 25 October 2026.",
                "sent_at": "2026-09-30T09:00:00+05:30",
            }, "event-original")
            engine.process(owner, original)
        message = store.put(owner, "message", {
            "subject": "Python Workshop" if key == "event" else "NLP201 assignments",
            "text": body, "sent_at": "2026-10-01T09:00:00+05:30",
        }, key)
        engine.process(owner, message)
        record = next(item for item in store.list(owner, key)
                      if item["status"] == "cancelled")
        assertion = record["field_evidence"]["status"]
        evidence = assertion["evidence"]
        assert evidence["document_id"] == message["id"]
        assert body[evidence["start"]:evidence["end"]] == evidence["text"]
        assert "cancelled" in evidence["text"]


def test_profile_value_span_and_confirmation_survive_replay(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    body = "My roll number is 23BIT044. I am enrolled in NLP201."
    message = store.put(owner, "message", {"subject": "Profile", "text": body},
                        "profile")
    engine = Engine(store)
    engine.process(owner, message)
    roll = next(item for item in store.list(owner, "profile_fact")
                if item["field"] == "roll_number")
    evidence = roll["field_evidence"]["value"]["evidence"]
    assert body[evidence["start"]:evidence["end"]] == "23BIT044"
    Personalizer(store).feedback(owner, roll["id"], "value", "23BIT044")
    engine.process(owner, message)
    assert store.get(owner, roll["id"])["field_evidence"]["value"]["origin"] == \
        "user_confirmed"
