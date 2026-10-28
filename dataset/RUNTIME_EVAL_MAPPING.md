# Development runtime evaluation mapping

This mapping is separate from the pinned DATA-06 pilot guide. It does not
change the pilot forms or their hashes.

`prepare_reviewed_runtime_cases` currently accepts only academic,
single-notice v2 records with complete entity and date annotations from two
distinct human reviewers, plus uniquely linked two-notice `updates` or
`corrects` relationships. Each update relation must itself be double-reviewed,
name a source and target entity, refer to the earlier notice, and have a
strictly later source timestamp. Entity kind and identity must agree on both
sides. The update must have a resolved date; unrelated entities in the first
notice are protected against silent mutation. Multi-step or ambiguous chains,
missing targets, cancellation links, unresolved order and unsupported context
are reported as exclusions.
Assignment and event annotations need `attributes.title` matching the intended
runtime title; optional `course`, `assignment_number` and `academic_term`
disambiguate multiple items in one notice. A linked, resolved date with role
`assignment_deadline` or `event_start` supplies the expected date. Unresolved,
multiple or timed linked dates are excluded. Action spans and statuses are
checked only when actions are also complete and double-reviewed. The adapter
reports every exclusion reason.

Prepared scenarios contain notice text in memory and must stay inside the
private development environment. The fixture runner emits only aggregate
counts, numeric case indices and field names. It labels its own output
`synthetic_fixture`. `scripts/run_runtime_development_eval.py` requires pinned
reviewed input and an EVAL-01 v2 selection verified against DATA-05 custody,
then writes an owner-only aggregate report under
`artifacts/research/experiments/runtime_eval`. It refuses a research report
if no scorable runtime scenario can be prepared. Never use this path for the
sealed holdout during tuning.
