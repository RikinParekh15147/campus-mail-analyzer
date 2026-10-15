from campusmail.store import Store
from campusmail.engine import Engine


def setup(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    return store, owner, Engine(store, blob_dir=tmp_path / "blobs")


def test_timed_meeting_produces_real_busy_interval(tmp_path):
    store, owner, engine = setup(tmp_path)
    message = store.put(
        owner,
        "message",
        {
            "subject": "Python Workshop",
            "text": "Python Workshop will be held on 25 October 2026 from 10:00 AM to 11:00 AM.",
        },
        "m",
    )
    engine.process(owner, message)
    event = store.list(owner, "event")[0]
    assert event["start"] == "2026-10-25T10:00:00+05:30"
    assert event["end"] == "2026-10-25T11:00:00+05:30"


def test_attachment_only_deadline_is_extracted_and_linked(tmp_path):
    store, owner, engine = setup(tmp_path)
    parent = store.put(
        owner,
        "message",
        {
            "subject": "NLP201 Assignment 2",
            "text": "Please see the attached instructions.",
        },
        "m",
    )
    resource = engine.attach(
        owner,
        b"NLP201 Assignment 2 must submit by 25 October 2026.",
        "instructions.txt",
        parent["id"],
    )
    task = store.list(owner, "assignment")[0]
    assert task["due_date"] == "2026-10-25"
    assert resource["id"] in task["resource_ids"]
    assert resource["importance"] == "high"


def test_rescheduled_date_does_not_retain_old_busy_interval(tmp_path):
    store, owner, engine = setup(tmp_path)
    first = store.put(
        owner,
        "message",
        {
            "subject": "Python Workshop",
            "text": "Python Workshop will be held on 25 October 2026 from 10:00 AM to 11:00 AM.",
        },
        "one",
    )
    engine.process(owner, first)
    update = store.put(
        owner,
        "message",
        {
            "subject": "Python Workshop",
            "text": "Python Workshop is rescheduled for 28 October 2026. Time will be confirmed.",
        },
        "two",
    )
    engine.process(owner, update)
    event = store.list(owner, "event")[0]
    assert event["date"] == "2026-10-28"
    assert event.get("start") is None
