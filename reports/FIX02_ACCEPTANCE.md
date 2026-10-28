# FIX-02 temporal candidate coverage acceptance — 28 October 2026

The local parser preserves source offsets for month-first, day-first, ISO and
supported numeric dates; AM/PM and 24-hour times are collected in one pass.
Subject dates use their own offset namespace, and a time immediately before a
body date can link to an unambiguous deadline. Missing years and standalone
times remain unresolved.

Compact same-month ranges such as `October 25-27, 2026` and
`25-27 October 2026` now produce one start/end candidate with exact evidence.
Their overlapping single-date matches are suppressed. Missing-year, invalid
and cross-month/date-format ranges stay unresolved. The engine never takes a
range endpoint as an automatic assignment or event date; it creates a review
prompt instead. Ambiguous one-meridiem time ranges, time-only deadlines, weekday
wording, relative offsets such as `within 3 days`, and `EOD`/end-of-week cues
also create review prompts rather than invented dates or times. Replays reuse
the same prompt; changed cue text has a distinct key.

Eighteen focused temporal tests cover compact and unsupported ranges, source
offsets, overlap suppression, engine review/no deadline mutation, subject-only
dates, time-before-date, mixed-format times and unresolved cues. The full
portable suite passed 230 tests with one private-data test deselected.
Changed Python files passed `ruff check` and `git diff --check` passed.

FIX-02 is accepted for these supported rule families. Review is intentional
for a range until a person chooses the relevant endpoint and entity. This is
fixture correctness, not a measured increase in recall or deadline precision;
DATA-06 reviewed labels and EVAL-03/06 baselines remain pending. Other natural
language date forms may still require review or future extraction work.
