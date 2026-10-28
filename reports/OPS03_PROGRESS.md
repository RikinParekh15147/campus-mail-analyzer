# OPS-03 restart acceptance — 28 October 2026

The worker now reclaims legacy running jobs with no lease. Completion and
failure writes use the revision from the claimed lease, so an old worker
cannot overwrite a job another worker reclaimed. A conflict leaves the newer
lease and its attempt state intact.

Long-running handlers now renew their leases on a bounded heartbeat. The
heartbeat uses revision fencing, refuses to renew a lease that has already
expired or changed owner, and the worker writes its result only while it still
holds a valid lease. A failure after renewal uses the latest revision for its
retry record. Unchanged Gmail refetches retain reviewed message decisions.
Application reprocessing refreshes reminders after it converges.
Failure injection also covers a Gmail ingest interrupted before its history
checkpoint and a Calendar create whose response is lost after the remote
write. Retrying the Gmail batch reuses message identities and then advances
history; retrying the Calendar export reuses its deterministic provider ID.

Direct application processing now writes a pending marker before analysis and
marks the message complete only after all local processing succeeds. A restarted
worker discovers expired pending markers, queues an owner-scoped recovery job,
reprocesses the stored message and refreshes reminders. A completed recovery
job can be revived if that message later fails again. The recovery test injects
two separate crashes after an entity write and verifies one assignment and
current reminders after each restart.

Verification: eight focused recovery tests passed, including a reopened store,
a simulated lease takeover, long-running success and failure, and a failure
injected between two message updates followed by a fresh application instance.
That restart produced one assignment with both evidence IDs and cancelled the
old pending reminders. The portable suite passed 181 tests with one
private-data test deselected. Changed Python files passed `ruff check` and
`git diff --check` passed.

OPS-03 is accepted for supported local and fake-provider failure paths. The
pending marker uses a 15-minute lease before automatic reclaim, so a live direct
process is not immediately duplicated. Real-provider behavior, process pauses
beyond that lease and exactly-once external execution are not established by
these fixtures; environment/release verification owns those claims.
