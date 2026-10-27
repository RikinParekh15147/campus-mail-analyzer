"""Build private DATA-04 leakage groups from a pinned DATA-03 run."""

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy

from campusmail.research.files import file_sha256
from campusmail.research.grouping import build_components
from campusmail.research.group_verification import verify_membership


def build_from_run(project_root, input_run, output_dir, manifest_path=None):
    root = Path(project_root).resolve()
    input_run = Path(input_run).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise ValueError("Component output directory must be new")
    if output_dir.is_relative_to(root / "dataset"):
        raise ValueError("Component output must be outside the immutable dataset")
    manifest_path = Path(manifest_path or root / "research_sources.json").resolve()
    manifest = json.loads(manifest_path.read_text())
    run = json.loads((input_run / "run.json").read_text())
    if run.get("status") != "valid" or run.get("manifest_sha256") != file_sha256(
        manifest_path
    ):
        raise ValueError("Input run or source manifest is not valid/pinned")
    if set(run["sources"]) != {item["name"] for item in manifest["sources"]}:
        raise ValueError("Input run does not contain every declared source")
    sources = []
    for entry in manifest["sources"]:
        declared = run["sources"][entry["name"]]
        if (
            declared["status"] != "valid"
            or declared["published_records"] != entry["records"]
        ):
            raise ValueError("Input run has incomplete source migration")
        sources.append(
            {
                "name": entry["name"],
                "dataset_id": entry["dataset_id"],
                "source_family": entry.get("source_family"),
                "path": input_run / (entry["name"] + ".v2.jsonl"),
                "expected_sha256": declared["output_sha256"],
            }
        )
    report = build_components(sources, output_dir, run_id=input_run.name)
    report["postcheck"] = verify_membership(sources, output_dir)
    if report["postcheck"]["status"] != "valid":
        report["status"] = "invalid"
    report["source_manifest_sha256"] = file_sha256(manifest_path)
    report["input_run_sha256"] = file_sha256(input_run / "run.json")
    report["python"] = sys.version
    report["numpy"] = numpy.__version__
    report["platform"] = platform.platform()
    report["implementation_sha256"] = {
        str(path.relative_to(root)): file_sha256(path)
        for path in (
            root / "backend/campusmail/research/grouping.py",
            root / "backend/campusmail/research/group_verification.py",
            root / "scripts/build_leakage_components.py",
        )
    }
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    )
    report["git_revision"] = (
        revision.stdout.strip() if revision.returncode == 0 else None
    )
    (output_dir / "component_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--input-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    result = build_from_run(
        args.project_root, args.input_run, args.output_dir, args.manifest
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "valid" else 1)
