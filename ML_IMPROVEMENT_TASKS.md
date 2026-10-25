# End-to-end ML robustness and accuracy improvement tasks

Source of truth: [ML_ROBUSTNESS_PLAN.md](ML_ROBUSTNESS_PLAN.md). Created 25 October 2026. Checkmarks require completion evidence; implementation progress does not imply measured accuracy gains. The original completed feature phases remain in [IMPLEMENTATION_TASKS.md](IMPLEMENTATION_TASKS.md).

Current progress: foundation and research-contract implementation verified on macOS; ENV-02, ENV-03 and DATA-02 completed. DATA-03 streaming validation, stable collection identities and conservative v1 migration are implemented with fixtures; legacy store migration and full-corpus verification remain open. ENV-01, ENV-04 and ENV-05 are partially implemented and remain unchecked until Windows/CI acceptance evidence exists. See [foundation verification](reports/FOUNDATION_IMPLEMENTATION.md) and [DATA-03 implementation](reports/DATA03_IMPLEMENTATION.md).

## Execution rules

- Complete P0 correctness and measurement work before promoting a new model. Development infrastructure and fixture-based fixes can proceed while annotations are prepared.
- Check a task only after its acceptance evidence exists. Record the commit, commands/results, relevant dataset/split/run IDs, and remaining limitations in the completion log below.
- Use private research exports only for explicitly designated research. Never automatically pool operational user feedback into shared training.
- Keep original data immutable. Keep source/weak labels, human-reviewed labels, synthetic fixtures and public datasets distinguishable.
- Develop against small fixtures on the Mac. Run full-data validation/training on the data owner's Windows machine; transfer only approved sanitized development data and verified artifacts.
- Do not tune on the sealed test. Fit preprocessing, feature selection, models, calibration and thresholds within development boundaries.
- Add focused regression tests for meaningful behavior changes. Run relevant tests and the existing suite; synthetic tests do not establish real-data model accuracy.
- Preserve owner isolation, source evidence, confirmed user overrides and conservative handling of ambiguous dates/identity.

### Ownership and inputs

Owners are suggested responsibilities, not assignments already accepted by team members.

| Code | Owner / input |
|---|---|
| M | You: Mac development, pipeline implementation, tooling and integration |
| W | Teammate: Windows data custody, full-data runs and artifact exports |
| B | Both: annotation, independent review and cross-platform verification |
| E | Named evaluator: sealed-test custody and final evaluation |
| F | Fabricated/public-safe fixtures only; full dataset unnecessary |
| D | Sanitized development pack or reviewed development annotations |
| R | Full designated research data; may stay on Windows |
| T | Sealed reviewed test; evaluator access only |

Task metadata uses **priority · suggested owner · input · dependencies**. A dependency names a task ID; `none` means work can begin immediately. Proposed new files and commands below do not exist until implemented.

## Milestones and sequencing

| Milestone | Task groups | Exit condition |
|---|---|---|
| M0: portable development | ENV | Both machines run the default suite without private data |
| M1: trustworthy benchmark | DATA, EVAL | Reviewed annotations, frozen leakage-safe splits, reproducible baseline |
| M2: correct pipeline behavior | PIPE, FIX | Known failures fixed; source evidence and replay invariants pass |
| M3: improved learned decisions | CLS, EXT, CONF | Development gains measured with uncertainty, coverage and error costs |
| M4: end-to-end integration | APP, OPS, REL | Downstream correctness, artifact verification, shadow evaluation and rollback |
| M5: optional research extensions | ADV | Only techniques justified by remaining measured errors are adopted |

Critical path: `ENV → DATA → EVAL → CLS/EXT → CONF → REL`. In parallel, `ENV → PIPE/FIX → APP/OPS → REL`. ADV is conditional and never blocks a release that already meets its quality gates. Independent work can be divided between teammates; this does not require automated sub-agents.

## 1. Portable development and baseline — WP0

Primary files: `pyproject.toml`, `requirements-linux.lock`, `scripts/setup.sh`, `scripts/setup.ps1`, `backend/campusmail/cli.py`, default tests and `desktop/tests/desktop.spec.cjs`.

