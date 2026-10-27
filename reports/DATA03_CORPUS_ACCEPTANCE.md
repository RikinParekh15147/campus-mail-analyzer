# Installed corpus audit and DATA-03 acceptance — 27 October 2026

DATA-01 (actual corpus inventory) and DATA-03 (streaming validation and stable
imports) are complete for the pinned snapshots in `research_sources.json`.
This is data infrastructure acceptance, not completion of the reviewed benchmark
milestone or evidence of improved model accuracy.

## Measured corpus

| Source | Original records | Nonblank text | Context-only unavailable text | Label status |
|---|---:|---:|---:|---|
| Scoped mail | 575 | 439 | 136 | 438 AI/weak category labels; no reviewed gold |
| Broader mail | 8,292 | 4,151 | 4,141 | 4,151 usable-text AI/weak category labels |
| Charlie9 | 3,655 | 3,655 | 0 | Binary source labels; no project review |
| Parakweet | 4,649 | 4,649 | 0 | Binary source labels; no project review |
| Durg inspection sample | 120 | 22 | 98 | Unlabeled; all remain quarantined |
| **Total** | **17,291** | **12,916** | **4,375** | Sources kept separate |

Nonblank text is a structural count, not a text-quality certification: only 20 of
120 Durg samples have the source's useful-extraction status; 11 are truncated.
The 2,476-entry notice catalogue is metadata, not another 2,476 labeled documents.
Two official institutional PDFs and three recorded download failures remain
separate from these research exports. Raw provider caches and ID maps were not
promoted into research/training inputs.

## Findings that change the ML strategy

1. **Scoped and broad mail are overlapping snapshots.** All 575 scoped document
   IDs also occur in broad mail; message IDs, thread IDs, timestamps and source
   types match for those records. Only 26 normalized bodies match exactly because
   sanitization/extraction changed. Text-hash deduplication alone would miss this
   leakage. Keep their shared source family together; do not use one as an
   independent test corpus for the other.
2. **Public actionability sources contain conflicting alternative annotations.**
   They share 3,644 normalized texts; 749 have different source labels. Charlie9
   has 2,403 negative/1,252 positive rows, Parakweet 2,621 negative/2,028 positive.
   Choose a declared annotation source or adjudicate conflicts. Their overlap
   makes cross-source train/test evaluation invalid without grouped separation.
3. **All mail labels are unreviewed.** The 84-row human-review sample is a selection
   list with category/source/reason columns, not completed human annotations. The
   scoped review queue contains 16,957 entries; broad contains 53,344. Empty weak
   annotation arrays cannot serve as reviewed negatives. No migrated task claims
   complete human review.
4. **Class support is limited.** Scoped nonacademic-other has only two labeled
   examples in two declared groups; scholarships has 17, assignments 25. Reliable
   class-wise testing needs reviewed support and explicit uncertainty. Broader
   weak labels do not automatically solve this problem.
5. **Extraction quality is a major bottleneck.** Scoped mail has 135 unavailable
   attachments and one whitespace-only message. Broad has 4,120 unavailable
   attachments plus 21 whitespace-only messages; counting only `text == ""`
   underestimates unusable input. Scoped attachment statuses are 143 extracted,
   120 image-only, 11 no-text, four unsupported. Broad extraction remains pending
   for 4,020 attachments.
6. **Long/decoded text needs deliberate treatment.** Scoped median text length is
   1,386 characters, p95 40,272 and maximum 387,859. Replacement characters occur
   in 55 scoped and 877 broad records. These need preprocessing/quality slices;
   a short transformer truncation limit would discard substantial content.
7. **Evidence is structurally usable but unverified semantically.** The audit
   checked 21,401 scoped and 40,737 broad evidence spans, all parent/context links,
   and 320/4,243 relationship records without missing references, invalid spans
   or timestamps beyond the declared cutoff. This does not prove date roles,
   actor identity, future-blind quoted content or annotation semantics. The old
   scoped validation report also retains three malformed sanitized URL findings;
   the converter preserves these legacy resources for review instead of treating
   them as verified fields.

Body-only label disagreement groups number one in scoped mail and five in broad
mail. These are diagnostics: different subjects can explain some differences.
There were no conflicting labels on identical normalized subject/body inputs in
the individual converted corpora. Their originals remain available for review.

