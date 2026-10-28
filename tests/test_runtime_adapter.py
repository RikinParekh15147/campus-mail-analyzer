"""Synthetic v2 adapter checks; no human pilot labels are asserted here."""

from campusmail.research.runtime_adapter import prepare_reviewed_runtime_cases
from campusmail.research.runtime_eval import evaluate_runtime_scenarios


def reviewed(ids=None):
    return {"completeness": "complete", "provenance": "human_reviewed",
            "reviewer_ids": ids or ["reviewer-a", "reviewer-b"]}


def fixture(**changes):
    text = "NLP201 Assignment 2 must submit by 25 November 2026."
    title = "NLP201 Assignment 2"
    date_text = "25 November 2026"
    return {
        "schema_version": "2.0", "dataset_id": "fixture-only",
        "document_id": "notice-1", "task": "academic",
        "data_origin": "designated_research", "source_type": "fixture",
        "usage_status": "permitted", "subject": title, "text": text,
        "sent_at": "2026-10-01T09:00:00+05:30",
        "annotation_status": {"entities": reviewed(), "dates": reviewed(),
                              "actions": reviewed()},
        "entities": [{"entity_id": "task-2", "type": "assignment",
                      "evidence_spans": [{"field": "text", "start": 0,
                                          "end": len(title), "text": title}],
                      "attributes": {"title": title, "course": "NLP201",
                                     "assignment_number": "2"}}],
        "dates": [{"evidence": {"field": "text", "start": text.index(date_text),
                                "end": text.index(date_text) + len(date_text),
                                "text": date_text},
                   "role": "assignment_deadline", "normalized_value": "2026-11-25",
                   "precision": "date", "entity_id": "task-2"}],
        "actions": [{"evidence": {"field": "text", "start": 0,
                                  "end": len(text), "text": text},
                     "actor": "student", "action_type": "submit",
                     "action_status": "required", "entity_id": "task-2"}],
        **changes,
    }


def test_double_reviewed_single_notice_maps_to_runtime_without_guessing():
    prepared = prepare_reviewed_runtime_cases([fixture()])
    assert prepared["prepared"] == 1
    assert prepared["excluded"] == {}
    result = evaluate_runtime_scenarios(prepared["cases"])
    assert result["error_counts"] == {}
    assert result["label_status"] == "synthetic_fixture"


def test_single_reviewer_and_context_dependent_notice_are_excluded():
    one = fixture(document_id="one", annotation_status={
        "entities": reviewed(["reviewer-a"]), "dates": reviewed(),
        "actions": reviewed(),
    })
    context = fixture(document_id="context", context_document_ids=["earlier"],
                      context_cutoff_at="2026-10-01T09:00:00+05:30")
    prepared = prepare_reviewed_runtime_cases([one, context])
    assert prepared["prepared"] == 0
    assert prepared["excluded"] == {
        "entities_or_dates_not_double_reviewed": 1,
        "context_or_relationship_required": 1,
    }


def test_missing_entity_identity_is_reported_unscorable():
    row = fixture()
    row["entities"][0]["attributes"] = {}
    prepared = prepare_reviewed_runtime_cases([row])
    assert prepared["prepared"] == 0
    assert prepared["excluded"] == {"missing_entity_title": 1}


def test_invalid_identity_attribute_and_unresolved_date_are_not_scored():
    invalid = fixture(document_id="invalid")
    invalid["entities"][0]["attributes"]["course"] = {"guess": "NLP201"}
    unresolved = fixture(document_id="unresolved")
    unresolved["dates"][0]["normalized_value"] = None
    unresolved["dates"][0]["needs_review"] = True
    unresolved["dates"][0]["reason"] = "Year not established"
    prepared = prepare_reviewed_runtime_cases([invalid, unresolved])
    assert prepared["prepared"] == 0
    assert prepared["excluded"] == {
        "invalid_entity_identity_attribute": 1,
        "unresolved_entity_date": 1,
    }


