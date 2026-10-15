from pathlib import Path
import hashlib
import re
from .nlp import analyze, sentences
from .documents import read_document
from datetime import datetime, time, date, timezone
from zoneinfo import ZoneInfo


class Engine:
    def __init__(self, store, model_path=None, blob_dir=None):
        self.store, self.model_path = store, model_path
        self.blob_dir = Path(blob_dir) if blob_dir else None

    def review(
        self,
        owner,
        key,
        question,
        record_id=None,
        field=None,
        choices=None,
        context=None,
    ):
        old = next(
            (r for r in self.store.list(owner, "review") if r["source_key"] == key),
            None,
        )
        if old and old.get("status") in ("answered", "deferred"):
            return old
        return self.store.put(
            owner,
            "review",
            {
                "question": question,
                "record_id": record_id,
                "field": field,
                "choices": choices or [],
                "context": context or {},
                "status": "open",
            },
            key,
        )

    def profile(self, owner):
        return {
            f["field"]: f["value"]
            for f in self.store.list(owner, "profile_fact")
            if f["status"] in ("confirmed", "corroborated")
        }

    @staticmethod
    def source_rank(stamp):
        try:
            value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            return (
                value.replace(tzinfo=timezone.utc).timestamp()
                if value.tzinfo is None
                else value.timestamp()
            )
        except (ValueError, TypeError, AttributeError):
            return 0

    def fact(self, owner, field, value, evidence_id, confirmed=False):
        old = next(
            (f for f in self.store.list(owner, "profile_fact") if f["field"] == field),
            None,
        )
        if (
            old
            and old["value"] != value
            and old["status"] == "confirmed"
            and not confirmed
        ):
            self.review(
                owner,
                "profile-conflict:" + field + ":" + value,
                "New evidence conflicts with your " + field,
                old["id"],
                "value",
                context={"candidate": value, "message_id": evidence_id},
            )
            return old
        evidence = sorted(
            set(
                (old.get("evidence_ids", []) if old and old["value"] == value else [])
                + [evidence_id]
            )
        )
        status = (
            "confirmed"
            if confirmed
            else "corroborated"
            if len(evidence) >= 2
            else "inferred"
        )
        if old and old["status"] == "confirmed" and old["value"] == value:
            status = "confirmed"
        result = self.store.put(
            owner,
            "profile_fact",
            {
                "field": field,
                "value": value,
                "status": status,
                "evidence_ids": evidence,
            },
            field,
        )
        if status == "inferred":
            self.review(
                owner,
                "profile:" + field,
                "Confirm your " + field.replace("_", " "),
                result["id"],
                "value",
                [value],
                {"message_id": evidence_id},
            )
        return result

    def resource(self, owner, payload, key):
        if payload.get("text", "").strip():
            analysis = analyze(payload["text"])
            text_hash = hashlib.sha256(
                " ".join(payload["text"].casefold().split()).encode()
            ).hexdigest()
            payload = {
                **payload,
                "text_sha256": text_hash,
                "content_analysis": analysis,
                "importance": "high"
                if any(d["role"].endswith("deadline") for d in analysis["dates"])
                or any(a["status"] == "required" for a in analysis["actions"])
                else "medium",
                "redundancy": "unique",
            }
            duplicate = next(
                (
                    r
                    for r in self.store.list(owner, "resource")
                    if r["source_key"] != key and r.get("text_sha256") == text_hash
                ),
                None,
            )
            if duplicate:
                payload.update(duplicate_of=duplicate["id"], redundancy="same_text")
        old = next(
            (r for r in self.store.list(owner, "resource") if r["source_key"] == key),
            None,
        )
        if old:
            payload = {
                **old,
                **payload,
                "message_ids": sorted(
                    set(old.get("message_ids", []) + payload.get("message_ids", []))
                ),
            }
            if (
                old.get("filename")
                and payload.get("filename")
                and old["filename"] != payload["filename"]
            ):
                payload["redundancy"] = "exact_duplicate"
        return self.store.put(owner, "resource", payload, key)

    def attach(self, owner, data, filename, parent_id=None):
        result = read_document(data, filename)
        path = None
        if self.blob_dir:
            directory = self.blob_dir / owner
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / result["sha256"]
            path.write_bytes(data)
        result.update(
            path=str(path) if path else None,
            message_ids=[parent_id] if parent_id else [],
        )
        record = self.resource(owner, result, "blob:" + result["sha256"])
        if result["status"] == "readable":
            subject = (
                self.store.get(owner, parent_id).get("subject", filename)
                if parent_id
                else filename
            )
            parent = self.store.get(owner, parent_id) if parent_id else {}
            child = self.store.put(
                owner,
                "message",
                {
                    "text": result["text"],
                    "subject": subject,
                    "source_type": "uploaded_attachment",
                    "parent_record_id": parent_id,
                    "sent_at": parent.get("sent_at") or parent.get("created_at"),
                    "attachment_resource_ids": [record["id"]],
                },
                "attachment:" + record["sha256"],
            )
            self.process(owner, child)
            record = self.store.patch(
                owner, record["id"], {"analysis_message_id": child["id"]}
            )
        if parent_id:
            parent = self.store.get(owner, parent_id)
            self.store.patch(
                owner,
                parent_id,
                {
                    "attachment_resource_ids": sorted(
                        set(parent.get("attachment_resource_ids", []) + [record["id"]])
                    )
                },
            )
            if parent.get("text", "").strip():
                self.process(owner, self.store.get(owner, parent_id))
        return record

    def process(self, owner, message):
        if message["owner_id"] != owner:
            raise ValueError("Message owner mismatch")
        full = message.get("text", "")
        text = re.split(
            r"\n(?:On .{5,180}wrote:|[- ]*Original Message|From:)", full, maxsplit=1
        )[0]
        subject = message.get("subject", "")
        result = analyze(text, subject, message.get("sent_at"), self.model_path)
        if self.model_path and result["actions"]:
            action_model = (
                Path(self.model_path).parent.parent / "actionability/classifier.joblib"
            )
            if action_model.is_file():
                from .nlp import load_pipeline

                labels = load_pipeline(
                    str(action_model), action_model.stat().st_mtime_ns
                ).predict([a["text"] for a in result["actions"]])
                for action, label in zip(result["actions"], labels):
                    action["trained_actionability"] = str(label)
                    action["method"] = "local_rules_with_trained_actionability"
        for extracted in result["dates"]:
            correction = message.get("date_corrections", {}).get(
                str(extracted["start"])
            )
            if correction:
                extracted.update(
                    normalized=correction["date"],
                    role=correction["role"],
                    needs_review=False,
                    reason=None,
                )
        for match in re.finditer(
            r"\b(?:your|my)\s+roll\s*(?:number|no\.?)\s*(?:is|:)?\s*([A-Za-z0-9-]{5,20})",
            text,
            re.I,
        ):
            self.fact(owner, "roll_number", match.group(1).upper(), message["id"])
        for field, pattern in [
            ("program", r"\b(?:your|my) program(?:me)?\s*(?:is|:)\s*([^\n.]{2,70})"),
            (
                "semester",
                r"\b(?:your|my|current) semester\s*(?:is|:)?\s*([1-9][0-2]?)\b",
            ),
            ("batch", r"\b(?:your|my) batch\s*(?:is|:)?\s*([A-Za-z0-9-]{1,20})"),
            ("university", r"\b(?:your|my) university\s*(?:is|:)\s*([^\n.]{2,100})"),
            (
                "field",
                r"\b(?:your|my) (?:department|branch)\s*(?:is|:)\s*([^\n.]{2,70})",
            ),
        ]:
            for match in re.finditer(pattern, text, re.I):
                self.fact(owner, field, match.group(1).strip(), message["id"])
        for match in re.finditer(
            r"\b(?:you are|I am) enrolled in\s+([A-Z]{2,5}[- ]?\d{3})", text
        ):
            self.fact(owner, "enrollment:" + match.group(1), True, message["id"])
        profile = self.profile(owner)
        for name in profile:
            if name.startswith("enrollment:"):
                code = name.split(":", 1)[1]
                if len(code) >= 3 and re.search(
                    r"(?<!\w)" + re.escape(code) + r"(?!\w)", subject + " " + text, re.I
                ):
                    result["courses"].append(code)
        result["courses"] = sorted(set(result["courses"]))
        course = result["courses"][0] if len(result["courses"]) == 1 else None
        course_known = bool(course and profile.get("enrollment:" + course))
        unrelated = bool(
            course
            and (
                profile.get("enrollment:" + course) is False
                or profile.get("enrollment_complete")
                and "enrollment:" + course not in profile
            )
        )
        relevance = (
            "unrelated" if unrelated else "applicable" if course_known else "uncertain"
        )
        source_at = message.get("sent_at") or message["created_at"]
        for code in result["courses"]:
            self.store.put(
                owner,
                "course",
                {
                    "title": code,
                    "enrolled": bool(self.profile(owner).get("enrollment:" + code)),
                },
                code,
            )
        specs = {}
        for sentence in sentences(text):
            for match in re.finditer(
                r"\b(?:assignment|homework|project)\s*[-#:]?\s*(\d+)\b",
                sentence.group(),
                re.I,
            ):
                codes = [
                    c
                    for c in result["courses"]
                    if re.search(
                        r"(?<!\w)" + re.escape(c) + r"(?!\w)", sentence.group(), re.I
                    )
                ]
                local_course = codes[0] if len(codes) == 1 else course
                key = (local_course or "unknown") + ":assignment:" + match[1]
                spec = specs.setdefault(
                    key,
                    {
                        "course": local_course,
                        "title": (local_course + " " if local_course else "")
                        + "Assignment "
                        + match[1],
                        "spans": [],
                    },
                )
                spec["spans"].append((sentence.start(), sentence.end()))
        if not specs:
            for number in dict.fromkeys(
                re.findall(
                    r"\b(?:assignment|homework|project)\s*[-#:]?\s*(\d+)\b",
                    subject,
                    re.I,
                )
            ):
                specs[(course or "unknown") + ":assignment:" + number] = {
                    "course": course,
                    "title": (course + " " if course else "") + "Assignment " + number,
                    "spans": [(0, len(text))],
                }
        if (
            not specs
            and re.search(
                r"\b(assignments?|homework|project submission|practical file)\b",
                subject + " " + text,
                re.I,
            )
            and not re.search(r"\bno assignment\b", text, re.I)
        ):
            title = (
                re.sub(r"^(?:Re:|Fwd:)\s*", "", subject, flags=re.I)
                or "Assignment to review"
            )
            specs[
                (course or "unknown")
                + ":task:"
                + hashlib.sha256(title.lower().encode()).hexdigest()[:16]
            ] = {"course": course, "title": title, "spans": [(0, len(text))]}
        task_keys = list(specs)
        resource_ids = list(message.get("attachment_resource_ids", []))
        for resource in result["resources"]:
            linked_keys = (
                task_keys
                if len(task_keys) == 1
                else [
                    key
                    for key, spec in specs.items()
                    if any(
                        left <= resource["start"] < right
                        for left, right in spec["spans"]
                    )
                ]
            )
            record = self.resource(
                owner,
                {
                    **resource,
                    "title": resource["url"].split("/")[-1] or resource["role"],
                    "course": specs[linked_keys[0]]["course"]
                    if len(linked_keys) == 1
                    else course,
                    "item_keys": linked_keys,
                    "message_ids": [message["id"]],
                    "sanitized_placeholder": bool(
                        message.get("sanitized") and "/RESOURCE_" in resource["url"]
                    ),
                },
                "url:" + hashlib.sha256(resource["url"].encode()).hexdigest(),
            )
            resource_ids.append(record["id"])
        for itemkey in task_keys:
            spec = specs[itemkey]
            course = spec["course"]
            course_known = bool(course and profile.get("enrollment:" + course))
            unrelated = bool(
                course
                and (
                    profile.get("enrollment:" + course) is False
                    or profile.get("enrollment_complete")
                    and "enrollment:" + course not in profile
                )
            )
            relevance = (
                "unrelated"
                if unrelated
                else "applicable"
                if course_known
                else "uncertain"
            )
            resources = (resource_ids if len(task_keys) == 1 else []) + [
                r["id"]
                for r in self.store.list(owner, "resource")
                if itemkey in r.get("item_keys", [])
            ]
            old = next(
                (
                    x
                    for x in self.store.list(owner, "assignment")
                    if x["source_key"] == itemkey
                ),
                None,
            )
            dates = [
                d
                for d in result["dates"]
                if d["normalized"]
                and d["role"] == "assignment_deadline"
                and any(left <= d["start"] < right for left, right in spec["spans"])
            ]
            due_date = dates[-1]["normalized"] if dates else (old or {}).get("due_date")
            due_at = (old or {}).get("due_at") if not dates else None
            if dates:
                nearby = [
                    t
                    for t in result["times"]
                    if dates[-1]["end"] <= t["start"] < dates[-1]["end"] + 65
                ]
                if len(nearby) == 1:
                    zone = ZoneInfo(
                        next(iter(self.store.list(owner, "settings")), {}).get(
                            "timezone", "Asia/Kolkata"
                        )
                    )
                    due_at = datetime.combine(
                        date.fromisoformat(due_date),
                        time.fromisoformat(nearby[0]["time"]),
                        zone,
                    ).isoformat()
            older = bool(
                old
                and self.source_rank(source_at)
                < self.source_rank(old.get("latest_source_at"))
            )
            if older:
                due_date = old.get("due_date")
                due_at = old.get("due_at")
            payload = {
                **(old or {}),
                "title": (course + " " if course else "")
                + "Assignment "
                + itemkey.rsplit(":", 1)[1],
                "description": text,
                "course": course,
                "due_date": due_date,
                "date_precision": "date",
                "importance": (old or {}).get("importance", "high"),
                "relevance": "applicable" if course_known else "uncertain",
                "participation": "mandatory" if course_known else "unknown",
                "resource_ids": sorted(
                    set((old or {}).get("resource_ids", []) + resources)
                ),
                "evidence_ids": sorted(
                    set((old or {}).get("evidence_ids", []) + [message["id"]])
                ),
                "status": "cancelled"
                if re.search(r"\bcancelled\b", text, re.I)
                else (old or {}).get("status", "open"),
            }
            payload.update(
                relevance=relevance,
                latest_source_at=old.get("latest_source_at") if older else source_at,
            )
            payload.update(
                due_at=due_at, date_precision="datetime" if due_at else "date"
            )
            payload["title"] = spec["title"]
            if older:
                payload.update(
                    description=old.get("description"), status=old.get("status", "open")
                )
            for field, value in (old or {}).get("overrides", {}).items():
                if payload.get(field) != value:
                    self.review(
                        owner,
                        "changed:"
                        + old["id"]
                        + ":"
                        + field
                        + ":"
                        + str(payload.get(field)),
                        "New notice conflicts with your " + field,
                        old["id"],
                        field,
                        context={
                            "candidate": payload.get(field),
                            "message_id": message["id"],
                        },
                    )
                payload[field] = value
            assignment = self.store.put(owner, "assignment", payload, itemkey)
            if not course_known and not unrelated:
                self.review(
                    owner,
                    "enrolled:" + assignment["id"],
                    "Is this assignment for a course you take?",
                    assignment["id"],
                    "relevance",
                    ["applicable", "unrelated"],
                )
            else:
                for question in self.store.list(owner, "review"):
                    if (
                        question.get("record_id") == assignment["id"]
                        and question.get("field") == "relevance"
                        and question.get("status") in ("open", "deferred")
                    ):
                        self.store.patch(
                            owner,
                            question["id"],
                            {"status": "resolved_by_context", "answer": relevance},
                        )
        event_names = []
        course = result["courses"][0] if len(result["courses"]) == 1 else None
        course_known = bool(course and profile.get("enrollment:" + course))
        unrelated = bool(
            course
            and (
                profile.get("enrollment:" + course) is False
                or profile.get("enrollment_complete")
                and "enrollment:" + course not in profile
            )
        )
        for sentence in sentences(text):
            match = re.search(
                r"\b([A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){0,4} (?:Workshop|Meeting|Seminar|Webinar|Exam))\b",
                sentence.group(),
            )
            if match:
                event_names.append((match.group(1), sentence.group()))
        if not event_names and re.search(
            r"\b(meeting|workshop|seminar|webinar|exam|examination|event)\b",
            subject + " " + text,
            re.I,
        ):
            event_names = [
                (
                    re.sub(r"^(?:Re:|Fwd:)\s*", "", subject, flags=re.I)
                    or "Academic event",
                    text,
                )
            ]
        for title, context in event_names:
            local = analyze(context, reference_date=message.get("sent_at"))
            event_date = next(
                (
                    d["normalized"]
                    for d in result["dates"]
                    if d["text"] in context
                    and d["role"] in ("event_start", "exam_date")
                    and d["normalized"]
                ),
                None,
            )
            base = (course or "") + ":" + re.sub(r"^the\s+", "", title.lower().strip())
            candidates = [
                e
                for e in self.store.list(owner, "event")
                if e.get("base_key") == base or e["source_key"] == base
            ]
            old = next(
                (e for e in candidates if event_date and e.get("date") == event_date),
                None,
            )
            updating = bool(
                re.search(
                    r"\b(rescheduled|extended|updated|cancelled|corrected)\b",
                    context,
                    re.I,
                )
            )
            if old is None and len(candidates) == 1 and (updating or not event_date):
                old = candidates[0]
            if len(candidates) > 1 and updating and not event_date:
                self.review(
                    owner,
                    "event-match:" + message["id"],
                    "Which occurrence does this update refer to?",
                    context={"message_id": message["id"]},
                )
                continue
            key = (
                old["source_key"]
                if old
                else base
                + ":"
                + (event_date or message.get("thread_id") or message["id"])
            )
            older = bool(
                old
                and self.source_rank(source_at)
                < self.source_rank(old.get("latest_source_at"))
            )
            if older:
                event_date = old.get("date")
            compulsory = not unrelated and bool(
                re.search(
                    r"\b(compulsory|mandatory|required to attend)\b", context, re.I
                )
                or (course_known and re.search(r"exam", title, re.I))
            )
            timing = {}
            if event_date:
                timing = {"start": None, "end": None}
                zone = ZoneInfo(
                    next(iter(self.store.list(owner, "settings")), {}).get(
                        "timezone", "Asia/Kolkata"
                    )
                )
                if local["times"]:
                    left = datetime.combine(
                        date.fromisoformat(event_date),
                        time.fromisoformat(local["times"][0]["time"]),
                        zone,
                    )
                    timing["start"] = left.isoformat()
                    if len(local["times"]) == 2 and re.search(
                        r"to|until|[-–]",
                        context[local["times"][0]["end"] : local["times"][1]["start"]],
                    ):
                        right = datetime.combine(
                            date.fromisoformat(event_date),
                            time.fromisoformat(local["times"][1]["time"]),
                            zone,
                        )
                        if right > left:
                            timing["end"] = right.isoformat()
            event = self.store.put(
                owner,
                "event",
                {
                    **(old or {}),
                    **timing,
                    "title": title,
                    "course": course,
                    "date": event_date or (old or {}).get("date"),
                    "date_precision": "datetime" if timing.get("start") else "date",
                    "description": context,
                    "importance": (old or {}).get(
                        "importance", "high" if compulsory else "medium"
                    ),
                    "participation": (old or {}).get(
                        "participation", "mandatory" if compulsory else "unknown"
                    ),
                    "status": "cancelled"
                    if re.search(r"\bcancelled\b", context, re.I)
                    else "active",
                    "resource_ids": sorted(
                        set((old or {}).get("resource_ids", []) + resource_ids)
                    ),
                    "evidence_ids": sorted(
                        set((old or {}).get("evidence_ids", []) + [message["id"]])
                    ),
                },
                key,
            )
            event = self.store.patch(
                owner,
                event["id"],
                {
                    "base_key": base,
                    "relevance": relevance if course else "potentially_relevant",
                    "latest_source_at": old.get("latest_source_at")
                    if older
                    else source_at,
                    **(
                        {
                            k: old.get(k)
                            for k in (
                                "start",
                                "end",
                                "date_precision",
                                "description",
                                "status",
                            )
                        }
                        if older
                        else {}
                    ),
                },
            )
            if not compulsory and not unrelated and event["participation"] == "unknown":
                self.review(
                    owner,
                    "participate:" + event["id"],
                    "Are you interested in " + title + "?",
                    event["id"],
                    "participation",
                    ["confirmed", "interested", "declined"],
                )
        for d in result["dates"]:
            if d["needs_review"]:
                self.review(
                    owner,
                    "date:" + message["id"] + ":" + str(d["start"]),
                    "Clarify date: " + d["text"],
                    message["id"],
                    "date",
                    context=d,
                )
        self.store.patch(owner, message["id"], {"analysis": result})
        return result
