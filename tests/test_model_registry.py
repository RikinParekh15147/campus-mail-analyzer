"""A pickle is never opened without a pinned, compatible bundle."""

import json

import pytest

from campusmail.model_registry import (
    activate_plain_model, model_health, promote_bundle, rollback_bundle,
    seal_bundle, verify_bundle,
)


def _bundle(tmp_path):
    directory = tmp_path / "candidate"
    directory.mkdir()
    (directory / "classifier.joblib").write_bytes(b"fixture pickle bytes, never loaded")
    (directory / "metrics.json").write_text(json.dumps({"scope": "fixture"}))
    digest = seal_bundle(directory, task="academic", model_revision="fixture-v1",
                         thresholds={"safe_auto": 0.9})
    return directory, digest


def test_pinned_bundle_rejects_corruption_and_resealing(tmp_path):
    directory, digest = _bundle(tmp_path)
    metadata = verify_bundle(directory, task="academic", expected_manifest_sha256=digest)
    assert metadata["taxonomy"][0] == "examinations"
    with pytest.raises(FileExistsError):
        seal_bundle(directory, task="academic", model_revision="fixture-v2", thresholds={})
    with pytest.raises(ValueError, match="pinned"):
        verify_bundle(directory, task="academic", expected_manifest_sha256="")
    (directory / "classifier.joblib").write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact checksum"):
        verify_bundle(directory, task="academic", expected_manifest_sha256=digest)


def test_bundle_rejects_wrong_taxonomy_preprocessing_and_unpinned_manifest(tmp_path):
    directory, digest = _bundle(tmp_path)
    with pytest.raises(ValueError, match="incompatible"):
        verify_bundle(directory, task="actionability", expected_manifest_sha256=digest)
    manifest = json.loads((directory / "bundle.json").read_text())
    manifest["preprocessing_version"] = "old"
    (directory / "bundle.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest checksum"):
        verify_bundle(directory, task="academic", expected_manifest_sha256=digest)
    from hashlib import sha256
    new_digest = sha256((directory / "bundle.json").read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="incompatible"):
        verify_bundle(directory, task="academic", expected_manifest_sha256=new_digest)


def test_bundle_rejects_symlinked_model_even_with_matching_hash(tmp_path):
    directory = tmp_path / "candidate"
    directory.mkdir()
    external = tmp_path / "model.joblib"
    external.write_bytes(b"not trusted")
    (directory / "classifier.joblib").symlink_to(external)
    (directory / "metrics.json").write_text("{}")
    with pytest.raises(ValueError, match="non-symlinked"):
        seal_bundle(directory, task="academic", model_revision="fixture-v1", thresholds={})