- [ ] **ENV-01 — Establish compatible isolated environments.** P0 · B · F · none. Select and test one shared Python minor version and coherent NumPy/SciPy/scikit-learn dependencies; validate platform-specific locks and Windows timezone data. **Done when:** fresh Mac and Windows environments import the numerical stack and report exact installed versions without modifying global Python.
- [x] **ENV-02 — Separate portable and private-data tests.** P0 · M · F · ENV-01. Replace default private-dataset existence assumptions with fixture-backed contract tests; mark full-data/artifact checks explicitly. Inject fake vault/provider dependencies. **Done when:** the default suite needs no private data, credentials or network, while explicitly requested research checks fail clearly on missing inputs.
- [x] **ENV-03 — Add environment and artifact diagnostics.** P0 · M · F · ENV-01. Implement `campusmail doctor` for interpreter/dependency versions, dataset availability, model availability and compatibility. **Done when:** missing inputs have actionable status and no secret values are printed.
- [ ] **ENV-04 — Make launch/build tests platform-aware.** P1 · B · F · ENV-01. Remove the hardcoded Unix Python path in the desktop test; verify setup native-command failures, backend startup and shutdown. **Done when:** each supported platform uses its own environment and reports startup failures clearly.
- [ ] **ENV-05 — Record a clean baseline and automate portable checks.** P0 · B · F · ENV-02, ENV-04. Add a Mac/Windows CI matrix or reproducible local verification scripts; capture Python, bridge and frontend-build results. **Done when:** results identify machine, dependency lock and source commit; historical audit results are not presented as a new run.

## 2. Data contracts, handoff and annotation — WP1

Primary files: `training.py`, `ingestion.py`, `dataset/README.md`, `DATASET_COLLECTION_PROMPT.md`; proposed `backend/campusmail/research/validation.py`, research schema and annotation guide.

- [ ] **DATA-01 — Inventory the actual research corpus.** P0 · W · R · none. Export manifest/hash, actual counts, label/source distribution, annotation provenance, text lengths, missing fields, duplicate conflicts and available context. **Done when:** counts reconcile with source files and no estimate is represented as a measured count.
- [x] **DATA-02 — Implement versioned research contracts.** P0 · M · F · none. Define document IDs, source timestamp/timezone, all grouping relations, source offsets, task-specific label completeness, reviewer/adjudication metadata and typed labels. **Done when:** missing annotations differ from reviewed empty annotations; invalid labels/spans/references are rejected or quarantined with reasons.
- [ ] **DATA-03 — Add streaming validation and stable imports.** P0 · M · F, then R · DATA-02. Validate JSONL incrementally with line-level errors; use manifest dataset IDs rather than absolute machine paths for import identity. Preserve all grouping metadata. **Done when:** relocating the same export does not duplicate imported records; validation preserves original files and reports exclusions.
- [ ] **DATA-04 — Build and audit leakage components.** P0 · M + W · R · DATA-01, DATA-03. Union thread, parent attachment, exact/near duplicate, template and explicit update-family relations; namespace IDs. Audit giant components and contradictory labels. **Done when:** adversarial overlap fixtures stay together and the actual corpus has an auditable component manifest.
- [ ] **DATA-05 — Reserve the test pool and publish a safe development handoff.** P0 · W + E · R · DATA-04. Reserve complete groups using a documented, score-independent policy; export approximately 100–200 development records if available, preserving relationships, plus safe representative attachment fixtures. **Done when:** the Mac pack has no reserved test groups or raw identity map, and manifests/checksums verify its contents.
- [ ] **DATA-06 — Write the annotation guide and double-review a pilot.** P0 · B · D · DATA-02, DATA-05. Independently annotate 40–60 development documents across difficult cases; define primary/secondary categories, action actor/status, date roles, entity links and thread observation cutoffs. **Done when:** disagreements are adjudicated and guide changes/version are recorded.
- [ ] **DATA-07 — Expand reviewed development labels.** P0 · B · D/R · DATA-06. Review classification labels across the small scoped corpus where feasible; target 150–250 deeply annotated development documents subject to available groups. Include real negatives and ambiguous cases. **Done when:** per-task reviewed coverage and independent group counts are reported, with weak labels retained separately.
- [ ] **DATA-08 — Curate the sealed reviewed test.** P0 · E · T · DATA-05, DATA-06. Independently review/adjudicate reserved examples using the finalized guide; maintain separate test labels and completeness flags. **Done when:** test content/labels are versioned and withheld from routine tuning; insufficient class support is disclosed rather than manufactured.
- [ ] **DATA-09 — Preserve public-source task boundaries.** P0 · W · R · DATA-01, DATA-04. Keep academic, corporate actionability and quarantined university data distinct; record Charlie9/Parakweet overlap and reuse/provenance status. **Done when:** training selections enforce permitted sources and no overlapping corpus is claimed as independent evaluation.

