"""Validate independent DATA-06 pilot forms without manufacturing gold labels."""

import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from campusmail.research.contracts import ResearchDocument, TASKS
from campusmail.research.files import file_sha256, jsonl_records

FORM_KEYS = {
    "review_id", "form_owner", "reviewer_id", "guide_version",
    "complete_fields", "primary_category", "secondary_categories",
    "actions", "dates", "entities", "relationships", "reply_state", "notes",
}
TASK_VALUES = {
    "classification": ("primary_category", "secondary_categories"),
    "dates": ("dates",),
    "actions": ("actions",),
    "entities": ("entities",),
    "relationships": ("relationships",),
    "reply_state": ("reply_state",),
}


def read_index(path, identity_field):
    values = {}
    for line, row, _, error in jsonl_records(path):
        if error or row is None or identity_field not in row:
            raise ValueError(f"Invalid JSONL row {line} in {path.name}")
        key = row[identity_field]
        if not isinstance(key, str) or not key or key in values:
            raise ValueError(f"Duplicate/invalid identity in {path.name}")
        values[key] = row
    return values


def nonempty(value):
    return value is not None and value != []


def validate_form(row, pack_row, pack_ids, owner):
    if set(row) != FORM_KEYS or row["form_owner"] != owner or row["guide_version"] != "0.1":
        raise ValueError("Review form shape, owner or guide version mismatch")
    complete = row["complete_fields"]
    if not isinstance(complete, list) or len(complete) != len(set(complete)) or set(complete) - set(TASKS):
        raise ValueError("Invalid complete_fields")
    reviewer = row["reviewer_id"]
    if reviewer is not None and (not isinstance(reviewer, str) or not reviewer.strip()):
        raise ValueError("Invalid reviewer ID")
    if not isinstance(row["notes"], str):
        raise ValueError("Review notes must be text")
    for key in ("secondary_categories", "dates", "actions", "entities", "relationships"):
        if not isinstance(row[key], list):
            raise ValueError(f"{key} must be a list")
    if (complete or any(nonempty(row[key]) for keys in TASK_VALUES.values() for key in keys)) and not reviewer:
        raise ValueError("Entered review decisions require a reviewer ID")
    if "classification" in complete and row["primary_category"] is None:
        raise ValueError("Complete classification requires a primary category")
    if "reply_state" in complete and row["reply_state"] is None:
        raise ValueError("Complete reply-state review requires a state")
    relationships = []
    for item in row["relationships"]:
        if not isinstance(item, dict) or item.get("target_review_id") not in pack_ids:
            raise ValueError("Relationship target is absent from development pack")
        converted = dict(item)
        converted["target_document_id"] = converted.pop("target_review_id")
        relationships.append(converted)
    statuses = {}
    for task, keys in TASK_VALUES.items():
        has_values = any(nonempty(row[key]) for key in keys)
        completeness = "complete" if task in complete else "partial" if has_values else "unannotated"
        statuses[task] = {
            "completeness": completeness,
            "provenance": "human_reviewed" if completeness != "unannotated" else "unlabeled",
            "reviewer_ids": [reviewer] if completeness != "unannotated" else [],
        }
    document = {
        "schema_version": "2.0", "dataset_id": "pilot-development-v1",
        "document_id": row["review_id"], "task": "academic",
        "data_origin": "designated_research", "source_type": "pilot_review",
        "subject": pack_row["subject"], "text": pack_row["text"],
        "text_status": pack_row["text_status"],
        "sent_at": pack_row.get("sent_at"), "timezone": pack_row.get("timezone"),
        "context_cutoff_at": pack_row.get("context_cutoff_at"),
        "context_document_ids": pack_row.get("context_review_ids", []),
        "parent_document_id": pack_row.get("parent_review_id"),
        "primary_category": row["primary_category"],
        "secondary_categories": row["secondary_categories"],
        "secondary_categories_complete": "classification" in complete,
        "dates": row["dates"], "actions": row["actions"],
        "entities": row["entities"], "relationships": relationships,
        "reply_state": row["reply_state"], "annotation_status": statuses,
    }
    try:
        ResearchDocument.model_validate(document)
    except ValueError as exc:
        # Do not print private text or the validation input in errors.
        locations = sorted({".".join(str(part) for part in error["loc"])
                            for error in exc.errors(include_input=False)}) if hasattr(exc, "errors") else []
        raise ValueError("Invalid annotation contract fields: " + ", ".join(locations[:10])) from None
    return complete


