import unittest
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
from campusmail.store import Store
from campusmail.ingestion import parse_message, import_dataset, GmailSync
from campusmail.jobs import Queue


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "db.sqlite")
        self.owner = self.store.create_user("A")["id"]

    def test_multipart_html_is_visible_and_attachment_is_a_reference(self):
        raw = {
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "headers": [{"name": "Subject", "value": "Meeting"}],
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {
                            "data": base64.urlsafe_b64encode(
                                b"<script>bad()</script><p>Hello</p>"
                            ).decode()
                        },
                    },
                    {
                        "filename": "agenda.pdf",
                        "mimeType": "application/pdf",
                        "body": {"attachmentId": "att1"},
                    },
                ],
            },
        }
        parsed = parse_message(raw)
        self.assertIn("Hello", parsed["text"])
        self.assertNotIn("bad()", parsed["text"])
        self.assertEqual(parsed["attachments"][0]["provider_id"], "att1")

    def test_import_is_idempotent_and_skips_unknown_annotations(self):
        path = Path(self.temp.name) / "docs.jsonl"
        path.write_text(
            '{"document_id":"d1","text":"Workshop on 25 October 2026","primary_category":"null"}\n'
        )
        import_dataset(self.store, self.owner, path)
        import_dataset(self.store, self.owner, path)
        docs = self.store.list(self.owner, "message")
        self.assertEqual(len(docs), 1)
        self.assertIsNone(docs[0]["source_category"])

    def test_jobs_survive_reopen_and_do_not_repeat_success(self):
        queue = Queue(self.store)
        queue.enqueue(self.owner, "count", {"value": 1}, "once")
        calls = []
        queue = Queue(Store(self.store.path))
        queue.run_once({"count": lambda owner, p: calls.append(p["value"])})
        queue.enqueue(self.owner, "count", {"value": 1}, "once")
        queue.run_once({"count": lambda owner, p: calls.append(9)})
        self.assertEqual(calls, [1])

    def test_history_cursor_expiry_rebootstraps_without_duplicates(self):
        class API:
            def get(self, path, params=None):
                if path == "profile":
                    return {"historyId": "200"}
                if path == "history":
                    raise LookupError("expired")
                if path == "messages":
                    return {"messages": [{"id": "m1"}]}
                if path == "messages/m1":
                    return {
                        "id": "m1",
                        "threadId": "t1",
                        "labelIds": ["INBOX"],
                        "payload": {
                            "headers": [],
                            "body": {
                                "data": base64.urlsafe_b64encode(
                                    b"Please register."
                                ).decode()
                            },
                            "mimeType": "text/plain",
                        },
                    }
                if path == "threads/t1":
                    return {"messages": []}
                raise AssertionError(path)

        sync = GmailSync(self.store, self.owner, API())
        sync.run()
        sync.run()
        self.assertEqual(len(self.store.list(self.owner, "message")), 1)
        self.assertEqual(
            self.store.list(self.owner, "sync_state")[0]["history_id"], "200"
        )
