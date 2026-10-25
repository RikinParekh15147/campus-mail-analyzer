import json
import os
from pathlib import Path
import subprocess
import sys

from campusmail.diagnostics import inspect_assets


def test_missing_research_assets_are_explicit_and_do_not_create_files(tmp_path):
    result = inspect_assets(tmp_path, sklearn_version="1.7.2")
    assert all(row["status"] == "missing" for row in result["datasets"].values())
    assert all(row["status"] == "missing" for row in result["models"].values())
    assert list(tmp_path.iterdir()) == []


def test_model_metadata_mismatch_is_detected_without_loading_pickle(tmp_path):
    directory = tmp_path / "artifacts/models/academic"
    directory.mkdir(parents=True)
    (directory / "classifier.joblib").write_bytes(b"not a trusted pickle")
    (directory / "metrics.json").write_text(json.dumps({"sklearn_version": "0.0"}))
    result = inspect_assets(tmp_path, sklearn_version="1.7.2")
    assert result["models"]["academic"]["status"] == "incompatible_metadata"


def test_matching_metadata_does_not_claim_artifact_integrity(tmp_path):
    directory = tmp_path / "artifacts/models/academic"
    directory.mkdir(parents=True)
    (directory / "classifier.joblib").write_bytes(b"not a trusted pickle")
    (directory / "metrics.json").write_text(json.dumps({"sklearn_version": "1.7.2"}))
    result = inspect_assets(tmp_path, sklearn_version="1.7.2")
    assert result["models"]["academic"]["status"] == "metadata_matches_unverified"
    (directory / "metrics.json").write_text("invalid JSON")
    assert (
        inspect_assets(tmp_path)["models"]["academic"]["status"] == "invalid_metadata"
    )


def test_doctor_reports_missing_data_without_accessing_credentials(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "campusmail", "doctor", "--project-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 0, report
    assert report["environment"]["python"] == sys.version.split()[0]
    assert report["datasets"]["academic"]["status"] == "missing"
    assert report["mode"] == "rules_only"
    assert list(tmp_path.iterdir()) == []


def test_doctor_can_require_research_inputs(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "campusmail",
            "doctor",
            "--project-root",
            str(tmp_path),
            "--require-datasets",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "error"


def test_doctor_still_runs_when_site_packages_are_unavailable(tmp_path):
    source = Path(__file__).resolve().parents[1] / "backend"
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-m",
            "campusmail",
            "doctor",
            "--project-root",
            str(tmp_path),
        ],
        env={
            **os.environ,
            "PYTHONPATH": str(source),
            "CAMPUS_BOOTSTRAP_KEY": "do-not-print-secret",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "error"
    assert any(row["status"] == "missing" for row in report["dependencies"])
    assert "do-not-print-secret" not in result.stdout + result.stderr
