import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from campusmail.research.contracts import ResearchDocument
from campusmail.research.validation import validate_jsonl


def document(**changes):
    return {
        "schema_version": "2.0",
        "dataset_id": "fabricated-dev",
        "document_id": "notice-1",
        "task": "academic",
        "data_origin": "synthetic",
        "source_type": "fixture",
        "text": "Please submit by 25 October 2026.",
        **changes,
    }


def reviewed():
    return {
        "completeness": "complete",
        "provenance": "human_reviewed",
        "reviewer_ids": ["reviewer-a"],
    }


def write_rows(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_unannotated_and_reviewed_empty_are_different():
    missing = ResearchDocument.model_validate(document())
    empty = ResearchDocument.model_validate(
        document(annotation_status={"dates": reviewed()})
    )
    assert missing.dates == empty.dates == []
    assert not missing.gold_eligible("dates")
    assert empty.gold_eligible("dates")
    # Being reviewed is separate from being real data: synthetic fixtures stay tagged.
    assert empty.data_origin == "synthetic"


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "1.0"},
        {
            "primary_category": "made_up",
            "annotation_status": {"classification": reviewed()},
        },
        {"primary_category": "assignments"},
        {"annotation_status": {"classification": reviewed()}},
        {"sent_at": "2026-10-01T12:00:00"},
        {"sent_at": 1790856000},
        {"context_document_ids": ["other"]},
        {"timezone": "Unknown/Nowhere"},
        {"data_origin": "operational"},
        {"human_reviewed": True},
        {
            "annotation_status": {
                "dates": {"completeness": "complete", "provenance": "human_reviewed"}
            }
        },
        {
            "annotation_status": {
                "dates": {
                    "completeness": "complete",
                    "provenance": "source",
                    "reviewer_ids": ["a"],
                }
            }
        },
    ],
)
def test_invalid_or_ambiguous_contracts_are_rejected(changes):
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate(document(**changes))


def test_exact_unicode_evidence_and_group_metadata_survive_roundtrip():
    text = "📚 Submit by 25 October 2026."
    row = document(
        text=text,
        thread_id="thread-1",
        parent_document_id="mail-1",
        duplicate_group_id="dup-1",
        template_group_id="template-1",
        leakage_group_id="leak-1",
        update_family_id="update-1",
        annotation_status={"dates": reviewed()},
        dates=[
            {
                "evidence": {
                    "field": "text",
                    "start": 12,
                    "end": 27,
                    "text": "25 October 2026",
                },
                "role": "assignment_deadline",
                "normalized_value": "2026-10-25",
                "precision": "date",
            }
        ],
    )
    # Compute offsets from Python Unicode indices, never UTF-8 byte positions.
    row["dates"][0]["evidence"]["start"] = text.index("25")
    row["dates"][0]["evidence"]["end"] = text.index("25") + len("25 October 2026")
    parsed = ResearchDocument.model_validate(row)
    assert ResearchDocument.model_validate(parsed.model_dump(mode="json")) == parsed
    for name in (
        "thread_id",
        "parent_document_id",
        "duplicate_group_id",
        "template_group_id",
        "leakage_group_id",
        "update_family_id",
    ):
        assert getattr(parsed, name) == row[name]
    broken = copy.deepcopy(row)
    broken["dates"][0]["evidence"]["start"] += 1
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate(broken)


def test_partial_annotation_cannot_be_used_as_gold():
    row = document(
        annotation_status={
            "actions": {
                "completeness": "partial",
                "provenance": "human_reviewed",
                "reviewer_ids": ["a"],
            }
        }
    )
    assert not ResearchDocument.model_validate(row).gold_eligible("actions")


def test_actionability_is_a_distinct_label_contract():
    row = document(
        task="actionability",
        actionability_label=False,
        annotation_status={"classification": reviewed()},
    )
    assert ResearchDocument.model_validate(row).actionability_label is False
    row["primary_category"] = "assignments"
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate(row)