def test_atomic_promotion_runtime_fallback_and_rollback(tmp_path):
    import joblib
    from sklearn.dummy import DummyClassifier

    from campusmail.nlp import analyze
    from campusmail.store import Store

    (tmp_path / "profile").mkdir()
    store = Store(tmp_path / "profile/campus.sqlite")
    owner = store.create_user("student")["id"]
    assignment = store.put(owner, "assignment", {
        "title": "Assignment 2", "due_date": "2026-10-28",
        "due_date_origin": "user_confirmed",
    })

    task_dir = tmp_path / "artifacts/models/academic"
    bundles = task_dir / "bundles"
    bundles.mkdir(parents=True)

    def candidate(bundle_id, label):
        directory = bundles / bundle_id
        directory.mkdir()
        model = DummyClassifier(strategy="constant", constant=label)
        model.fit(["first", "second"], ["assignments", "workshops_events"])
        joblib.dump(model, directory / "classifier.joblib")
        (directory / "metrics.json").write_text(json.dumps({"evaluation_scope": "fixture"}))
        return seal_bundle(directory, task="academic", model_revision=bundle_id,
                           thresholds={})

    first = candidate("candidate-a", "assignments")
    second = candidate("candidate-b", "workshops_events")
    legacy = task_dir / "classifier.joblib"
    joblib.dump(DummyClassifier(strategy="most_frequent"), legacy)
    before = analyze("Attend the seminar tomorrow.", model_path=legacy)
    assert before["classification_method"] == "local_rules"
    assert before["model_health"] == "invalid_or_unavailable"
    assert model_health(task_dir, task="academic")["status"] == "rules_only"

    promote_bundle(task_dir, task="academic", bundle_id="candidate-a",
                   manifest_sha256=first, expected_revision=0)
    active = analyze("Attend the seminar tomorrow.", model_path=legacy)
    assert active["category"] == "assignments"
    assert active["model_health"] == "verified"
    assert active["model_revision"] == "candidate-a"
    assert active["model_bundle_id"] == "candidate-a"
    assert model_health(task_dir, task="academic")["status"] == "verified"
    from campusmail.diagnostics import inspect_assets
    assert inspect_assets(tmp_path)["models"]["academic"]["status"] == "verified"

    promote_bundle(task_dir, task="academic", bundle_id="candidate-b",
                   manifest_sha256=second, expected_revision=1)
    with pytest.raises(ValueError, match="revision changed"):
        promote_bundle(task_dir, task="academic", bundle_id="candidate-a",
                       manifest_sha256=first, expected_revision=1)
    second_result = analyze("Attend the seminar tomorrow.", model_path=legacy)
    assert second_result["category"] == "workshops_events"
    assert second_result["model_revision"] == "candidate-b"
    rollback_bundle(task_dir, task="academic", expected_revision=2)
    assert analyze("Attend the seminar tomorrow.", model_path=legacy)["category"] == \
        "assignments"
    assert store.get(owner, assignment["id"])["due_date_origin"] == "user_confirmed"
    assert store.get(owner, assignment["id"])["due_date"] == "2026-10-28"

    (bundles / "candidate-a/classifier.joblib").write_bytes(b"corrupt")
    invalid = analyze("Attend the seminar tomorrow.", model_path=legacy)
    assert invalid["classification_method"] == "local_rules"
    assert invalid["model_health"] == "invalid_or_unavailable"
    assert invalid["model_revision"] == "local_rules"
    assert model_health(task_dir, task="academic")["status"] == "rules_only"
    assert inspect_assets(tmp_path)["models"]["academic"]["bundle_health"]["status"] == \
        "rules_only"


