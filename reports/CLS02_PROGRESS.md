# CLS-02 bounded sparse-model comparison — 28 October 2026

The comparison tool is ready; the reviewed experiment is blocked by DATA-06 and EVAL-06. The pilot audit still records zero human-completed forms. No candidate has been selected or promoted, and no accuracy improvement is claimed.

`backend/campusmail/research/sparse_comparison.py` fixes nine candidates before seeing reviewed scores: majority, existing word NB and SVM, word/character SVM, balanced SVM, course-code-masked SVM, logistic regression, ComplementNB and subject/body SVM. Each receives the same frozen DATA-05 whole-guard folds, with fold-local vectorizer fitting and out-of-fold predictions. The scorer rejects duplicate document IDs, mismatched guards, stale preprocessing and folds without two training classes. It returns support, predictions and macro-F1 with `selection: null`.

The reviewed wrapper verifies the development-selection v2 manifest and DATA-05 custody before reading documents. It requires double-reviewed classification labels and excludes the sealed holdout by protocol. The CLI checks caller-provided input and selection SHA-256 hashes, binds the run to code, dependency and candidate-matrix hashes, then writes an immutable owner-only report under `artifacts/research/experiments/sparse_comparison/`. It never changes the deployed model.

Once the team has adjudicated labels and frozen the development selection, run:

```sh
PYTHONPATH=backend .venv/bin/python scripts/run_sparse_development_comparison.py \
  --input /path/to/reviewed-development.jsonl \
  --selection /path/to/development-selection.json \
  --input-sha256 <reviewed-file-sha256> \
  --selection-sha256 <selection-file-sha256>
```

Before interpreting scores, inspect class and guard support, paired errors and class regressions. Then reproduce the existing rules/model baseline on the same reviewed selection (EVAL-06). CLS-02 remains open until that comparison is run and interpreted; CLS-03/04 remain open until diagnostic review and champion freeze.

Verification: three focused fixture tests cover paired deterministic folds, guard/preprocessing rejection, and verified custody/tamper rejection. The portable suite passed **273 tests**, with one private-data test deselected. Ruff passed on the new comparison files and `git diff --check` passed. These tests establish the comparison contract, not real-world accuracy.
