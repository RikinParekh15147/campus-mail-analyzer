# PIPE-01 runtime evidence contract acceptance — 28 October 2026

`candidates.py` now defines frozen evidence and field-assertion records with
document ID, source field, exact text span, optional locator, value, extraction
method/version, uncertainty and optional calibrated probability. Rule outputs
cannot claim calibrated confidence. `Engine.process` validates the extracted
date, range, time, action, resource and temporal-warning spans against the
stored body or subject before downstream mutations, then persists a versioned
assertion list alongside its legacy analysis dictionary. Reviewed date
corrections are reflected in the assertions.

Assignment `due_date` and event `date` now retain the exact validated
assertion that supplied the committed field. Field-specific source ordering
keeps the winning assertion when an older notice is replayed. Manual feedback
records a user-confirmed origin immediately, and engine replay preserves it.

Targeted assignment/event cancellations now retain the exact validated clause
that changed `status`. Profile values extracted from message text retain exact
value spans; manually confirmed values keep their confirmed origin on replay.
The adapter preserves the dictionary interface consumed by the current engine.

Fixture acceptance: 255 portable tests passed; one private-data test was
deselected. Invalid offsets, unsupported values and uncalibrated rule scores
are rejected. Existing saved analyses and old attachment occurrence keys need
the backward-compatible migration specified in PIPE-05. Category and derived
course/entity decisions are document-level decisions, not exact-span
extractions; their source IDs remain available, with broader preprocessing and
model provenance governed by PIPE-02 and OPS-01. No accuracy gain is claimed.
