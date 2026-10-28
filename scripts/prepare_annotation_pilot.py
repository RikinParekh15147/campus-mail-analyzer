"""Create two independent blank DATA-06 review forms from a pinned pack."""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile

from campusmail.research.files import file_sha256, jsonl_records

PILOT_COUNT = 50


def prepare_pilot(root, reservation_dir, output_dir):
    root = Path(root).resolve()
    reservation_dir = Path(reservation_dir).resolve()
    output_dir = Path(output_dir).resolve()
    if not output_dir.is_relative_to((root / "artifacts/research").resolve()):
        raise ValueError("Pilot output must remain under private artifacts/research")
    if output_dir.exists():
        raise ValueError("Pilot output directory must be new")
    report = json.loads((reservation_dir / "reservation_report.json").read_text(encoding="utf-8"))
    pack_path = reservation_dir / "development_pack.jsonl"
    if report.get("status") != "valid" or file_sha256(pack_path) != report["file_sha256"].get("development_pack.jsonl"):
        raise ValueError("Development pack is not valid/pinned")
    guide_path = root / "dataset/ANNOTATION_GUIDE.md"
    rows = []
    seen_ids = set()
    for line, row, _, error in jsonl_records(pack_path):
        if error or row is None or row.get("review_id") in seen_ids:
            raise ValueError(f"Invalid development pack line {line}")
        seen_ids.add(row["review_id"])
        if row.get("text_status") == "available":
            rows.append(row)
    if len(rows) < PILOT_COUNT:
        raise ValueError("Insufficient available development documents for pilot")
    buckets = {"linked": [], "long": [], "short": [], "ordinary": []}
    for row in sorted(rows, key=lambda value: value["review_id"]):
        length = len(row["text"])
        if row.get("parent_review_id") or row.get("grouping_relations"):
            bucket = "linked"
        elif length >= 5000:
            bucket = "long"
        elif length < 500:
            bucket = "short"
        else:
            bucket = "ordinary"
        buckets[bucket].append(row)
    selected = []
    selected_guards = set()
    names = ("linked", "long", "short", "ordinary")
    while len(selected) < PILOT_COUNT:
        progress = False
        for name in names:
            while buckets[name] and buckets[name][0]["guard_token"] in selected_guards:
                buckets[name].pop(0)
            if not buckets[name]:
                continue
            row = buckets[name].pop(0)
            selected.append(row)
            selected_guards.add(row["guard_token"])
            progress = True
            if len(selected) == PILOT_COUNT:
                break
        if not progress:
            raise ValueError("Insufficient independent development guards for pilot")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".data06-", dir=output_dir.parent))
    try:
        for form_owner in ("reviewer_a", "reviewer_b"):
            with (stage / f"{form_owner}.jsonl").open("w", encoding="utf-8") as stream:
                for row in selected:
                    blank = {
                        "review_id": row["review_id"], "form_owner": form_owner,
                        "reviewer_id": None, "guide_version": "0.1",
                        "complete_fields": [], "primary_category": None,
                        "secondary_categories": [], "actions": [], "dates": [],
                        "entities": [], "relationships": [], "reply_state": None,
                        "notes": "",
                    }
                    stream.write(json.dumps(blank, ensure_ascii=False, sort_keys=True) + "\n")
        summary = {
            "status": "forms_prepared_unreviewed", "pilot_rows": len(selected),
            "independent_guards": len(selected_guards),
            "selection_policy": "one_available_row_per_guard_round_robin_linked_long_short_ordinary_v1",
            "bucket_counts": dict(Counter(
                "linked" if row.get("parent_review_id") or row.get("grouping_relations")
                else "long" if len(row["text"]) >= 5000
                else "short" if len(row["text"]) < 500 else "ordinary"
                for row in selected
            )),
            "development_pack_sha256": file_sha256(pack_path),
            "guide_sha256": file_sha256(guide_path),
            "form_sha256": {
                name: file_sha256(stage / f"{name}.jsonl")
                for name in ("reviewer_a", "reviewer_b")
            },
        }
        (stage / "pilot_manifest.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        if output_dir.exists():
            raise ValueError("Pilot output appeared during staging")
        stage.rename(output_dir)
    except BaseException:
        shutil.rmtree(stage)
        raise
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--reservation-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_pilot(args.project_root, args.reservation_dir, args.output_dir), indent=2))
