"""Conservative local analysis; every extraction references original text."""

from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
import re
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MONTHS = {
    name: i
    for i, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        1,
    )
}
MONTH_PATTERN = "|".join(name + "|" + name[:3] for name in MONTHS)
DATE = re.compile(
    r"\b(?:20\d{2}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+(?:"
    + MONTH_PATTERN
    + r")(?:\s+\d{4})?|(?:"
    + MONTH_PATTERN
    + r")\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|tomorrow|today)\b",
    re.I,
)
TIME = re.compile(
    r"\b(?:(\d{1,2})(?::(\d{2}))?\s*(AM|PM)|([01]?\d|2[0-3]):([0-5]\d))\b",
    re.I,
)
DATE_RANGE_PATTERNS = (
    re.compile(
        rf"\b(?P<month>{MONTH_PATTERN})\s+(?P<first>\d{{1,2}})(?:st|nd|rd|th)?"
        rf"\s*(?:-|–|—|to|through)\s*(?P<last>\d{{1,2}})(?:st|nd|rd|th)?"
        r"(?:,?\s+(?P<year>20\d{2}))?\b", re.I,
    ),
    re.compile(
        rf"\b(?P<first>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|—|to|through)"
        rf"\s*(?P<last>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{MONTH_PATTERN})"
        r"(?:\s+(?P<year>20\d{2}))?\b", re.I,
    ),
)
UNSUPPORTED_RELATIVE = re.compile(
    r"\b(?:(?:next|this|coming|by|on|before|until)\s+)?"
    r"(?:mon(?:day)?|tues?(?:day)?|wed(?:nesday)?|thu(?:rs(?:day)?)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b"
    r"|\b(?:next|this|coming)\s+(?:week|weekend|month)\b"
    r"|\b(?:within|in)\s+\d+\s+(?:days?|weeks?)\b"
    r"|\b(?:eod|cob|end of (?:the )?(?:day|week))\b", re.I,
)
AMBIGUOUS_TIME_RANGE = re.compile(
    r"\b\d{1,2}(?::[0-5]\d)?\s*[-–—]\s*\d{1,2}(?::[0-5]\d)?\s*(?:AM|PM)\b",
    re.I,
)
RULES = {
    "assignments": r"\b(assignment|homework|project submission)\b",
    "examinations": r"\b(exam|examination|marks|result|viva|midsem)\b",
    "scholarships": r"\b(scholarship|fellowship|financial aid)\b",
    "placements": r"\b(placement|internship|recruitment|job opportunity)\b",
    "course_materials": r"\b(lecture notes|slides|syllabus|course material)\b",
    "workshops_events": r"\b(workshop|webinar|meeting|seminar|event|hackathon)\b",
    "administration": r"\b(fees|holiday|administration|circular|timetable|registration)\b",
}


@lru_cache(maxsize=4)
def load_pipeline(path, modified):
    import joblib

    return joblib.load(path)


@dataclass(frozen=True)
class TextSpan:
    source: str
    left: int
    right: int

    def start(self):
        return self.left

    def end(self):
        return self.right

    def group(self):
        return self.source[self.left : self.right]


ABBREVIATIONS = {
    "dr", "prof", "mr", "mrs", "ms", "fig", "no", "vs", "etc", "dept",
}
CLAUSE_BREAK = re.compile(r";|,\s*but\b|\bbut\b", re.I)
URL = re.compile(r"https?://[^\s<>\"']+", re.I)