def audit_pilot(reservation_dir, pilot_dir, reviewer_a_path, reviewer_b_path,
                queue_output=None):
    reservation_dir = Path(reservation_dir)
    pilot_dir = Path(pilot_dir)
    manifest = json.loads((pilot_dir / "pilot_manifest.json").read_text(encoding="utf-8"))
    pack_path = reservation_dir / "development_pack.jsonl"
    if manifest["development_pack_sha256"] != file_sha256(pack_path):
        raise ValueError("Pilot pack checksum mismatch")
    guide_path = Path(__file__).resolve().parents[1] / "dataset/ANNOTATION_GUIDE.md"
    if manifest["guide_sha256"] != file_sha256(guide_path):
        raise ValueError("Pilot annotation guide changed after forms were generated")
    for owner in ("reviewer_a", "reviewer_b"):
        if manifest["form_sha256"][owner] != file_sha256(pilot_dir / f"{owner}.jsonl"):
            raise ValueError("Original blank pilot form checksum mismatch")
    pack = read_index(pack_path, "review_id")
    original_a = read_index(pilot_dir / "reviewer_a.jsonl", "review_id")
    original_b = read_index(pilot_dir / "reviewer_b.jsonl", "review_id")
    if set(original_a) != set(original_b) or len(original_a) != manifest["pilot_rows"]:
        raise ValueError("Pilot form identity mismatch")
    if any(key not in pack for key in original_a):
        raise ValueError("Pilot references unknown development row")
    forms = {}
    reviewed = {}
    for owner, path in (("reviewer_a", reviewer_a_path), ("reviewer_b", reviewer_b_path)):
        path = Path(path)
        values = read_index(path, "review_id")
        if set(values) != set(original_a):
            raise ValueError(f"{owner} has missing or extra pilot rows")
        counts = Counter()
        reviewer_ids = set()
        for review_id, value in values.items():
            complete = validate_form(value, pack[review_id], set(pack), owner)
            counts.update(complete)
            if value["reviewer_id"]:
                reviewer_ids.add(value["reviewer_id"])
        forms[owner] = values
        reviewed[owner] = {"complete_task_counts": dict(counts),
                           "reviewer_ids": sorted(reviewer_ids),
                           "fully_reviewed_documents": sum(set(TASKS) <= set(v["complete_fields"])
                                                            for v in values.values()),
                           "classification_complete": counts["classification"]}
    shared_reviewers = set(reviewed["reviewer_a"]["reviewer_ids"]) & set(reviewed["reviewer_b"]["reviewer_ids"])
    if shared_reviewers:
        raise ValueError("Pilot reviewers must be independent people")
    disagreement_counts = Counter()
    comparable = Counter()
    disputes = []
    for review_id in original_a:
        left, right = forms["reviewer_a"][review_id], forms["reviewer_b"][review_id]
        different = []
        for task, keys in TASK_VALUES.items():
            if task not in left["complete_fields"] or task not in right["complete_fields"]:
                continue
            comparable[task] += 1
            if any(left[key] != right[key] for key in keys):
                disagreement_counts[task] += 1
                different.append(task)
        if different:
            disputes.append({"review_id": review_id, "disputed_tasks": different,
                             "adjudicator_id": None, "reason": "",
                             "final_decisions_recorded": False})
    if queue_output is not None:
        if comparable["classification"] != manifest["pilot_rows"]:
            raise ValueError("Both reviewers must complete classification before adjudication queue publication")
        queue_output = Path(queue_output).resolve()
        root = Path(__file__).resolve().parents[1]
        if not queue_output.is_relative_to((root / "artifacts/research").resolve()):
            raise ValueError("Adjudication queue must stay under private artifacts/research")
        if queue_output.exists():
            raise ValueError("Adjudication queue output must be new")
        queue_output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=queue_output.parent,
            prefix=".adjudication-", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            for dispute in sorted(disputes, key=lambda item: item["review_id"]):
                stream.write(json.dumps(dispute, sort_keys=True) + "\n")
        temporary.rename(queue_output)
    return {
        "status": "ready_for_adjudication" if comparable["classification"] == manifest["pilot_rows"]
                  else "human_review_incomplete",
        "pilot_rows": manifest["pilot_rows"],
        "independent_guards": manifest["independent_guards"],
        "reviewer_a": reviewed["reviewer_a"], "reviewer_b": reviewed["reviewer_b"],
        "comparable_complete_tasks": dict(comparable),
        "task_disagreements": dict(disagreement_counts),
        "disputed_documents": len(disputes),
        "adjudicated": False,
        "gold_eligible": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reservation-dir", type=Path, required=True)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--reviewer-a", type=Path, required=True)
    parser.add_argument("--reviewer-b", type=Path, required=True)
    parser.add_argument("--adjudication-queue", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_pilot(args.reservation_dir, args.pilot_dir,
                                 args.reviewer_a, args.reviewer_b,
                                 args.adjudication_queue), indent=2))