## 3. Evaluation and experiment foundations — WP2

Primary files: `evaluation.py`, `training.py`, `scripts/research_report.py`; proposed research split, metric, run-config and report modules.

- [ ] **EVAL-01 — Freeze split manifests and development folds.** P0 · M + E · D/R · DATA-04, DATA-07, DATA-08. Finalize a group-disjoint test allocation only where support permits; create feasible development folds, with stable IDs and no split shopping. **Done when:** every relation stays within its split; class/group support and missing classes are reported.
- [ ] **EVAL-02 — Implement completeness-aware component metrics.** P0 · M · F, then D · DATA-02. Add category metrics, strict span F1, diagnostic one-to-one overlap, date-role F1, action status/actor scores and conditional normalization. **Done when:** invalid offsets cannot silently disappear and unannotated fields cannot become negative gold labels.
- [ ] **EVAL-03 — Evaluate the deployed pipeline end to end.** P0 · M · F, then D · EVAL-02. Replay sources through `Application`/`Engine` into temporary profiles; score entity–action–deadline tuples, false merges, wrong mutations, reply state and resulting calendar/reminders. **Done when:** wrong-target, missed and spurious tuples are counted even when category prediction is correct.
- [ ] **EVAL-04 — Add slices, uncertainty and cost reporting.** P0 · M · D · EVAL-01, EVAL-02, EVAL-03. Report per-class/source/length/layout/language slices, group-bootstrap intervals, paired candidate differences and abstention coverage. **Done when:** every headline score has support, dataset/split identity and meaningful limitations; tiny slices are flagged.
- [ ] **EVAL-05 — Build a reproducible experiment runner.** P0 · M · F/D · EVAL-01, ENV-03. Add configurable data/config/output paths, immutable run IDs, seeds, preprocessing versions, dependency hashes and prediction outputs. **Done when:** fixture runs reproduce and research runs do not overwrite deployed artifacts; private predictions stay private.
- [ ] **EVAL-06 — Reproduce and freeze the current baseline.** P0 · W · R/D · EVAL-04, EVAL-05, DATA-09. Evaluate majority, existing NB/SVM, rules and full runtime on the new development protocol. **Done when:** baseline errors and reports are saved; historical weak-label metrics remain separately labeled.
- [ ] **EVAL-07 — Add chronological and source-transfer audits.** P1 · M + W · R/D · EVAL-01, EVAL-05. Define forward-time cutoffs and, if data supports it, held-out source/institution audits; purge or disclose boundary-spanning families. **Done when:** thread features contain no future replies and claims match actual source coverage.

## 4. Shared preprocessing and evidence contracts — WP3

Primary files: `nlp.py`, `documents.py`, `ingestion.py`, `engine.py`, `application.py`; proposed `contracts.py` and `preprocessing.py`.

