"""Run a pinned, private rules-only development experiment."""

import argparse
import json
from pathlib import Path

from campusmail.research.experiment import run_rules_experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Reviewed v2 JSONL")
    parser.add_argument("--selection", type=Path, required=True,
                        help="Development selection JSON")
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--output-name", required=True,
                        help="Single directory name within artifacts/research/experiments")
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if args.output_name in {"", ".", ".."} or Path(args.output_name).name != args.output_name:
        parser.error("--output-name must be one directory name")
    private = Path(__file__).resolve().parents[1] / "artifacts/research/experiments"
    result = run_rules_experiment(
        args.input, args.selection, private / args.output_name, private,
        expected_input_sha256=args.input_sha256,
        expected_manifest_sha256=args.selection_sha256, seed=args.seed,
    )
    print(json.dumps({"run_id": result["run_id"], "output_dir": result["output_dir"],
                      "documents": result["documents"]}, sort_keys=True))


if __name__ == "__main__":
    main()
