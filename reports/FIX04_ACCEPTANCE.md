# FIX-04 cancellation targeting acceptance — 28 October 2026

Cancellation matching now uses local contrastive and newly named clauses.
An explicit numbered assignment or named event can change status only when
the cancellation wording belongs to that item. A cancellation in another
clause no longer turns a different unknown-course assignment into an update
or silently merges it across threads. Event extraction considers every named
event in a sentence instead of only the first.

Negated cancellation leaves status unchanged. Hedged wording such as
`may be cancelled`, number lists and clauses naming multiple events preserve
current status and create review. Generic unnumbered assignment and generic
event cancellation also require a target decision. Review questions remain
linked to candidate records; a person's status answer survives replay.

Ten focused fixture tests cover two assignment targets, mixed active/cancelled
events, negation, hedging, ambiguous lists, unknown-course cross-thread
isolation, generic review decisions, replay, calendar removal and cancellation
of pending reminders. The portable suite passed 240 tests with one private-data
test deselected. Changed Python files passed `ruff check`; `git diff --check`
passed.

FIX-04 is accepted for these supported fixture paths. Complex conjunctions
without a safe local target deliberately go to review. No reviewed corpus run
or measured reduction in wrong-target cancellations exists yet; DATA-06 and
EVAL-03/06 remain the accuracy gate.
