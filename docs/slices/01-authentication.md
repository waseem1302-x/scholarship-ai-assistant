# Vertical Slice 1 — Secure Authentication

## Goal

Establish trustworthy user identity and session boundaries before storing
student profiles or allowing administrators to curate public opportunity data.

## Acceptance criteria

- A new public user can register only as a student.
- Emails are normalized and unique; passwords are never stored in plaintext.
- A valid user can log in and call a protected identity endpoint.
- Access tokens are short-lived and validated for signature, issuer, audience,
  expiry, token type, user, active status, and current role.
- Refresh tokens rotate once; replay revokes the whole token family.
- Logout is idempotent and revokes the refresh family.
- Inactive users lose protected and refresh access.
- Student/admin authorization can be declared and produces a safe 403 response.
- Database migrations upgrade and downgrade cleanly.

## Decisions

### Password hashing

- **Decision:** Argon2 via `pwdlib`.
- **Reason:** A memory-hard password hash is an appropriate default for new systems.
- **Alternative:** bcrypt; widely supported, but Argon2 is the chosen modern baseline.
- **Tradeoff:** Argon2 costs more memory/CPU by design and needs capacity tuning before scale.
- **Learning:** Password hashing, verification, and why encryption is the wrong primitive.
- **Portfolio evidence:** A tested credential boundary rather than plaintext or fast hashing.

### Access and refresh sessions

- **Decision:** 15-minute signed JWT access token plus 30-day random opaque refresh token.
- **Reason:** APIs can validate short-lived access locally while the database controls long sessions.
- **Alternative:** Database-backed opaque session cookie for every request.
- **Tradeoff:** Logout cannot revoke an already-issued access token immediately; it remains valid
  for at most its short lifetime. Database checks already disable an inactive user immediately.
- **Learning:** Token claims, rotation, hashing at rest, replay detection, and revocation families.
- **Portfolio evidence:** Session lifecycle tests covering both happy paths and token replay.

### Architecture

- **Decision:** Thin routes -> service -> repository -> SQLAlchemy model.
- **Reason:** HTTP, business rules, and persistence can be tested and changed independently.
- **Alternative:** Put database operations directly in FastAPI routes.
- **Tradeoff:** More small files now, but the opportunity and matching domains will not become
  entangled with transport details.
- **Learning:** Dependency injection, transaction ownership, and domain boundaries.
- **Portfolio evidence:** A scalable module pattern instead of a single-file demonstration.

## Demonstration

1. `POST /api/v1/auth/register` with an email and a 12+ character alphanumeric password.
2. Copy the access token into the API documentation's authorization control.
3. `GET /api/v1/auth/me` returns only safe user fields.
4. `POST /api/v1/auth/refresh` returns a replacement pair.
5. Reusing the old refresh token returns 401 and invalidates the replacement family.
6. `POST /api/v1/auth/logout` invalidates the active refresh family.

## Verification performed

- Ruff lint and formatting checks pass.
- 13 automated tests pass with 97% statement coverage on the implemented application,
  including an integration test against the actual Alembic-created schema.
- Alembic upgrade and downgrade were exercised against SQLite.
- PostgreSQL migration SQL was generated offline for review.
- OpenAPI generation succeeds with seven paths in the current slice.

Docker Compose and PostgreSQL migration execution have since been verified
locally as part of the Phase 1 release check.

## Known limitations

- Email verification and password reset are implemented with hashed, single-use
  token records; production email sending needs a configured provider.
- The request-rate limiter is in-process only; a shared backend is required for
  multiple application instances.
- MFA/WebAuthn and compromised-password checks are not implemented yet.
- Access tokens are not denylisted on logout; their maximum remaining life is 15 minutes.
- Administrator assignment needs a trusted bootstrap/runbook before admin CRUD is built.
- The test client currently emits one upstream Starlette deprecation warning about its HTTP
  test transport; it does not affect the passing tests and should be revisited on dependency update.

## Next slice

Implement a source-first catalog slice: `Provider`, `Opportunity`, `Source`, and
append-only `VerificationRecord`; admin-only draft CRUD; and a publication rule
that refuses to expose an opportunity without a current officially verified
source. This is the foundation for profiles, search, and matching.
