import json
from pathlib import Path
import sqlite3

import pytest
from pydantic import ValidationError

from campusmail.dataset_import import (
    import_dataset,
    migrate_import_ids,
    inspect_import_ids,
    _dataset_source_key,
)
from campusmail.store import Store
from campusmail.research.contracts import ResearchDocument
from campusmail.research.migration import migrate_v1_jsonl
from campusmail.research.validation import validate_jsonl

OPTIONS = dict(
    dataset_id="fixture-v1",
    task="academic",
    data_origin="synthetic",
    source_type="fixture",
)


def write(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_context_records_parent_and_group_edges_survive_migration(tmp_path):
    source = write(
        tmp_path / "in.jsonl",
        [
            {
                "document_id": "mail",
                "text": "Submit work",
                "primary_category": "assignments",
                "secondary_categories": [
                    "assignments",
                    "administration",
                    "administration",
                ],
            },
            {
                "document_id": "attachment",
                "text": " \n",
                "primary_category": "assignments",
                "source_metadata": {"parent_document_id": "mail"},
            },
        ],
    )
    edges = write(
        tmp_path / "edges.jsonl",
        [
            {
                "relationship_id": "r1",
                "source_id": "attachment",
                "target_id": "mail",
                "type": "supports",
                "evidence_spans": [],
            }
        ],
    )
    output = tmp_path / "out.jsonl"
    original = source.read_bytes()
    report = migrate_v1_jsonl(
        source, output, **OPTIONS, policy="preserve_context", relationships_path=edges
    )
    assert report["status"] == "valid"
    assert report["published_records"] == 2
    assert report["changes"] == {
        "duplicate_categories_removed": 1,
        "unavailable_text_context_only": 1,
    }
    rows = [json.loads(s) for s in output.read_text().splitlines()]
    assert rows[0]["secondary_categories"] == ["administration"]
    assert rows[1]["text_status"] == "unavailable"
    assert "primary_category" not in rows[1]
    assert rows[1]["parent_document_id"] == "mail"
    assert rows[1]["grouping_relations"][0]["target_document_id"] == "mail"
    assert (
        rows[1]["source_metadata"]["legacy_labels"]["primary_category"] == "assignments"
    )
    assert validate_jsonl(output)["unavailable_text_records"] == 1
    assert source.read_bytes() == original


def test_conflicting_labels_are_withheld_without_selecting_a_winner(tmp_path):
    source = write(
        tmp_path / "in.jsonl",
        [
            {
                "document_id": "a",
                "text": "Identical notice",
                "primary_category": "assignments",
            },
            {
                "document_id": "b",
                "text": "Identical notice",
                "primary_category": "examinations",
            },
        ],
    )
    output = tmp_path / "out.jsonl"
    assert migrate_v1_jsonl(source, output, **OPTIONS)["status"] == "invalid"
    assert not output.exists()
    report = migrate_v1_jsonl(source, output, **OPTIONS, policy="preserve_context")
    assert report["status"] == "valid"
    assert report["changes"]["conflicting_classification_withheld"] == 2
    rows = [
        ResearchDocument.model_validate(json.loads(s))
        for s in output.read_text().splitlines()
    ]
    assert all(
        r.primary_category is None and not r.gold_eligible("classification")
        for r in rows
    )
    assert {r.source_metadata["legacy_labels"]["primary_category"] for r in rows} == {
        "assignments",
        "examinations",
    }


def test_public_binary_zero_maps_explicitly_and_preserves_source_label(tmp_path):
    source = write(
        tmp_path / "in.jsonl",
        [
            {
                "record_id": "public-1",
                "task": "sentence_actionability",
                "text": "Thank you",
                "label": 0,
            }
        ],
    )
    output = tmp_path / "out.jsonl"
    options = {**OPTIONS, "task": "actionability", "data_origin": "public"}
    report = migrate_v1_jsonl(
        source, output, **options, input_format="sentence_actionability"
    )
    assert report["status"] == "valid"
    row = json.loads(output.read_text())
    assert row["actionability_label"] is False
    assert row["annotation_status"]["classification"] == {
        "completeness": "partial",
        "provenance": "source",
    }
    write(
        source,
        [
            {
                "record_id": "public-1",
                "task": "sentence_actionability",
                "text": "Thank you",
                "label": 2,
            }
        ],
    )
    original = output.read_bytes()
    assert (
        migrate_v1_jsonl(
            source, output, **options, input_format="sentence_actionability"
        )["status"]
        == "invalid"
    )
    assert output.read_bytes() == original


def test_missing_relationship_target_stops_publication(tmp_path):
    source = write(tmp_path / "in.jsonl", [{"document_id": "a", "text": "Notice"}])
    edges = write(
        tmp_path / "edges.jsonl",
        [
            {
                "relationship_id": "r",
                "source_id": "a",
                "target_id": "missing",
                "type": "updates",
            }
        ],
    )
    output = tmp_path / "out.jsonl"
    report = migrate_v1_jsonl(source, output, **OPTIONS, relationships_path=edges)
    assert report["status"] == "invalid"
    assert report["errors"][0]["code"] == "missing_reference"
    assert not output.exists()


def test_unavailable_text_cannot_be_labeled_or_claim_review():
    row = dict(
        schema_version="2.0",
        dataset_id="test",
        document_id="a",
        task="academic",
        data_origin="synthetic",
        source_type="fixture",
        text="",
        text_status="unavailable",
    )
    ResearchDocument.model_validate(row)
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate({**row, "text": "Readable"})
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate(
            {
                **row,
                "primary_category": "assignments",
                "annotation_status": {
                    "classification": {"provenance": "weak", "completeness": "partial"}
                },
            }
        )


def test_import_preflight_is_atomic_and_reports_unusable_text(tmp_path):
    store = Store(tmp_path / "store.sqlite")
    owner = store.create_user("Test")["id"]
    source = write(
        tmp_path / "in.jsonl",
        [{"document_id": "a", "text": "Notice"}, {"document_id": "b", "text": "  "}],
    )
    source.write_text(source.read_text() + "{invalid\n")
    with pytest.raises(ValueError):
        import_dataset(store, owner, source, dataset_id="test")
    assert store.list(owner, "message") == []
    write(
        source,
        [{"document_id": "a", "text": "Notice"}, {"document_id": "b", "text": "  "}],
    )
    report = {}
    assert import_dataset(store, owner, source, dataset_id="test", report=report) == 1
    assert report["excluded_unusable_text"] == 1
    assert report["created"] == 1
    write(
        source,
        [
            {"document_id": "new", "text": "New notice"},
            {"document_id": "a", "text": "Changed existing source"},
        ],
    )
    with pytest.raises(ValueError):
        import_dataset(store, owner, source, dataset_id="test")
    assert len(store.list(owner, "message")) == 1


def test_legacy_key_migration_backup_reimport_and_user_overrides(tmp_path):
    store = Store(tmp_path / "store.sqlite")
    owner = store.create_user("Test")["id"]
    row = {"document_id": "a", "text": "Notice", "subject": "Course"}
    source = write(tmp_path / "in.jsonl", [row])
    namespace = "a" * 12
    old = store.put(
        owner,
        "message",
        {
            "text": "Notice",
            "subject": "Course",
            "original_document_id": "a",
            "confirmed": "keep",
            "analysis": {"category": "manual"},
        },
        "dataset:" + namespace + ":a",
    )
    other = store.create_user("Other")["id"]
    untouched = store.put(
        other, "message", {"original_document_id": "a"}, "dataset:" + namespace + ":a"
    )
    with pytest.raises(ValueError, match="Legacy import identity"):
        import_dataset(store, owner, source, dataset_id="test")
    assert inspect_import_ids(store.path, owner=owner)["namespaces"] == {namespace: 1}
    assert (
        migrate_import_ids(
            store.path, owner=owner, dataset_id="test", legacy_namespace=namespace
        )["records"]
        == 1
    )
    assert store.get(owner, old["id"])["source_key"] == old["source_key"]
    backup = tmp_path / "backup.sqlite"
    report = migrate_import_ids(
        store.path,
        owner=owner,
        dataset_id="test",
        legacy_namespace=namespace,
        apply=True,
        backup_path=backup,
    )
    assert report["records"] == 1
    migrated = store.get(owner, old["id"])
    assert {k: v for k, v in migrated.items() if k != "source_key"} == {
        k: v for k, v in old.items() if k != "source_key"
    }
    assert store.get(other, untouched["id"]) == untouched
    with sqlite3.connect(backup) as db:
        assert (
            db.execute(
                "SELECT source_key FROM records WHERE id=?", (old["id"],)
            ).fetchone()[0]
            == old["source_key"]
        )
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    calls = []
    relocated = write(tmp_path / "moved.jsonl", [row])
    import_dataset(
        store,
        owner,
        relocated,
        dataset_id="test",
        on_message=lambda *a: calls.append(a),
    )
    assert len(store.list(owner, "message")) == 1
    final = store.get(owner, old["id"])
    assert final["confirmed"] == "keep" and final["analysis"] == {"category": "manual"}
    assert calls == []
    assert final["dataset_id"] == "test"


def test_legacy_collision_aborts_without_backup_or_changes(tmp_path):
    store = Store(tmp_path / "store.sqlite")
    owner = store.create_user("Test")["id"]
    namespace = "b" * 12
    legacy = store.put(
        owner, "message", {"original_document_id": "a"}, "dataset:" + namespace + ":a"
    )
    store.put(
        owner,
        "message",
        {"original_document_id": "a"},
        _dataset_source_key("test", "a"),
    )
    backup = tmp_path / "backup.sqlite"
    with pytest.raises(ValueError, match="already exists"):
        migrate_import_ids(
            store.path,
            owner=owner,
            dataset_id="test",
            legacy_namespace=namespace,
            apply=True,
            backup_path=backup,
        )
    assert not backup.exists()
    assert store.get(owner, legacy["id"]) == legacy


def test_interrupted_processing_resumes_but_completed_import_does_not_replay(tmp_path):
    store = Store(tmp_path / "store.sqlite")
    owner = store.create_user("Test")["id"]
    source = write(tmp_path / "in.jsonl", [{"document_id": "a", "text": "Notice"}])

    def fail(*args):
        raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError):
        import_dataset(store, owner, source, dataset_id="test", on_message=fail)
    record = store.list(owner, "message")[0]
    assert record["import_processing_status"] == "pending"
    calls = []

    def process(*args):
        calls.append(args)

    import_dataset(store, owner, source, dataset_id="test", on_message=process)
    import_dataset(store, owner, source, dataset_id="test", on_message=process)
    assert len(calls) == 1
    assert store.get(owner, record["id"])["import_processing_status"] == "complete"


