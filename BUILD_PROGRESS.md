# Build progress

## DATA-06 reviewed pilot handoff — 29 October 2026

Added a private finalization gate for two independent pilot reviews and explicit
adjudication. It publishes development labels only after complete validation;
the pinned guide and blank forms remain unchanged. Synthetic finalization
checks and the portable Python suite passed (284 tests, one private research
test deselected). The real forms still have no human-completed labels, so
DATA-06 and reviewed accuracy evaluation remain open. See
[handoff](dataset/ANNOTATION_HANDOFF.md) and
[finalization progress](reports/DATA06_FINALIZATION_PROGRESS.md).

## Desktop navigation verification — 29 October 2026

Guarded page refreshes against stale responses and refreshed the current page
after successful mutations. The isolated real Electron/Python notice-to-assignment
workflow passed three consecutive runs; six desktop unit tests and the frontend
build passed. This verifies the user flow, not model accuracy.

## Local trained models active — 29 October 2026

Plain academic and actionability models from the accepted development split
are active; verified versioned bundles are standby fallbacks. A clear category
rule overrides conflicting predictions from these unreviewed weak models.
Temporary-profile API ingestion and the real Electron workflow passed, and
the desktop remains open. No reviewed accuracy gain is claimed. See
[local activation evidence](reports/LOCAL_MODEL_ACTIVATION_20261029.md).

## Portable launch and recorded verification — 28 October 2026

The Electron backend lifecycle now fails promptly on bad spawn/exit, validates
its health response and waits for child shutdown. A unified verification
command captures machine, commit, dirty-tree state, dependency versions and
lock hashes alongside Python, bridge, build and desktop results. Mac run
`20261028T151353Z-fedc5f8f` passed all checks: **280 Python tests**, six Node
tests, frontend build and real desktop workflow. Windows CI is configured but
has not run; ENV-04/01 remain open. See
[portable launch progress](reports/ENV04_05_PROGRESS.md).

## Verified model bundles and rollback accepted — 28 October 2026

OPS-01/02 now use write-once model manifests, pinned active/previous pointers,
atomic promotion and rollback, pre-load verification, visible health and
rules-only fallback. No real model was promoted. The portable suite passed
**279 tests**, with one private-data test deselected; frontend build, bridge
tests, scoped lint and diff checks passed. See
[bundle acceptance](reports/OPS01_ACCEPTANCE.md).

## Bounded sparse comparison tooling — 28 October 2026

Added the fixed CLS-02 candidate matrix, paired whole-guard fold scorer and a
private immutable development runner. The reviewed wrapper enforces DATA-05
custody and double-reviewed classification labels. Fixture checks pass, but
DATA-06 has no completed human pilot forms, so no reviewed candidate comparison
or model promotion has occurred. The portable suite passed **273 tests**, with
one private-data test deselected; scoped lint and diff checks passed. See
[comparison progress](reports/CLS02_PROGRESS.md).

## Sparse feature candidates accepted — 28 October 2026

Added independently selectable word, character and subject/body TF-IDF
channels. Research loaders can retain separate prepared fields without
changing the current default training path. Fixture tests verify fold-local
vocabulary fitting and independent channel ablation. CLS-01 is accepted as
tooling; reviewed comparison and promotion remain pending. The 270-test
portable suite passed, with one private-data test deselected; lint passed.
See [feature acceptance](reports/CLS01_ACCEPTANCE.md).

## Backward-compatible profile migration accepted — 28 October 2026

New profiles and analyses are versioned. A version 1 profile loads without
schema writes; explicit dry-run migration identifies legacy analyses and
attachment keys. Apply requires a fresh verified SQLite backup. Recovery
restores to a new path after checksum and integrity checks. Fixture replay
preserves a confirmed deadline, and ambiguous Gmail provider identity blocks
duplicate reimport. PIPE-05 is accepted at fixture level; no live profile was
migrated. The 267-test portable suite passed, with one private-data test
deselected; lint passed. See [migration acceptance](reports/PIPE05_ACCEPTANCE.md).

