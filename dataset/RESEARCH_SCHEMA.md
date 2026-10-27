# Research document contract v2

This contract implements DATA-02 from [the ML improvement checklist](../ML_IMPROVEMENT_TASKS.md). It is a validation boundary for designated research exports, separate from operational profile records and the existing v1 training/import paths. It does not grant reuse permission, prove human annotation quality, or select training/test splits.

Canonical Python definition: `backend/campusmail/research/contracts.py`.
Generated JSON Schema: [research_document.v2.json](../schemas/research_document.v2.json).
Fabricated examples: [research_v2.jsonl](../tests/fixtures/research_v2.jsonl).

## Run validation

macOS:

```bash
.venv/bin/python -m campusmail dataset validate \
  --input tests/fixtures/research_v2.jsonl \
  --report artifacts/verification/research-fixture.json
```

Windows PowerShell:

```powershell
.\.venv-win\Scripts\python.exe -m campusmail dataset validate --input tests/fixtures/research_v2.jsonl --report artifacts/verification/research-fixture.json
```

Replace `--input` with a designated v2 research export on the data owner's machine. No large archive is needed on the Mac. Reports are emitted as JSON on stdout; `--report` also saves one atomically. Exit codes: **0** valid, **1** invalid dataset, **2** invalid arguments or an I/O/validation execution failure. The report cannot overwrite the input, including through a symlink or hard link.

Input is UTF-8 JSONL, one object per nonblank physical line. The validator rejects duplicate JSON keys, non-finite JSON numbers, invalid UTF-8, unknown fields, and unsupported schema versions. Default line limit is 16 MiB; oversized lines are drained in bounded chunks and validation continues. The first 100 error entries are retained by default (`--max-errors` changes this), while the full error count is recorded. Bodies are processed one record at a time; IDs, hashes and references use a temporary disk-backed SQLite index. Aggregate category/source counters remain in memory.

## Required fields

| Field | Meaning |
|---|---|
| `schema_version` | Exactly `"2.0"` |
| `dataset_id`, `document_id` | Stable sanitized IDs; document identity is namespaced by dataset |
| `task` | `academic` or `actionability`; their target labels are not interchangeable |
| `data_origin` | `designated_research`, `public`, or `synthetic`; operational mail is not a research input type |
| `source_type` | Controlled source/genre name such as `gmail_message`, `attachment`, or `fixture` |
| `text` | Canonical text, at most 2,000,000 Unicode characters; blank only with explicit unavailable status |

`usage_status` defaults to `unverified`; `permitted` and `quarantined` are also representable. Validation accepts quarantined material for inventory purposes; acceptance does **not** authorize training. Metadata, reference dates and labels are never inferred from a path or from current time.

## Annotation completeness and provenance

Each task has its own entry in `annotation_status`: `classification`, `dates`, `actions`, `entities`, `relationships`, and `reply_state`. Absent entries default to **unannotated/unlabeled**, even when their arrays are empty.

```json
{
  "annotation_status": {
    "dates": {
      "completeness": "complete",
      "provenance": "human_reviewed",
      "reviewer_ids": ["reviewer-a", "reviewer-b"],
      "adjudication": "resolved",
      "adjudicator_id": "reviewer-c"
    }
  },
  "dates": []
}
```

The example declares that the entire document was reviewed for dates and contains none. It is different from an unannotated empty array. `partial` means some annotation exists or review is incomplete; it cannot serve as complete gold for that task. Human-reviewed provenance requires reviewer IDs. Resolved adjudication requires an adjudicator. Pending adjudication is excluded by `gold_eligible(task)`.

`gold_eligible(task)` checks only asserted completeness/review metadata. It does not authenticate the reviewers, verify factual correctness, exclude synthetic origins, check reuse permission or establish split independence. Reports separately count complete reviewed annotations and their non-synthetic subset. Future benchmark selection must enforce all those additional conditions.

Provenance values: `unlabeled`, `source`, `weak`, `ai_generated`, `human_reviewed`, `synthetic`. Do not convert a legacy `human_reviewed: true` into all-task review without evidence. Supplying annotations while leaving that task unannotated is an error.

Academic records use one of the eight existing `primary_category` values. Secondary labels have a separate `secondary_categories_complete` flag; missing secondary labels do not imply an exhaustive negative set. Actionability records use a strict boolean `actionability_label` and cannot carry academic categories. Complete classification requires the appropriate label; uncertainty can remain partial with a null label.

## Evidence, dates and source mapping