def test_corpus_audit_measures_whitespace_overlap_and_references(tmp_path, monkeypatch):
    from campusmail.research import audit

    root = tmp_path / "dataset"
    root.mkdir()
    paths = {
        name: name + "/documents.jsonl"
        for name in ("scoped", "broad", "charlie9", "parakweet")
    }
    monkeypatch.setattr(audit, "SOURCES", paths)
    for name, relative in paths.items():
        path = root / relative
        path.parent.mkdir()
        if name in ("scoped", "broad"):
            rows = [
                {
                    "document_id": "a",
                    "text": "Private fixture body",
                    "source_type": "gmail_message",
                    "primary_category": "assignments",
                    "context_document_ids": [],
                },
                {
                    "document_id": "b",
                    "text": " \n",
                    "source_type": "gmail_attachment",
                    "source_metadata": {"parent_document_id": "a"},
                },
            ]
        else:
            rows = [
                {
                    "record_id": name + "1",
                    "text": "Shared actionability sentence",
                    "label": 0 if name == "charlie9" else 1,
                }
            ]
        write(path, rows)
    report = audit.audit_corpus(tmp_path, verify_assets=False)
    assert report["status"] == "valid"
    assert report["sources"]["scoped"]["counts"]["unusable_text"] == 1
    assert report["sources"]["scoped"]["counts"]["whitespace_only"] == 1
    assert (
        report["sources"]["scoped"]["reference_evidence_audit"]["parent_references"]
        == 1
    )
    assert report["overlap"]["charlie9:parakweet"]["label_disagreement_texts"] == 1
    assert report["overlap"]["scoped:broad"]["shared_document_ids"] == 2
    assert "Private fixture body" not in json.dumps(report)


