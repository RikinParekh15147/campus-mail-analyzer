import re
from .engine import Engine


class Conversations:
    def __init__(self, store):
        self.store = store

    def analyze(self, owner, thread_id):
        messages = sorted(
            (
                m
                for m in self.store.list(owner, "message")
                if m.get("thread_id") == thread_id
            ),
            key=lambda m: m.get("sent_at") or m["created_at"],
        )
        requests = []
        for i, message in enumerate(messages):
            text = re.split(r"\nOn .{5,180}wrote:", message["text"], maxsplit=1)[0]
            candidates = []
            for match in re.finditer(r"[^.!?\n]+[.!?]?", text):
                sentence = match.group().strip()
                if re.search(
                    r"\b(?:can|could|would) you\b|\bplease (?:send|reply|confirm|submit|review|provide)\b|\bI need you to\b",
                    sentence,
                    re.I,
                ):
                    candidates.append((match, sentence))
            for match, sentence in candidates:
                if message.get("cc_only"):
                    continue
                state = "waiting_for_other" if message.get("is_self") else "needs_reply"
                keywords = set(
                    re.findall(
                        r"\b(?:report|attendance|budget|file|form|schedule|proposal|marks|details)\b",
                        sentence.lower(),
                    )
                )
                for response in messages[i + 1 :]:
                    if bool(response.get("is_self")) == bool(message.get("is_self")):
                        continue
                    reply = re.split(
                        r"\nOn .{5,180}wrote:", response["text"], maxsplit=1
                    )[0].lower()
                    if (
                        keywords
                        and any(re.search(r"\b" + k + r"\b", reply) for k in keywords)
                        and not re.search(
                            r"\b(?:will send|later|cannot|not yet)\b", reply
                        )
                    ):
                        state = "resolved"
                    elif len(candidates) == 1 and re.fullmatch(
                        r"\s*(?:yes|confirmed|done|thank you|thanks)[.!\s]*", reply
                    ):
                        state = "resolved"
                key = message["id"] + ":" + str(match.start())
                old = next(
                    (
                        r
                        for r in self.store.list(owner, "reply_request")
                        if r["source_key"] == key
                    ),
                    None,
                )
                if old and old.get("overrides", {}).get("status") == "resolved":
                    state = "resolved"
                record = self.store.put(
                    owner,
                    "reply_request",
                    {
                        **(old or {}),
                        "title": sentence,
                        "state": state,
                        "thread_id": thread_id,
                        "message_id": message["id"],
                        "source_link": message.get("source_link"),
                        "evidence": {
                            "start": match.start(),
                            "end": match.end(),
                            "text": match.group(),
                        },
                        "needs_review": False,
                    },
                    key,
                )
                requests.append(record)
        return requests


class Grades:
    def __init__(self, store):
        self.store = store

    def extract(self, owner, text, course, assessment, source_id):
        engine = Engine(self.store)
        identity = next(
            (
                f
                for f in self.store.list(owner, "profile_fact")
                if f["field"] == "roll_number" and f["status"] == "confirmed"
            ),
            None,
        )
        roll = identity["value"] if identity else None
        if not roll:
            engine.review(
                owner,
                "marks-identity:" + source_id,
                "Confirm your roll number before extracting marks",
                context={"message_id": source_id},
            )
            return []
        matching = [
            line
            for line in text.splitlines()
            if re.search(
                r"(?<![A-Za-z0-9_])" + re.escape(roll) + r"(?![A-Za-z0-9_])", line, re.I
            )
        ]
        if len(matching) != 1:
            engine.review(
                owner,
                "marks-match:" + source_id,
                "Result row is missing or ambiguous",
                context={"message_id": source_id},
            )
            return []
        row = matching[0]
        tail = re.split(re.escape(roll), row, flags=re.I, maxsplit=1)[1]
        absent = re.search(r"\b(absent|withheld)\b", tail, re.I)
        scores = list(
            re.finditer(r"(?<!\d)(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?!\d)", tail)
        )
        if len(scores) > 1 or absent and scores:
            engine.review(
                owner,
                "marks-columns:" + source_id,
                "Multiple assessments in one row; confirm which columns apply",
                context={"message_id": source_id},
            )
            return []
        score = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?!\d)", tail)
        if not score:
            # Plain tabular row, requiring both earned and maximum values.
            score = re.search(
                r"^\s*[\t,| ]\s*(\d+(?:\.\d+)?)\s*[\t,|]\s*(\d+(?:\.\d+)?)(?:\s|$)",
                tail,
            )
        if not absent and not score:
            engine.review(
                owner,
                "marks-layout:" + source_id,
                "Confirm result columns and maximum marks",
                context={"message_id": source_id},
            )
            return []
        earned = float(score[1]) if score and not absent else None
        maximum = float(score[2]) if score and not absent else None
        if maximum is not None and (maximum <= 0 or earned > maximum):
            engine.review(
                owner,
                "marks-range:" + source_id,
                "Marks are outside the supported range",
                context={"message_id": source_id},
            )
            return []
        key = course + ":" + assessment
        old = next(
            (g for g in self.store.list(owner, "grade") if g["source_key"] == key), None
        )
        if (
            old
            and old.get("earned") != earned
            and not re.search(r"\b(corrected|revised|updated)\b", text, re.I)
        ):
            engine.review(
                owner,
                "marks-change:" + source_id,
                "New marks differ; confirm whether this is a correction",
                old["id"],
                context={"candidate": earned, "message_id": source_id},
            )
            return [old]
        return [
            self.store.put(
                owner,
                "grade",
                {
                    "title": course + " · " + assessment,
                    "course": course,
                    "assessment": assessment,
                    "roll_number": roll,
                    "earned": earned,
                    "maximum": maximum,
                    "result_status": absent[1].lower() if absent else "published",
                    "evidence": {"source_id": source_id, "text": row},
                    "evidence_ids": sorted(
                        set((old or {}).get("evidence_ids", []) + [source_id])
                    ),
                },
                key,
            )
        ]

    def total(self, owner, course):
        scheme = next(
            (
                s
                for s in self.store.list(owner, "grading_scheme")
                if s["course"] == course
            ),
            None,
        )
        if not scheme:
            return None
        grades = {
            g["assessment"]: g
            for g in self.store.list(owner, "grade")
            if g["course"] == course
        }
        weights = scheme["weights"]
        if abs(sum(weights.values()) - 1) > 0.00001 or any(
            v < 0 for v in weights.values()
        ):
            raise ValueError("Grading weights must sum to one")
        if any(
            a not in grades or grades[a]["earned"] is None or not grades[a]["maximum"]
            for a in weights
        ):
            return None
        return round(
            sum(
                grades[a]["earned"] / grades[a]["maximum"] * w * 100
                for a, w in weights.items()
            ),
            2,
        )