- [ ] **PIPE-01 — Introduce typed candidates and field assertions.** P0 · M · F · DATA-02. Include source document/field/span, exact text, locator, value, method/version, uncertainty and optional calibrated score. **Done when:** evidence validates and the old engine interface can consume candidates through a compatibility adapter.
- [ ] **PIPE-02 — Unify training, evaluation and runtime preprocessing.** P0 · M · F/D · PIPE-01. Preserve subject/body/attachment blocks, authored/quoted/signature regions and canonical-to-source maps. **Done when:** all paths use a versioned common contract while quoted history remains available for contextual linking.
- [ ] **PIPE-03 — Preserve document layout and decoding context.** P1 · M · F/D · PIPE-01. Handle MIME charsets, HTML table boundaries, DOCX block order, PDF page offsets and XLSX cell/row locators. Add text-quality indicators. **Done when:** representative formats retain usable evidence and poor extraction triggers an explicit status.
- [ ] **PIPE-04 — Separate attachment blobs from contextual occurrences.** P0 · M · F · PIPE-01. Keep byte deduplication, but key analysis occurrences by parent/context and propagate original source dates. **Done when:** identical bytes under different parents preserve both contexts and do not overwrite provenance.
- [ ] **PIPE-05 — Define backward-compatible storage migration.** P1 · M · F · PIPE-01, PIPE-04. Version analysis payloads and add migrations/reanalysis rules for existing profiles. **Done when:** a fixture of the old database loads safely, confirmed edits survive, and migration has a tested backup/recovery procedure.

## 5. Known correctness defects — WP3

Each task includes a regression case that demonstrates the existing failure before the fix. These can be developed using fixtures while research annotation continues.

- [ ] **FIX-01 — Fix sentence and clause boundaries.** P0 · M · F · PIPE-02. Preserve URLs/abbreviations/decimals and clause offsets; scope negation/completion locally. **Done when:** a URL does not truncate an action and “already registered, but must upload…” retains the unfinished obligation.
- [ ] **FIX-02 — Fix temporal candidate coverage.** P0 · M · F · PIPE-02. Support month-first dates, mixed AM/PM and 24-hour times, subject dates, time-before-date and supported ranges; flag unsupported temporal cues. **Done when:** “October 25, 2026” and mixed-format times are preserved, overlapping matches deduplicate, and missing years/times remain unresolved.
- [ ] **FIX-03 — Anchor relative dates correctly.** P0 · M · F · FIX-02, PIPE-04. Use source timestamps/timezones for body and attachment dates. **Done when:** historical imports and timezone-boundary cases do not use processing time or silently invent a reference date.
- [ ] **FIX-04 — Restrict cancellation to the referenced entity.** P0 · M · F · PIPE-01, FIX-01. Resolve cancellation evidence to its assignment/event before mutation. **Done when:** cancelling Assignment 1 leaves Assignment 2 active; ambiguous targets create review.
- [ ] **FIX-05 — Resolve assignment and event occurrence identity.** P0 · M · F · PIPE-01. Include term/course/thread/explicit references in matching; avoid unknown-course number collisions. **Done when:** ambiguous reschedules cannot create an authoritative third occurrence or incorrectly merge two existing occurrences; unrelated terms stay separate.
- [ ] **FIX-06 — Reconcile per-field assertions and all user overrides.** P0 · M · F · FIX-04, FIX-05, PIPE-05. Apply a shared precedence/conflict policy to assignments and events; track field-specific source times. **Done when:** newer informational mail cannot suppress an intermediate deadline correction and manual dates/statuses survive replay with conflicts surfaced.
- [ ] **FIX-07 — Prove replay and downstream consistency.** P0 · M · F · FIX-03, FIX-06, PIPE-04. Replay duplicates, reverse-order imports, corrections and attachment/body variants. **Done when:** final records are consistent under supported replay orders, with no duplicate entities, stale reminders or lost evidence; ambiguity remains explicit.

## 6. Strong supervised classification baselines — WP4

Primary files: `training.py`, `nlp.py`; proposed `classification.py`, research feature/config modules. These tasks change classification, not all extraction behavior automatically.

- [ ] **CLS-01 — Implement feature candidates.** P1 · M · F/D · PIPE-02, EVAL-05. Compare word TF-IDF, character `char_wb` TF-IDF and subject/body channels; retain negation, identifiers and useful temporal cues. **Done when:** vocabulary fitting remains fold-local and each feature change can be ablated independently.
- [ ] **CLS-02 — Run a bounded sparse-model comparison.** P1 · W · R/D · CLS-01, EVAL-06. Compare existing NB/SVM with feature-enhanced LinearSVC, logistic regression and ComplementNB using predeclared parameter budgets. **Done when:** all candidates use identical folds; class weighting and masking are measured rather than assumed helpful.
- [ ] **CLS-03 — Diagnose errors and data shortcuts.** P1 · B · D · CLS-02, EVAL-04. Inspect minority classes, placeholder IDs, sender/template shortcuts, long documents and multi-topic examples; produce learning curves. **Done when:** the next action is justified as a label, preprocessing, model or policy change, with no sealed-test error inspection.
- [ ] **CLS-04 — Freeze a development champion.** P1 · B · D · CLS-03. Select using macro-F1, class regressions, uncertainty and runtime cost; retain the existing model as a rollback candidate. **Done when:** the selection rationale and exact run/config IDs are recorded before final test evaluation.

