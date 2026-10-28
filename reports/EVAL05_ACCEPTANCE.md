# EVAL-05 reproducible experiment runner acceptance — 28 October 2026

The rules-only development runner is `backend/campusmail/research/experiment.py`;
the CLI is `scripts/run_development_experiment.py`. It takes a v2 JSONL input,
`development-selection-v2` manifest for research runs, both expected SHA-256
values, an output name and seed. Research mode re-creates the selection from
the accepted DATA-05 reservation, maps blinded review IDs through its private
identity map, verifies the guard allocation and requires double-reviewed
academic classification. The earlier `development-selection-v1` path remains
fixture-only. Fixture mode is explicit and is part of run identity.

The 24-character run ID derives from pinned input/selection hashes, code hash,
preprocessing/schema versions, Python and installed dependency versions, the
hash of pinned runtime dependency specifications in `pyproject.toml`, seed and
fixture mode. `run.json`, `metrics.json` and `predictions.jsonl` are written to
an owner-only temporary directory, then published under that ID. The lock and
existing-run check reject overwrite; failure removes partial output. Research
outputs are confined to `artifacts/research/experiments`, not the deployed
`artifacts/models` path. Output files are mode 0600 and the experiment root is
mode 0700. Predictions can contain private source text and remain ignored by Git.

Six focused runner tests verify byte-identical reruns in separate private
roots, refusal to overwrite, checksum/holdout/public-path/invalid-ID/seed
rejection, run metadata, and the v2 custody gate. Four additional protocol
tests cover blinded ID mapping, fold/support reporting, source-text binding
and tamper rejection. The portable suite passed 200 tests with one private-data
test deselected. `ruff check` on changed Python files and `git diff --check`
passed. The CLI help entry point succeeded.

The current-code ephemeral synthetic fixture run ID is
`53702c8fa7e8020052c85a39` (the ID changed after FIX-02/03 updated `nlp.py`);
its input SHA-256 was `93459ddd1ffb38e165bcb284cd5c23613d302059a3b54dbe8e5929d72ec1e151`
and selection SHA-256 was
`7664b7356e0d1b3c1e5586d7986ad36604e169c53fc0a6ea5d2e3b0e3972b657`.
The output was intentionally temporary and contains no corpus data.

This is experiment infrastructure, not an accuracy result. The DATA-06 pilot
has no completed human reviews, so no real development experiment or baseline
score was run. EVAL-01 fold support, EVAL-03 runtime scoring
and EVAL-06 baseline comparison remain open. The recorded dependency hash pins
the project's declared versions; it does not certify wheel bytes across
platforms. The rules-only runner does not evaluate a trained model or full
application state.
