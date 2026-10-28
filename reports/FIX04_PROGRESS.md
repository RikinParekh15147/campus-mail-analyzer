# Assignment cancellation scoping increment — 28 October 2026

FIX-04 is now accepted for supported fixture paths after clause-level targeting,
negation/hedging review and replay/downstream checks. See
[FIX-04 acceptance](FIX04_ACCEPTANCE.md). The notes below describe the
earlier partial implementation.

Assignment status no longer changes to `cancelled` merely because the notice
contains that word somewhere. Cancellation must appear in the assignment's
associated text span and identify its number, or refer generically to the sole
assignment in that span. A span mentioning multiple assignment numbers is
treated as ambiguous and creates a review question instead of cancelling all
assignments. Each question is linked to the candidate assignment's status, so
the student's answer can apply to that record. Existing manual status overrides
remain applied afterward.

Named events use the sentence that identified each event. A cancellation in a
sentence naming multiple events, or in the generic subject-based fallback, now
creates review instead of cancelling every event. A sentence with one named
event can still cancel it. Ambiguous cancellation preserves the prior status;
its review question is linked to that event's status.

At this stage FIX-04 was partial. The later acceptance adds multi-clause
targeting, generic single-event review decisions, replay and downstream checks.
Complex conjunctions still go to review; no real-data error reduction is claimed.
