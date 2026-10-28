from datetime import date, datetime, timedelta
from urllib.parse import quote
import hashlib
from .engine import Engine


class CalendarSync:
    def __init__(self, store, owner, api):
        self.store, self.owner, self.api = store, owner, api

    def managed_calendar(self):
        old = next(iter(self.store.list(self.owner, "managed_calendar")), None)
        if old:
            return old["provider_id"]
        remote = self.api.post(
            "calendars",
            json={"summary": "Campus Mail Analyser", "timeZone": "Asia/Kolkata"},
        )
        self.store.put(
            self.owner, "managed_calendar", {"provider_id": remote["id"]}, "managed"
        )
        return remote["id"]

    @staticmethod
    def eligible(item):
        if item.get("status") in ("cancelled", "complete", "deleted"):
            return False
        if item["kind"] == "event":
            allowed = item.get("participation") in ("confirmed", "mandatory")
            schedulable = bool(
                item.get("date") or item.get("start") and item.get("end")
            )
        elif item["kind"] == "assignment":
            allowed = item.get("relevance") == "applicable"
            schedulable = bool(item.get("due_date"))
        else:
            return False
        return allowed and schedulable

    def unexport(self, mapping):
        if mapping["owner_id"] != self.owner or mapping["kind"] != "calendar_mapping":
            raise ValueError("Account or mapping mismatch")
        if mapping.get("status") == "deleted":
            return mapping
        path = (
            "calendars/" + quote(mapping["calendar_id"], safe="")
            + "/events/" + mapping["provider_id"]
        )
        try:
            self.api.delete(path)
        except LookupError:
            pass
        return self.store.patch(self.owner, mapping["id"], {"status": "deleted"})

    def reconcile_managed(self, items, calendar_id):
        """Export current eligible records and remove stale managed commitments."""
        eligible = {item["id"]: item for item in items if self.eligible(item)}
        for item in eligible.values():
            self.export(item, calendar_id)
        for mapping in self.store.list(self.owner, "calendar_mapping"):
            if (
                mapping.get("calendar_id") == calendar_id
                and mapping.get("status") == "active"
                and mapping.get("record_id") not in eligible
            ):
                self.unexport(mapping)

    def export(self, item, calendar_id):
        if item["owner_id"] != self.owner:
            raise ValueError("Account mismatch")
        remote_id = hashlib.sha256((self.owner + item["id"]).encode()).hexdigest()
        collection = "calendars/" + quote(calendar_id, safe="") + "/events"
        path = collection + "/" + remote_id
        if item.get("status") in ("cancelled", "complete"):
            try:
                self.api.delete(path)
            except LookupError:
                pass
            return self.store.put(
                self.owner,
                "calendar_mapping",
                {
                    "record_id": item["id"],
                    "provider_id": remote_id,
                    "calendar_id": calendar_id,
                    "status": "deleted",
                },
                item["id"],
            )
        day = item.get("due_date") or item.get("date")
        if not day and not (item.get("start") and item.get("end")):
            raise ValueError("Resolve event date before exporting")
        if item.get("start") and item.get("end"):
            start = {"dateTime": item["start"]}
            end = {"dateTime": item["end"]}
        elif item["kind"] == "assignment" and item.get("due_at"):
            due = datetime.fromisoformat(item["due_at"].replace("Z", "+00:00"))
            if due.tzinfo is None:
                raise ValueError("Timed deadline needs a timezone")
            start = {"dateTime": due.isoformat()}
            end = {"dateTime": (due + timedelta(minutes=1)).isoformat()}
        else:
            start = {"date": day}
            end = {"date": (date.fromisoformat(day) + timedelta(days=1)).isoformat()}
        payload = {
            "id": remote_id,
            "summary": item["title"],
            "start": start,
            "end": end,
            "transparency": (
                "opaque" if item["kind"] == "event" and "dateTime" in start
                else "transparent"
            ),
            "description": (
                "Deadline marker; does not block time. "
                if item["kind"] == "assignment" else ""
            ) + "Managed by Campus Mail Analyser. Refer to the original notice for official details.",
            "extendedProperties": {"private": {"campusmail_source": item["id"]}},
        }
        mapping = next(
            (
                r
                for r in self.store.list(self.owner, "calendar_mapping")
                if r["source_key"] == item["id"]
            ),
            None,
        )
        try:
            remote = self.api.get(path)
            if (
                mapping
                and remote.get("updated")
                and mapping.get("remote_updated")
                and remote["updated"] != mapping["remote_updated"]
            ):
                question = Engine(self.store).review(
                    self.owner,
                    "remote-edit:" + item["id"] + ":" + remote["updated"],
                    "Google Calendar changed this item; review before replacing it",
                    item["id"],
                    choices=["keep_remote", "replace_remote"],
                    context={"remote": remote},
                )
                if question.get("answer") != "replace_remote":
                    return mapping
            if not mapping or mapping.get("local_revision") != item["revision"]:
                remote = self.api.patch(
                    path, json={k: v for k, v in payload.items() if k != "id"}
                )
        except LookupError:
            if mapping and mapping.get("status") != "deleted":
                Engine(self.store).review(
                    self.owner,
                    "remote-deleted:" + item["id"],
                    "This event was removed from Google Calendar; confirm whether to restore it",
                    item["id"],
                )
                return mapping
            remote = self.api.post(collection, json=payload)
        return self.store.put(
            self.owner,
            "calendar_mapping",
            {
                "record_id": item["id"],
                "provider_id": remote_id,
                "calendar_id": calendar_id,
                "local_revision": item["revision"],
                "remote_updated": remote.get("updated"),
                "status": "active",
            },
            item["id"],
        )

    def pull(self, calendar_id="primary"):
        key = calendar_id
        state = next(
            (
                r
                for r in self.store.list(self.owner, "calendar_sync")
                if r["source_key"] == key
            ),
            None,
        )
        token = state.get("sync_token") if state else None
        page = None
        items = []
        next_sync = None
        for _ in range(100):
            params = {
                "maxResults": 2500,
                "singleEvents": True,
                **({"syncToken": token} if token else {}),
                **({"pageToken": page} if page else {}),
            }
            try:
                data = self.api.get(
                    "calendars/" + quote(calendar_id, safe="") + "/events",
                    params=params,
                )
            except LookupError:
                if token:
                    token = None
                    page = None
                    items = []
                    continue
                raise
            items.extend(data.get("items", []))
            page = data.get("nextPageToken")
            next_sync = data.get("nextSyncToken")
            if not page:
                break
        else:
            raise ValueError(
                "Calendar exceeds this sync budget; narrow selected calendars"
            )
        present = set()
        for remote in items:
            source_key = calendar_id + ":" + remote["id"]
            present.add(source_key)
            old = next(
                (
                    r
                    for r in self.store.list(self.owner, "external_event")
                    if r["source_key"] == source_key
                ),
                None,
            )
            if remote.get("status") == "cancelled":
                if old:
                    self.store.delete(self.owner, old["id"])
                continue
            if (
                remote.get("extendedProperties", {})
                .get("private", {})
                .get("campusmail_source")
            ):
                continue
            start = remote.get("start", {})
            end = remote.get("end", {})
            payload = {
                "title": remote.get("summary", "Busy"),
                "provider_id": remote["id"],
                "calendar_id": calendar_id,
                "status": "active",
                "flexible": False,
                "source_link": remote.get("htmlLink"),
            }
            if start.get("dateTime"):
                payload.update(start=start["dateTime"], end=end["dateTime"])
            elif start.get("date"):
                payload.update(date=start["date"], all_day=True)
            else:
                continue
            self.store.put(self.owner, "external_event", payload, source_key)
        if not token:
            for old in self.store.list(self.owner, "external_event"):
                if (
                    old.get("calendar_id") == calendar_id
                    and old["source_key"] not in present
                ):
                    self.store.delete(self.owner, old["id"])
        self.store.put(
            self.owner,
            "calendar_sync",
            {"calendar_id": calendar_id, "sync_token": next_sync},
            key,
        )
        return {"events": len(items), "calendar_id": calendar_id}
