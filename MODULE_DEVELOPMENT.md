# Module API v1

A package contains `manifest.json`, an entry point, resources, and optional `vendor/` dependencies. No code is downloaded at run time. Modules execute as trusted code in a separate worker process; they are not security-sandboxed.

The manifest declares `id`, `name`, three-part `version`, ISO `released` date, `summary`, `description`, `release_notes`, `platforms` (`windows`, `macos`), `api_version` (1), `host_version` (PEP 440 specifier), `dependencies` (bundled dependency descriptions), and `entrypoint`. The packaging tool computes the `files` SHA-256 map. Do not include secrets or customer data.

The entry point exports `create_module()`. Its object implements:

- `describe_settings()`: list of `{key, label, type, default?}` fields. Types: `text`, `boolean`, `choice`; choices may include `options: [{value,label}]`.
- `validate(path)`: empty string when valid, otherwise a user-facing error.
- `preview(path, settings)`: proposed output name. No remote mutation.
- `open(settings, credentials)`: initialise resources and authenticate. The built-in uploader receives credentials over the worker's stdin, never command-line arguments or files. Other modules receive an empty credentials object in v1.
- `prepare(job)`: return `(name, baseline_dict)` without submitting. Job includes `id`, `path`, `settings` (JSON string), `name`, `baseline` (JSON string), attempts and state. The host persists preparation before calling submit.
- `submit(job)`: perform one operation and return `automation_hub.api.Result`.
- `reconcile(job)`: inspect whether the prior operation completed; never submit again.
- `close()`: release resources, including partially opened ones.

`Result(state, remote_id='', verification='', error='')` accepts `completed`, `failed`, or `needs_review`. Only use `failed` if it is known that no remote operation committed. A timeout after a request is usually `needs_review`. A completed result must carry an honest verification label.

The host emits newline-delimited JSON worker events: `description`, `preview`, `options`, `progress`, `notice`, `error`, and `finished`. stdin accepts pause/resume/stop between jobs. Module logs should go to stderr, not stdout. A module must make browser/network operations bounded so stop can finish promptly. Settings and queue operations are not deleted by module uninstall.

An optional `options()` returns `{field_key: [{value,label}]}` after `open`; the UI's Refresh account choices action uses this for Help2Rent. Non-Help2Rent modules should declare static choices for v1. The current file picker accepts XLSX workbooks; other file types require a future host capability update.

## Build an offline example

```sh
python tools/package_module.py examples/workbook-checker dist/workbook-checker-1.0.0.hubmodule
```

Install that file in the app. Workbook Checker runs offline and submits nothing. It proves module installation and execution independently of Help2Rent.

Pure-Python libraries can be copied into `vendor/`. Native extensions must match Python 3.13, target architecture and operating system; build separate packages and restrict `platforms`. Never invoke pip from a module. List dependency licences alongside bundled libraries.

## Catalogue

```sh
python tools/build_catalogue.py --base-url https://github.com/OWNER/REPOSITORY/releases/download/v1.0.0 --output dist/catalogue.json dist/workbook-checker-1.0.0.hubmodule
```

Upload the module and catalogue as release assets when ready, then configure the catalogue's HTTPS URL in the app. No GitHub account/token is embedded. Private repositories need a future authentication implementation. Catalogue format is `{schema_version: 1, modules: [...]}`; each entry carries its manifest plus `download_url` and whole-package `sha256`.

Hashes detect corruption, not publisher identity. Use a trusted catalogue or receive files directly from a trusted developer. Updates switch the active version only after extraction and validation. The previous version is retained for rollback. Module package changes are blocked while a worker owns the queue lock.
