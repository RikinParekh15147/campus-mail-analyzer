# Build progress

## DATA-04 leakage components accepted — 27 October 2026

Built pinned, private membership for all 17,291 records: 8,068 trusted components
and 7,859 conservative split guards. Linked scoped/broad source identities,
threads, parents, exact/near duplicates, templates and explicit relation edges.
Audited one legitimate 142-row thread component, 124 broad subject-based legacy
groups spanning trusted components, and conflicting weak labels. A separate
postcheck verified 48,995 references with zero errors. **138 tests passed with
research inputs enabled**. DATA-04 is checked complete; DATA-05 must allocate
whole split guards until soft links are reviewed. See
[component acceptance](reports/DATA04_COMPONENT_ACCEPTANCE.md).

## DATA-01/DATA-03 accepted on the installed corpus — 27 October 2026

Audited all five designated JSONL sources, original asset hashes and the full
2,376-file notice archive inventory. Published 17,291 v2 records with all source
counts/relationships retained; unavailable-text records remain context-only.
Operational import stages/validates before mutation, preserves existing analysis,
and supports an explicit backup-backed legacy identity migration. Real-file
relocation/reimport created zero duplicates or revisions across 4,590 usable mail
records. Tests: **129 portable passed; 130 passed with research checks enabled**.
DATA-01 and DATA-03 are checked complete; DATA-04 leakage components are next.
See [measured findings and acceptance evidence](reports/DATA03_CORPUS_ACCEPTANCE.md).

## Stable research import identity and explicit legacy migration — 25 October 2026

Implemented the next DATA-03 increment. Operational JSONL import now streams records
and uses collection IDs from `dataset_collections.json` with document IDs for stable
identity across file relocation. Group IDs survive import. An explicit `dataset
migrate-v1` command converts the known legacy export shape to v2, retains old
metadata, downgrades inherited labels to partial weak annotations, and atomically
publishes only after complete v2 validation. The Mac suite has **117 passed, 1
private research test deselected**. No actual private corpus or Windows run was
available. Existing stores with path-derived source keys need a separate identity
migration before reimport; DATA-03 remains open. See
[DATA-03 implementation report](reports/DATA03_IMPLEMENTATION.md).

## Research contracts and validation — 25 October 2026

Completed DATA-02: typed v2 research schema, per-task annotation completeness,
evidence/time/reference validation and a read-only streaming JSONL validator/CLI.
Added 32 targeted tests; full Mac suite now **109 passed, 1 research test deselected**.
The fabricated example export validates with zero errors and remains explicitly
synthetic. No real-data validation, training or accuracy improvement is claimed.
See [research-contract verification](reports/RESEARCH_CONTRACT_IMPLEMENTATION.md).

## ML improvement foundation — 25 October 2026

Implemented portable test isolation, opt-in private-data checks, read-only setup/model
diagnostics, Python 3.12 setup constraints, platform-aware desktop test paths and a
Mac/Windows CI matrix. New Mac verification: **77 Python tests passed**, one private
research test deselected; **2 bridge tests passed**, frontend build passed, and the
real Electron/Python workflow **passed (1 test)** without datasets or model artifacts.
The explicit research check fails clearly when inputs are absent. Windows and remote
CI execution remain pending; no accuracy gain is claimed. See
[foundation verification](reports/FOUNDATION_IMPLEMENTATION.md) and
[ML task status](ML_IMPROVEMENT_TASKS.md).

## Phase 0

- Tests written first in `tests/test_phase0.py`; initial run failed because the repository module did not exist.
- Implemented owner-scoped transactional SQLite storage, revision history, hashed application sessions and typed notice input.
- Consolidated all existing data under `dataset/` with same-filesystem renames; kept private/sanitized/quarantined boundaries.
- Foundation unittest run: 3 tests passed. The final pytest suite covers the same three foundation behaviors without duplicate wrappers.
- Implementation choice: the local repository uses Python's SQLite driver behind a storage boundary rather than requiring SQLAlchemy for core operations. Remote deployment remains a future repository adapter.

## Phase 1

- Tests written first for separate date roles/evidence, ambiguous-date abstention, negated actions, readable/unsupported resources, and duplicate-safe model splits.
- Initial run failed on missing implementation. Local extraction tests and grouped model-training tests now pass.
- Trained actual academic models on 438 scoped source-labeled examples, and separate actionability models on 3,655 Charlie9 sentences. SVM macro-F1: 0.481 academic and 0.802 actionability. Scores are preliminary source-label agreement.

## Phases 2–8

Each phase's tests were written and run failing on its missing module before implementation; the corresponding behavioral gate then passed.

- Phase 2: MIME/HTML parsing, scoped/idempotent dataset imports, durable jobs, read-only Gmail adapter, OS vault, history expiry recovery and bounded older-context searches.
- Phase 3: identity evidence/review, courses, multiple assignments/events, cross-email resources, content/byte duplicate signals, revisions/cancellations, attachment-only notices and exact supported times.
- Phase 4: private accept/correct feedback, preference weights, override preservation, stale-revision rejection, deferred questions and obsolete-question resolution. Shared research models remain separate.
- Phase 5: schema-driven timetable/holiday imports, batch and time validation, activation, recurrence, holidays, due markers, conflicts and approval-based flexible-block moves.
- Phase 6: outstanding requests, selective sent-reply resolution, persistent user resolutions, confirmed-roll marks tracking, absent vs zero, and ambiguous-row abstention.
- Phase 7: durable in-app reminders, changed-date cancellation, source-linked daily/live/weekly summaries, personal timezone, optional API transport/validation/cache and local fallback.
- Phase 8: real Google Calendar adapter with deterministic event IDs, managed-calendar writes, external busy events and incremental-token recovery. Provider behavior tested with deterministic fake transports; live authorization remains external setup.

## Phase 9 — final verification

- Implemented all desktop screens, narrow context-isolated preload, Python supervision, native file pickers, protected downloads, external-browser links and profile switching.
- Real Electron/real Python workflow passed: profile creation, notice analysis, identity confirmation, marks extraction, timetable preview/activation, actual conflicting work block, suggested move and explicit approval, plus navigation through all screens.
- Python source has been formatted and checked for undefined names. Research extraction agreement and classifier reports are saved in `reports/PRELIMINARY_RESULTS.md`; no human-reviewed gold scores are claimed.
- Source development app runs with the private My campus profile seeded from 50 existing scoped records.
- Final Python suite: **69 passed**; undefined-name/syntax lint passed. Desktop bridge security suite: **2 passed**. Production frontend build passed.
- Standalone frozen Python smoke check passed against a clean temporary profile, including actual trained inference, exact deadline time, local timezone, prompt schema, ambiguous marks abstention and dashboard access. This check caught SciPy's dynamically imported compatibility module; the build recipe now explicitly collects it.
- Linux unpacked Electron distribution built successfully. The full real-desktop workflow also passed against the **packaged executable** (1 test, 19.3 seconds), covering notice analysis, identity/marks, timetable activation, conflict proposal/approval and every screen. Build outputs stay ignored.
- Latest development app restarted with the existing private profile. Windows-native/signing and live Google/paid-provider checks are not claimed from this Linux/WSL environment.

See `FEATURE_COVERAGE.md` for every requirement, implementation boundary and deferred/external prerequisite.
