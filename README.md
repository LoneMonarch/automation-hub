# Automation Hub

A local desktop application for Windows and macOS. The included Help2Rent module uploads Excel contact lists; additional modules can be installed from a file or a configurable HTTPS catalogue.

## For the person using the app

1. Install **Automation Hub** using the Windows setup program, or copy the Mac app into Applications.
2. Open **Settings**, enter your Help2Rent account, and click **Save Settings**. Passwords go into Windows Credential Manager or macOS Keychain.
3. Open **My Modules** and click **Refresh account choices**. The app automatically selects the existing upload tag previously used by the old uploader (Help2Rent tag ID `31`). Choose the officer and check the displayed tag before continuing.
4. Add your Excel files or a folder. Click **Preview**, check the results, then **Start**.
5. Watch progress in **Activity**. Pause or stop finishes checking the current submission first. Use **Resume Queue** to continue after restarting the app.

Open the **Tutorial** tab at any time for an explanation of every step, including why the app previews files, how the `sample` tag is selected, what each activity state means, and how to recover an uncertain upload. Settings also includes an **Open Step-by-Step Tutorial** button.

Original files are never moved or deleted. The app copies them into its own queue. Completed files are skipped when the same content, destination, account, and settings are selected again. **Upload Again** intentionally creates a new submission.

If an upload is uncertain, the queue stops. Resume checks the website again without resubmitting. **Resolve Uncertain Upload** lets you record your own website check. Do not mark an upload as absent unless you have checked the website. Verification means a new list was found, not that every contact was imported correctly.

**Export Report** produces a CSV of saved results even if a previous session was interrupted.

### Installing modules

Use **Install Module from File** for a `.hubmodule` or `.zip` package supplied by a trusted developer. The app checks its contents and compatibility. Installed modules run without further downloads. Modules are executable code, not sandboxed applications.

Alternatively, enter a catalogue HTTPS URL in Settings, then browse **Module Catalogue**. Search, view descriptions/version dates, and click **Install / Update Selected Module**. The catalogue is cached for offline viewing. Downloads and website uploads require internet; offline modules do not.

Module updates preserve history/settings. **Roll Back** returns to the previous installed version. Uninstall preserves stored data. The built-in Help2Rent module remains available when an installed override is removed.

### Existing uploader data

Choose **Import Previous Configuration & Reports** in Settings and select the old project folder. This copies account settings and historical CSV reports; no spreadsheet is submitted or moved. Historical reports are labelled as historical evidence, not current verification. Refresh account choices after migration.

The old project files and archives are retained. The original `run_upload.py` implementation is retained for reference, but its command-line entry point opens the new desktop app to prevent accidental legacy uploads. The inspection scripts remain developer tools.

### Data location

- Windows: `%LOCALAPPDATA%\AutomationHub`
- macOS: `~/Library/Application Support/AutomationHub`

Back up this folder while the app is closed to preserve queues and history. Credentials stay in the operating system credential store and are not included in a folder backup. No catalogue is configured by default.

## Development

Requires Python 3.13. Supported package targets: Windows 11 x64 and macOS 14+ (build separately for each CPU architecture).

```sh
python -m venv venv
# Activate the environment for your operating system, then:
python -m pip install -r requirements-build.txt
python -m playwright install chromium
python desktop.py
python -m unittest discover -s tests -v
```

`start.sh` is a Mac developer launcher. Packaged users never install Python or use these commands.

The UI lives in `automation_hub/ui.py`; the process-isolated worker implements the module contract in `automation_hub/api.py`. SQLite stores durable job states. Module code does not own queue transactions. The worker commits the baseline and submission intent before clicking Submit and reconciles interrupted jobs before any retry. A system-held lock prevents simultaneous workers and module changes during a job.

### Build installers

```sh
python tools/build_app.py
```

This bundles the matching Playwright Chromium browser. Windows builds require Inno Setup 6; Mac builds produce an app and DMG. The GitHub Actions workflow builds each OS independently and saves artifacts; it does not publish a release automatically. Only app code and explicit notices are included, not this project's configuration, spreadsheets, reports, or browser sessions.

**Release gates:** clean Windows-machine acceptance, Windows signing, Mac signing/notarisation, and a small explicitly authorised live-site validation remain required before calling the release ready for nontechnical users. Unsigned builds can show operating-system warnings. Local tests use a mock website and do not prove compatibility with the current live Help2Rent page.

See `MODULE_DEVELOPMENT.md` for module authoring, `AUDIT.md` for findings and changes, and `THIRD_PARTY_NOTICES.md` for dependencies.
