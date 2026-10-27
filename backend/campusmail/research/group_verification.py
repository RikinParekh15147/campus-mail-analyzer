"""Independent postcondition checks for private leakage component manifests."""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from .contracts import ResearchDocument
from .files import file_sha256, jsonl_records
from .grouping import GROUP_FIELDS, body_hash, source_identity, _node_bytes


def verify_membership(sources, output_dir):
    folder = Path(output_dir)
    report = json.loads((folder / "component_report.json").read_text())
    problems = Counter()
    for name, key in (
        ("membership.jsonl", "membership_sha256"),
        ("near_edges.jsonl", "near_edges_sha256"),
        ("legacy_leakage_review.jsonl", "legacy_leakage_review_sha256"),
    ):
        if file_sha256(folder / name) != report[key]:
            problems["output_hash_mismatch"] += 1
    membership = {}
    hard_to_guard = {}
    by_hard, by_guard = defaultdict(list), defaultdict(list)
    for _, row, _, error in jsonl_records(folder / "membership.jsonl"):
        if error:
            problems["invalid_membership_json"] += 1
            continue
        key = (row.get("dataset_id"), row.get("document_id"))
        if key in membership:
            problems["duplicate_membership"] += 1
        membership[key] = row
        hard, guard = row.get("component_id"), row.get("provisional_split_guard_id")
        if hard in hard_to_guard and hard_to_guard[hard] != guard:
            problems["hard_component_crosses_guard"] += 1
        hard_to_guard[hard] = guard
        by_hard[hard].append(key)
        by_guard[guard].append(key)
    for grouping, prefix in ((by_hard, "cmp_"), (by_guard, "guard_")):
        for group_id, members in grouping.items():
            calculated = (
                prefix
                + hashlib.sha256(
                    b"\n".join(sorted(_node_bytes(*key) for key in members))
                ).hexdigest()[:24]
            )
            if group_id != calculated:
                problems["unstable_component_id"] += 1
    seen = set()
    group_first = {}
    soft_first = {}
    exact_first = {}
    source_first = {}
    delayed = []
    source_counts = Counter()

    def assert_same(a, b, *, guard_only=False):
        if a not in membership or b not in membership:
            problems["missing_edge_endpoint"] += 1
            return
        field = "provisional_split_guard_id" if guard_only else "component_id"
        if membership[a][field] != membership[b][field]:
            problems[
                "soft_edge_crosses_guard"
                if guard_only
                else "hard_edge_crosses_component"
            ] += 1

    for source in sources:
        if file_sha256(source["path"]) != source["expected_sha256"]:
            problems["source_hash_mismatch"] += 1
            continue
        for _, row, _, error in jsonl_records(source["path"]):
            if error:
                problems["invalid_source_json"] += 1
                continue
            doc = ResearchDocument.model_validate(row)
            key = (doc.dataset_id, doc.document_id)
            if key in seen:
                problems["duplicate_source_id"] += 1
            seen.add(key)
            source_counts[source["name"]] += 1
            if (
                key not in membership
                or membership[key]["task"] != doc.task
                or membership[key]["source_name"] != source["name"]
            ):
                problems["missing_or_wrong_membership"] += 1
                continue
            for field in GROUP_FIELDS:
                value = getattr(doc, field)
                if value is None:
                    continue
                group = (doc.dataset_id, field, value)
                if group in group_first:
                    assert_same(key, group_first[group])
                else:
                    group_first[group] = key
            if doc.leakage_group_id:
                group = (doc.dataset_id, doc.leakage_group_id)
                if group in soft_first:
                    assert_same(key, soft_first[group], guard_only=True)
                else:
                    soft_first[group] = key
            if doc.text_status == "available":
                group = (doc.task, body_hash(doc.text))
                if group in exact_first:
                    assert_same(key, exact_first[group])
                else:
                    exact_first[group] = key
            identity = source_identity(doc, source.get("source_family"))
            if identity:
                stable = (
                    doc.thread_id,
                    doc.sent_at.isoformat() if doc.sent_at else None,
                )
                if identity in source_first and source_first[identity][1] == stable:
                    assert_same(key, source_first[identity][0])
                else:
                    source_first.setdefault(identity, (key, stable))
            refs = list(doc.context_document_ids)
            if doc.parent_document_id:
                refs.append(doc.parent_document_id)
            refs.extend(item.target_document_id for item in doc.grouping_relations)
            refs.extend(item.target_document_id for item in doc.relationships)
            delayed.extend((key, (doc.dataset_id, target)) for target in refs)
    for a, b in delayed:
        assert_same(a, b)
    for _, edge, _, error in jsonl_records(folder / "near_edges.jsonl"):
        expected_threshold = (
            report["near_jaccard_threshold"]
            if edge and edge.get("method") == "word4"
            else report["near_short_jaccard_threshold"]
            if edge and edge.get("method") == "char5"
            else None
        )
        if (
            error
            or expected_threshold is None
            or edge.get("threshold") != expected_threshold
            or not isinstance(edge.get("shingle_jaccard"), (float, int))
            or edge["shingle_jaccard"] < expected_threshold
        ):
            problems["invalid_near_edge"] += 1
            continue
        a, b = edge["left"], edge["right"]
        assert_same(
            (a["dataset_id"], a["document_id"]), (b["dataset_id"], b["document_id"])
        )
    if seen != set(membership):
        problems["source_membership_mismatch"] += 1
    if dict(source_counts) != report["source_counts"] or len(seen) != report["records"]:
        problems["source_count_mismatch"] += 1
    if (
        len(by_hard) != report["components"]
        or len(by_guard) != report["provisional_split_guards"]
    ):
        problems["component_count_mismatch"] += 1
    return {
        "status": "valid" if not problems else "invalid",
        "records_checked": len(seen),
        "hard_components_checked": len(by_hard),
        "split_guards_checked": len(by_guard),
        "reference_edges_checked": len(delayed),
        "errors": dict(problems),
    }