## File and provenance integrity

- All 278 scoped original attachment hashes match; all 143 declared text exports
  exist. A stale absolute path for the broad export's one saved binary resolves
  to the local attachment by an exact SHA-256 match; the original manifest was
  not rewritten. Broad's other undeclared/pending binaries remain explicitly so.
- All eight public raw source/license files match their recorded hashes.
- The full 2,794,910,093-byte Durg archive matches SHA-256
  `62bc93a6c0271f6d41d3e624b79df3526a43a1f92ffa7fd65cb6635389338270`.
  Streaming tar inspection reconciles all 2,376 file names and sizes with the
  inventory, with no extraction to disk and no mismatches.
- All 120 sampled PDFs and both saved official PDFs match their hashes. All 554
  sample page spans are in bounds. Catalogue checksum and count also match.
- Source JSONL counts reconcile with both mail collection manifests. Every source
  JSONL and relationship sidecar has an exact checksum in the pinned manifest;
  migration verifies the sources remain unchanged.

## Implementation completed

The v2 contract now represents unavailable text explicitly, preserving context
nodes without manufacturing labels or breaking references. The conservative
migration policy retains old labels/metadata, logs the one repeated-category
normalization, promotes nested parent IDs, and preserves every sidecar grouping
edge. Unknown legacy semantic annotations remain auditable metadata rather than
reviewed v2 annotations. Publication requires whole-corpus validation.

Operational imports stage the complete file before a single insertion transaction,
validate snapshot checksums and duplicate identities, and report excluded unusable
text. Reimport preserves completed analysis and confirmed edits. Pending processing
can resume after interruption. Source changes under an existing identity are
rejected rather than silently replacing records.

Legacy path-derived keys have an explicit owner/namespace dry-run and apply
migration. Apply creates and verifies a new SQLite backup before changing keys;
message IDs, payloads, revisions and relationships remain intact. Collisions abort.
This migration was tested against isolated databases; no existing live profile
was present in the project or modified by the acceptance run.

## Acceptance evidence

Run ID: `data03-20261027-verified`, based on Git `e378643` with implementation
file hashes recorded in the run report. Platform: macOS arm64, Python 3.12.9.
Private artifacts are local and ignored by Git:

- `artifacts/research/data03-20261027-verified/run.json`
- `artifacts/research/data03-20261027-verified/corpus-audit.json`
- Five `*.v2.jsonl` exports and corresponding `*.migration.json` reports
- `artifacts/research/data03-20261027-verified/real-import-verification.json`

All **17,291** records were published across separate validated exports; zero
original rows were deleted. Context-only exclusions total 4,375. Operational
storage acceptance imported **439 scoped + 4,151 broad = 4,590** usable messages
in an isolated database. Relocating and reimporting both files created **zero**
new records and **zero** revisions. This verifies import/storage behavior without
ML inference; it is not a pipeline latency or model-quality benchmark.

Verification: **129 portable tests passed**; enabling installed research inputs
produced **130 passed**, with the existing Starlette/AnyIO deprecation warning.
Regression coverage includes failed-input transaction rollback, identity collisions,
backup integrity, owner isolation, confirmed-state retention, pending-processing
recovery, unavailable context nodes, sidecar links and explicit public-label mapping.
Ruff undefined-name checks and whitespace checks passed.

Reproduce in a new run directory:

```bash
.venv/bin/python scripts/prepare_research_data.py --output-dir artifacts/research/NEW_RUN_ID
.venv/bin/python scripts/verify_dataset_imports.py
.venv/bin/python -m pytest -q --run-research
```

See [the schema/migration guide](../dataset/RESEARCH_SCHEMA.md) for Windows commands
and legacy-profile migration. Windows execution remains an ENV acceptance task.

## Next gate

DATA-04 must rebuild leakage components using shared source identities, threads,
parents, duplicate/template groups and all explicit relation edges. Then reserve
whole groups, establish reviewed development/test labels and measure the current
baseline before promoting model changes. The broader corpus, public annotations
and OCR candidates remain useful development options with the source boundaries
and quality limitations above. No new model has been trained or promoted here.
