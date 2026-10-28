"""Activate a locally trained plain classifier without using a model bundle."""

import argparse
import json
from pathlib import Path

from campusmail.model_registry import activate_plain_model, model_health


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=("academic", "actionability"))
    args = parser.parse_args()
    task_dir = Path(__file__).resolve().parents[1] / "artifacts/models" / args.task
    activation = activate_plain_model(task_dir, task=args.task)
    print(json.dumps({"task": args.task, "activation": activation,
                      "health": model_health(task_dir, task=args.task)}, sort_keys=True))


if __name__ == "__main__":
    main()
