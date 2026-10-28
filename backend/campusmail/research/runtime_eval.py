"""Fixture replay checks for persisted entities and downstream state.

This runner never turns source or weak labels into gold. Reviewed-corpus
adapters and sealed-test custody are separate evaluation work.
"""

from collections import Counter
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from ..application import Application
from .development_protocol import verify_development_selection
from .files import file_sha256, jsonl_records
from .runtime_adapter import prepare_reviewed_runtime_cases

ENTITY_FIELDS = {
    "assignment": {"title", "course", "assignment_number", "academic_term",
                   "due_date", "due_at", "status", "relevance", "participation"},
    "event": {"title", "course", "academic_term", "date", "start", "end",
              "status", "relevance", "participation"},
}


def evaluate_runtime_scenarios(cases):
    """Return aggregate fixture errors, without notice text or private evidence."""
    errors = []
    checkpoints = 0
    seen_cases = set()
    with TemporaryDirectory(prefix="campus-runtime-eval-") as directory:
        root = Path(directory)
        for case_index, case in enumerate(cases, 1):
            case_id = case["case_id"]
            if not isinstance(case_id, str) or not case_id or case_id in seen_cases:
                raise ValueError("Scenario IDs must be unique nonempty strings")
            seen_cases.add(case_id)
            app = Application(root / str(case_index), project_root=root / "rules_only")
            owner = app.store.create_user("Fixture student")["id"]
            for field, value in case.get("confirmed_facts", {}).items():
                app.engine.fact(owner, field, value, "fixture-profile", True)
            sources = {}
            for index, step in enumerate(case["steps"], 1):
                if ("message" in step) == ("replay" in step):
                    raise ValueError("Each step needs one message or replay key")
                if "message" in step:
                    item = step["message"]
                    key = item["source_key"]
                    if key in sources:
                        raise ValueError("Duplicate scenario source key")
                    message = app.store.put(owner, "message", {
                        k: v for k, v in item.items() if k != "source_key"
                    }, key)
                    sources[key] = message["id"]
                else:
                    key = step["replay"]
                    if key not in sources:
                        raise ValueError("Replay source is not yet present")
                    message = app.store.get(owner, sources[key])
                before_records = {r["id"]: r for r in app.store.list(owner)
                                  if r["kind"] in ("assignment", "event")}
                app.process(owner, message)
                expected = step.get("expect")
                if expected is None:
                    continue
                checkpoints += 1
                records = [r for r in app.store.list(owner)
                           if r["kind"] in ("assignment", "event")]
                current_records = {r["id"]: r for r in records}
                for protected in expected.get("preserve", []):
                    anchor, kind = protected["anchor"], protected["kind"]
                    fields = protected.get("fields", [])
                    match = protected.get("match", {})
                    if (anchor not in sources or kind not in ENTITY_FIELDS
                        or not isinstance(fields, list)
                        or any(not isinstance(field, str) for field in fields)
                        or set(fields) - ENTITY_FIELDS[kind]
                        or not isinstance(match, dict)
                        or set(match) - ENTITY_FIELDS[kind]):
                        raise ValueError("Invalid preserved entity expectation")
                    candidates = [r for r in before_records.values()
                                  if r["kind"] == kind
                                  and sources[anchor] in r.get("evidence_ids", [])
                                  and all(r.get(field) == value for field, value
                                          in match.items())]
                    if len(candidates) != 1:
                        raise ValueError("Preserved entity must exist uniquely before step")
                    previous = candidates[0]
                    current = current_records.get(previous["id"])
                    if (current is None or any(current.get(field) != previous.get(field)
                                               for field in fields)
                        or current.get("evidence_ids", []) != previous.get("evidence_ids", [])):
                        errors.append((case_index, index, "wrong_target_mutation", kind))
                matched = Counter()
                for wanted in expected.get("entities", []):
                    anchor = wanted["anchor"]
                    kind = wanted["kind"]
                    if (kind not in ENTITY_FIELDS
                        or set(wanted.get("fields", {})) - ENTITY_FIELDS[kind]
                        or set(wanted.get("match", {})) - ENTITY_FIELDS[kind]):
                        raise ValueError("Unsupported expected entity kind or field")
                    if anchor not in sources:
                        raise ValueError("Expected entity anchor is not yet present")
                    candidates = [r for r in records
                                  if r["kind"] == kind
                                  and sources[anchor] in r.get("evidence_ids", [])
                                  and all(r.get(field) == value
                                          for field, value in wanted.get("match", {}).items())]
                    if len(candidates) != 1:
                        errors.append((case_index, index, "missing_or_split_entity", "entity"))
                        continue
                    record = candidates[0]
                    matched[record["id"]] += 1
                    for field, value in wanted.get("fields", {}).items():
                        if record.get(field) != value:
                            errors.append((case_index, index, "field_mismatch", field))
                    if "evidence" in wanted:
                        observed = {app.store.get(owner, item_id)["source_key"]
                                    for item_id in record.get("evidence_ids", [])}
                        if observed != set(wanted["evidence"]):
                            errors.append((case_index, index, "evidence_mismatch", "entity"))
                for record in records:
                    if matched[record["id"]] > 1:
                        errors.append((case_index, index, "false_merge", record["kind"]))
                    elif not matched[record["id"]]:
                        errors.append((case_index, index, "spurious_entity", record["kind"]))
                matched_actions = {}
                for wanted in expected.get("actions", []):
                    anchor = wanted["anchor"]
                    if anchor not in sources:
                        raise ValueError("Expected action anchor is not yet present")
                    message = app.store.get(owner, sources[anchor])
                    if (type(wanted.get("start")) is not int or type(wanted.get("end")) is not int
                        or not 0 <= wanted["start"] < wanted["end"] <= len(message.get("text", ""))):
                        raise ValueError("Expected action span is invalid")
                    actions = message.get("analysis", {}).get("actions", [])
                    candidates = [i for i, action in enumerate(actions)
                                  if action.get("start") == wanted["start"]
                                  and action.get("end") == wanted["end"]]
                    if len(candidates) != 1:
                        errors.append((case_index, index, "missing_or_split_action", "action"))
                    else:
                        matched_actions.setdefault(anchor, set()).add(candidates[0])
                        if actions[candidates[0]].get("status") != wanted["status"]:
                            errors.append((case_index, index, "action_status_mismatch", "status"))
                for anchor in expected.get("action_complete_for", []):
                    if anchor not in sources:
                        raise ValueError("Complete action source is not yet present")
                    actions = app.store.get(owner, sources[anchor]).get("analysis", {}).get("actions", [])
                    for action_index in set(range(len(actions))) - matched_actions.get(anchor, set()):
                        errors.append((case_index, index, "spurious_action", "action"))
                for wanted in expected.get("reply_states", []):
                    anchor = wanted["anchor"]
                    if anchor not in sources:
                        raise ValueError("Expected reply anchor is not yet present")
                    candidates = [r for r in app.store.list(owner, "reply_request")
                                  if r.get("message_id") == sources[anchor]]
                    if len(candidates) != 1:
                        errors.append((case_index, index, "missing_or_split_reply", "reply"))
                    elif candidates[0].get("state") != wanted["state"]:
                        errors.append((case_index, index, "reply_state_mismatch", "state"))
                if "calendar" in expected:
                    window = expected["calendar_window"]
                    entries = app.calendar.entries(owner, window[0], window[1])
                    actual = Counter((r["kind"], r["date"]) for r in entries
                                     if r["kind"] in ("assignment", "event"))
                    if actual != Counter(tuple(row) for row in expected["calendar"]):
                        errors.append((case_index, index, "calendar_mismatch", "schedule"))
                if "pending_reminders" in expected:
                    clock = datetime.fromisoformat(expected["reminder_clock"])
                    if clock.tzinfo is None:
                        raise ValueError("Reminder clock requires a timezone")
                    app.reminders.refresh(owner, clock)
                    actual = Counter(r["target_date"] for r in app.store.list(owner, "reminder")
                                     if r["status"] == "pending")
                    if actual != Counter(expected["pending_reminders"]):
                        errors.append((case_index, index, "reminder_mismatch", "schedule"))
                for field in expected.get("required_open_review_fields", []):
                    if not any(r.get("field") == field and r["status"] == "open"
                               for r in app.store.list(owner, "review")):
                        errors.append((case_index, index, "missing_review", "review"))
    return {
        "label_status": "synthetic_fixture",
        "scenarios": len(seen_cases), "checkpoints": checkpoints,
        "error_counts": dict(Counter(item[2] for item in errors)),
        "errors": [
            {"case_index": case_index, "step": step, "type": kind, "field": field}
            for case_index, step, kind, field in errors
        ],
    }


