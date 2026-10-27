"""Read-only inventory of the project's designated research snapshots.

Reports contain counts and hashes, not bodies, subjects, source identities or
provider maps. No downloaded collector code is executed and no archives expanded.
"""

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import tarfile
from tempfile import TemporaryDirectory

from .files import file_sha256, jsonl_records

SOURCES = {
    "scoped": "mail/scoped_run/sanitized/documents.jsonl",
    "broad": "mail/sanitized/documents.jsonl",
    "charlie9": "public/normalized/charlie9_verified.jsonl",
    "parakweet": "public/normalized/parakweet.jsonl",
    "durg_sample": "public/quarantine/durg_university/sample_documents.jsonl",
}


def normalized_hash(text):
    return hashlib.sha256(" ".join(text.casefold().split()).encode()).hexdigest()


def audit_corpus(project_root, *, verify_assets=True):
    root = Path(project_root).resolve() / "dataset"
    report = {
        "audit_version": "1.0",
        "status": "valid",
        "sources": {},
        "overlap": {},
        "assets": {},
    }
    inventory = defaultdict(lambda: {"files": 0, "bytes": 0})
    for directory, _, files in os.walk(root):
        for name in files:
            p = Path(directory) / name
            if p.is_symlink():
                continue
            relative = p.relative_to(root)
            area = (
                "/".join(relative.parts[:2])
                if len(relative.parts) > 2
                else relative.parts[0]
            )
            inventory[area]["files"] += 1
            inventory[area]["bytes"] += p.stat().st_size
    report["filesystem"] = dict(sorted(inventory.items()))
    with TemporaryDirectory(prefix="campus-corpus-audit-") as temporary:
        db = sqlite3.connect(Path(temporary) / "index.sqlite")
        try:
            db.executescript("""
                CREATE TABLE docs(source TEXT, id TEXT, line INTEGER, body TEXT, digest TEXT,
                    label TEXT, length INTEGER, thread TEXT, leakage TEXT, PRIMARY KEY(source,id));
                CREATE INDEX bodies ON docs(source,digest);
            """)
            for name, relative in SOURCES.items():
                path = root / relative
                if not path.is_file():
                    report["sources"][name] = {
                        "status": "missing",
                        "relative_path": relative,
                    }
                    report["status"] = "invalid"
                    continue
                fields = defaultdict(Counter)
                counts = {
                    k: Counter()
                    for k in (
                        "labels",
                        "sources",
                        "provenance",
                        "reviewed",
                        "empty_by_source",
                        "empty_by_label",
                        "date_roles",
                        "date_precision",
                    )
                }
                stats = Counter()
                input_hash = file_sha256(path)
                for line, row, _, problem in jsonl_records(path):
                    stats["physical_lines"] += 1
                    if problem:
                        stats[problem] += 1
                        continue
                    for key, value in row.items():
                        fields[key][type(value).__name__] += 1
                    text = row.get("text", "")
                    doc_id = row.get("document_id", row.get("record_id"))
                    if not isinstance(text, str) or not isinstance(doc_id, str):
                        stats["invalid_core_fields"] += 1
                        continue
                    label = row.get("primary_category", row.get("label"))
                    label_key = str(label) if label is not None else "null"
                    kind = row.get("source_type", "sentence_actionability")
                    counts["labels"][label_key] += 1
                    counts["sources"][kind] += 1
                    counts["provenance"][row.get("label_provenance", "source")] += 1
                    counts["reviewed"][
                        str(
                            row.get(
                                "human_reviewed",
                                row.get("human_reviewed_by_project", False),
                            )
                        ).lower()
                    ] += 1
                    if not text.strip():
                        stats["unusable_text"] += 1
                        counts["empty_by_source"][kind] += 1
                        counts["empty_by_label"][label_key] += 1
                    stats["empty_string"] += text == ""
                    stats["whitespace_only"] += bool(text) and not text.strip()
                    stats["labeled_usable"] += bool(text.strip()) and label is not None
                    stats["replacement_character_records"] += "\ufffd" in text
                    stats["date_annotations"] += len(row.get("dates", []))
                    stats["action_annotations"] += len(row.get("actions", []))
                    for date in row.get("dates", []):
                        stats["unresolved_date_values"] += (
                            date.get("normalized_value") is None
                        )
                        counts["date_roles"][str(date.get("role"))] += 1
                        counts["date_precision"][str(date.get("precision"))] += 1
                    try:
                        db.execute(
                            "INSERT INTO docs VALUES(?,?,?,?,?,?,?,?,?)",
                            (
                                name,
                                doc_id,
                                line,
                                json.dumps(row),
                                normalized_hash(text) if text.strip() else None,
                                label_key if label is not None else None,
                                len(text),
                                row.get("thread_id"),
                                row.get("leakage_group_id"),
                            ),
                        )
                    except sqlite3.IntegrityError:
                        stats["duplicate_document_ids"] += 1
                n = db.execute(
                    "SELECT COUNT(*) FROM docs WHERE source=?", (name,)
                ).fetchone()[0]
                quantiles = {}
                if n:
                    for q in (0, 50, 90, 95, 99, 100):
                        quantiles[str(q)] = db.execute(
                            "SELECT length FROM docs WHERE source=? ORDER BY length LIMIT 1 OFFSET ?",
                            (name, round((n - 1) * q / 100)),
                        ).fetchone()[0]
                duplicates = db.execute(
                    "SELECT COUNT(*),COALESCE(SUM(n-1),0) FROM (SELECT COUNT(*) n FROM docs WHERE source=? AND digest IS NOT NULL GROUP BY digest HAVING COUNT(*)>1)",
                    (name,),
                ).fetchone()
                conflicts = db.execute(
                    "SELECT COUNT(*),COALESCE(SUM(n),0) FROM (SELECT COUNT(*) n FROM docs WHERE source=? AND digest IS NOT NULL GROUP BY digest HAVING COUNT(DISTINCT label)>1)",
                    (name,),
                ).fetchone()
                per_class_groups = {
                    str(label): {"threads": threads, "declared_leakage_groups": groups}
                    for label, threads, groups in db.execute(
                        "SELECT label,COUNT(DISTINCT thread),COUNT(DISTINCT leakage) FROM docs WHERE source=? AND label IS NOT NULL AND digest IS NOT NULL GROUP BY label",
                        (name,),
                    )
                }
                result = {
                    "relative_path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": input_hash,
                    "records": n,
                    "counts": dict(stats),
                    "distributions": {k: dict(v) for k, v in counts.items()},
                    "field_types": {k: dict(v) for k, v in fields.items()},
                    "text_length_percentiles": quantiles,
                    "normalized_body_duplicate_groups": duplicates[0],
                    "duplicate_excess_rows": duplicates[1],
                    "conflicting_body_label_groups": conflicts[0],
                    "conflicting_body_label_rows": conflicts[1],
                    "class_declared_group_support": per_class_groups,
                }
                report["sources"][name] = result
                if input_hash != file_sha256(path):
                    result["source_changed"] = True
                    report["status"] = "invalid"
            # Reference and evidence checks use an indexed corpus, including unreadable context nodes.
            for name, result in report["sources"].items():
                if "records" not in result:
                    continue
                checks = Counter()

                def get(target):
                    found = db.execute(
                        "SELECT body FROM docs WHERE source=? AND id=?", (name, target)
                    ).fetchone()
                    return json.loads(found[0]) if found else None

                def span_check(span, default_id):
                    checks["evidence_spans_checked"] += 1
                    target = get(span.get("document_id", default_id))
                    a, b = span.get("start"), span.get("end")
                    evidence = span.get("text", span.get("raw_text"))
                    if (
                        target is None
                        or type(a) is not int
                        or type(b) is not int
                        or not 0 <= a < b <= len(target["text"])
                    ):
                        checks["invalid_evidence_bounds_or_target"] += 1
                    elif evidence is not None and target["text"][a:b] != evidence:
                        checks["evidence_text_mismatch"] += 1

                for doc_id, body in db.execute(
                    "SELECT id,body FROM docs WHERE source=?", (name,)
                ):
                    row = json.loads(body)
                    cutoff = row.get("context_cutoff_at")
                    try:
                        cutoff = (
                            datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
                            if cutoff
                            else None
                        )
                        stamp = (
                            datetime.fromisoformat(
                                row["sent_at"].replace("Z", "+00:00")
                            )
                            if row.get("sent_at")
                            else None
                        )
                        checks["missing_timestamp"] += stamp is None
                        if stamp and cutoff:
                            checks["source_after_cutoff"] += stamp > cutoff
                    except (ValueError, TypeError):
                        checks["invalid_timestamp"] += 1
                        cutoff = None
                    parent = row.get("parent_document_id") or row.get(
                        "source_metadata", {}
                    ).get("parent_document_id")
                    refs = [
                        (ref, "context") for ref in row.get("context_document_ids", [])
                    ] + ([(parent, "parent")] if parent else [])
                    for target, kind in refs:
                        checks[kind + "_references"] += 1
                        other = get(target)
                        if other is None:
                            checks["missing_" + kind] += 1
                        elif cutoff:
                            try:
                                stamp = datetime.fromisoformat(
                                    other["sent_at"].replace("Z", "+00:00")
                                )
                                checks["future_" + kind] += stamp > cutoff
                            except (ValueError, TypeError, KeyError):
                                checks["unverified_" + kind + "_time"] += 1
                    for key in (
                        "dates",
                        "actions",
                        "entities",
                        "resources",
                        "profile_evidence",
                        "reply_requests",
                    ):
                        for item in row.get(key, []):
                            if key == "dates":
                                span_check(item, doc_id)
                            if key == "actions" and "start" in item:
                                span_check(
                                    {**item, "text": item.get("sentence")}, doc_id
                                )
                            for span in item.get("evidence_spans", []):
                                span_check(span, doc_id)
                relationships = (root / SOURCES[name]).with_name("relationships.jsonl")
                if relationships.exists():
                    kinds = Counter()
                    for _, edge, _, problem in jsonl_records(relationships):
                        if problem:
                            checks["invalid_relationship_json"] += 1
                            continue
                        kinds[edge.get("type")] += 1
                        checks["relationship_records"] += 1
                        checks["missing_relationship_endpoints"] += (
                            get(edge.get("source_id")) is None
                            or get(edge.get("target_id")) is None
                        )
                        for span in edge.get("evidence_spans", []):
                            span_check(span, edge.get("source_id"))
                    result["relationships"] = {
                        "sha256": file_sha256(relationships),
                        "types": dict(kinds),
                    }
                result["reference_evidence_audit"] = dict(checks)
            for left, right in (("scoped", "broad"), ("charlie9", "parakweet")):
                common = db.execute(
                    """SELECT COUNT(*),SUM(a.labels!=b.labels) FROM
                    (SELECT digest,GROUP_CONCAT(DISTINCT label) labels FROM docs WHERE source=? AND digest IS NOT NULL GROUP BY digest) a
                    JOIN (SELECT digest,GROUP_CONCAT(DISTINCT label) labels FROM docs WHERE source=? AND digest IS NOT NULL GROUP BY digest) b USING(digest)""",
                    (left, right),
                ).fetchone()
                same_ids = db.execute(
                    "SELECT COUNT(*) FROM docs a JOIN docs b ON a.id=b.id WHERE a.source=? AND b.source=?",
                    (left, right),
                ).fetchone()[0]
                report["overlap"][left + ":" + right] = {
                    "normalized_body_texts": common[0],
                    "label_disagreement_texts": common[1] or 0,
                    "shared_document_ids": same_ids,
                }
        finally:
            db.close()
    if verify_assets and all(
        "records" in entry for entry in report["sources"].values()
    ):
        report["assets"] = audit_assets(root)
        for name in ("scoped", "broad"):
            declared = report["assets"][name]["declared_counts"]
            actual = report["sources"][name]
            actual["manifest_counts_reconciled"] = (
                declared["documents"] == actual["records"]
                and declared["per_source"] == actual["distributions"]["sources"]
                and declared["per_primary_category"]
                == actual["distributions"]["labels"]
                and declared["relationships"]
                == actual["reference_evidence_audit"]["relationship_records"]
            )
            if not actual["manifest_counts_reconciled"]:
                report["status"] = "invalid"
        if report["assets"]["integrity_failures"]:
            report["status"] = "invalid"
    for source in report["sources"].values():
        problems = (
            "invalid_json_object",
            "line_too_large",
            "invalid_core_fields",
            "duplicate_document_ids",
        )
        reference_problems = (
            "invalid_evidence_bounds_or_target",
            "evidence_text_mismatch",
            "missing_context",
            "missing_parent",
            "missing_relationship_endpoints",
            "invalid_relationship_json",
            "source_after_cutoff",
            "future_context",
            "future_parent",
            "invalid_timestamp",
            "unverified_context_time",
            "unverified_parent_time",
        )
        if any(source.get("counts", {}).get(key, 0) for key in problems) or any(
            source.get("reference_evidence_audit", {}).get(key, 0)
            for key in reference_problems
        ):
            report["status"] = "invalid"
    report["notes"] = [
        "Source annotations are not reviewed project gold; structural checks do not establish semantic accuracy.",
        "Body-only duplicate disagreements are diagnostic; differing subjects may explain some academic disagreements.",
        "Scoped/broad overlap is underestimated by text hashes when sanitization/extraction changed; shared source IDs are not independent samples.",
        "No sealed split, model training, OCR or private provider-map inspection is performed.",
    ]
    return report


