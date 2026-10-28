"""Pinned model-bundle metadata. Verification never deserializes a model."""

from contextlib import contextmanager
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import tempfile

from .candidates import ANALYSIS_SCHEMA_VERSION
from .models import CATEGORIES
from .preprocessing import PREPROCESSING_VERSION


BUNDLE_SCHEMA_VERSION = "model-bundle-v1"
DEPENDENCIES = ("numpy", "scipy", "scikit-learn", "joblib")
ARTIFACTS = ("classifier.joblib", "metrics.json")
POINTER_SCHEMA_VERSION = "model-pointer-v1"
_BUNDLE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")


def _reject_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate model manifest key")
        result[key] = value
    return result


def _hash(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Model bundle file must be regular and non-symlinked")
    return path


def _taxonomy(task):
    if task == "academic":
        return list(CATEGORIES)
    if task == "actionability":
        return [False, True]
    raise ValueError("Unknown model task")


def _metrics(path):
    path = _regular(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError("Model metrics are too large")
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           object_pairs_hook=_unique_keys,
                           parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Invalid model metrics") from None
    if not isinstance(value, dict):
        raise ValueError("Model metrics must be an object")
    return value


def seal_bundle(directory, *, task, model_revision, thresholds):
    """Seal an existing candidate once; return the manifest digest to pin externally."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Model bundle directory must be regular")
    if not isinstance(model_revision, str) or not model_revision.strip():
        raise ValueError("Model revision is required")
    if not isinstance(thresholds, dict) or any(
        not isinstance(key, str) or not isinstance(value, (int, float))
        or isinstance(value, bool) or not 0 <= value <= 1
        for key, value in thresholds.items()
    ):
        raise ValueError("Thresholds must be named values from zero to one")
    taxonomy = _taxonomy(task)
    _metrics(directory / "metrics.json")
    files = {name: _hash(_regular(directory / name)) for name in ARTIFACTS}
    manifest = {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "task": task,
        "taxonomy": taxonomy,
        "preprocessing_version": PREPROCESSING_VERSION,
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "model_revision": model_revision,
        "thresholds": thresholds,
        "dependencies": {name: version(name) for name in DEPENDENCIES},
        "files": files,
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    descriptor = os.open(directory / "bundle.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        (directory / "bundle.json").unlink(missing_ok=True)
        raise
    return sha256(payload).hexdigest()


def verify_bundle(directory, *, task, expected_manifest_sha256):
    """Reject unpinned or incompatible artifacts before any joblib.load call."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Model bundle directory must be regular")
    if not isinstance(expected_manifest_sha256, str) or len(expected_manifest_sha256) != 64:
        raise ValueError("A pinned bundle manifest SHA-256 is required")
    path = _regular(directory / "bundle.json")
    if path.stat().st_size > 128_000 or _hash(path) != expected_manifest_sha256:
        raise ValueError("Model bundle manifest checksum mismatch")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"),
                              object_pairs_hook=_unique_keys,
                              parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Invalid model bundle manifest") from None
    if not isinstance(manifest, dict) or set(manifest) != {
        "bundle_schema_version", "task", "taxonomy", "preprocessing_version",
        "analysis_schema_version", "model_revision", "thresholds", "dependencies", "files",
    }:
        raise ValueError("Invalid model bundle manifest schema")
    if (manifest["bundle_schema_version"] != BUNDLE_SCHEMA_VERSION
        or manifest["task"] != task or manifest["taxonomy"] != _taxonomy(task)
        or manifest["preprocessing_version"] != PREPROCESSING_VERSION
        or manifest["analysis_schema_version"] != ANALYSIS_SCHEMA_VERSION
        or manifest["dependencies"] != {name: version(name) for name in DEPENDENCIES}
        or not isinstance(manifest["model_revision"], str)
        or not manifest["model_revision"].strip()
        or not isinstance(manifest["thresholds"], dict)
        or any(not isinstance(key, str) or type(value) not in (int, float)
               or not 0 <= value <= 1
               for key, value in manifest["thresholds"].items())
        or not isinstance(manifest["files"], dict)
        or set(manifest["files"]) != set(ARTIFACTS)):
        raise ValueError("Model bundle is incompatible with this runtime")
    for name in ARTIFACTS:
        if _hash(_regular(directory / name)) != manifest["files"][name]:
            raise ValueError(f"Model bundle artifact checksum mismatch: {name}")
    _metrics(directory / "metrics.json")
    return manifest


def _entry(entry):
    if (not isinstance(entry, dict) or set(entry) != {"bundle_id", "manifest_sha256"}
        or not isinstance(entry["bundle_id"], str)
        or not _BUNDLE_ID.fullmatch(entry["bundle_id"])
        or entry["bundle_id"] in (".", "..")
        or not isinstance(entry["manifest_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["manifest_sha256"])):
        raise ValueError("Invalid model pointer entry")
    return entry


def _pointer(task_dir):
    path = Path(task_dir) / "active.json"
    if not path.exists():
        return {"pointer_schema_version": POINTER_SCHEMA_VERSION,
                "revision": 0, "active": None, "previous": None}
    if path.stat().st_size > 4096:
        raise ValueError("Model pointer is too large")
    try:
        value = json.loads(_regular(path).read_text(encoding="utf-8"),
                           object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Invalid model pointer") from None
    if (not isinstance(value, dict)
        or set(value) != {"pointer_schema_version", "revision", "active", "previous"}
        or value["pointer_schema_version"] != POINTER_SCHEMA_VERSION
        or type(value["revision"]) is not int or value["revision"] < 0):
        raise ValueError("Invalid model pointer")
    for name in ("active", "previous"):
        if value[name] is not None:
            _entry(value[name])
    return value


def _bundle_path(task_dir, entry):
    _entry(entry)
    path = Path(task_dir) / "bundles" / entry["bundle_id"]
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Referenced model bundle is missing or symlinked")
    return path


def _verify_entry(task_dir, task, entry):
    path = _bundle_path(task_dir, entry)
    manifest = verify_bundle(path, task=task,
                             expected_manifest_sha256=entry["manifest_sha256"])
    return path / "classifier.joblib", manifest


def resolve_active_model(task_dir, *, task):
    """Return only an active, fully verified classifier path and manifest."""
    task_dir = Path(task_dir)
    if task_dir.is_symlink() or not task_dir.is_dir():
        raise ValueError("Model task directory is missing or symlinked")
    pointer = _pointer(task_dir)
    if pointer["active"] is None:
        raise ValueError("No active model bundle")
    return _verify_entry(task_dir, task, pointer["active"])


def model_health(task_dir, *, task):
    """Read-only health for diagnostics; no pickle deserialization."""
    try:
        path, manifest = resolve_active_model(task_dir, task=task)
    except Exception as exc:
        return {"status": "rules_only", "reason": str(exc)}
    return {"status": "verified", "model_revision": manifest["model_revision"],
            "bundle": path.parent.name}


def _atomic_pointer(task_dir, pointer):
    payload = (json.dumps(pointer, sort_keys=True, indent=2) + "\n").encode()
    descriptor, staged = tempfile.mkstemp(prefix=".active-", dir=task_dir)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, Path(task_dir) / "active.json")
        try:
            descriptor = os.open(task_dir, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            # Windows does not support opening a directory handle this way.
            pass
    finally:
        Path(staged).unlink(missing_ok=True)


@contextmanager
def _promotion_lock(task_dir):
    path = Path(task_dir) / ".promotion.lock"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


def promote_bundle(task_dir, *, task, bundle_id, manifest_sha256,
                   expected_revision):
    """Atomically switch a previously sealed bundle, preserving one rollback slot."""
    task_dir = Path(task_dir)
    if task_dir.is_symlink() or not task_dir.is_dir():
        raise ValueError("Model task directory is missing or symlinked")
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected pointer revision is required")
    entry = _entry({"bundle_id": bundle_id,
                    "manifest_sha256": manifest_sha256})
    with _promotion_lock(task_dir):
        _verify_entry(task_dir, task, entry)
        pointer = _pointer(task_dir)
        if pointer["revision"] != expected_revision:
            raise ValueError("Model pointer revision changed")
        if pointer["active"] is not None:
            _verify_entry(task_dir, task, pointer["active"])
        if pointer["active"] == entry:
            raise ValueError("Bundle is already active")
        updated = {"pointer_schema_version": POINTER_SCHEMA_VERSION,
                   "revision": expected_revision + 1,
                   "active": entry, "previous": pointer["active"]}
        _atomic_pointer(task_dir, updated)
        return updated


def rollback_bundle(task_dir, *, task, expected_revision):
    """Atomically restore the verified previous bundle; never edits profile data."""
    task_dir = Path(task_dir)
    if task_dir.is_symlink() or not task_dir.is_dir():
        raise ValueError("Model task directory is missing or symlinked")
    with _promotion_lock(task_dir):
        pointer = _pointer(task_dir)
        if type(expected_revision) is not int or pointer["revision"] != expected_revision:
            raise ValueError("Model pointer revision changed")
        if pointer["previous"] is None:
            raise ValueError("No previous model bundle")
        _verify_entry(task_dir, task, pointer["previous"])
        updated = {"pointer_schema_version": POINTER_SCHEMA_VERSION,
                   "revision": expected_revision + 1,
                   "active": pointer["previous"], "previous": pointer["active"]}
        _atomic_pointer(task_dir, updated)
        return updated
