from campusmail.evaluation import evaluate_extraction


def test_extraction_agreement_reports_exact_spans_and_roles():
    text = "Please submit by 25 October 2026."
    start = text.index("25")
    row = {
        "text": text,
        "dates": [
            {
                "start": start,
                "end": start + 15,
                "role": "assignment_deadline",
                "normalized_value": "2026-10-25",
            }
        ],
        "actions": [{"start": 0, "end": len(text)}],
        "human_reviewed": False,
    }
    result = evaluate_extraction([row])
    assert result["dates"]["f1"] == 1
    assert result["actions"]["f1"] == 1
    assert result["date_role_accuracy"] == 1
    assert result["label_status"] == "provisional_source_agreement"


def test_empty_reviewed_set_is_not_reported_as_measured_accuracy():
    result = evaluate_extraction(
        [{"text": "No annotations", "human_reviewed": False}], reviewed_only=True
    )
    assert result["documents"] == 0
    assert result["date_role_accuracy"] is None
    assert result["dates"]["f1"] is None
