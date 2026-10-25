# Campus Mail

A Python-first academic mail assistant with a thin Electron desktop interface. It analyzes notices and readable attachments, maintains evidence-linked academic records, learns personal preferences, and brings calendars, assignments, resources, requests and marks into one workspace.

## Fresh clone without the private dataset

Use Python **3.12** for the shared development environment and Node.js 22 or newer.
The dataset and trained artifacts are optional for development. A fresh clone runs
rules-only analysis until trusted model artifacts are installed. Do not copy your
teammate's Windows virtual environment onto macOS.

macOS/Linux:

```bash
bash scripts/setup.sh
.venv/bin/python -m campusmail doctor
.venv/bin/python -m pytest -q
npm --prefix desktop start
```

Windows PowerShell:

```powershell
.\scripts\setup.ps1
.\.venv-win\Scripts\python.exe -m campusmail doctor
.\.venv-win\Scripts\python.exe -m pytest -q
npm --prefix desktop start
```

For backend-only development use `bash scripts/setup.sh --backend-only` or
`.\scripts\setup.ps1 -BackendOnly`. Set `CAMPUS_SETUP_PYTHON` on macOS/Linux or
pass `-Python` on Windows to select a Python 3.12 executable. Setup consumes
`requirements-dev.constraints`; the older Linux lock is a historical snapshot.
The constraints were resolved on macOS; Windows-only dependencies and the complete
Windows environment must be verified by the CI matrix, which saves each platform's
installed versions. This is not a fully hash-locked cross-platform environment.

Default Python tests use temporary data, fake credential storage, blocked external network
connections and no installed private model bundle. Private-data checks are opt-in:

```bash
.venv/bin/python -m campusmail doctor --require-datasets
.venv/bin/python -m pytest --run-research -m research -q
```

Those commands deliberately fail with missing-input diagnostics when the research
exports are absent. `doctor` emits JSON and exits nonzero for broken dependencies,
failed imports, incompatible/invalid model metadata, or explicitly required missing
datasets. It never opens the credential vault or loads a pickle. Matching model
metadata is **not** an integrity or prediction-quality check; full artifact
verification remains a later implementation task.

Implementation status: [ML_IMPROVEMENT_TASKS.md](ML_IMPROVEMENT_TASKS.md).

Research exports can now be checked against the explicit v2 contract without
changing their contents:

```bash
.venv/bin/python -m campusmail dataset validate --input tests/fixtures/research_v2.jsonl --report artifacts/verification/research-fixture.json
```

To convert a designated legacy research export, run `campusmail dataset migrate-v1`
with explicit input/output paths, dataset ID, task, data origin and source type.
See [the research schema guide](dataset/RESEARCH_SCHEMA.md) for the command and its
conservative annotation rules. Operational import identities are declared in
[dataset_collections.json](dataset_collections.json).

See the [research schema guide](dataset/RESEARCH_SCHEMA.md) for annotation
completeness, evidence offsets, Windows commands and validation errors. Existing
v1 exports require an explicit migration; the current training/import behavior
has not been switched to v2 automatically.

## Original development workspace

The original author's workspace had a Python environment, desktop dependencies,
two trained model families and fifty imported records in a **My campus** profile.
These ignored local resources are not included in a fresh clone.

```bash
npm --prefix desktop start
```

Choose **My campus** on the welcome screen. Settings → Import scoped mail dataset imports the rest of the scoped collection as a durable background job. Re-imports reuse source records. The first import may take time; progress/errors are visible under Background activity. Sanitation placeholders are deliberately not presented as usable original web links.

## Fresh development setup

The reproducible setup scripts target Python 3.12 and Node.js 22 or newer.
The training/import commands below additionally require the designated datasets.

Linux/WSL:

```bash
bash scripts/setup.sh
.venv/bin/python -m campusmail train --task academic
.venv/bin/python -m campusmail train --task actionability
.venv/bin/python -m campusmail import --collection scoped --limit 50 --profile "My campus"
npm --prefix desktop start
```

Windows PowerShell:

