# Campus Mail

Campus Mail is a **desktop assistant for academic email**. It turns supported notices into assignments, events, resources, reminders, reply-needed items and marks. Each result keeps a link to its source, so the student can check it and correct uncertain details.

The app has a React/Electron interface and a Python backend. It stores each local profile in SQLite. Gmail and Google Calendar are optional connections; you can try the app by pasting a notice without connecting either service.

## Start here

You need **Python 3.12**, **Node.js 22 or newer**, and npm. Run the commands from the project folder. Internet access is needed for the first dependency install.

### macOS or Linux

```bash
cd /path/to/campus-mail-analyzer
bash scripts/setup.sh
npm --prefix desktop start
```

### Windows PowerShell

```powershell
cd C:\path\to\campus-mail-analyzer
.\scripts\setup.ps1
npm --prefix desktop start
```

The setup script creates a Python virtual environment, installs the Python and desktop dependencies, checks the Python setup, and builds the desktop interface. On later runs, **only** run `npm --prefix desktop start`. Keep that terminal open while using the app. Close the desktop window or press `Ctrl+C` to stop it.

**You do not need to start the backend separately.** Electron starts the Python API on a free local port and stops it when the app closes. If the interface has changed since your last build, run `npm --prefix desktop run build` before starting it again.

If Python 3.12 is not the default `python3.12` on macOS/Linux, choose it with `CAMPUS_SETUP_PYTHON=/path/to/python3.12 bash scripts/setup.sh`. On Windows, pass `-Python C:\path\to\python.exe` to `setup.ps1` if the `py -3.12` launcher is unavailable. Use the Windows environment on Windows; do not copy a virtual environment from another operating system.

## Try the main workflow

1. Open the app and create or select a local profile.
2. Click **Analyze a notice**. Paste a sample notice with a course, task and clear date, then analyze it.
3. Open **Assignments** or **Events** to inspect the record. Check its date, resource link and original evidence.
4. Open **Review** for questions the app could not settle safely. Confirm or correct an item and check the result again.
5. Open **Calendar** to see due markers and events. You can import a timetable from **Settings** and review any proposed move of a personal work block before approving it.
6. Open **Models** to see whether local classifiers are active. A fresh clone can still analyze notices with rules when no model artifact is installed.

For a quick example, enter **NLP201 Assignment 2** as the subject and paste this as the notice text:

```text
NLP201 Assignment 2 must be submitted by 12 November 2026.
Instructions: https://example.edu/task.pdf
```

Look for the assignment in **Assignments**, then open it to check the date and source. The URL is an example link; the app does not download the page. If the course is not confirmed in your profile, the app may ask you to review its relevance.

For a fuller test, import a supported TXT, CSV, HTML, text-based PDF, DOCX or XLSX file. Scanned PDFs and images are not read by the baseline document readers. Unreadable files are marked as such instead of being treated as understood.

## Use your own email (optional)

Campus Mail can connect to Gmail with **read-only** access. It cannot send, draft, archive or delete mail. The first sync starts with the latest 50 inbox messages by default; related threads and older attachments are searched within limits. It does not guarantee that every old deadline will be found.

To connect:

1. In your own Google Cloud project, enable the Gmail API. Enable the Google Calendar API only if you want calendar integration.
2. Configure an OAuth consent screen and a **Desktop app** OAuth client. Add test users if the Google project is in testing mode.
3. Download the client JSON and keep it outside Git.
4. In Campus Mail, open **Settings → Gmail → Connect**, choose the JSON and finish authorization in your system browser. Connect Google Calendar separately if needed.
5. Use **Sync now** in Settings and watch **Background activity** for progress or errors.

Provider tokens go to the operating system's credential vault, not ordinary app tables. Google or an institution may impose its own verification and access restrictions. Google Drive URLs are saved as links; the app does not fetch Drive files.

## Dataset and models

The private dataset and trained model files are **not included in a fresh clone**. They are not required to launch the app or analyze a pasted notice. Keep private data, generated models, local profiles and OAuth files out of Git.

On the development Mac, two checksum-verified local classifiers have been activated. On another machine, model status depends on the artifacts installed there. The app can fall back to verified model bundles or local rules when a preferred artifact is unavailable. **Training scores from source or weak labels are preliminary; the independent human-reviewed accuracy study is unfinished.**

If you have the designated research corpus and want to prepare data, train and activate models, follow the [development and research guide](docs/DEVELOPMENT.md). The [dataset guide](dataset/README.md) explains what belongs in the private dataset directory.

## Check your installation

Run these from the project root after setup:

```bash
.venv/bin/python -m campusmail doctor
.venv/bin/python -m pytest -q -m 'not research'
npm --prefix desktop test
npm --prefix desktop run build
```

On Windows, replace `.venv/bin/python` with `.\.venv-win\Scripts\python.exe`. `doctor` prints a JSON health report. The normal test suite uses temporary data and does not require the private corpus or live Google access. To check a locally installed corpus, add `--require-datasets` to the doctor command; that check will fail on a fresh clone by design. A desktop integration test and further research checks are in the [development guide](docs/DEVELOPMENT.md).

## Common problems

| What you see | What to do |
|---|---|
| Python 3.12 is not found | Install Python 3.12 or select its executable in the setup command above. |
| `npm --prefix desktop start` cannot find Python | Run the setup script on this computer first. The desktop uses `.venv` on macOS/Linux and `.venv-win` on Windows. |
| The desktop shows an old interface | Run `npm --prefix desktop run build`, then restart it. |
| Models are missing or the app says rules-only | The clone has no private model artifacts. The app can still work; see the model steps in the development guide if you have the corpus. |
| Gmail or Calendar will not connect | Check the Desktop OAuth JSON, enabled API, consent-screen test users, Google account permissions and OS credential vault. |
| A notice has no assignment or date | Check the source text and **Review**. Unclear dates, unsupported formats and uncertain identity may require a student decision. |

## What this release does and does not cover

The local app supports profiles, source-backed records, review, timetable and calendar planning, in-app reminders, summaries and a private marks tracker. Basic summaries work without an AI key. Optional AI wording uses a separately configured provider and selected structured facts; it is not needed for the main workflow.

Reminders and sync run while the app is open and can catch up after restart. The app cannot deliver live reminders while the computer is off. It is a local desktop project, not a hosted multi-user service. Live Gmail/Calendar authorization, optional paid AI wording and signed Windows distribution need separate configuration and validation.

See [feature coverage](FEATURE_COVERAGE.md) for the detailed feature boundary, [build progress](BUILD_PROGRESS.md) for implementation evidence, and [ML tasks](ML_IMPROVEMENT_TASKS.md) for remaining research work.
