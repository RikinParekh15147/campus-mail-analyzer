from pathlib import Path
import json
import pytest
from campusmail.store import Store, NotFound
from campusmail.models import Notice
from campusmail.training import load_rows


@pytest.mark.research
def test_dataset_consolidation():
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "dataset/mail/scoped_run/sanitized/documents.jsonl",
        "dataset/public/normalized/charlie9_verified.jsonl",
    ):
        assert (root / relative).is_file(), (
            f"Research input missing: {relative}. Install the private research export "
            "or run the default suite without --run-research."
        )
    assert not (root / "mail_dataset").exists()
    assert not (root / "research/public_data").exists()


def test_training_input_contract_uses_sanitized_fixture(tmp_path):
    rows = [
        {
            "document_id": "fixture-1",
            "subject": "NLP201",
            "text": "Submit assignment.",
            "primary_category": "assignments",
            "leakage_group_id": "fixture-thread",
        },
        {
            "document_id": "fixture-2",
            "text": "Unlabeled notice",
            "primary_category": None,
        },
    ]
    path = tmp_path / "documents.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    assert load_rows(path) == [
        {
            "text": "NLP201 Submit assignment.",
            "label": "assignments",
            "group": "fixture-thread",
        }
    ]


def test_store_isolates_accounts_and_persists(tmp_path):
    path = tmp_path / "app.sqlite"
    store = Store(path)
    a, b = store.create_user("A"), store.create_user("B")
    record = store.put(
        a["id"], "assignment", {"title": "Private"}, source_key="message1"
    )
    assert store.list(b["id"], "assignment") == []
    try:
        store.get(b["id"], record["id"])
        raise AssertionError("Cross-account read succeeded")
    except NotFound:
        pass
    again = store.put(
        a["id"], "assignment", {"title": "Updated"}, source_key="message1"
    )
    assert again["id"] == record["id"]
    assert len(Store(path).list(a["id"], "assignment")) == 1


def test_unknown_date_is_not_invented():
    doc = Notice(text="Please submit your assignment soon.")
    assert doc.reference_date is None
    assert doc.owner_id is None