Evidence uses `{field, start, end, text, locator?}`. `field` is `text` or `subject`, defaulting to `text`. Offsets are **Python Unicode character indices**, zero-based and end-exclusive; UTF-8 byte offsets and JavaScript UTF-16 offsets are not equivalent. Every span must be nonempty, within bounds, and match exactly. Optional locators retain PDF page or spreadsheet sheet/row/cell references.

Dates contain evidence, role, normalized value, precision, optional timezone/reference date and optional local entity ID. Date precision accepts `YYYY-MM-DD`; datetime precision requires an ISO timestamp with an explicit offset. A supplied IANA timezone must agree with that offset. Invalid calendar dates are rejected. Missing normalized values or unknown roles require `needs_review: true` and a reason. No year, time, timezone, role or reference date is guessed.

Actions explicitly carry actor, action type and required/optional/completed/negated/uncertain status. Entity annotations have stable local IDs and evidence. Local entity references must resolve inside the document. The schema is intentionally strict: extended tasks such as detailed per-request conversation labels or additional action types need a reviewed schema extension, not silent arbitrary fields.

`original_text` is optional and must itself be safe to retain in the designated research export. `offset_map` maps canonical `text` intervals to original intervals. Both sides are checked for bounds; `exact` mappings also require identical text, while `normalized` mappings explicitly declare transformation. Partial maps are allowed and do not claim complete original-source coverage. This schema validates a supplied map; it does not implement preprocessing or sanitization.

## Context and group identity

Keep all of `thread_id`, `parent_document_id`, `duplicate_group_id`, `template_group_id`, `leakage_group_id` and `update_family_id`. Validation preserves them instead of selecting only one. Leakage-component construction remains DATA-04.

Document references resolve within the same dataset; forward references are allowed, missing references are errors. Relationship evidence belongs to the source record. `target_document_id` and optional `target_entity_id` identify the destination; local `source_entity_id` must exist. Relationship kinds distinguish support, same entity, update, cancellation, correction, exact duplicate and candidate supersession.

`sent_at`, `context_cutoff_at` and `reference_date` require timezone-aware timestamps; numeric epochs are rejected. Context-document references and reply-state annotations require an observation cutoff. A document cannot be later than its cutoff, and referenced documents with later timestamps or unverifiable timestamps are flagged when a cutoff is provided. These checks do not prove that quoted prose itself is future-free; chronological dataset construction is still required.

## Reports and migration boundary

Reports include the SHA-256 of exactly the input bytes read, physical-line counts, structurally valid/unique record counts, source/label/origin/usage counts, per-task annotation coverage and bounded errors. Duplicate IDs and inconsistent labels on normalized duplicate text invalidate the corpus. Invalid references are checked after all records have been indexed. A schema-valid record count is **not** a count of final benchmark-eligible records.

Error entries omit document bodies, arbitrary unknown field names, validation inputs and exception messages. They retain line number, error type and known schema field locations. Reports still reveal source distribution and other research metadata; keep real-data reports private until reviewed for sharing.

Existing v1 exports remain rejected by `dataset validate`. An explicit converter is available for legacy JSONL rows that have stable `document_id` and canonical `text` fields:

```bash
.venv/bin/python -m campusmail dataset migrate-v1 \
  --input /path/to/legacy/documents.jsonl \
  --output /path/to/private/research-v2.jsonl \
  --dataset-id campus-mail-scoped-v1 \
  --task academic --data-origin designated_research \
  --source-type sanitized_mail --usage-status unverified \
  --report /path/to/private/migration-report.json
```

Use the collection's declared `dataset_id` from [dataset_collections.json](../dataset_collections.json) where applicable. The converter streams input, keeps the source file unchanged, checks every converted row against the v2 contract, validates the complete candidate export, and publishes the output atomically only when valid. Existing output stays unchanged on failure. Output and reports can contain private research metadata; store them with the source archive.

Legacy category or boolean labels become **partial, weak** classification annotations, even if an old field says `human_reviewed`. Legacy annotation arrays remain under `source_metadata.legacy_extra_fields` and are not promoted to v2 annotations. Old label provenance, secondary-label completeness, original metadata and each source line hash remain in metadata. Grouping IDs and source text are copied as supplied. Conversion does not repair timestamps, infer missing IDs, normalize evidence, establish source permission or assert gold quality. Schema-invalid labels or unresolved document references stop publication; fix the source export or add an explicit, reviewed mapping.

Operational collection imports now stream from disk and use the manifest's stable dataset ID plus document ID as record identity. The CLI's existing `import` command still consumes the designated legacy operational export, not research v2. Profiles imported with an earlier path-derived source key require a deliberate store migration before reimporting, to avoid duplicate records. The converter does not switch the model training loader or establish a benchmark split.