def evaluate_development_runtime(input_path, selection_path, reservation_dir, *,
                                 expected_input_sha256, expected_selection_sha256,
                                 fixture_mode=False):
    """Score only a pinned, verified development selection; return aggregate data."""
    if (file_sha256(input_path) != expected_input_sha256
        or file_sha256(selection_path) != expected_selection_sha256):
        raise ValueError("Pinned runtime evaluation input changed")
    selection = verify_development_selection(
        input_path, selection_path, reservation_dir, fixture_mode=fixture_mode)
    documents = []
    for line, row, _, error in jsonl_records(input_path):
        if error or row is None:
            raise ValueError(f"Invalid reviewed runtime input at line {line}")
        documents.append(row)
    prepared = prepare_reviewed_runtime_cases(documents)
    if not fixture_mode and not prepared["prepared"]:
        raise ValueError("No fully reviewed runtime scenarios could be prepared")
    result = evaluate_runtime_scenarios(prepared["cases"])
    result["label_status"] = "synthetic_fixture" if fixture_mode else "reviewed_development"
    result["input_sha256"] = expected_input_sha256
    result["selection_sha256"] = expected_selection_sha256
    result["selection_support"] = selection["support"]
    result["prepared_scenarios"] = prepared["prepared"]
    result["excluded"] = prepared["excluded"]
    return result
