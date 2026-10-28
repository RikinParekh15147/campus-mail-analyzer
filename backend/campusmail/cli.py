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
    profile = sub.add_parser("store", help="Inspect or migrate local profile storage")
    profile_sub = profile.add_subparsers(dest="store_command", required=True)
    migrate_store = profile_sub.add_parser("migrate")
    migrate_store.add_argument("--database", type=Path, required=True)
    migrate_store.add_argument("--apply", action="store_true")
    migrate_store.add_argument("--backup", type=Path)
    restore_store = profile_sub.add_parser("restore")
    restore_store.add_argument("--backup", type=Path, required=True)
    restore_store.add_argument("--output", type=Path, required=True)
    restore_store.add_argument("--expected-sha256", required=True)
    restore_store.add_argument("--apply", action="store_true")
    dataset = sub.add_parser(
        "dataset", help="Validate designated research inputs without changing them"
    )
    dataset_sub = dataset.add_subparsers(dest="dataset_command", required=True)
    audit = dataset_sub.add_parser("audit")
    audit.add_argument("--project-root", type=Path, default=PROJECT)
    audit.add_argument("--report", type=Path)
    audit.add_argument("--skip-asset-hashes", action="store_true")
    identities = dataset_sub.add_parser("import-identities")
    identities.add_argument("--database", type=Path, required=True)
    identities.add_argument("--owner", required=True)
    rekey = dataset_sub.add_parser("migrate-import-ids")
    rekey.add_argument("--database", type=Path, required=True)
    rekey.add_argument("--owner", required=True)
    rekey.add_argument("--dataset-id", required=True)
    rekey.add_argument("--legacy-namespace", required=True)
    rekey.add_argument("--apply", action="store_true")
    rekey.add_argument("--backup", type=Path)
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
    migrate.add_argument(
        "--policy", choices=["strict", "preserve_context"], default="strict"
    )
    migrate.add_argument(
        "--input-format",
        choices=["document_v1", "sentence_actionability"],
        default="document_v1",
    )
    migrate.add_argument("--relationships", type=Path)
    server = sub.add_parser("serve")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--data-dir", default=str(PROJECT / "runtime"))
    train = sub.add_parser("train")
    train.add_argument(
        "--task", choices=["academic", "actionability"], default="academic"
    )
    train.add_argument(
        "--reservation",
        type=Path,
        default=PROJECT / "artifacts/research/data05-20261028-reserved-v2",
    )
    train.add_argument(
        "--input-run",
        type=Path,
        default=PROJECT / "artifacts/research/data03-20261027-verified",
    )
    train.add_argument(
        "--component-run",
        type=Path,
        default=PROJECT / "artifacts/research/data04-20261027-short",
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
    elif args.command == "store":
        import sqlite3
        from .storage_migration import migrate_store, restore_backup

        try:
            if args.store_command == "migrate":
                report = migrate_store(args.database, apply=args.apply,
                                       backup_path=args.backup)
            else:
                report = restore_backup(args.backup, args.output,
                                        expected_sha256=args.expected_sha256,
                                        apply=args.apply)
        except (OSError, ValueError, sqlite3.Error) as exc:
            parser.error(f"Store operation failed ({type(exc).__name__}); "
                         "check the database, backup path and checksum")
        print(json.dumps(report, indent=2))
        raise SystemExit(0)
    elif args.command == "dataset" and args.dataset_command in (
        "migrate-import-ids",
        "import-identities",
        "audit",
    ):
        import sqlite3

        try:
            if args.dataset_command == "audit":
                from .research.audit import audit_corpus

                if args.report and args.report.resolve().is_relative_to(
                    (args.project_root / "dataset").resolve()
                ):
                    parser.error(
                        "Audit reports must be outside the immutable dataset directory"
                    )
                report = audit_corpus(
                    args.project_root, verify_assets=not args.skip_asset_hashes
                )
                if args.report:
                    from tempfile import NamedTemporaryFile

                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    with NamedTemporaryFile(
                        mode="w", encoding="utf-8", dir=args.report.parent, delete=False
                    ) as stream:
                        temporary = Path(stream.name)
                        json.dump(report, stream, indent=2)
                    try:
                        temporary.replace(args.report)
                    finally:
                        temporary.unlink(missing_ok=True)
            elif args.dataset_command == "import-identities":
                from .dataset_import import inspect_import_ids

                report = inspect_import_ids(args.database, owner=args.owner)
            else:
                from .dataset_import import migrate_import_ids

                report = migrate_import_ids(
                    args.database,
                    owner=args.owner,
                    dataset_id=args.dataset_id,
                    legacy_namespace=args.legacy_namespace,
                    apply=args.apply,
                    backup_path=args.backup,
                )
        except (OSError, ValueError, sqlite3.Error) as exc:
            parser.error(
                f"Dataset operation failed ({type(exc).__name__}); verify paths, owner and identity declarations"
            )
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["status"] == "valid" else 1)
    elif args.command == "dataset":
        import sqlite3
        from .research.validation import validate_jsonl
        from tempfile import NamedTemporaryFile

        protected = [args.input]
        if args.dataset_command == "migrate-v1":
            protected.append(args.output)
            if args.relationships:
                protected.append(args.relationships)
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
                    policy=args.policy,
                    input_format=args.input_format,
                    relationships_path=args.relationships,
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
        from .training import load_reserved_development_rows, train_models

        source = "scoped" if args.task == "academic" else "charlie9"
        rows = load_reserved_development_rows(
            PROJECT, args.task, source, args.reservation,
            args.input_run, args.component_run,
        )
        report = train_models(rows, PROJECT / "artifacts/models" / args.task)
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
        import_report = {}
        count = app.import_collection(
            owner["id"],
            {"collection": args.collection, "limit": args.limit},
            report=import_report,
        )
        print(
            json.dumps(
                {
                    "profile_id": owner["id"],
                    "imported": count,
                    "import_report": import_report,
                    "counts": app.dashboard(owner["id"])["counts"],
                }
            )
        )


if __name__ == "__main__":
    main()
