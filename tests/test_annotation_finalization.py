"""Synthetic review handoff checks; no corpus example is treated as gold."""

import json

import pytest

from campusmail.research.contracts import ResearchDocument
from campusmail.research.files import file_sha256
from scripts.finalize_annotation_pilot import finalize_pilot


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def setup_pilot(tmp_path):
    reservation = tmp_path / "reservation"
    pilot = tmp_path / "pilot"
    reservation.mkdir()
    pilot.mkdir()
    pack = [
        {"review_id": f"review-{i}", "guard_token": f"guard-{i}",
         "subject": "", "text": f"Submit assignment {i}.",
         "text_status": "available", "sent_at": None, "timezone": None,
         "context_cutoff_at": None, "context_review_ids": [],
         "parent_review_id": None}
        for i in range(2)
    ]
    write_jsonl(reservation / "development_pack.jsonl", pack)
    blank = {}
    for owner in ("reviewer_a", "reviewer_b"):
        blank[owner] = [
            {"review_id": row["review_id"], "form_owner": owner,
             "reviewer_id": None, "guide_version": "0.1",
             "complete_fields": [], "primary_category": None,
             "secondary_categories": [], "actions": [], "dates": [],
             "entities": [], "relationships": [], "reply_state": None,
             "notes": ""}
            for row in pack
        ]
        write_jsonl(pilot / f"{owner}.jsonl", blank[owner])
    guide = "dataset/ANNOTATION_GUIDE.md"
    (pilot / "pilot_manifest.json").write_text(json.dumps({
        "development_pack_sha256": file_sha256(reservation / "development_pack.jsonl"),
        "guide_sha256": file_sha256(guide), "pilot_rows": 2,
        "independent_guards": 2,
        "form_sha256": {owner: file_sha256(pilot / f"{owner}.jsonl")
                        for owner in blank},
    }), encoding="utf-8")
    completed = {}
    for owner, reviewer in (("reviewer_a", "alice"), ("reviewer_b", "bob")):
        rows = [dict(row, reviewer_id=reviewer,
                     complete_fields=["classification"],
                     primary_category="assignments") for row in blank[owner]]
        rows[1]["complete_fields"] = ["classification", "actions"]
        if owner == "reviewer_b":
            rows[0]["primary_category"] = "examinations"
        completed[owner] = tmp_path / f"{owner}_completed.jsonl"
        write_jsonl(completed[owner], rows)
    adjudication = tmp_path / "adjudication.jsonl"
    write_jsonl(adjudication, [{
        "review_id": "review-0", "disputed_tasks": ["classification"],
        "adjudicator_id": "carol", "reason": "The main purpose is submission.",
        "final_decisions_recorded": True,
        "decisions": {"classification": {
            "primary_category": "assignments", "secondary_categories": []}},
    }])
    return reservation, pilot, completed, adjudication


def finalize(paths, tmp_path, name="published"):
    reservation, pilot, completed, adjudication = paths
    return finalize_pilot(reservation, pilot, completed["reviewer_a"],
                          completed["reviewer_b"], adjudication,
                          tmp_path / name, private_root=tmp_path)


def test_finalization_requires_real_double_review_and_resolves_disputes(tmp_path):
    paths = setup_pilot(tmp_path)
    manifest = finalize(paths, tmp_path)
    assert manifest["pilot_rows"] == manifest["independent_guards"] == 2
    assert manifest["disputed_documents"] == 1
    assert manifest["complete_task_counts"] == {"classification": 2, "actions": 1}
    assert manifest["primary_category_counts"] == {"assignments": 2}
    output = tmp_path / "published"
    assert manifest["reviewed_development_sha256"] == file_sha256(
        output / "reviewed_development.jsonl")
    docs = [ResearchDocument.model_validate(json.loads(line)) for line in
            (output / "reviewed_development.jsonl").read_text().splitlines()]
    assert all(doc.gold_eligible("classification") for doc in docs)
    assert not docs[0].gold_eligible("actions")
    assert docs[1].gold_eligible("actions") and docs[1].actions == []
    assert docs[0].annotation_status.classification.reviewer_ids == ["alice", "bob"]
    assert docs[0].annotation_status.classification.adjudication == "resolved"
    assert docs[0].annotation_status.classification.adjudicator_id == "carol"
    assert docs[1].annotation_status.classification.adjudication == "not_required"


def test_finalization_rejects_incomplete_and_nonindependent_review(tmp_path):
    paths = setup_pilot(tmp_path)
    reservation, pilot, completed, adjudication = paths
    rows = [json.loads(line) for line in completed["reviewer_b"].read_text().splitlines()]
    rows[1]["complete_fields"] = []
    rows[1]["primary_category"] = None
    write_jsonl(completed["reviewer_b"], rows)
    with pytest.raises(ValueError, match="finish every classification"):
        finalize(paths, tmp_path)
    assert not (tmp_path / "published").exists()
    rows[1]["complete_fields"] = ["classification", "actions"]
    rows[1]["primary_category"] = "assignments"
    rows[1]["reviewer_id"] = "another-person"
    write_jsonl(completed["reviewer_b"], rows)
    with pytest.raises(ValueError, match="consistent human reviewer"):
        finalize(paths, tmp_path)
    for row in rows:
        row["reviewer_id"] = "alice"
    write_jsonl(completed["reviewer_b"], rows)
    with pytest.raises(ValueError, match="independent"):
        finalize(paths, tmp_path)
    assert not (tmp_path / "published").exists()


def test_finalization_rejects_missing_or_invalid_adjudication(tmp_path):
    paths = setup_pilot(tmp_path)
    adjudication = paths[3]
    write_jsonl(adjudication, [])
    with pytest.raises(ValueError, match="lacks adjudication"):
        finalize(paths, tmp_path)
    row = {"review_id": "review-0", "disputed_tasks": ["classification"],
           "adjudicator_id": "alice", "reason": "reason",
           "final_decisions_recorded": True,
           "decisions": {"classification": {
               "primary_category": "assignments", "secondary_categories": []}}}
    write_jsonl(adjudication, [row])
    with pytest.raises(ValueError, match="not independent"):
        finalize(paths, tmp_path)
    row["adjudicator_id"] = "carol"
    row["decisions"]["classification"]["primary_category"] = "invalid"
    write_jsonl(adjudication, [row])
    with pytest.raises(ValueError):
        finalize(paths, tmp_path)
    assert not (tmp_path / "published").exists()
