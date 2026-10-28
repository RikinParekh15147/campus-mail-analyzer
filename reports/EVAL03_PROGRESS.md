# EVAL-03 runtime replay progress — 28 October 2026

## Two-notice mapping and pinned research entry point

The adapter now maps uniquely linked, double-reviewed `updates` and `corrects`
between two notices. It requires explicit source/target entity IDs, matching
entity identity, resolved linked dates and strictly ordered source times. The
first notice is checked before the update; later checkpoints expect the
revised target and unchanged unrelated entities after the update and replay
of the original notice. The runtime scorer now emits
`wrong_target_mutation` when a protected entity's fields or evidence change,
even if another expected entity is correct. Three-notice chains and ambiguous
relations are explicitly excluded.

`evaluate_development_runtime` verifies input and selection hashes and
recreates the EVAL-01 selection from accepted DATA-05 custody before replay.
The CLI writes an aggregate, immutable, owner-only report under
`artifacts/research/experiments/runtime_eval`; it refuses a research run with
zero scorable scenarios. Run identity includes the pinned input and selection,
Python/dependency versions and backend code hash. Reports contain counts, class support and numeric
case indices, without notice text or source IDs. Six new synthetic tests cover
the two-notice replay, unrelated-entity protection, wrong-target error,
unsupported chain and relationship, and pinned wrapper. The full portable
suite passed 206 tests with one private-data test deselected; lint and diff
checks passed.

EVAL-03 remains open: DATA-06 still has no human-completed pilot forms, so no
reviewed development replay has run. Cancellation relationships, longer
chains, actor/entity action links, timed dates and real downstream schedule
labels are not yet mapped. The two-notice fixture establishes scorer behavior,
not measured runtime accuracy.

## Earlier single-notice fixture foundation

`research/runtime_eval.py` replays fixture notices through isolated
`Application` profiles with the rules-only artifact path. Explicit checkpoints
compare assignment/event fields and source evidence, detect missing, split,
merged or spurious entities, and check action span/status, reply state, required
review, calendar entries and pending reminders. Action false positives count
only when that source is explicitly marked complete. Reports contain numeric
case indices, counts and field names, without notice text or source IDs.

`research/runtime_adapter.py` now prepares only unambiguous single-notice
development cases with complete, double-reviewed v2 entity/date labels. It
requires explicit entity identity attributes and resolved linked dates, and
reports exclusions for missing identities, unresolved/timed dates, context or
relationships. It keeps prepared source text private in memory. The pilot
guide and its pinned hash were not changed; [mapping rules](../dataset/RUNTIME_EVAL_MAPPING.md)
document the adapter boundary.

Nine synthetic tests cover a corrected deadline and old-source replay,
calendar/reminder convergence, wrong date/false merge reporting, reply-state
errors, invalid replay references, action completeness, double-review gating
and unscorable cases. The portable suite passed 190 tests with one private-data test deselected; changed Python files
passed `ruff check` and `git diff --check` passed.

At that stage the adapter did not map multi-notice adjudicated relationships,
actor/entity action links or timed dates into runtime checkpoints, and no
reviewed development set had been scored.
The installed DATA-06 pilot audit still reports 0/50 classification reviews
for each reviewer. These fixtures establish evaluator behavior, not model
accuracy.
