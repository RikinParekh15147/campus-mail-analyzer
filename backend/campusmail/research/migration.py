"""Explicit, conservative migration of legacy JSONL research exports.

The original input is never modified. Legacy labels are retained as partial weak
annotations; this module cannot establish review completeness from old fields.
"""

from hashlib import sha256
from collections import Counter
import sqlite3
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from .contracts import ResearchDocument
from .validation import validate_jsonl
from .files import file_sha256, jsonl_records

GROUP_FIELDS = (
    "thread_id",
    "parent_document_id",
    "duplicate_group_id",
    "template_group_id",
    "leakage_group_id",
    "update_family_id",
)
COPY_FIELDS = (
    "subject",
    "original_text",
    "offset_map",
    "sent_at",
    "timezone",
    "context_cutoff_at",
    "context_document_ids",
    *GROUP_FIELDS,
)
MAPPED_FIELDS = {
    "schema_version",
    "dataset_id",
    "document_id",
    "task",
    "data_origin",
    "source_type",
    "usage_status",
    "text",
    "primary_category",
    "secondary_categories",
    "secondary_categories_complete",
    "actionability_label",
    "label_provenance",
    "source_metadata",
    *COPY_FIELDS,
}


def convert_legacy_row(
    row,
    *,
    dataset_id,
    task,
    data_origin,
    source_type,
    usage_status,
    line_hash,
    policy="strict",
    input_format="document_v1",
):
    """Map only fields whose meaning is known; keep all others as legacy metadata."""
    original_row = row
    if input_format == "sentence_actionability":
        if task != "actionability" or data_origin not in ("public", "synthetic"):
            raise ValueError("source_boundary_mismatch")
        if (
            row.get("task") != "sentence_actionability"
            or type(row.get("label")) is not int
            or row["label"] not in (0, 1)
        ):
            raise ValueError("invalid_public_actionability")
        row = {
            **row,
            "document_id": row.get("record_id"),
            "task": "actionability",
            "actionability_label": bool(row["label"]),
            "label_provenance": "source",
        }
    if not isinstance(row, dict) or row.get("schema_version") not in (None, "1.0"):
        raise ValueError("unsupported_legacy_record")
    if row.get("dataset_id", dataset_id) != dataset_id:
        raise ValueError("dataset_id_mismatch")
    if (
        row.get("task", task) != task
        or row.get("data_origin", data_origin) != data_origin
    ):
        raise ValueError("source_boundary_mismatch")
    if row.get("usage_status", usage_status) != usage_status:
        raise ValueError("source_boundary_mismatch")
    if not isinstance(row.get("document_id"), str) or not row["document_id"].strip():
        raise ValueError("missing_document_id")
    if not isinstance(row.get("text"), str) or (
        not row["text"].strip() and policy == "strict"
    ):
        raise ValueError("missing_text")
    if not isinstance(row.get("source_metadata", {}), dict):
        raise ValueError("invalid_source_metadata")
    if "annotation_status" in row:
        raise ValueError("unexpected_annotation_status")
    result = {
        "schema_version": "2.0",
        "dataset_id": dataset_id,
        "document_id": row["document_id"],
        "task": task,
        "data_origin": data_origin,
        "source_type": row.get("source_type") or source_type,
        "usage_status": usage_status,
        "text": row["text"],
        "source_metadata": {
            "legacy_source_metadata": row.get("source_metadata", {}),
            "legacy_task": original_row.get("task"),
            "legacy_labels": {
                k: original_row.get(k)
                for k in (
                    "primary_category",
                    "secondary_categories",
                    "label",
                    "original_label",
                )
            },
            "migration_changes": [],
            "legacy_extra_fields": {
                key: value for key, value in row.items() if key not in MAPPED_FIELDS
            },
            "legacy_label_provenance": row.get("label_provenance"),
            "legacy_secondary_categories_complete": row.get(
                "secondary_categories_complete"
            ),
            "legacy_line_sha256": line_hash,
        },
    }
    result.update({key: row[key] for key in COPY_FIELDS if key in row})
    parent = row.get("source_metadata", {}).get("parent_document_id")
    if parent:
        if result.get("parent_document_id") not in (None, parent):
            raise ValueError("parent_identity_mismatch")
        result["parent_document_id"] = parent
    if task == "academic":
        if row.get("actionability_label") is not None:
            raise ValueError("mixed_task_labels")
        label = row.get("primary_category")
        secondary = row.get("secondary_categories") or []
        if policy == "preserve_context" and isinstance(secondary, list):
            unique = list(dict.fromkeys(x for x in secondary if x != label))
            if unique != secondary:
                result["source_metadata"]["migration_changes"].append(
                    "duplicate_categories_removed"
                )
            secondary = unique
        if label is not None or secondary:
            result["primary_category"] = label
            result["secondary_categories"] = secondary
            result["secondary_categories_complete"] = False
            result["annotation_status"] = {
                "classification": {"completeness": "partial", "provenance": "weak"}
            }
    else:
        if row.get("primary_category") is not None or row.get("secondary_categories"):
            raise ValueError("mixed_task_labels")
        label = row.get("actionability_label")
        if label is not None:
            result["actionability_label"] = label
            result["annotation_status"] = {
                "classification": {"completeness": "partial", "provenance": "weak"}
            }
    if input_format == "sentence_actionability" and "annotation_status" in result:
        result["annotation_status"]["classification"]["provenance"] = "source"
    if not row["text"].strip():
        result["text_status"] = "unavailable"
        for field in (
            "primary_category",
            "secondary_categories",
            "secondary_categories_complete",
            "actionability_label",
            "annotation_status",
        ):
            result.pop(field, None)
        result["source_metadata"]["migration_changes"].append(
            "unavailable_text_context_only"
        )
    # Unknown legacy arrays remain in legacy_extra_fields, never promoted to gold.
    ResearchDocument.model_validate(result)
    return result


