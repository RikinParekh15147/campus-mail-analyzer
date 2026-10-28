from pathlib import Path
import hashlib
import re
from .nlp import analyze, sentences
from .preprocessing import prepare_document, PREPROCESSING_VERSION
from .documents import read_document
from .candidates import (
    ANALYSIS_SCHEMA_VERSION, adapt_legacy_analysis, source_assertion,
    confirmed_origin, span_assertion,
)
from .reconciliation import align_date_times
from datetime import datetime, time, date, timezone
from zoneinfo import ZoneInfo

TERM = re.compile(
    r"\b(?:spring|summer|fall|autumn|winter)\s+20\d{2}\b"
    r"|\b20\d{2}\s+(?:spring|summer|fall|autumn|winter)\b"
    r"|\b(?:semester|sem)\s*(?:[1-9]|1[0-2])\s*[-/, ]\s*20\d{2}\b",
    re.I,
)
EVENT_NAME = re.compile(
    r"\b([A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){0,4} "
    r"(?:Workshop|Meeting|Seminar|Webinar|Exam))\b"
)
CANCEL_WORD = re.compile(r"\b(?:cancelled|canceled)\b", re.I)
ASSIGNMENT_NUMBER = re.compile(
    r"\b(?:assignment|homework|project)\s*[-#:]?\s*(\d+)\b", re.I,
)
CANCEL_NEGATION = re.compile(
    r"\b(?:not|never|no longer|isn't|wasn't|hasn't|haven't|won't|shouldn't)"
    r"\s+(?:be\s+|been\s+|being\s+)?$", re.I,
)
CANCEL_HEDGE = re.compile(
    r"\b(?:may|might|could|possibly|perhaps|pending|proposed|considering|if)\b"
    r".{0,30}\b(?:cancelled|canceled)\b", re.I,
)
CANCEL_BREAK = re.compile(
    r";|\b(?:but|while|whereas)\b"
    r"|,\s*(?:and\s+)?(?=(?:[A-Z]{2,5}[- ]?\d{3}\s+)?"
    r"(?:assignment|homework|project)\s*[-#:]?\s*\d+\b)"
    r"|,\s*(?:and\s+)?(?=[A-Z][A-Za-z ]{0,35}"
    r"(?:Workshop|Meeting|Seminar|Webinar|Exam)\b)", re.I,
)


def cancellation_clauses(context):
    """Keep contrastive and newly named items in separate local clauses."""
    return [part for _, _, part in cancellation_clause_spans(context)]


def cancellation_clause_spans(context, offset=0):
    """Return exact source offsets for the same clauses used by targeting."""
    boundaries = [0] + [m.end() for m in CANCEL_BREAK.finditer(context)]
    ends = [m.start() for m in CANCEL_BREAK.finditer(context)] + [len(context)]
    clauses = []
    for left, right in zip(boundaries, ends):
        fragment = context[left:right]
        leading = len(fragment) - len(fragment.lstrip())
        trailing = len(fragment.rstrip())
        if leading < trailing:
            start, end = offset + left + leading, offset + left + trailing
            clauses.append((start, end, context[left + leading:left + trailing]))
    return clauses


def cancellation_signal(context):
    """Return none, positive or ambiguous for local cancellation wording."""
    positive = negative = 0
    for match in CANCEL_WORD.finditer(context):
        prefix = context[max(0, match.start() - 30):match.start()]
        if CANCEL_NEGATION.search(prefix):
            negative += 1
        else:
            positive += 1
    if positive and negative:
        return "ambiguous"
    if positive and CANCEL_HEDGE.search(context):
        return "ambiguous"
    return "positive" if positive else "none"


def assignment_clause_matches(context, number, task_count):
    numbers = set(ASSIGNMENT_NUMBER.findall(context))
    return number in numbers if numbers else task_count == 1


