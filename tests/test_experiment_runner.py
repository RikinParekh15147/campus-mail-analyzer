"""EVAL-05 fixture runs are reproducible and stay in private research output."""

import json
from pathlib import Path

import pytest

from campusmail.research.experiment import run_rules_experiment
from campusmail.research.files import file_sha256
from campusmail.research.source_policy import expected_split


def inputs(tmp_path, partition="development"):
    source = tmp_path / "fixture.jsonl"
    source.write_text(json.dumps({
        "schema_version": "2.0", "dataset_id": "fixture-only",
        "document_id": "notice-1", "task": "academic",
        "data_origin": "synthetic", "source_type": "fixture",
        "text": "NLP201 Assignment 2 must submit by 25 October 2026.",
        "leakage_group_id": "guard-1",
    }) + "\n", encoding="utf-8")
    manifest = tmp_path / "selection.json"
    manifest.write_text(json.dumps({
        "schema_version": "development-selection-v1", "partition": partition,
        "dataset_id": "fixture-only", "document_ids": ["notice-1"],
        "guard_ids": ["guard-1"],
    }), encoding="utf-8")
    return source, manifest


def run(source, manifest, output, private):
    return run_rules_experiment(
        source, manifest, output, private,
        expected_input_sha256=file_sha256(source),
        expected_manifest_sha256=file_sha256(manifest),
        fixture_mode=True,
    )


def test_pinned_fixture_runs_reproduce_without_overwriting(tmp_path):
    source, manifest = inputs(tmp_path)
    private = tmp_path / "artifacts" / "research"
    first = run(source, manifest, private / "runs-a", private)
    second = run(source, manifest, private / "runs-b", private)
    assert first["run_id"] == second["run_id"]
    for filename in ("predictions.jsonl", "metrics.json", "run.json"):
        left = Path(first["output_dir"]) / filename
        right = Path(second["output_dir"]) / filename
        assert left.read_bytes() == right.read_bytes()
        assert left.stat().st_mode & 0o777 == 0o600
    assert first["metrics"]["documents_seen"] == 0
    assert json.loads((Path(first["output_dir"]) / "run.json").read_text())["label_status"] == "fixture_only"
    with pytest.raises(FileExistsError, match="already exists"):
        run(source, manifest, private / "runs-a", private)
    assert not (tmp_path / "artifacts" / "models").exists()


def test_runner_rejects_changed_input_holdout_and_public_output(tmp_path):
    source, manifest = inputs(tmp_path)
    private = tmp_path / "artifacts" / "research"
    with pytest.raises(ValueError, match="checksum changed"):
        run_rules_experiment(
            source, manifest, private / "runs", private,
            expected_input_sha256="0" * 64,
            expected_manifest_sha256=file_sha256(manifest), fixture_mode=True,
        )
    with pytest.raises(ValueError, match="private research root"):
        run(source, manifest, tmp_path / "public", private)
    source, manifest = inputs(tmp_path, partition="sealed_holdout")
    with pytest.raises(ValueError, match="development selection"):
        run(source, manifest, private / "runs", private)


@pytest.mark.parametrize("document_ids,guards", [([{"bad": "id"}], ["guard-1"]),
                                                 (["notice-1"], [True])])
def test_manifest_rejects_nonstring_ids_without_traceback(tmp_path, document_ids, guards):
    source, manifest = inputs(tmp_path)
    data = json.loads(manifest.read_text())
    data.update(document_ids=document_ids, guard_ids=guards)
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid identifiers"):
        run(source, manifest, tmp_path / "artifacts/research/runs", tmp_path / "artifacts/research")


def test_research_mode_requires_canonical_private_root_and_v2_custody(tmp_path):
    source, manifest = inputs(tmp_path)
    guard = next(f"guard-{i}" for i in range(100)
                 if expected_split("academic", f"guard-{i}") == "development")
    row = json.loads(source.read_text())
    row.update(data_origin="designated_research", leakage_group_id=guard)
    source.write_text(json.dumps(row) + "\n", encoding="utf-8")
    data = json.loads(manifest.read_text())
    data["guard_ids"] = [guard]
    manifest.write_text(json.dumps(data), encoding="utf-8")
    private = tmp_path / "artifacts/research/experiments"
    with pytest.raises(ValueError, match="project private research root"):
        run_rules_experiment(source, manifest, private / "runs", private,
                             expected_input_sha256=file_sha256(source),
                             expected_manifest_sha256=file_sha256(manifest))
    project_private = Path(__file__).resolve().parents[1] / "artifacts/research/experiments"
    with pytest.raises(ValueError, match="development selection manifest"):
        run_rules_experiment(source, manifest, project_private / "runs", project_private,
                             expected_input_sha256=file_sha256(source),
                             expected_manifest_sha256=file_sha256(manifest))
    assert not project_private.exists()


def test_run_identity_includes_fixture_mode_and_rejects_bad_seed(tmp_path):
    source, manifest = inputs(tmp_path)
    private = tmp_path / "artifacts/research"
    with pytest.raises(ValueError, match="seed"):
        run_rules_experiment(source, manifest, private / "runs", private,
                             expected_input_sha256=file_sha256(source),
                             expected_manifest_sha256=file_sha256(manifest),
                             seed=True, fixture_mode=True)
    first = run(source, manifest, private / "runs", private)
    identity = json.loads((Path(first["output_dir"]) / "run.json").read_text())
    assert identity["fixture_mode"] is True
    assert len(identity["code_sha256"]) == 64
    assert len(identity["dependency_spec_sha256"]) == 64
    assert identity["preprocessing_version"] == "nlp-rules-source-spans-v1"
    assert identity["dependencies"]["scikit-learn"]