To regenerate the JSON Schema after intentional contract changes:

```bash
.venv/bin/python -c 'import json; from pathlib import Path; from campusmail.research.contracts import ResearchDocument; Path("schemas/research_document.v2.json").write_text(json.dumps(ResearchDocument.model_json_schema(), indent=2) + "\n", encoding="utf-8")'
```

The test suite verifies that the checked-in schema matches Python exactly.


## DATA-03 acceptance on the installed corpus (27 October 2026)

The pinned source inventory is [research_sources.json](../research_sources.json).
The original five JSONL exports remain immutable. Reproduce inventory, file hashes,
reference/evidence checks and all five v2 migrations in a **new** run directory:

```bash
.venv/bin/python scripts/prepare_research_data.py --output-dir artifacts/research/my-data03-run
```

PowerShell:

```powershell
.\.venv-win\Scripts\python.exe scripts/prepare_research_data.py --output-dir artifacts/research/my-data03-run
```

The run fails if a declared source checksum changes. It verifies the scoped
attachment binaries, public raw files, sampled PDFs and full archive inventory;
outputs stay under ignored local research storage. `run.json` records input/output
hashes, code hashes, counts, policy, interpreter and platform. The original source
IDs remain stable across machines. A changed source snapshot needs an intentional
manifest/dataset-version update; never edit the expected checksum merely to bypass
a failure.

For an individual mail export, add `--policy preserve_context` and
`--relationships path/to/relationships.jsonl` to the migration command above.
For normalized public sentence files, use `--input-format sentence_actionability`
with `--task actionability --data-origin public`. Integer 0/1 source labels map
explicitly to false/true. Their provenance remains `source`, completeness remains
`partial`, and upstream split/label metadata is retained. No public source is
silently turned into an academic-category corpus.

### Unavailable text and exclusions

`text_status` defaults to `available`, which still requires nonblank text.
`unavailable` explicitly permits blank/whitespace text and requires every annotation
task to remain unannotated. Such records preserve IDs, timestamps, parent/context
links and groups but are excluded from text-model input. The original labels and
text remain auditable in source files and migration metadata. This avoids deleting
an unreadable attachment and breaking valid context references.

The `preserve_context` policy also removes repeated secondary-category entries
while retaining the original list; it never invents a replacement category.
Conflicting labels on the same normalized subject/body input are withheld from
**all** affected rows, with original labels retained. Every transformation has a
count and source-line diagnostic. Strict mode still rejects these cases. A complete
error report prevents publication; no partially converted corpus is promoted.

`grouping_relations` retains directed source-declared links from the relationship
sidecar. These are grouping candidates, separate from reviewed semantic annotations;
raw relationship evidence remains in `source_metadata.legacy_relationships`.
Targets must resolve. Nested attachment parent IDs are promoted to the canonical
`parent_document_id`, with conflicting declarations rejected.

### Operational reimport and legacy profile migration

Operational import stages and validates the whole JSONL before inserting selected
records in one transaction. It reports unavailable-text exclusions, verifies the
collection checksum when declared, rejects duplicate IDs and changed source data
under an existing identity, and preserves completed analysis/confirmed edits on
reimport. Interrupted processing remains pending and can resume. A deliberate
reanalysis workflow is separate from importing the same snapshot again.

Old path-derived source keys are detected before reimport. Inspect an existing
profile (substitute its actual owner ID and database path):

```bash
.venv/bin/python -m campusmail dataset import-identities --database runtime/campus.sqlite --owner OWNER_ID
.venv/bin/python -m campusmail dataset migrate-import-ids --database runtime/campus.sqlite --owner OWNER_ID --dataset-id campus-mail-scoped-v1 --legacy-namespace OLD_12_HEX_NAMESPACE
```

The second command is a dry run. Apply the reviewed mapping with a **new** backup
path:

```bash
.venv/bin/python -m campusmail dataset migrate-import-ids --database runtime/campus.sqlite --owner OWNER_ID --dataset-id campus-mail-scoped-v1 --legacy-namespace OLD_12_HEX_NAMESPACE --apply --backup artifacts/private-backups/before-import-ids.sqlite
```

Only that owner's selected legacy namespace is migrated. A verified SQLite backup
is taken under the database write lock before changes. Message IDs, payloads,
revision history and related records remain intact; collisions abort instead of
merging. To recover, close the application and restore the full backup as the profile
database. Never replace a database while the application is running. Do not expose
profile databases/backups in Git or in shared research artifacts.