def academic_term(subject, text):
    """Use only explicit season/semester plus year; never infer from import time."""
    terms = set()
    for match in TERM.finditer(subject + " " + text):
        words = match.group().casefold().replace(",", " ").replace("/", " ").replace("-", " ").split()
        if words[0].isdigit():
            words = [words[1], words[0]]
        if words[0] == "autumn":
            words[0] = "fall"
        if words[0] in ("sem", "semester"):
            words[0] = "semester"
        terms.add(" ".join(words))
    return (next(iter(terms)), False) if len(terms) == 1 else (None, len(terms) > 1)


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

    def occurrence_choice(self, owner, message, key, kind, candidates, question):
        """Return a reviewed target, 'create_separate', or None for pending review."""
        decision_key = key
        selected = message.get("occurrence_decisions", {}).get(key)
        if selected == "create_separate":
            return selected
        if selected:
            target = next((item for item in candidates if item["id"] == selected), None)
            if target is not None:
                return target
            # A stale choice cannot silently target a changed candidate set.
            key += ":stale"
        self.review(
            owner,
            key,
            question,
            message["id"],
            "occurrence",
            [f"existing_{i + 1}" for i in range(len(candidates))]
            + ["create_separate"],
            context={
                "message_id": message["id"],
                "decision_key": decision_key,
                "candidate_kind": kind,
                "candidate_ids": [item["id"] for item in candidates],
                "text": "\n".join(
                    f"{i + 1}. {item.get('title', kind)} — "
                    f"{item.get('due_date') or item.get('date') or 'date unknown'}"
                    for i, item in enumerate(candidates)
                ),
            },
        )
        return None

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

    def field_stale(self, old, field, source_at):
        if not old:
            return False
        previous = old.get("field_source_at", {}).get(field)
        if previous is None:
            previous = (
                old.get("source_sent_at") or old.get("latest_source_at")
                if old.get("field_source_at")
                else old.get("latest_source_at")
            )
        return self.source_rank(source_at) < self.source_rank(previous)

    def apply_entity_overrides(self, owner, old, payload, message_id):
        """Preserve confirmed edits and surface each differing source assertion."""
        if not old:
            return payload
        for field, value in old.get("overrides", {}).items():
            candidate = payload.get(field)
            if candidate != value:
                self.review(
                    owner,
                    "changed:" + old["id"] + ":" + field + ":" + str(candidate),
                    "New notice conflicts with your " + field,
                    old["id"], field,
                    [value, candidate] if candidate is not None else [value],
                    context={"candidate": candidate, "message_id": message_id},
                )
            payload = align_date_times(payload, field, value)
            if field not in ("date", "due_date"):
                payload[field] = value
            payload.setdefault("field_evidence", {})[field] = confirmed_origin(
                old["id"], value)
        return payload

    def fact(self, owner, field, value, evidence_id, confirmed=False,
             source_span=None):
        source_evidence = None
        if source_span is not None:
            message = self.store.get(owner, evidence_id)
            if message["kind"] != "message":
                raise ValueError("Profile evidence source must be a message")
            source_evidence = span_assertion(
                evidence_id, message["text"], "profile." + field, value,
                source_span[0], source_span[1])
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
        field_evidence = source_evidence
        if old and old.get("status") == "confirmed" and old.get("value") == value:
            field_evidence = old.get("field_evidence", {}).get("value") or source_evidence
        if field_evidence is None and old and old.get("value") == value:
            field_evidence = old.get("field_evidence", {}).get("value")
        if field_evidence is None:
            field_evidence = {
                "origin": "confirmed_input" if confirmed else "legacy_unverified",
                "source_id": evidence_id, "value": value,
            }
        result = self.store.put(
            owner,
            "profile_fact",
            {
                "field": field,
                "value": value,
                "status": status,
                "evidence_ids": evidence,
                "field_evidence": {"value": field_evidence},
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
        if (payload.get("text", "").strip()
            and payload.get("status") not in
                ("needs_text_review", "needs_ocr_or_review", "unreadable")):
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

    def attach(self, owner, data, filename, parent_id=None, occurrence_id=None,
               charset=None):
        parent = self.store.get(owner, parent_id) if parent_id else {}
        if parent and parent["kind"] != "message":
            raise ValueError("Attachment parent must be a message")
        result = read_document(data, filename, charset)
        if occurrence_id and parent_id:
            legacy_key = "attachment:" + result["sha256"] + ":parent:" + parent_id
            if any(m["source_key"] == legacy_key
                   and m.get("legacy_provider_identity_unresolved")
                   for m in self.store.list(owner, "message")):
                raise ValueError("Legacy attachment provider identity needs review")
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
            subject = parent.get("subject", filename)
            occurrence_key = (
                "attachment:" + record["sha256"]
                + (":parent:" + parent_id if parent_id else ":standalone")
                + (":item:" + str(occurrence_id) if occurrence_id else "")
            )
            old_child = next(
                (m for m in self.store.list(owner, "message")
                 if m["source_key"] == occurrence_key),
                None,
            )
            retained = (
                {k: old_child[k] for k in ("date_corrections", "occurrence_decisions")
                 if k in old_child}
                if old_child and old_child.get("text") == result["text"]
                else {}
            )
            child = self.store.put(
                owner,
                "message",
                {
                    "text": result["text"],
                    "subject": subject,
                    "source_type": "uploaded_attachment",
                    "source_filename": filename,
                    "source_charset": charset,
                    "source_locators": result.get("locators", []),
                    "attachment_occurrence_id": occurrence_id,
                    "parent_record_id": parent_id,
                    "sent_at": parent.get("sent_at"),
                    "timezone": parent.get("timezone"),
                    "relative_reference_trusted": parent.get(
                        "relative_reference_trusted",
                        not str(parent.get("source_key", "")).startswith("gmail:"),
                    ),
                    "thread_id": parent.get("thread_id"),
                    "attachment_resource_ids": [record["id"]],
                    **retained,
                },
                occurrence_key,
            )
            self.process(owner, child)
            record = self.store.patch(
                owner, record["id"],
                {
                    "analysis_message_id": child["id"],
                    "analysis_message_ids": sorted(set(
                        record.get("analysis_message_ids", [])
                        + ([record["analysis_message_id"]]
                           if record.get("analysis_message_id") else [])
                        + [child["id"]]
                    )),
                },
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
        if message.get("text_quality_status") == "needs_text_review":
            result = {"category": "unknown", "dates": [], "subject_dates": [],
                      "actions": [], "resources": [], "courses": [],
                      "reason": "Source text decoding needs review",
                      "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
                      "preprocessing_version": PREPROCESSING_VERSION}
            self.store.patch(owner, message["id"], {"analysis": result})
            self.review(owner, "text-quality:" + message["id"],
                        "Check this message's decoded text before using its dates or actions",
                        message["id"], context={"message_id": message["id"]})
            return result
        prepared = prepare_document(
            message.get("subject", ""), full,
            source_type="attachment" if message.get("source_type") == "uploaded_attachment"
            else "body",
        )
        text = prepared.body.canonical
        if not text.strip():
            result = {"category": "unknown", "dates": [], "subject_dates": [],
                      "actions": [], "resources": [], "courses": [],
                      "reason": "No authored email text outside quoted history",
                      "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
                      "preprocessing_version": prepared.version}
            self.store.patch(owner, message["id"], {"analysis": result})
            return result
        subject = message.get("subject", "")
        trusted = message.get("relative_reference_trusted")
        if trusted is None:
            parent_id = message.get("parent_record_id")
            parent = self.store.get(owner, parent_id) if parent_id else {}
            origin = parent or message
            trusted = origin.get("relative_reference_trusted")
            if trusted is None:
                trusted = not str(origin.get("source_key", "")).startswith("gmail:")
        relative_anchor = message.get("sent_at") if trusted is True else None
        result = analyze(text, subject, relative_anchor, self.model_path,
                         message.get("timezone"))
        if self.model_path and result["actions"]:
            action_model = (
                Path(self.model_path).parent.parent / "actionability/classifier.joblib"
            )
            try:
                from .nlp import load_pipeline

                action_pipeline = load_pipeline(str(action_model), None)
                labels = action_pipeline.predict([a["text"] for a in result["actions"]])
                if not all(str(label) in ("True", "False") for label in labels):
                    raise ValueError("Actionability model returned an invalid label")
                for action, label in zip(result["actions"], labels):
                    action["trained_actionability"] = str(label)
                    action["method"] = "local_rules_with_trained_actionability"
                identity = getattr(action_pipeline, "_campus_bundle_identity", None)
                if identity:
                    result["actionability_model_revision"] = identity["revision"]
                    result["actionability_model_bundle_id"] = identity["bundle"]
            except Exception:
                result["actionability_model_health"] = "invalid_or_unavailable"
        for extracted in result["dates"] + result["subject_dates"]:
            correction_key = (
                "subject:" + str(extracted["start"])
                if extracted.get("field") == "subject"
                else str(extracted["start"])
            )
            correction = message.get("date_corrections", {}).get(
                correction_key
            )
            if correction:
                extracted.update(
                    normalized=correction["date"],
                    role=correction["role"],
                    needs_review=False,
                    reason=None,
                    correction_method="user_confirmed",
                )
        body_locators = list(message.get("source_locators", []))
        if message.get("source_type") == "uploaded_attachment":
            if not body_locators:
                for resource_id in message.get("attachment_resource_ids", []):
                    resource = self.store.get(owner, resource_id)
                    body_locators.extend(resource.get("locators", []))
        result = adapt_legacy_analysis(message["id"], full, subject, result,
                                       body_locators)
        for match in re.finditer(
            r"\b(?:your|my)\s+roll\s*(?:number|no\.?)\s*(?:is|:)?\s*([A-Za-z0-9-]{5,20})",
            text,
            re.I,
        ):
            self.fact(owner, "roll_number", match.group(1).upper(), message["id"],
                      source_span=match.span(1))
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
                self.fact(owner, field, match.group(1).strip(), message["id"],
                          source_span=match.span(1))
        for match in re.finditer(
            r"\b(?:you are|I am) enrolled in\s+([A-Z]{2,5}[- ]?\d{3})", text
        ):
            self.fact(owner, "enrollment:" + match.group(1), True, message["id"],
                      source_span=match.span(1))
        profile = self.profile(owner)
        for name in profile:
            if name.startswith("enrollment:"):
                code = name.split(":", 1)[1]
                if len(code) >= 3 and re.search(
                    r"(?<!\w)" + re.escape(code) + r"(?!\w)", subject + " " + text, re.I
                ):
                    result["courses"].append(code)
        result["courses"] = sorted(set(result["courses"]))
        term, term_ambiguous = academic_term(subject, text)
        if term_ambiguous:
            result["needs_review"] = True
            result["reason"] = "Multiple explicit academic terms need entity-level review"
            self.review(
                owner,
                "academic-term:" + message["id"],
                "This notice spans multiple terms; add or correct its items manually.",
                message["id"],
                context={"message_id": message["id"], "reason": result["reason"]},
            )
            self.store.patch(owner, message["id"], {"analysis": result})
            return result
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
        parent_id = message.get("parent_record_id")
        parent_message = self.store.get(owner, parent_id) if parent_id else {}
        unknown_context = (
            message.get("thread_id")
            or parent_message.get("thread_id")
            or parent_id
            or message["id"]
        )
        unknown_scope = "unknown@" + hashlib.sha256(
            str(unknown_context).encode()
        ).hexdigest()[:16]

        def assignment_scope(code):
            return code or unknown_scope

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
                key = (
                    assignment_scope(local_course)
                    + (":term:" + term.replace(" ", "_") if term else "")
                    + ":assignment:" + match[1]
                )
                spec = specs.setdefault(
                    key,
                    {
                        "course": local_course,
                        "number": match[1],
                        "academic_term": term,
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
                key = (
                    assignment_scope(course)
                    + (":term:" + term.replace(" ", "_") if term else "")
                    + ":assignment:" + number
                )
                specs[key] = {
                    "course": course,
                    "number": number,
                    "academic_term": term,
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
                assignment_scope(course)
                + (":term:" + term.replace(" ", "_") if term else "")
                + ":task:"
                + hashlib.sha256(title.lower().encode()).hexdigest()[:16]
            ] = {"course": course, "number": None, "academic_term": term,
                 "title": title, "spans": [(0, len(text))]}
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
            assignment_number = spec["number"]
            all_assignments = self.store.list(owner, "assignment")
            candidates = [
                x for x in all_assignments
                if x.get("course") == course
                and (
                    x.get("assignment_number") == assignment_number
                    if assignment_number is not None
                    else x.get("title") == spec["title"]
                )
                and (not term or x.get("academic_term") in (None, term))
            ]
            # Old records predate assignment_number. Their numbered source key
            # is enough to consider them candidates, never enough to merge.
            if assignment_number is not None:
                candidates.extend(
                    x for x in all_assignments
                    if x not in candidates and x.get("course") == course
                    and x["source_key"].endswith(":assignment:" + assignment_number)
                    and (not term or x.get("academic_term") in (None, term))
                )
            assignment_update = any(
                assignment_clause_matches(context, assignment_number, len(task_keys))
                and (re.search(r"\b(?:rescheduled|extended|updated|corrected)\b",
                               context, re.I)
                     or cancellation_signal(context) != "none")
                for left, right in spec["spans"]
                for context in cancellation_clauses(text[left:right])
            )
            if (
                course is None and message.get("thread_id") and candidates
                and not assignment_update
                and all(x.get("source_thread_id")
                        and x["source_thread_id"] != message["thread_id"]
                        for x in candidates)
            ):
                candidates = []
            old = next((x for x in candidates if x["source_key"] == itemkey), None)
            if old is None:
                same_evidence = [
                    x for x in candidates if message["id"] in x.get("evidence_ids", [])
                ]
                if len(same_evidence) == 1:
                    old = same_evidence[0]
            if old is None and message.get("thread_id"):
                same_thread = [
                    x for x in candidates
                    if x.get("source_thread_id") == message["thread_id"]
                ]
                if len(same_thread) == 1:
                    old = same_thread[0]
            thread_conflict = bool(
                old and message.get("thread_id") and old.get("source_thread_id")
                and message["thread_id"] != old["source_thread_id"]
            )
            year_conflict = bool(
                old and message.get("sent_at") and old.get("source_sent_at")
                and not term and message["sent_at"][:4] != old["source_sent_at"][:4]
            )
            term_conflict = bool(
                old and (
                    (not term and old.get("academic_term"))
                    or (term and old.get("academic_term") is None
                        and message["id"] not in old.get("evidence_ids", []))
                )
            )
            legacy_identity_conflict = bool(
                old and "assignment_number" not in old
                and message["id"] not in old.get("evidence_ids", [])
            )
            target_key = itemkey
            if (
                (old is None and candidates) or thread_conflict or year_conflict
                or term_conflict or legacy_identity_conflict
            ):
                choice_key = "assignment-match:" + message["id"] + ":" + itemkey
                choice = self.occurrence_choice(
                    owner, message, choice_key, "assignment", candidates,
                    "Which assignment occurrence does this notice refer to?",
                )
                if choice is None:
                    continue
                if choice == "create_separate":
                    old = None
                    if any(x["source_key"] == itemkey for x in all_assignments):
                        target_key = itemkey + ":source@" + hashlib.sha256(
                            message["id"].encode()
                        ).hexdigest()[:12]
                        old = next(
                            (x for x in all_assignments
                             if x["source_key"] == target_key), None,
                        )
                else:
                    old = choice
            elif old:
                target_key = old["source_key"]
            cancellation_targeted = False
            cancellation_ambiguous = False
            cancellation_evidence = None
            for left, right in spec["spans"]:
                for clause_start, clause_end, context in cancellation_clause_spans(
                    text[left:right], left
                ):
                    signal = cancellation_signal(context)
                    if signal == "none":
                        continue
                    mentioned_numbers = set(ASSIGNMENT_NUMBER.findall(context))
                    if mentioned_numbers and assignment_number not in mentioned_numbers:
                        continue
                    bare_number = bool(re.search(r"\b(?:and|,)\s*\d+\b", context, re.I))
                    if signal == "ambiguous" or bare_number or len(mentioned_numbers) > 1:
                        cancellation_ambiguous = True
                    elif mentioned_numbers == {assignment_number} and assignment_number:
                        cancellation_targeted = True
                        cancellation_evidence = span_assertion(
                            message["id"], full, "assignment.status", "cancelled",
                            clause_start, clause_end)
                    elif (len(task_keys) == 1 and not mentioned_numbers
                          and re.search(r"\b(?:assignment|homework|project)\b",
                                        context, re.I)
                          and (assignment_number is not None or old is not None)):
                        cancellation_targeted = True
                        cancellation_evidence = span_assertion(
                            message["id"], full, "assignment.status", "cancelled",
                            clause_start, clause_end)
                    else:
                        cancellation_ambiguous = True
            dates = [
                d
                for d in result["dates"]
                if d["normalized"]
                and d["role"] == "assignment_deadline"
                and any(left <= d["start"] < right for left, right in spec["spans"])
            ]
            if not dates and len(task_keys) == 1:
                subject_candidates = [
                    d for d in result["subject_dates"]
                    if d["normalized"] and d["role"] == "assignment_deadline"
                    and not d["needs_review"]
                ]
                if len(subject_candidates) == 1:
                    dates = subject_candidates
            due_date = dates[-1]["normalized"] if dates else (old or {}).get("due_date")
            due_at = (old or {}).get("due_at") if not dates else None
            if dates and dates[-1].get("field") != "subject":
                date_sentence = next(
                    (s for s in sentences(text)
                     if s.start() <= dates[-1]["start"] < s.end()), None
                )
                after = [
                    t
                    for t in result["times"]
                    if dates[-1]["end"] <= t["start"] < dates[-1]["end"] + 65
                    and date_sentence is not None
                    and t["end"] <= date_sentence.end()
                ]
                before = [
                    t for t in result["times"]
                    if 0 <= dates[-1]["start"] - t["end"] <= 65
                    and date_sentence is not None
                    and t["start"] >= date_sentence.start()
                    and re.fullmatch(
                        r"[\s,;]*(?:on|at|by)?[\s,;]*",
                        text[t["end"] : dates[-1]["start"]], re.I,
                    )
                ]
                nearby = after + before
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
            date_stale = bool(dates and self.field_stale(old, "due_date", source_at))
            previous_date_at = (old or {}).get("field_source_at", {}).get("due_date")
            date_tie = bool(
                old and dates and due_date != old.get("due_date")
                and previous_date_at
                and self.source_rank(source_at) == self.source_rank(previous_date_at)
                and (old or {}).get("field_source_id", {}).get("due_date") != message["id"]
            )
            if date_tie:
                self.review(
                    owner, "field-conflict:" + old["id"] + ":due_date:" + message["id"],
                    "Two sources at the same time disagree on this assignment deadline",
                    old["id"], "due_date", [old.get("due_date"), due_date],
                    context={"candidate": due_date, "message_id": message["id"]},
                )
            field_source_at = dict((old or {}).get("field_source_at", {}))
            field_source_id = dict((old or {}).get("field_source_id", {}))
            field_evidence = dict((old or {}).get("field_evidence", {}))
            if old is None:
                field_source_at["status"] = source_at
            if dates and not date_stale and not date_tie:
                field_source_at["due_date"] = source_at
                field_source_id["due_date"] = message["id"]
                selected = dates[-1]
                group = "subject_dates" if selected.get("field") == "subject" else "dates"
                field_evidence["due_date"] = source_assertion(
                    result, group, "normalized", selected)
            if cancellation_targeted and not self.field_stale(old, "status", source_at):
                field_source_at["status"] = source_at
                field_source_id["status"] = message["id"]
                field_evidence["status"] = cancellation_evidence
            if date_stale or date_tie:
                due_date = old.get("due_date")
                due_at = old.get("due_at")
            payload = {
                **(old or {}),
                "title": (course + " " if course else "")
                + "Assignment "
                + itemkey.rsplit(":", 1)[1],
                "description": text,
                "course": course,
                "assignment_number": assignment_number,
                "academic_term": (old or {}).get("academic_term") or term,
                "source_sent_at": (old or {}).get("source_sent_at")
                or message.get("sent_at"),
                "source_thread_id": (old or {}).get("source_thread_id")
                or message.get("thread_id"),
                "due_date": due_date,
                "field_source_at": field_source_at,
                "field_source_id": field_source_id,
                "field_evidence": field_evidence,
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
                if cancellation_targeted and not self.field_stale(old, "status", source_at)
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
                    description=old.get("description")
                )
            payload = self.apply_entity_overrides(owner, old, payload, message["id"])
            assignment = self.store.put(
                owner, "assignment", payload, old["source_key"] if old else target_key
            )
            if cancellation_ambiguous and not cancellation_targeted and not older:
                self.review(
                    owner,
                    "assignment-cancel:" + message["id"] + ":" + itemkey,
                    "Is this assignment cancelled?",
                    assignment["id"],
                    "status",
                    ["open", "cancelled"],
                    context={"message_id": message["id"], "candidate_key": itemkey},
                )
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
        fallback_event_name = False
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
            for clause_start, clause_end, context in cancellation_clause_spans(
                sentence.group(), sentence.start()
            ):
                event_names.extend((match.group(1), context, clause_start, clause_end)
                                   for match in EVENT_NAME.finditer(context))
        if not event_names and re.search(
            r"\b(meeting|workshop|seminar|webinar|exam|examination|event)\b",
            subject + " " + text,
            re.I,
        ):
            fallback_event_name = True
            event_names = [
                (
                    re.sub(r"^(?:Re:|Fwd:)\s*", "", subject, flags=re.I)
                    or "Academic event",
                    text,
                    0,
                    len(text),
                )
            ]
        for title, context, context_start, context_end in event_names:
            local = analyze(context, reference_date=relative_anchor,
                            source_timezone=message.get("timezone"))
            cancellation_kind = cancellation_signal(context)
            cancellation_seen = cancellation_kind != "none"
            event_cancelled = (
                cancellation_kind == "positive"
                and not fallback_event_name
                and sum(1 for _, related_context, _, _ in event_names
                        if related_context == context) == 1
            )
            subject_date_used = False
            event_date_candidate = next(
                (
                    d
                    for d in result["dates"]
                    if d["text"] in context
                    and d["role"] in ("event_start", "exam_date")
                    and d["normalized"]
                ),
                None,
            )
            if event_date_candidate is None and len(event_names) == 1:
                subject_candidates = [
                    d for d in result["subject_dates"]
                    if d["normalized"] and d["role"] in ("event_start", "exam_date")
                    and not d["needs_review"]
                ]
                if len(subject_candidates) == 1:
                    event_date_candidate = subject_candidates[0]
                    subject_date_used = True
            event_date = (event_date_candidate or {}).get("normalized")
            base = (
                (course or "")
                + (":term:" + term.replace(" ", "_") if term else "")
                + ":" + re.sub(r"^the\s+", "", title.lower().strip())
            )
            candidates = [
                e
                for e in self.store.list(owner, "event")
                if e.get("course") == course
                and e.get("title", "").casefold() == title.casefold()
                and (not term or e.get("academic_term") in (None, term))
            ]
            old = next(
                (e for e in candidates if message["id"] in e.get("evidence_ids", [])),
                None,
            )
            if old is None:
                old = next(
                    (e for e in candidates if event_date and e.get("date") == event_date),
                    None,
                )
            updating = bool(
                re.search(
                    r"\b(rescheduled|extended|updated|corrected)\b",
                    context,
                    re.I,
                )
                or cancellation_seen
            )
            if updating and len(candidates) > 1 and not (
                old and message["id"] in old.get("evidence_ids", [])
            ):
                same_thread = [
                    e for e in candidates
                    if message.get("thread_id")
                    and e.get("source_thread_id") == message["thread_id"]
                ]
                if len(same_thread) == 1:
                    old = same_thread[0]
                else:
                    old = None
            if old is None and len(candidates) == 1 and (updating or not event_date):
                candidate = candidates[0]
                old = candidate
            thread_conflict = bool(
                updating and old and message.get("thread_id")
                and old.get("source_thread_id")
                and message["thread_id"] != old["source_thread_id"]
            )
            term_missing_conflict = bool(updating and old and not term and old.get("academic_term"))
            year_conflict = bool(
                updating and old and not term and message.get("sent_at")
                and old.get("source_sent_at")
                and message["sent_at"][:4] != old["source_sent_at"][:4]
            )
            legacy_identity_conflict = bool(
                updating and old and "academic_term" not in old
                and message["id"] not in old.get("evidence_ids", [])
            )
            create_separate = False
            if (
                updating and old is None
                or thread_conflict or term_missing_conflict or year_conflict
                or legacy_identity_conflict
                or updating and old and term and old.get("academic_term") is None
            ):
                choice_key = "event-match:" + message["id"] + ":" + base
                choice = self.occurrence_choice(
                    owner, message, choice_key, "event", candidates,
                    "Which event occurrence does this update refer to?",
                )
                if choice is None:
                    continue
                if choice == "create_separate":
                    old = None
                    create_separate = True
                else:
                    old = choice
            elif old:
                pending_key = "event-match:" + message["id"] + ":" + base
                pending = next(
                    (q for q in self.store.list(owner, "review")
                     if q["source_key"] == pending_key and q["status"] == "open"),
                    None,
                )
                if pending:
                    self.store.patch(owner, pending["id"], {
                        "status": "answered", "answer": "resolved_by_replay",
                        "resolved_record_id": old["id"],
                    })
            key = (
                old["source_key"]
                if old
                else base
                + ":"
                + (event_date or message.get("thread_id") or message["id"])
            )
            if create_separate:
                key += ":source@" + hashlib.sha256(message["id"].encode()).hexdigest()[:12]
                old = next(
                    (e for e in candidates if e["source_key"] == key), None
                )
            older = bool(
                old
                and self.source_rank(source_at)
                < self.source_rank(old.get("latest_source_at"))
            )
            date_asserted = bool(event_date)
            date_stale = bool(date_asserted and self.field_stale(old, "date", source_at))
            previous_date_at = (old or {}).get("field_source_at", {}).get("date")
            date_tie = bool(
                old and date_asserted and event_date != old.get("date")
                and previous_date_at
                and self.source_rank(source_at) == self.source_rank(previous_date_at)
                and (old or {}).get("field_source_id", {}).get("date") != message["id"]
            )
            if date_tie:
                self.review(
                    owner, "field-conflict:" + old["id"] + ":date:" + message["id"],
                    "Two sources at the same time disagree on this event date",
                    old["id"], "date", [old.get("date"), event_date],
                    context={"candidate": event_date, "message_id": message["id"]},
                )
            field_source_at = dict((old or {}).get("field_source_at", {}))
            field_source_id = dict((old or {}).get("field_source_id", {}))
            field_evidence = dict((old or {}).get("field_evidence", {}))
            if old is None:
                field_source_at["status"] = source_at
            if date_asserted and not date_stale and not date_tie:
                field_source_at["date"] = source_at
                field_source_id["date"] = message["id"]
                group = "subject_dates" if subject_date_used else "dates"
                field_evidence["date"] = source_assertion(
                    result, group, "normalized", event_date_candidate)
            status_stale = self.field_stale(old, "status", source_at)
            if event_cancelled and not status_stale:
                field_source_at["status"] = source_at
                field_source_id["status"] = message["id"]
                field_evidence["status"] = span_assertion(
                    message["id"], full, "event.status", "cancelled",
                    context_start, context_end)
            if date_stale or date_tie:
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
                if local["times"] and not subject_date_used:
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
            if date_stale or date_tie:
                timing = {
                    "start": old.get("start"), "end": old.get("end")
                }
            payload = {
                    **(old or {}),
                    **timing,
                    "title": title,
                    "course": course,
                    "academic_term": (old or {}).get("academic_term") or term,
                    "source_sent_at": (old or {}).get("source_sent_at")
                    or message.get("sent_at"),
                    "source_thread_id": (old or {}).get("source_thread_id")
                    or message.get("thread_id"),
                    "date": event_date or (old or {}).get("date"),
                    "date_precision": (
                        old.get("date_precision", "date") if old and (date_stale or date_tie or not date_asserted)
                        else "datetime" if timing.get("start") else "date"
                    ),
                    "field_source_at": field_source_at,
                    "field_source_id": field_source_id,
                    "field_evidence": field_evidence,
                    "description": context,
                    "importance": (old or {}).get(
                        "importance", "high" if compulsory else "medium"
                    ),
                    "relevance": relevance if course else "potentially_relevant",
                    "participation": (old or {}).get(
                        "participation", "mandatory" if compulsory else "unknown"
                    ),
                    "status": (
                        "cancelled" if event_cancelled and not status_stale
                        else (old or {}).get("status", "active")
                    ),
                    "resource_ids": sorted(
                        set((old or {}).get("resource_ids", []) + resource_ids)
                    ),
                    "evidence_ids": sorted(
                        set((old or {}).get("evidence_ids", []) + [message["id"]])
                    ),
                }
            payload = self.apply_entity_overrides(owner, old, payload, message["id"])
            event = self.store.put(owner, "event", payload, key)
            event = self.store.patch(
                owner,
                event["id"],
                {
                    "base_key": base,
                    "latest_source_at": old.get("latest_source_at")
                    if older
                    else source_at,
                    **(
                        {
                            k: old.get(k)
                            for k in ("description",)
                        }
                        if older
                        else {}
                    ),
                },
            )
            if cancellation_seen and not event_cancelled and not older:
                self.review(
                    owner,
                    "event-cancel:" + message["id"] + ":" + title,
                    "Is this event cancelled?",
                    event["id"],
                    "status",
                    ["active", "cancelled"],
                    context={"message_id": message["id"], "candidate_title": title},
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
        for d in result["dates"] + result["subject_dates"]:
            if d["needs_review"]:
                key = (
                    "subject:" + str(d["start"])
                    if d.get("field") == "subject"
                    else str(d["start"])
                )
                self.review(
                    owner,
                    "date:" + message["id"] + ":" + key,
                    "Clarify date: " + d["text"],
                    message["id"],
                    "date",
                    context=d,
                )
        for item in (result["date_ranges"] + result["subject_date_ranges"]
                     + result["temporal_warnings"] + result["subject_temporal_warnings"]):
            field = item.get("field", "text")
            cue_hash = hashlib.sha256(item["text"].encode()).hexdigest()[:12]
            self.review(
                owner,
                f"temporal:{message['id']}:{field}:{item['start']}:{item['end']}:{cue_hash}",
                "Clarify temporal expression: " + item["text"],
                message["id"],
                context={**item, "field": field},
            )
        self.store.patch(owner, message["id"], {"analysis": result})
        return result