def update_fixture(**changes):
    text = "NLP201 Assignment 2 deadline extended to 28 November 2026."
    title = "NLP201 Assignment 2"
    date_text = "28 November 2026"
    relation_text = "deadline extended"
    row = fixture(
        document_id="notice-2", text=text,
        sent_at="2026-10-02T09:00:00+05:30",
        context_cutoff_at="2026-10-02T09:00:00+05:30",
        context_document_ids=["notice-1"],
        annotation_status={"entities": reviewed(), "dates": reviewed(),
                           "actions": reviewed(), "relationships": reviewed()},
        entities=[{"entity_id": "task-2", "type": "assignment",
                   "evidence_spans": [{"field": "text", "start": 0,
                                       "end": len(title), "text": title}],
                   "attributes": {"title": title, "course": "NLP201",
                                  "assignment_number": "2"}}],
        dates=[{"evidence": {"field": "text", "start": text.index(date_text),
                             "end": text.index(date_text) + len(date_text),
                             "text": date_text},
                "role": "assignment_deadline", "normalized_value": "2026-11-28",
                "precision": "date", "entity_id": "task-2"}],
        actions=[],
        relationships=[{"relationship_id": "update-1", "target_document_id": "notice-1",
                        "source_entity_id": "task-2", "target_entity_id": "task-2",
                        "type": "updates", "evidence_spans": [{
                            "field": "text", "start": text.index(relation_text),
                            "end": text.index(relation_text) + len(relation_text),
                            "text": relation_text}]}],
    )
    row.update(changes)
    return row


def test_double_reviewed_update_pair_maps_to_update_and_replay_checkpoints():
    prepared = prepare_reviewed_runtime_cases([fixture(), update_fixture()])
    assert prepared["prepared"] == 1
    assert prepared["excluded"] == {}
    case = prepared["cases"][0]
    assert len(case["steps"]) == 3
    assert case["steps"][1]["expect"]["entities"][0]["fields"]["due_date"] == "2026-11-28"
    result = evaluate_runtime_scenarios([case])
    assert result["checkpoints"] == 3
    assert result["error_counts"] == {}


def test_update_without_double_reviewed_relation_is_excluded():
    update = update_fixture()
    update["annotation_status"]["relationships"]["reviewer_ids"] = ["reviewer-a"]
    prepared = prepare_reviewed_runtime_cases([fixture(), update])
    assert prepared["prepared"] == 0
    assert prepared["excluded"] == {"relationship_not_double_reviewed": 1}


def test_update_mapping_protects_an_unrelated_assignment():
    text = ("NLP201 Assignment 2 must submit by 25 November 2026. "
            "NLP201 Assignment 3 must submit by 27 November 2026.")
    entities = []
    dates = []
    for number, day in ((2, 25), (3, 27)):
        title = f"NLP201 Assignment {number}"
        date_text = f"{day} November 2026"
        entities.append({"entity_id": f"task-{number}", "type": "assignment",
                         "evidence_spans": [{"field": "text", "start": text.index(title),
                                             "end": text.index(title) + len(title),
                                             "text": title}],
                         "attributes": {"title": title, "course": "NLP201",
                                        "assignment_number": str(number)}})
        dates.append({"evidence": {"field": "text", "start": text.index(date_text),
                                   "end": text.index(date_text) + len(date_text),
                                   "text": date_text},
                      "role": "assignment_deadline",
                      "normalized_value": f"2026-11-{day}",
                      "precision": "date", "entity_id": f"task-{number}"})
    base = fixture(text=text, entities=entities, dates=dates, actions=[])
    prepared = prepare_reviewed_runtime_cases([base, update_fixture()])
    assert prepared["prepared"] == 1
    final = prepared["cases"][0]["steps"][1]["expect"]
    assert len(final["entities"]) == 2
    assert final["preserve"] == [{"kind": "assignment", "anchor": "notice-1",
                                  "match": {"title": "NLP201 Assignment 3",
                                            "course": "NLP201", "assignment_number": "3"},
                                  "fields": ["title", "course", "assignment_number",
                                             "due_date"]}]


def test_three_notice_update_chain_is_reported_unscorable():
    first_update = update_fixture()
    second_update = update_fixture(document_id="notice-3",
                                   sent_at="2026-10-03T09:00:00+05:30",
                                   context_cutoff_at="2026-10-03T09:00:00+05:30",
                                   context_document_ids=["notice-2"])
    second_update["relationships"][0]["target_document_id"] = "notice-2"
    prepared = prepare_reviewed_runtime_cases([fixture(), first_update, second_update])
    assert prepared["prepared"] == 0
    assert prepared["excluded"] == {"unsupported_update_chain": 2}
