# Unified dataset directory

New research-contract tooling: [v2 schema and validation guide](RESEARCH_SCHEMA.md).
The validator is read-only and requires an explicit v2 export. Legacy exports
can be converted with the explicit `dataset migrate-v1` command described in the
schema guide. The operational import collections and their stable IDs are listed
in [dataset_collections.json](../dataset_collections.json).

All project research inputs are now under this directory. No source records were discarded.

- `mail/`: original personal-mail collection, private originals, anonymized exports and collection utilities. The default academic training source is `mail/scoped_run/sanitized/documents.jsonl` (575 records; unavailable labels are excluded). The broader `mail/sanitized/documents.jsonl` has 8,292 records and is retained as a separate alternative, not merged into the scoped collection.
- `public/`: original public resources, normalized actionability datasets, licenses and acquisition manifests. Unverified university data remains quarantined.
- `tools/`: preserved public acquisition/inspection scripts and research training entrypoints.

Private operational data and feedback never automatically enter shared training. Imported source/weak annotations are not human-reviewed gold labels. Repeated threads, templates and duplicates must stay together when splitting data. Public sentence actionability and academic-category classification are distinct tasks.

Migration: `mail_dataset/` → `dataset/mail/`; `research/public_data/` → `dataset/public/`; `research/scripts/` → `dataset/tools/`. Historic collection manifests retain their original paths as provenance. The app resolves current inputs from this layout instead of those historic absolute paths.

Keep this entire directory out of source control and public packages. Collection scripts can contain personal configuration; do not publish them without review.
