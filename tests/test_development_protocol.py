"""EVAL-01 fixture custody and fold checks; no corpus labels are used."""

import json

import pytest

from campusmail.research.development_protocol import (
    freeze_development_selection, verify_development_selection,
)
from campusmail.research.files import file_sha256
from campusmail.research.runtime_eval import evaluate_development_runtime
from campusmail.research.source_policy import SPLIT_POLICY_VERSION, expected_split


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def fixture(tmp_path):
    reservation = tmp_path / "reservation"
    reservation.mkdir()
    guards = [f"guard-{i}" for i in range(20)
              if expected_split("academic", f"guard-{i}") == "development"][:2]
    allocation = [{"guard_id": guard, "task": "academic", "split": "development"}
                  for guard in guards]
    identities = [{"review_id": f"review-{i}", "source_name": "scoped",
                   "provisional_split_guard_id": guard, "dataset_id": "original-source",
                   "document_id": f"original-{i}"}
                  for i, guard in enumerate(guards)]
    _write_jsonl(reservation / "allocation.jsonl", allocation)
    _write_jsonl(reservation / "private_identity_map.jsonl", identities)
    _write_jsonl(reservation / "development_pack.jsonl",
                 [{"review_id": row["review_id"],
                   "subject": "", "text": f"Assignment {i} due tomorrow.",
                   "text_status": "available", "sent_at": None,
                   "context_cutoff_at": None, "timezone": None,
                   "context_review_ids": [], "parent_review_id": None}
                  for i, row in enumerate(identities)])
    hashes = {name: file_sha256(reservation / name) for name in
              ("allocation.jsonl", "private_identity_map.jsonl", "development_pack.jsonl")}
    (reservation / "reservation_report.json").write_text(json.dumps({
        "status": "valid", "policy_version": SPLIT_POLICY_VERSION,
        "total_guards": 2, "development_pack_rows": 2,
        "file_sha256": hashes, "membership_sha256": "fixture-only",
    }), encoding="utf-8")
    reviewed = {"completeness": "complete", "provenance": "human_reviewed",
                "reviewer_ids": ["alice", "bob"]}
    input_path = tmp_path / "reviewed.jsonl"
    _write_jsonl(input_path, [
        {"schema_version": "2.0", "dataset_id": "pilot-development-v1",
         "document_id": f"review-{i}", "task": "academic",
         "data_origin": "designated_research", "source_type": "pilot_review",
         "text": f"Assignment {i} due tomorrow.",
         "primary_category": "assignments",
         "annotation_status": {"classification": reviewed}}
        for i in range(2)
    ])
    return input_path, reservation


def test_protocol_maps_blinded_ids_to_pinned_guards_and_reports_support(tmp_path):
    input_path, reservation = fixture(tmp_path)
    manifest = freeze_development_selection(input_path, reservation, fixture_mode=True)
    assert manifest["schema_version"] == "development-selection-v2"
    assert manifest["dataset_id"] == "pilot-development-v1"
    assert manifest["fold_count"] == 2
    assert set(manifest["guard_folds"].values()) == {0, 1}
    assert manifest["support"]["class_documents"]["assignments"] == 2
    assert manifest["support"]["class_guards"]["assignments"] == 2
    assert "scholarships" in manifest["support"]["missing_classes"]
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert verify_development_selection(input_path, path, reservation, fixture_mode=True) == manifest


def test_protocol_rejects_tampered_fold_and_identity_map(tmp_path):
    input_path, reservation = fixture(tmp_path)
    manifest = freeze_development_selection(input_path, reservation, fixture_mode=True)
    path = tmp_path / "selection.json"
    manifest["guard_folds"][next(iter(manifest["guard_folds"]))] = 99
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from accepted"):
        verify_development_selection(input_path, path, reservation, fixture_mode=True)
    identities = reservation / "private_identity_map.jsonl"
    identities.write_text(identities.read_text() + "{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sidecar changed"):
        freeze_development_selection(input_path, reservation, fixture_mode=True)


def test_protocol_requires_two_double_reviewed_guards(tmp_path):
    input_path, reservation = fixture(tmp_path)
    rows = [json.loads(line) for line in input_path.read_text().splitlines()]
    rows[1]["annotation_status"]["classification"]["reviewer_ids"] = ["alice"]
    _write_jsonl(input_path, rows)
    with pytest.raises(ValueError, match="double-reviewed"):
        freeze_development_selection(input_path, reservation, fixture_mode=True)


def test_protocol_rejects_review_id_reassigned_to_other_text(tmp_path):
    input_path, reservation = fixture(tmp_path)
    rows = [json.loads(line) for line in input_path.read_text().splitlines()]
    rows[0]["text"] = "Different notice text."
    _write_jsonl(input_path, rows)
    with pytest.raises(ValueError, match="differs from the pinned"):
        freeze_development_selection(input_path, reservation, fixture_mode=True)


def test_runtime_wrapper_enforces_pinned_selection_and_reports_exclusions(tmp_path):
    input_path, reservation = fixture(tmp_path)
    manifest = freeze_development_selection(input_path, reservation, fixture_mode=True)
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps(manifest), encoding="utf-8")
    report = evaluate_development_runtime(
        input_path, selection, reservation,
        expected_input_sha256=file_sha256(input_path),
        expected_selection_sha256=file_sha256(selection), fixture_mode=True)
    assert report["label_status"] == "synthetic_fixture"
    assert report["selection_support"]["independent_guards"] == 2
    assert report["prepared_scenarios"] == 0
    assert report["excluded"] == {"entities_or_dates_not_double_reviewed": 2}
    with pytest.raises(ValueError, match="Pinned runtime evaluation input changed"):
        evaluate_development_runtime(
            input_path, selection, reservation,
            expected_input_sha256="0" * 64,
            expected_selection_sha256=file_sha256(selection), fixture_mode=True)
