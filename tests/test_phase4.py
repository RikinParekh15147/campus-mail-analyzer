import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from campusmail.store import Store, Conflict
from campusmail.personalization import Personalizer


class PersonalLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "db")
        self.a = self.store.create_user("A")["id"]
        self.b = self.store.create_user("B")["id"]
        self.p = Personalizer(self.store)
        self.item = self.store.put(
            self.a,
            "event",
            {
                "title": "Robotics workshop",
                "course": "ROB201",
                "importance": "medium",
                "participation": "unknown",
            },
            "robotics",
        )

    def test_correction_updates_item_and_only_personal_memory(self):
        self.p.feedback(self.a, self.item["id"], "importance", "high")
        self.assertEqual(self.store.get(self.a, self.item["id"])["importance"], "high")
        self.assertEqual(
            self.store.get(self.a, self.item["id"])["participation"], "unknown"
        )
        self.assertEqual(len(self.store.list(self.a, "feedback")), 1)
        self.assertEqual(self.store.list(self.b, "preference"), [])

    def test_acceptance_is_feedback_but_repeat_click_is_deduplicated(self):
        self.p.feedback(self.a, self.item["id"], "importance", "medium")
        self.p.feedback(self.a, self.item["id"], "importance", "medium")
        self.assertEqual(len(self.store.list(self.a, "feedback")), 1)

    def test_invalid_or_stale_feedback_is_rejected(self):
        with self.assertRaises(ValueError):
            self.p.feedback(self.a, self.item["id"], "importance", "critical")
        self.p.feedback(self.a, self.item["id"], "importance", "high")
        with self.assertRaises(Conflict):
            self.p.feedback(
                self.a, self.item["id"], "importance", "low", expected_revision=1
            )

    def test_deferred_question_does_not_learn(self):
        q = self.store.put(
            self.a,
            "review",
            {
                "question": "Interested?",
                "status": "open",
                "record_id": self.item["id"],
                "field": "participation",
            },
            "q",
        )
        self.p.answer(self.a, q["id"], None, defer=True)
        self.assertEqual(self.store.list(self.a, "feedback"), [])
