# Unified dataset directory

The installed corpus was audited on 27 October 2026. See the
[DATA-01/DATA-03 acceptance report](../reports/DATA03_CORPUS_ACCEPTANCE.md),
[schema and migration guide](RESEARCH_SCHEMA.md), and pinned
[source manifest](../research_sources.json). Reproducible derived exports stay in
ignored `artifacts/research/`; source exports and private originals are immutable.

All project research inputs are now under this directory. No source records were discarded.

- `mail/`: original personal-mail collection, private originals, anonymized exports and collection utilities. The default academic training source is `mail/scoped_run/sanitized/documents.jsonl` (575 records; unavailable labels are excluded). The broader `mail/sanitized/documents.jsonl` has 8,292 records and is retained as a separate alternative, not merged into the scoped collection.
- `public/`: original public resources, normalized actionability datasets, licenses and acquisition manifests. Unverified university data remains quarantined.
- `tools/`: preserved public acquisition/inspection scripts and research training entrypoints.

Private operational data and feedback never automatically enter shared training. Imported source/weak annotations are not human-reviewed gold labels. Repeated threads, templates and duplicates must stay together when splitting data. Public sentence actionability and academic-category classification are distinct tasks.

Migration: `mail_dataset/` → `dataset/mail/`; `research/public_data/` → `dataset/public/`; `research/scripts/` → `dataset/tools/`. Historic collection manifests retain their original paths as provenance. The app resolves current inputs from this layout instead of those historic absolute paths.

Keep this entire directory out of source control and public packages. Collection scripts can contain personal configuration; do not publish them without review.
