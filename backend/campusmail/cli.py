import argparse
from pathlib import Path
import json
import os
from .paths import PROJECT


def main():
    parser = argparse.ArgumentParser(prog="campusmail")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser(
        "doctor", help="Report setup health without accessing credentials"
    )
    doctor.add_argument("--project-root", type=Path, default=PROJECT)
    doctor.add_argument("--require-datasets", action="store_true")
    dataset = sub.add_parser(
        "dataset", help="Validate designated research inputs without changing them"
    )
    dataset_sub = dataset.add_subparsers(dest="dataset_command", required=True)
    validate = dataset_sub.add_parser("validate")
    validate.add_argument("--input", type=Path, required=True)
    validate.add_argument("--report", type=Path)
    validate.add_argument("--max-errors", type=int, default=100)
    migrate = dataset_sub.add_parser("migrate-v1")
    migrate.add_argument("--input", type=Path, required=True)
    migrate.add_argument("--output", type=Path, required=True)
    migrate.add_argument("--dataset-id", required=True)
    migrate.add_argument("--task", choices=["academic", "actionability"], required=True)
    migrate.add_argument(
        "--data-origin",
        choices=["designated_research", "public", "synthetic"],
        required=True,
    )
    migrate.add_argument("--source-type", required=True)
    migrate.add_argument(
        "--usage-status",
        choices=["unverified", "permitted", "quarantined"],
        default="unverified",
    )
    migrate.add_argument("--report", type=Path)
    migrate.add_argument("--max-errors", type=int, default=100)
    server = sub.add_parser("serve")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--data-dir", default=str(PROJECT / "runtime"))
    train = sub.add_parser("train")
    train.add_argument(
        "--task", choices=["academic", "actionability"], default="academic"
    )
    seed = sub.add_parser("import")
    seed.add_argument("--data-dir", default=str(PROJECT / "runtime"))
    seed.add_argument("--collection", choices=["scoped", "broad"], default="scoped")
    seed.add_argument("--limit", type=int, default=None)
    seed.add_argument("--profile", default="My campus")
    args = parser.parse_args()
    if args.command == "doctor":
        from .diagnostics import diagnose

        report = diagnose(args.project_root, args.require_datasets)
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["status"] == "ok" else 1)
    elif args.command == "dataset":
        import sqlite3
        from .research.validation import validate_jsonl
        from tempfile import NamedTemporaryFile

        protected = [args.input]
        if args.dataset_command == "migrate-v1":
            protected.append(args.output)
        if args.report and any(
            args.report.resolve() == path.resolve()
            or (
                args.report.exists()
                and path.exists()
                and os.path.samefile(args.report, path)
            )
            for path in protected
        ):
            parser.error("Report must not overwrite input or output data")
        try:
            if args.dataset_command == "validate":
                report = validate_jsonl(args.input, max_errors=args.max_errors)
            else:
                from .research.migration import migrate_v1_jsonl

                report = migrate_v1_jsonl(
                    args.input,
                    args.output,
                    dataset_id=args.dataset_id,
                    task=args.task,
                    data_origin=args.data_origin,
                    source_type=args.source_type,
                    usage_status=args.usage_status,
                    max_errors=args.max_errors,
                )
            output = json.dumps(report, indent=2) + "\n"
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                temporary = None
                try:
                    with NamedTemporaryFile(
                        mode="w", encoding="utf-8", dir=args.report.parent, delete=False
                    ) as stream:
                        temporary = Path(stream.name)
                        stream.write(output)
                    temporary.replace(args.report)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
            print(output, end="")
        except (OSError, ValueError, sqlite3.Error) as exc:
            # Report the failure class, not source content or arbitrary exception text.
            parser.error(
                f"Dataset validation could not finish ({type(exc).__name__}); check input/output paths and limits"
            )
        raise SystemExit(0 if report["status"] == "valid" else 1)
    elif args.command == "serve":
        if not os.environ.get("CAMPUS_BOOTSTRAP_KEY"):
            raise SystemExit(
                "Launch through Electron, or set CAMPUS_BOOTSTRAP_KEY for local API development"
            )
        import uvicorn
        from .api import create_app

        uvicorn.run(
            create_app(args.data_dir, worker=True),
            host="127.0.0.1",
            port=args.port,
            log_level="warning",
        )
    elif args.command == "train":
        from .training import load_rows, train_models

        path = PROJECT / (
            "dataset/mail/scoped_run/sanitized/documents.jsonl"
            if args.task == "academic"
            else "dataset/public/normalized/charlie9_verified.jsonl"
        )
        report = train_models(load_rows(path), PROJECT / "artifacts/models" / args.task)
        print(
            json.dumps(
                {
                    "task": args.task,
                    "records": report["records"],
                    "models": {
                        k: {"accuracy": v["accuracy"], "macro_f1": v["macro_f1"]}
                        for k, v in report["models"].items()
                    },
                    "label_warning": report["label_warning"],
                },
                indent=2,
            )
        )
    else:
        from .application import Application

        app = Application(args.data_dir)
        owner = next(
            (u for u in app.store.users() if u["name"] == args.profile), None
        ) or app.store.create_user(args.profile)
        count = app.import_collection(
            owner["id"], {"collection": args.collection, "limit": args.limit}
        )
        print(
            json.dumps(
                {
                    "profile_id": owner["id"],
                    "imported": count,
                    "counts": app.dashboard(owner["id"])["counts"],
                }
            )
        )


if __name__ == "__main__":
    main()
