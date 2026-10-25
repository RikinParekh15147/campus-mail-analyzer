# ML foundation implementation — 25 October 2026

Source baseline: `969143d` plus the current uncommitted implementation. This report records new verification on macOS; it does not reuse the previous author's Linux results.

## Delivered

- Created an isolated Python 3.12 environment and installed the existing pinned application/dev dependencies. Global Python was not modified.
- Added shared resolved dependency constraints consumed by setup and CI, an explicit Python 3.12 development version, and packaged timezone data for systems without an OS timezone database.
- Added `campusmail doctor`: read-only JSON diagnostics for package versions, native imports, timezone data, dataset presence and model metadata compatibility. It works without importing application services first and can still report missing dependencies when site packages are unavailable. It does not read credentials or deserialize models.
- Default tests now use fabricated data, temporary application roots, in-memory credentials and blocked external networking. Local IPC remains available for Windows asyncio socketpair behavior.
- Moved the private dataset existence check behind `--run-research`; explicit research checks still fail when required inputs are absent.
- Added a real fixture-backed research-loader contract test and diagnostics/isolation regressions.
- Made the desktop test select the correct Python path on Windows and honor `CAMPUS_PYTHON`.
- Added setup error handling, backend-only setup options and a macOS/Windows CI matrix with dependency/doctor/test artifacts.
- Updated README with a clean-clone, no-dataset workflow and accurate model-verification limitations.

## Verification performed

| Check | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | **77 passed, 1 research test deselected** |
| `.venv/bin/python -m pytest tests/test_diagnostics.py -q` | **6 passed** |
| `.venv/bin/python -m pytest --run-research -m research -q` | **Expected failure:** missing scoped research export, with actionable instructions |
| `.venv/bin/python -m campusmail doctor` | **Passed**; datasets/models absent and rules-only mode explicit |
| `.venv/bin/python -m pip check` | **No broken requirements** |
| `npm --prefix desktop test` | **2 passed** |
| `npm --prefix desktop run build` | **Passed** |
| `npx --no-install playwright test tests/desktop.spec.cjs --workers=1` from `desktop/` | **1 passed**, real Electron/Python workflow with temporary profile, 9.2 seconds overall |
| Shell/JavaScript syntax and `git diff --check` | **Passed** |

The desktop test covered profile creation, notice analysis, confirmed identity, marks, timetable import, conflict proposal/approval, screen navigation and shutdown. No Gmail authorization, private dataset or trained model was used. This verifies the rules-only development workflow, not trained-model accuracy.

Local machine-readable diagnostics and installed versions are saved under ignored `artifacts/verification/doctor.json` and `artifacts/verification/freeze.txt`. The full numerical environment uses scikit-learn 1.7.2, NumPy 2.5.4, SciPy 1.18.1 and joblib 1.6.0. The checked-in constraints capture this resolved environment; they are not a hash-verified universal lock.

## Task status and limitations

- **ENV-02 and ENV-03 completed.** Their behavioral checks passed locally.
- **ENV-01 remains partial:** compatible Mac environment exists; Windows installation and its complete transitive dependency resolution still need execution.
- **ENV-04 remains partial:** native paths and setup failure handling implemented; Mac desktop startup/workflow/shutdown passed. Windows startup and PowerShell execution are not claimed.
- **ENV-05 remains partial:** CI configuration exists, but no remote CI run was triggered or observed. Both-platform completion requires actual job results.
- Existing Starlette/AnyIO code emits one deprecation warning during Python testing. It did not fail the suite.
- The unchanged npm lock reported four dependency advisories during installation (one moderate, three high). No forced dependency upgrade was performed in this foundation change; dependency remediation requires a separate compatibility review.
- No research data was downloaded, no real model was trained, and no improvement in accuracy is claimed.

## Next phase

Proceed with DATA-02 research schemas and validation using fixtures. The teammate can independently produce DATA-01's real corpus manifest on Windows. Actual group construction, reviewed labels and sealed evaluation require the designated research inputs; a large archive transfer to the Mac is unnecessary.
