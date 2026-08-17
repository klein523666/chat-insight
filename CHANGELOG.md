# Changelog

## [Unreleased]

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
