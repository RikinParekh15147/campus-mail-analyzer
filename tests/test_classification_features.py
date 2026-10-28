"""CLS-01 fold-local vocabulary and independently ablatable channels."""

import json

import pytest

from campusmail.classification import (
    FEATURE_CONTRACT_VERSION, FEATURE_VARIANTS, FeatureSpec,
    build_features, validate_feature_rows,
)
from campusmail.preprocessing import PREPROCESSING_VERSION
from campusmail.training import load_rows


def test_training_loader_retains_source_channels_only_when_requested(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text(json.dumps({
        "subject": "NLP201 deadline",
        "text": "> Old notice.\nStudents must not submit tomorrow.",
        "label": "assignments", "leakage_group_id": "group-1",
    }) + "\n")
    standard = load_rows(path)
    feature = load_rows(path, include_channels=True)
    assert set(standard[0]) == {"text", "label", "group"}
    assert feature[0]["text"] == standard[0]["text"]
    assert feature[0]["subject_text"] == "NLP201 deadline"
    assert "Old notice" not in feature[0]["body_text"]
    assert feature[0]["preprocessing_version"] == PREPROCESSING_VERSION
    assert FEATURE_CONTRACT_VERSION == "sparse-channels-v1"


def test_word_character_and_channel_vocabulary_fit_only_training_rows():
    rows = [
        {"text": "NLP201 must not submit by 25 October 2026",
         "subject_text": "NLP201 assignment", "body_text": "must not submit by 25 October 2026",
         "preprocessing_version": PREPROCESSING_VERSION},
        {"text": "Python Workshop held tomorrow",
         "subject_text": "Python Workshop", "body_text": "held tomorrow",
         "preprocessing_version": PREPROCESSING_VERSION},
    ]
    held_out = {"text": "CANARYTOKEN unrelated text",
                "subject_text": "CANARYTOKEN", "body_text": "unrelated text",
                "preprocessing_version": PREPROCESSING_VERSION}
    spec = FEATURE_VARIANTS["all_channels"]
    validate_feature_rows(rows, spec)
    features = build_features(spec).fit(rows)
    assert features.transform([held_out]).shape[1] == features.transform(rows).shape[1]
    word_vocab = features.transformer_list[0][1].named_steps["tfidf"].vocabulary_
    assert {"nlp201", "not", "2026", "tomorrow"} <= set(word_vocab)
    assert "canarytoken" not in word_vocab
    char_vocab = features.transformer_list[1][1].named_steps["tfidf"].vocabulary_
    assert char_vocab and all("canary" not in token for token in char_vocab)

    subject_only = build_features(FeatureSpec(subject=True)).fit(rows)
    body_only = build_features(FeatureSpec(body=True)).fit(rows)
    subject_vocab = subject_only.transformer_list[0][1].named_steps["tfidf"].vocabulary_
    body_vocab = body_only.transformer_list[0][1].named_steps["tfidf"].vocabulary_
    assert "assignment" in subject_vocab and "assignment" not in body_vocab
    assert "tomorrow" in body_vocab and "tomorrow" not in subject_vocab


def test_channel_preflight_rejects_missing_or_stale_contract():
    with pytest.raises(ValueError, match="at least one"):
        FeatureSpec()
    with pytest.raises(ValueError, match="version"):
        validate_feature_rows([{"text": "notice", "subject_text": "Subject",
                                "body_text": "Body", "preprocessing_version": "old"}],
                              FEATURE_VARIANTS["subject_body"])
    with pytest.raises(ValueError, match="Subject channel"):
        validate_feature_rows([{"text": "notice", "subject_text": "",
                                "body_text": "Body",
                                "preprocessing_version": PREPROCESSING_VERSION}],
                              FEATURE_VARIANTS["subject_body"])