## Document layout and decoding accepted — 28 October 2026

HTML table rows, DOCX document order, PDF page spans and XLSX row/cell spans
now retain source offsets. MIME charset decoding and text-quality status
explicitly stop poor text from creating automatic entities. Attachment
occurrences keep their own locators, and validated date assertions point to
the containing page or cell. PIPE-03 is accepted at fixture level; OCR and a
corpus-wide format audit remain separate. The 263-test portable suite passed,
with one private-data test deselected; lint passed. See
[layout acceptance](reports/PIPE03_ACCEPTANCE.md).

## Shared preprocessing accepted — 28 October 2026

Training, extraction evaluation, research experiments and runtime now share
`source-blocks-v1`: subject/body/attachment blocks, authored and contextual
regions, and source-aligned canonical offsets. The model input is identical
across training and inference; quote-only bodies do not train or score as
authored extraction input. The experiment identity includes this version and
its code. PIPE-02 is accepted at fixture level; OPS-01 still owns model bundle
compatibility. The 258-test portable suite passed, with one private-data test
deselected. See [preprocessing acceptance](reports/PIPE02_ACCEPTANCE.md).

## Attachment occurrences and typed evidence accepted — 28 October 2026

Byte-identical attachments retain parent-specific source dates and separate
analysis messages; provider item IDs also distinguish repeated bytes under one
parent. Runtime extraction now validates exact source spans and persists typed,
versioned field assertions through a legacy adapter. PIPE-04 is accepted at
fixture level. Assignment/event dates now link to the winning assertion;
targeted cancellations and profile values carry exact spans, and manual edits
carry a confirmed origin. PIPE-01 is accepted at fixture level; legacy storage
migration remains PIPE-05. The 255-test portable suite passed; one private-data
test was deselected. See
[attachment acceptance](reports/PIPE04_ACCEPTANCE.md) and
[evidence acceptance](reports/PIPE01_ACCEPTANCE.md).

## Sentence and clause boundaries accepted — 28 October 2026

Protected URL punctuation, decimals and abbreviations while splitting new
explicit obligations after completed clauses. Quoted reply lines are masked
without changing offsets, and quoted history cannot create entities.
Eight focused tests and the 248-test portable suite passed; one
private-data test was deselected. FIX-01 is accepted at fixture level. See
[boundary acceptance](reports/FIX01_ACCEPTANCE.md).

## Cancellation targeting accepted — 28 October 2026

Assignment and event cancellation now uses local clauses and named targets.
Negated, hedged, listed and generic ambiguity routes to review. Candidate
status decisions survive replay, and canceled events leave calendar and
pending reminders. Ten focused tests and the 240-test portable suite passed;
one private-data test was deselected. FIX-04 is accepted at fixture level.
See [cancellation acceptance](reports/FIX04_ACCEPTANCE.md).

## Temporal candidate coverage accepted — 28 October 2026

Added exact-span same-month date ranges, overlap suppression, and review for
cross-month/missing-year ranges, ambiguous time ranges, time-only deadlines
and unsupported relative cues. Subject and body warnings keep separate offsets;
range endpoints never silently become deadlines. Eighteen focused tests and
the 230-test portable suite passed; one private-data test was deselected.
FIX-02 is accepted at fixture level. See
[temporal candidate acceptance](reports/FIX02_ACCEPTANCE.md).

## Relative-date source anchoring accepted — 28 October 2026

Gmail authored dates now anchor relative text only when the header has an
explicit offset; receipt-only timestamps go to review. Historical imports and
attachment analysis carry source timezones and reference trust, including
legacy reimport/replay recovery. Six focused regressions and the 212-test
portable suite passed; one private-data test was deselected. FIX-03 is accepted
at fixture level; FIX-02 candidate coverage was accepted in the later slice above. See
[relative-date acceptance](reports/FIX03_ACCEPTANCE.md).

## Two-notice runtime evaluation increment — 28 October 2026