def sentences(text):
    """Return source-aligned sentence spans without splitting URLs or decimals."""
    urls = []
    for match in URL.finditer(text):
        end = match.end()
        while end > match.start() and text[end - 1] in ".,;!?":
            end -= 1
        urls.append((match.start(), end))
    result = []
    left = 0
    url_index = 0
    for index, char in enumerate(text):
        while url_index < len(urls) and index >= urls[url_index][1]:
            url_index += 1
        in_url = (
            url_index < len(urls)
            and urls[url_index][0] <= index < urls[url_index][1]
        )
        boundary = char == "\n"
        if char in ".!?" and not in_url:
            followed_by_space = index + 1 == len(text) or text[index + 1].isspace()
            if followed_by_space:
                if char == ".":
                    prefix = text[max(left, index - 10) : index + 1]
                    word = re.search(r"([A-Za-z]+)\.$", prefix)
                    abbreviation = bool(
                        (word and word[1].lower() in ABBREVIATIONS)
                        or re.search(r"(?:e\.g|i\.e)\.$", prefix, re.I)
                        or re.search(r"(?:[A-Z]\.){2,}$", prefix)
                    )
                    boundary = not abbreviation
                else:
                    boundary = True
        if boundary:
            span = TextSpan(text, left, index if char == "\n" else index + 1)
            if span.group().strip():
                result.append(span)
            left = index + 1
    if left < len(text):
        span = TextSpan(text, left, len(text))
        if span.group().strip():
            result.append(span)
    return result


def clauses(sentence):
    """Split contrasting obligations while retaining canonical body offsets."""
    result = []
    left = sentence.start()
    url_ranges = [(match.start(), match.end()) for match in URL.finditer(sentence.group())]
    for match in CLAUSE_BREAK.finditer(sentence.group()):
        if any(start <= match.start() < end for start, end in url_ranges):
            continue
        right = sentence.start() + match.start()
        span = TextSpan(sentence.source, left, right)
        if span.group().strip():
            result.append(span)
        left = sentence.start() + match.end()
    span = TextSpan(sentence.source, left, sentence.end())
    if span.group().strip():
        result.append(span)
    return result


def _date_ranges(text):
    """Collect explicit same-month ranges and quarantine ambiguous paired dates."""
    ranges = []
    occupied = []
    for pattern in DATE_RANGE_PATTERNS:
        for match in pattern.finditer(text):
            if any(start < match.end() and match.start() < end for start, end in occupied):
                continue
            start_date = end_date = None
            reason = "Date range needs endpoint-to-entity review"
            year = match.group("year")
            if year is None:
                reason = "Date range needs an explicit year"
            else:
                try:
                    month = next(value for name, value in MONTHS.items()
                                 if name.lower().startswith(match.group("month").lower()))
                    first = datetime(int(year), month, int(match.group("first"))).date()
                    last = datetime(int(year), month, int(match.group("last"))).date()
                    if last < first:
                        reason = "Date range end precedes start"
                    else:
                        start_date, end_date = first.isoformat(), last.isoformat()
                except (ValueError, StopIteration):
                    reason = "Invalid date range"
            ranges.append({"text": match.group(), "start": match.start(),
                           "end": match.end(), "start_date": start_date,
                           "end_date": end_date, "needs_review": True,
                           "reason": reason})
            occupied.append((match.start(), match.end()))
    candidates = [match for match in DATE.finditer(text)
                  if not any(start < match.end() and match.start() < end
                             for start, end in occupied)]
    spans = sentences(text)
    for first, second in zip(candidates, candidates[1:]):
        if any(start <= first.start() < end or start <= second.start() < end
               for start, end in occupied):
            continue
        sentence = next((span for span in spans
                         if span.start() <= first.start() < second.end() <= span.end()), None)
        if sentence is None:
            continue
        connector = text[first.end():second.start()].strip().lower()
        between = "between" in text[max(sentence.start(), first.start() - 20):first.start()].lower()
        if connector in {"-", "–", "—", "to", "through"} or (connector == "and" and between):
            ranges.append({"text": text[first.start():second.end()],
                           "start": first.start(), "end": second.end(),
                           "start_date": None, "end_date": None,
                           "needs_review": True,
                           "reason": "Cross-format date range needs review"})
            occupied.append((first.start(), second.end()))
    return sorted(ranges, key=lambda row: row["start"]), occupied


