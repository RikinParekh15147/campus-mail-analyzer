"""Leakage components for v2 research records; no split assignment or training.

All source IDs are namespaced. The output is a private research artifact because
it contains document IDs and links, although it never contains message bodies.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import re

import numpy as np

from .contracts import ResearchDocument
from .files import file_sha256, jsonl_records
from .validation import validate_jsonl

GROUP_FIELDS = (
    "thread_id",
    "duplicate_group_id",
    "template_group_id",
    "update_family_id",
)
NEAR_VERSION = "word4-char5-minhash32-v2"
NEAR_SHORT_MIN_CHARS = 45
NEAR_MIN_CHARS = 120
NEAR_MIN_SHINGLES = 12
NEAR_SHORT_MIN_SHINGLES = 20
NEAR_MAX_SHINGLES = 50000
NEAR_JACCARD = 0.90
NEAR_SHORT_JACCARD = 0.88
NEAR_LENGTH_RATIO = 0.82
MAX_BUCKET = 400
MAX_CANDIDATES = 2_000_000
WORDS = re.compile(r"\w+", re.UNICODE)
RNG = random.Random(20261027)
SALT = np.array([RNG.getrandbits(64) for _ in range(32)], dtype=np.uint64)
MULTIPLIER = np.array([RNG.getrandbits(64) | 1 for _ in range(32)], dtype=np.uint64)


class UnionFind:
    def __init__(self):
        self.parent = []
        self.size = []

    def add(self):
        index = len(self.parent)
        self.parent.append(index)
        self.size.append(1)
        return index

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return False
        if self.size[a] < self.size[b]:
            a, b = b, a
        self.parent[b] = a
        self.size[a] += self.size[b]
        return True


def normalized_body(text):
    return " ".join(text.casefold().split())


def body_hash(text):
    return hashlib.sha256(normalized_body(text).encode("utf-8")).hexdigest()


def shingles(text):
    words = WORDS.findall(text.casefold())
    if len(words) < 15:
        return np.empty(0, dtype=np.uint64)
    values = {
        int.from_bytes(
            hashlib.blake2b(
                " ".join(words[i : i + 4]).encode("utf-8"), digest_size=8
            ).digest(),
            "big",
        )
        for i in range(len(words) - 3)
    }
    return np.fromiter(sorted(values), dtype=np.uint64)


def character_shingles(text):
    canonical = normalized_body(text)
    if len(canonical) < 5:
        return np.empty(0, dtype=np.uint64)
    values = {
        int.from_bytes(
            hashlib.blake2b(
                canonical[i : i + 5].encode("utf-8"), digest_size=8
            ).digest(),
            "big",
        )
        for i in range(len(canonical) - 4)
    }
    return np.fromiter(sorted(values), dtype=np.uint64)


def minhash(values):
    # Odd 64-bit affine permutations are deterministic and vectorized. Candidate
    # matches are always verified with exact shingle-set Jaccard below.
    return np.min((values[:, None] ^ SALT[None, :]) * MULTIPLIER[None, :], axis=0)


def jaccard(left, right):
    common = np.intersect1d(left, right, assume_unique=True).size
    return common / (left.size + right.size - common)


def source_identity(document, family):
    """Cross-snapshot identity only when original message and source agree."""
    if not family or document.data_origin != "designated_research":
        return None
    legacy = document.source_metadata.get("legacy_extra_fields", {})
    if not isinstance(legacy, dict):
        return None
    message = legacy.get("message_id")
    if not isinstance(message, str) or not message:
        return None
    return (family, document.source_type, document.document_id, message)


def _node_bytes(dataset_id, document_id):
    return json.dumps(
        [dataset_id, document_id], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def build_components(sources, output_dir, *, run_id="fixture"):
    """Validate pinned exports, build components, and publish a private manifest.

    sources: sequence of name,dataset_id,source_family,path,expected_sha256.
    The output directory must not exist. Structural input failures leave it absent.
    """
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError("Component output directory must be new")
    seen_names, seen_ids = set(), set()
    for source in sources:
        if source["name"] in seen_names or source["dataset_id"] in seen_ids:
            raise ValueError("Duplicate research source identity")
        seen_names.add(source["name"])
        seen_ids.add(source["dataset_id"])
        if file_sha256(source["path"]) != source["expected_sha256"]:
            raise ValueError("Research export hash differs from pinned run")
        check = validate_jsonl(source["path"])
        if (
            check["status"] != "valid"
            or check["unique_records"] != check["physical_lines"]
        ):
            raise ValueError("Research export is not fully valid")
        if set(check["origin_counts"]) - {"designated_research", "public", "synthetic"}:
            raise ValueError("Invalid source origins")
    uf = UnionFind()
    nodes = []
    by_id = {}
    declared = {}
    legacy_leakage = defaultdict(list)
    exact = {}
    original = {}
    references = []
    bodies = defaultdict(list)
    near_arrays = {}
    near_kinds = {}
    near_buckets = defaultdict(list)
    attempts, unions, diagnostics = Counter(), Counter(), Counter()
    same_source_label_conflicts = 0

    def merge(a, b, reason):
        attempts[reason] += 1
        if uf.union(a, b):
            unions[reason] += 1

    for source in sources:
        for line, raw, _, problem in jsonl_records(source["path"]):
            if problem:
                raise ValueError(f"Research source has invalid JSON at line {line}")
            document = ResearchDocument.model_validate(raw)
            if document.dataset_id != source["dataset_id"]:
                raise ValueError(
                    "Research export contains an undeclared dataset identity"
                )
            key = (document.dataset_id, document.document_id)
            if key in by_id:
                raise ValueError("Duplicate namespaced document ID")
            index = uf.add()
            by_id[key] = index
            label = (
                document.primary_category
                if document.task == "academic"
                else document.actionability_label
            )
            node = {
                "dataset_id": document.dataset_id,
                "document_id": document.document_id,
                "task": document.task,
                "data_origin": document.data_origin,
                "usage_status": document.usage_status,
                "source_name": source["name"],
                "text_available": document.text_status == "available",
                "label": label,
                "source_family": source.get("source_family"),
            }
            nodes.append(node)
            if document.leakage_group_id:
                # Legacy groups were themselves built using bare normalized
                # subjects across threads. Keep them as audit candidates, not
                # authoritative edges that can overmerge unrelated years.
                legacy_leakage[(document.dataset_id, document.leakage_group_id)].append(
                    index
                )
            for field in GROUP_FIELDS:
                value = getattr(document, field)
                if value is not None:
                    group = (document.dataset_id, field, value)
                    if group in declared:
                        merge(index, declared[group], field)
                    else:
                        declared[group] = index
            links = [(ref, "context") for ref in document.context_document_ids]
            if document.parent_document_id:
                links.append((document.parent_document_id, "parent"))
            links.extend(
                (rel.target_document_id, "grouping_relation")
                for rel in document.grouping_relations
            )
            links.extend(
                (rel.target_document_id, "reviewed_relationship")
                for rel in document.relationships
            )
            for target, reason in links:
                references.append((index, (document.dataset_id, target), reason))
            identity = source_identity(document, source.get("source_family"))
            if identity:
                stamp = document.sent_at.isoformat() if document.sent_at else None
                stable = (document.thread_id, stamp)
                if identity in original:
                    first, first_stable = original[identity]
                    if first_stable != stable:
                        diagnostics["source_identity_metadata_conflicts"] += 1
                    else:
                        merge(index, first, "cross_snapshot_identity")
                        if (
                            label is not None
                            and nodes[first]["label"] is not None
                            and label != nodes[first]["label"]
                        ):
                            same_source_label_conflicts += 1
                else:
                    original[identity] = (index, stable)
            if document.text_status == "available":
                digest = body_hash(document.text)
                group = (document.task, digest)
                bodies[group].append(index)
                if group in exact:
                    merge(index, exact[group], "exact_body")
                else:
                    exact[group] = index
                if len(document.text) < NEAR_SHORT_MIN_CHARS:
                    diagnostics["near_skipped_short"] += 1
                    continue
                kind = "word4" if len(document.text) >= NEAR_MIN_CHARS else "char5"
                values = (
                    shingles(document.text)
                    if kind == "word4"
                    else character_shingles(document.text)
                )
                minimum = (
                    NEAR_MIN_SHINGLES if kind == "word4" else NEAR_SHORT_MIN_SHINGLES
                )
                if values.size < minimum and kind == "word4":
                    kind = "char5"
                    values = character_shingles(document.text)
                    minimum = NEAR_SHORT_MIN_SHINGLES
                if values.size < minimum:
                    diagnostics["near_skipped_few_shingles"] += 1
                    continue
                if values.size > NEAR_MAX_SHINGLES:
                    diagnostics["near_skipped_long"] += 1
                    continue
                near_arrays[index] = values
                near_kinds[index] = kind
                diagnostics["near_indexed_" + kind] += 1
                signature = minhash(values)
                for band in range(8):
                    bucket = (
                        document.task,
                        kind,
                        band,
                        tuple(int(x) for x in signature[band * 4 : (band + 1) * 4]),
                    )
                    near_buckets[bucket].append(index)
    for source_index, target_key, reason in references:
        target = by_id.get(target_key)
        if target is None:
            raise ValueError("Reference target absent from component corpus")
        merge(source_index, target, reason)
    for source in sources:
        if file_sha256(source["path"]) != source["expected_sha256"]:
            raise ValueError("Research export changed during grouping")
    candidates = set()
    for bucket in near_buckets.values():
        if len(bucket) > MAX_BUCKET:
            diagnostics["oversized_near_bucket"] += 1
            continue
        for i, a in enumerate(bucket):
            for b in bucket[i + 1 :]:
                candidates.add((min(a, b), max(a, b)))
                if len(candidates) > MAX_CANDIDATES:
                    raise ValueError(
                        "Near-duplicate candidate limit exceeded; review indexing policy"
                    )
    diagnostics["near_candidate_pairs"] = len(candidates)
    near_edges = []
    near_source_pairs = Counter()
    near_label_disagreements = 0
    for a, b in sorted(candidates):
        if uf.find(a) == uf.find(b):
            diagnostics["near_already_grouped"] += 1
            continue
        if nodes[a]["task"] != nodes[b]["task"]:
            raise ValueError("Cross-task near candidate")
        left, right = near_arrays[a], near_arrays[b]
        if near_kinds[a] != near_kinds[b]:
            raise ValueError("Near-duplicate shingle methods disagree")
        ratio = min(left.size, right.size) / max(left.size, right.size)
        if ratio < NEAR_LENGTH_RATIO:
            continue
        score = jaccard(left, right)
        diagnostics["near_verified_pairs"] += 1
        threshold = NEAR_JACCARD if near_kinds[a] == "word4" else NEAR_SHORT_JACCARD
        if score >= threshold:
            merge(a, b, "near_duplicate")
            near_source_pairs[
                ":".join(sorted((nodes[a]["source_name"], nodes[b]["source_name"])))
            ] += 1
            near_label_disagreements += (
                nodes[a]["label"] is not None
                and nodes[b]["label"] is not None
                and nodes[a]["label"] != nodes[b]["label"]
            )
            near_edges.append(
                {
                    "left": {k: nodes[a][k] for k in ("dataset_id", "document_id")},
                    "right": {k: nodes[b][k] for k in ("dataset_id", "document_id")},
                    "shingle_jaccard": round(score, 6),
                    "method": near_kinds[a],
                    "threshold": threshold,
                }
            )
    components = defaultdict(list)
    for i in range(len(nodes)):
        components[uf.find(i)].append(i)
    component_ids = {}
    seen_component_ids = set()
    component_stats = []
    for members in components.values():
        digest = hashlib.sha256(
            b"\n".join(
                sorted(
                    _node_bytes(nodes[i]["dataset_id"], nodes[i]["document_id"])
                    for i in members
                )
            )
        ).hexdigest()
        cid = "cmp_" + digest[:24]
        if cid in seen_component_ids:
            raise ValueError("Component ID collision")
        seen_component_ids.add(cid)
        for i in members:
            component_ids[i] = cid
        counts = Counter(nodes[i]["task"] for i in members)
        if len(counts) != 1:
            raise ValueError("Component spans incompatible prediction tasks")
        component_stats.append(
            {
                "component_id": cid,
                "size": len(members),
                "task": next(iter(counts)),
                "source_counts": dict(
                    Counter(nodes[i]["source_name"] for i in members)
                ),
                "available_text": sum(nodes[i]["text_available"] for i in members),
                "quarantined": sum(
                    nodes[i]["usage_status"] == "quarantined" for i in members
                ),
            }
        )
    exact_conflicts = Counter()
    legacy_soft = []
    for (dataset_id, group_id), members in legacy_leakage.items():
        roots = {uf.find(i) for i in members}
        if len(roots) > 1:
            legacy_soft.append(
                {
                    "dataset_id": dataset_id,
                    "legacy_leakage_group_id": group_id,
                    "members": len(members),
                    "derived_components": len(roots),
                    "component_ids": sorted({component_ids[i] for i in members}),
                }
            )
    # A conservative split guard additionally joins every unresolved legacy
    # family. DATA-05 can use it immediately or adjudicate soft links first.
    guard = UnionFind()
    for _ in nodes:
        guard.add()
    for members in components.values():
        for index in members[1:]:
            guard.union(members[0], index)
    for members in legacy_leakage.values():
        for index in members[1:]:
            guard.union(members[0], index)
    guards = defaultdict(list)
    for index in range(len(nodes)):
        guards[guard.find(index)].append(index)
    guard_ids = {}
    seen_guard_ids = set()
    guard_sizes = defaultdict(list)
    for members in guards.values():
        digest = hashlib.sha256(
            b"\n".join(
                sorted(
                    _node_bytes(nodes[i]["dataset_id"], nodes[i]["document_id"])
                    for i in members
                )
            )
        ).hexdigest()
        guard_id = "guard_" + digest[:24]
        if guard_id in seen_guard_ids:
            raise ValueError("Provisional split guard ID collision")
        seen_guard_ids.add(guard_id)
        for index in members:
            guard_ids[index] = guard_id
        tasks = {nodes[index]["task"] for index in members}
        if len(tasks) != 1:
            raise ValueError(
                "Provisional split guard spans incompatible prediction tasks"
            )
        guard_sizes[next(iter(tasks))].append(len(members))
    for (task, _), members in bodies.items():
        labels = {nodes[i]["label"] for i in members if nodes[i]["label"] is not None}
        if len(labels) > 1:
            exact_conflicts[task] += 1
    class_support = defaultdict(
        lambda: {"records": 0, "components": set(), "provisional_split_guards": set()}
    )
    for index, node in enumerate(nodes):
        if node["text_available"] and node["label"] is not None:
            key = (node["source_name"], str(node["label"]).lower())
            class_support[key]["records"] += 1
            class_support[key]["components"].add(component_ids[index])
            class_support[key]["provisional_split_guards"].add(guard_ids[index])
    support_report = defaultdict(dict)
    for (name, label), counts in class_support.items():
        support_report[name][label] = {
            "records": counts["records"],
            "components": len(counts["components"]),
            "provisional_split_guards": len(counts["provisional_split_guards"]),
        }
    by_task = Counter(node["task"] for node in nodes)
    component_by_task = Counter(s["task"] for s in component_stats)
    largest = {
        task: sorted(
            (s["size"] for s in component_stats if s["task"] == task), reverse=True
        )[:10]
        for task in by_task
    }
    giants = [
        s
        for s in component_stats
        if s["size"] >= max(100, math.ceil(by_task[s["task"]] * 0.01))
    ]
    diagnostics["near_indexed"] = len(near_arrays)
    report = {
        "status": "valid",
        "component_schema_version": "1.0",
        "run_id": run_id,
        "near_method": NEAR_VERSION,
        "near_min_chars": NEAR_MIN_CHARS,
        "near_short_min_chars": NEAR_SHORT_MIN_CHARS,
        "near_min_shingles": NEAR_MIN_SHINGLES,
        "near_short_min_shingles": NEAR_SHORT_MIN_SHINGLES,
        "near_max_shingles": NEAR_MAX_SHINGLES,
        "near_jaccard_threshold": NEAR_JACCARD,
        "near_short_jaccard_threshold": NEAR_SHORT_JACCARD,
        "near_min_length_ratio": NEAR_LENGTH_RATIO,
        "source_sha256": {
            source["name"]: source["expected_sha256"] for source in sources
        },
        "records": len(nodes),
        "source_counts": dict(Counter(node["source_name"] for node in nodes)),
        "task_counts": dict(by_task),
        "components": len(components),
        "components_by_task": dict(component_by_task),
        "largest_component_sizes": largest,
        "giant_thresholds": {
            task: max(100, math.ceil(n * 0.01)) for task, n in by_task.items()
        },
        "giant_components": sorted(
            giants, key=lambda item: (-item["size"], item["component_id"])
        )[:20],
        "giant_components_total": len(giants),
        "exact_body_label_conflict_groups": dict(exact_conflicts),
        "cross_snapshot_source_label_conflicts": same_source_label_conflicts,
        "edge_attempts": dict(attempts),
        "edge_unions": dict(unions),
        "diagnostics": dict(diagnostics),
        "near_new_edges": len(near_edges),
        "near_edge_source_pairs": dict(near_source_pairs),
        "near_edge_label_disagreements": near_label_disagreements,
        "weak_label_support": dict(support_report),
        "legacy_leakage_groups_checked": len(legacy_leakage),
        "legacy_leakage_groups_spanning_components": len(legacy_soft),
        "legacy_leakage_spanning_top_sizes": sorted(
            (x["members"] for x in legacy_soft), reverse=True
        )[:10],
        "provisional_split_guards": len(guards),
        "provisional_split_guards_by_task": {
            task: len(sizes) for task, sizes in guard_sizes.items()
        },
        "largest_split_guard_sizes": {
            task: sorted(sizes, reverse=True)[:10]
            for task, sizes in guard_sizes.items()
        },
        "notes": [
            "Labels are weak/source assertions; disagreements require review, not majority voting.",
            "The component manifest is private and assigns no train/test split.",
            "A giant component may be legitimate or overmerged; inspect its private member IDs before splitting.",
            "Legacy leakage IDs are advisory because the source pipeline grouped bare subjects across threads; spanning IDs need review before split allocation.",
            "Until soft legacy groups are adjudicated, allocate whole provisional_split_guard_id groups across train/test boundaries.",
        ],
    }
    if (
        diagnostics["oversized_near_bucket"]
        or diagnostics["near_skipped_long"]
        or diagnostics["source_identity_metadata_conflicts"]
    ):
        report["status"] = "review_required"
    output_dir.mkdir(parents=True, exist_ok=False)
    with (output_dir / "membership.jsonl").open("w", encoding="utf-8") as stream:
        for i in sorted(
            range(len(nodes)),
            key=lambda j: _node_bytes(nodes[j]["dataset_id"], nodes[j]["document_id"]),
        ):
            node = nodes[i]
            stream.write(
                json.dumps(
                    {
                        "dataset_id": node["dataset_id"],
                        "document_id": node["document_id"],
                        "task": node["task"],
                        "source_name": node["source_name"],
                        "component_id": component_ids[i],
                        "provisional_split_guard_id": guard_ids[i],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    with (output_dir / "near_edges.jsonl").open("w", encoding="utf-8") as stream:
        for edge in near_edges:
            stream.write(json.dumps(edge, ensure_ascii=False) + "\n")
    with (output_dir / "legacy_leakage_review.jsonl").open(
        "w", encoding="utf-8"
    ) as stream:
        for item in sorted(
            legacy_soft, key=lambda x: (x["dataset_id"], x["legacy_leakage_group_id"])
        ):
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    report["membership_sha256"] = file_sha256(output_dir / "membership.jsonl")
    report["near_edges_sha256"] = file_sha256(output_dir / "near_edges.jsonl")
    report["legacy_leakage_review_sha256"] = file_sha256(
        output_dir / "legacy_leakage_review.jsonl"
    )
    (output_dir / "component_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
