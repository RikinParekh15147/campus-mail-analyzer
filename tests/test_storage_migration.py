"""PIPE-05 legacy profile migration, backup and recovery."""

import json
import sqlite3

import pytest

from campusmail.application import Application
from campusmail.engine import Engine
from campusmail.personalization import Personalizer
from campusmail.storage_migration import migrate_store, restore_backup
from campusmail.store import Store


def legacy_profile(tmp_path):
    path = tmp_path / "campus.sqlite"
    store = Store(path)
    owner = store.create_user("Student")["id"]
    parent = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2", "text": "See attached notice.",
        "sent_at": "2026-10-01T09:00:00+05:30",
    }, "parent")
    content = b"NLP201 Assignment 2 must submit by 25 October 2026."
    resource = Engine(store).attach(owner, content, "instructions.txt", parent["id"])
    child = store.get(owner, resource["analysis_message_id"])
    assignment = store.list(owner, "assignment")[0]
    Personalizer(store).feedback(owner, assignment["id"], "due_date", "2026-10-27")
    analysis = dict(child["analysis"])
    for key in ("analysis_schema_version", "evidence_contract_version",
                "field_assertions"):
        analysis.pop(key, None)
    payload = {key: value for key, value in child.items()
               if key not in ("id", "owner_id", "kind", "source_key", "revision",
                              "created_at", "updated_at")}
    payload["analysis"] = analysis
    start = str(analysis["dates"][0]["start"])
    payload["date_corrections"] = {
        start: {"date": "2026-10-26", "role": "assignment_deadline"}}
    payload["occurrence_decisions"] = {"legacy-choice": "create_separate"}
    resource_payload = {key: value for key, value in resource.items()
                        if key not in ("id", "owner_id", "kind", "source_key",
                                       "revision", "created_at", "updated_at")}
    resource_payload.pop("analysis_message_ids", None)
    resource_payload["content_analysis"].pop("analysis_schema_version", None)
    legacy_key = "attachment:" + resource["sha256"]
    with sqlite3.connect(path) as db:
        db.execute("UPDATE records SET source_key=?,payload=? WHERE id=?",
                   (legacy_key, json.dumps(payload), child["id"]))
        db.execute("UPDATE records SET payload=? WHERE id=?",
                   (json.dumps(resource_payload), resource["id"]))
        db.execute("PRAGMA user_version=1")
    return path, owner, parent, child, assignment, resource


def version(path):
    with sqlite3.connect(path) as db:
        return db.execute("PRAGMA user_version").fetchone()[0]


def test_migration_preserves_edits_and_restores_verified_backup(tmp_path):
    path, owner, parent, child, assignment, resource = legacy_profile(tmp_path)
    assert version(path) == 1
    assert Store(path).get(owner, assignment["id"])["due_date"] == "2026-10-27"
    assert version(path) == 1  # Opening an old profile must not reset its version.
    backup = tmp_path / "before-v2.sqlite"
    dry = migrate_store(path)
    assert dry["mode"] == "dry_run"
    assert dry["attachment_keys"] == 1
    assert dry["legacy_analyses"] >= 1
    assert dry["resource_links"] == 1
    assert not backup.exists()
    with pytest.raises(ValueError, match="backup"):
        migrate_store(path, apply=True)
    report = migrate_store(path, apply=True, backup_path=backup)
    assert report["status"] == "valid"
    assert version(path) == 2
    assert backup.is_file() and version(backup) == 1
    migrated = Store(path)
    current = migrated.get(owner, child["id"])
    assert current["source_key"] == (
        "attachment:" + resource["sha256"] + ":parent:" + parent["id"])
    assert current["analysis"]["analysis_schema_version"] == 1
    assert current["analysis"]["requires_reanalysis"] is True
    assert current["date_corrections"] == {
        str(child["analysis"]["dates"][0]["start"]):
        {"date": "2026-10-26", "role": "assignment_deadline"}}
    assert current["occurrence_decisions"] == {"legacy-choice": "create_separate"}
    assert migrated.get(owner, assignment["id"])["overrides"]["due_date"] == \
        "2026-10-27"
    assert migrated.history(owner, child["id"])
    assert migrated.get(owner, resource["id"])["analysis_message_ids"] == [child["id"]]
    assert migrate_store(path)["records_to_update"] == 0

    restored = tmp_path / "recovered.sqlite"
    assert restore_backup(backup, restored,
                          expected_sha256=report["backup_sha256"])["mode"] == "dry_run"
    assert not restored.exists()
    restore_backup(backup, restored, expected_sha256=report["backup_sha256"],
                   apply=True)
    assert version(restored) == 1
    assert Store(restored).get(owner, child["id"])["source_key"] == \
        "attachment:" + resource["sha256"]
    with pytest.raises(ValueError, match="checksum"):
        restore_backup(backup, tmp_path / "wrong.sqlite",
                       expected_sha256="0" * 64, apply=True)

    app = Application(tmp_path)
    app.reprocess(owner, {})
    assert app.store.get(owner, child["id"])["analysis"]["analysis_schema_version"] == 2
    assert app.store.get(owner, resource["id"])["content_analysis"]["analysis_schema_version"] == 2
    assert app.store.get(owner, child["id"])["date_corrections"] == \
        current["date_corrections"]
    assert app.store.get(owner, assignment["id"])["due_date"] == "2026-10-27"
    assert len(app.store.list(owner, "assignment")) == 1