```powershell
.\scripts\setup.ps1
.\.venv-win\Scripts\python.exe -m campusmail train --task academic
.\.venv-win\Scripts\python.exe -m campusmail train --task actionability
.\.venv-win\Scripts\python.exe -m campusmail import --collection scoped --limit 50 --profile "My campus"
npm --prefix desktop start
```

Use the Windows environment on Windows; the Linux `.venv` cannot run in Windows. For this WSL workspace, local copies of three missing Electron libraries were extracted under ignored `runtime/linux-deps/`; the launcher discovers them without changing system packages. On a fresh Linux system, normal Electron runtime libraries are required.

## What is implemented

- Isolated local profiles, hashed application sessions, transactional SQLite data, revision history and durable background work.
- Pasted notices and local TXT, CSV, HTML, text-PDF, DOCX and XLSX readers. Unreadable/unsupported attachments retain their status instead of guessed content.
- Self-trained TF-IDF + Naive Bayes and linear SVM models, a majority baseline, grouped evaluation and an honest model-comparison screen.
- Date roles, supported exact times, required actions, course/profile evidence, assignments and events. Ambiguous dates become review questions. Original text and evidence are retained.
- Cross-email resource relationships, exact-duplicate hashes, attachment-only notices and protected attachment downloads. Drive stays a link; arbitrary linked pages are not fetched.
- Personal importance overrides, feedback records, topic/course preference weights, participation choices, relevance decisions and preference reset. No operational student feedback trains the shared models.
- Timetable and holiday schemas, guided external-AI prompts, validation, preview, explicit activation, weekly recurrence, term dates and dated exceptions. Combined batch schedules must be resolved before import.
- Internal calendar, due markers, interval conflicts, workload clustering and proposed moves of flexible personal blocks. Official times never move automatically; proposals require approval and a fresh availability check.
- Thread request tracking, sent-reply resolution, user resolution overrides, a private marks tracker and exact-row matching against a confirmed roll number. Unknown grading rules do not produce a guessed total.
- In-app reminders, catch-up on restart, daily snapshots, live weekly summaries and optional API wording with structured facts and local fallback.
- Real Gmail and optional Google Calendar adapters, separate OAuth scopes, OS-vault tokens, bounded history backfill, cursor recovery and stable remote-event identifiers. These need your own application OAuth configuration and interactive authorization.

See [FEATURE_COVERAGE.md](FEATURE_COVERAGE.md) for the requirement-to-code/test map and explicit limitations.

## Connect Google services

1. In your Google Cloud project, enable Gmail API and (optionally) Google Calendar API.
2. Configure the OAuth consent screen and a **Desktop app** OAuth client. Configure test users while using Google's testing mode.
3. Download the desktop client JSON to a private location outside Git.
4. Open Settings in Campus Mail and select Connect for Gmail. Choose that JSON and complete authorization in your system browser. Connect Google Calendar separately if desired.

Gmail uses `gmail.readonly`: the application does not send, draft, archive or delete mail. Calendar uses app-created-calendar access plus read access to authorized external events. Drive content is not requested. Google testing/verification and institution administrator restrictions are external prerequisites; public distribution requires the applicable Google verification process.

Tokens live in Windows Credential Manager or the platform's OS keyring. Linux requires an unlocked Secret Service/keyring. If unavailable, the app reports it rather than writing tokens to a plaintext fallback. Connecting a ChatGPT Gmail connector is separate from configuring this application's own OAuth client.

Email processing starts with the latest 50 inbox messages. Settings can change labels/senders. Relevant threads are read for context; bounded searches look for referenced older assignment attachments. This is intentionally not a promise that 50 messages contain all deadlines. Provider failures remain visible in background jobs and sync warnings.

## Optional API summary wording

Local summaries require no API. To enable optional wording, create a private JSON file:

```json
{
  "endpoint": "https://your-provider.example/v1/chat/completions",
  "model": "your-model-name",
  "api_key": "YOUR_PRIVATE_API_KEY"
}
```

