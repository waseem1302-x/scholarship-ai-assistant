# Phase 1: correctness and security repairs

## Delivered

- Added immutable `opportunity_cycles` for recurring and historical application
  windows, while retaining existing date fields as the current/legacy projection.
- Added an effective application-window evaluator with `upcoming`, `open`,
  `closed`, `rolling`, `deadline_unknown`, and `archived` states. `open_now=true`
  returns only fresh, officially verified `open` or `rolling` records.
- Added typed `eligibility_rules` carrying type, operator, structured value,
  optional unit/grading scale, required/preferred semantics, source reference,
  confidence, and curator notes.
- Added eligibility status, fit score suppression on hard failure, evidence
  completeness, confidence, warnings, matcher version, and evaluation timestamp
  to match results. A closed application window, wrong degree, explicit legacy
  nationality exclusion, or failed required structured rule cannot show a
  positive fit score.
- Replaced browser local-storage token persistence with an in-memory access
  token and refresh-session cookies. Production omits refresh tokens from JSON,
  validates CSRF for cookie refresh/logout, and uses secure/HttpOnly/SameSite
  cookie settings.
- Added production JWT-secret validation, security headers, and an in-process
  login/register abuse limiter. CI now rehearses Alembic against PostgreSQL.
- Added hashed, expiring, single-use email-verification and password-reset
  tokens. Password reset revokes every existing refresh session. In development
  and test only, token endpoints return a debug token; production deliberately
  returns no token until a transactional email sender is configured.
- Added administrator password re-authentication and a short-lived, single-use
  `X-Admin-Step-Up` token for production admin mutations. Production also
  requires the administrator's verified email. Administrator actions and token
  consumption produce audit-log records.
- Added `python -m app.cli.reconcile_opportunity_lifecycles` to mark active
  opportunities expired when their official effective window closes, while
  retaining the record and its provenance.
- Added static frontend accessibility regression checks for language, main
  landmark, status announcements, form autocomplete, and visible keyboard focus.
- Added Playwright/Chromium browser journeys for student registration,
  catalogue loading, logout, and keyboard navigation. GitHub Actions now starts
  the API and runs these browser journeys against a live PostgreSQL-backed app.

## Verification

- Non-browser `pytest`: 72 passed (one upstream Starlette TestClient
  deprecation warning). Browser end-to-end suite: 2 passed against the local
  Docker application.
- `ruff check .` and `ruff format --check .`: passed.
- Fresh SQLite Alembic upgrade through `20260811_0005` and downgrade back to
  `20260722_0004`: passed locally.
- Docker Compose build with PostgreSQL 16: passed locally. The API applied every
  migration through `20260811_0006`; `GET /health/ready` returned `200`, and
  the new account-security tables exist in PostgreSQL.

## Release boundaries

- A transactional email sender is intentionally not configured. The secure
  token architecture is complete, but production email delivery needs the
  product owner to choose and authorize a provider.
- Password re-authentication is the implemented administrator step-up method.
  MFA/WebAuthn and a distributed rate-limit backend remain Phase 9 launch
  hardening, not unimplemented Phase 1 requirements.
- Browser automation is now available through Playwright/Chromium and is part
  of CI. Broader cross-browser, assistive-technology, and user research testing
  remain release-quality work before a public launch.
- The reconciliation command is ready for a scheduler. A curator UI belongs to
  the later opportunity-data platform work.
