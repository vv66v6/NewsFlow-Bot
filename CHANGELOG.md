# Changelog

Notable changes to NewsFlow-Bot. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and version numbers
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**The project is still `0.x`**, so the configuration surface can still change
between minor releases. [docs/compatibility.md](docs/compatibility.md) states
what is covered, what never will be, and what 1.0 is going to freeze — read it
before you pin a version.

## [0.9.4] - 2026-08-25

Version numbering: 0.10.0 and 0.10.1 were withdrawn and their tags removed, and
numbering resumed here at 0.9.4, because this project's minor field does not go
past 9. Nothing they contained was reverted — all of it is in this release.
Their source stays reachable by commit (`ca2a8db` and `5d8d43c`). Do not pull
their images: both carry the article-truncation bug fixed below, and the
`0.10.0`, `0.10.1` and `0.10` tags are being withdrawn from the registry.
Pin `0.9.4`.

### Security

- `email_imap` sources now verify the IMAP server's TLS certificate. Connections
  were encrypted but never verified, which exposed the mailbox password and every
  message to an active machine-in-the-middle. **This can break an existing
  setup:** a self-hosted mail server with a self-signed certificate now fails to
  fetch until the certificate is replaced or the source sets `tls: insecure`.
  Mainstream providers (Gmail, Outlook, Fastmail, Yahoo, Zoho) are unaffected.
- User-supplied filter patterns now run on the `regex` engine with a match
  timeout. The standard library's `re` cannot be interrupted, so a catastrophic
  pattern wedged the event loop for the whole process. Timeouts and invalid
  patterns fail open with a warning, as before.
- The Docker Compose file publishes the API port on `127.0.0.1` instead of
  `0.0.0.0`. A VPS has no private interface, and read endpoints are unauthenticated
  unless `API_KEY` is set. Existing deployments keep their own compose file and are
  unaffected; put a reverse proxy in front, or change it back deliberately.

### Fixed

- **Large feeds silently lost most of their articles.** Response bodies were
  size-capped with `StreamReader.read(n)`, which returns only the bytes already
  buffered, so any body arriving in more than one chunk was cut short with no
  error anywhere. BBC News parsed as 4 of its 37 entries and the Guardian as 8 of
  45, while feeds small enough to arrive in one chunk were unaffected. Present in
  every release up to 0.10.1, in both the RSS path and `json_api` sources.
- Rate-limited webhook deliveries retry once instead of counting toward the
  destination's circuit breaker, which could disable a healthy endpoint after ten
  rate limits in a row. The wait comes from `X-RateLimit-Reset-After`, because
  Discord answers webhook 429s with a `Retry-After` in milliseconds.
- `email_imap` messages with no parseable `Date` header are stored with no
  publication date instead of 1900-01-01, which placed them outside
  `MAX_ENTRY_PUBLISH_AGE_DAYS` and dropped them from every dispatch round.

### Added

- `discord` and `matrix` outbound webhook formats. A Discord channel webhook
  needs no bot token, no server invite and no gateway connection; append
  `?thread_id=<id>` to the URL to post into a thread. `matrix` targets
  matrix-hookshot's generic webhook and must not have a transformation function
  configured.
- `tls` option on `email_imap` sources: `verify` (default) or `insecure`.
- Guidance for running translation and digests against a local LLM
  (Ollama, vLLM, LM Studio, LocalAI) in the user guide.

### Changed

- `ENTRY_RETENTION_DAYS` default raised from 7 to 10 days, so cleanup cannot
  delete the oldest day a weekly digest still needs.
- A `webhooks.yaml` on its own now satisfies the startup configuration check: a
  headless RSS-to-webhook deployment no longer needs a Discord or Telegram token.
- `GUIDE.md` moved to `docs/user-guide.md`, and `README_CN.md` was renamed to
  `README.zh-CN.md`.

## [0.10.1] - 2026-08-06 — withdrawn

### Fixed

- Feed delivery hardening and DEBUG log hygiene: `DB_ECHO` is decoupled from
  `LOG_LEVEL` so raising the log level cannot flush stored secrets into the log.

### Changed

- Documentation reconciled with the code after drift.

## [0.10.0] - 2026-07-18 — withdrawn

### Added

- Per-subscription message templates with `{placeholder}` substitution. A
  template that fails to render falls back to the default layout rather than
  losing the article.
- Discord mentions per subscription, built from a native role or user picker and
  whitelisted through `allowed_mentions` at delivery.
- Telegram forum-topic delivery: the topic is captured at subscribe time and
  delivery self-heals to the default view if the topic is later deleted.

## [0.9.3] - 2026-07-17

### Added

- Offline configuration validation (`make checkconfig`) covering `.env` and both
  YAML files, plus cross-file target references.
- Hot reload of `webhooks.yaml` and `sources.yaml` via SIGHUP or
  `POST /api/admin/reload`. A file that fails to parse keeps the previous state
  instead of killing the process.
- REST API completeness: subscription CRUD, OPML export, and `/metrics`.

### Changed

- Unknown keys in either YAML file are now a hard startup error. A typo used to
  be ignored silently, which is how an HMAC signing secret once disappeared.
- ruff upgraded from 0.1 to 0.15.

## [0.9.2] - 2026-07-17

### Added

- Channel management commands, digest scheduling with per-channel timezones, and
  a `/manage` button panel on Telegram.
- Filter matching semantics: an ASCII-only keyword matches on word boundaries, so
  `ai` stops firing on "brain" while still hitting "AI芯片"; CJK and punctuated
  keywords keep substring matching, which is the natural unit there.
- Same-language short-circuit, so an entry already in the target language is not
  sent to the translation provider.

### Security

- State-changing commands are gated behind administrator permissions. Button
  visibility was never access control.

## [0.9.1] - 2026-07-16

### Added

- Telegram command menu and inline keyboards.
- `FEED_MAX_CONCURRENT` and `LOG_FORMAT` wired through to the runtime.
- End-to-end delivery pipeline integration test.

### Fixed

- The dispatch loop survives a failed per-subscription commit instead of
  aborting the whole round.
- Subscriptions owned by another source are kept when a source leaves
  `sources.yaml`.
- httpx no longer logs bot tokens; JSON tracebacks render correctly.

### Changed

- `mypy --strict` and ruff became blocking CI gates.
- `asyncpg` raised to 0.30 so installs succeed on Python 3.13.

## [0.9.0] - 2026-06-01

First release to carry a version number in the tree. RSS, JSON-API, IMAP and
inbound-webhook sources feeding a platform-agnostic dispatch loop that delivers
to Discord, Telegram and declarative webhook destinations, with keyword and
regex filtering, optional translation, silent mode, AI daily and weekly digests,
an optional REST API, and Docker images published to GHCR.

Tags `v0.1.0` through `v0.8.0` were added retroactively to mark development
milestones that predate versioning. They have no changelog entries and no
published Docker images.

[0.9.4]: https://github.com/Lynthar/NewsFlow-Bot/compare/v0.9.3...v0.9.4
[0.10.1]: https://github.com/Lynthar/NewsFlow-Bot/compare/ca2a8db...5d8d43c
[0.10.0]: https://github.com/Lynthar/NewsFlow-Bot/compare/v0.9.3...ca2a8db
[0.9.3]: https://github.com/Lynthar/NewsFlow-Bot/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/Lynthar/NewsFlow-Bot/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/Lynthar/NewsFlow-Bot/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/Lynthar/NewsFlow-Bot/compare/v0.8.0...v0.9.0
