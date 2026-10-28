# Development, datasets and model training

This guide contains commands for contributors who need more than the [quick start](../README.md). Run commands from the repository root unless a command changes directory.

## Project map

| Path | Purpose |
|---|---|
| `backend/campusmail/` | Python API, analysis, records, adapters and training |
| `desktop/` | Electron main process, restricted bridge and React interface |
| `tests/` | Python behavior and integration tests |
| `dataset/` | Private research inputs and their public documentation |
| `artifacts/` | Ignored generated model, evaluation and verification output |
| `runtime/` | Ignored local profiles, attachments and background work |
| `reports/` | Implementation and acceptance notes |

The app is a modular Python application with a desktop interface, not a hosted service. Its SQLite data belongs to local profiles. The renderer does not receive Google tokens or the backend bootstrap key. The desktop launcher chooses a free loopback port and starts the Python service itself.

## Setup and tests

The setup scripts require Python 3.12 and Node.js 22 or newer. They install dependencies using `requirements-dev.constraints` and `desktop/package-lock.json`. The Python constraints are not a complete hash-locked environment for every platform. Use `bash scripts/setup.sh --backend-only` (or `.\scripts\setup.ps1 -BackendOnly` on Windows) when you only need Python.

For portable local verification:

```bash
.venv/bin/python scripts/verify_portable.py --desktop-workflow
```

The command records the platform, dependency versions, lock hashes, commit state and results under an ignored `artifacts/verification/<run-id>/` directory. It runs the Python suite without private research tests, desktop bridge tests, frontend build and a real Electron/Python workflow using a temporary profile. On Windows, invoke the script with `.\.venv-win\Scripts\python.exe`. A normal `pytest` run also skips private research checks.

For individual checks:

```bash
.venv/bin/python -m campusmail doctor
.venv/bin/python -m pytest -q -m 'not research'
npm --prefix desktop test
npm --prefix desktop run build
```

To run the Electron integration test directly:

```bash
cd desktop
npx playwright test tests/desktop.spec.cjs --workers=1
```

It uses invented records and a temporary profile. It does not authorize Google or call an AI provider. On a Linux system, Electron may require the normal system desktop libraries.

## Private dataset rules

A fresh clone has no private corpus. The designated corpus was audited as 17,291 source records, but that count is an inventory, not an accuracy result. Keep original exports immutable, keep generated data out of Git and do not mix a student's operational feedback into shared research training. Read the [dataset guide](../dataset/README.md), [research schema](../dataset/RESEARCH_SCHEMA.md) and [leakage grouping guide](../dataset/LEAKAGE_GROUPING.md) before preparing a new run.

The accepted local research workflow creates validated exports, conservative whole-group split guards and a reserved development allocation. On the machine holding the designated data, use **new output directory names** for each run:

```bash
.venv/bin/python -m campusmail doctor --require-datasets
.venv/bin/python scripts/prepare_research_data.py --output-dir artifacts/research/data03-MY_RUN
.venv/bin/python scripts/build_leakage_components.py --input-run artifacts/research/data03-MY_RUN --output-dir artifacts/research/data04-MY_RUN
.venv/bin/python scripts/reserve_research_splits.py --input-run artifacts/research/data03-MY_RUN --component-run artifacts/research/data04-MY_RUN --output-dir artifacts/research/data05-MY_RUN
```

Inspect each report and its source IDs before proceeding. These commands cannot be used successfully on a fresh clone with no dataset. The installed corpus and original run are documented in [DATA-03 acceptance](../reports/DATA03_CORPUS_ACCEPTANCE.md) and [DATA-04 acceptance](../reports/DATA04_COMPONENT_ACCEPTANCE.md). Operational collection IDs live in [dataset_collections.json](../dataset_collections.json); moving an export between laptops must not create a new collection identity.

To validate a v2 research file without changing it:

```bash
.venv/bin/python -m campusmail dataset validate --input tests/fixtures/research_v2.jsonl --report artifacts/verification/research-fixture.json
```

Legacy v1 exports need an explicit `campusmail dataset migrate-v1` conversion. The [schema guide](../dataset/RESEARCH_SCHEMA.md) gives its required arguments and review rules. Do not feed an arbitrary file into training.

## Train and activate the local classifiers

The two tasks are academic category and actionability. The training command reads only the reserved development allocation. Replace the three run paths below with the validated paths produced above:

```bash
.venv/bin/python -m campusmail train --task academic --input-run artifacts/research/data03-MY_RUN --component-run artifacts/research/data04-MY_RUN --reservation artifacts/research/data05-MY_RUN
.venv/bin/python -m campusmail train --task actionability --input-run artifacts/research/data03-MY_RUN --component-run artifacts/research/data04-MY_RUN --reservation artifacts/research/data05-MY_RUN
.venv/bin/python scripts/activate_plain_model.py --task academic
.venv/bin/python scripts/activate_plain_model.py --task actionability
.venv/bin/python -m campusmail doctor
```

The training output goes under ignored `artifacts/models/`. Training alone does not make a model active. Activation verifies hashes and compatibility metadata before the app loads the artifact. `scripts/manage_model_bundle.py` supports sealing, status, promotion and rollback of versioned standby bundles; see [bundle acceptance](../reports/OPS01_ACCEPTANCE.md). The [local activation report](../reports/LOCAL_MODEL_ACTIVATION_20261029.md) records the development Mac's currently activated models. A fresh clone has none.

Current scores measure agreement with source or weak labels. They are **not human-reviewed real-world accuracy**. The independent DATA-06 pilot still needs completed reviewer forms and adjudication. See [preliminary results](../reports/PRELIMINARY_RESULTS.md), [annotation handoff](../dataset/ANNOTATION_HANDOFF.md) and the [remaining ML tasks](../ML_IMPROVEMENT_TASKS.md).

## Import the scoped example collection

The import is optional and requires the designated dataset. In the app, use **Settings → Import scoped mail dataset** and watch **Background activity**. Re-imports use stable source IDs. For a bounded command-line import into the default local runtime:

```bash
.venv/bin/python -m campusmail import --collection scoped --limit 50 --profile "My campus"
```

Do not import into a teammate's live profile without first checking the profile and collection identity. A fresh clone can be demonstrated more simply with **Analyze a notice**.

## Optional external services

Gmail uses read-only OAuth; Google Calendar is a separate opt-in connection. The [README](../README.md#use-your-own-email-optional) has the student setup steps. OS credential storage is required. The app does not fetch Google Drive content or send email.

Basic daily and weekly summaries work locally. For optional enhanced weekly wording, create a private JSON file outside Git:

```json
{
  "endpoint": "https://your-provider.example/v1/chat/completions",
  "model": "your-model-name",
  "api_key": "YOUR_PRIVATE_API_KEY"
}
```

Choose this file under **Settings → Optional AI wording**, then explicitly request enhanced wording in the weekly briefing. The app sends selected structured facts, checks returned dates and IDs, and falls back to local wording if the provider fails or gives invalid output. Do not commit this file or claim that the paid provider was live-tested by the local verification suite.

## Package for the current operating system

Build on the operating system you intend to package. Install and verify models first if the package should include them:

```bash
.venv/bin/python -m pip install pyinstaller==6.16.0
.venv/bin/python scripts/build_backend.py
.venv/bin/python scripts/smoke_sidecar.py
npm --prefix desktop run package
```

The desktop release is under `desktop/release/`. The sidecar packages code and installed model artifacts, not the private corpus, profiles, attachments or credentials. Windows packaging must run on Windows; a signed Windows installer and cross-platform release validation remain separate work.