Added conservative reviewed update/correction pairs to the EVAL-03 adapter,
wrong-target mutation checks, and a private CLI that verifies the pinned
EVAL-01 selection before application replay. Longer chains and unsupported
links are reported as exclusions. Six new synthetic tests and the 206-test
portable suite passed; one private-data test was deselected. EVAL-03 remains
open until reviewed development labels support a real run. See
[runtime evaluation progress](reports/EVAL03_PROGRESS.md).

## Reviewed development protocol increment — 28 October 2026

Pinned the accepted DATA-05 reservation and added blinded-ID-to-guard
verification, deterministic whole-guard development folds, and class/group
support reporting. The experiment runner now requires that verified v2
selection for research runs; v1 selections are fixture-only. The installed
reservation reconciled 7,859 guards and 189 blinded development IDs. Four
protocol tests and the 200-test portable suite passed; one private-data test
was deselected. EVAL-01 stays open until DATA-06 review creates real class
support and fold evidence. See [protocol progress](reports/EVAL01_PROGRESS.md).

## Reproducible development runner accepted — 28 October 2026

Added a pinned rules-only experiment runner and CLI. It validates a development
selection against document/guard IDs, refuses held-out guards and unreviewed
research input, records code, preprocessing, Python and dependency identities,
and publishes owner-only predictions/metrics under a content-derived run ID.
Fixture reruns reproduce byte-for-byte; an existing run cannot be overwritten.
Six focused runner tests and 200 portable tests passed; one private-data test was
deselected. EVAL-05 is accepted as tooling; DATA-06 review and the EVAL-03/06
reviewed baseline are still pending. See [runner acceptance](reports/EVAL05_ACCEPTANCE.md).

## End-to-end evaluation tooling increment — 28 October 2026

Added an isolated rules-only runtime replay scorer for entity/evidence errors,
action status, reply state, review prompts, calendar entries and reminders.
Nine synthetic tests and the full portable suite passed (190 tests; one
private-data test deselected). A conservative double-reviewed v2 adapter now
prepares single-notice cases and reports unsupported links. EVAL-03 remains
open for multi-notice mapping and an actual development run. See
[evaluation progress](reports/EVAL03_PROGRESS.md).

## Component scoring infrastructure accepted — 28 October 2026

The completeness-aware v2 scorer now validates predicted evidence for every
included document, counts duplicate predictions, and excludes unreviewed tasks
from gold denominators. Four synthetic contract tests and the full portable
suite passed (181 tests; one private-data test deselected). EVAL-02 is accepted
as tooling; DATA-06 still has zero completed human pilot reviews and no reviewed
accuracy exists. See [scorer acceptance](reports/EVAL02_ACCEPTANCE.md).

## Queue and direct recovery accepted — 28 October 2026

Legacy running jobs without leases are recoverable, revision-checked final
writes prevent an old worker from replacing a newer lease result, and a
heartbeat renews long-running work. A failure injected between message updates
converged after restart with one assignment and current reminders. Five focused
tests plus Gmail/Calendar external retry checks passed. Direct application
processing now keeps a pending marker until completion; the worker recovers
expired markers after a crash and refreshes reminders. The full portable suite
passed (177 tests; one private-data test deselected). OPS-03 is accepted for
fixture failure paths. See [restart acceptance](reports/OPS03_PROGRESS.md).

## Replay consistency accepted — 28 October 2026

Identical attachment bytes retain separate parent analysis messages and source
timestamps while sharing one blob. Duplicate application reimports preserve
reviewed decisions; equal-time date disagreements require review. Reverse-order
event replay converges, old pending reminders are cancelled after refresh, and
managed-calendar mappings are reconciled when eligibility changes. The portable
suite passed 168 tests. FIX-07 is accepted for supported fixture replay; OPS-03
still owns fault-injected restart behavior. See [replay acceptance](reports/FIX07_PROGRESS.md)
and [schedule progress](reports/APP03_PROGRESS.md).

