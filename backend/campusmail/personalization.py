from datetime import date
import re
from .store import Conflict
from .reconciliation import align_date_times
from .candidates import confirmed_origin

ALLOWED = {
    "importance": {"high", "medium", "low"},
    "relevance": {"applicable", "potentially_relevant", "unrelated", "uncertain"},
    "participation": {"confirmed", "interested", "declined", "unknown", "mandatory"},
    "status": {"open", "complete", "active", "cancelled", "resolved"},
}


class Personalizer:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def topic_for(item):
        if item.get("course") or item.get("topic"):
            return item.get("course") or item["topic"]
        generic = {
            "workshop",
            "meeting",
            "seminar",
            "webinar",
            "event",
            "session",
            "the",
            "a",
            "on",
            "for",
            "to",
            "and",
            "introduction",
            "advanced",
            "basic",
        }
        words = sorted(
            {
                w
                for w in re.findall(r"[a-z]{3,}", item.get("title", "").lower())
                if w not in generic
            }
        )
        return " ".join(words[:4])

    def feedback(self, owner, record_id, field, value, expected_revision=None):
        record = self.store.get(owner, record_id)
        if expected_revision is not None and record["revision"] != expected_revision:
            raise Conflict("Item changed since review")
        if field not in ALLOWED and field not in ("due_date", "date", "value"):
            raise ValueError("Unsupported feedback field")
        if field in ALLOWED and value not in ALLOWED[field]:
            raise ValueError("Invalid " + field)
        if field in ("due_date", "date"):
            date.fromisoformat(value)
        if field == "value" and record["kind"] != "profile_fact":
            raise ValueError("Only profile facts accept a value")
        if field in record.get("overrides", {}) and record["overrides"][field] == value:
            return record
        old_value = record.get(field)
        date_changes = (
            align_date_times(record, field, value)
            if field in ("due_date", "date") else {field: value}
        )
        updated = self.store.patch(
            owner,
            record_id,
            {
                **date_changes,
                "overrides": {**record.get("overrides", {}), field: value},
                "field_evidence": {
                    **record.get("field_evidence", {}),
                    field: confirmed_origin(record_id, value),
                },
                **({"status": "confirmed"} if record["kind"] == "profile_fact" else {}),
                **(
                    {"state": "resolved"}
                    if record["kind"] == "reply_request"
                    and field == "status"
                    and value == "resolved"
                    else {}
                ),
            },
            expected_revision,
        )
        topic = self.topic_for(record)
        event = self.store.put(
            owner,
            "feedback",
            {
                "record_id": record_id,
                "field": field,
                "old_value": old_value,
                "value": value,
                "topic": topic,
                "weight": 1 if old_value == value else 2,
                "scope": "personal_only",
            },
        )
        if field == "importance" and topic:
            key = field + ":" + topic
            old = next(
                (
                    p
                    for p in self.store.list(owner, "preference")
                    if p["source_key"] == key
                ),
                None,
            )
            weights = dict((old or {}).get("weights", {}))
            weights[value] = weights.get(value, 0) + event["weight"]
            self.store.put(
                owner,
                "preference",
                {
                    "field": field,
                    "topic": topic,
                    "weights": weights,
                    "examples": (old or {}).get("examples", 0) + 1,
                },
                key,
            )
        for question in self.store.list(owner, "review"):
            if (
                question.get("record_id") == record_id
                and question.get("field") == field
                and question.get("status") in ("open", "deferred")
            ):
                self.store.patch(
                    owner, question["id"], {"status": "answered", "answer": value}
                )
        return updated

    def apply(self, owner, item):
        if item.get("participation") == "mandatory" or "importance" in item.get(
            "overrides", {}
        ):
            return item
        topic = self.topic_for(item)
        preferences = [
            p
            for p in self.store.list(owner, "preference")
            if p["field"] == "importance" and p["topic"] == topic and p["examples"] >= 2
        ]
        if preferences:
            preference = preferences[0]
            importance = max(preference["weights"], key=preference["weights"].get)
            return {
                **item,
                "importance": importance,
                "importance_reason": "Your explicit preferences",
                "preference_id": preference["id"],
            }
        return item

    def answer(self, owner, question_id, value, defer=False):
        question = self.store.get(owner, question_id)
        if question["kind"] != "review":
            raise ValueError("Not a review question")
        if defer:
            return self.store.patch(owner, question_id, {"status": "deferred"})
        if question.get("record_id"):
            field = question.get("field")
            record = self.store.get(owner, question["record_id"])
            if field == "occurrence" and record["kind"] == "message":
                choices = question.get("choices", [])
                if value not in choices:
                    raise ValueError("Select one listed occurrence choice")
                context = question.get("context", {})
                candidates = context.get("candidate_ids", [])
                if value == "create_separate":
                    selected = value
                else:
                    index = choices.index(value)
                    if index >= len(candidates):
                        raise ValueError("Occurrence choice has no target")
                    target = self.store.get(owner, candidates[index])
                    if target["kind"] != context.get("candidate_kind"):
                        raise ValueError("Occurrence target kind changed")
                    selected = target["id"]
                decision_key = context.get("decision_key")
                if not isinstance(decision_key, str) or not decision_key:
                    raise ValueError("Occurrence decision key is missing")
                self.store.patch(
                    owner,
                    record["id"],
                    {"occurrence_decisions": {
                        **record.get("occurrence_decisions", {}),
                        decision_key: selected,
                    }},
                )
                self.store.put(
                    owner, "feedback",
                    {"record_id": record["id"], "field": "occurrence",
                     "value": selected, "scope": "personal_only", "weight": 2},
                )
                return self.store.patch(
                    owner, question_id, {"status": "answered", "answer": value}
                )
            if field == "date" and record["kind"] == "message":
                correction = (
                    value
                    if isinstance(value, dict)
                    else {
                        "date": value,
                        "role": question.get("context", {}).get("role", "unknown"),
                    }
                )
                date.fromisoformat(correction["date"])
                if correction.get("role") not in (
                    "event_start",
                    "event_end",
                    "exam_date",
                    "assignment_deadline",
                    "registration_deadline",
                    "publication_date",
                    "other",
                ):
                    raise ValueError("Select the date role")
                start = str(question["context"]["start"])
                if question["context"].get("field") == "subject":
                    start = "subject:" + start
                self.store.patch(
                    owner,
                    record["id"],
                    {
                        "date_corrections": {
                            **record.get("date_corrections", {}),
                            start: correction,
                        }
                    },
                )
                self.store.put(
                    owner,
                    "feedback",
                    {
                        "record_id": record["id"],
                        "field": "date",
                        "value": correction,
                        "scope": "personal_only",
                        "weight": 2,
                    },
                )
                return self.store.patch(
                    owner, question_id, {"status": "answered", "answer": correction}
                )
            if field is None:
                self.store.put(
                    owner,
                    "feedback",
                    {
                        "record_id": question["id"],
                        "field": "review",
                        "value": value,
                        "scope": "personal_only",
                        "weight": 1,
                    },
                )
                return self.store.patch(
                    owner, question_id, {"status": "answered", "answer": value}
                )
            if field == "date":
                field = (
                    "due_date"
                    if self.store.get(owner, question["record_id"])["kind"]
                    == "assignment"
                    else "date"
                )
            self.feedback(owner, question["record_id"], field, value)
        if not question.get("record_id"):
            self.store.put(
                owner,
                "feedback",
                {
                    "record_id": question_id,
                    "field": "review",
                    "value": value,
                    "scope": "personal_only",
                    "weight": 1,
                },
            )
        return self.store.patch(
            owner, question_id, {"status": "answered", "answer": value}
        )

    def reset(self, owner):
        for kind in ("preference", "feedback"):
            for record in self.store.list(owner, kind):
                self.store.delete(owner, record["id"])