## 7. Learned actions, dates and relationships — WP5

Primary files: `nlp.py`, `engine.py`, `trackers.py`; proposed `action_detection.py`, `temporal.py`, `linking.py`.

- [ ] **EXT-01 — Detect actions across all eligible authored sentences.** P0 · M · F/D · FIX-01, EVAL-03, DATA-07. Remove the dependency on rule-detected action candidates; include subject/neighbor/recipient/quote context. **Done when:** learned inference can recover a required action absent from the regex candidates, with valid evidence offsets.
- [ ] **EXT-02 — Train and evaluate campus action attributes.** P1 · W + M · D/R · EXT-01, EVAL-05. Separate action detection, actor, requiredness, optionality, completion and negation; preserve the public corporate baseline as a separate experiment. **Done when:** campus metrics and domain-transfer errors are reported; a positive corporate label cannot directly create a compulsory task.
- [ ] **EXT-03 — Learn temporal roles and normalize deterministically.** P1 · M + W · D · FIX-02, FIX-03, EVAL-05. Score marked date/context candidates for deadline/event/exam/publication roles; preserve ambiguity and date precision. **Done when:** role-aware and full-tuple metrics improve on development data without invented values.
- [ ] **EXT-04 — Link actions, dates, entities and resources.** P1 · M · D · EXT-02, EXT-03, FIX-05. Use sentence/section/table structure and contextual entity identity; distinguish updates, corrections, support and possible supersession. **Done when:** multi-event/multi-assignment notices retain the correct links and ambiguous links go to review.
- [ ] **EXT-05 — Measure extraction gains end to end.** P0 · B · D · EXT-04, EVAL-04, FIX-07. Compare old rules, rules with fixes, learned components and combined pipeline. **Done when:** reports separate candidate recall, final tuple quality, wrong mutations and review coverage; no gain is inferred from classification alone.

## 8. Calibration, uncertainty and decision policy — WP4/WP5

Primary files: classification/action/temporal modules, `personalization.py`, `engine.py`; proposed policy/calibration configs.

- [ ] **CONF-01 — Generate leakage-safe calibrated predictions.** P1 · M + W · D · CLS-04, EVAL-05. Compare sigmoid-calibrated SVM with logistic predictions; nest calibration within outer training folds and retain group boundaries. Extend to learned extraction scores where supported. **Done when:** calibration reliability, Brier/log loss and coverage are reported; raw margins are never labeled probabilities.
- [ ] **CONF-02 — Choose task-specific decision thresholds.** P0 · B · D · CONF-01, EXT-05. Optimize on development predictions against false deadlines, missed obligations and review capacity; define small-support fallback behavior. **Done when:** thresholds/configs are frozen and automatic mutations require valid evidence and resolved identity in addition to confidence.
- [ ] **CONF-03 — Add unsupported-input and shift handling.** P1 · M · F/D · CONF-02. Evaluate novel topics, nonacademic mail, language shifts, low vocabulary coverage, long text and model disagreement. **Done when:** unsupported cases have visible fallback/review behavior; shift heuristics are not represented as guaranteed detectors.
- [ ] **CONF-04 — Keep personal policy distinct from extracted facts.** P0 · M · F/D · CONF-02, FIX-06. Separate academic relevance, student applicability, participation, priority and urgency; retain confirmed enrollment and overrides. **Done when:** uncertain enrollment does not suppress a real obligation and model preference cannot override confirmed user choices.

## 9. Downstream product accuracy — WP5/WP7

