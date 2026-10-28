"""Freeze a reviewed development selection against accepted DATA-05 guards."""

import argparse
import json
import os
from pathlib import Path
import tempfile

from campusmail.research.development_protocol import (
    ACCEPTED_RESERVATION, freeze_development_selection,
)
from campusmail.research.files import file_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Adjudicated v2 JSONL")
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output-name", required=True,
                        help="One filename stem in the private protocol directory")
    args = parser.parse_args()
    if (args.output_name in {"", ".", ".."}
        or Path(args.output_name).name != args.output_name
        or not all(char.isalnum() or char in "-_" for char in args.output_name)):
        parser.error("--output-name must use letters, digits, hyphen or underscore")
    if file_sha256(args.input) != args.input_sha256:
        raise ValueError("Pinned reviewed input checksum changed")
    project = Path(__file__).resolve().parents[1]
    reservation = project / "artifacts/research" / ACCEPTED_RESERVATION
    manifest = freeze_development_selection(args.input, reservation)
    private = project / "artifacts/research/experiments"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    if private.stat().st_mode & 0o077:
        raise ValueError("Private experiment directory must be owner-only")
    folder = private / "protocols"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if folder.stat().st_mode & 0o077:
        raise ValueError("Private protocol directory must be owner-only")
    output = folder / f"{args.output_name}.json"
    descriptor, staged_name = tempfile.mkstemp(prefix=".selection-", dir=folder)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.link(staged_name, output)
    finally:
        Path(staged_name).unlink(missing_ok=True)
    print(json.dumps({"selection_path": str(output),
                      "selection_sha256": file_sha256(output),
                      "documents": manifest["support"]["documents"],
                      "independent_guards": manifest["support"]["independent_guards"],
                      "missing_classes": manifest["support"]["missing_classes"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
