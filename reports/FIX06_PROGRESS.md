# FIX-06 field reconciliation acceptance — 28 October 2026

Assignments and events now retain `field_source_at` for asserted dates and
cancelled status. Date precedence compares a correction with the latest source
that asserted that date; a newer informational notice no longer blocks an
intermediate deadline or reschedule correction. Replaying an older date source
does not restore the old date. Informational event mail preserves a prior
cancelled status. A shared override path preserves assignment and event edits,
including event relevance, and surfaces differing source values with explicit
choices. Manual date edits shift stored time instants to the chosen calendar day
so calendar and reminders use the corrected date. Legacy records without
`field_source_at` use a conservative fallback and populate field times on the
next accepted assertion.

Verification: seven focused field reconciliation tests and the full portable
suite passed (163 tests; one private-data test deselected). `ruff check` on
changed Python files and `git diff --check` passed. One dependency deprecation
warning remains.

FIX-06 is accepted for assignment/event precedence and user override behavior
at fixture level. PIPE-01/05 still own a richer typed assertion contract and
full storage migration; FIX-07 owns broader replay and downstream proof. No
measured model accuracy gain is claimed.