Primary files: `trackers.py`, `calendar.py`, `external_calendar.py`, `briefings.py`, `summary_api.py`, `api.py`, `desktop/src/main.jsx`.

- [ ] **APP-01 — Improve request-state tracking.** P1 · M · F/D · EXT-02, EVAL-03. Normalize timestamps to instants; track each request/actor and observation cutoff; require evidence of resolution rather than shared keywords. **Done when:** partial replies, delayed commitments, broadcasts, CC-only mail and manual resolutions behave correctly in annotated thread snapshots.
- [ ] **APP-02 — Preserve marks identity and table correctness.** P0 · M · F/D · PIPE-03, FIX-06. Extend fixtures for leading zeros, multiple assessments, ambiguous headers, revised scores and absent/withheld values. **Done when:** no unconfirmed student match is accepted and ambiguity never becomes guessed scores/totals.
- [ ] **APP-03 — Propagate validated schedule changes consistently.** P0 · M · F · FIX-07, CONF-04. Update internal calendar, external mapping and reminders together; preserve all-day end ranges and distinguish due markers from busy intervals. **Done when:** cancellations/reschedules remove obsolete output and remote eligibility changes do not leave stale exported commitments.
- [ ] **APP-04 — Strengthen schedule contracts and timezone consistency.** P1 · M · F · ENV-04. Validate timetable exceptions, generate schema/prompt copies from canonical definitions, and use profile timezone for frontend today/date views. **Done when:** schema drift and timezone-boundary fixtures pass on both OSes.
- [ ] **APP-05 — Validate summary facts and fallback.** P1 · M · F/D · APP-03. Test changed dates, reordered numeric values, incorrect participation and unsupported obligations, beyond numeric-token membership. **Done when:** canonical facts remain authoritative and invalid enhancement falls back without changing stored records.
- [ ] **APP-06 — Improve evidence and review workflows.** P1 · M · F/D · PIPE-01, CONF-04. Show source highlights, uncertainty reasons, model/rules-only status, alternatives and pending conflicts; allow source date for pasted notices. **Done when:** a student can understand and correct the actual uncertain field, and irrelevant acknowledgments cannot silently resolve factual conflicts.

## 10. Artifacts, scaling and operational reliability — WP7

Primary files: `store.py`, `jobs.py`, `application.py`, `cli.py`, API model endpoints and packaging scripts; proposed `model_registry.py`.

- [ ] **OPS-01 — Add immutable model bundles and verification.** P0 · M · F · EVAL-05, PIPE-01. Store taxonomy, preprocessing/schema versions, dependency/model revisions, checksums, metrics and thresholds. Validate trusted bundles before loading. **Done when:** wrong taxonomy, incompatible preprocessing or corrupt artifacts are rejected with visible model health.
- [ ] **OPS-02 — Implement atomic promotion and rollback.** P0 · M · F/D · OPS-01, PIPE-05. Use active/previous manifest pointers and explicit analysis versions rather than overwriting experiment files. **Done when:** interrupted promotion cannot leave a partially active bundle and rollback preserves confirmed user edits.
- [ ] **OPS-03 — Make processing transactional and restartable.** P0 · M · F · FIX-07, PIPE-05. Commit related record updates with durable downstream work; add checkpoints, job lease renewal and source/version idempotency. **Done when:** failure injection/restart produces no duplicate entities or permanently stale reminders.
- [ ] **OPS-04 — Profile and reduce scaling bottlenecks.** P1 · M + W · F/R · DATA-03, EVAL-05. Replace repeated full-store scans with bounded indexed queries, stream imports, batch inference and cache by input/model version. **Done when:** measured memory/latency reports cover realistic mailbox sizes and cache invalidation preserves correctness.
- [ ] **OPS-05 — Add shadow inference and monitoring.** P1 · M · D · OPS-01, CONF-03. Compare champion/challenger without mutating live records; track correction/abstention rates, unreadable inputs, source mix and latency. **Done when:** disagreements are reviewable and monitoring never silently retrains from operational feedback.

## 11. Conditional advanced-model experiments — WP6

These are optional experiments, not required infrastructure. Each needs an explicit development error analysis and a bounded compute/annotation budget before starting. A rejected experiment may be closed with its evidence; it does not need deployment to count as completed research.

