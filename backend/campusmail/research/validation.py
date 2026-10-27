"""Read-only streaming validation with a disk-backed reference index.

No document bodies or validation exception inputs enter the report.
Aggregate source-type counts still reveal provenance; treat reports as research data.
The temporary SQLite index holds IDs/hashes/timestamps, not document bodies.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from . import contracts
from .contracts import Contract, ResearchDocument, TASKS

SAFE_FIELDS = set().union(
    *(
        model.model_fields.keys()
        for model in vars(contracts).values()
        if isinstance(model, type) and issubclass(model, Contract)
    )
)


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")


def validate_jsonl(path, *, max_errors=100, max_line_bytes=16 * 1024 * 1024):
    if max_errors < 1 or max_line_bytes < 1:
        raise ValueError("Validation limits must be positive")
    digest = hashlib.sha256()
    report = {
        "schema_version": "2.0",
        "status": "valid",
        "physical_lines": 0,
        "schema_valid_records": 0,
        "unique_records": 0,
        "unavailable_text_records": 0,
        "error_count": 0,
        "errors": [],
        "reviewed_complete_counts": {task: 0 for task in TASKS},
        "real_reviewed_complete_counts": {task: 0 for task in TASKS},
        "unannotated_counts": {task: 0 for task in TASKS},
        "partial_counts": {task: 0 for task in TASKS},
    }
    sources, labels, origins, usages = Counter(), Counter(), Counter(), Counter()

    def error(line, code, **details):
        report["status"] = "invalid"
        report["error_count"] += 1
        if len(report["errors"]) < max_errors:
            report["errors"].append({"line": line, "code": code, **details})

    with TemporaryDirectory(prefix="campus-research-validation-") as temporary:
        db = sqlite3.connect(Path(temporary) / "references.sqlite")
        try:
            db.executescript("""
                CREATE TABLE documents(dataset TEXT, id TEXT, line INTEGER, stamp REAL,
                    task TEXT, digest TEXT, label TEXT, PRIMARY KEY(dataset,id));
                CREATE TABLE entities(dataset TEXT, document TEXT, id TEXT,
                    PRIMARY KEY(dataset,document,id));
                CREATE TABLE refs(dataset TEXT, target TEXT, entity TEXT, line INTEGER,
                    kind TEXT, cutoff REAL);
                CREATE INDEX duplicate_text ON documents(task,digest);
            """)
            with Path(path).open("rb") as stream:
                while chunk := stream.readline(max_line_bytes + 1):
                    report["physical_lines"] += 1
                    line = report["physical_lines"]
                    digest.update(chunk)
                    if len(chunk) > max_line_bytes:
                        # Drain the rest of this physical line without allocating it.
                        while not chunk.endswith(b"\n"):
                            chunk = stream.readline(max_line_bytes + 1)
                            if not chunk:
                                break
                            digest.update(chunk)
                        error(line, "line_too_large")
                        continue
                    if not chunk.strip():
                        error(line, "blank_line")
                        continue
                    try:
                        raw = json.loads(
                            chunk.decode("utf-8"),
                            object_pairs_hook=_unique_keys,
                            parse_constant=_reject_constant,
                        )
                    except UnicodeDecodeError:
                        error(line, "invalid_utf8")
                        continue
                    except (ValueError, RecursionError):
                        error(line, "invalid_json")
                        continue
                    try:
                        document = ResearchDocument.model_validate(raw)
                    except ValidationError as exc:
                        # Retain only known contract field names and indices; arbitrary
                        # keys, inputs and exception messages may contain private text.
                        violations = exc.errors(
                            include_input=False,
                            include_context=False,
                            include_url=False,
                        )
                        error(
                            line,
                            "schema_invalid",
                            validation_types=sorted({e["type"] for e in violations}),
                            violations=[
                                {
                                    "field": [
                                        part
                                        if isinstance(part, int) or part in SAFE_FIELDS
                                        else "<unknown_field>"
                                        for part in e["loc"]
                                    ],
                                    "type": e["type"],
                                }
                                for e in violations[:20]
                            ],
                        )
                        continue
                    report["schema_valid_records"] += 1
                    label = (
                        document.primary_category
                        if document.task == "academic"
                        else (
                            str(document.actionability_label).lower()
                            if document.actionability_label is not None
                            else None
                        )
                    )
                    text_hash = hashlib.sha256(
                        " ".join(
                            (document.subject + " " + document.text).casefold().split()
                        ).encode("utf-8")
                    ).hexdigest()
                    try:
                        db.execute(
                            "INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                            (
                                document.dataset_id,
                                document.document_id,
                                line,
                                document.sent_at.timestamp()
                                if document.sent_at
                                else None,
                                document.task,
                                text_hash,
                                label,
                            ),
                        )
                    except sqlite3.IntegrityError:
                        error(line, "duplicate_document_id")
                        continue
                    report["unique_records"] += 1
                    report["unavailable_text_records"] += (
                        document.text_status == "unavailable"
                    )
                    sources[document.source_type] += 1
                    origins[document.data_origin] += 1
                    usages[document.usage_status] += 1
                    if label is not None:
                        labels[f"{document.task}:{label}"] += 1
                    for task in TASKS:
                        status = getattr(document.annotation_status, task)
                        if status.completeness == "unannotated":
                            report["unannotated_counts"][task] += 1
                        elif status.completeness == "partial":
                            report["partial_counts"][task] += 1
                        if document.gold_eligible(task):
                            report["reviewed_complete_counts"][task] += 1
                            if document.data_origin != "synthetic":
                                report["real_reviewed_complete_counts"][task] += 1
                    for entity in document.entities:
                        db.execute(
                            "INSERT INTO entities VALUES(?,?,?)",
                            (
                                document.dataset_id,
                                document.document_id,
                                entity.entity_id,
                            ),
                        )
                    references = [
                        (target, None, "context")
                        for target in document.context_document_ids
                    ]
                    if document.parent_document_id:
                        references.append((document.parent_document_id, None, "parent"))
                    references.extend(
                        (r.target_document_id, r.target_entity_id, "relationship")
                        for r in document.relationships
                    )
                    references.extend(
                        (r.target_document_id, None, "grouping")
                        for r in document.grouping_relations
                    )
                    for target, entity, kind in references:
                        db.execute(
                            "INSERT INTO refs VALUES(?,?,?,?,?,?)",
                            (
                                document.dataset_id,
                                target,
                                entity,
                                line,
                                kind,
                                document.context_cutoff_at.timestamp()
                                if document.context_cutoff_at
                                else None,
                            ),
                        )
            if report["physical_lines"] == 0:
                error(0, "empty_dataset")
            for (
                line,
                kind,
                cutoff,
                target,
                stamp,
                entity,
                matched_entity,
            ) in db.execute("""
                SELECT r.line,r.kind,r.cutoff,d.id,d.stamp,r.entity,e.id
                FROM refs r LEFT JOIN documents d ON d.dataset=r.dataset AND d.id=r.target
                LEFT JOIN entities e ON e.dataset=r.dataset AND e.document=r.target AND e.id=r.entity
                ORDER BY r.line,r.rowid
            """):
                if target is None:
                    error(line, "missing_reference", reference_kind=kind)
                elif entity is not None and matched_entity is None:
                    error(line, "missing_entity_reference", reference_kind=kind)
                if target is not None and cutoff is not None:
                    if stamp is None:
                        error(line, "unverified_context_time", reference_kind=kind)
                    elif stamp > cutoff:
                        error(line, "future_context", reference_kind=kind)
            # Detect disagreement even across datasets; corpus source boundaries do not
            # make duplicate text independent. Dataset grouping itself comes in DATA-04.
            for (line,) in db.execute("""
                SELECT MIN(line) FROM documents WHERE label IS NOT NULL
                GROUP BY task,digest HAVING COUNT(DISTINCT label)>1
                ORDER BY MIN(line)
            """):
                error(line, "conflicting_duplicate_labels")
        finally:
            db.close()
    report.update(
        input_sha256=digest.hexdigest(),
        errors_truncated=report["error_count"] > len(report["errors"]),
        source_counts=dict(sorted(sources.items())),
        label_counts=dict(sorted(labels.items())),
        origin_counts=dict(sorted(origins.items())),
        usage_counts=dict(sorted(usages.items())),
        limits={"max_errors": max_errors, "max_line_bytes": max_line_bytes},
        notes=[
            "Schema-valid counts are structural counts, not final benchmark eligibility.",
            "Complete human-review metadata is asserted provenance, not independent proof of annotation quality.",
            "Usage status, group-disjoint splits and independent review still require research approval/curation.",
            "Legacy v1 exports are not automatically converted or relabeled.",
        ],
    )
    return report
