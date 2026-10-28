"""FIX-05 occurrence identity and reviewed replay boundaries."""

from campusmail.engine import Engine
from campusmail.api import create_app
from campusmail.personalization import Personalizer
from campusmail.store import Store
from fastapi.testclient import TestClient


def setup(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    return store, owner, Engine(store)


def message(store, owner, key, text, subject="", **fields):
    return store.put(owner, "message", {"text": text, "subject": subject, **fields}, key)


def occurrence_question(store, owner, kind):
    questions = [
        q for q in store.list(owner, "review")
        if q.get("field") == "occurrence"
        and q.get("context", {}).get("candidate_kind") == kind
        and q.get("status") == "open"
    ]
    assert len(questions) == 1
    return questions[0]


def test_unknown_course_number_is_scoped_by_thread_and_replays(tmp_path):
    store, owner, engine = setup(tmp_path)
    first = message(store, owner, "one", "Assignment 2 must submit by 25 October 2026.",
                    thread_id="thread-a")
    second = message(store, owner, "two", "Assignment 2 must submit by 28 October 2026.",
                     thread_id="thread-b")
    engine.process(owner, first)
    engine.process(owner, second)
    assert len(store.list(owner, "assignment")) == 2
    assert {a["due_date"] for a in store.list(owner, "assignment")} == {
        "2026-10-25", "2026-10-28"
    }
    engine.process(owner, store.get(owner, first["id"]))
    assert len(store.list(owner, "assignment")) == 2


def test_explicit_terms_keep_repeated_assignment_numbers_separate(tmp_path):
    store, owner, engine = setup(tmp_path)
    fall = message(store, owner, "fall", "Fall 2026: NLP201 Assignment 2 must submit by 25 October 2026.")
    spring = message(store, owner, "spring", "Spring 2027: NLP201 Assignment 2 must submit by 25 March 2027.")
    engine.process(owner, fall)
    engine.process(owner, spring)
    assignments = store.list(owner, "assignment")
    assert len(assignments) == 2
    assert {a["academic_term"] for a in assignments} == {"fall 2026", "spring 2027"}
    assert len({a["source_key"] for a in assignments}) == 2


def test_term_alias_and_reverse_order_replay_same_occurrence(tmp_path):
    store, owner, engine = setup(tmp_path)
    first = message(store, owner, "first", "Autumn 2026: NLP201 Assignment 2 must submit by 25 October 2026.")
    update = message(store, owner, "update", "2026 Fall: NLP201 Assignment 2 deadline extended to 28 October 2026.")
    engine.process(owner, first)
    engine.process(owner, update)
    assignments = store.list(owner, "assignment")
    assert len(assignments) == 1
    assert assignments[0]["academic_term"] == "fall 2026"
    assert assignments[0]["due_date"] == "2026-10-28"


def test_explicit_terms_keep_same_title_events_separate(tmp_path):
    store, owner, engine = setup(tmp_path)
    for key, term, date in (("fall", "Fall 2026", "25 October 2026"),
                            ("spring", "Spring 2027", "25 March 2027")):
        engine.process(owner, message(
            store, owner, key,
            f"{term}: Python Workshop will be held on {date}.",
            subject="Python Workshop",
        ))
    events = store.list(owner, "event")
    assert len(events) == 2
    assert {e["academic_term"] for e in events} == {"fall 2026", "spring 2027"}


def test_legacy_unknown_key_requires_review_then_can_create_separate(tmp_path):
    store, owner, engine = setup(tmp_path)
    store.put(owner, "assignment", {"title": "Assignment 2", "course": None,
                                    "due_date": "2026-10-25", "evidence_ids": []},
              "unknown:assignment:2")
    notice = message(store, owner, "new", "Assignment 2 must submit by 28 October 2026.")
    engine.process(owner, notice)
    assert len(store.list(owner, "assignment")) == 1
    question = occurrence_question(store, owner, "assignment")
    assert question["choices"] == ["existing_1", "create_separate"]
    Personalizer(store).answer(owner, question["id"], "create_separate")
    engine.process(owner, store.get(owner, notice["id"]))
    assert len(store.list(owner, "assignment")) == 2
    engine.process(owner, store.get(owner, notice["id"]))
    assert len(store.list(owner, "assignment")) == 2


def test_legacy_unknown_key_can_be_selected_without_duplicate(tmp_path):
    store, owner, engine = setup(tmp_path)
    legacy = store.put(owner, "assignment", {"title": "Assignment 2", "course": None,
                                              "due_date": "2026-10-25", "evidence_ids": []},
                       "unknown:assignment:2")
    notice = message(store, owner, "new", "Assignment 2 deadline extended to 28 October 2026.")
    engine.process(owner, notice)
    question = occurrence_question(store, owner, "assignment")
    Personalizer(store).answer(owner, question["id"], "existing_1")
    engine.process(owner, store.get(owner, notice["id"]))
    assignments = store.list(owner, "assignment")
    assert len(assignments) == 1
    assert assignments[0]["id"] == legacy["id"]
    assert assignments[0]["due_date"] == "2026-10-28"


def test_legacy_known_course_assignment_requires_identity_choice(tmp_path):
    store, owner, engine = setup(tmp_path)
    legacy = store.put(
        owner, "assignment",
        {"title": "NLP201 Assignment 2", "course": "NLP201",
         "due_date": "2026-10-25", "evidence_ids": []},
        "NLP201:assignment:2",
    )
    notice = message(
        store, owner, "new",
        "NLP201 Assignment 2 deadline extended to 28 October 2026.",
    )
    engine.process(owner, notice)
    assert store.get(owner, legacy["id"])["due_date"] == "2026-10-25"
    question = occurrence_question(store, owner, "assignment")
    Personalizer(store).answer(owner, question["id"], "existing_1")
    engine.process(owner, store.get(owner, notice["id"]))
    assert len(store.list(owner, "assignment")) == 1
    assert store.get(owner, legacy["id"])["due_date"] == "2026-10-28"


def test_legacy_event_requires_identity_choice(tmp_path):
    store, owner, engine = setup(tmp_path)
    legacy = store.put(
        owner, "event",
        {"title": "Python Workshop", "course": None,
         "date": "2026-10-25", "base_key": ":python workshop",
         "evidence_ids": []},
        ":python workshop:2026-10-25",
    )
    update = message(
        store, owner, "update",
        "Python Workshop is rescheduled for 28 October 2026.",
        subject="Python Workshop",
    )
    engine.process(owner, update)
    assert store.get(owner, legacy["id"])["date"] == "2026-10-25"
    question = occurrence_question(store, owner, "event")
    Personalizer(store).answer(owner, question["id"], "existing_1")
    engine.process(owner, store.get(owner, update["id"]))
    assert len(store.list(owner, "event")) == 1
    assert store.get(owner, legacy["id"])["date"] == "2026-10-28"


def test_ambiguous_event_reschedule_waits_for_review_and_replays(tmp_path):
    store, owner, engine = setup(tmp_path)
    for key, day in (("one", "25"), ("two", "28")):
        engine.process(owner, message(
            store, owner, key,
            f"Python Workshop will be held on {day} October 2026.",
            subject="Python Workshop",
        ))
    update = message(store, owner, "update",
                     "Python Workshop is rescheduled for 30 October 2026.",
                     subject="Python Workshop")
    engine.process(owner, update)
    assert len(store.list(owner, "event")) == 2
    question = occurrence_question(store, owner, "event")
    assert question["choices"] == ["existing_1", "existing_2", "create_separate"]
    Personalizer(store).answer(owner, question["id"], "existing_2")
    engine.process(owner, store.get(owner, update["id"]))
    assert len(store.list(owner, "event")) == 2
    assert sorted(e["date"] for e in store.list(owner, "event")) == [
        "2026-10-25", "2026-10-30"
    ]
    engine.process(owner, store.get(owner, update["id"]))
    assert len(store.list(owner, "event")) == 2


def test_create_separate_event_choice_is_idempotent(tmp_path):
    store, owner, engine = setup(tmp_path)
    for key, day in (("one", "25"), ("two", "28")):
        engine.process(owner, message(
            store, owner, key,
            f"Python Workshop will be held on {day} October 2026.",
            subject="Python Workshop",
        ))
    update = message(store, owner, "update",
                     "Python Workshop is rescheduled for 30 October 2026.",
                     subject="Python Workshop")
    engine.process(owner, update)
    question = occurrence_question(store, owner, "event")
    Personalizer(store).answer(owner, question["id"], "create_separate")
    engine.process(owner, store.get(owner, update["id"]))
    assert len(store.list(owner, "event")) == 3
    engine.process(owner, store.get(owner, update["id"]))
    assert len(store.list(owner, "event")) == 3


def test_update_seen_before_original_events_cannot_create_third(tmp_path):
    store, owner, engine = setup(tmp_path)
    update = message(store, owner, "update",
                     "Python Workshop is rescheduled for 30 October 2026.",
                     subject="Python Workshop")
    engine.process(owner, update)
    assert store.list(owner, "event") == []
    for key, day in (("one", "25"), ("two", "28")):
        engine.process(owner, message(
            store, owner, key,
            f"Python Workshop will be held on {day} October 2026.",
            subject="Python Workshop",
        ))
    engine.process(owner, store.get(owner, update["id"]))
    assert len(store.list(owner, "event")) == 2
    question = occurrence_question(store, owner, "event")
    assert len(question["context"]["candidate_ids"]) == 2
    Personalizer(store).answer(owner, question["id"], "existing_1")
    engine.process(owner, store.get(owner, update["id"]))
    assert len(store.list(owner, "event")) == 2


def test_older_event_replay_preserves_reviewed_reschedule(tmp_path):
    store, owner, engine = setup(tmp_path)
    original = message(
        store, owner, "original",
        "Python Workshop will be held on 25 October 2026.",
        subject="Python Workshop", sent_at="2026-10-01T09:00:00+05:30",
    )
    update = message(
        store, owner, "update",
        "Python Workshop is rescheduled for 28 October 2026.",
        subject="Python Workshop", sent_at="2026-10-02T09:00:00+05:30",
    )
    engine.process(owner, original)
    engine.process(owner, update)
    engine.process(owner, store.get(owner, original["id"]))
    events = store.list(owner, "event")
    assert len(events) == 1
    assert events[0]["date"] == "2026-10-28"


def test_cross_thread_known_assignment_requires_decision(tmp_path):
    store, owner, engine = setup(tmp_path)
    first = message(store, owner, "one", "NLP201 Assignment 2 must submit by 25 October 2026.",
                    thread_id="first-thread")
    second = message(store, owner, "two", "NLP201 Assignment 2 must submit by 28 October 2026.",
                     thread_id="second-thread")
    engine.process(owner, first)
    engine.process(owner, second)
    assert len(store.list(owner, "assignment")) == 1
    question = occurrence_question(store, owner, "assignment")
    Personalizer(store).answer(owner, question["id"], "create_separate")
    engine.process(owner, store.get(owner, second["id"]))
    assert len(store.list(owner, "assignment")) == 2
    engine.process(owner, store.get(owner, second["id"]))
    assert len(store.list(owner, "assignment")) == 2


def test_multiple_explicit_terms_abstain_from_entity_mutation(tmp_path):
    store, owner, engine = setup(tmp_path)
    notice = message(
        store, owner, "mixed",
        "Fall 2026 Assignment 2 is replaced by Spring 2027 Assignment 2.",
    )
    result = engine.process(owner, notice)
    assert result["needs_review"]
    assert store.list(owner, "assignment") == []


def test_invalid_occurrence_choice_does_not_mutate_message(tmp_path):
    store, owner, engine = setup(tmp_path)
    legacy = store.put(owner, "assignment", {"title": "Assignment 2", "course": None},
                       "unknown:assignment:2")
    notice = message(store, owner, "new", "Assignment 2 must submit by 28 October 2026.")
    engine.process(owner, notice)
    question = occurrence_question(store, owner, "assignment")
    try:
        Personalizer(store).answer(owner, question["id"], legacy["id"])
    except ValueError:
        pass
    else:
        raise AssertionError("Unlisted occurrence choice was accepted")
    assert "occurrence_decisions" not in store.get(owner, notice["id"])


def test_api_review_choice_reprocesses_ambiguous_event(tmp_path):
    app = create_app(tmp_path, bootstrap_key="occurrence-bootstrap", worker=False)
    with TestClient(app) as client:
        created = client.post(
            "/profiles", json={"name": "Student"},
            headers={"X-Bootstrap-Key": "occurrence-bootstrap"},
        )
        assert created.status_code == 200
        headers = {"Authorization": "Bearer " + created.json()["token"]}
        for day in ("25", "28"):
            response = client.post(
                "/ingest", headers=headers,
                json={"subject": "Python Workshop",
                      "text": f"Python Workshop will be held on {day} October 2026."},
            )
            assert response.status_code == 200
        update = client.post(
            "/ingest", headers=headers,
            json={"subject": "Python Workshop",
                  "text": "Python Workshop is rescheduled for 30 October 2026."},
        )
        assert update.status_code == 200
        questions = client.get("/records/review", headers=headers).json()
        question = next(q for q in questions if q.get("field") == "occurrence")
        answered = client.post(
            f"/reviews/{question['id']}/answer", headers=headers,
            json={"value": "existing_2"},
        )
        assert answered.status_code == 200
        events = client.get("/records/event", headers=headers).json()
        assert sorted(e["date"] for e in events) == ["2026-10-25", "2026-10-30"]
