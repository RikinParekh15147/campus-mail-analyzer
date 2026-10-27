from pathlib import Path
from datetime import datetime, timezone
import base64
import hashlib
import json
import re
from .store import Store
from .engine import Engine
from .personalization import Personalizer
from .calendar import Calendar
from .trackers import Conversations, Grades
from .briefings import Briefings, Reminders
from .jobs import Queue
from .ingestion import import_dataset, GmailSync
from .google import GoogleConnection, GoogleHTTP
from .external_calendar import CalendarSync

from .paths import PROJECT


class Application:
    def __init__(self, data_dir, project_root=None):
        self.project = Path(project_root or PROJECT)
        self.data_dir = Path(data_dir)
        self.store = Store(self.data_dir / "campus.sqlite")
        self.engine = Engine(
            self.store,
            self.project / "artifacts/models/academic/classifier.joblib",
            self.data_dir / "blobs",
        )
        self.personal = Personalizer(self.store)
        self.calendar = Calendar(self.store)
        self.grades = Grades(self.store)
        self.conversations = Conversations(self.store)
        self.reminders = Reminders(self.store)
        self.briefings = Briefings(self.store)
        self.queue = Queue(self.store)
        self.oauth_configs = {}

    def settings(self, owner):
        old = next(iter(self.store.list(owner, "settings")), None)
        return old or {
            "timezone": "Asia/Kolkata",
            "sync_minutes": 10,
            "gmail_labels": ["INBOX"],
            "senders": [],
            "calendar_ids": ["primary"],
        }

    def process(self, owner, message):
        if not message.get("text", "").strip():
            self.store.patch(
                owner,
                message["id"],
                {
                    "analysis": {
                        "category": "unknown",
                        "dates": [],
                        "actions": [],
                        "resources": [],
                        "courses": [],
                        "reason": "No readable email body; inspect attached content",
                    }
                },
            )
            return
        self.engine.process(owner, message)
        if (
            message.get("sanitized")
            and message.get("source_type")
            and message["source_type"] != "gmail_message"
        ):
            resource = self.engine.resource(
                owner,
                {
                    "title": "Imported attachment",
                    "filename": message.get("original_document_id", "attachment")
                    + ".txt",
                    "text": message["text"],
                    "status": "readable",
                    "sha256": hashlib.sha256(message["text"].encode()).hexdigest(),
                    "message_ids": [message["id"]],
                    "sanitized": True,
                },
                "imported:" + message["id"],
            )
            parent = next(
                (
                    m
                    for m in self.store.list(owner, "message")
                    if m.get("original_message_id") == message.get("parent_message_id")
                ),
                None,
            )
            if parent:
                self.store.patch(
                    owner,
                    parent["id"],
                    {
                        "attachment_resource_ids": sorted(
                            set(
                                parent.get("attachment_resource_ids", [])
                                + [resource["id"]]
                            )
                        )
                    },
                )
                self.engine.process(owner, self.store.get(owner, parent["id"]))
        for item in self.store.list(owner):
            if item["kind"] in ("assignment", "event") and message["id"] in item.get(
                "evidence_ids", []
            ):
                adjusted = self.personal.apply(owner, item)
                if adjusted != item:
                    self.store.patch(owner, item["id"], adjusted)
        if message.get("thread_id"):
            self.conversations.analyze(owner, message["thread_id"])
        if re.search(
            r"\b(marks|results?|score)\b",
            message.get("subject", "") + " " + message["text"],
            re.I,
        ):
            analysis = self.store.get(owner, message["id"]).get("analysis", {})
            assessment = re.search(
                r"\b(midsem|endsem|quiz\s*\d+|assignment\s*\d+)\b",
                message.get("subject", ""),
                re.I,
            )
            if len(analysis.get("courses", [])) == 1 and assessment:
                self.grades.extract(
                    owner,
                    message["text"],
                    analysis["courses"][0],
                    assessment.group().lower(),
                    message["id"],
                )

    def ingest(self, owner, text, subject="", reference_date=None, source_key=None):
        if not text.strip():
            raise ValueError("Paste readable notice text")
        message = self.store.put(
            owner,
            "message",
            {"text": text, "subject": subject, "sent_at": reference_date},
            source_key,
        )
        self.process(owner, message)
        return self.store.get(owner, message["id"])

    def attach(self, owner, data, filename, parent_id=None):
        resource = self.engine.attach(owner, data, filename, parent_id)
        if resource.get("analysis_message_id"):
            self.process(owner, self.store.get(owner, resource["analysis_message_id"]))
        return resource

    def dataset_collection(self, collection):
        manifest = json.loads((self.project / "dataset_collections.json").read_text())
        if collection not in manifest:
            raise ValueError("Unknown dataset collection")
        entry = manifest[collection]
        relative = Path(entry["relative_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Dataset collection path must stay inside the project")
        path = (self.project / relative).resolve()
        if not path.is_relative_to(self.project.resolve()):
            raise ValueError("Dataset collection path must stay inside the project")
        if not path.is_file():
            raise ValueError("Dataset is not installed")
        return path, entry["dataset_id"]

    def dataset_path(self, collection):
        return self.dataset_collection(collection)[0]

    def import_collection(self, owner, payload, report=None):
        collection = payload.get("collection", "scoped")
        path, dataset_id = self.dataset_collection(collection)
        entry = json.loads((self.project / "dataset_collections.json").read_text())[
            collection
        ]
        return import_dataset(
            self.store,
            owner,
            path,
            self.process,
            payload.get("limit"),
            dataset_id=dataset_id,
            report=report,
            expected_sha256=entry.get("input_sha256"),
        )

    def gmail_sync(self, owner, payload):
        connection = GoogleConnection(owner, "gmail")
        api = GoogleHTTP(connection)
        settings = self.settings(owner)

        def callback(account, message):
            self.process(account, message)
            for attachment in message.get("attachments", []):
                key = (
                    "gmail-attachment:"
                    + message["provider_id"]
                    + ":"
                    + (attachment.get("provider_id") or attachment["filename"])
                )
                if any(
                    r["source_key"] == key
                    for r in self.store.list(owner, "attachment_download")
                ):
                    continue
                if (attachment.get("size") or 0) > 20 * 1024 * 1024:
                    self.engine.resource(
                        owner,
                        {
                            **attachment,
                            "status": "too_large",
                            "title": attachment["filename"],
                            "message_ids": [message["id"]],
                        },
                        key,
                    )
                    continue
                try:
                    encoded = (
                        attachment.get("inline_data")
                        or api.get(
                            "messages/"
                            + message["provider_id"]
                            + "/attachments/"
                            + attachment["provider_id"]
                        )["data"]
                    )
                    data = base64.urlsafe_b64decode(
                        encoded + "=" * ((-len(encoded)) % 4)
                    )
                    resource = self.attach(
                        owner, data, attachment["filename"], message["id"]
                    )
                    self.store.put(
                        owner,
                        "attachment_download",
                        {"resource_id": resource["id"], "status": "complete"},
                        key,
                    )
                except Exception as error:
                    self.engine.resource(
                        owner,
                        {
                            "title": attachment["filename"],
                            "status": "download_failed",
                            "error": str(error)[:150],
                            "message_ids": [message["id"]],
                        },
                        key,
                    )

        sync = GmailSync(
            self.store,
            owner,
            api,
            callback,
            {
                "labels": settings.get("gmail_labels", ["INBOX"]),
                "senders": settings.get("senders", []),
            },
        )
        result = sync.run(payload.get("limit", 50))
        missing = [
            item
            for item in self.store.list(owner, "assignment")
            if not item.get("resource_ids")
            and item.get("course")
            and re.search(
                r"attachment|attached|pdf|earlier (?:email|mail)",
                item.get("description", ""),
                re.I,
            )
        ]
        for item in missing[:3]:
            key = "backfill:" + item["id"]
            if any(
                r["source_key"] == key for r in self.store.list(owner, "context_search")
            ):
                continue
            if not any(
                self.store.get(owner, mid).get("provider_id")
                for mid in item.get("evidence_ids", [])
            ):
                continue
            course = re.sub(r"[^A-Za-z0-9 ]", "", item["course"])
            number = re.search(r"Assignment (\d+)", item["title"])
            query = (
                '"'
                + course
                + '" '
                + ('"Assignment ' + number[1] + '" ' if number else "")
                + "has:attachment"
            )
            found = sync.search_context(query, 10)
            self.store.put(owner, "context_search", {"query": query, **found}, key)
        return result

    def calendar_sync(self, owner, payload):
        api = GoogleHTTP(GoogleConnection(owner, "calendar"))
        sync = CalendarSync(self.store, owner, api)
        for calendar_id in self.settings(owner).get("calendar_ids", ["primary"]):
            sync.pull(calendar_id)
        managed = sync.managed_calendar()
        for item in self.store.list(owner):
            if (
                item["kind"] == "event"
                and item.get("participation") in ("confirmed", "mandatory")
                or item["kind"] == "assignment"
                and item.get("relevance") == "applicable"
            ):
                if item.get("date") or item.get("due_date") or item.get("start"):
                    sync.export(item, managed)

    def connect(self, owner, payload):
        service = payload["service"]
        config = self.oauth_configs.pop((owner, service), None)
        if config is None:
            raise ValueError("Choose your OAuth client configuration again")
        GoogleConnection(owner, service).connect(config)

    def reprocess(self, owner, payload):
        for message in self.store.list(owner, "message"):
            self.process(owner, message)

    def run_jobs(self):
        return self.queue.run_once(
            {
                "import": self.import_collection,
                "gmail_sync": self.gmail_sync,
                "calendar_sync": self.calendar_sync,
                "connect": self.connect,
                "reprocess": self.reprocess,
            }
        )

    def tick(self):
        self.run_jobs()
        clock = datetime.now(timezone.utc)
        for user in self.store.users():
            owner = user["id"]
            self.reminders.refresh(owner, clock)
            self.reminders.deliver(owner, clock)
            self.briefings.save_daily(owner, clock)
            for service in ("gmail", "calendar"):
                if GoogleConnection(owner, service).status()["connected"]:
                    interval = max(5, self.settings(owner).get("sync_minutes", 10))
                    bucket = int(clock.timestamp() // (interval * 60))
                    self.queue.enqueue(
                        owner, service + "_sync", {}, service + ":" + str(bucket)
                    )

    def dashboard(self, owner):
        records = self.store.list(owner)
        counts = {}
        for kind, name in [
            ("assignment", "assignments"),
            ("event", "events"),
            ("resource", "resources"),
            ("grade", "grades"),
        ]:
            counts[name] = sum(r["kind"] == kind for r in records)
        counts["review"] = sum(
            r["kind"] == "review" and r.get("status") == "open" for r in records
        )
        counts["replies"] = sum(
            r["kind"] == "reply_request" and r.get("state") == "needs_reply"
            for r in records
        )
        return {
            "counts": counts,
            "timezone": self.settings(owner).get("timezone", "Asia/Kolkata"),
            "summary": self.briefings.generate(owner),
            "notifications": [
                r for r in records if r["kind"] == "notification" and not r.get("read")
            ],
            "sync": next(iter(self.store.list(owner, "sync_state")), None),
            "recent": [r for r in records if r["kind"] in ("assignment", "event")][-8:],
            "important_resources": [
                r
                for r in records
                if r["kind"] == "resource" and r.get("importance") == "high"
            ][-5:],
        }