def test_reference_date_cutoff_and_normalization_are_validated():
    row = document(
        sent_at="2026-10-02T12:00:00Z", context_cutoff_at="2026-10-01T12:00:00Z"
    )
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate(row)
    row = document(
        annotation_status={"dates": reviewed()},
        dates=[
            {
                "evidence": {"start": 17, "end": 32, "text": "25 October 2026"},
                "role": "assignment_deadline",
                "precision": "date",
                "normalized_value": "2026-02-30",
            }
        ],
    )
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate(row)


def test_streaming_validator_checks_forward_references_and_does_not_mutate_input(
    tmp_path,
):
    path = tmp_path / "documents.jsonl"
    write_rows(
        path,
        [
            document(document_id="attachment", parent_document_id="mail"),
            document(document_id="mail"),
        ],
    )
    before = path.read_bytes()
    report = validate_jsonl(path)
    assert report["status"] == "valid"
    assert report["schema_valid_records"] == 2
    assert path.read_bytes() == before
    assert report["unannotated_counts"]["dates"] == 2


def test_reference_must_exist_in_same_dataset_and_before_cutoff(tmp_path):
    path = tmp_path / "documents.jsonl"
    write_rows(
        path,
        [
            document(
                document_id="one",
                context_document_ids=["two"],
                context_cutoff_at="2026-10-01T12:00:00Z",
            ),
            document(document_id="two", sent_at="2026-10-02T12:00:00Z"),
        ],
    )
    assert "future_context" in {e["code"] for e in validate_jsonl(path)["errors"]}
    write_rows(path, [document(parent_document_id="missing")])
    assert "missing_reference" in {e["code"] for e in validate_jsonl(path)["errors"]}


def test_duplicate_ids_and_conflicting_duplicate_labels_are_errors(tmp_path):
    path = tmp_path / "documents.jsonl"
    write_rows(
        path,
        [
            document(
                primary_category="assignments",
                annotation_status={"classification": reviewed()},
            ),
            document(
                document_id="notice-2",
                primary_category="examinations",
                annotation_status={"classification": reviewed()},
            ),
            document(),
        ],
    )
    codes = {e["code"] for e in validate_jsonl(path)["errors"]}
    assert {"duplicate_document_id", "conflicting_duplicate_labels"} <= codes


def test_invalid_lines_are_redacted_and_error_details_are_bounded(tmp_path):
    path = tmp_path / "documents.jsonl"
    path.write_bytes(b'{"secret":"do-not-echo"}\nnot-json\n\xff\n\n')
    report = validate_jsonl(path, max_errors=2)
    assert report["error_count"] == 4
    assert len(report["errors"]) == 2
    assert report["errors_truncated"] is True
    assert "do-not-echo" not in json.dumps(report)


def test_empty_and_oversized_files_fail_validation(tmp_path):
    path = tmp_path / "documents.jsonl"
    path.write_bytes(b"")
    assert validate_jsonl(path)["status"] == "invalid"
    path.write_bytes(b"x" * 300 + b"\n")
    assert (
        validate_jsonl(path, max_line_bytes=100)["errors"][0]["code"]
        == "line_too_large"
    )


