# DATA-06 development pilot finalization — 29 October 2026

The private pilot has 50 available-text notices from 50 independent development
guards. Its two pinned forms remain blank: the audit reports zero completed
classification rows for each reviewer. No reviewed score or accuracy gain exists.

`scripts/finalize_annotation_pilot.py` now accepts separate completed forms and
an adjudication record. It checks pinned pack/guide/form hashes, unique and
consistent reviewer identities, complete classification on both sides, every
task disagreement, a distinct human adjudicator, decision fields and source
evidence under the v2 contract. It drops tasks not completed by both reviewers.
After all records validate, it atomically publishes private reviewed development
JSONL and a checksum/support manifest. It rejects an existing output directory.

Synthetic tests cover a resolved category dispute, agreed complete empty action
labels, an unreviewed task, incomplete review, shared reviewer identity, missing
adjudication, a reviewer acting as adjudicator and an invalid final category.
The portable Python suite passed 284 tests (one private research test deselected)
on 29 October 2026. The pinned real pilot audit still reports 0/50 completed
classification rows for each reviewer and `human_review_incomplete`. The real
pilot is deliberately not finalized. DATA-06 remains open until the team
performs independent review and adjudication. DATA-08 sealed labels are
separate and must not be drawn from this development output. The operational
steps are in [the private review handoff](../dataset/ANNOTATION_HANDOFF.md).