def test_collision_refuses_migration_without_mutating_profile(tmp_path):
    path, owner, parent, child, _, resource = legacy_profile(tmp_path)
    store = Store(path)
    store.put(owner, "message", {"text": "Other occurrence",
                                 "parent_record_id": parent["id"]},
              "attachment:" + resource["sha256"] + ":parent:" + parent["id"])
    backup = tmp_path / "should-not-exist.sqlite"
    with pytest.raises(ValueError, match="collision"):
        migrate_store(path, apply=True, backup_path=backup)
    assert not backup.exists()
    assert version(path) == 1
    assert store.get(owner, child["id"])["source_key"] == \
        "attachment:" + resource["sha256"]


def test_unambiguous_legacy_gmail_item_rekeys_without_duplicate(tmp_path):
    path, owner, parent, child, assignment, resource = legacy_profile(tmp_path)
    parent_payload = {key: value for key, value in parent.items()
                      if key not in ("id", "owner_id", "kind", "source_key",
                                     "revision", "created_at", "updated_at")}
    parent_payload["attachments"] = [{"filename": "instructions.txt",
                                       "provider_id": "provider-item-1"}]
    with sqlite3.connect(path) as db:
        db.execute("UPDATE records SET source_key=?,payload=? WHERE id=?",
                   ("gmail:message-1", json.dumps(parent_payload), parent["id"]))
    backup = tmp_path / "before-gmail-migration.sqlite"
    report = migrate_store(path, apply=True, backup_path=backup)
    assert report["provider_items"] == 1
    store = Store(path)
    assert store.get(owner, child["id"])["source_key"].endswith(
        ":parent:" + parent["id"] + ":item:provider-item-1")
    Engine(store).attach(owner,
                         b"NLP201 Assignment 2 must submit by 25 October 2026.",
                         "instructions.txt", parent["id"], "provider-item-1")
    assert len(store.list(owner, "message")) == 2
    assert len(store.list(owner, "assignment")) == 1
    assert store.get(owner, assignment["id"])["due_date"] == "2026-10-27"


def test_ambiguous_provider_items_remain_parent_scoped(tmp_path):
    path, owner, parent, child, _, resource = legacy_profile(tmp_path)
    parent_payload = {key: value for key, value in parent.items()
                      if key not in ("id", "owner_id", "kind", "source_key",
                                     "revision", "created_at", "updated_at")}
    parent_payload["attachments"] = [
        {"filename": "instructions.txt", "provider_id": "first"},
        {"filename": "instructions.txt", "provider_id": "second"},
    ]
    with sqlite3.connect(path) as db:
        db.execute("UPDATE records SET source_key=?,payload=? WHERE id=?",
                   ("gmail:message-1", json.dumps(parent_payload), parent["id"]))
    report = migrate_store(path, apply=True,
                           backup_path=tmp_path / "before-ambiguous.sqlite")
    assert report["provider_items"] == 0
    assert report["unresolved_provider_items"] == 1
    assert Store(path).get(owner, child["id"])["source_key"] == (
        "attachment:" + resource["sha256"] + ":parent:" + parent["id"])
    store = Store(path)
    assert store.get(owner, child["id"])["legacy_provider_identity_unresolved"] is True
    with pytest.raises(ValueError, match="identity needs review"):
        Engine(store).attach(owner,
                             b"NLP201 Assignment 2 must submit by 25 October 2026.",
                             "instructions.txt", parent["id"], "first")
    assert len(store.list(owner, "message")) == 2
