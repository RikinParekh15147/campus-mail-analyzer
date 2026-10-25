# Research contracts and validation — 25 October 2026

Implements DATA-02 and the streaming-validation portion of DATA-03 from
[ML_IMPROVEMENT_TASKS.md](../ML_IMPROVEMENT_TASKS.md). Source baseline remains
`969143d` plus the current uncommitted foundation and research-contract changes.

## Delivered

- Versioned Pydantic research document contract and matching generated JSON Schema.
- Separate academic-category and binary-actionability targets.
- Task-specific annotation completeness, provenance, reviewer and adjudication metadata; unannotated and reviewed-empty fields are distinguishable.
- Exact Unicode evidence offsets, optional page/sheet/row/cell locators, original-to-canonical mapping checks and local entity-reference validation.
- Explicit dates, date roles, date/time precision, IANA timezones, aware source/reference timestamps and observation cutoffs.
- Preservation of all thread, parent, duplicate, template, leakage and update-family IDs.
- Read-only streaming JSONL validation with bounded line/error handling and a temporary SQLite reference index.
- Cross-document and entity reference checks, timestamp cutoff checks, duplicate-ID detection and contradictory duplicate-label detection.
- SHA-256 input fingerprint, provenance/label/source/annotation coverage counts and redacted line-level error reports.
- `campusmail dataset validate --input PATH [--report PATH] [--max-errors N]`, atomic report saving and input-overwrite protection, including hard links.
- A three-record fabricated example export and [schema/usage documentation](../dataset/RESEARCH_SCHEMA.md).

## Verification

| Check | Result |
|---|---|
| Initial targeted run before implementation | Failed collection as expected: research package did not exist |
| `.venv/bin/python -m pytest tests/test_research_contracts.py -q` | **32 passed** |
| `.venv/bin/python -m pytest -q` | **109 passed, 1 research test deselected** |
| CLI validation of `tests/fixtures/research_v2.jsonl` | **Valid: 3 unique records, zero errors; all synthetic** |
| Schema parity | Checked-in JSON Schema equals `ResearchDocument.model_json_schema()` |
| Undefined-name lint and `git diff --check` | Passed |

The tests cover invalid labels/version/fields, missing review metadata, partial/pending review, Unicode spans, aware timestamps, task separation, forward references, missing references/entities, dataset namespaces, future context, duplicate IDs/labels, original offsets, malformed UTF-8/JSON, duplicate JSON keys, NaN, blank/empty/oversized input, bounded errors, full-input hashes, CLI exit statuses and source-overwrite prevention.

The CLI result is saved locally at ignored `artifacts/verification/research-fixture.json`. No private dataset or credentials were used. The existing Starlette/AnyIO deprecation warning remains unchanged. The desktop suite was not rerun because this phase adds research-only validation and leaves the application processing path unchanged.

## Status and boundaries

**DATA-02 complete:** contracts and fixture-backed structural/reference validation are implemented and tested.

**DATA-03 partial:** JSONL validation streams without reading the full file into memory. Operational imports still use their existing namespace and loader; stable dataset-based import identity, migration and full-corpus validation remain open.

This phase does not authenticate reviewers, prove labels correct, enforce a train/test split, build leakage components, migrate v1 annotations, sanitize original exports or retrain a model. A complete human-review flag is asserted provenance, not independently verified truth. Synthetic records are reported separately. Real research reports should remain private until reviewed for sharing.

The source dataset is never rewritten. Unsupported v1 exports are rejected rather than silently transformed. All invalid references and conflicting duplicate labels make the overall corpus invalid even if individual records pass their structural schema.

## Next implementation work

Complete DATA-03 by designing explicit v1 migration and stable import identities while preserving existing user records. Then implement DATA-04 leakage-component construction on fixture graphs. The teammate can run real-data inventory and provide the sanitized development handoff independently; no large archive transfer to the Mac is required.
