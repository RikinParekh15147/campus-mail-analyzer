"""Verify real collection relocation in a temporary store, without running ML."""

import argparse
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import time

from campusmail.dataset_import import import_dataset
from campusmail.store import Store


def verify(project_root):
    root = Path(project_root).resolve()
    manifest = json.loads((root / "dataset_collections.json").read_text())
    results = {
        "status": "valid",
        "scope": "Storage/import acceptance; no ML inference or training",
        "collections": {},
    }
    with TemporaryDirectory(prefix="campus-real-import-") as temporary:
        folder = Path(temporary)
        store = Store(folder / "import.sqlite")
        owner = store.create_user("Isolated import acceptance")["id"]
        for name, entry in manifest.items():
            source = (root / entry["relative_path"]).resolve()
            if not source.is_relative_to(root / "dataset"):
                raise ValueError("Collection path escapes dataset directory")
            moved = folder / (str(len(results["collections"])) + ".jsonl")
            shutil.copyfile(source, moved)
            first, again = {}, {}
            started = time.perf_counter()
            import_dataset(
                store,
                owner,
                source,
                dataset_id=entry["dataset_id"],
                expected_sha256=entry["input_sha256"],
                report=first,
            )
            import_dataset(
                store,
                owner,
                moved,
                dataset_id=entry["dataset_id"],
                expected_sha256=entry["input_sha256"],
                report=again,
            )
            with store.connect() as db:
                revisions = db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0]
            if again["created"] or first["created"] != again["existing"] or revisions:
                raise RuntimeError("Relocation acceptance failed")
            results["collections"][name] = {
                "first": first,
                "relocated_reimport": again,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "store_revision_rows": revisions,
            }
        with store.connect() as db:
            results["total_message_records"] = db.execute(
                "SELECT COUNT(*) FROM records WHERE kind='message'"
            ).fetchone()[0]
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    print(json.dumps(verify(args.project_root), indent=2))
