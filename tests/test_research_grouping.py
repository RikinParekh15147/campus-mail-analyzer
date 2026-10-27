import json
from pathlib import Path

import pytest

from campusmail.research.files import file_sha256
from campusmail.research.grouping import build_components
from campusmail.research.group_verification import verify_membership


def doc(dataset, doc_id, text, *, task="academic", label=None, **changes):
    row = {
        "schema_version": "2.0",
        "dataset_id": dataset,
        "document_id": doc_id,
        "task": task,
        "data_origin": "synthetic",
        "source_type": "fixture",
        "text": text,
        **changes,
    }
    if label is not None:
        row["annotation_status"] = {
            "classification": {"completeness": "partial", "provenance": "synthetic"}
        }
        row["primary_category" if task == "academic" else "actionability_label"] = label
    return row


def source(tmp_path, name, dataset, rows, family=None):
    path = tmp_path / (name + ".jsonl")
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return {
        "name": name,
        "dataset_id": dataset,
        "source_family": family,
        "path": path,
        "expected_sha256": file_sha256(path),
    }


def memberships(folder):
    return {
        (r["dataset_id"], r["document_id"]): r["component_id"]
        for r in (json.loads(line) for line in (folder / "membership.jsonl").open())
    }


def test_all_declared_edges_and_cross_source_identity_are_grouped(tmp_path):
    long = " ".join(f"token{i:03d}" for i in range(130))
    variant = long.replace("token070", "replacement070")
    rows_a = [
        doc("a", "thread-1", "First notice", thread_id="thread"),
        doc("a", "thread-2", "Second notice", thread_id="thread"),
        doc(
            "a", "child", " ", text_status="unavailable", parent_document_id="thread-1"
        ),
        doc("a", "dup-1", "One document", duplicate_group_id="duplicate"),
        doc("a", "dup-2", "Another document", duplicate_group_id="duplicate"),
        doc("a", "template-1", "Template one", template_group_id="template"),
        doc("a", "template-2", "Template two", template_group_id="template"),
        doc("a", "update-1", "Update one", update_family_id="update"),
        doc("a", "update-2", "Update two", update_family_id="update"),
        doc(
            "a",
            "linked-1",
            "A link",
            grouping_relations=[
                {
                    "relationship_id": "r1",
                    "target_document_id": "linked-2",
                    "type": "updates",
                }
            ],
        ),
        doc("a", "linked-2", "Linked target"),
        doc(
            "a",
            "context-1",
            "Context source",
            context_document_ids=["context-2"],
            context_cutoff_at="2026-10-27T12:00:00Z",
        ),
        doc("a", "context-2", "Context target", sent_at="2026-10-26T12:00:00Z"),
        doc("a", "exact-a", "Identical text across sources", label="assignments"),
        doc("a", "near-a", long),
        doc(
            "a",
            "shared",
            "Different sanitized text A",
            data_origin="designated_research",
            sent_at="2026-10-20T12:00:00Z",
            thread_id="same-thread",
            source_metadata={"legacy_extra_fields": {"message_id": "provider-1"}},
        ),
    ]
    rows_b = [
        doc("b", "exact-b", "Identical text across sources", label="examinations"),
        doc("b", "near-b", variant),
        doc(
            "b",
            "shared",
            "Different sanitized text B",
            data_origin="designated_research",
            sent_at="2026-10-20T12:00:00Z",
            thread_id="same-thread",
            source_metadata={"legacy_extra_fields": {"message_id": "provider-1"}},
        ),
    ]
    rows_c = [
        doc(
            "c",
            "other-task",
            "Identical text across sources",
            task="actionability",
            label=True,
        )
    ]
    sources = [
        source(tmp_path, "first", "a", rows_a, "same-origin"),
        source(tmp_path, "second", "b", rows_b, "same-origin"),
        source(tmp_path, "third", "c", rows_c),
    ]
    out = tmp_path / "out"
    report = build_components(sources, out)
    groups = memberships(out)
    for first, second in [
        ("thread-1", "thread-2"),
        ("child", "thread-1"),
        ("dup-1", "dup-2"),
        ("template-1", "template-2"),
        ("update-1", "update-2"),
        ("linked-1", "linked-2"),
        ("context-1", "context-2"),
    ]:
        assert groups["a", first] == groups["a", second]
    assert groups["a", "exact-a"] == groups["b", "exact-b"]
    assert groups["a", "near-a"] == groups["b", "near-b"]
    assert groups["a", "shared"] == groups["b", "shared"]
    assert groups["c", "other-task"] != groups["a", "exact-a"]
    assert report["edge_unions"]["cross_snapshot_identity"] == 1
    assert report["near_new_edges"] >= 1
    assert report["exact_body_label_conflict_groups"]["academic"] == 1
    assert report["records"] == 20
    assert "Identical text across sources" not in json.dumps(report)
    reordered = tmp_path / "reordered"
    build_components(list(reversed(sources)), reordered)
    assert memberships(reordered) == groups


