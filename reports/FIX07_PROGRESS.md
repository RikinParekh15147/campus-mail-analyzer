# FIX-07 replay acceptance — 28 October 2026

The replay suite now checks reverse-order event imports after replay, duplicate
attachments, parent-specific attachment analysis, relative dates anchored to
each parent source time, assignment reschedules and pending reminder cleanup.
An event update imported before its original notice can now close its earlier
occurrence review once a replay resolves the target unambiguously. Shared blob
bytes remain deduplicated, while each parent has a distinct analysis message
and the resource retains all analysis-message IDs.

Application reimport of byte-identical messages and attachments now retains
reviewed date corrections and occurrence decisions across restart/reprocess.
Equal-time conflicting date assertions from body and attachment, or from event
notices, create a field review and preserve the existing date until the user
chooses. Managed calendar reconciliation removes previously exported records
when participation or relevance becomes ineligible and restores them
idempotently if eligibility returns. A rescheduled all-day export updates the
remote date with an exclusive next-day end.

Verification: eight focused replay tests passed; the full portable suite
passed 168 tests with one private-data test deselected. Changed Python files
passed `ruff check`, and `git diff --check` passed. These are synthetic
correctness checks, not accuracy measurements.

FIX-07 is accepted for supported fixture replay orders and downstream records.
OPS-03 still owns fault injection, durable transactions and worker restart
semantics. PIPE-05 owns explicit migration of existing attachment occurrence
keys; environment/release gates own real-provider calendar verification. No
real-data accuracy or production recovery result is claimed.
