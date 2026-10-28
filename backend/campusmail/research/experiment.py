"""Pinned, private rules-only development experiment runs."""

from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from pydantic import ValidationError

from ..nlp import analyze
from ..preprocessing import PREPROCESSING_VERSION
from .contracts import ResearchDocument
from .development_protocol import ACCEPTED_RESERVATION, verify_development_selection
from .files import file_sha256, jsonl_records
from .metrics import evaluate_reviewed_components
from .validation import _reject_constant, _unique_keys

CODE_FILES = ("nlp.py", "candidates.py", "preprocessing.py", "models.py", "research/contracts.py",
              "research/development_protocol.py", "research/files.py",
              "research/metrics.py", "research/source_policy.py",
              "research/validation.py", "research/experiment.py")


def _digest_code():
    root = Path(__file__).resolve().parents[1]
    digest = sha256()
    for relative in CODE_FILES:
        path = root / relative
        digest.update(relative.encode() + b"\0")
        digest.update(bytes.fromhex(file_sha256(path)))
    return digest.hexdigest()


def run_rules_experiment(input_path, manifest_path, output_root, private_root,
                         *, expected_input_sha256, expected_manifest_sha256,
                         seed=17, fixture_mode=False):
    """Score pinned development v2 rows and publish one immutable private run."""
    input_path, manifest_path = Path(input_path), Path(manifest_path)
    output_root, private_root = Path(output_root).resolve(), Path(private_root).resolve()
    if type(seed) is not int or seed < 0:
        raise ValueError("Experiment seed must be a nonnegative integer")
    project_private = (Path(__file__).resolve().parents[3] / "artifacts/research/experiments").resolve()
    if not fixture_mode and private_root != project_private:
        raise ValueError("Research runs require the project private research root")
    if output_root == private_root or not output_root.is_relative_to(private_root):
        raise ValueError("Experiment output must stay under the private research root")
    input_hash = file_sha256(input_path)
    manifest_hash = file_sha256(manifest_path)
    if input_hash != expected_input_sha256 or manifest_hash != expected_manifest_sha256:
        raise ValueError("Pinned input or selection manifest checksum changed")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"),
                              object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise ValueError("Invalid selection manifest JSON") from None
    if not isinstance(manifest, dict):
        raise ValueError("Selection manifest must be an object")
    schema_version = "development-selection-v1" if fixture_mode else "development-selection-v2"
    if (manifest.get("schema_version") != schema_version
        or manifest.get("partition") != "development"
        or not isinstance(manifest.get("document_ids"), list)
        or not isinstance(manifest.get("guard_ids"), list)
        or not manifest["document_ids"] or not manifest["guard_ids"]):
        raise ValueError("Expected a nonempty development selection manifest")
    ids = manifest["document_ids"]
    guards = manifest["guard_ids"]
    if (not isinstance(manifest.get("dataset_id"), str) or not manifest["dataset_id"]
        or any(not isinstance(value, str) or not value.strip() for value in ids + guards)):
        raise ValueError("Selection manifest has invalid identifiers")
    if len(ids) != len(set(ids)) or len(guards) != len(set(guards)):
        raise ValueError("Selection manifest contains duplicate IDs")
    if not fixture_mode:
        reservation_dir = Path(__file__).resolve().parents[3] / "artifacts/research" / ACCEPTED_RESERVATION
        verify_development_selection(input_path, manifest_path, reservation_dir)
    documents = []
    seen = set()
    for line, row, _, error in jsonl_records(input_path):
        if error or row is None:
            raise ValueError(f"Invalid research input at line {line}: {error}")
        try:
            doc = ResearchDocument.model_validate(row)
        except ValidationError as exc:
            fields = sorted({".".join(str(part) for part in error["loc"])
                             for error in exc.errors(include_input=False)})
            raise ValueError(f"Invalid research document at line {line}: {', '.join(fields[:10])}") from None
        if doc.document_id in seen or doc.dataset_id != manifest.get("dataset_id"):
            raise ValueError("Duplicate or dataset-mismatched research document")
        guard = doc.leakage_group_id if fixture_mode else manifest["document_guards"][doc.document_id]
        if guard not in guards or doc.document_id not in ids:
            raise ValueError("Document is outside pinned development selection")
        if doc.usage_status == "quarantined" or (
            not fixture_mode and (doc.data_origin != "designated_research"
                                  or doc.task != "academic"
                                  or doc.text_status != "available")
        ):
            raise ValueError("Disallowed source for this development run")
        seen.add(doc.document_id)
        documents.append(doc)
    if seen != set(ids):
        raise ValueError("Selection manifest and research input differ")
    used_guards = ({doc.leakage_group_id for doc in documents} if fixture_mode
                   else {manifest["document_guards"][doc.document_id] for doc in documents})
    if set(guards) != used_guards:
        raise ValueError("Selection manifest has unused or missing guards")
    if not fixture_mode and not any(doc.gold_eligible(task) for doc in documents
                                    for task in ("classification", "dates", "actions")):
        raise ValueError("Research run requires at least one reviewed task")
    dependencies = {name: version(name) for name in ("numpy", "pydantic", "scikit-learn")}
    dependency_spec_hash = file_sha256(Path(__file__).resolve().parents[3] / "pyproject.toml")
    identity = {
        "input_sha256": input_hash, "selection_sha256": manifest_hash,
        "code_sha256": _digest_code(), "seed": seed,
        "fixture_mode": fixture_mode,
        "research_schema_version": "2.0",
        "selection_schema_version": schema_version,
        "preprocessing_version": PREPROCESSING_VERSION,
        "dependency_spec_sha256": dependency_spec_hash,
        "python": ".".join(map(str, sys.version_info[:3])),
        "dependencies": dependencies, "pipeline": "rules_only_v1",
    }
    run_id = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if private_root.stat().st_mode & 0o077:
        raise ValueError("Private research root must be owner-only")
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output_root.stat().st_mode & 0o077:
        raise ValueError("Experiment output root must be owner-only")
    final = output_root / run_id
    lock = output_root / ("." + run_id + ".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    temporary = None
    try:
        if final.exists():
            raise FileExistsError("Experiment run already exists")
        temporary = Path(tempfile.mkdtemp(prefix=".experiment-", dir=output_root))
        temporary.chmod(0o700)
        pairs = []
        with (temporary / "predictions.jsonl").open("w", encoding="utf-8") as stream:
            os.chmod(stream.name, 0o600)
            for document in documents:
                prediction = analyze(document.text, document.subject,
                                     document.sent_at.isoformat() if document.sent_at else None)
                pairs.append((document, prediction))
                stream.write(json.dumps({"document_id": document.document_id,
                                         "prediction": prediction}, sort_keys=True) + "\n")
        metrics = evaluate_reviewed_components(pairs)
        for name, value in (
            ("metrics.json", metrics),
            ("run.json", {**identity, "run_id": run_id,
                          "dataset_id": manifest["dataset_id"],
                          "documents": len(documents),
                          "label_status": "fixture_only" if fixture_mode else "reviewed_tasks_only"}),
        ):
            path = temporary / name
            path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            path.chmod(0o600)
        temporary.rename(final)
        temporary = None
    finally:
        os.close(descriptor)
        lock.unlink(missing_ok=True)
        if temporary is not None:
            shutil.rmtree(temporary)
    return {"run_id": run_id, "output_dir": str(final),
            "documents": len(documents), "metrics": metrics}
