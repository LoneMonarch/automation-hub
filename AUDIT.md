# Code audit and redesign

Source inspection found a monolithic uploader combining UI, configuration, browser automation, file movement and reporting. The old script used broad page-text success detection, including default success for unrecognised responses; partial dropdown matching; name-only verification; current-page-only inventory; end-of-run CSV generation; and retries spanning both remote submission and local file moves. Startup and working-directory assumptions were Mac-specific. Documentation contained credentials and stale operating notes. No module boundary or regression suite existed.

## Implemented replacement

- A PySide6 desktop host with separate module worker processes, settings, previews, activity and catalogue screens.
- Durable SQLite queue transitions, file fingerprints scoped by module/settings, copied source files, explicit intentional reuploads and system-held worker locking.
- Submission baseline IDs persisted before Submit; new-ID verification; pagination traversal; exact dropdown values; bounded waits; unknown results stop for review without automatic resubmission.
- Completed remote state preserved when a later local event/report fails. Exports query persisted state rather than end-of-run memory.
- Offline package installation, compatibility and file-hash checks, cached catalogue, atomic version activation, rollback, data-preserving uninstall and a module SDK example.
- OS credential storage, explicit legacy migration, clean documentation, pinned runtime/build dependencies, explicit packaging allowlist, Windows/macOS build workflow.

## Known boundaries / release checks

- Site verification proves list creation, not full contact import. The live website may require selector/pagination adjustments; tests intentionally use a local fixture.
- A pre-existing list created concurrently by a different uploader after the baseline could still be ambiguous. Use one uploader per account; remote idempotency is unavailable.
- XLSX checks validate container integrity, not contact-column semantics. The current host picker supports XLSX modules.
- Jobs run serially; pause/stop is cooperative at safe boundaries. The worker does not force-kill in-flight submissions.
- Modules are trusted executable code. SHA-256 is an integrity check, not a publisher signature. Private GitHub authentication is deferred.
- Module migrations requiring database schema changes are not part of API v1; modules should keep version-compatible settings.
- Windows clean-machine testing and release signing/notarisation cannot be certified from this Mac. No live uploads have been performed as part of this redesign.
- Existing original project data remains local and is excluded from builds. Historical reports are not promoted into freshly verified completed jobs.
