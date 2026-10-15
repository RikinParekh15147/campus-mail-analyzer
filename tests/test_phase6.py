import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from campusmail.store import Store
from campusmail.trackers import Conversations, Grades


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "db")
        self.owner = self.store.create_user("A")["id"]

    def test_sent_response_resolves_only_matching_request(self):
        self.store.put(
            self.owner,
            "message",
            {
                "thread_id": "t",
                "text": "Can you send the report? Can you confirm attendance?",
                "is_self": False,
                "sent_at": "2026-10-01T10:00:00+00:00",
            },
            "m1",
        )
        self.store.put(
            self.owner,
            "message",
            {
                "thread_id": "t",
                "text": "The report is attached.",
                "is_self": True,
                "sent_at": "2026-10-01T11:00:00+00:00",
            },
            "m2",
        )
        requests = Conversations(self.store).analyze(self.owner, "t")
        self.assertEqual([r["state"] for r in requests], ["resolved", "needs_reply"])

    def test_rhetorical_or_cc_only_message_does_not_require_reply(self):
        self.store.put(
            self.owner,
            "message",
            {"thread_id": "t", "text": "How are you?", "is_self": False},
            "m1",
        )
        self.assertEqual(Conversations(self.store).analyze(self.owner, "t"), [])

    def test_marks_require_established_identity_and_exact_match(self):
        grades = Grades(self.store)
        text = "23BIT0440 95/100\n23BIT044 80/100"
        self.assertEqual(grades.extract(self.owner, text, "NLP201", "Midsem", "d1"), [])
        self.store.put(
            self.owner,
            "profile_fact",
            {"field": "roll_number", "value": "23BIT044", "status": "confirmed"},
            "roll_number",
        )
        result = grades.extract(self.owner, text, "NLP201", "Midsem", "d1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["earned"], 80)

    def test_absent_is_not_zero_and_unknown_grading_has_no_total(self):
        self.store.put(
            self.owner,
            "profile_fact",
            {"field": "roll_number", "value": "23BIT044", "status": "confirmed"},
            "roll_number",
        )
        grades = Grades(self.store)
        r = grades.extract(self.owner, "23BIT044 ABSENT", "NLP201", "Quiz", "d1")[0]
        self.assertIsNone(r["earned"])
        self.assertEqual(r["result_status"], "absent")
        self.assertIsNone(grades.total(self.owner, "NLP201"))
