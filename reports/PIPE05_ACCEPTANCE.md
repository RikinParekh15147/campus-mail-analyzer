# PIPE-05 profile storage migration acceptance — 28 October 2026

New profile databases use SQLite schema version 2 and new analysis payloads
carry `analysis_schema_version=2`. Opening a version 1 profile leaves its
schema version and records untouched. The explicit migration scans every
record and fails on unsupported analysis versions, missing attachment parents
or occurrence-key collisions before writing.

Migration marks old analysis payloads as version 1 with
`requires_reanalysis=true`; it does not silently rerun inference. It rekeys
legacy attachment children by parent and, when Gmail metadata identifies one
provider item, by that item. Ambiguous provider identity stays parent-scoped,
is counted in the report and blocks a provider reimport that would create an
unverified duplicate. Resource links are backfilled from attachment children.
Record IDs, confirmed edits, date corrections and occurrence decisions are
preserved. Changed records keep their prior payload in revision history.

The CLI defaults to read-only dry runs. Apply requires a new backup path; the
SQLite backup is made while the migration holds the write lock and passes an
integrity check before changes commit. Recovery verifies its SHA-256 and
restores to a **new** path, leaving the migrated database untouched:

```text
campusmail store migrate --database /path/campus.sqlite
campusmail store migrate --database /path/campus.sqlite --apply --backup /path/before-v2.sqlite
campusmail store restore --backup /path/before-v2.sqlite --output /path/recovered.sqlite --expected-sha256 HASH
campusmail store restore --backup /path/before-v2.sqlite --output /path/recovered.sqlite --expected-sha256 HASH --apply
```

Run migration while the app is stopped. After migration, explicitly replay the
profile through `Application.reprocess(owner, {})`; the replay replaces legacy
message and readable-resource analyses using the current pipeline and retains
confirmed overrides.
Keep the verified backup until that replay and the desktop workflow are
checked. If recovery is needed, inspect the restored database, then select it
as the app database while the app remains stopped. No live profile was
migrated in this acceptance.

Four synthetic migration tests cover old-profile loading, dry-run/apply,
backup and checksum recovery, replay with a confirmed date, Gmail provider
mapping, ambiguity and collision refusal. The portable suite passed 267 tests
with one private-data test deselected; lint and diff checks passed. This is
storage compatibility evidence, not measured ML accuracy.
