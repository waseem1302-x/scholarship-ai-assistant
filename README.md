# Scholarship AI Assistant

**Global Opportunity Intelligence Platform**

A source-first platform that helps students discover, understand, and track
scholarships using structured eligibility data, explainable matching, and
answers grounded in official sources.

> This platform provides decision support. It does not guarantee admission,
> scholarship selection, or visa approval.

## Product story

As a Pakistani scholarship-funded Computer Science student in Malaysia, I am
building an AI system that helps other students make better international
education decisions. The project connects lived scholarship experience with
backend engineering, responsible AI, and education access.

## Current status

The repository has completed **Phase 1: correctness and security repairs**.
Phase 2 has started with the opportunity data-platform trust layer. Phase 3
frontend foundation work is now underway on an isolated preview route.
The product, architecture, database, API, matching, RAG, evaluation, security,
and delivery plans are in [docs/blueprint.md](docs/blueprint.md).

Implemented so far:

- FastAPI application with versioned routes and centralized configuration
- PostgreSQL-ready SQLAlchemy models and Alembic migration
- registration, login, authenticated `me`, refresh-token rotation, and logout
- Argon2 password hashing and short-lived JWT access tokens
- opaque, hashed, single-use refresh tokens with reuse detection
- generic authentication errors and role-aware authorization dependency
- source-first opportunity catalog models for providers, universities,
  opportunities, sources, and verification records
- admin-only opportunity creation and verification workflow
- public opportunity search that only returns active records with officially
  verified official sources
- structured funding fields and validation against unsupported "full funding"
  claims
- authenticated student profile create/read/update with incomplete-profile
  support
- profile completeness metadata and validation for grades, language tests, GRE,
  experience, target countries, and intake preferences
- deterministic matching endpoint that ranks verified opportunities against the
  student's profile with satisfied, missing, and uncertain explanations
- saved-opportunity tracker for student notes, application status, document
  checklists, recommendation letters, test requirements, deadlines, submission
  dates, and outcomes
- admin JSON batch import for opportunities with row-level validation,
  duplicate detection, data-quality warnings, dry-run support, and forced human
  review before public visibility
- CSV batch import parsing that maps spreadsheet columns into the same
  review-safe import contract and reports row-level warnings
- curated verified seed dataset with real opportunities from official sources
  and a CLI loader for local demos
- expanded database-backed public and admin opportunity filters for field,
  nationality, intake year, deadline windows, funding coverage, application-fee
  text, English requirements, verification freshness, and admin review queues
- paginated public and admin opportunity search responses with total counts,
  result counts, offsets, and next/previous page indicators
- local FastAPI-served frontend for login/register, opportunity search,
  official-source detail, student profile editing, explainable matches,
  saved-opportunity tracking, and basic admin curation
- polished opportunity cards and detail pages that emphasize funding components,
  deadlines, eligibility warnings, official evidence, and last verification
- frontend regression tests for the static product shell, required flows,
  encoding artifacts, and duplicate JavaScript function definitions
- Playwright/Chromium end-to-end tests for registration, catalogue loading,
  logout, and keyboard form navigation
- expanded verified seed dataset with 16 official-source records across major
  destination systems such as Chevening, Commonwealth, Fulbright, DAAD, Eiffel,
  Swiss Excellence, Erasmus Mundus, CSC, MEXT, GKS, Turkiye Scholarships,
  Australia Awards, RTP, Manaaki, and ADB-JSP
- Docker Compose, lint configuration, and automated tests
- effective application-window states with a safe `open_now` catalogue filter
- historical opportunity cycles and structured eligibility-rule foundation
- hard eligibility gates that suppress fit scores for failed requirements
- production secret validation, security headers, auth abuse limiting, and
  cookie-based browser refresh sessions
- immutable source-excerpt snapshots for official evidence captured during
  curation
- admin source-check workflow that records content-hash changes, creates audit
  history, and returns changed sources to `needs_review`
- scheduled source-monitor runner with HTTPS-only fetching, private-network
  blocking, timeouts, byte limits, and dry-run support
- admin reviewer actions for publishing, holding, flagging conflicts,
  requesting rechecks, resolving conflicts, expiring, and archiving records
- admin review queue and data-quality issue APIs plus frontend panels for
  curation work
- React, TypeScript, and Vite Phase 3 foundation at `/app`, with a typed
  same-origin API client, cookie-session-aware authentication shell, and a
  verified catalogue, official-evidence detail journey, student profile,
  explainable matches, and application tracker; the original static MVP remains
  at `/` during the staged migration

