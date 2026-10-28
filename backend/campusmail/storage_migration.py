"""Explicit v1-to-v2 profile migration and non-destructive SQLite recovery."""

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import sqlite3
import tempfile

from .candidates import ANALYSIS_SCHEMA_VERSION


LEGACY_ATTACHMENT = re.compile(r"attachment:([0-9a-f]{64})\Z")
PARENT_ATTACHMENT = re.compile(r"attachment:([0-9a-f]{64}):parent:([^:]+)\Z")


def file_hash(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_database(db):
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("SQLite integrity check failed")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in (1, ANALYSIS_SCHEMA_VERSION):
        raise ValueError("Unsupported profile schema version")
    return version


def _mark_legacy(analysis):
    if not isinstance(analysis, dict):
        raise ValueError("Analysis payload must be an object")
    version = analysis.get("analysis_schema_version")
    if version not in (None, 1, ANALYSIS_SCHEMA_VERSION):
        raise ValueError("Unsupported analysis payload version")
    if version == ANALYSIS_SCHEMA_VERSION:
        return analysis
    return {**analysis, "analysis_schema_version": 1,
            "requires_reanalysis": True}


def _backup_locked(source_path, destination):
    raw_destination = Path(destination)
    if raw_destination.is_symlink():
        raise ValueError("Backup path must not be a symbolic link")
    destination = raw_destination.resolve()
    if destination.exists() or destination == source_path:
        raise ValueError("Backup must be a new file separate from the database")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".profile-backup-", dir=destination.parent)
    os.close(fd)
    try:
        source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)
        target = sqlite3.connect(temporary)
        try:
            source.backup(target)
            _check_database(target)
        finally:
            target.close()
            source.close()
        os.link(temporary, destination)
        return file_hash(destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def migrate_store(database, *, apply=False, backup_path=None):
    """Dry-run by default; applied changes require a new verified backup.

    Legacy analyses are marked for explicit replay, never silently reanalyzed.
    Source-key changes preserve record IDs, revisions and confirmed overrides.
    """
    path = Path(database).resolve()
    if not path.is_file():
        raise ValueError("Profile database does not exist")
    if apply and backup_path is None:
        raise ValueError("An explicit new backup path is required")
    db = sqlite3.connect(path.as_uri() + ("?mode=rw" if apply else "?mode=ro"),
                         uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        version = _check_database(db)
        rows = list(db.execute("SELECT * FROM records ORDER BY owner_id,kind,id"))
        identities = {(row["owner_id"], row["kind"], row["source_key"])
                      for row in rows}
        message_ids = {(row["owner_id"], row["id"]) for row in rows
                       if row["kind"] == "message"}
        messages = {}
        resources = {}
        children = {}
        for row in rows:
            if row["kind"] in ("message", "resource"):
                payload = json.loads(row["payload"])
                if not isinstance(payload, dict):
                    raise ValueError("Record payload must be an object")
                if row["kind"] == "resource":
                    resources[(row["owner_id"], row["id"])] = payload
                else:
                    messages[(row["owner_id"], row["id"])] = {
                        **payload, "_record_source_key": row["source_key"]}
                    if (payload.get("source_type") == "uploaded_attachment"
                        or row["source_key"].startswith("attachment:")):
                        for resource_id in payload.get("attachment_resource_ids", []):
                            children.setdefault((row["owner_id"], resource_id), set()).add(row["id"])
        changes = []
        counts = {"legacy_analyses": 0, "attachment_keys": 0,
                  "provider_items": 0, "unresolved_provider_items": 0,
                  "resource_links": 0}
        for row in rows:
            original = json.loads(row["payload"])
            payload = dict(original)
            if not isinstance(payload, dict):
                raise ValueError("Record payload must be an object")
            key = row["source_key"]
            if row["kind"] == "message":
                if "analysis" in payload:
                    marked = _mark_legacy(payload["analysis"])
                    if marked != payload["analysis"]:
                        payload["analysis"] = marked
                        counts["legacy_analyses"] += 1
                match = LEGACY_ATTACHMENT.fullmatch(key)
                parent_match = PARENT_ATTACHMENT.fullmatch(key)
                if match or parent_match:
                    parent_id = payload.get("parent_record_id")
                    if parent_match and parent_match[2] != parent_id:
                        raise ValueError("Attachment key and parent disagree")
                    if parent_id and (row["owner_id"], parent_id) not in message_ids:
                        raise ValueError("Legacy attachment parent is missing")
                    digest = match[1] if match else parent_match[1]
                    base = (f"attachment:{digest}:parent:{parent_id}"
                            if parent_id else f"attachment:{digest}:standalone")
                    key = base
                    if parent_id:
                        parent = messages[(row["owner_id"], parent_id)]
                        if str(parent.get("_record_source_key", "")).startswith("gmail:"):
                            filename = payload.get("source_filename")
                            if not filename:
                                resource_ids = payload.get("attachment_resource_ids", [])
                                if len(resource_ids) == 1:
                                    filename = resources.get(
                                        (row["owner_id"], resource_ids[0]), {}).get("filename")
                            attachments = parent.get("attachments", [])
                            eligible = [item.get("provider_id") for item in attachments
                                        if item.get("provider_id")
                                        and (item.get("filename") == filename
                                             if filename else len(attachments) == 1)]
                            if len(eligible) == 1:
                                key = base + ":item:" + str(eligible[0])
                                counts["provider_items"] += 1
                            else:
                                counts["unresolved_provider_items"] += 1
                                payload["legacy_provider_identity_unresolved"] = True
                    if key != row["source_key"]:
                        identity = (row["owner_id"], row["kind"], key)
                        if identity in identities:
                            raise ValueError("Attachment occurrence key collision")
                        identities.add(identity)
                        counts["attachment_keys"] += 1
            elif row["kind"] == "resource":
                if "content_analysis" in payload:
                    marked = _mark_legacy(payload["content_analysis"])
                    if marked != payload["content_analysis"]:
                        payload["content_analysis"] = marked
                        counts["legacy_analyses"] += 1
                linked = set(payload.get("analysis_message_ids", []))
                if payload.get("analysis_message_id"):
                    linked.add(payload["analysis_message_id"])
                linked.update(children.get((row["owner_id"], row["id"]), set()))
                if linked and sorted(linked) != payload.get("analysis_message_ids", []):
                    payload["analysis_message_ids"] = sorted(linked)
                    counts["resource_links"] += 1
            if key != row["source_key"] or payload != original:
                body = json.dumps(payload, ensure_ascii=False)
                changes.append((row, key, body))
        report = {"status": "valid", "mode": "apply" if apply else "dry_run",
                  "from_version": version, "to_version": ANALYSIS_SCHEMA_VERSION,
                  "records_to_update": len(changes), **counts,
                  "reanalysis_policy": "explicit_reprocess_after_migration"}
        if apply and (changes or version != ANALYSIS_SCHEMA_VERSION):
            report["backup_sha256"] = _backup_locked(path, backup_path)
            stamp = datetime.now(timezone.utc).isoformat()
            for row, key, body in changes:
                db.execute("INSERT INTO revisions VALUES(?,?,?,?,?)",
                           (row["id"], row["owner_id"], row["revision"],
                            row["payload"], stamp))
                db.execute("UPDATE records SET source_key=?,payload=?,revision=revision+1,"
                           "updated_at=? WHERE id=?", (key, body, stamp, row["id"]))
            db.execute(f"PRAGMA user_version={ANALYSIS_SCHEMA_VERSION}")
        db.commit()
        return report
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def restore_backup(backup, output, *, expected_sha256, apply=False):
    """Verify a backup and restore it only to a new, unused database path."""
    raw_output = Path(output)
    if raw_output.is_symlink():
        raise ValueError("Recovery output must not be a symbolic link")
    backup, output = Path(backup).resolve(), raw_output.resolve()
    if not backup.is_file() or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Backup or expected checksum is invalid")
    if backup == output or output.exists():
        raise ValueError("Recovery output must be a new file")
    actual = file_hash(backup)
    if actual != expected_sha256:
        raise ValueError("Backup checksum mismatch")
    source = sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)
    try:
        version = _check_database(source)
        report = {"status": "valid", "mode": "apply" if apply else "dry_run",
                  "schema_version": version, "backup_sha256": actual}
        if apply:
            output.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".profile-restore-", dir=output.parent)
            os.close(fd)
            try:
                target = sqlite3.connect(temporary)
                try:
                    source.backup(target)
                    _check_database(target)
                finally:
                    target.close()
                if file_hash(backup) != actual:
                    raise ValueError("Backup changed during recovery")
                os.link(temporary, output)
            finally:
                Path(temporary).unlink(missing_ok=True)
        return report
    finally:
        source.close()