- [ ] **ADV-01 — Frozen semantic embeddings plus a linear head.** P2 · W + M · D/R · CLS-03, EVAL-05. Compare MiniLM with the sparse champion; preserve subject and chunk long documents with documented pooling. **Done when:** paired metrics, long-text behavior, memory and latency justify adopting or rejecting it.
- [ ] **ADV-02 — SetFit few-shot comparison.** P2 · W · D/R · ADV-01. Generate training pairs only within training folds; record pretrained model revision and seed variability. **Done when:** gains are evaluated against reviewed labels with the same folds and resource budget.
- [ ] **ADV-03 — Sparse/semantic ensemble.** P2 · W · D · ADV-01 or ADV-02, CONF-01. Proceed only for complementary errors; fit blending on development out-of-fold predictions and recalibrate. **Done when:** gain and deployment overhead are measured without test leakage.
- [ ] **ADV-04 — Active-learning annotation loop.** P2 · B · D/R · CLS-03, EXT-05. Select uncertainty/disagreement plus diversity and random audit examples, excluding sealed groups. **Done when:** learning curves compare added label cost and performance; evaluation does not consist only of selected hard examples.
- [ ] **ADV-05 — Weak supervision or pseudo-labeling.** P2 · W + B · R/D · ADV-04. Use permitted development data, preserve provisional provenance, account for correlated rules and cap class imbalance. **Done when:** reviewed development ablations demonstrate benefit and synthetic/weak labels never become gold test truth.
- [ ] **ADV-06 — Optional OCR and multilingual support.** P2 · M + W · D · PIPE-03, CLS-03. Quantify affected documents first; benchmark bounded local OCR and, separately, language-specific/multilingual models. **Done when:** page/box evidence, language slices, resource limits and unsupported cases are reported before enabling the feature.
- [ ] **ADV-07 — Advanced span/relation model or retrieval-assisted extraction.** P2 · W + M · D/R · EXT-05. Compare a compact token/span model only if role/linking errors justify it; retrieve context within owner/time boundaries. **Done when:** end-to-end tuple/link quality improves and similarity alone never authorizes merging or supersession.
- [ ] **ADV-08 — Teacher-assisted annotation or constrained LLM fallback.** P2 · B · D · EXT-05, CONF-02. Keep teacher output provisional, validate evidence, and separate external-data consent from optional summary wording. **Done when:** human adjudication and unsupported-fact rates are recorded; generated suggestions cannot directly mutate authoritative records.
- [ ] **ADV-09 — Deployment compression or conformal sets.** P2 · M + W · D · a proven advanced candidate, CONF-01. Evaluate compression only for a measured resource bottleneck; evaluate prediction sets only with sufficient calibration data. **Done when:** compression preserves agreed quality/calibration, or sets report empirical coverage/size and drift limitations. Split these into separate implementation tickets if both are pursued.

## 12. Release and research reporting

- [ ] **REL-01 — Ratify achievable release targets.** P0 · B + E · D · EVAL-06, EVAL-04. Review the provisional targets below against label quality, support and review capacity. **Done when:** promotion rules and acceptable class-level regressions are written before inspecting final-test results.
- [ ] **REL-02 — Freeze the full candidate pipeline.** P0 · B · D · CLS-04, EXT-05, CONF-04, APP-01 through APP-06, OPS-01 through OPS-05, REL-01. Include any selected ADV outputs; lock code, data, models, thresholds and preprocessing. **Done when:** development gates pass and the exact candidate can be recreated.
- [ ] **REL-03 — Run the sealed end-to-end evaluation.** P0 · E · T · REL-02, DATA-08. Run once for release reporting; publish aggregate metrics, group confidence intervals, coverage and source limitations. **Done when:** no threshold/model changes are made using these results; subsequent tuning reclassifies the set as development or requires a new holdout.
- [ ] **REL-04 — Validate packages and inference parity.** P0 · B · F + verified artifact · REL-02, ENV-04, OPS-02. Run backend/bridge/build tests, frozen sidecar and desktop workflow on each target OS; compare reference predictions and numeric tolerances. **Done when:** startup, model failure, review, source evidence, restart and rollback work on both machines without the training corpus.
- [ ] **REL-05 — Publish the final project evidence.** P1 · B · aggregate results · REL-03, REL-04. Update README, feature coverage, build progress and a new research report/model card. **Done when:** results distinguish old weak-label scores, new reviewed scores, synthetic tests, accepted/rejected experiments and remaining limitations; raw private examples are excluded.

