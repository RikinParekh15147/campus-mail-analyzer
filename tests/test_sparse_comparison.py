"""Paired sparse comparisons keep guard boundaries and avoid promotion."""

from copy import deepcopy
import json

import pytest

from campusmail.preprocessing import PREPROCESSING_VERSION
from campusmail.research.development_protocol import freeze_development_selection
from campusmail.research.files import file_sha256
from campusmail.research.source_policy import SPLIT_POLICY_VERSION, expected_split
from campusmail.research.sparse_comparison import (
    CANDIDATES, compare_reviewed_development, compare_sparse_models,
)


def _reviewed_rows():
    rows = []
    for fold in range(3):
        for label, topic in (("assignments", "submit assignment"),
                             ("workshops_events", "attend seminar")):
            for variant in range(2):
                rows.append({
                    "document_id": f"{fold}-{label}-{variant}",
                    "group": f"guard-{fold}-{label}",
                    "label": label,
                    "text": f"NLP20{fold} {topic} on October {variant + 10}",
                    "subject_text": f"NLP20{fold} {topic}",
                    "body_text": f"Please {topic} on October {variant + 10}",
                    "preprocessing_version": PREPROCESSING_VERSION,
                })
    folds = {f"guard-{fold}-{label}": fold
             for fold in range(3) for label in ("assignments", "workshops_events")}
    return rows, folds


def test_candidates_use_paired_out_of_fold_predictions_without_selection():
    rows, folds = _reviewed_rows()
    report = compare_sparse_models(rows, folds)
    assert report == compare_sparse_models(list(reversed(rows)), folds)
    assert report["selection"] is None
    assert set(report["candidates"]) == {candidate.name for candidate in CANDIDATES}
    assert {report["folds"][row["document_id"]] for row in rows} == {0, 1, 2}
    assert all(set(candidate["predictions"]) == set(report["folds"])
               for candidate in report["candidates"].values())
    assert report["candidates"]["linear_svm_word_char_balanced"]["class_weight"] == "balanced"
    assert report["candidates"]["linear_svm_word_char_masked"]["mask_identifiers"]


def test_comparison_rejects_guard_leakage_and_stale_preprocessing():
    rows, folds = _reviewed_rows()
    bad = deepcopy(rows)
    bad[0]["document_id"] = bad[1]["document_id"]
    with pytest.raises(ValueError, match="unique"):
        compare_sparse_models(bad, folds)
    with pytest.raises(ValueError, match="guards"):
        compare_sparse_models(rows, {**folds, "unseen-guard": 0})
    bad = deepcopy(rows)
    bad[0]["preprocessing_version"] = "old"
    with pytest.raises(ValueError, match="preprocessing"):
        compare_sparse_models(bad, folds)
    with pytest.raises(ValueError, match="two training classes"):
        compare_sparse_models(rows, {guard: (0 if "assignments" in guard else 1)
                                     for guard in folds})


def test_reviewed_wrapper_requires_verified_development_custody(tmp_path):
    def write_jsonl(path, values):
        path.write_text("".join(json.dumps(value) + "\n" for value in values))

    reservation = tmp_path / "reservation"
    reservation.mkdir()
    guards = [f"guard-{index}" for index in range(100)
              if expected_split("academic", f"guard-{index}") == "development"][:2]
    allocation = [{"guard_id": guard, "task": "academic", "split": "development"}
                  for guard in guards]
    identities, pack, reviewed = [], [], []
    for index, guard in enumerate(guards):
        for label, content in (("assignments", "Submit the assignment on Friday."),
                               ("workshops_events", "Attend the seminar on Friday.")):
            review_id = f"review-{index}-{label}"
            identities.append({"review_id": review_id, "source_name": "scoped",
                               "provisional_split_guard_id": guard})
            pack.append({"review_id": review_id, "subject": f"NLP20{index} {label}",
                         "text": content, "text_status": "available",
                         "sent_at": None, "context_cutoff_at": None,
                         "timezone": None, "context_review_ids": [],
                         "parent_review_id": None})
            reviewed.append({"schema_version": "2.0", "dataset_id": "fixture-only",
                             "document_id": review_id, "task": "academic",
                             "data_origin": "designated_research", "source_type": "pilot_review",
                             "subject": f"NLP20{index} {label}", "text": content,
                             "primary_category": label,
                             "annotation_status": {"classification": {
                                 "completeness": "complete", "provenance": "human_reviewed",
                                 "reviewer_ids": ["alice", "bob"]}}})
    for name, values in (("allocation.jsonl", allocation),
                         ("private_identity_map.jsonl", identities),
                         ("development_pack.jsonl", pack)):
        write_jsonl(reservation / name, values)
    hashes = {name: file_sha256(reservation / name) for name in
              ("allocation.jsonl", "private_identity_map.jsonl", "development_pack.jsonl")}
    (reservation / "reservation_report.json").write_text(json.dumps({
        "status": "valid", "policy_version": SPLIT_POLICY_VERSION,
        "total_guards": 2, "development_pack_rows": 4,
        "file_sha256": hashes, "membership_sha256": "fixture-only",
    }))
    source = tmp_path / "reviewed.jsonl"
    write_jsonl(source, reviewed)
    manifest = freeze_development_selection(source, reservation, fixture_mode=True)
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps(manifest))
    report = compare_reviewed_development(source, selection, reservation,
                                          fixture_mode=True)
    assert report["selection"] is None
    assert report["support"]["documents"] == 4
    assert report["custody"]["input_sha256"] == file_sha256(source)
    altered = deepcopy(manifest)
    altered["guard_folds"][guards[0]] = 99
    selection.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="differs from accepted"):
        compare_reviewed_development(source, selection, reservation, fixture_mode=True)
