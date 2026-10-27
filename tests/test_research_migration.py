import json
from pathlib import Path
import subprocess
import sys

from campusmail.research.contracts import ResearchDocument
from campusmail.research.migration import migrate_v1_jsonl
from campusmail.research.validation import validate_jsonl


OPTIONS = {
    "dataset_id": "campus-mail-scoped-v1",
    "task": "academic",
    "data_origin": "synthetic",
    "source_type": "fixture",
}


def test_legacy_migration_preserves_groups_but_never_invents_gold(tmp_path):
    source = tmp_path / "legacy.jsonl"
    output = tmp_path / "v2.jsonl"
    row = {
        "document_id": "d1",
        "text": "Submit the assignment.",
        "original_text": "Submit the assignment.",
        "subject": "Course notice",
        "primary_category": "assignments",
        "secondary_categories": ["workshops_events"],
        "secondary_categories_complete": True,
        "label_provenance": "human_reviewed",
        "source_metadata": {"source": "fabricated"},
        "thread_id": "thread-1",
        "duplicate_group_id": "dup-1",
        "template_group_id": "template-1",
        "leakage_group_id": "leak-1",
        "update_family_id": "update-1",
        "legacy_unknown": {"key": "value"},
        "dates": [{"raw_value": "tomorrow"}],
    }
    source.write_text(json.dumps(row) + "\n", encoding="utf-8")
    original = source.read_bytes()
    report = migrate_v1_jsonl(source, output, **OPTIONS)
    assert report["status"] == "valid"
    assert source.read_bytes() == original
    assert validate_jsonl(output)["status"] == "valid"
    converted = ResearchDocument.model_validate(json.loads(output.read_text()))
    assert converted.annotation_status.classification.completeness == "partial"
    assert converted.annotation_status.classification.provenance == "weak"
    assert not converted.gold_eligible("classification")
    assert converted.annotation_status.dates.completeness == "unannotated"
    assert converted.source_metadata["legacy_extra_fields"]["dates"] == row["dates"]
    assert converted.source_metadata["legacy_secondary_categories_complete"] is True
    assert converted.source_metadata["legacy_label_provenance"] == "human_reviewed"
    assert converted.source_metadata["legacy_source_metadata"] == row["source_metadata"]
    for field in (
        "thread_id",
        "duplicate_group_id",
        "template_group_id",
        "leakage_group_id",
        "update_family_id",
    ):
        assert getattr(converted, field) == row[field]


def test_invalid_legacy_rows_do_not_publish_or_replace_output(tmp_path):
    source = tmp_path / "legacy.jsonl"
    output = tmp_path / "existing.jsonl"
    output.write_text("existing", encoding="utf-8")
    source.write_text(
        json.dumps({"document_id": "d1", "text": "One"})
        + "\n"
        + json.dumps({"document_id": "d1", "text": "Two"})
        + "\n"
    )
    report = migrate_v1_jsonl(source, output, **OPTIONS)
    assert report["status"] == "invalid"
    assert report["errors"][0]["code"] == "duplicate_document_id"
    assert output.read_text() == "existing"


def test_malformed_and_unknown_labels_are_excluded_without_private_text(tmp_path):
    source = tmp_path / "legacy.jsonl"
    output = tmp_path / "v2.jsonl"
    source.write_text(
        json.dumps(
            {"document_id": "d1", "text": "secret body", "primary_category": "invented"}
        )
        + "\n{broken private text\n"
    )
    report = migrate_v1_jsonl(source, output, **OPTIONS)
    assert report["status"] == "invalid"
    assert report["error_count"] == 2
    assert not output.exists()
    assert "secret body" not in json.dumps(report)
    assert "broken private text" not in json.dumps(report)


def test_migration_refuses_source_overwrite_and_schema_v2(tmp_path):
    source = tmp_path / "legacy.jsonl"
    source.write_text('{"schema_version":"2.0","document_id":"d1","text":"One"}\n')
    try:
        migrate_v1_jsonl(source, source, **OPTIONS)
        assert False, "source overwrite was accepted"
    except ValueError:
        pass
    report = migrate_v1_jsonl(source, tmp_path / "v2.jsonl", **OPTIONS)
    assert report["errors"][0]["line"] == 1
    assert report["errors"][0]["code"] == "unsupported_legacy_record"


def test_migration_cli_produces_valid_export(tmp_path):
    source = tmp_path / "legacy.jsonl"
    output = tmp_path / "v2.jsonl"
    source.write_text('{"document_id":"d1","text":"A notice"}\n')
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "campusmail",
            "dataset",
            "migrate-v1",
            "--input",
            str(source),
            "--output",
            str(output),
            "--dataset-id",
            OPTIONS["dataset_id"],
            "--task",
            OPTIONS["task"],
            "--data-origin",
            OPTIONS["data_origin"],
            "--source-type",
            OPTIONS["source_type"],
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "valid"
    assert validate_jsonl(output)["status"] == "valid"
