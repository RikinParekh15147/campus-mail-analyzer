"""Replay pinned reviewed development notices through the local application."""

import argparse
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import tempfile

from campusmail.research.development_protocol import ACCEPTED_RESERVATION
from campusmail.research.files import file_sha256
from campusmail.research.runtime_eval import evaluate_development_runtime


def _code_hash(project):
    digest = sha256()
    for path in sorted((project / "backend/campusmail").rglob("*.py")):
        digest.update(str(path.relative_to(project)).encode() + b"\0")
        digest.update(bytes.fromhex(file_sha256(path)))
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--selection-sha256", required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    reservation = project / "artifacts/research" / ACCEPTED_RESERVATION
    report = evaluate_development_runtime(
        args.input, args.selection, reservation,
        expected_input_sha256=args.input_sha256,
        expected_selection_sha256=args.selection_sha256,
    )
    code_hash = _code_hash(project)
    identity = {"input_sha256": args.input_sha256,
                "selection_sha256": args.selection_sha256,
                "code_sha256": code_hash,
                "dependency_spec_sha256": file_sha256(project / "pyproject.toml"),
                "python": ".".join(map(str, sys.version_info[:3])),
                "dependencies": {name: version(name) for name in ("pydantic", "fastapi")}}
    run_id = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    report["run_identity"] = identity
    report["code_sha256"] = code_hash
    report["run_id"] = run_id
    private = project / "artifacts/research/experiments"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    if private.stat().st_mode & 0o077:
        raise ValueError("Private experiment directory must be owner-only")
    folder = private / "runtime_eval"
    folder.mkdir(exist_ok=True, mode=0o700)
    if folder.stat().st_mode & 0o077:
        raise ValueError("Runtime evaluation directory must be owner-only")
    output = folder / f"{run_id}.json"
    descriptor, staged_name = tempfile.mkstemp(prefix=".runtime-", dir=folder)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.link(staged_name, output)
    finally:
        Path(staged_name).unlink(missing_ok=True)
    print(json.dumps({"run_id": run_id, "report": str(output),
                      "prepared_scenarios": report["prepared_scenarios"]}, sort_keys=True))


if __name__ == "__main__":
    main()
