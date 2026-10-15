# Build progress

## Phase 0

- Tests written first in `tests/test_phase0.py`; initial run failed because the repository module did not exist.
- Implemented owner-scoped transactional SQLite storage, revision history, hashed application sessions and typed notice input.
- Consolidated all existing data under `dataset/` with same-filesystem renames; kept private/sanitized/quarantined boundaries.
- Foundation unittest run: 3 tests passed. Pytest will also discover the original function-level tests once its environment is installed.
- Implementation choice: the local repository uses Python's SQLite driver behind a storage boundary rather than requiring SQLAlchemy for core operations. Remote deployment remains a future repository adapter.

## Phase 1 — in progress

- Tests written first for separate date roles/evidence, ambiguous-date abstention, negated actions, readable/unsupported resources, and duplicate-safe model splits.
- Initial run failed on missing implementation. Local extraction tests now pass; scientific training dependencies are installing before the full phase gate runs.
