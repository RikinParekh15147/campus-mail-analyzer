from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import re
from .calendar import Calendar


class Reminders:
    def __init__(self, store):
        self.store = store

    def refresh(self, owner, clock=None):
        clock = clock or datetime.now(timezone.utc)
        zone = ZoneInfo(
            next(iter(self.store.list(owner, "settings")), {}).get(
                "timezone", "Asia/Kolkata"
            )
        )
        today = clock.astimezone(zone).date()
        valid = set()
        for item in Calendar(self.store).entries(
            owner, today, today + timedelta(days=90)
        ):
            if item.get("kind") == "class":
                continue
            target = (
                datetime.fromisoformat(item["start"])
                if item.get("start")
                else datetime.combine(date.fromisoformat(item["date"]), time(9), zone)
            )
            for hours in [24, 1] if item.get("start") else [24, 0]:
                key = (
                    item["id"]
                    + ":"
                    + item["date"]
                    + ":"
                    + str(hours)
                    + ":"
                    + target.isoformat()
                )
                valid.add(key)
                old = next(
                    (
                        r
                        for r in self.store.list(owner, "reminder")
                        if r["source_key"] == key
                    ),
                    None,
                )
                if old and old["status"] == "delivered":
                    continue
                self.store.put(
                    owner,
                    "reminder",
                    {
                        "record_id": item["id"],
                        "title": item["title"],
                        "target_date": item["date"],
                        "run_at": (target - timedelta(hours=hours)).isoformat(),
                        "status": "pending",
                        "time_unspecified": not bool(item.get("start")),
                    },
                    key,
                )
        for reminder in self.store.list(owner, "reminder"):
            if reminder["status"] == "pending" and reminder["source_key"] not in valid:
                self.store.patch(owner, reminder["id"], {"status": "cancelled"})

    def deliver(self, owner, clock=None):
        clock = clock or datetime.now(timezone.utc)
        for reminder in self.store.list(owner, "reminder"):
            if (
                reminder["status"] == "pending"
                and datetime.fromisoformat(reminder["run_at"]) <= clock
            ):
                self.store.put(
                    owner,
                    "notification",
                    {
                        "title": reminder["title"],
                        "date": reminder["target_date"],
                        "record_id": reminder["record_id"],
                        "read": False,
                        "time_unspecified": reminder["time_unspecified"],
                    },
                    reminder["id"],
                )
                self.store.patch(owner, reminder["id"], {"status": "delivered"})


class Briefings:
    def __init__(self, store):
        self.store = store

    def generate(self, owner, clock=None, days=7, enhancer=None):
        clock = clock or datetime.now(timezone.utc)
        zone = ZoneInfo(
            next(iter(self.store.list(owner, "settings")), {}).get(
                "timezone", "Asia/Kolkata"
            )
        )
        today = clock.astimezone(zone).date()
        calendar = Calendar(self.store)
        entries = calendar.entries(owner, today, today + timedelta(days=days))
        items = [
            {
                "id": x["id"],
                "title": x["title"],
                "date": x["date"],
                "start": x.get("start"),
                "kind": x["kind"],
                "evidence_ids": x.get("evidence_ids", []),
                "summary": x["title"]
                + " · "
                + x["date"]
                + (" · time not specified" if not x.get("start") else ""),
            }
            for x in entries
        ]
        items.extend(
            {
                "id": r["id"],
                "title": r["title"],
                "date": None,
                "kind": "reply_request",
                "evidence_ids": [r["message_id"]],
                "summary": "Reply needed: " + r["title"],
            }
            for r in self.store.list(owner, "reply_request")
            if r["state"] == "needs_reply"
        )
        method = "local_template"
        warning = None
        if enhancer and items:
            try:
                generated = enhancer(items)
                lookup = {x["id"]: x for x in items}
                if not isinstance(generated, list) or {
                    r["id"] for r in generated
                } != set(lookup):
                    raise ValueError("Summary IDs do not match supplied facts")
                for row in generated:
                    if set(row) - {"id", "summary"} or not isinstance(
                        row["summary"], str
                    ):
                        raise ValueError("Unsupported generated fields")
                    allowed = set(
                        re.findall(
                            r"\d+",
                            json.dumps(
                                {
                                    k: v
                                    for k, v in lookup[row["id"]].items()
                                    if k not in ("id", "evidence_ids")
                                }
                            ),
                        )
                    )
                    if set(re.findall(r"\d+", row["summary"])) - allowed:
                        raise ValueError("Generated numerical facts lack evidence")
                for row in generated:
                    lookup[row["id"]]["summary"] = row["summary"]
                method = "api_assisted"
            except Exception:
                warning = "Enhanced summary unavailable; local facts shown"
        result = {
            "date": today.isoformat(),
            "horizon_days": days,
            "items": items,
            "method": method,
            "warning": warning,
            "review_count": sum(
                r.get("status") == "open" for r in self.store.list(owner, "review")
            ),
            "conflicts": calendar.conflicts(owner, today, today + timedelta(days=days)),
        }
        result["text"] = (
            "Nothing scheduled in this window."
            if not items
            else "\n".join(x["summary"] for x in items)
        )
        result["fingerprint"] = hashlib.sha256(
            json.dumps(result, sort_keys=True).encode()
        ).hexdigest()
        return result

    def save_daily(self, owner, clock=None):
        report = self.generate(owner, clock, days=1)
        return self.store.put(owner, "briefing", report, "daily:" + report["date"])
