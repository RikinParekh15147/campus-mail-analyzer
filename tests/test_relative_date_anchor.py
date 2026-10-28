"""FIX-03 source-time and timezone regressions for relative dates."""

import base64
from datetime import datetime
import json

from campusmail.dataset_import import import_dataset
from campusmail.engine import Engine
from campusmail.ingestion import GmailSync, parse_message
from campusmail.nlp import analyze
from campusmail.store import Store


def _gmail(text, *, date_header=None, received="2026-10-25T03:35:00+00:00"):
    headers = [{"name": "Subject", "value": "NLP201 Assignment 2"}]
    if date_header:
        headers.append({"name": "Date", "value": date_header})
    return {
        "id": "gmail-relative", "labelIds": ["INBOX"],
        "internalDate": str(int(datetime.fromisoformat(received).timestamp() * 1000)),
        "payload": {"headers": headers, "mimeType": "text/plain",
                    "body": {"data": base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")}},
    }


def test_named_source_timezone_changes_relative_calendar_day():
    text = "NLP201 Assignment 2 must submit by tomorrow."
    utc = analyze(text, reference_date="2026-10-24T21:00:00+00:00")
    local = analyze(text, reference_date="2026-10-24T21:00:00+00:00",
                    source_timezone="Asia/Kolkata")
    assert utc["dates"][0]["normalized"] == "2026-10-25"
    assert local["dates"][0]["normalized"] == "2026-10-26"
    assert local["dates"][0]["text"] == "tomorrow"
    invalid = analyze(text, reference_date="2026-10-24T21:00:00+00:00",
                      source_timezone="Unknown/Zone")
    assert invalid["dates"][0]["normalized"] is None
    assert invalid["dates"][0]["needs_review"]
    assert invalid["dates"][0]["reason"] == "Unknown source timezone"


def test_historical_dataset_import_keeps_source_timezone(tmp_path):
    path = tmp_path / "historical.jsonl"
    path.write_text(json.dumps({
        "document_id": "archived-1", "subject": "NLP201 Assignment 2",
        "text": "NLP201 Assignment 2 must submit by tomorrow.",
        "sent_at": "2026-10-24T21:00:00+00:00", "timezone": "Asia/Kolkata",
    }) + "\n", encoding="utf-8")
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store)
    import_dataset(store, owner, path, on_message=engine.process,
                   dataset_id="historical-fixture")
    message = store.list(owner, "message")[0]
    assert message["timezone"] == "Asia/Kolkata"
    assert message["analysis"]["dates"][0]["normalized"] == "2026-10-26"
    assert store.list(owner, "assignment")[0]["due_date"] == "2026-10-26"
    engine.process(owner, store.get(owner, message["id"]))
    assert len(store.list(owner, "assignment")) == 1
    assert store.list(owner, "assignment")[0]["due_date"] == "2026-10-26"

    # Simulate the prior importer, which stored the row hash but omitted timezone.
    store.patch(owner, message["id"], {
        "timezone": None, "import_processing_status": "complete",
    })
    report = {}
    import_dataset(store, owner, path, on_message=engine.process,
                   dataset_id="historical-fixture", report=report)
    restored = store.get(owner, message["id"])
    assert report["existing"] == 1 and report["processed"] == 1
    assert restored["timezone"] == "Asia/Kolkata"
    assert restored["analysis"]["dates"][0]["normalized"] == "2026-10-26"


def test_gmail_authored_offset_overrides_utc_receipt_for_relative_date(tmp_path):
    text = "NLP201 Assignment 2 must submit by tomorrow."
    raw = _gmail(text, date_header="Sat, 24 Oct 2026 23:30:00 -0400")
    parsed = parse_message(raw)
    assert parsed["sent_at"] == "2026-10-24T23:30:00-04:00"
    assert parsed["received_at"] == "2026-10-25T03:35:00+00:00"
    assert parsed["relative_reference_trusted"] is True
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    GmailSync(store, owner, api=None, on_message=Engine(store).process).ingest(raw)
    assignment = store.list(owner, "assignment")[0]
    assert assignment["due_date"] == "2026-10-25"


def test_receipt_only_time_cannot_silently_anchor_tomorrow(tmp_path):
    text = "NLP201 Assignment 2 must submit by tomorrow."
    raw = _gmail(text)
    assert parse_message(raw)["relative_reference_trusted"] is False
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    GmailSync(store, owner, api=None, on_message=Engine(store).process).ingest(raw)
    message = store.list(owner, "message")[0]
    assert message["analysis"]["dates"][0]["normalized"] is None
    assert message["analysis"]["dates"][0]["needs_review"]
    assert all(item.get("due_date") is None for item in store.list(owner, "assignment"))


def test_legacy_gmail_without_reference_provenance_fails_closed(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store, blob_dir=tmp_path / "blobs")
    legacy = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2",
        "text": "NLP201 Assignment 2 must submit by tomorrow.",
        "sent_at": "2026-10-25T03:35:00+00:00",
    }, "gmail:legacy")
    engine.process(owner, legacy)
    analyzed = store.get(owner, legacy["id"])
    assert analyzed["analysis"]["dates"][0]["normalized"] is None
    engine.attach(owner, b"NLP201 Assignment 2 must submit by tomorrow.",
                  "instructions.txt", legacy["id"])
    child = next(message for message in store.list(owner, "message")
                 if message.get("parent_record_id") == legacy["id"])
    assert child["relative_reference_trusted"] is False
    assert child["analysis"]["dates"][0]["normalized"] is None


def test_attachment_inherits_trusted_timezone_and_untrusted_receipt(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store, blob_dir=tmp_path / "blobs")
    trusted = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2", "text": "See attached instructions.",
        "sent_at": "2026-10-24T21:00:00+00:00", "timezone": "Asia/Kolkata",
        "relative_reference_trusted": True,
    }, "trusted")
    engine.attach(owner, b"NLP201 Assignment 2 must submit by tomorrow.",
                  "instructions.txt", trusted["id"])
    assert any(item.get("due_date") == "2026-10-26"
               for item in store.list(owner, "assignment"))
    untrusted = store.put(owner, "message", {
        "subject": "NLP201 Assignment 3", "text": "See attached instructions.",
        "sent_at": "2026-10-24T21:00:00+00:00", "timezone": "Asia/Kolkata",
        "relative_reference_trusted": False,
    }, "untrusted")
    engine.attach(owner, b"NLP201 Assignment 3 must submit by tomorrow.",
                  "instructions3.txt", untrusted["id"])
    child = next(message for message in store.list(owner, "message")
                 if message.get("parent_record_id") == untrusted["id"])
    assert child["relative_reference_trusted"] is False
    assert child["analysis"]["dates"][0]["normalized"] is None
