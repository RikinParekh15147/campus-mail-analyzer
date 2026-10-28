"""Freeze and verify reviewed development selection against accepted DATA-05 custody."""

from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from pydantic import ValidationError

from ..models import CATEGORIES
from .contracts import ResearchDocument
from .files import file_sha256, jsonl_records
from .source_policy import SPLIT_POLICY_VERSION, expected_split
from .validation import _reject_constant, _unique_keys

ACCEPTED_RESERVATION = "data05-20261028-reserved-v2"
ACCEPTED_REPORT_SHA256 = "07595cb9fe9ac510ea2fee3dd6e7db0f21c70ab37a3342ddb5d0a62ef62ad099"
FOLD_POLICY_VERSION = "guard-hash-round-robin-5-v1"
FOLD_SEED = "campus-mail-development-folds-20261028"


def _json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"),
                           object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise ValueError("Invalid pinned protocol JSON") from None
    if not isinstance(value, dict):
        raise ValueError("Pinned protocol JSON must be an object")
    return value


def _rows(path):
    for line, row, _, error in jsonl_records(path):
        if error or row is None:
            raise ValueError(f"Invalid pinned protocol JSONL at line {line}")
        yield row


def _reservation(reservation_dir, *, fixture_mode):
    folder = Path(reservation_dir).resolve()
    project = Path(__file__).resolve().parents[3]
    if not fixture_mode and folder != (project / "artifacts/research" / ACCEPTED_RESERVATION).resolve():
        raise ValueError("Research protocol requires the accepted DATA-05 reservation")
    report_path = folder / "reservation_report.json"
    report_hash = file_sha256(report_path)
    if not fixture_mode and report_hash != ACCEPTED_REPORT_SHA256:
        raise ValueError("Accepted DATA-05 reservation report changed")
    report = _json(report_path)
    if (report.get("status") != "valid" or report.get("policy_version") != SPLIT_POLICY_VERSION
        or not isinstance(report.get("file_sha256"), dict)):
        raise ValueError("Invalid DATA-05 reservation report")
    for name in ("allocation.jsonl", "private_identity_map.jsonl", "development_pack.jsonl"):
        if report["file_sha256"].get(name) != file_sha256(folder / name):
            raise ValueError("DATA-05 reservation sidecar changed")
    if not fixture_mode:
        membership = project / "artifacts/research/data04-20261027-short/membership.jsonl"
        if file_sha256(membership) != report.get("membership_sha256"):
            raise ValueError("DATA-04 membership changed after reservation")
    allocation = {}
    for row in _rows(folder / "allocation.jsonl"):
        guard, task, split = row.get("guard_id"), row.get("task"), row.get("split")
        if (not isinstance(guard, str) or not guard or guard in allocation
            or task != "academic" and task != "actionability"
            or split != expected_split(task, guard)):
            raise ValueError("Invalid DATA-05 guard allocation")
        allocation[guard] = row
    if len(allocation) != report.get("total_guards"):
        raise ValueError("DATA-05 allocation count changed")
    identities = {}
    for row in _rows(folder / "private_identity_map.jsonl"):
        review_id, guard = row.get("review_id"), row.get("provisional_split_guard_id")
        if (not isinstance(review_id, str) or not review_id or review_id in identities
            or guard not in allocation or allocation[guard]["split"] != "development"
            or row.get("source_name") != "scoped"):
            raise ValueError("Invalid DATA-05 development identity map")
        identities[review_id] = row
    pack_rows = list(_rows(folder / "development_pack.jsonl"))
    pack_ids = [row.get("review_id") for row in pack_rows]
    if (any(not isinstance(value, str) for value in pack_ids)
        or len(pack_ids) != len(set(pack_ids)) or set(pack_ids) != set(identities)
        or len(pack_ids) != report.get("development_pack_rows")):
        raise ValueError("DATA-05 pack and identity map differ")
    return report, report_hash, allocation, identities, dict(zip(pack_ids, pack_rows))


def _source_matches_pack(document, pack):
    def instant(value):
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            return object()

    return (
        document.subject == pack.get("subject", "")
        and document.text == pack.get("text")
        and document.text_status == pack.get("text_status", "available")
        and document.sent_at == instant(pack.get("sent_at"))
        and document.context_cutoff_at == instant(pack.get("context_cutoff_at"))
        and document.timezone == pack.get("timezone")
        and document.context_document_ids == pack.get("context_review_ids", [])
        and document.parent_document_id == pack.get("parent_review_id")
    )


