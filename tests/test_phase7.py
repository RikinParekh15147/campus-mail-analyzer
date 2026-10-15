import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from campusmail.store import Store
from campusmail.briefings import Briefings, Reminders


class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "db")
        self.owner = self.store.create_user("A")["id"]
        self.task = self.store.put(
            self.owner,
            "assignment",
            {
                "title": "NLP Assignment",
                "due_date": "2026-10-21",
                "relevance": "applicable",
                "status": "open",
                "evidence_ids": ["source1"],
            },
            "task",
        )
        self.clock = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)

    def test_reminders_are_durable_and_delivered_once(self):
        r = Reminders(self.store)
        r.refresh(self.owner, self.clock)
        r.deliver(self.owner, self.clock)
        r.deliver(self.owner, self.clock)
        self.assertEqual(len(self.store.list(self.owner, "notification")), 1)

    def test_changed_deadline_cancels_old_pending_reminders(self):
        r = Reminders(self.store)
        r.refresh(self.owner, self.clock)
        self.store.patch(self.owner, self.task["id"], {"due_date": "2026-11-01"})
        r.refresh(self.owner, self.clock)
        old = [
            x
            for x in self.store.list(self.owner, "reminder")
            if x["target_date"] == "2026-10-21"
        ]
        self.assertTrue(all(x["status"] == "cancelled" for x in old))

    def test_briefing_is_source_linked_and_updates_when_data_changes(self):
        b = Briefings(self.store)
        first = b.generate(self.owner, self.clock)
        self.assertEqual(first["items"][0]["evidence_ids"], ["source1"])
        self.store.patch(self.owner, self.task["id"], {"status": "complete"})
        self.assertEqual(b.generate(self.owner, self.clock)["items"], [])

    def test_unknown_api_ids_fall_back_to_local_summary(self):
        report = Briefings(self.store).generate(
            self.owner,
            self.clock,
            enhancer=lambda facts: [{"id": "invented", "summary": "Invented event"}],
        )
        self.assertEqual(report["method"], "local_template")
