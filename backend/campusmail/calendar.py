from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .store import Conflict


class Session(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course: str
    weekday: int = Field(ge=0, le=6)
    start: time
    end: time
    batch: str | None = None
    location: str = ""
    instructor: str = ""

    @model_validator(mode="after")
    def valid(self):
        if self.start >= self.end:
            raise ValueError("Session end must follow start")
        return self


class Timetable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    timezone: str
    student_context: dict
    term_start: date
    term_end: date
    sessions: list[Session]
    exceptions: list[dict] = []

    @model_validator(mode="after")
    def valid(self):
        ZoneInfo(self.timezone)
        if self.term_end < self.term_start:
            raise ValueError("Invalid term range")
        if (self.term_end - self.term_start).days > 730:
            raise ValueError("Term exceeds two years")
        batch = self.student_context.get("batch")
        if any(s.batch and s.batch != batch for s in self.sessions):
            raise ValueError("Resolve batch alternatives before importing")
        for i, a in enumerate(self.sessions):
            if any(
                a.weekday == b.weekday and a.start < b.end and b.start < a.end
                for b in self.sessions[i + 1 :]
            ):
                raise ValueError("Resolve overlapping timetable choices")
        return self


class Holiday(BaseModel):
    date: date
    name: str
    classes_suspended: bool = True
    end_date: date | None = None
    batches: list[str] = []

    @model_validator(mode="after")
    def valid(self):
        if self.end_date and self.end_date < self.date:
            raise ValueError("Holiday end precedes start")
        return self


class Holidays(BaseModel):
    schema_version: Literal["1.0"]
    timezone: str
    academic_year: str | None = None
    holidays: list[Holiday]

    @model_validator(mode="after")
    def valid(self):
        ZoneInfo(self.timezone)
        return self


def validate_timetable(data):
    return Timetable.model_validate(data).model_dump(mode="json")


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Calendar times require a timezone")
    return result


class Calendar:
    def __init__(self, store):
        self.store = store

    def import_timetable(self, owner, data, confirm=False):
        parsed = validate_timetable(data)
        if confirm:
            self.store.put(owner, "timetable", {**parsed, "active": True}, "active")
        return parsed

    def import_holidays(self, owner, data, confirm=False):
        parsed = Holidays.model_validate(data).model_dump(mode="json")
        if confirm:
            self.store.put(owner, "holidays", {**parsed, "active": True}, "active")
        return parsed

    def entries(self, owner, start, end):
        if isinstance(start, str):
            start = date.fromisoformat(start)
        if isinstance(end, str):
            end = date.fromisoformat(end)
        if end < start or (end - start).days > 366:
            raise ValueError("Calendar query must be within one year")
        records = self.store.list(owner)
        result = []
        zone = ZoneInfo(
            next((r for r in records if r["kind"] == "settings"), {}).get(
                "timezone", "Asia/Kolkata"
            )
        )
        timetable = next(
            (r for r in records if r["kind"] == "timetable" and r.get("active")), None
        )
        holidays = next(
            (r for r in records if r["kind"] == "holidays" and r.get("active")), {}
        ).get("holidays", [])
        if timetable:
            zone = ZoneInfo(timetable["timezone"])
            day = max(start, date.fromisoformat(timetable["term_start"]))
            while day <= min(end, date.fromisoformat(timetable["term_end"])):
                blocked = any(
                    h.get("classes_suspended")
                    and date.fromisoformat(h["date"])
                    <= day
                    <= date.fromisoformat(h.get("end_date") or h["date"])
                    and (
                        not h.get("batches")
                        or timetable["student_context"].get("batch") in h["batches"]
                    )
                    for h in holidays
                )
                for i, s in enumerate(timetable["sessions"]):
                    if s["weekday"] != day.weekday() or blocked:
                        continue
                    exception = next(
                        (
                            e
                            for e in timetable.get("exceptions", [])
                            if e.get("date") == day.isoformat()
                            and e.get("course") == s["course"]
                        ),
                        {},
                    )
                    if exception.get("cancelled"):
                        continue
                    left = datetime.combine(
                        day,
                        time.fromisoformat(exception.get("start", s["start"])),
                        zone,
                    )
                    right = datetime.combine(
                        day, time.fromisoformat(exception.get("end", s["end"])), zone
                    )
                    result.append(
                        {
                            "id": timetable["id"]
                            + ":"
                            + day.isoformat()
                            + ":"
                            + str(i),
                            "title": s["course"],
                            "course": s["course"],
                            "kind": "class",
                            "start": left.isoformat(),
                            "end": right.isoformat(),
                            "blocks_time": True,
                            "flexible": False,
                            "date": day.isoformat(),
                        }
                    )
                day += timedelta(days=1)
        for r in records:
            if (
                r.get("status") in ("cancelled", "complete", "deleted")
                or r.get("relevance") == "unrelated"
            ):
                continue
            if r["kind"] == "assignment":
                if (
                    r.get("due_date")
                    and r.get("relevance") == "applicable"
                    and start <= date.fromisoformat(r["due_date"]) <= end
                ):
                    result.append(
                        {
                            **r,
                            "date": r["due_date"],
                            "start": r.get("due_at"),
                            "blocks_time": False,
                            "due_marker": True,
                        }
                    )
            elif r["kind"] in ("calendar_item", "external_event", "event"):
                if r["kind"] == "event" and r.get("participation") not in (
                    "mandatory",
                    "confirmed",
                ):
                    continue
                day = (
                    instant(r["start"]).astimezone(zone).date()
                    if r.get("start")
                    else date.fromisoformat(r["date"])
                    if r.get("date")
                    else None
                )
                # Include intervals that begin before the query but continue into it.
                last = (
                    instant(r["end"]).astimezone(zone).date() if r.get("end") else day
                )
                if day and day <= end and last >= start:
                    result.append(
                        {
                            **r,
                            "date": day.isoformat(),
                            "blocks_time": bool(r.get("start") and r.get("end")),
                            "possible_busy": not bool(r.get("start") and r.get("end")),
                        }
                    )
        return sorted(result, key=lambda r: r.get("start") or r.get("date", ""))

    def conflicts(self, owner, start, end):
        entries = self.entries(owner, start, end)
        result = []
        for i, a in enumerate(entries):
            for b in entries[i + 1 :]:
                if a.get("due_marker") or b.get("due_marker"):
                    continue
                overlap = (
                    a.get("blocks_time")
                    and b.get("blocks_time")
                    and instant(a["start"]) < instant(b["end"])
                    and instant(b["start"]) < instant(a["end"])
                )
                possible = (a.get("possible_busy") or b.get("possible_busy")) and a[
                    "date"
                ] == b["date"]
                if overlap or possible:
                    result.append(
                        {
                            "a": a,
                            "b": b,
                            "severity": "overlap" if overlap else "possible",
                            "suggestion": "Move a flexible personal block, decline an optional event, or contact the organizer. Official times are fixed.",
                        }
                    )
        deadlines = {}
        for e in entries:
            if e.get("due_marker"):
                deadlines.setdefault(e["date"], []).append(e)
        result.extend(
            {
                "severity": "workload",
                "date": d,
                "items": items,
                "suggestion": "Several deadlines share this date; plan work blocks.",
            }
            for d, items in deadlines.items()
            if len(items) > 1
        )
        return result

    def free(self, owner, left, right, excluding):
        return not any(
            e["id"] != excluding
            and e.get("blocks_time")
            and instant(e["start"]) < right
            and left < instant(e["end"])
            for e in self.entries(owner, left.date(), right.date())
        )

    def propose(self, owner, record_id):
        item = self.store.get(owner, record_id)
        if item["kind"] != "calendar_item" or not item.get("flexible"):
            raise ValueError("Only flexible personal blocks may move")
        original = instant(item["start"])
        duration = instant(item["end"]) - original
        if duration <= timedelta(0) or duration > timedelta(hours=12):
            raise ValueError("Invalid work-block duration")
        for i in range(1, 7 * 48):
            left = original + timedelta(minutes=30 * i)
            right = left + duration
            if left.hour < 8 or right.hour >= 22:
                continue
            if self.free(owner, left, right, record_id):
                return self.store.put(
                    owner,
                    "proposal",
                    {
                        "record_id": record_id,
                        "basis_revision": item["revision"],
                        "start": left.isoformat(),
                        "end": right.isoformat(),
                        "status": "pending",
                        "explanation": "First available slot within the next week and daytime planning hours.",
                    },
                )
        raise ValueError("No available slot found; adjust your planning window")

    def approve(self, owner, proposal_id):
        p = self.store.get(owner, proposal_id)
        if p["kind"] != "proposal" or p["status"] != "pending":
            raise Conflict("Proposal is no longer pending")
        item = self.store.get(owner, p["record_id"])
        if item["revision"] != p["basis_revision"] or not self.free(
            owner, instant(p["start"]), instant(p["end"]), item["id"]
        ):
            raise Conflict("Availability changed; request a new proposal")
        self.store.patch(
            owner,
            item["id"],
            {"start": p["start"], "end": p["end"]},
            p["basis_revision"],
        )
        return self.store.patch(owner, proposal_id, {"status": "approved"})
