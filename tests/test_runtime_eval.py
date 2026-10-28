"""EVAL-03 synthetic replay scorer checks, never a reviewed accuracy run."""

import pytest

from campusmail.research.runtime_eval import evaluate_runtime_scenarios


def assignment_message(key, day, sent_day, wording):
    return {
        "source_key": key, "subject": "NLP201 Assignment 2",
        "text": f"NLP201 Assignment 2 {wording} {day} November 2026.",
        "sent_at": f"2026-10-{sent_day}T09:00:00+05:30",
    }


def test_runtime_checkpoints_count_entities_evidence_calendar_and_reminders():
    case = {
        "case_id": "deadline-replay",
        "confirmed_facts": {"enrollment:NLP201": True},
        "steps": [
            {"message": assignment_message("original", "25", "01", "must submit by"),
             "expect": {
                 "entities": [{"kind": "assignment", "anchor": "original",
                               "fields": {"due_date": "2026-11-25", "status": "open"},
                               "evidence": ["original"]}],
                 "actions": [{"anchor": "original", "start": 0, "end": 52,
                              "status": "required"}],
                 "action_complete_for": ["original"],
                 "calendar_window": ["2026-11-01", "2026-11-30"],
                 "calendar": [["assignment", "2026-11-25"]],
                 "reminder_clock": "2026-11-01T09:00:00+05:30",
                 "pending_reminders": ["2026-11-25", "2026-11-25"],
             }},
            {"message": assignment_message("update", "28", "02", "deadline extended to"),
             "expect": {
                 "entities": [{"kind": "assignment", "anchor": "original",
                               "fields": {"due_date": "2026-11-28", "status": "open"},
                               "evidence": ["original", "update"]}],
                 "calendar_window": ["2026-11-01", "2026-11-30"],
                 "calendar": [["assignment", "2026-11-28"]],
                 "reminder_clock": "2026-11-01T09:00:00+05:30",
                 "pending_reminders": ["2026-11-28", "2026-11-28"],
             }},
            {"replay": "original", "expect": {
                "entities": [{"kind": "assignment", "anchor": "original",
                              "fields": {"due_date": "2026-11-28"},
                              "evidence": ["original", "update"]}],
            }},
        ],
    }
    report = evaluate_runtime_scenarios([case])
    assert report["label_status"] == "synthetic_fixture"
    assert report["scenarios"] == 1
    assert report["checkpoints"] == 3
    assert report["error_counts"] == {}


def test_runtime_scorer_exposes_wrong_date_and_false_merge():
    report = evaluate_runtime_scenarios([{
        "case_id": "deliberate-mismatch", "steps": [
            {"message": assignment_message("one", "25", "01", "must submit by")},
            {"message": assignment_message("two", "28", "02", "deadline extended to"),
             "expect": {"entities": [
                 {"kind": "assignment", "anchor": "one",
                  "fields": {"due_date": "2026-11-30"}},
                 {"kind": "assignment", "anchor": "two"},
             ]}},
        ],
    }])
    assert report["error_counts"]["field_mismatch"] == 1
    assert report["error_counts"]["false_merge"] == 1
    assert "NLP201" not in str(report["errors"])


def test_runtime_scorer_rejects_missing_replay_source():
    with pytest.raises(ValueError, match="Replay source"):
        evaluate_runtime_scenarios([{
            "case_id": "invalid", "steps": [{"replay": "absent"}],
        }])


def test_runtime_scorer_checks_reply_state():
    report = evaluate_runtime_scenarios([{
        "case_id": "reply", "steps": [{
            "message": {"source_key": "request", "subject": "Report",
                        "text": "Can you send the report?", "thread_id": "thread-1"},
            "expect": {"reply_states": [{"anchor": "request", "state": "resolved"}]},
        }],
    }])
    assert report["error_counts"] == {"reply_state_mismatch": 1}


def test_runtime_scorer_counts_spurious_actions_only_when_complete():
    message = {"source_key": "notice", "subject": "Reminder",
               "text": "Please submit the form now."}
    incomplete = evaluate_runtime_scenarios([{
        "case_id": "unreviewed", "steps": [{"message": message, "expect": {}}],
    }])
    complete = evaluate_runtime_scenarios([{
        "case_id": "reviewed", "steps": [
            {"message": message, "expect": {"action_complete_for": ["notice"]}},
        ],
    }])
    assert incomplete["error_counts"] == {}
    assert complete["error_counts"]["spurious_action"] >= 1


def test_runtime_scorer_counts_a_protected_wrong_target_mutation():
    case = {"case_id": "protected-target", "steps": [
        {"message": assignment_message("original", "25", "01", "must submit by")},
        {"message": assignment_message("update", "28", "02", "deadline extended to"),
         "expect": {"preserve": [{"anchor": "original", "kind": "assignment",
                                   "match": {"title": "NLP201 Assignment 2"},
                                   "fields": ["due_date"]}]}},
    ]}
    result = evaluate_runtime_scenarios([case])
    assert result["error_counts"]["wrong_target_mutation"] == 1
    assert "NLP201" not in str(result["errors"])
