from campusmail.application import Application


def test_attachment_only_email_does_not_block_ingestion(tmp_path):
    app = Application(tmp_path)
    owner = app.store.create_user("A")["id"]
    parent = app.store.put(
        owner,
        "message",
        {"subject": "NLP201 Assignment 2", "text": "", "provider_id": "mail-with-pdf"},
        "m",
    )
    app.process(owner, parent)
    resource = app.attach(
        owner,
        b"NLP201 Assignment 2 must submit by 25 October 2026.",
        "instructions.txt",
        parent["id"],
    )
    assert app.store.list(owner, "assignment")[0]["due_date"] == "2026-10-25"
    assert resource["status"] == "readable"
