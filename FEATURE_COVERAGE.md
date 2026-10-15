# Agreed feature coverage

This matrix distinguishes implemented local behavior from services that require the student's own credentials. It does not claim unrestricted language understanding or live-provider verification.

| Requirement | Implementation | Verification / boundary |
|---|---|---|
| Python-first, thin Electron | `application.py`, `api.py`, Electron main/preload and React | API tests and real Electron workflow |
| Multiple private users | Owner-scoped repository, per-profile sessions and vault keys | Cross-owner reads rejected; desktop OS owner can select local profiles |
| Gmail, latest 30–50 | Read-only OAuth, MIME parsing, latest-50 bootstrap, history cursors | Fake-provider cursor/idempotency tests; live OAuth not run without your configuration |
| Older attachment context | Bounded course/assignment searches inside chosen labels/senders | Search-scope test; three candidate lookups per sync |
| Meetings/events, importance | Multi-event extraction, exact supported times, priorities, participation | Separate-event, exact-time, rescheduling and feedback tests |
| Assignments/descriptions | Numbered and unnumbered tasks, per-course/date context, revisions | Multiple-course and old-source replay tests |
| Attachments beyond PDFs | TXT/CSV/HTML/PDF/DOCX/XLSX readers; unsupported status | Reader, duplicate and attachment-only notice tests; no OCR |
| Important or redundant PDF | Content analysis, critical-resource priority, exact hashes, related-resource IDs | Attachment-content deadline and exact-duplicate tests; near-duplicate supersession remains a review judgment |
| Useful links per item | Registration/submission/meeting/reference roles and item links | Cross-email resource test; Drive and arbitrary URLs remain links |
| Academic identity/personalization | Evidence-backed roll/program/university/semester/batch/branch, enrollment facts and complete-timetable context | Class-list identity rejection, inferred-fact review and unrelated-course tests |
| Quiz-style clarification | Grouped review questions, choices, dates/roles, deferral and confirmations | Feedback/clarification tests; source evidence always accessible |
| Learn every correction/acceptance | Private feedback log, direct overrides and weighted personal preferences | Acceptance, repeat-click, stale-revision and account-isolation tests; no pooled training |
| Internal calendar | Confirmed obligations/events, date-only due markers, recurrence | Weekly/batch/holiday tests |
| Google Calendar optional | Separate scopes, managed calendar, external events, sync token recovery, stable event IDs | Fake-provider tests; production connection pending OAuth setup |
| Conflicts and resolver | Interval overlaps, date uncertainty, deadline clusters, flexible-block proposals | Approval and stale-availability tests; fixed official obligations never move |
| Reminders | Durable in-app reminders, date changes, cancellations, catch-up | Delivery-once and old-reminder cancellation tests; app must be running |
| Daily + live + weekly summaries | Daily snapshots, polling-driven dashboard refresh, on-demand week | Source-linked update/fallback tests |
| Optional API summarizer | Explicit provider configuration, OS-vault key, structured-fact-only call, schema/numeric checks and cache | Transport/invalid-ID tests; no paid API call was made |
| Reply expected in conversation | Request ownership clues, sent responses, waiting/resolved states, manual override | Partial-response and replay tests; ambiguous conversational semantics remain a limitation |
| Marks tracker | Confirmed roll, exact row match, course/assessment records and correction history | Leading/extraneous ID rejection, absent vs zero tests; complicated tables require review |
| Timetable/holiday external AI | Versioned schema and clarification-first prompts, preview and confirm | Combined-batch rejection, range/time and holiday tests; weekly patterns plus dated exceptions |
| Self-trained model submission | TF-IDF/NB/SVM/majority comparisons for academic and actionability tasks | Real training artifacts and grouped holdout reports; labels still need human evaluation review |
| Extensibility | Python modules and provider/reader/service boundaries | Graph relationships use persistent IDs; a dedicated graph database is unnecessary initially |

## Explicit deferred or external work

- Supply and authorize the application's Google Desktop OAuth configuration. Connector authorization in another chat does not automatically configure this application.
- Supply an optional summary-provider key only if enhanced wording is wanted.
- Review evaluation labels before presenting scores as human-verified accuracy.
- Add OCR, more complex table/date formats, rotation rules beyond weekly schedules, richer semantic linking and more training examples as measured needs arise.
- Hosted authentication/PostgreSQL, cross-device sync, notification channels beyond in-app, Drive content retrieval, drafts/sending and signed Windows distribution are future work.

The last integration phase covers every agreed feature through a local implementation or an explicit credential-dependent adapter; these external/deferred boundaries are not silently represented as completed live integrations.
