"""FIX-01 source offsets, local obligation scope and quoted-history isolation."""

from campusmail.engine import Engine
from campusmail.nlp import analyze, clauses, sentences
from campusmail.store import Store


def test_url_decimal_and_trailing_semicolon_preserve_later_required_action():
    text = "Please see https://portal.edu/a.b?score=3.5; must upload the form."
    result = analyze(text)
    required = [item for item in result["actions"] if item["status"] == "required"]
    assert len(required) == 1
    assert required[0]["text"].strip() == "must upload the form."
    assert text[required[0]["start"]:required[0]["end"]] == required[0]["text"]
    assert len(sentences(text)) == 1
    assert len(clauses(sentences(text)[0])) == 2


def test_semicolon_inside_url_does_not_split_clause():
    text = "See https://portal.edu/a;b?x=1.5 and then must upload the form."
    spans = clauses(sentences(text)[0])
    assert len(spans) == 1
    assert spans[0].group() == text


def test_completed_and_negated_clauses_do_not_hide_new_obligation():
    for text in (
        "Already registered, but must upload the form.",
        "You already registered and must upload the form.",
        "Do not submit the old form; must upload the new form.",
    ):
        actions = analyze(text)["actions"]
        assert len(actions) == 1
        assert actions[0]["status"] == "required"
        assert "upload" in actions[0]["text"]
        assert text[actions[0]["start"]:actions[0]["end"]] == actions[0]["text"]


def test_abbreviations_and_decimal_do_not_merge_true_following_sentence():
    text = "Prof. Rao reported a 3.5 score etc. Submit the form now."
    spans = sentences(text)
    assert len(spans) == 2
    assert "Prof. Rao" in spans[0].group()
    assert "3.5" in spans[0].group()
    result = analyze(text)
    assert len(result["actions"]) == 1
    assert result["actions"][0]["text"].strip() == "Submit the form now."


def test_quoted_lines_are_masked_without_shifting_authored_offsets():
    text = ("> Assignment 2 must submit by 25 October 2026.\n"
            "You already registered and must upload the new form.\n"
            "> Workshop starts on 27 October 2026.")
    result = analyze(text)
    assert result["dates"] == []
    assert len(result["actions"]) == 1
    action = result["actions"][0]
    assert action["status"] == "required"
    assert text[action["start"]:action["end"]] == action["text"]


def test_engine_does_not_mutate_entities_from_quoted_history(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store)
    message = store.put(owner, "message", {
        "subject": "Update", "text": (
            "The old registration was completed.\n"
            "> NLP201 Assignment 2 must submit by 25 October 2026."
        ),
    }, "with-quote")
    engine.process(owner, message)
    assert store.list(owner, "assignment") == []
    assert store.get(owner, message["id"])["analysis"]["dates"] == []


def test_quote_only_message_has_no_authored_analysis(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store)
    message = store.put(owner, "message", {
        "subject": "NLP201 Assignment 2",
        "text": "> NLP201 Assignment 2 must submit by 25 October 2026.",
    }, "quote-only")
    result = engine.process(owner, message)
    assert result["category"] == "unknown"
    assert result["actions"] == []
    assert store.list(owner, "assignment") == []


def test_reply_header_excludes_old_obligation_from_engine(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("Student")["id"]
    engine = Engine(store)
    message = store.put(owner, "message", {
        "subject": "Re: Notice",
        "text": ("Thanks for the update.\n"
                 "On Tue, 27 Oct 2026 at 10:00 Prof. Rao wrote:\n"
                 "NLP201 Assignment 2 must submit by 28 October 2026."),
    }, "reply")
    engine.process(owner, message)
    assert store.list(owner, "assignment") == []
    assert store.get(owner, message["id"])["analysis"]["dates"] == []
