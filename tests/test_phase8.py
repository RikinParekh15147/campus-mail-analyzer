import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from campusmail.store import Store
from campusmail.external_calendar import CalendarSync


class ExternalCalendarTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "db")
        self.owner = self.store.create_user("A")["id"]

    def test_export_reuses_deterministic_provider_id_after_retry(self):
        class API:
            def __init__(self):
                self.events = {}
                self.creates = 0

            def get(self, path, params=None):
                if path in self.events:
                    return self.events[path]
                raise LookupError(path)

            def post(self, path, json):
                self.creates += 1
                self.events[path + "/" + json["id"]] = {"id": json["id"], **json}
                return self.events[path + "/" + json["id"]]

            def patch(self, path, json):
                self.events[path].update(json)
                return self.events[path]

        api = API()
        sync = CalendarSync(self.store, self.owner, api)
        item = self.store.put(
            self.owner,
            "event",
            {"title": "Meeting", "date": "2026-10-25", "participation": "confirmed"},
            "meeting",
        )
        sync.export(item, "managed")
        sync.export(item, "managed")
        self.assertEqual(api.creates, 1)

    def test_expired_sync_token_recovers_and_remote_cancellation_removes_busy_item(
        self,
    ):
        class API:
            def get(self, path, params=None):
                if params and params.get("syncToken"):
                    raise LookupError("expired")
                return {
                    "items": [
                        {
                            "id": "remote1",
                            "summary": "Appointment",
                            "start": {"dateTime": "2026-10-25T09:00:00+05:30"},
                            "end": {"dateTime": "2026-10-25T10:00:00+05:30"},
                        }
                    ],
                    "nextSyncToken": "fresh",
                }

        sync = CalendarSync(self.store, self.owner, API())
        sync.pull("primary")
        sync.pull("primary")
        self.assertEqual(len(self.store.list(self.owner, "external_event")), 1)
        self.assertEqual(
            self.store.list(self.owner, "calendar_sync")[0]["sync_token"], "fresh"
        )
