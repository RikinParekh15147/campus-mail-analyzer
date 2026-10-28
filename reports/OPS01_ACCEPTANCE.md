# OPS-01/02 model bundle and rollback acceptance — 28 October 2026

The local delivery contract is implemented and fixture-verified. No real model was promoted. The installed Mac currently runs rules-only unless a versioned bundle is explicitly sealed and activated.

Each candidate lives under `artifacts/models/<task>/bundles/<bundle-id>/` with `classifier.joblib`, `metrics.json` and a write-once `bundle.json`. The manifest records taxonomy, preprocessing and analysis schema versions, model revision, thresholds, dependency versions, and SHA-256 hashes for both artifacts. A candidate must have valid metrics JSON. Verification requires the exact manifest digest from the active pointer and rejects incompatible or corrupt files and symlinks without deserializing the pickle. Runtime rechecks the model bytes on the same open file handle before `joblib.load`.

`active.json` in each task directory stores active and previous bundle IDs and manifest hashes with a monotonic revision. Promotion and rollback acquire an exclusive local lock, verify the target bundle, require the caller's expected revision, and publish with atomic replace. An injected replace failure leaves the old pointer intact and removes staging files. Rollback changes only the pointer; a fixture confirmed profile date remains unchanged. No model file is overwritten.

Application classification and actionability load only active verified bundles. Missing, legacy, corrupt or incompatible artifacts fall back to local rules. Each analysis records the exact classification model revision and bundle ID (or `local_rules`); actionability records its model identity when used. Analysis includes `model_health`; doctor and `/models` expose verified or rules-only health. The Models desktop screen now shows that status and does not display unverified legacy scores as active model results.

For an approved candidate already copied into the bundle directory:

```sh
PYTHONPATH=backend .venv/bin/python scripts/manage_model_bundle.py seal --task academic --bundle-id <id> --model-revision <revision>
PYTHONPATH=backend .venv/bin/python scripts/manage_model_bundle.py promote --task academic --bundle-id <id> --manifest-sha256 <seal-output-sha256> --expected-revision 0
PYTHONPATH=backend .venv/bin/python scripts/manage_model_bundle.py status --task academic
PYTHONPATH=backend .venv/bin/python scripts/manage_model_bundle.py rollback --task academic --expected-revision <current-revision>
```

Operational limit: a local owner can deliberately approve a bundle; checksums detect accidental alteration and enforce an exact selected artifact, but they are not a signature or external publisher identity. Do not promote the existing weak-label baseline as a measured accuracy improvement. DATA-06/EVAL-06 and CLS-02/04 still govern candidate selection and reporting. Windows native packaging and a real promoted-model smoke run remain release gates.

Verification: six focused registry/API tests, including runtime prediction and fallback, stale revision, interrupted promotion, rollback and unchanged confirmed profile data; **279 portable tests passed**, one private-data test deselected. Frontend build and two bridge tests passed. Scoped Ruff and `git diff --check` passed.
