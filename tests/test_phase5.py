import unittest
from datetime import date
from tempfile import TemporaryDirectory
from pathlib import Path
from campusmail.store import Store, Conflict
from campusmail.calendar import Calendar, validate_timetable


def timetable():
    return {
        "schema_version": "1.0",
        "timezone": "Asia/Kolkata",
        "student_context": {"batch": "B"},
        "term_start": "2026-10-01",
        "term_end": "2026-12-31",
        "sessions": [
            {
                "course": "NLP201",
                "weekday": 0,
                "start": "09:00",
                "end": "10:00",
                "batch": "B",
            }
        ],
    }


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "db")
        self.owner = self.store.create_user("A")["id"]
        self.cal = Calendar(self.store)

    def test_wrong_batch_and_invalid_time_rejected(self):
        data = timetable()
        data["sessions"][0]["batch"] = "A"
        with self.assertRaises(ValueError):
            validate_timetable(data)
        data = timetable()
        data["sessions"][0]["end"] = "08:00"
        with self.assertRaises(ValueError):
            validate_timetable(data)

    def test_holidays_suppress_classes_only(self):
        preview = self.cal.import_timetable(self.owner, timetable(), confirm=False)
        self.assertEqual(
            self.cal.entries(self.owner, date(2026, 10, 19), date(2026, 10, 19)), []
        )
        self.cal.import_timetable(self.owner, timetable(), confirm=True)
        self.cal.import_holidays(
            self.owner,
            {
                "schema_version": "1.0",
                "timezone": "Asia/Kolkata",
                "holidays": [
                    {"date": "2026-10-19", "name": "Holiday", "classes_suspended": True}
                ],
            },
            True,
        )
        self.store.put(
            self.owner,
            "event",
            {
                "title": "Independent meeting",
                "date": "2026-10-19",
                "participation": "confirmed",
                "status": "active",
            },
            "meeting",
        )
        entries = self.cal.entries(self.owner, date(2026, 10, 19), date(2026, 10, 19))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Independent meeting")

    def test_deadline_is_not_a_busy_interval(self):
        self.store.put(
            self.owner,
            "assignment",
            {
                "title": "Assignment",
                "due_date": "2026-10-19",
                "relevance": "applicable",
                "status": "open",
            },
            "assignment",
        )
        entries = self.cal.entries(self.owner, date(2026, 10, 19), date(2026, 10, 19))
        self.assertFalse(entries[0]["blocks_time"])

    def test_resolution_is_a_proposal_until_approved_and_rechecks(self):
        fixed = self.store.put(
            self.owner,
            "calendar_item",
            {
                "title": "Class",
                "start": "2026-10-19T09:00:00+05:30",
                "end": "2026-10-19T10:00:00+05:30",
                "flexible": False,
            },
            "class",
        )
        flexible = self.store.put(
            self.owner,
            "calendar_item",
            {
                "title": "Study",
                "start": "2026-10-19T09:00:00+05:30",
                "end": "2026-10-19T10:00:00+05:30",
                "flexible": True,
            },
            "study",
        )
        conflicts = self.cal.conflicts(
            self.owner, date(2026, 10, 19), date(2026, 10, 19)
        )
        self.assertTrue(conflicts)
        proposal = self.cal.propose(self.owner, flexible["id"])
        self.assertEqual(
            self.store.get(self.owner, flexible["id"])["start"], flexible["start"]
        )
        self.cal.approve(self.owner, proposal["id"])
        self.assertNotEqual(
            self.store.get(self.owner, flexible["id"])["start"], flexible["start"]
        )
