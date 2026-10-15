import argparse
from pathlib import Path
import json
import os
from .application import Application, PROJECT


def main():
    parser = argparse.ArgumentParser(prog="campusmail")
    sub = parser.add_subparsers(dest="command", required=True)
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
    if args.command == "serve":
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