def test_import_hash_and_duplicate_id_fail_before_mutation(tmp_path):
    store = Store(tmp_path / "store.sqlite")
    owner = store.create_user("Test")["id"]
    source = write(tmp_path / "in.jsonl", [{"document_id": "a", "text": "Notice"}])
    with pytest.raises(ValueError, match="checksum"):
        import_dataset(
            store, owner, source, dataset_id="test", expected_sha256="0" * 64
        )
    write(
        source,
        [{"document_id": "a", "text": "Notice"}, {"document_id": "a", "text": "Other"}],
    )
    with pytest.raises(ValueError, match="duplicate"):
        import_dataset(store, owner, source, dataset_id="test")
    assert store.list(owner, "message") == []


def test_prepare_refuses_changed_manifest_source_before_creating_output(tmp_path):
    import runpy

    prepare = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/prepare_research_data.py")
    )["prepare"]
    data = tmp_path / "dataset"
    data.mkdir()
    source = write(data / "in.jsonl", [{"document_id": "a", "text": "Notice"}])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "sources": [
                    {
                        "name": "test",
                        "dataset_id": "test",
                        "relative_path": "dataset/in.jsonl",
                        "input_sha256": "0" * 64,
                    }
                ],
            }
        )
    )
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="hash mismatch"):
        prepare(tmp_path, manifest, output, verify_assets=False)
    assert not output.exists()