def test_failed_pointer_replace_preserves_active_bundle(tmp_path, monkeypatch):
    import campusmail.model_registry as registry

    task_dir = tmp_path / "academic"
    bundles = task_dir / "bundles"
    for bundle_id in ("candidate-a", "candidate-b"):
        directory = bundles / bundle_id
        directory.mkdir(parents=True)
        (directory / "classifier.joblib").write_bytes(bundle_id.encode())
        (directory / "metrics.json").write_text("{}")
    first = seal_bundle(bundles / "candidate-a", task="academic",
                        model_revision="candidate-a", thresholds={})
    second = seal_bundle(bundles / "candidate-b", task="academic",
                         model_revision="candidate-b", thresholds={})
    promote_bundle(task_dir, task="academic", bundle_id="candidate-a",
                   manifest_sha256=first, expected_revision=0)
    old = (task_dir / "active.json").read_bytes()
    monkeypatch.setattr(registry.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(OSError, match="injected"):
        promote_bundle(task_dir, task="academic", bundle_id="candidate-b",
                       manifest_sha256=second, expected_revision=1)
    assert (task_dir / "active.json").read_bytes() == old
    assert not list(task_dir.glob(".active-*"))
    assert not (task_dir / ".promotion.lock").exists()


def test_models_api_exposes_rules_only_health_without_legacy_scores(tmp_path):
    from fastapi.testclient import TestClient

    from campusmail.api import create_app

    legacy = tmp_path / "artifacts/models/academic"
    legacy.mkdir(parents=True)
    (legacy / "classifier.joblib").write_bytes(b"unverified")
    (legacy / "metrics.json").write_text(json.dumps({"records": 999,
                                                       "models": {"linear_svm": {"macro_f1": 1}}}))
    app = create_app(tmp_path / "profile", project_root=tmp_path,
                     bootstrap_key="test-bootstrap", worker=False)
    with TestClient(app) as client:
        token = client.post("/profiles", json={"name": "Student"},
                            headers={"X-Bootstrap-Key": "test-bootstrap"}).json()["token"]
        headers = {"Authorization": "Bearer " + token}
        reports = client.get("/models", headers=headers).json()
        assert reports["academic"]["health"]["status"] == "rules_only"
        assert "records" not in reports["academic"]
        notice = client.post("/ingest", headers=headers,
                             json={"subject": "Assignment 2", "text": "Submit tomorrow."})
        assert notice.status_code == 200
        assert notice.json()["analysis"]["classification_method"] == "local_rules"


def test_plain_activation_checks_hash_and_prefers_explicit_rule_on_conflict(tmp_path):
    import joblib
    from sklearn.dummy import DummyClassifier

    from campusmail.nlp import analyze
    from campusmail.preprocessing import PREPROCESSING_VERSION
    import sklearn

    task_dir = tmp_path / "academic"
    task_dir.mkdir()
    model = DummyClassifier(strategy="constant", constant="workshops_events")
    from campusmail.models import CATEGORIES
    model.fit([str(index) for index in range(len(CATEGORIES))], list(CATEGORIES))
    joblib.dump(model, task_dir / "classifier.joblib")
    (task_dir / "metrics.json").write_text(json.dumps({
        "preprocessing_version": PREPROCESSING_VERSION,
        "sklearn_version": sklearn.__version__, "selected": "linear_svm",
        "evaluation_scope": "development_only_source_or_weak_labels",
        "dataset_sha256": "fixture", "labels": sorted(CATEGORIES),
    }))
    activation = activate_plain_model(task_dir, task="academic")
    assert activation["model_revision"].startswith("plain-")
    assert model_health(task_dir, task="academic")["activation_kind"] == "plain"
    result = analyze("Assignment 2 must be submitted today.",
                     model_path=task_dir / "classifier.joblib")
    assert result["category"] == "assignments"
    assert result["classification_method"] == "local_rules_model_disagreement"
    assert result["model_health"] == "verified"
    assert result["model_bundle_id"] is None
    original = (task_dir / "classifier.joblib").read_bytes()
    (task_dir / "classifier.joblib").write_bytes(b"corrupt")
    fallback = analyze("Assignment 2 must be submitted today.",
                       model_path=task_dir / "classifier.joblib")
    assert fallback["classification_method"] == "local_rules"
    assert fallback["model_health"] == "invalid_or_unavailable"
    (task_dir / "classifier.joblib").write_bytes(original)

    backup = task_dir / "bundles/weak-backup"
    backup.mkdir(parents=True)
    joblib.dump(model, backup / "classifier.joblib")
    (backup / "metrics.json").write_text("{}")
    digest = seal_bundle(backup, task="academic", model_revision="weak-backup",
                         thresholds={})
    promote_bundle(task_dir, task="academic", bundle_id="weak-backup",
                   manifest_sha256=digest, expected_revision=0)
    assert model_health(task_dir, task="academic")["activation_kind"] == "plain"
    assert model_health(task_dir, task="academic")["backup_bundle"] == "weak-backup"
    (task_dir / "classifier.joblib").write_bytes(b"corrupt")
    rescued = analyze("Assignment 2 must be submitted today.",
                      model_path=task_dir / "classifier.joblib")
    assert rescued["model_health"] == "verified"
    assert rescued["model_bundle_id"] == "weak-backup"
    assert rescued["category"] == "assignments"
    assert model_health(task_dir, task="academic")["activation_kind"] == "bundle_fallback"
