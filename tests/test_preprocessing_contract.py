"""PIPE-02 source alignment and model-input parity across paths."""

import json
import pytest

from campusmail import nlp
from campusmail.preprocessing import PREPROCESSING_VERSION, prepare_document
from campusmail.training import load_rows
from campusmail.evaluation import evaluate_extraction


def test_regions_preserve_offsets_and_context_without_extracting_old_text():
    body = (
        "Submit the form by 25 October 2026.\n"
        "> Old deadline 20 October 2026.\n"
        "On Tue, 27 Oct 2026 at 10:00 Prof. Rao wrote:\n"
        "Old assignment due 28 October 2026."
    )
    prepared = prepare_document("NLP201 Assignment 2", body,
                                attachments=("Attachment deadline 29 October 2026.",))
    assert prepared.version == PREPROCESSING_VERSION
    assert len(prepared.body.canonical) == len(body)
    assert prepare_document("", prepared.body.canonical).body.canonical == \
        prepared.body.canonical
    assert {region.kind for region in prepared.body.regions} == {
        "quoted", "reply_history"
    }
    assert "20 October" not in prepared.body.canonical
    assert "28 October" not in prepared.body.canonical
    assert "28 October" in prepared.body.original
    start = body.index("25 October")
    assert prepared.body.source_span(start, start + len("25 October")) == (
        "body", start, start + len("25 October"), "25 October"
    )
    quoted_start = body.index("20 October")
    with pytest.raises(ValueError, match="masked"):
        prepared.body.source_span(quoted_start, quoted_start + len("20 October"))
    assert prepared.attachments[0].source_type == "attachment"
    assert prepared.attachments[0].field == "attachment:0"
    assert prepared.attachments[0].original.startswith("Attachment deadline")


def test_training_and_runtime_classifier_input_match(tmp_path, monkeypatch):
    subject = "NLP201 Assignment 2"
    body = "Submit by 25 October 2026.\n> Old due 20 October 2026.\n-- \nOld signature"
    source = tmp_path / "rows.jsonl"
    source.write_text(json.dumps({"subject": subject, "text": body,
                                  "label": "assignments"}) + "\n")
    training_text = load_rows(source)[0]["text"]
    seen = []

    class Model:
        def predict(self, inputs):
            seen.extend(inputs)
            return ["assignments"]

    model = tmp_path / "classifier.joblib"
    model.write_bytes(b"fixture")
    monkeypatch.setattr(nlp, "load_pipeline", lambda path, modified: Model())
    result = nlp.analyze(body, subject, model_path=model)
    assert seen == [training_text]
    assert result["preprocessing_version"] == PREPROCESSING_VERSION
    assert len(result["dates"]) == 1
    assert result["dates"][0]["text"] == "25 October 2026"


def test_quote_only_body_is_not_training_or_extraction_evaluation_input(tmp_path):
    row = {"subject": "Assignment 2", "text": "> Old due 25 October 2026.",
           "label": "assignments"}
    source = tmp_path / "rows.jsonl"
    source.write_text(json.dumps(row) + "\n")
    assert load_rows(source) == []
    assert evaluate_extraction([row])["documents"] == 0