def analyze(text, subject="", reference_date=None, model_path=None, source_timezone=None):
    if not text.strip():
        raise ValueError("Notice text is empty")
    if isinstance(reference_date, str):
        try:
            reference_date = datetime.fromisoformat(
                reference_date.replace("Z", "+00:00")
            )
        except ValueError:
            reference_date = None
    invalid_source_timezone = False
    if source_timezone is not None:
        try:
            zone = ZoneInfo(source_timezone)
            reference_date = (
                reference_date.astimezone(zone)
                if isinstance(reference_date, datetime)
                and reference_date.tzinfo is not None
                and reference_date.utcoffset() is not None
                else None
            )
        except (ZoneInfoNotFoundError, TypeError, ValueError):
            reference_date = None
            invalid_source_timezone = True
    category = next(
        (k for k, v in RULES.items() if re.search(v, subject + " " + text, re.I)),
        "nonacademic_other",
    )
    method = "local_rules"
    if model_path and Path(model_path).is_file():
        model = load_pipeline(str(model_path), Path(model_path).stat().st_mtime_ns)
        category, method = (
            str(model.predict([subject + " " + text])[0]),
            "self_trained_pipeline",
        )
    result = {
        "category": category,
        "classification_method": method,
        "dates": [],
        "date_ranges": [],
        "subject_dates": [],
        "subject_date_ranges": [],
        "times": [],
        "temporal_warnings": [],
        "subject_temporal_warnings": [],
        "actions": [],
        "resources": [],
        "courses": [],
        "needs_review": False,
    }
    result["date_ranges"], range_spans = _date_ranges(text)
    ambiguous_times = list(AMBIGUOUS_TIME_RANGE.finditer(text))
    for match in ambiguous_times:
        result["temporal_warnings"].append({
            "text": match.group(), "start": match.start(), "end": match.end(),
            "reason": "Time range needs explicit endpoint meridiems",
        })
    for match in UNSUPPORTED_RELATIVE.finditer(text):
        result["temporal_warnings"].append({
            "text": match.group(), "start": match.start(), "end": match.end(),
            "reason": "Unsupported relative date cue",
        })
    for m in TIME.finditer(text):
        if any(match.start() < m.end() and m.start() < match.end()
               for match in ambiguous_times):
            continue
        if m[3]:
            hour = int(m[1])
            minute = int(m[2] or 0)
            if not 1 <= hour <= 12 or minute > 59:
                continue
            hour = hour % 12 + (12 if m[3].lower() == "pm" else 0)
        else:
            hour, minute = int(m[4]), int(m[5])
        result["times"].append(
            {"text": m.group(), "start": m.start(), "end": m.end(),
             "time": f"{hour:02}:{minute:02}:00"}
        )
    for match in DATE.finditer(text):
        if any(start < match.end() and match.start() < end
               for start, end in range_spans):
            continue
        raw = match.group()
        normalized = None
        reason = None
        try:
            if raw.lower() in ("today", "tomorrow"):
                if invalid_source_timezone:
                    reason = "Unknown source timezone"
                elif (
                    not isinstance(reference_date, datetime)
                    or reference_date.tzinfo is None
                    or reference_date.utcoffset() is None
                ):
                    reason = "Relative date needs a timezone-aware source date"
                else:
                    normalized = (
                        (reference_date + timedelta(days=raw.lower() == "tomorrow"))
                        .date()
                        .isoformat()
                    )
            elif re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw):
                normalized = datetime.fromisoformat(raw).date().isoformat()
            elif "/" in raw or "-" in raw:
                day, month, year = map(int, re.split(r"[/\-]", raw))
                if day <= 12 and month <= 12:
                    reason = "Ambiguous numeric date order"
                elif year < 100:
                    reason = "Two-digit year needs review"
                else:
                    normalized = datetime(year, month, day).date().isoformat()
            else:
                parts = raw.replace(",", " ").split()
                month_first = parts[0][0].isalpha()
                day = int(re.sub(r"\D", "", parts[1 if month_first else 0]))
                month = next(
                    i
                    for n, i in MONTHS.items()
                    if n.lower().startswith(parts[0 if month_first else 1].lower())
                )
                if len(parts) == 2:
                    reason = "Missing year"
                else:
                    normalized = datetime(int(parts[2]), month, day).date().isoformat()
        except (ValueError, StopIteration):
            reason = "Invalid or unsupported date"
        sentence = next(
            (s for s in sentences(text) if s.start() <= match.start() < s.end()), None
        )
        prefix = text[
            sentence.start()
            if sentence
            else max(0, match.start() - 100) : match.start()
        ].lower()
        cues = []
        for role, pattern in [
            (
                "registration_deadline",
                r"registration.{0,25}(?:close|deadline|last date)|register by",
            ),
            (
                "assignment_deadline",
                r"submit(?:ted)?.{0,40}\bby|submission.{0,20}(?:deadline|due)|deadline(?: extended to)?|due(?: on| by)?|last date",
            ),
            ("exam_date", r"exam(?:ination)?.{0,30}(?:on|held)"),
            (
                "event_start",
                r"held on|conducted on|scheduled (?:on|for)|meet on|starts? on",
            ),
        ]:
            cues.extend((m.end(), role) for m in re.finditer(pattern, prefix))
        role = max(cues)[1] if cues else "unknown"
        result["dates"].append(
            {
                "text": raw,
                "start": match.start(),
                "end": match.end(),
                "normalized": normalized,
                "precision": "date",
                "role": role,
                "needs_review": bool(reason) or role == "unknown",
                "reason": reason
                or ("Date role unclear" if role == "unknown" else None),
            }
        )
    for span in sentences(text):
        local_times = [item for item in result["times"]
                       if span.start() <= item["start"] < span.end()]
        has_date = any(span.start() <= item["start"] < span.end()
                       for item in result["dates"] + result["date_ranges"])
        if (local_times and not has_date
            and re.search(r"\b(?:deadline|due|by|meet at|starts? at|held at)\b",
                          span.group(), re.I)):
            for item in local_times:
                result["temporal_warnings"].append({
                    "text": item["text"], "start": item["start"], "end": item["end"],
                    "reason": "Time has no calendar date",
                })
    for sentence in sentences(text):
        for clause in clauses(sentence):
            raw = clause.group()
            lower = raw.lower()
            if re.search(
                r"\b(must|should|please|register|submit|apply|bring|upload|complete)\b",
                lower,
            ) and not re.search(
                r"\b(do not|must not|already|has closed|submitted|completed|no need)\b",
                lower,
            ):
                result["actions"].append(
                    {
                        "text": raw,
                        "start": clause.start(),
                        "end": clause.end(),
                        "status": "required"
                        if re.search(r"\b(must|required|submit by)\b", lower)
                        else "optional_or_uncertain",
                    }
                )
    for m in re.finditer(r'https?://[^\s<>"\)]+', text):
        url = m.group().rstrip(".,;")
        context = text[max(0, m.start() - 70) : m.start()].lower()
        role = (
            "meeting"
            if re.search(r"meet\.google|zoom\.", url)
            else "submission"
            if "submit" in context
            else "registration"
            if "register" in context
            else "reference"
        )
        result["resources"].append(
            {
                "url": url,
                "role": role,
                "start": m.start(),
                "end": m.start() + len(url),
                "drive_link_only": "drive.google.com" in url
                or "docs.google.com" in url,
            }
        )
    result["courses"] = sorted(
        set(re.findall(r"\b[A-Z]{2,5}[- ]?\d{3}\b", subject + " " + text))
    )
    if subject.strip():
        # Reuse the same bounded parser while preserving the subject's own
        # offsets. The recursive call has an empty subject and stops here.
        subject_result = analyze(subject, "", reference_date,
                                 source_timezone=source_timezone)
        result["subject_dates"] = [
            {**candidate, "field": "subject"}
            for candidate in subject_result["dates"]
        ]
        result["subject_date_ranges"] = [
            {**candidate, "field": "subject"}
            for candidate in subject_result["date_ranges"]
        ]
        result["subject_temporal_warnings"] = [
            {**candidate, "field": "subject"}
            for candidate in subject_result["temporal_warnings"]
        ]
    result["needs_review"] = any(
        x["needs_review"] for x in result["dates"] + result["subject_dates"]
    ) or bool(result["date_ranges"] + result["subject_date_ranges"]
              + result["temporal_warnings"] + result["subject_temporal_warnings"])
    return result
