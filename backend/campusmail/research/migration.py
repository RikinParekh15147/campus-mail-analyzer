"""Explicit, conservative migration of legacy JSONL research exports.

The original input is never modified. Legacy labels are retained as partial weak
annotations; this module cannot establish review completeness from old fields.
"""

from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from .contracts import ResearchDocument
from .validation import _reject_constant, _unique_keys, validate_jsonl

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
    row, *, dataset_id, task, data_origin, source_type, usage_status, line_hash
):
    """Map only fields whose meaning is known; keep all others as legacy metadata."""
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
    if not isinstance(row.get("text"), str) or not row["text"].strip():
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
    if task == "academic":
        if row.get("actionability_label") is not None:
            raise ValueError("mixed_task_labels")
        label = row.get("primary_category")
        secondary = row.get("secondary_categories") or []
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
):
    input_path, output_path = Path(input_path), Path(output_path)
    if max_errors < 1 or max_line_bytes < 1:
        raise ValueError("Migration limits must be positive")
    if input_path.resolve() == output_path.resolve() or (
        input_path.exists()
        and output_path.exists()
        and os.path.samefile(input_path, output_path)
    ):
        raise ValueError("Migration output must differ from its source")
    # Check command-level declarations before reading private records.
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
    digest = sha256()
    report = {
        "status": "invalid",
        "source_lines": 0,
        "converted_records": 0,
        "error_count": 0,
        "errors": [],
    }

    def error(line, code):
        report["error_count"] += 1
        if len(report["errors"]) < max_errors:
            report["errors"].append({"line": line, "code": code})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix="campus-v1-migration-", dir=output_path.parent
    ) as temporary:
        candidate = Path(temporary) / "candidate.jsonl"
        with (
            input_path.open("rb") as source,
            candidate.open("w", encoding="utf-8") as target,
        ):
            while chunk := source.readline(max_line_bytes + 1):
                report["source_lines"] += 1
                line = report["source_lines"]
                line_digest = sha256(chunk)
                digest.update(chunk)
                if len(chunk) > max_line_bytes:
                    while not chunk.endswith(b"\n"):
                        chunk = source.readline(max_line_bytes + 1)
                        if not chunk:
                            break
                        digest.update(chunk)
                    error(line, "line_too_large")
                    continue
                try:
                    row = json.loads(
                        chunk.decode("utf-8"),
                        object_pairs_hook=_unique_keys,
                        parse_constant=_reject_constant,
                    )
                    converted = convert_legacy_row(
                        row,
                        dataset_id=dataset_id,
                        task=task,
                        data_origin=data_origin,
                        source_type=source_type,
                        usage_status=usage_status,
                        line_hash=line_digest.hexdigest(),
                    )
                except (
                    UnicodeDecodeError,
                    ValueError,
                    TypeError,
                    RecursionError,
                ) as exc:
                    code = (
                        str(exc)
                        if type(exc) is ValueError
                        and str(exc)
                        in {
                            "unsupported_legacy_record",
                            "dataset_id_mismatch",
                            "source_boundary_mismatch",
                            "missing_document_id",
                            "missing_text",
                            "invalid_source_metadata",
                            "unexpected_annotation_status",
                            "mixed_task_labels",
                        }
                        else "invalid_legacy_record"
                    )
                    error(line, code)
                    continue
                except ValidationError:
                    # Pydantic errors may contain private input; report only a code.
                    error(line, "schema_invalid")
                    continue
                target.write(json.dumps(converted, ensure_ascii=False) + "\n")
                report["converted_records"] += 1
        report["input_sha256"] = digest.hexdigest()
        report["errors_truncated"] = report["error_count"] > len(report["errors"])
        if report["error_count"] or not report["converted_records"]:
            if not report["converted_records"] and not report["error_count"]:
                error(0, "empty_dataset")
            return report
        validation = validate_jsonl(
            candidate, max_errors=max_errors, max_line_bytes=max_line_bytes
        )
        report["v2_validation"] = {
            key: validation[key]
            for key in ("status", "error_count", "errors", "errors_truncated")
        }
        if validation["status"] != "valid":
            return report
        candidate.replace(output_path)
        report["status"] = "valid"
        report["output_sha256"] = validation["input_sha256"]
    return report