def freeze_development_selection(input_path, reservation_dir, *, fixture_mode=False):
    """Return deterministic, reviewed-only v2 selection and support audit."""
    input_path = Path(input_path)
    report, report_hash, allocation, identities, pack = _reservation(
        reservation_dir, fixture_mode=fixture_mode)
    documents = []
    seen = set()
    dataset_id = None
    for line, row, _, error in jsonl_records(input_path):
        if error or row is None:
            raise ValueError(f"Invalid reviewed JSONL at line {line}")
        try:
            doc = ResearchDocument.model_validate(row)
        except ValidationError as exc:
            fields = sorted({".".join(str(part) for part in item["loc"])
                             for item in exc.errors(include_input=False)})
            raise ValueError(f"Invalid reviewed document at line {line}: {', '.join(fields[:10])}") from None
        if (doc.document_id in seen or doc.document_id not in identities
            or doc.task != "academic" or doc.data_origin != "designated_research"
            or doc.usage_status == "quarantined" or doc.text_status != "available"
            or not doc.gold_eligible("classification")
            or len(set(doc.annotation_status.classification.reviewer_ids)) < 2):
            raise ValueError("Development selection needs unique double-reviewed scoped academic records")
        if not _source_matches_pack(doc, pack[doc.document_id]):
            raise ValueError("Reviewed document differs from the pinned DATA-05 review pack")
        if dataset_id is not None and doc.dataset_id != dataset_id:
            raise ValueError("Development selection crosses datasets")
        dataset_id = doc.dataset_id
        seen.add(doc.document_id)
        documents.append(doc)
    if not documents:
        raise ValueError("Development selection has no reviewed documents")
    document_guards = {
        doc.document_id: identities[doc.document_id]["provisional_split_guard_id"]
        for doc in documents
    }
    guards = set(document_guards.values())
    if len(guards) < 2 or any(allocation[guard]["split"] != "development" for guard in guards):
        raise ValueError("Development folds require at least two independent development guards")
    ordered_guards = sorted(guards, key=lambda guard: (sha256(
        f"{FOLD_SEED}|{guard}".encode()).hexdigest(), guard))
    fold_count = min(5, len(ordered_guards))
    folds = {guard: index % fold_count for index, guard in enumerate(ordered_guards)}
    support = Counter(doc.primary_category for doc in documents)
    by_fold = defaultdict(Counter)
    groups_by_class = defaultdict(set)
    for doc in documents:
        guard = document_guards[doc.document_id]
        by_fold[folds[guard]][doc.primary_category] += 1
        groups_by_class[doc.primary_category].add(guard)
    return {
        "schema_version": "development-selection-v2", "partition": "development",
        "dataset_id": dataset_id, "source_name": "scoped",
        "input_sha256": file_sha256(input_path),
        "reservation_report_sha256": report_hash,
        "allocation_sha256": report["file_sha256"]["allocation.jsonl"],
        "identity_map_sha256": report["file_sha256"]["private_identity_map.jsonl"],
        "development_pack_sha256": report["file_sha256"]["development_pack.jsonl"],
        "membership_sha256": report.get("membership_sha256"),
        "split_policy_version": SPLIT_POLICY_VERSION,
        "fold_policy_version": FOLD_POLICY_VERSION,
        "fold_count": fold_count,
        "document_ids": sorted(seen),
        "guard_ids": sorted(guards),
        "document_guards": dict(sorted(document_guards.items())),
        "guard_folds": dict(sorted(folds.items())),
        "support": {
            "documents": len(documents), "independent_guards": len(guards),
            "class_documents": {label: support[label] for label in CATEGORIES},
            "class_guards": {label: len(groups_by_class[label]) for label in CATEGORIES},
            "missing_classes": [label for label in CATEGORIES if not support[label]],
            "folds": {str(fold): {
                "documents": sum(by_fold[fold].values()),
                "class_documents": {label: by_fold[fold][label] for label in CATEGORIES},
                "missing_classes": [label for label in CATEGORIES if not by_fold[fold][label]],
            } for fold in range(fold_count)},
        },
    }


def verify_development_selection(input_path, manifest_path, reservation_dir, *, fixture_mode=False):
    """Recreate selection from pinned custody; reject any changed field or mapping."""
    manifest = _json(manifest_path)
    expected = freeze_development_selection(input_path, reservation_dir, fixture_mode=fixture_mode)
    if manifest != expected:
        raise ValueError("Development selection differs from accepted DATA-05 custody")
    return expected
