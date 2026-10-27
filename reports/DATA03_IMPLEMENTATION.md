# DATA-03 implementation checkpoint — 25 October 2026

**Superseded acceptance status:** DATA-03 was completed against the installed corpus
on 27 October 2026. See [the final corpus acceptance report](DATA03_CORPUS_ACCEPTANCE.md).
The limitations below describe the earlier checkpoint.

## Implemented

- Operational `import_dataset` reads JSONL one line at a time. Its source key is a
  SHA-256 digest of the explicit `(dataset_id, document_id)` pair, independent of
  file location. Built-in collection IDs and relative paths live in the checked-in
  `dataset_collections.json` manifest. The import retains thread, parent, duplicate,
  template, leakage and update family identifiers.
- `dataset migrate-v1` accepts explicit source identity, task, origin and usage
  declarations. It preserves the original input and legacy extras/provenance in
  the candidate v2 record. It never promotes old labels to complete human review.
  Unsupported label values, ambiguous source boundaries and invalid v2 references
  fail publication. Temporary output is validated as a complete JSONL corpus
  before atomic replacement of the requested output.
- v2 validation remains read-only and reports line-level exclusions/errors without
  copying document text into its report.

## Verification

On macOS with Python 3.12, the portable test suite passed: **117 passed, 1 private
research test deselected**. Focused migration/import tests cover relocation without
duplicate store records, namespacing across collection IDs, grouping retention,
conservative label provenance, complete-corpus duplicate rejection, output safety,
private text omission from error reports and the CLI entrypoint. Ruff selected
undefined-name checks and `git diff --check` passed. These tests use fabricated
records; they do not measure model accuracy.

## Remaining acceptance work

The data owner must inspect the actual legacy field inventory and run conversion
and validation on the Windows corpus. Stable IDs in the manifest must be matched
to the true source export versions. Existing profile databases imported before
this change use path-derived source keys; reimporting those exports would create
new message records. A deliberate, backup-backed store identity migration is
needed before reimport into such profiles. DATA-03 remains unchecked until the
actual corpus and exclusion counts are reconciled.
