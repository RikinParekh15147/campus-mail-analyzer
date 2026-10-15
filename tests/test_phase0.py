from pathlib import Path
from campusmail.store import Store, NotFound
from campusmail.models import Notice


def test_dataset_consolidation():
    root = Path(__file__).resolve().parents[1]
    assert (root / "dataset/mail/scoped_run/sanitized/documents.jsonl").is_file()
    assert (root / "dataset/public/normalized/charlie9_verified.jsonl").is_file()
    assert not (root / "mail_dataset").exists()
    assert not (root / "research/public_data").exists()


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