## Provisional acceptance scorecard

These are planning targets from the source plan, not current results or guaranteed outcomes. REL-01 must ratify them. A small test may be insufficient to substantiate high precision; always report counts, independent groups and intervals. Report review coverage so abstention cannot conceal poor recall.

| Dimension | Proposed gate | Evidence producer |
|---|---|---|
| Category quality | +0.05 absolute macro-F1 over the reproduced baseline on the same reviewed protocol, with class regressions inspected | CLS-04, REL-03 |
| Required actions | Recall ≥0.90, with precision and review volume reported | EXT-05, REL-03 |
| Automatic deadline tuples | Precision ≥0.98 at disclosed coverage; zero invented missing times in acceptance fixtures | CONF-02, REL-03 |
| Entity changes | Zero known wrong-target cancellations, stale reschedules or override losses in regression suite | FIX-07, APP-03 |
| Evidence | Every committed extracted field has valid evidence/structured locator or an explicit user-confirmed origin | PIPE-01, EVAL-03 |
| Review burden | Initially budget 20–30 reviews per 100 messages; adjust to real error costs | CONF-02, OPS-05 |
| Performance | Initial short-text CPU p95 target <500 ms, excluding network/OCR; specify document size and hardware | OPS-04 |
| Portability | Default tests require no private archive; packages infer on both supported OSes | ENV-05, REL-04 |
| Recovery | Deterministic supported replay, no duplicate entities, verified artifact rollback | FIX-07, OPS-02, OPS-03 |

## First work batch

Start with these tasks; do not wait for the full archive to arrive on the Mac:

| Sequence | Task | Immediate output |
|---|---|---|
| 1 | ENV-01 | Agreed isolated environment and version report |
| 2 | ENV-02 | Portable default test suite |
| 3 | DATA-01 | Teammate's actual corpus manifest |
| 4 | DATA-02 | Fixture-tested schema and completeness rules |
| 5 | ENV-03 | Actionable diagnostics |
| 6 | DATA-03, DATA-04 | Validated data and complete leakage groups |
| 7 | DATA-05, DATA-06 | Safe development handoff and annotation pilot |
| 8 | PIPE-01, PIPE-02 | Shared candidate/preprocessing contracts |
| 9 | FIX-01 through FIX-07 | Regression-backed correctness fixes |
| 10 | DATA-07, DATA-08, EVAL group | Reviewed benchmark and reproducible baseline |

Do not interpret this sequence as requiring all annotation work to finish before fixture-based fixes. After the baseline, run CLS and EXT work, calibrate policy, then freeze/evaluate the release. Schedule advanced experiments only where development evidence justifies them.

## Completion log

For every checked task, add a row here. For research tasks, include the immutable run ID and dataset/split hashes. For rejected optional experiments, record the rejection evidence and resulting decision.

| Task ID | Owner | Commit / run ID | Verification / result location | Remaining limitation | Completion date |
|---|---|---|---|---|---|
| ENV-02 | Mac implementation | Working tree based on `969143d` | [Foundation verification](reports/FOUNDATION_IMPLEMENTATION.md): 77 portable Python tests; explicit research preflight failure | Windows run pending in ENV-01/04/05 | 2026-10-25 |
| ENV-03 | Mac implementation | Working tree based on `969143d` | Six diagnostic tests; doctor exits successfully in isolated environment and reports rules-only mode | Model metadata checks do not replace OPS-01 artifact verification | 2026-10-25 |
| DATA-02 | Mac implementation | Working tree based on `969143d` | [Research-contract verification](reports/RESEARCH_CONTRACT_IMPLEMENTATION.md): 32 targeted tests; 109 total tests passed | Actual corpus validation, v1 migration and split construction remain separate tasks | 2026-10-25 |
