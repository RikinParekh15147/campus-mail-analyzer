"""Reserve whole DATA-04 guards and publish a private, blinded review queue."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from campusmail.research.files import file_sha256, jsonl_records
from campusmail.research.source_policy import (
    SOURCE_RULES, SPLIT_POLICY_VERSION, SPLIT_SEED, expected_split, require_source,
)

REVIEW_TARGET = 150
HOLDOUT_REVIEW_GUARDS = 30
MAX_REVIEW_GUARD_ROWS = 8


def digest(kind, value):
    return hashlib.sha256(f"{SPLIT_SEED}|{kind}|{value}".encode()).hexdigest()


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(compact_json(row) + "\n")


def verify_reservation(component_run, reservation_dir):
    """Reread published sidecars and check hashes, split coverage and blind pack."""
    component_run = Path(component_run)
    reservation_dir = Path(reservation_dir)
    report = json.loads((reservation_dir / "reservation_report.json").read_text(encoding="utf-8"))
    membership_path = component_run / "membership.jsonl"
    if report.get("membership_sha256") != file_sha256(membership_path):
        raise ValueError("Reservation membership checksum mismatch")
    for name, expected in report["file_sha256"].items():
        if file_sha256(reservation_dir / name) != expected:
            raise ValueError(f"Reservation output checksum mismatch: {name}")
    allocation = {}
    for line, row, _, error in jsonl_records(reservation_dir / "allocation.jsonl"):
        if error or row is None or row.get("split") != expected_split(row.get("task"), row.get("guard_id")):
            raise ValueError(f"Invalid split allocation line {line}")
        if row["guard_id"] in allocation:
            raise ValueError("Duplicate split guard")
        allocation[row["guard_id"]] = row
    count_by_guard = Counter()
    for line, row, _, error in jsonl_records(membership_path):
        if error or row is None:
            raise ValueError(f"Invalid membership line {line}")
        guard = row["provisional_split_guard_id"]
        if guard not in allocation or row["task"] != allocation[guard]["task"]:
            raise ValueError("Missing or cross-task split guard")
        count_by_guard[guard] += 1
    if len(allocation) != report["total_guards"] or sum(count_by_guard.values()) != report["total_records"]:
        raise ValueError("Split totals do not match reservation")
    if any(count_by_guard[g] != entry["member_count"] for g, entry in allocation.items()):
        raise ValueError("Split guard membership count mismatch")
    identities = {}
    for line, row, _, error in jsonl_records(reservation_dir / "private_identity_map.jsonl"):
        if error or row is None:
            raise ValueError(f"Invalid private identity line {line}")
        if allocation[row["provisional_split_guard_id"]]["split"] != "development":
            raise ValueError("Sealed member entered development identity map")
        if row["review_id"] in identities:
            raise ValueError("Duplicate review identity")
        identities[row["review_id"]] = row
    review = {}
    forbidden = {"document_id", "dataset_id", "source_metadata", "primary_category", "actionability_label"}
    for line, row, _, error in jsonl_records(reservation_dir / "development_pack.jsonl"):
        if error or row is None or forbidden.intersection(row):
            raise ValueError(f"Invalid or unblinded development row {line}")
        if row["review_id"] not in identities or row["review_id"] in review:
            raise ValueError("Development row has missing or duplicate private mapping")
        review[row["review_id"]] = row
    if set(review) != set(identities) or len(review) != report["development_pack_rows"]:
        raise ValueError("Development pack and private mapping differ")
    if any(ref not in review for row in review.values() for ref in row["context_review_ids"]):
        raise ValueError("Development context reference is missing")
    if any(relation["target_review_id"] not in review for row in review.values()
           for relation in row["grouping_relations"] + row["semantic_relations"]):
        raise ValueError("Development relation reference is missing")
    if any(row["parent_review_id"] and row["parent_review_id"] not in review for row in review.values()):
        raise ValueError("Development parent reference is missing")
    holdout = set()
    for line, row, _, error in jsonl_records(reservation_dir / "sealed_review_queue.jsonl"):
        if error or row is None or allocation[row["guard_id"]]["split"] != "sealed_holdout":
            raise ValueError(f"Invalid sealed review queue line {line}")
        holdout.add(row["guard_id"])
    if len(holdout) != report["holdout_review_guards"]:
        raise ValueError("Sealed review queue count mismatch")
    return {"status": "valid", "guards_checked": len(allocation),
            "members_checked": sum(count_by_guard.values()),
            "development_rows_checked": len(review), "holdout_queue_guards_checked": len(holdout)}


def read_pinned_membership(root, input_run, component_run):
    source_manifest = root / "research_sources.json"
    source_config = json.loads(source_manifest.read_text(encoding="utf-8"))
    migration = json.loads((input_run / "run.json").read_text(encoding="utf-8"))
    components = json.loads((component_run / "component_report.json").read_text(encoding="utf-8"))
    if migration.get("status") != "valid" or components.get("status") != "valid":
        raise ValueError("Upstream research run is not valid")
    if migration.get("manifest_sha256") != file_sha256(source_manifest):
        raise ValueError("Source manifest changed after DATA-03")
    if components.get("source_manifest_sha256") != file_sha256(source_manifest):
        raise ValueError("Source manifest changed after DATA-04")
    if components.get("input_run_sha256") != file_sha256(input_run / "run.json"):
        raise ValueError("DATA-04 was built from a different DATA-03 run")
    membership_path = component_run / "membership.jsonl"
    if components.get("membership_sha256") != file_sha256(membership_path):
        raise ValueError("DATA-04 membership checksum changed")
    if set(SOURCE_RULES) != {entry["name"] for entry in source_config["sources"]}:
        raise ValueError("Source policy is incomplete for the pinned manifest")

    members = {}
    guards = defaultdict(list)
    for line, row, _, error in jsonl_records(membership_path):
        if error or row is None:
            raise ValueError(f"Invalid membership line {line}")
        source = row.get("source_name")
        rule = require_source(source, row.get("task"), "inventory")
        entry = next(item for item in source_config["sources"] if item["name"] == source)
        if row.get("dataset_id") != entry["dataset_id"]:
            raise ValueError("Membership dataset/source mismatch")
        key = (row["dataset_id"], row["document_id"])
        if key in members:
            raise ValueError("Duplicate membership identity")
        members[key] = row
        guards[row["provisional_split_guard_id"]].append(row)
        if any(item["task"] != rule.task for item in guards[row["provisional_split_guard_id"]]):
            raise ValueError("Split guard crosses prediction tasks")
    if len(members) != components["records"] or len(guards) != components["provisional_split_guards"]:
        raise ValueError("Membership totals do not match DATA-04 report")
    return source_config, migration, components, members, guards


def build_reservation(root, input_run, component_run, output_dir):
    root = Path(root).resolve()
    input_run = Path(input_run).resolve()
    component_run = Path(component_run).resolve()
    output_dir = Path(output_dir).resolve()
    research_root = (root / "artifacts/research").resolve()
    if not output_dir.is_relative_to(research_root) or output_dir == research_root:
        raise ValueError("Private reservation output must be under artifacts/research")
    if output_dir.exists():
        raise ValueError("Reservation output directory must be new")
    source_config, migration, components, members, guards = read_pinned_membership(
        root, input_run, component_run
    )
    allocation = {}
    for guard_id, rows in guards.items():
        task = rows[0]["task"]
        allocation[guard_id] = expected_split(task, guard_id)

    # The default review queue represents the existing scoped academic model.
    # Broad mail is retained in the allocation, but its overlapping copies do
    # not masquerade as independent development or holdout examples.
    scoped_entry = next(x for x in source_config["sources"] if x["name"] == "scoped")
    require_source("scoped", "academic", "review")
    scoped_path = input_run / "scoped.v2.jsonl"
    if file_sha256(scoped_path) != migration["sources"]["scoped"]["output_sha256"]:
        raise ValueError("Scoped v2 export checksum changed")
    scoped = {}
    for line, row, _, error in jsonl_records(scoped_path):
        if error or row is None:
            raise ValueError(f"Invalid scoped export line {line}")
        key = (row["dataset_id"], row["document_id"])
        if row["dataset_id"] != scoped_entry["dataset_id"] or key not in members:
            raise ValueError("Scoped export/membership identity mismatch")
        if row["task"] != "academic" or row["usage_status"] == "quarantined":
            raise ValueError("Scoped export violates research source policy")
        scoped[key] = row
    if len(scoped) != scoped_entry["records"]:
        raise ValueError("Scoped export count mismatch")

    scoped_by_guard = defaultdict(list)
    for key, row in scoped.items():
        scoped_by_guard[members[key]["provisional_split_guard_id"]].append((key, row))
    eligible = {
        guard: rows
        for guard, rows in scoped_by_guard.items()
        if len(rows) <= MAX_REVIEW_GUARD_ROWS
        and any(row.get("text_status", "available") == "available" for _, row in rows)
    }
    ordered = sorted(eligible, key=lambda guard: digest("review-order", guard))
    development_guards = []
    available_count = 0
    for guard in ordered:
        if allocation[guard] != "development":
            continue
        count = sum(row.get("text_status", "available") == "available" for _, row in eligible[guard])
        if available_count + count > 200:
            continue
        development_guards.append(guard)
        available_count += count
        if available_count >= REVIEW_TARGET:
            break
    holdout_guards = [
        guard for guard in ordered if allocation[guard] == "sealed_holdout"
    ][:HOLDOUT_REVIEW_GUARDS]
    if available_count < 100 or len(holdout_guards) < HOLDOUT_REVIEW_GUARDS:
        raise ValueError("Insufficient independent scoped guards for declared review queue")

    pack_keys = {
        key for guard in development_guards for key, _ in eligible[guard]
    }
    token = {key: digest("review-id", compact_json(key))[:24] for key in pack_keys}
    if len(set(token.values())) != len(token):
        raise ValueError("Review token collision")
    review_rows = []
    identity_rows = []
    for key in sorted(pack_keys, key=lambda item: token[item]):
        row = scoped[key]
        member = members[key]
        guard = member["provisional_split_guard_id"]
        related_ids = list(row.get("context_document_ids", []))
        related_ids.extend(rel["target_document_id"] for rel in row.get("grouping_relations", []))
        related_ids.extend(rel["target_document_id"] for rel in row.get("relationships", []))
        if row.get("parent_document_id"):
            related_ids.append(row["parent_document_id"])
        if any((key[0], target) not in token for target in related_ids):
            raise ValueError("Selected guard has a relationship outside the review pack")
        refs = [
            token[(key[0], ref)] for ref in row.get("context_document_ids", [])
            if (key[0], ref) in token
        ]
        parent = row.get("parent_document_id")
        grouping_relations = [
            {"type": relation["type"],
             "target_review_id": token[(key[0], relation["target_document_id"])]}
            for relation in row.get("grouping_relations", [])
            if (key[0], relation["target_document_id"]) in token
        ]
        semantic_relations = [
            {"type": relation["type"],
             "target_review_id": token[(key[0], relation["target_document_id"])]}
            for relation in row.get("relationships", [])
            if (key[0], relation["target_document_id"]) in token
        ]
        review_rows.append({
            "review_id": token[key],
            "guard_token": digest("guard-token", guard)[:24],
            "component_token": digest("component-token", member["component_id"])[:24],
            "source_role": "scoped_academic",
            "thread_token": digest("thread-token", f"{key[0]}|{row['thread_id']}")[:24] if row.get("thread_id") else None,
            "duplicate_token": digest("duplicate-token", f"{key[0]}|{row['duplicate_group_id']}")[:24] if row.get("duplicate_group_id") else None,
            "template_token": digest("template-token", f"{key[0]}|{row['template_group_id']}")[:24] if row.get("template_group_id") else None,
            "update_family_token": digest("update-family-token", f"{key[0]}|{row['update_family_id']}")[:24] if row.get("update_family_id") else None,
            "subject": row.get("subject", ""),
            "text": row["text"],
            "text_status": row.get("text_status", "available"),
            "sent_at": row.get("sent_at"),
            "timezone": row.get("timezone"),
            "context_cutoff_at": row.get("context_cutoff_at"),
            "context_review_ids": refs,
            "parent_review_id": token.get((key[0], parent)) if parent else None,
            "grouping_relations": grouping_relations,
            "semantic_relations": semantic_relations,
            "weak_label_hidden": True,
        })
        identity_rows.append({
            "review_id": token[key], "dataset_id": key[0], "document_id": key[1],
            "source_name": "scoped", "provisional_split_guard_id": guard,
        })
    if any(allocation[identity["provisional_split_guard_id"]] != "development" for identity in identity_rows):
        raise ValueError("Sealed guard entered the development pack")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".data05-", dir=output_dir.parent))
    try:
        write_jsonl(stage / "allocation.jsonl", (
            {"guard_id": guard, "task": guards[guard][0]["task"],
             "split": allocation[guard], "member_count": len(guards[guard])}
            for guard in sorted(guards)
        ))
        write_jsonl(stage / "development_pack.jsonl", review_rows)
        write_jsonl(stage / "private_identity_map.jsonl", identity_rows)
        write_jsonl(stage / "sealed_review_queue.jsonl", (
            {"guard_id": guard, "guard_token": digest("guard-token", guard)[:24],
             "scoped_available_records": sum(row.get("text_status", "available") == "available" for _, row in eligible[guard])}
            for guard in holdout_guards
        ))
        split_counts = Counter(allocation.values())
        report = {
            "status": "valid", "policy_version": SPLIT_POLICY_VERSION, "seed": SPLIT_SEED,
            "source_manifest_sha256": file_sha256(root / "research_sources.json"),
            "data03_run_sha256": file_sha256(input_run / "run.json"),
            "data04_report_sha256": file_sha256(component_run / "component_report.json"),
            "membership_sha256": components["membership_sha256"],
            "total_guards": len(guards), "total_records": len(members),
            "split_guard_counts": dict(split_counts),
            "split_record_counts": dict(Counter(
                allocation[guard] for guard, rows in guards.items() for _ in rows
            )),
            "development_review_guards": len(development_guards),
            "development_review_available": available_count,
            "development_pack_rows": len(review_rows),
            "holdout_review_guards": len(holdout_guards),
            "eligible_scoped_guards": len(eligible),
            "source_policy": {
                name: {"task": rule.task, "role": rule.role, "family": rule.family,
                       "training_allowed": rule.training_allowed,
                       "review_allowed": rule.review_allowed, "reason": rule.reason}
                for name, rule in SOURCE_RULES.items()
            },
            "limitations": [
                "Hash allocation is score-independent, not class-stratified; reviewed class support is pending.",
                "Scoped review queue prefers guards of at most eight scoped rows and is not a random corpus estimate.",
                "Original private corpus on this Mac is physically accessible; sealed status is a workflow boundary.",
                "No review labels or accuracy scores are created by this reservation.",
            ],
            "file_sha256": {
                path.name: file_sha256(path) for path in stage.iterdir() if path.is_file()
            },
        }
        (stage / "reservation_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        verify_reservation(component_run, stage)
        if output_dir.exists():
            raise ValueError("Reservation output directory appeared during staging")
        stage.rename(output_dir)
    except BaseException:
        shutil.rmtree(stage)
        raise
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--input-run", type=Path, required=True)
    parser.add_argument("--component-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_reservation(args.project_root, args.input_run, args.component_run, args.output_dir)
    print(json.dumps({key: value for key, value in result.items() if key not in {"seed", "source_policy"}}, indent=2))