def test_source_identity_requires_metadata_agreement(tmp_path):
    left = doc(
        "a",
        "shared",
        "Private original",
        data_origin="designated_research",
        sent_at="2026-10-20T12:00:00Z",
        thread_id="t",
        source_metadata={"legacy_extra_fields": {"message_id": "provider-1"}},
    )
    right = doc(
        "b",
        "shared",
        "Different original",
        data_origin="designated_research",
        sent_at="2026-10-21T12:00:00Z",
        thread_id="t",
        source_metadata={"legacy_extra_fields": {"message_id": "provider-1"}},
    )
    report = build_components(
        [
            source(tmp_path, "a", "a", [left], "family"),
            source(tmp_path, "b", "b", [right], "family"),
        ],
        tmp_path / "out",
    )
    groups = memberships(tmp_path / "out")
    assert groups["a", "shared"] != groups["b", "shared"]
    assert report["status"] == "review_required"
    assert report["diagnostics"]["source_identity_metadata_conflicts"] == 1


def test_legacy_subject_group_is_audited_without_merging_unrelated_threads(tmp_path):
    rows = [
        doc(
            "a",
            "early",
            "A timetable from an old term",
            thread_id="t1",
            leakage_group_id="legacy-subject",
        ),
        doc(
            "a",
            "late",
            "An unrelated timetable years later",
            thread_id="t2",
            leakage_group_id="legacy-subject",
        ),
    ]
    report = build_components([source(tmp_path, "a", "a", rows)], tmp_path / "out")
    groups = memberships(tmp_path / "out")
    assert groups["a", "early"] != groups["a", "late"]
    assert report["legacy_leakage_groups_spanning_components"] == 1
    assert (
        len((tmp_path / "out" / "legacy_leakage_review.jsonl").read_text().splitlines())
        == 1
    )


def test_same_thread_token_is_namespaced_by_dataset(tmp_path):
    sources = [
        source(
            tmp_path,
            "a",
            "a",
            [doc("a", "one", "First unrelated notice", thread_id="t1")],
        ),
        source(
            tmp_path,
            "b",
            "b",
            [doc("b", "two", "Second unrelated notice", thread_id="t1")],
        ),
    ]
    build_components(sources, tmp_path / "out")
    groups = memberships(tmp_path / "out")
    assert groups["a", "one"] != groups["b", "two"]


def test_short_sentence_near_duplicates_are_grouped(tmp_path):
    text = "Please upload the signed registration form by Friday at the campus office for review."
    rows = [
        doc("a", "one", text, task="actionability", label=True),
        doc("a", "two", text[:-1] + "!", task="actionability", label=True),
    ]
    report = build_components([source(tmp_path, "a", "a", rows)], tmp_path / "out")
    groups = memberships(tmp_path / "out")
    assert groups["a", "one"] == groups["a", "two"]
    assert report["near_new_edges"] == 1
    edge = json.loads((tmp_path / "out" / "near_edges.jsonl").read_text())
    assert edge["method"] == "char5"
    assert (
        verify_membership([source(tmp_path, "a", "a", rows)], tmp_path / "out")[
            "status"
        ]
        == "valid"
    )


def test_giant_component_is_reported_and_private_membership_is_complete(tmp_path):
    rows = [
        doc("a", f"n{i:03d}", f"Text for member {i}", thread_id="oversized-thread")
        for i in range(105)
    ]
    report = build_components([source(tmp_path, "a", "a", rows)], tmp_path / "out")
    assert report["giant_components_total"] == 1
    assert report["giant_components"][0]["size"] == 105
    assert len(memberships(tmp_path / "out")) == 105
    assert report["membership_sha256"] == file_sha256(
        tmp_path / "out" / "membership.jsonl"
    )


def test_postcheck_rejects_corrupted_membership(tmp_path):
    rows = [
        doc("a", "one", "Notice one", thread_id="same"),
        doc("a", "two", "Notice two", thread_id="same"),
    ]
    sources = [source(tmp_path, "a", "a", rows)]
    folder = tmp_path / "out"
    build_components(sources, folder)
    assert verify_membership(sources, folder)["status"] == "valid"
    entries = [json.loads(line) for line in (folder / "membership.jsonl").open()]
    entries[1]["component_id"] = "cmp_" + "0" * 24
    (folder / "membership.jsonl").write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries)
    )
    check = verify_membership(sources, folder)
    assert check["status"] == "invalid"
    assert check["errors"]["hard_edge_crosses_component"] >= 1


def test_invalid_or_changed_export_never_creates_component_output(tmp_path):
    src = source(tmp_path, "a", "a", [doc("a", "one", "Valid source")])
    src["expected_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        build_components([src], tmp_path / "out")
    assert not (tmp_path / "out").exists()
    src["expected_sha256"] = file_sha256(src["path"])
    src["path"].write_text(src["path"].read_text() + "{broken\n")
    src["expected_sha256"] = file_sha256(src["path"])
    with pytest.raises(ValueError, match="not fully valid"):
        build_components([src], tmp_path / "out")
    assert not (tmp_path / "out").exists()
