# Research leakage components (DATA-04)

The builder takes a validated, pinned DATA-03 run. It produces a private membership
manifest and audit reports. It does **not** choose train/test folds, convert weak
labels into gold, or authorize quarantined content for training.

```bash
.venv/bin/python scripts/build_leakage_components.py \
  --input-run artifacts/research/data03-20261027-verified \
  --output-dir artifacts/research/NEW_DATA04_RUN
```

PowerShell:

```powershell
.\.venv-win\Scripts\python.exe scripts/build_leakage_components.py --input-run artifacts/research/data03-20261027-verified --output-dir artifacts/research/NEW_DATA04_RUN
```

The output directory must be new and outside `dataset/`. Source V2 files are
validated again, and their exact byte hashes must match the DATA-03 run.
Membership output includes a namespaced dataset ID and document ID, prediction
task, source name, `component_id`, and `provisional_split_guard_id` for every
record, including unavailable-text context nodes. Output remains ignored by Git
because membership exposes private document identities.

## Strong grouping rules

Components join documents through:

- Provider thread ID, attachment parent, context reference, and source-declared
  grouping/semantic relationship. Explicit update, correction and cancellation
  links remain in the same component even if the suggested target still needs
  semantic review.
- Source-declared duplicate, template and update-family IDs, each namespaced by
  dataset. The same opaque token in unrelated datasets cannot merge records.
- Exact normalized canonical body text within the **same prediction task**.
  Blank/unavailable text never forms an exact or near-duplicate group.
- Cross-snapshot source identity when the source family, document ID, original
  message ID, source type, thread ID and timestamp agree. This joins scoped/broad
  copies even when privacy transformations altered their text. Inconsistent
  identity metadata triggers review rather than automatic union.
- Verified near duplicates. Text of at least 120 characters uses four-word
  shingles with Jaccard >=0.90. Text of 45–119 characters (and long texts with
  too few word shingles) uses five-character shingles with Jaccard >=0.88.
  Both use 32 deterministic MinHash values only for candidate lookup; a candidate
  must pass the exact shingle-set comparison and size-ratio gate >=0.82 before
  union. Hash keys include task and shingle method. Candidate caps and skipped
  long/bucket counts are reported; an incomplete index requires review.

Signatures are an efficient search method, **not a proof that all possible near
pairs were found**. Conservative grouping is one defense alongside future
source-aware and chronological evaluation. Source task boundaries remain separate:
academic documents and binary sentence actionability never share a component.

## Legacy groups and split guards

Original `leakage_group_id` values remain in the v2 records but are advisory.
The source collection pipeline built them using bare subject equality across
threads. The first DATA-04 run unconditionally unioned these IDs and produced
an 114-record group covering 43 threads across three years. That is an
unreliable hard link for a document component. The accepted policy records
these IDs in `legacy_leakage_review.jsonl` for later adjudication.

Each record also has `provisional_split_guard_id`: a conservative union of its
hard component and every unresolved legacy leakage group. **DATA-05 must allocate
whole provisional split guards** unless a reviewer adjudicates those legacy
connections and rebuilds the manifest. This protects the split while keeping
trusted document components precise. The larger guard may reduce feasible class
support; the report quantifies that tradeoff.

`component_report.json` includes source/output hashes, thresholds, task/source
counts, edge counts, top component and guard sizes, near-duplicate diagnostics,
weak-label support by independent groups, and disagreement counts. The independent
postcheck rereads all sources and verifies every hard relationship edge, exact
body match, cross-snapshot identity, soft-group split guard, near edge, stable
component ID and output checksum. Any failure makes the run invalid.

The first completed report is
[DATA-04 component acceptance](../reports/DATA04_COMPONENT_ACCEPTANCE.md).
The DATA-03 source manifest and schema remain described in
[RESEARCH_SCHEMA.md](RESEARCH_SCHEMA.md).