def test_cli_writes_report_and_prevents_source_overwrite(tmp_path):
    path, output = tmp_path / "documents.jsonl", tmp_path / "report.json"
    write_rows(path, [document()])
    base = [
        sys.executable,
        "-m",
        "campusmail",
        "dataset",
        "validate",
        "--input",
        str(path),
    ]
    result = subprocess.run(
        base + ["--report", str(output)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())["status"] == "valid"
    before = path.read_bytes()
    result = subprocess.run(
        base + ["--report", str(path)], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert path.read_bytes() == before


def test_checked_in_schema_matches_python_contract():
    schema = Path(__file__).resolve().parents[1] / "schemas/research_document.v2.json"
    assert json.loads(schema.read_text()) == ResearchDocument.model_json_schema()


def test_cross_document_entity_references_and_dataset_namespaces(tmp_path):
    path = tmp_path / "documents.jsonl"
    span = {"start": 0, "end": 6, "text": "Please"}
    rows = [
        document(
            document_id="source",
            annotation_status={"relationships": reviewed()},
            relationships=[
                {
                    "relationship_id": "link-1",
                    "target_document_id": "target",
                    "target_entity_id": "task-1",
                    "type": "supports",
                    "evidence_spans": [span],
                }
            ],
        ),
        document(
            document_id="target",
            annotation_status={"entities": reviewed()},
            entities=[
                {"entity_id": "task-1", "type": "assignment", "evidence_spans": [span]}
            ],
        ),
    ]
    write_rows(path, rows)
    assert validate_jsonl(path)["status"] == "valid"
    rows[1]["entities"][0]["entity_id"] = "different"
    write_rows(path, rows)
    assert "missing_entity_reference" in {
        e["code"] for e in validate_jsonl(path)["errors"]
    }
    rows[1]["dataset_id"] = "another-corpus"
    write_rows(path, rows)
    assert "missing_reference" in {e["code"] for e in validate_jsonl(path)["errors"]}


def test_exact_offset_mapping_must_match_original_text():
    row = document(
        original_text="Prefix " + document()["text"],
        offset_map=[{"start": 0, "end": 6, "original_start": 7, "original_end": 13}],
    )
    assert ResearchDocument.model_validate(row).offset_map
    row["offset_map"][0]["original_start"] = 0
    with pytest.raises(ValidationError):
        ResearchDocument.model_validate(row)


def test_pending_adjudication_is_not_gold_and_unknown_tasks_fail():
    status = {**reviewed(), "adjudication": "pending"}
    parsed = ResearchDocument.model_validate(
        document(annotation_status={"dates": status})
    )
    assert not parsed.gold_eligible("dates")
    with pytest.raises(ValueError, match="Unknown annotation task"):
        parsed.gold_eligible("typo")


def test_duplicate_json_keys_and_nan_are_rejected(tmp_path):
    path = tmp_path / "documents.jsonl"
    path.write_text('{"document_id":"a","document_id":"b"}\n{"value":NaN}\n')
    report = validate_jsonl(path)
    assert [e["code"] for e in report["errors"]] == ["invalid_json", "invalid_json"]


def test_oversized_line_is_drained_before_next_record_and_hash_covers_all_bytes(
    tmp_path,
):
    import hashlib

    path = tmp_path / "documents.jsonl"
    contents = b"x" * 2000 + b"\n" + json.dumps(document()).encode() + b"\n"
    path.write_bytes(contents)
    report = validate_jsonl(path, max_line_bytes=1000)
    assert report["physical_lines"] == 2
    assert report["schema_valid_records"] == 1
    assert report["error_count"] == 1
    assert report["input_sha256"] == hashlib.sha256(contents).hexdigest()


def test_report_cannot_overwrite_input_through_hardlink(tmp_path):
    import os

    source, alias = tmp_path / "input.jsonl", tmp_path / "alias.json"
    write_rows(source, [document()])
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("Filesystem does not support hard links")
    before = source.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "campusmail",
            "dataset",
            "validate",
            "--input",
            str(source),
            "--report",
            str(alias),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert source.read_bytes() == alias.read_bytes() == before


def test_invalid_dataset_cli_returns_failure_with_valid_json_report(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("not-json\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "campusmail",
            "dataset",
            "validate",
            "--input",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "invalid"


def test_fabricated_example_export_is_valid():
    path = Path(__file__).resolve().parents[1] / "tests/fixtures/research_v2.jsonl"
    report = validate_jsonl(path)
    assert report["status"] == "valid", report
    assert report["origin_counts"] == {"synthetic": 3}
    assert report["real_reviewed_complete_counts"]["classification"] == 0