Settings → Optional AI wording → Choose provider configuration JSON. The endpoint must implement the chat-completions request/JSON-object response contract. Keys go directly to the OS vault through the desktop main process. Open the weekly briefing and explicitly request enhancement; selected structured facts are sent, not the entire mailbox. IDs and numerical facts are checked, canonical dates/evidence remain authoritative, invalid outputs fall back locally, and repeated identical requests use a personal cache. Qualitative generated wording still needs source verification.

## Tests and research

```bash
.venv/bin/python -m pytest tests -q
npm --prefix desktop test
npm --prefix desktop run build
cd desktop
npx playwright test tests/desktop.spec.cjs --workers=1
```

The Electron test uses a temporary profile and real Python API. It does not connect Google, send mail, access private dataset contents, or call an AI provider. On this WSL system, pass the local `runtime/linux-deps/root/usr/lib/x86_64-linux-gnu` directory through `LD_LIBRARY_PATH` when running Playwright directly. Playwright disables Chromium's sandbox for its test process; the normal application keeps renderer sandboxing and context isolation enabled.

Research artifacts are in ignored `artifacts/models/`. Academic training uses the scoped designated mail research export; public actionability uses Charlie9, not a random merge with overlapping Parakweet data. Unknown-license university PDFs remain quarantined and are not automatically trained on. The current academic split has 438 labeled examples; the actionability split has 3,655. Source/weak-label agreement is preliminary, not a reviewed gold benchmark. Pipelines fit TF-IDF on training data only; duplicate/source groups do not cross the holdout boundary. SVM is a predeclared deployment choice, not selected by repeatedly tuning on the final test set.

## Layout and data boundaries

```text
backend/campusmail/   Python API, domain services, adapters, research training
desktop/             Electron main/preload, React renderer, desktop tests
tests/               Phase-first behavioral and integration tests
dataset/mail/        Preserved private originals and sanitized mail research exports
dataset/public/      Public raw/normalized/quarantined resources and provenance
dataset/tools/       Research acquisition/inspection utilities
schemas/             Versioned schedule import schemas
prompts/             External-AI prompt templates with schemas
scripts/             Setup and current-platform packaging
runtime/             Ignored local profiles, blobs, queue and local runtime libraries
artifacts/           Ignored trained models, reports and test screenshots
```

The Python implementation is a modular monolith. The local repository and job ledger use SQLite behind an owner-scoped boundary. Electron proxies a restricted API through a preload bridge; provider tokens and the backend bootstrap key never enter renderer JavaScript. Email HTML is converted to visible text, attachment paths are generated hashes, downloads enforce the profile's blob directory, and browser links allow only HTTP(S).

Multiple local profiles are isolated by the API, but the same operating-system owner can select those profiles. This is a desktop trust boundary, not hosted password-based multi-user authentication. Hosted PostgreSQL/worker deployment and cross-device accounts remain future deployment work.

## Packaging

Build for the operating system on which the build command runs; Windows installers are built on Windows.

```bash
.venv/bin/python -m pip install pyinstaller==6.16.0
.venv/bin/python scripts/build_backend.py
npm --prefix desktop run package
```

Verify the standalone Python runtime with `.venv/bin/python scripts/smoke_sidecar.py`. The desktop workflow can also run against the unpacked executable: set `CAMPUS_PACKAGED_EXECUTABLE` to its absolute path before running the Playwright command above. Both checks use temporary profiles.

The Python sidecar bundles application code and trained model artifacts, never the mail dataset, runtime profile database, attachments or credentials. `desktop/release/` contains the unpacked desktop build. Installers/code signing and testing on other operating systems are separate distribution steps. Models must exist before packaging; build dependencies and compiled libraries are platform-specific.

Closing the application stops its backend. Syncing and in-app reminders run while it is open and catch up when reopened; delivery while the machine is off is not supported. Scanned images/PDFs need an optional OCR adapter. Complex layouts and ambiguous language go to review. Automatic mail drafting/sending, Drive downloads, and external notification channels are outside the agreed initial release.
