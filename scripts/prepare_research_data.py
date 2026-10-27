"""Reproduce DATA-01/03 checks and migrations from the pinned research manifest.

Usage: .venv/bin/python scripts/prepare_research_data.py --output-dir artifacts/research/RUN_ID
The output directory must be new; sources and prior runs are never overwritten.
"""

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

from campusmail.research.audit import audit_corpus
from campusmail.research.files import file_sha256
from campusmail.research.migration import migrate_v1_jsonl


def prepare(root, manifest_path, output_dir, *, verify_assets=True):
    root, output_dir = Path(root).resolve(), Path(output_dir).resolve()
    if output_dir.is_relative_to(root / "dataset"):
        raise ValueError("Run output must be outside the immutable dataset directory")
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("manifest_version") != "1.0":
        raise ValueError("Unsupported source manifest")
    names, ids = set(), set()
    for entry in manifest["sources"]:
        if entry["name"] in names or entry["dataset_id"] in ids:
            raise ValueError("Duplicate source identity in manifest")
        names.add(entry["name"])
        ids.add(entry["dataset_id"])
        if Path(entry["name"]).name != entry["name"] or entry["name"] in (".", ".."):
            raise ValueError("Invalid output source name")
        for path_key, hash_key in (
            ("relative_path", "input_sha256"),
            ("relationships_path", "relationships_sha256"),
        ):
            if path_key not in entry:
                continue
            path = (root / entry[path_key]).resolve()
            if not path.is_relative_to(root / "dataset"):
                raise ValueError("Source path must stay inside the dataset directory")
            if file_sha256(path) != entry[hash_key]:
                raise ValueError(
                    "Input hash mismatch; inventory and version the changed source first"
                )
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "status": "valid",
        "run_id": output_dir.name,
        "manifest_sha256": file_sha256(manifest_path),
        "python": sys.version,
        "platform": platform.platform(),
        "sources": {},
        "code_sha256": {
            str(p.relative_to(root)): file_sha256(p)
            for p in sorted((root / "backend/campusmail/research").glob("*.py"))
        },
    }
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True
    )
    summary["git_revision"] = (
        revision.stdout.strip() if revision.returncode == 0 else None
    )
    audit = audit_corpus(root, verify_assets=verify_assets)
    (output_dir / "corpus-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    for entry in manifest["sources"]:
        report = migrate_v1_jsonl(
            root / entry["relative_path"],
            output_dir / (entry["name"] + ".v2.jsonl"),
            **{
                key: entry[key]
                for key in (
                    "dataset_id",
                    "task",
                    "data_origin",
                    "source_type",
                    "usage_status",
                    "input_format",
                    "policy",
                )
            },
            relationships_path=root / entry["relationships_path"]
            if entry.get("relationships_path")
            else None,
        )
        (output_dir / (entry["name"] + ".migration.json")).write_text(
            json.dumps(report, indent=2) + "\n"
        )
        counts_match = (
            report["source_lines"] == entry["records"] == report["published_records"]
        )
        summary["sources"][entry["name"]] = {
            key: report.get(key)
            for key in (
                "status",
                "source_lines",
                "published_records",
                "changes",
                "input_sha256",
                "output_sha256",
                "relationship_records",
                "source_unchanged",
            )
        }
        summary["sources"][entry["name"]]["manifest_counts_match"] = counts_match
        if report["status"] != "valid" or not counts_match:
            summary["status"] = "invalid"
    if audit["status"] != "valid":
        summary["status"] = "invalid"
    (output_dir / "run.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skip-asset-hashes", action="store_true")
    args = parser.parse_args()
    result = prepare(
        args.project_root,
        args.manifest or args.project_root / "research_sources.json",
        args.output_dir,
        verify_assets=not args.skip_asset_hashes,
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "valid" else 1)
