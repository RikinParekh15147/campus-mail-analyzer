# Temporal correctness increment — 28 October 2026

FIX-02 temporal candidate coverage and FIX-03 source-date anchoring are now
accepted for supported fixture paths. See [FIX-02 acceptance](FIX02_ACCEPTANCE.md)
and [FIX-03 acceptance](FIX03_ACCEPTANCE.md). The earlier notes below describe
the initial partial implementation.

The local parser now recognizes month-first dates such as
`October 25, 2026` and `October 25` while preserving the existing day-first,
ISO, numeric and relative paths. A missing year remains unresolved. One
combined time scan records both AM/PM and 24-hour times in the same notice,
without emitting a second 24-hour match inside `5:30 PM`.

Subject dates now have their own `subject_dates` evidence list and offset
namespace. The engine applies a single role-matched, resolved subject date only
when there is one assignment or event target and no body date for that target.
Ambiguous subject dates go to review; user corrections use a `subject:` key so
they cannot collide with body offsets. A subject-only date is not combined with
an unrelated body time. For body deadlines, a time immediately before the date
can be linked when it is the only nearby time in the same sentence; time after
the date is also restricted to that sentence.

Relative `today`/`tomorrow` normalization now requires a timezone-aware source
timestamp. A missing or naive timestamp produces a review reason. A readable
attachment inherits the parent's actual `sent_at` only; record creation time
is no longer substituted for the source date. This prevents processing time
from changing a historical relative date.

At this stage FIX-02/FIX-03 were partial. Later acceptance reports add
conservative range extraction, unsupported-cue review and source-time replay
checks. No reviewed accuracy measurement is claimed.
