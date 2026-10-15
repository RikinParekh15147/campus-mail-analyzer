import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from campusmail.store import Store
from campusmail.engine import Engine


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "db")
        self.owner = self.store.create_user("Student")["id"]
        self.engine = Engine(self.store)

    def message(self, key, text, subject="NLP201 Assignment 2"):
        msg = self.store.put(
            self.owner, "message", {"text": text, "subject": subject}, key
        )
        return self.engine.process(self.owner, msg)

    def test_cross_email_resources_and_revised_deadline(self):
        self.message(
            "one",
            "NLP201 Assignment 2 instructions: https://example.edu/instructions.pdf",
        )
        self.message("two", "NLP201 Assignment 2 must submit by 25 October 2026.")
        self.message(
            "three", "NLP201 Assignment 2 deadline extended to 28 October 2026."
        )
        tasks = self.store.list(self.owner, "assignment")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["due_date"], "2026-10-28")
        self.assertEqual(len(tasks[0]["resource_ids"]), 1)
        self.assertGreaterEqual(tasks[0]["revision"], 2)

    def test_identity_requires_corroboration_and_is_not_taken_from_class_list(self):
        self.message("table", "Results: 23BIT044 80/100", "Exam results")
        self.assertEqual(self.store.list(self.owner, "profile_fact"), [])
        self.message("identity", "Your roll number is 23BIT044.", "Student identity")
        facts = self.store.list(self.owner, "profile_fact")
        self.assertEqual(facts[0]["status"], "inferred")
        self.assertTrue(self.store.list(self.owner, "review"))

    def test_duplicate_attachment_does_not_create_second_resource(self):
        a = self.engine.attach(self.owner, b"Assignment instructions", "one.txt")
        b = self.engine.attach(self.owner, b"Assignment instructions", "copy.txt")
        self.assertEqual(a["id"], b["id"])

    def test_multiple_events_are_preserved(self):
        self.message(
            "multi",
            "Python Workshop will be held on 25 October 2026. Robotics Workshop will be held on 28 October 2026.",
            "Upcoming workshops",
        )
        self.assertEqual(len(self.store.list(self.owner, "event")), 2)
