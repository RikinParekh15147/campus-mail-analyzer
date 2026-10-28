# EVAL-02 component scorer acceptance — 28 October 2026

The reviewed-v2 scorer reports supported-class category accuracy/macro-F1,
strict one-to-one action/date spans, diagnostic overlap, date role and
normalization, and action actor/status agreement. It scores only fields whose
annotation status is complete and human-reviewed. Predicted evidence is
validated even for an unreviewed task, so a malformed offset cannot silently
vanish from a run. Duplicate predictions count as false positives. Synthetic
and quarantined source rows are excluded.

Four synthetic contract tests cover complete versus unreviewed fields,
duplicate predictions, invalid offsets and source exclusions. The portable
suite passed 181 tests with one private-data test deselected; changed Python
files passed `ruff check` and `git diff --check` passed.

EVAL-02 is accepted as scoring infrastructure. No reviewed development or
holdout score exists: the installed DATA-06 pilot audit still reports 0/50
classification reviews for each reviewer. EVAL-03/05/06 and DATA-06–08 remain
open. This report makes no accuracy claim.