## Quick start

### Local development

1. Install Python 3.12+ and PostgreSQL 16, or use Docker.
2. Copy `.env.example` to `.env` and replace every development secret.
3. Create a virtual environment and install the project:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   python -m pip install -e ".[dev]"
   ```

4. Apply migrations and start the API:

   ```bash
   python -m alembic upgrade head
   python -m uvicorn app.main:app --reload
   ```

5. Open `http://localhost:8000`.

The product frontend is served at `http://localhost:8000`. The API
documentation remains available at `http://localhost:8000/docs`.

### Docker

```bash
docker compose up --build
```

The API is available at `http://localhost:8000`; PostgreSQL is not exposed
outside the Compose network.

## Frontend walkthrough

The first frontend is intentionally lightweight and served by FastAPI from
`app/web/static`. It avoids adding a separate JavaScript build system before the
backend and data model stabilize.

From `http://localhost:8000`, users can:

- register or login as a student
- search verified public opportunities with structured filters and pagination
- open opportunity details with official-source excerpts and verification dates
- create or update a student profile
- refresh explainable profile matches
- save opportunities and update tracker status/notes

Administrators can login with an admin account created through the trusted CLI
and use the admin section to:

- list admin opportunities
- create a draft opportunity with official-source provenance
- mark a source as officially verified, which makes the opportunity active

For a useful local demo, create an admin account and load the verified seed
dataset:

```bash
docker compose exec api python -m app.cli.create_admin
docker compose exec api python -m app.cli.seed_verified_opportunities
```

## Quality checks

```bash
ruff check .
ruff format --check .
pytest
```

