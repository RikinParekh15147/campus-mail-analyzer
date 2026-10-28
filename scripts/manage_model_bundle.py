"""Seal, inspect, promote or roll back local versioned model bundles."""

import argparse
import json
from pathlib import Path
import re

from campusmail.model_registry import (
    model_health, promote_bundle, rollback_bundle, seal_bundle,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seal", "status", "promote", "rollback"))
    parser.add_argument("--task", required=True, choices=("academic", "actionability"))
    parser.add_argument("--bundle-id")
    parser.add_argument("--model-revision")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--expected-revision", type=int)
    args = parser.parse_args()
    if args.bundle_id and (not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}",
                                              args.bundle_id)
                           or args.bundle_id in (".", "..")):
        parser.error("--bundle-id must be a simple directory name")
    project = Path(__file__).resolve().parents[1]
    task_dir = project / "artifacts/models" / args.task
    if args.command == "seal":
        if not args.bundle_id or not args.model_revision:
            parser.error("seal needs --bundle-id and --model-revision")
        digest = seal_bundle(task_dir / "bundles" / args.bundle_id,
                             task=args.task, model_revision=args.model_revision,
                             thresholds={})
        output = {"bundle_id": args.bundle_id, "manifest_sha256": digest}
    elif args.command == "status":
        output = model_health(task_dir, task=args.task)
        pointer = task_dir / "active.json"
        if pointer.is_file() and not pointer.is_symlink():
            try:
                value = json.loads(pointer.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    output["revision"] = value.get("revision")
                    output["active"] = value.get("active")
                    output["previous"] = value.get("previous")
            except (OSError, ValueError, UnicodeDecodeError):
                pass
    elif args.command == "promote":
        if not args.bundle_id or not args.manifest_sha256 or args.expected_revision is None:
            parser.error("promote needs --bundle-id, --manifest-sha256 and --expected-revision")
        output = promote_bundle(task_dir, task=args.task, bundle_id=args.bundle_id,
                                manifest_sha256=args.manifest_sha256,
                                expected_revision=args.expected_revision)
    else:
        if args.expected_revision is None:
            parser.error("rollback needs --expected-revision")
        output = rollback_bundle(task_dir, task=args.task,
                                 expected_revision=args.expected_revision)
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
