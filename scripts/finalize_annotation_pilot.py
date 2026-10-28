"""Publish a private development pilot only after independent human adjudication."""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile

if __package__:
    from scripts.audit_annotation_pilot import TASK_VALUES, audit_pilot, read_index, validate_form
else:
    from audit_annotation_pilot import TASK_VALUES, audit_pilot, read_index, validate_form
from campusmail.research.contracts import ResearchDocument, TASKS
from campusmail.research.files import file_sha256


def finalize_pilot(reservation_dir, pilot_dir, reviewer_a_path, reviewer_b_path,
                   adjudication_path, output_dir, *, private_root=None):
    """Validate all inputs before atomically creating a reviewed-only output."""
    root = Path(__file__).resolve().parents[1]
    private_root = (Path(private_root) if private_root is not None
                    else root / "artifacts/research").resolve()
    output_dir = Path(output_dir).resolve()
    if not output_dir.is_relative_to(private_root):
        raise ValueError("Reviewed pilot output must stay under private artifacts/research")
    if output_dir.exists():
        raise ValueError("Reviewed pilot output must be new")
    audit = audit_pilot(reservation_dir, pilot_dir, reviewer_a_path, reviewer_b_path)
    if audit["status"] != "ready_for_adjudication":
        raise ValueError("Both human reviewers must finish every classification row")

    pack = read_index(Path(reservation_dir) / "development_pack.jsonl", "review_id")
    forms = {
        "reviewer_a": read_index(reviewer_a_path, "review_id"),
        "reviewer_b": read_index(reviewer_b_path, "review_id"),
    }
    adjudications = read_index(adjudication_path, "review_id")
    reviewer_ids = {}
    for owner, rows in forms.items():
        ids = {row["reviewer_id"] for row in rows.values()}
        if len(ids) != 1 or None in ids:
            raise ValueError(f"{owner} must use one consistent human reviewer ID")
        reviewer_ids[owner] = ids.pop()
    if reviewer_ids["reviewer_a"] == reviewer_ids["reviewer_b"]:
        raise ValueError("Pilot reviews require two distinct people")

    documents = []
    disputed_ids = set()
    task_support = Counter()
    class_support = Counter()
    for review_id in sorted(forms["reviewer_a"]):
        left = forms["reviewer_a"][review_id]
        right = forms["reviewer_b"][review_id]
        agreed = {}
        disputed = {}
        for task, keys in TASK_VALUES.items():
            if task not in left["complete_fields"] or task not in right["complete_fields"]:
                continue
            values = {key: left[key] for key in keys}
            if any(left[key] != right[key] for key in keys):
                disputed[task] = values
            else:
                agreed[task] = values

        decision_row = adjudications.get(review_id)
        if disputed:
            disputed_ids.add(review_id)
            if not isinstance(decision_row, dict):
                raise ValueError("A disputed document lacks adjudication")
            if set(decision_row) != {
                "review_id", "disputed_tasks", "adjudicator_id", "reason",
                "final_decisions_recorded", "decisions",
            }:
                raise ValueError("Adjudication row has invalid fields")
            if (not isinstance(decision_row["disputed_tasks"], list)
                or any(not isinstance(task, str) for task in decision_row["disputed_tasks"])
                or set(decision_row["disputed_tasks"]) != set(disputed)
                or len(decision_row["disputed_tasks"]) != len(disputed)
                or decision_row["final_decisions_recorded"] is not True
                or not isinstance(decision_row["reason"], str)
                or not decision_row["reason"].strip()
                or not isinstance(decision_row["adjudicator_id"], str)
                or not decision_row["adjudicator_id"].strip()
                or decision_row["adjudicator_id"] in reviewer_ids.values()
                or not isinstance(decision_row["decisions"], dict)
                or set(decision_row["decisions"]) != set(disputed)):
                raise ValueError("Adjudication is incomplete or is not independent")
            for task, values in decision_row["decisions"].items():
                if not isinstance(values, dict) or set(values) != set(TASK_VALUES[task]):
                    raise ValueError("Adjudicated task decision has invalid fields")
        elif decision_row is not None:
            raise ValueError("Adjudication supplied for a document without disputes")

        final = dict(left)
        final.update({key: None if key in ("primary_category", "reply_state") else []
                      for keys in TASK_VALUES.values() for key in keys})
        final["complete_fields"] = [task for task in TASKS if task in agreed or task in disputed]
        for values in agreed.values():
            final.update(values)
        if disputed:
            for values in decision_row["decisions"].values():
                final.update(values)
        document = validate_form(final, pack[review_id], set(pack), "reviewer_a")
        gold = document.model_dump(mode="json")
        for task in TASKS:
            if task in final["complete_fields"]:
                status = gold["annotation_status"][task]
                status["reviewer_ids"] = [reviewer_ids["reviewer_a"], reviewer_ids["reviewer_b"]]
                if task in disputed:
                    status["adjudication"] = "resolved"
                    status["adjudicator_id"] = decision_row["adjudicator_id"]
                task_support[task] += 1
        gold = ResearchDocument.model_validate(gold)
        if not gold.gold_eligible("classification"):
            raise ValueError("Pilot classification must be double reviewed and resolved")
        class_support[gold.primary_category] += 1
        documents.append(gold)
    if set(adjudications) != disputed_ids:
        raise ValueError("Adjudication has missing or extra document decisions")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".reviewed-pilot-", dir=output_dir.parent))
    try:
        reviewed_path = stage / "reviewed_development.jsonl"
        with reviewed_path.open("w", encoding="utf-8") as stream:
            for document in documents:
                stream.write(json.dumps(document.model_dump(mode="json"),
                                        ensure_ascii=False, sort_keys=True) + "\n")
        manifest = {
            "status": "double_reviewed_development_pilot",
            "pilot_rows": len(documents),
            "independent_guards": len({pack[doc.document_id]["guard_token"]
                                       for doc in documents}),
            "disputed_documents": len(disputed_ids),
            "complete_task_counts": dict(task_support),
            "primary_category_counts": dict(class_support),
            "input_sha256": {
                "pilot_manifest": file_sha256(Path(pilot_dir) / "pilot_manifest.json"),
                "reviewer_a": file_sha256(reviewer_a_path),
                "reviewer_b": file_sha256(reviewer_b_path),
                "adjudication": file_sha256(adjudication_path),
            },
            "reviewed_development_sha256": file_sha256(reviewed_path),
            "partition": "development",
        }
        (stage / "reviewed_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if output_dir.exists():
            raise ValueError("Reviewed pilot output appeared during staging")
        stage.rename(output_dir)
    except BaseException:
        shutil.rmtree(stage)
        raise
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reservation-dir", type=Path, required=True)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--reviewer-a", type=Path, required=True)
    parser.add_argument("--reviewer-b", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(finalize_pilot(args.reservation_dir, args.pilot_dir,
                                    args.reviewer_a, args.reviewer_b,
                                    args.adjudication, args.output_dir), indent=2))