## Authentication walkthrough

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me              Authorization: Bearer <access token>
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
POST /api/v1/auth/email-verifications       Authorization: Bearer <access token>
POST /api/v1/auth/email-verifications/confirm
POST /api/v1/auth/password-resets
POST /api/v1/auth/password-resets/confirm
POST /api/v1/auth/admin/step-up             Authorization: Bearer <access token>
```

Verification and reset tokens are hashed, single-use, and expiring. In local
development/test the API returns a debug token so the flow can be tested. In
production it intentionally returns no token until a transactional email sender
is configured. Production administrator changes additionally require a
password re-authentication token supplied in `X-Admin-Step-Up`.

Registration creates students only. Administrator roles must be assigned by a
trusted operational process; public clients cannot self-promote.

For local development, create or promote an administrator inside the running
Docker API container:

```bash
docker compose exec api python -m app.cli.create_admin
```

The command prompts for an admin email and password without adding public admin
registration to the API.

## Opportunity catalog walkthrough

```text
POST  /api/v1/admin/opportunities                       admin only
GET   /api/v1/admin/opportunities                       admin only
POST  /api/v1/admin/opportunities/import                admin only, JSON or CSV text
PATCH /api/v1/admin/opportunities/{id}/verification     admin only
POST  /api/v1/admin/opportunities/{id}/review-actions   admin only
GET   /api/v1/admin/review-queue                        admin only
GET   /api/v1/admin/data-quality-issues                 admin only
POST  /api/v1/admin/sources/{id}/checks                 admin only
GET   /api/v1/opportunities                             public verified search
GET   /api/v1/opportunities/{id}                        public verified detail
```

Draft and unverified opportunities are hidden from public search. A public
opportunity must have an official source marked `officially_verified`.

Imported opportunities are always created as drafts with sources marked
`needs_review`, even when the import file claims they are active or verified.
This applies to JSON rows and CSV text imports, keeping imported data out of
public search until a human curator verifies the official source.

When a source-check records a changed content hash, the source is returned to
`needs_review`. Public search then hides the record until a curator verifies the
official source again.

Run due source monitoring locally with:

```bash
python -m app.cli.monitor_sources
```

Useful environment controls:

```bash
APP_SOURCE_MONITOR_DRY_RUN=true
APP_SOURCE_MONITOR_LIMIT=20
APP_SOURCE_MONITOR_INTERVAL_DAYS=7
```

Public search supports structured filters such as `country`, `degree_level`,
`funding_type`, `field`, `nationality`, `intake_year`, `deadline_after`,
`deadline_before`, `funding_coverage`, `application_fee`, `english_requirement`,
and `verified_after`. Admin search also supports `status`,
`verification_status`, `needs_review`, `provider_query`, and `search_query`.

Use `open_now=true` for the authoritative currently-open view. It excludes
future, closed, archived, unknown-deadline, and stale-source records; historical
records remain discoverable when a user intentionally searches without it.

Opportunity list responses use this envelope:

```json
{
  "items": [],
  "pagination": {
    "total": 0,
    "limit": 20,
    "offset": 0,
    "count": 0,
    "has_next": false,
    "has_previous": false
  }
}
```

## Student profile walkthrough

```text
GET /api/v1/profiles/me       Authorization: Bearer <access token>
PUT /api/v1/profiles/me       Authorization: Bearer <access token>
```

Profiles intentionally allow missing fields. Missing information is returned as
profile completeness metadata instead of being interpreted as eligibility.

## Matching walkthrough

```text
GET /api/v1/matches/me        Authorization: Bearer <access token>
```

The match score ranks profile fit against stated requirements. It is not a
probability of admission, scholarship selection, or visa approval.

## Saved opportunity tracker walkthrough

```text
POST   /api/v1/saved-opportunities          student only
GET    /api/v1/saved-opportunities          student only
GET    /api/v1/saved-opportunities/{id}     student only
PATCH  /api/v1/saved-opportunities/{id}     student only
DELETE /api/v1/saved-opportunities/{id}     student only
```

Students can only save active opportunities with officially verified official
sources. Saved trackers are isolated by user, so one student cannot read or
modify another student's applications.

## Verified seed dataset walkthrough

The repository includes a manually curated source-verified demo dataset:

```text
data/seed/verified_opportunities.json
```

Load it only after creating an admin account:

```bash
docker compose exec api python -m app.cli.seed_verified_opportunities
```

The loader skips duplicates, records source verification metadata, and makes the
seed records public only because the dataset was manually checked against
official source pages. Use this for local portfolio demos, not as a promise that
deadlines or eligibility will remain unchanged forever. The dataset is a
verified flagship sample, not a claim to include every scholarship worldwide.

## Important limitations

- CSV text is parsed directly through the admin import endpoint. Multipart file
  upload UI and custom column mapping are not implemented yet.
- Source checks can be recorded through the admin API or monitor runner, but
  production scheduling still depends on the eventual hosting environment.
- Seed opportunities were verified on 2026-07-22 and need re-verification before
  any public production use.
- Matching currently uses explicit baseline rules and simple parsing for some
  free-text requirements. Structured eligibility rules come next.
- Saved opportunities do not send reminders yet. Notification logic belongs in
  a later slice.
- Email ownership verification and password reset are implemented. A
  transactional email provider still must be configured before public release.
- Access tokens remain valid for their short lifetime after logout. Logout
  revokes the refresh-token family; a future high-security mode can add a token
  version check on every request.
- Seed records are manually curated; they are not an automatically refreshed
  scholarship database and do not represent every opportunity in every country.
- The frontend is an MVP product surface, not the final visual system. It uses
  an in-memory access token and a cookie-backed refresh session. Email
  verification and password reset are implemented, but a transactional email
  provider, MFA/WebAuthn, and a distributed rate-limit store are still required
  before public production use.
- Deployment, public users, and evaluation metrics have not been claimed.

## Documentation

- [Implementation blueprint](docs/blueprint.md)
- [Authentication slice handoff](docs/slices/01-authentication.md)
- [Opportunity catalog slice handoff](docs/slices/02-source-first-opportunity-catalog.md)
- [Student profile slice handoff](docs/slices/03-student-profiles.md)
- [Rule-based matching slice handoff](docs/slices/04-rule-based-matching.md)
- [Saved opportunity tracker slice handoff](docs/slices/05-saved-opportunities.md)
- [Structured ingestion slice handoff](docs/slices/06-structured-ingestion.md)
- [Verified seed dataset slice handoff](docs/slices/07-verified-seed-dataset.md)
- [Expanded structured search slice handoff](docs/slices/08-expanded-search.md)
- [Paginated search responses slice handoff](docs/slices/09-paginated-search.md)
- [Frontend MVP slice handoff](docs/slices/10-frontend-mvp.md)
- [Phase 1 correctness/security increment](docs/slices/11-phase1-correctness-security.md)
- [Phase 2 opportunity data platform increment](docs/slices/12-phase2-opportunity-data-platform.md)
- [Phase 3 frontend foundation increment](docs/slices/13-phase3-frontend-foundation.md)
- [Phased implementation roadmap](docs/implementation-roadmap.md)
- [Architecture decisions](docs/decisions/0001-modular-monolith.md)
- [Environment template](.env.example)
