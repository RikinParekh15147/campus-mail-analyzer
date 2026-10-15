# Implementation phases and acceptance gates

Work rule: write behavioral tests for each phase, run them failing, implement, then run the phase tests and existing suite. Record actual results in `BUILD_PROGRESS.md`. Gmail/Calendar production credentials are external setup, not fake connected states.

- [x] Phase 0 — foundation and dataset consolidation: preserve existing data under `dataset/mail` and `dataset/public`; typed models; SQLite account isolation; Python API scaffold.
- [ ] Phase 1 — local NLP: evidence-backed dates/actions, readable document adapters, real NB/SVM/actionability training and grouped evaluation, explicit weak-label provenance.
- [ ] Phase 2 — ingestion: safe dataset import, durable jobs, account-specific Gmail OAuth/token storage, MIME/thread/attachment parsing, cursor recovery/idempotency.
- [ ] Phase 3 — knowledge: profiles/courses, resource links, duplicate detection, cross-email matching, revisions/cancellations and review questions.
- [ ] Phase 4 — personal learning: distinct relevance/importance/participation, scoped feedback, explicit overrides, review answers, no shared-model updates.
- [ ] Phase 5 — calendar: timetable/holiday JSON schemas/prompts, validation/preview/activation, recurring occurrences, conflicts, approved flexible-plan proposals.
- [ ] Phase 6 — conversations/marks: request state, sent-reply resolution, exact verified identity matching, assessment revision tracking.
- [ ] Phase 7 — reminders/briefings: durable in-app delivery, date changes/cancellations, daily/live/weekly source-linked summaries and optional grounded API enhancement.
- [ ] Phase 8 — optional external calendar: separate authorization, provider IDs, external busy intervals, incremental sync and managed-calendar writes without duplication.
- [ ] Phase 9 — complete desktop integration: polished Electron interface for every module, secure preload, Python supervision, persistent worker/scheduler, install/build checks, full-workflow tests and setup documentation. Reconcile every agreed feature against an explicit coverage matrix.

Datasets remain private and out of source control. Unknown-license public documents remain quarantined. Imported weak labels are not gold evaluation labels. The final coverage matrix must distinguish working local features, credential-dependent adapters, and limitations.
