"""Read-only setup diagnostics. Never opens credentials or deserializes models."""

from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import tomllib

from .paths import PROJECT
from .model_registry import model_health

DATASETS = {
    "academic": "dataset/mail/scoped_run/sanitized/documents.jsonl",
    "actionability": "dataset/public/normalized/charlie9_verified.jsonl",
}


def installed_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def inspect_assets(project, sklearn_version=None):
    project = Path(project)
    datasets = {
        task: {
            "path": relative,
            "status": "present" if (project / relative).is_file() else "missing",
        }
        for task, relative in DATASETS.items()
    }
    models = {}
    for task in DATASETS:
        directory = project / "artifacts/models" / task
        health = model_health(directory, task=task)
        row = {
            "path": f"artifacts/models/{task}/classifier.joblib",
            "status": "missing",
            "bundle_health": health,
        }
        if health["status"] == "verified":
            row["status"] = "verified"
        if health["status"] != "verified" and (directory / "classifier.joblib").is_file():
            row["status"] = "metadata_missing_unverified"
            if (directory / "metrics.json").is_file():
                try:
                    # Bound metadata reads; never inspect or execute the serialized model.
                    with (directory / "metrics.json").open("rb") as stream:
                        raw = stream.read(2_000_001)
                    if len(raw) > 2_000_000:
                        raise ValueError("Metadata too large")
                    report = json.loads(raw)
                    trained_version = report.get("sklearn_version")
                    if not isinstance(trained_version, str):
                        raise ValueError("Missing version")
                    row["trained_sklearn_version"] = trained_version
                    row["status"] = (
                        "metadata_matches_unverified"
                        if trained_version == sklearn_version
                        else "incompatible_metadata"
                    )
                except (OSError, ValueError, TypeError, AttributeError):
                    row["status"] = "invalid_metadata"
        models[task] = row
    return {"datasets": datasets, "models": models}


def dependency_checks():
    """Read installed requirements, falling back to source metadata before installation."""
    try:
        requirements = metadata.requires("campus-mail-analyser") or []
    except metadata.PackageNotFoundError:
        with (PROJECT / "pyproject.toml").open("rb") as stream:
            requirements = tomllib.load(stream)["project"]["dependencies"]
    try:
        from packaging.requirements import Requirement
    except ImportError:
        return [{"name": "packaging", "status": "missing", "version": None}]
    results = []
    for raw in requirements:
        requirement = Requirement(raw)
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        version = installed_version(requirement.name)
        results.append(
            {
                "name": requirement.name,
                "required": str(requirement.specifier),
                "version": version,
                "status": "missing"
                if version is None
                else (
                    "ok"
                    if requirement.specifier.contains(version)
                    else "version_mismatch"
                ),
            }
        )
    return results


def import_checks():
    # Subprocess isolates broken native imports and limits their duration. Output from
    # dependencies is deliberately not echoed: diagnostics should not leak local data.
    checks = []
    for module in ("numpy", "scipy", "sklearn", "fastapi", "keyring", "zoneinfo"):
        probe = (
            "from zoneinfo import ZoneInfo; ZoneInfo('Asia/Kolkata')"
            if module == "zoneinfo"
            else f"import {module}"
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", probe],
                capture_output=True,
                timeout=30,
            )
            status = "ok" if result.returncode == 0 else "import_failed"
        except (OSError, subprocess.TimeoutExpired):
            status = "import_failed_or_timeout"
        checks.append({"module": module, "status": status})
    return checks


def diagnose(project=PROJECT, require_datasets=False):
    dependencies = dependency_checks()
    imports = import_checks()
    assets = inspect_assets(project, installed_version("scikit-learn"))
    errors = any(row["status"] != "ok" for row in dependencies + imports)
    errors |= any(
        row["status"] in ("incompatible_metadata", "invalid_metadata")
        for row in assets["models"].values()
    )
    errors |= any(
        (Path(project) / "artifacts/models" / task / "active.json").exists()
        and row["bundle_health"]["status"] != "verified"
        for task, row in assets["models"].items()
    )
    if require_datasets:
        errors |= any(row["status"] == "missing" for row in assets["datasets"].values())
    academic_status = assets["models"]["academic"]["status"]
    return {
        "status": "error" if errors else "ok",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.system(),
            "architecture": platform.machine(),
            "isolated": sys.prefix != sys.base_prefix,
            "numerical_versions": {
                name: installed_version(name)
                for name in ("numpy", "scipy", "scikit-learn", "joblib")
            },
        },
        "dependencies": dependencies,
        "imports": imports,
        **assets,
        "mode": "verified_model" if academic_status == "verified" else "rules_only",
        "guidance": [
            "Use the project virtual environment and rerun setup if dependency/import checks fail.",
            "Missing datasets are optional for development; use --require-datasets for research preflight.",
            "Only an explicitly activated, checksum-verified academic model is loaded; otherwise classification uses local rules.",
            "Unactivated model files and matching metadata are not loaded.",
            "No credential vault, provider API, dataset content or environment secrets were read.",
        ],
    }
