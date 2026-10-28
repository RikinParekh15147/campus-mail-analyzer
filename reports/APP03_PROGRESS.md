# APP-03 schedule propagation acceptance — 28 October 2026

Managed-calendar sync now reconciles existing mappings against current
assignment/event eligibility. Declined events, unrelated assignments,
cancelled or completed records, removed records and records without dates are
unexported, rather than silently skipped. Retries are idempotent; renewed
eligibility recreates the managed event. A reschedule patches the same remote
ID, with an exclusive next-day end for all-day items. Pending local reminders
for old assignment dates are cancelled on refresh. Timed assignment deadlines
export as one-minute transparent due markers at the actual due time; untimed
deadlines remain all-day transparent markers. Incomplete event records are not
exported. When an existing Google Calendar event has been edited remotely,
sync waits for an explicit `keep_remote` or `replace_remote` review decision;
the latter applies the current local schedule and updates the mapping.

Verification: fake-API export/retry/reschedule tests and local reminder replay
tests passed as part of the 168-test portable suite. `ruff check` and
`git diff --check` passed. No real Google Calendar call was made.

APP-03 is accepted at fixture level for local calendar, reminder and managed
export propagation. Real Google Calendar behavior and credentialed package
acceptance remain in the environment/release gates; a fake API cannot establish
real-provider reliability. No measured accuracy claim is made.