def migrate_v1_jsonl(
    input_path,
    output_path,
    *,
    dataset_id,
    task,
    data_origin,
    source_type,
    usage_status="unverified",
    max_errors=100,
    max_line_bytes=16 * 1024 * 1024,
    policy="strict",
    input_format="document_v1",
    relationships_path=None,
):
    """Stage on disk, preserve source identities, and publish only a valid corpus.

    preserve_context retains blank sources as explicitly unavailable context nodes,
    normalizes repeated category entries and withholds conflicting class labels.
    It never chooses a winning annotation or drops a document/reference.
    """
    input_path, output_path = Path(input_path), Path(output_path)
    if max_errors < 1 or max_line_bytes < 1:
        raise ValueError("Migration limits must be positive")
    if policy not in ("strict", "preserve_context") or input_format not in (
        "document_v1",
        "sentence_actionability",
    ):
        raise ValueError("Unknown migration policy or format")
    sources = [input_path] + ([Path(relationships_path)] if relationships_path else [])
    for source in sources:
        if source.resolve() == output_path.resolve() or (
            source.exists()
            and output_path.exists()
            and os.path.samefile(source, output_path)
        ):
            raise ValueError("Migration output must differ from its sources")
    ResearchDocument.model_validate(
        {
            "schema_version": "2.0",
            "dataset_id": dataset_id,
            "document_id": "preflight",
            "task": task,
            "data_origin": data_origin,
            "source_type": source_type,
            "usage_status": usage_status,
            "text": "preflight",
        }
    )
    hashes = [file_sha256(p) for p in sources]
    report = {
        "status": "invalid",
        "source_lines": 0,
        "converted_records": 0,
        "published_records": 0,
        "error_count": 0,
        "errors": [],
        "policy": policy,
        "input_format": input_format,
        "input_sha256": hashes[0],
        "dataset_id": dataset_id,
        "changes": {},
        "changed_lines": [],
        "relationship_records": 0,
    }
    changes = Counter()

    def error(line, code, source="documents"):
        report["error_count"] += 1
        if len(report["errors"]) < max_errors:
            report["errors"].append({"line": line, "code": code, "source": source})

    def changed(line, codes):
        for code in codes:
            changes[code] += 1
        if codes and len(report["changed_lines"]) < max_errors:
            report["changed_lines"].append({"line": line, "codes": codes})

    def finish():
        report["errors_truncated"] = report["error_count"] > len(report["errors"])
        report["changes"] = dict(changes)
        report["changed_lines_truncated"] = report.get("changed_records", 0) > len(
            report["changed_lines"]
        )
        return report

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix="campus-v1-migration-", dir=output_path.parent
    ) as temporary:
        candidate = Path(temporary) / "candidate.jsonl"
        db = sqlite3.connect(Path(temporary) / "stage.sqlite")
        try:
            db.executescript("""
                CREATE TABLE docs(id TEXT PRIMARY KEY, line INTEGER, body TEXT, digest TEXT, label TEXT);
                CREATE INDEX text_labels ON docs(digest,label);
                CREATE TABLE edges(id TEXT PRIMARY KEY, source TEXT, target TEXT, body TEXT);
                CREATE INDEX edge_sources ON edges(source);
            """)
            for line, row, line_hash, problem in jsonl_records(
                input_path, max_line_bytes
            ):
                report["source_lines"] += 1
                if problem:
                    error(line, problem)
                    continue
                try:
                    converted = convert_legacy_row(
                        row,
                        dataset_id=dataset_id,
                        task=task,
                        data_origin=data_origin,
                        source_type=source_type,
                        usage_status=usage_status,
                        line_hash=line_hash,
                        policy=policy,
                        input_format=input_format,
                    )
                except ValidationError:
                    error(line, "schema_invalid")
                    continue
                except (ValueError, TypeError, RecursionError) as exc:
                    safe = {
                        "unsupported_legacy_record",
                        "dataset_id_mismatch",
                        "source_boundary_mismatch",
                        "missing_document_id",
                        "missing_text",
                        "invalid_source_metadata",
                        "unexpected_annotation_status",
                        "mixed_task_labels",
                        "invalid_public_actionability",
                        "parent_identity_mismatch",
                    }
                    error(
                        line,
                        str(exc)
                        if type(exc) is ValueError and str(exc) in safe
                        else "invalid_legacy_record",
                    )
                    continue
                digest = sha256(
                    " ".join(
                        (converted.get("subject", "") + " " + converted["text"])
                        .casefold()
                        .split()
                    ).encode()
                ).hexdigest()
                label = (
                    converted.get("primary_category")
                    if task == "academic"
                    else converted.get("actionability_label")
                )
                try:
                    db.execute(
                        "INSERT INTO docs VALUES(?,?,?,?,?)",
                        (
                            converted["document_id"],
                            line,
                            json.dumps(converted),
                            digest,
                            json.dumps(label) if label is not None else None,
                        ),
                    )
                except sqlite3.IntegrityError:
                    error(line, "duplicate_document_id")
                    continue
                report["converted_records"] += 1
            if not report["source_lines"]:
                error(0, "empty_dataset")
            if relationships_path:
                report["relationships_sha256"] = hashes[1]
                for line, edge, _, problem in jsonl_records(
                    relationships_path, max_line_bytes
                ):
                    if problem:
                        error(line, problem, "relationships")
                        continue
                    try:
                        from .contracts import GroupingRelation

                        link = GroupingRelation.model_validate(
                            {
                                "relationship_id": edge.get("relationship_id"),
                                "target_document_id": edge.get("target_id"),
                                "type": edge.get("type"),
                            }
                        )
                        if not db.execute(
                            "SELECT 1 FROM docs WHERE id=?", (edge.get("source_id"),)
                        ).fetchone():
                            error(line, "missing_source_reference", "relationships")
                            continue
                        db.execute(
                            "INSERT INTO edges VALUES(?,?,?,?)",
                            (
                                link.relationship_id,
                                edge["source_id"],
                                link.target_document_id,
                                json.dumps(edge),
                            ),
                        )
                    except (ValidationError, sqlite3.IntegrityError):
                        error(
                            line, "invalid_or_duplicate_relationship", "relationships"
                        )
                        continue
                    report["relationship_records"] += 1
            if report["error_count"]:
                return finish()
            with candidate.open("w", encoding="utf-8") as stream:
                for doc_id, line, body, conflict in db.execute("""
                    SELECT d.id,d.line,d.body,c.digest IS NOT NULL FROM docs d
                    LEFT JOIN (SELECT digest FROM docs WHERE label IS NOT NULL GROUP BY digest
                               HAVING COUNT(DISTINCT label)>1) c ON c.digest=d.digest ORDER BY d.line
                """):
                    document = json.loads(body)
                    codes = document["source_metadata"]["migration_changes"]
                    if conflict and policy == "preserve_context":
                        for field in (
                            "primary_category",
                            "secondary_categories",
                            "secondary_categories_complete",
                            "actionability_label",
                            "annotation_status",
                        ):
                            document.pop(field, None)
                        codes.append("conflicting_classification_withheld")
                    edges = [
                        json.loads(r[0])
                        for r in db.execute(
                            "SELECT body FROM edges WHERE source=? ORDER BY id",
                            (doc_id,),
                        )
                    ]
                    if edges:
                        document["source_metadata"]["legacy_relationships"] = edges
                        document["grouping_relations"] = [
                            {
                                "relationship_id": e["relationship_id"],
                                "target_document_id": e["target_id"],
                                "type": e["type"],
                            }
                            for e in edges
                        ]
                    if codes:
                        report["changed_records"] = report.get("changed_records", 0) + 1
                        changed(line, codes)
                    stream.write(json.dumps(document, ensure_ascii=False) + "\n")
            validation = validate_jsonl(
                candidate, max_errors=max_errors, max_line_bytes=max_line_bytes
            )
            report["v2_validation"] = validation
            if validation["status"] != "valid":
                report["error_count"] = validation["error_count"]
                report["errors"] = validation["errors"]
                return finish()
            if hashes != [file_sha256(p) for p in sources]:
                error(0, "source_changed_during_migration")
                return finish()
            candidate.replace(output_path)
            report.update(
                status="valid",
                output_sha256=validation["input_sha256"],
                published_records=report["converted_records"],
                source_unchanged=True,
            )
            return finish()
        finally:
            db.close()