Timed assignment deadlines export as transparent one-minute markers at the due
time, while untimed deadlines remain transparent all-day markers. Remote edits
require an explicit keep-or-replace review decision. APP-03 is accepted at
fixture level; real-provider acceptance remains in the environment/release
gates.

## Field reconciliation accepted — 28 October 2026

Assignment and event date/status precedence uses field assertion times.
Manual overrides survive replay with explicit conflict choices, and manual
dates move associated time instants to the corrected calendar day. Seven
focused tests and the full portable suite passed (163 tests; one private-data
test deselected). FIX-06 is accepted at fixture level. See
[reconciliation acceptance](reports/FIX06_PROGRESS.md).

## Occurrence identity accepted — 28 October 2026

Unknown-course numbered assignments now use a thread/source-scoped key.
Known cross-thread assignment updates and ambiguous same-title event updates
go to review instead of silently merging or creating another authoritative
occurrence. Explicit terms, legacy candidate review, stored decisions and
replay/API resolution are covered by 16 focused tests; the portable suite
passed 153 tests. FIX-05 is accepted at fixture level. No measured accuracy
gain is claimed. See [identity acceptance](reports/FIX05_PROGRESS.md).

## Sentence and clause boundary increment — 28 October 2026

Replaced punctuation-only sentence matching with source-aligned spans that
preserve URLs, decimals and common abbreviations. Action rules now evaluate
contrasting clauses separately so a completed action does not hide a later
unfinished obligation. FIX-01 was still open at this stage; the later fixture
acceptance appears above. See [boundary progress](reports/FIX01_PROGRESS.md).

## Assignment cancellation scoping increment — 28 October 2026

An assignment now requires local cancellation evidence before its status
changes; multi-assignment ambiguity creates review instead of cancelling all
items. Named-event cancellation is scoped to a unique event sentence; generic
or multi-event notices create review. FIX-04 was still open at this stage for
clause resolution and replay verification; the later acceptance appears above.
See [scoping progress](reports/FIX04_PROGRESS.md).

## Temporal parser correctness increment — 28 October 2026

Added month-first date parsing, mixed AM/PM plus 24-hour time collection,
field-specific subject-date evidence and guarded single-target subject-date
use. Relative dates require timezone-aware source timestamps, including for
readable attachment analysis. Deadline times before dates can link within the
same sentence. FIX-02 and FIX-03 remain open because ranges, ambiguous
multi-target links and replay verification are unfinished. See
[temporal progress](reports/FIX02_FIX03_PROGRESS.md).

## DATA-06 pilot prepared, human review pending — 28 October 2026

Drafted the annotation guide and generated two independent blank forms for
50 available-text notices from 50 development guards. The private pilot is
balanced across linked, short, ordinary and long text, with pinned pack/guide
hashes. Added a strict form audit and completeness-aware component scoring core;
the initial audit correctly reports zero reviewed rows. No reviewer filled a
form or adjudicated labels yet. Development-only weak-label models were trained
from reserved rows, but a fabricated assignment was misclassified; those models
remain research candidates and the app stays in rules-only mode. DATA-06,
EVAL-02 and EVAL-06 stay open. See
[tooling progress](reports/DATA06_EVAL02_TOOLING_PROGRESS.md).

## DATA-05 reservation and DATA-09 source boundaries — 28 October 2026

Reserved all 7,859 provisional split guards with a fixed, score-independent
policy. The ignored private run `data05-20261028-reserved-v2` assigns 6,273
guards to development and 1,586 to sealed holdout. A blinded scoped review
pack contains 189 rows (151 available-text, 38 context-only) from 84 complete
guards; a separate ID-only queue selects 30 holdout guards. A post-publication
check verified all 17,291 memberships, hashes, pack mappings and disjointness.
Training now loads only pinned development rows from scoped mail or Charlie9;
broad mail, Parakweet and quarantined Durg are not pooled into the default
models. No model was trained or accuracy measured. DATA-06 annotation and
reviewed labels are next. See [reservation acceptance](reports/DATA05_RESERVATION_ACCEPTANCE.md).

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