def audit_assets(root):
    report = {}
    for name in ("scoped", "broad"):
        folder = (root / SOURCES[name]).parent
        path = folder / "attachments_manifest.jsonl"
        checks, statuses = Counter(), Counter()
        for _, row, _, problem in jsonl_records(path):
            checks["records"] += 1
            if problem:
                checks["invalid_json"] += 1
                continue
            statuses[str(row.get("extraction_status"))] += 1
            for field in ("local_path", "safe_export_path"):
                if not row.get(field):
                    checks[field + "_not_declared"] += 1
                    continue
                candidate = (folder / row[field].replace("\\", "/")).resolve()
                if not candidate.is_relative_to(root.resolve()):
                    checks[field + "_outside_dataset"] += 1
                    # Explicit legacy-layout fallback: trust neither an absolute
                    # path nor a filename alone. Accept only a local hash match.
                    if (
                        field == "local_path"
                        and row.get("file_hash")
                        and row.get("hash_algorithm") == "sha256"
                    ):
                        relocated = (
                            root
                            / "mail/private/attachments"
                            / Path(row.get("safe_filename", "")).name
                        )
                        if (
                            relocated.is_file()
                            and file_sha256(relocated) == row["file_hash"]
                        ):
                            checks["relocated_binary_hash_verified"] += 1
                elif not candidate.is_file():
                    checks[field + "_missing"] += 1
                else:
                    checks[field + "_exists"] += 1
                    if (
                        field == "local_path"
                        and row.get("file_hash")
                        and row.get("hash_algorithm") == "sha256"
                    ):
                        checks[
                            "binary_hash_verified"
                            if file_sha256(candidate) == row["file_hash"]
                            else "binary_hash_mismatch"
                        ] += 1
        manifest = folder / "collection_manifest.json"
        report[name] = {
            "manifest_sha256": file_sha256(path),
            "counts": dict(checks),
            "extraction_statuses": dict(statuses),
            "declared_counts": json.loads(manifest.read_text())["actual_counts"],
        }
    public = root / "public"
    checks = Counter()
    for source in json.loads((public / "source_registry.json").read_text()):
        for entry in source.get("files", []):
            path = public / entry["path"]
            checks["public_source_files_checked"] += 1
            checks[
                "verified"
                if path.is_file() and file_sha256(path) == entry["sha256"]
                else "missing_or_hash_mismatch"
            ] += 1
    archive = public / "quarantine/durg_university/archive/notices_dataset.tar.gz"
    digest = file_sha256(archive) if archive.exists() else None
    report["public_raw_files"] = dict(checks)
    catalogue = public / "quarantine/durg_notice_catalogue.json"
    report["catalogue"] = {
        "records": len(json.loads(catalogue.read_text())),
        "sha256": file_sha256(catalogue),
    }
    report["catalogue"]["matches_acquisition_sha256"] = (
        report["catalogue"]["sha256"]
        == "239c4a5c8dae0d0f1e40d068457ff5a06bf823c884c071c52100abd8c196a093"
    )
    official_root = public / "quarantine/official_institutional"
    official = Counter()
    for _, entry, _, problem in jsonl_records(official_root / "manifest.jsonl"):
        if problem:
            official["invalid_manifest_record"] += 1
        elif entry.get("status") != "downloaded":
            official["recorded_download_failure"] += 1
        else:
            path = (official_root / entry["resource_path"]).resolve()
            verified = (
                path.is_relative_to(official_root.resolve())
                and path.is_file()
                and file_sha256(path) == entry["sha256"]
            )
            official[
                "binary_hash_verified" if verified else "binary_missing_or_mismatch"
            ] += 1
    report["official_institutional"] = dict(official)
    sample_root = public / "quarantine/durg_university"
    sample_checks = Counter()
    for _, row, _, problem in jsonl_records(sample_root / "sample_documents.jsonl"):
        if problem:
            sample_checks["invalid_sample_json"] += 1
            continue
        path = (sample_root / row["resource_path"]).resolve()
        valid = (
            path.is_relative_to(sample_root.resolve())
            and path.is_file()
            and file_sha256(path) == row["sha256"]
        )
        sample_checks[
            "sample_pdf_hash_verified" if valid else "sample_pdf_missing_or_mismatch"
        ] += 1
        sample_checks["useful_extracted_text"] += (
            row.get("extraction_status") == "text_extracted"
        )
        sample_checks["truncated_extraction"] += bool(row.get("extraction_truncated"))
        for span in row.get("page_spans", []):
            sample_checks["page_spans_checked"] += 1
            if not 0 <= span["start"] <= span["end"] <= len(row["text"]):
                sample_checks["invalid_page_span"] += 1
    inventory = sample_root / "archive_inventory.jsonl"
    members = {}
    for _, entry, _, problem in jsonl_records(inventory):
        if problem:
            sample_checks["invalid_inventory_json"] += 1
        else:
            members[entry["archive_member"]] = entry["bytes"]
    sample_checks["archive_inventory_records"] = len(members)
    if archive.exists():
        with tarfile.open(archive, "r|gz") as stream:
            for member in stream:
                if member.isfile():
                    sample_checks["archive_files_checked"] += 1
                    expected = members.pop(member.name, None)
                    sample_checks["archive_member_mismatch"] += expected != member.size
        sample_checks["inventory_members_missing_from_archive"] = len(members)
    report["durg_sample"] = dict(sample_checks)
    report["durg_archive"] = {
        "bytes": archive.stat().st_size if archive.exists() else None,
        "sha256": digest,
        "matches_acquisition_sha256": digest
        == "62bc93a6c0271f6d41d3e624b79df3526a43a1f92ffa7fd65cb6635389338270",
    }
    failures = checks["missing_or_hash_mismatch"] + int(
        not report["durg_archive"]["matches_acquisition_sha256"]
    )
    failures += sum(
        sample_checks[k]
        for k in (
            "invalid_sample_json",
            "sample_pdf_missing_or_mismatch",
            "invalid_page_span",
            "invalid_inventory_json",
            "archive_member_mismatch",
            "inventory_members_missing_from_archive",
        )
    )
    for name in ("scoped", "broad"):
        counts = report[name]["counts"]
        failures += sum(
            counts.get(k, 0)
            for k in (
                "invalid_json",
                "binary_hash_mismatch",
                "local_path_missing",
                "safe_export_path_missing",
                "safe_export_path_outside_dataset",
            )
        )
        failures += max(
            0,
            counts.get("local_path_outside_dataset", 0)
            - counts.get("relocated_binary_hash_verified", 0),
        )
    report["integrity_failures"] = failures
    report["integrity_failures"] += (
        official["invalid_manifest_record"]
        + official["binary_missing_or_mismatch"]
        + int(not report["catalogue"]["matches_acquisition_sha256"])
    )
    return report
