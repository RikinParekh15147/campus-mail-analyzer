"""EVAL-02 synthetic contract checks; these are not reviewed dataset scores."""

import pytest

from campusmail.research.metrics import evaluate_reviewed_components


def reviewed():
    return {"completeness": "complete", "provenance": "human_reviewed",
            "reviewer_ids": ["fixture-reviewer"]}


def document(**changes):
    return {
        "schema_version": "2.0", "dataset_id": "synthetic-metric-fixture",
        "document_id": "fixture-1", "task": "academic",
        "data_origin": "designated_research", "source_type": "fixture",
        "text": "Submit by 25 October 2026.",
        **changes,
    }


def test_complete_fields_score_once_and_unreviewed_fields_do_not_become_negatives():
    text = "Submit by 25 October 2026."
    start = text.index("25")
    date = {"field": "text", "start": start, "end": start + 15,
            "text": "25 October 2026"}
    action = {"field": "text", "start": 0, "end": 6, "text": "Submit"}
    gold = document(
        primary_category="assignments",
        annotation_status={"classification": reviewed(), "dates": reviewed(),
                           "actions": reviewed()},
        dates=[{"evidence": date, "role": "assignment_deadline",
                "normalized_value": "2026-10-25", "precision": "date"}],
        actions=[{"evidence": action, "actor": "student", "action_type": "submit",
                  "action_status": "required"}],
    )
    prediction = {
        "category": "assignments",
        "dates": [{**date, "role": "assignment_deadline", "normalized": "2026-10-25"}],
        "actions": [{**action, "actor": "student", "status": "required"}],
    }
    unreviewed = document(document_id="fixture-2", text="Please submit soon.")
    result = evaluate_reviewed_components([
        (gold, prediction),
        (unreviewed, {"category": "administration", "actions": [
            {"field": "text", "start": 7, "end": 13, "text": "submit"}
        ]}),
    ])
    assert result["eligible_documents"] == {"classification": 1, "dates": 1, "actions": 1}
    assert result["classification"]["accuracy"] == 1
    assert result["strict_spans"]["dates"]["tp"] == 1
    assert result["strict_spans"]["actions"]["fp"] == 0
    assert result["date_role_and_span"]["f1"] == 1
    assert result["date_normalization_exact_span_accuracy"] == 1
    assert result["action_status_exact_span_accuracy"] == 1
    assert result["action_actor_exact_span_accuracy"] == 1
    assert "examinations" in result["classification"]["unsupported_classes"]


def test_duplicate_predictions_are_false_positives_and_invalid_offsets_fail():
    text = "Submit by 25 October 2026."
    start = text.index("25")
    date = {"field": "text", "start": start, "end": start + 15,
            "text": "25 October 2026"}
    gold = document(
        annotation_status={"dates": reviewed()},
        dates=[{"evidence": date, "role": "assignment_deadline",
                "normalized_value": "2026-10-25", "precision": "date"}],
    )
    prediction = {"dates": [date, date]}
    result = evaluate_reviewed_components([(gold, prediction)])
    assert result["strict_spans"]["dates"]["tp"] == 1
    assert result["strict_spans"]["dates"]["fp"] == 1
    with pytest.raises(ValueError, match="Invalid predicted dates evidence span"):
        evaluate_reviewed_components([(gold, {"dates": [{**date, "text": "wrong"}]})])


def test_synthetic_and_quarantined_rows_are_excluded_from_scoring():
    rows = [
        document(document_id="synthetic", data_origin="synthetic"),
        document(document_id="quarantined", usage_status="quarantined"),
    ]
    result = evaluate_reviewed_components((row, {}) for row in rows)
    assert result["documents_seen"] == 0
    assert result["excluded"]["source_policy"] == 2
    assert result["classification"]["accuracy"] is None


def test_unreviewed_prediction_still_requires_valid_evidence():
    with pytest.raises(ValueError, match="Invalid predicted dates evidence span"):
        evaluate_reviewed_components([
            (document(), {"dates": [{"field": "text", "start": 0, "end": 6,
                                    "text": "Not it"}]})
        ])
