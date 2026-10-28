"""Staged operational imports and explicit migration of legacy source keys."""

from collections import Counter
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from .models import CATEGORIES
from .store import now
from .research.files import file_sha256, jsonl_records


def _dataset_source_key(dataset_id, document_id):
    if not isinstance(dataset_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", dataset_id
    ):
        raise ValueError("A stable dataset_id is required for import")
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("Every imported record needs a document_id")
    return (
        "dataset:v2:"
        + hashlib.sha256(
            json.dumps([dataset_id, document_id], ensure_ascii=False).encode()
        ).hexdigest()
    )


def _payload(row, dataset_id):
    if not isinstance(row.get("subject", ""), str):
        raise ValueError("Invalid source subject")
    for field in (
        "sent_at",
        "timezone",
        "thread_id",
        "source_type",
        "parent_message_id",
        "message_id",
    ):
        if row.get(field) is not None and not isinstance(row[field], str):
            raise ValueError("Invalid source metadata field")
    category = row.get("primary_category")
    metadata = row.get("source_metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("Invalid source metadata")
    payload = {
        "text": row["text"],
        "subject": row.get("subject", ""),
        "sent_at": row.get("sent_at"),
        "timezone": row.get("timezone"),
        "thread_id": row.get("thread_id"),
        "source_category": category if category in CATEGORIES else None,
        "label_provenance": row.get("label_provenance", "unknown"),
        "source_type": row.get("source_type"),
        "sanitized": True,
        "dataset_id": dataset_id,
        "source_metadata": metadata,
        "imported_resources": row.get("resources", []),
        "parent_message_id": row.get("parent_message_id"),
        "original_document_id": row["document_id"],
        "original_message_id": row.get("message_id"),
        "is_self": metadata.get("sender_is_account", False),
        "imported_source_sha256": hashlib.sha256(
            json.dumps(row, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
    }
    for key in (
        "parent_document_id",
        "duplicate_group_id",
        "template_group_id",
        "leakage_group_id",
        "update_family_id",
    ):
        if key in row:
            payload[key] = row[key]
    if metadata.get("parent_document_id"):
        if payload.get("parent_document_id") not in (
            None,
            metadata["parent_document_id"],
        ):
            raise ValueError("Conflicting parent identities")
        payload["parent_document_id"] = metadata["parent_document_id"]
    return payload


def import_dataset(
    store,
    owner,
    path,
    on_message=None,
    limit=None,
    *,
    dataset_id,
    report=None,
    expected_sha256=None,
):
    """Validate/stage the entire input before atomically inserting selected messages.

    Existing content is never replaced. Reimports skip completed processing;
    interrupted callbacks retain a pending marker and can resume.
    """
    _dataset_source_key(dataset_id, "preflight")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("Import limit must be a positive integer")
    path = Path(path)
    digest = file_sha256(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(
            "Dataset checksum does not match the declared collection snapshot"
        )
    stats = Counter(
        physical_lines=0,
        excluded_unusable_text=0,
        usable_records=0,
        selected_records=0,
        created=0,
        existing=0,
        processed=0,
    )
    with TemporaryDirectory(prefix="campus-import-") as temporary:
        stage = sqlite3.connect(Path(temporary) / "stage.sqlite")
        try:
            stage.execute(
                "CREATE TABLE staged(id TEXT PRIMARY KEY, line INTEGER, source_key TEXT, payload TEXT, record_id TEXT, process INTEGER DEFAULT 0)"
            )
            for line, row, _, problem in jsonl_records(path):
                stats["physical_lines"] += 1
                if problem:
                    raise ValueError(f"Import row {line}: {problem}")
                if row.get("schema_version") not in (None, "1.0"):
                    raise ValueError(
                        "Only legacy operational exports can be imported; use dataset validation for research exports"
                    )
                if row.get("dataset_id", dataset_id) != dataset_id:
                    raise ValueError(f"Import row {line} has a different dataset_id")
                key = _dataset_source_key(dataset_id, row.get("document_id"))
                if not isinstance(row.get("text"), str):
                    raise ValueError(f"Import row {line} has invalid text")
                payload = _payload(row, dataset_id)
                usable = bool(row["text"].strip())
                stats["usable_records"] += usable
                stats["excluded_unusable_text"] += not usable
                selected = usable and (
                    limit is None or stats["selected_records"] < limit
                )
                stats["selected_records"] += selected
                try:
                    stage.execute(
                        "INSERT INTO staged(id,line,source_key,payload) VALUES(?,?,?,?)",
                        (
                            row["document_id"],
                            line,
                            key,
                            json.dumps(payload, ensure_ascii=False)
                            if selected
                            else None,
                        ),
                    )
                except sqlite3.IntegrityError:
                    raise ValueError(
                        f"Import row {line} has a duplicate document_id"
                    ) from None
            if not stats["physical_lines"]:
                raise ValueError("Import dataset is empty")
            if file_sha256(path) != digest:
                raise ValueError("Import source changed during validation")
            # The store lock covers preflight and insertion; there are no partial writes
            # on input/collision errors and no concurrent put can overwrite an import.
            with store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                for old in db.execute(
                    "SELECT source_key,payload FROM records WHERE owner_id=? AND kind='message' AND source_key LIKE 'dataset:%' AND source_key NOT LIKE 'dataset:v2:%'",
                    (owner,),
                ):
                    legacy = json.loads(old["payload"])
                    if stage.execute(
                        "SELECT 1 FROM staged WHERE id=? AND payload IS NOT NULL",
                        (legacy.get("original_document_id"),),
                    ).fetchone():
                        raise ValueError(
                            "Legacy import identity detected; run migrate-import-ids before reimport"
                        )
                for doc_id, line, key, encoded in stage.execute(
                    "SELECT id,line,source_key,payload FROM staged WHERE payload IS NOT NULL ORDER BY line"
                ):
                    incoming = json.loads(encoded)
                    old = db.execute(
                        "SELECT * FROM records WHERE owner_id=? AND kind='message' AND source_key=?",
                        (owner, key),
                    ).fetchone()
                    if old:
                        existing = json.loads(old["payload"])
                        old_hash = existing.get("imported_source_sha256")
                        if old_hash:
                            matches = old_hash == incoming["imported_source_sha256"]
                        else:
                            # Legacy records may have confirmed analysis, but source
                            # identity/content must agree before adopting provenance.
                            matches = all(
                                existing.get(k) == incoming.get(k)
                                for k in (
                                    "text",
                                    "subject",
                                    "sent_at",
                                    "original_document_id",
                                    "source_type",
                                    "thread_id",
                                )
                            )
                        if not matches:
                            raise ValueError(
                                f"Import row {line} changes an existing source; use a new dataset version"
                            )
                        stats["existing"] += 1
                        record_id = old["id"]
                        enriched = dict(existing)
                        metadata_changed = False
                        if not old_hash:
                            for k in (
                                "dataset_id",
                                "imported_source_sha256",
                                "parent_document_id",
                                "duplicate_group_id",
                                "template_group_id",
                                "leakage_group_id",
                                "update_family_id",
                            ):
                                if k in incoming:
                                    enriched.setdefault(k, incoming[k])
                            metadata_changed = enriched != existing
                        # Older imports recorded the source hash but omitted
                        # the timezone needed to resolve relative dates.
                        if incoming.get("timezone") and not enriched.get("timezone"):
                            enriched["timezone"] = incoming["timezone"]
                            enriched["import_processing_status"] = "pending"
                            metadata_changed = True
                        if metadata_changed:
                            stamp = now()
                            db.execute(
                                "INSERT INTO revisions VALUES(?,?,?,?,?)",
                                (
                                    record_id,
                                    owner,
                                    old["revision"],
                                    old["payload"],
                                    stamp,
                                ),
                            )
                            db.execute(
                                "UPDATE records SET payload=?,revision=revision+1,updated_at=? WHERE id=?",
                                (
                                    json.dumps(enriched, ensure_ascii=False),
                                    stamp,
                                    record_id,
                                ),
                            )
                        pending = enriched.get("import_processing_status") == "pending"
                    else:
                        record_id, stamp = uuid4().hex, now()
                        incoming["import_processing_status"] = (
                            "pending" if on_message else "complete"
                        )
                        db.execute(
                            "INSERT INTO records VALUES(?,?,?,?,?,1,?,?)",
                            (
                                record_id,
                                owner,
                                "message",
                                key,
                                json.dumps(incoming, ensure_ascii=False),
                                stamp,
                                stamp,
                            ),
                        )
                        stats["created"] += 1
                        pending = bool(on_message)
                    stage.execute(
                        "UPDATE staged SET record_id=?,process=? WHERE id=?",
                        (record_id, pending, doc_id),
                    )
            if on_message:
                for (record_id,) in stage.execute(
                    "SELECT record_id FROM staged WHERE process=1 ORDER BY line"
                ):
                    on_message(owner, store.get(owner, record_id))
                    store.patch(
                        owner, record_id, {"import_processing_status": "complete"}
                    )
                    stats["processed"] += 1
        finally:
            stage.close()
    if report is not None:
        report.update(
            status="valid", dataset_id=dataset_id, input_sha256=digest, **dict(stats)
        )
    return stats["selected_records"]


def migrate_import_ids(
    database, *, owner, dataset_id, legacy_namespace, apply=False, backup_path=None
):
    """Explicit owner/namespace migration; preserves payloads, IDs and revisions.

    Dry-run is the default. Applied changes require a new SQLite backup. Conflicts
    abort without merging records or changing any user/analysis data.
    """
    _dataset_source_key(dataset_id, "preflight")
    if not re.fullmatch(r"[a-f0-9]{12}", legacy_namespace):
        raise ValueError("Legacy namespace must be the 12-character path hash")
    path = Path(database).resolve()
    if not path.is_file():
        raise ValueError("Profile database does not exist")
    if apply and not backup_path:
        raise ValueError("An explicit new backup path is required")
    prefix = "dataset:" + legacy_namespace + ":"
    uri = path.as_uri() + ("?mode=rw" if apply else "?mode=ro")
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    result = {
        "status": "valid",
        "mode": "apply" if apply else "dry_run",
        "records": 0,
        "dataset_id": dataset_id,
        "legacy_namespace": legacy_namespace,
    }
    try:
        db.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        if not db.execute("SELECT 1 FROM users WHERE id=?", (owner,)).fetchone():
            raise ValueError("Unknown profile owner")
        changes = []
        for row in db.execute(
            "SELECT * FROM records WHERE owner_id=? AND kind='message' AND substr(source_key,1,?)=?",
            (owner, len(prefix), prefix),
        ):
            payload = json.loads(row["payload"])
            doc_id = payload.get("original_document_id")
            if not doc_id or row["source_key"] != prefix + doc_id:
                raise ValueError(
                    "Legacy source key and original document identity disagree"
                )
            if payload.get("dataset_id") not in (None, dataset_id):
                raise ValueError("Legacy record declares a different dataset_id")
            new_key = _dataset_source_key(dataset_id, doc_id)
            if db.execute(
                "SELECT 1 FROM records WHERE owner_id=? AND kind='message' AND source_key=?",
                (owner, new_key),
            ).fetchone():
                raise ValueError(
                    "Stable import identity already exists; resolve the collision explicitly"
                )
            changes.append((new_key, row["id"]))
        result["records"] = len(changes)
        if apply and changes:
            backup = Path(backup_path).resolve()
            if backup == path or backup.exists():
                raise ValueError(
                    "Backup must be a new file, separate from the database"
                )
            backup.parent.mkdir(parents=True, exist_ok=True)
            # Lock held before opening the read snapshot, so the backup and migration
            # refer to the same committed state. sqlite backup handles WAL safely.
            with backup.open("xb"):
                pass
            source = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            target = sqlite3.connect(backup)
            try:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed")
            finally:
                target.close()
                source.close()
            db.executemany("UPDATE records SET source_key=? WHERE id=?", changes)
            result["backup_sha256"] = file_sha256(backup)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def inspect_import_ids(database, *, owner):
    path = Path(database).resolve()
    if not path.is_file():
        raise ValueError("Profile database does not exist")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        if not db.execute("SELECT 1 FROM users WHERE id=?", (owner,)).fetchone():
            raise ValueError("Unknown profile owner")
        counts = Counter()
        for (key,) in db.execute(
            "SELECT source_key FROM records WHERE owner_id=? AND kind='message' AND source_key LIKE 'dataset:%'",
            (owner,),
        ):
            parts = key.split(":", 2)
            counts[parts[1]] += 1
        return {"status": "valid", "namespaces": dict(counts)}
    finally:
        db.close()
