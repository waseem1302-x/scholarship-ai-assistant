# Current product state

This document is the canonical capability inventory for the current release. Historical phase
plans, blueprints, audits, and remediation notes are useful decision records but are not claims
about the currently deployed product.

## Product truth boundary

The platform is a **source-backed scholarship assistant**. Official sources, reviewed structured
catalogue facts, and deterministic backend rules are authoritative in that order. Matching scores
rank stated criteria alignment; they are not selection probabilities. Funding labels describe
tracked evidence and are not guarantees. The default Assistant provider is a citation-first,
deterministic evidence-template provider. Generative inference is not implied unless the server
capability response explicitly reports a reviewed configured provider.

## Implemented and supported

- versioned FastAPI API, PostgreSQL/Alembic, Redis-backed production rate limiting, and a React web
  client;
- short-lived access tokens, rotating refresh cookies, email lifecycle, administrator step-up and
  passkeys;
- source-reviewed catalogue, historical application cycles, freshness states, structured criteria,
  explainable matching, and conservative evidence labels;
- Applications as the canonical student planning state, including tasks, reminders, document
  metadata, events, export, deletion, ownership controls, and optimistic concurrency;
- citation-first Assistant, private Document Lab foundation, Community, operational health,
  append-only audit integrity, tenant RLS, and fleet telemetry behind server capability gates;
- Azure Container Apps infrastructure definitions with managed identities, Key Vault, private data
  services, bounded scale, budgets, alerts, and staged-release workflow definitions.

## Capability tiers

- `decision_ready`: structured eligibility dependencies are covered by reviewed rules.
- `informational_only`: an official source is verified, but criteria still require manual checking.
- High-risk Assistant, Document Lab, Community, registration, and beta capabilities are disabled by
  default and can be paused server-side without a client release.
- Document Lab reports feature, scanner, worker, provider, and upload readiness separately. A
  production deployment must not equate a feature flag with an operational worker fleet.

## Deprecated compatibility surface

`/saved-opportunities` and `/tracker` are legacy compatibility surfaces. The web client uses
Applications only. Legacy API responses carry `Deprecation`, `Sunset`, and successor links. See
[legacy-tracker-deprecation.md](legacy-tracker-deprecation.md) before any contract migration.

## Not yet evidenced by repository code

- GitHub Environment approval rules and branch protection are repository/account settings.
- An Azure workflow definition is not proof of a successful staging deployment, rollback, PITR,
  soak test, or cost outcome.
- Draft catalogue records without structured official-source curation are not decision-ready.
- Android and iOS clients are target clients of the API, not implemented clients in this repository.

## Release evidence

A release is eligible for staging only when the exact commit passes CI Test, Browser E2E, Security
Scan, clean PostgreSQL migration, frontend test/build, Ruff checks, backend coverage, and relevant
PostgreSQL/Redis security and concurrency suites. Environment execution evidence is recorded
separately from code-level readiness.
