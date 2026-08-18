# Changelog

## [Unreleased]

## [0.1.2] - 2026-08-18

### Added

- Report tasks now display their current prompt and let operators edit it directly.
- In automatic mode, a successful report uses the current prompt, then safely evolves and persists
  the complete prompt for the next report from the current task prompt and raw message data.
- Manual mode keeps the operator-provided prompt unchanged between reports.

## [0.1.1] - 2026-08-18

### Added

- Report tasks can now be edited from the WebUI, including sources, schedule, delivery targets,
  enabled state, and report prompt controls.
- Each report task supports either adaptive analysis based on the current report-window data or a
  custom operator-provided report prompt.
- Report tasks can be deleted after confirmation; future scheduled runs are removed immediately.

### Changed

- Deleting a report task also removes its related runs, reports, and delivery logs through the
  existing foreign-key cascade. Sources, accounts, AI configuration, and delivery targets remain.

## [0.1.0] - 2026-08-17

### Added

- Core database, authentication, internal ingestion API and Source consent.
- Telegram TDLib collector and AstrBot QQ adapter with persistent Outbox.
- Hourly/daily report engine, OpenAI-compatible analysis and Feishu delivery.
- React administration UI, Docker Compose, CI and security/privacy documents.

### Known limitations

- Some QQ accounts are rejected by NapCat/QQ quick or password fallback login and require
  scanning a QR code again after the NapCat container restarts. Messages already accepted by
  the AstrBot Outbox and Core database remain persistent.

### Fixed

- Serialize report runs and keep LLM network calls outside SQLite write transactions, avoiding
  `database is locked` when scheduled tasks share a trigger time.
- Disable NapCat Docker logs because the upstream image prints temporary login QR URLs to stdout.

The local real-account, restart, failure and secret-scan acceptance gates passed. The 2C4G VPS
performance check is deferred until after release and remains unverified.
