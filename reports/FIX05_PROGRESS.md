# FIX-05 occurrence identity acceptance — 28 October 2026

FIX-05 is complete for the supported assignment and named-event paths. Numbered
assignments use course, explicit academic term and thread/source identity. Known
cross-thread updates and same-title event reschedules with multiple possible
targets require a user choice. Unknown-course numbered assignments do not share
a global key. Explicit Fall/Autumn and semester terms are normalized; a notice
spanning multiple terms abstains from entity mutation.

Legacy assignment and event records without identity metadata are candidates
for review, not automatic merge targets. The review can select an existing
record or create a separate occurrence. The decision is stored on the source
message, reprocessing applies it, and repeated replay remains idempotent.
Older event evidence is matched before the current event date so replay cannot
restore a pre-reschedule date.

Verification: `.venv/bin/python -m pytest -q tests/test_occurrence_identity.py`
passed 16 tests. `.venv/bin/python -m pytest -q -m 'not private_data'` passed
153 tests, with one private-data test deselected and one dependency warning.
The tests cover explicit terms, legacy records, reviewed resolution, API
reprocessing, ambiguous and reverse-order updates, and replay. No accuracy
gain is claimed; these are fixture-level correctness checks. Real corpus
review, broader replay consistency and user override precedence remain in
DATA-06, FIX-06 and FIX-07.
