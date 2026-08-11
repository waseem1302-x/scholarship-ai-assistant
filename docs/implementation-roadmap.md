# Implementation roadmap

## Audit summary (2026-08-11)

The application is a FastAPI modular monolith with SQLAlchemy models, Alembic
migrations, a PostgreSQL-compatible schema, and a static browser client. Its
route -> service -> repository boundaries are appropriate and will be retained.
The immediate risks are correctness (application-window and free-text matching)
and production browser/authentication security, not a need for a rewrite.

## Phases

1. **Phase 0 — repository audit and plan** — complete.
2. **Phase 1 — correctness and security repairs** — complete, pending product
   approval to begin Phase 2.
   - application-cycle and effective-window semantics, including `open_now`;
   - structured eligibility rules and hard eligibility gates;
   - explainable fit/readiness response with versioning;
   - production configuration validation, security headers, rate limits, and
     cookie-based refresh-session migration path;
   - frontend error/XSS hardening and regression tests;
   - PostgreSQL CI migration coverage.
   - hashed, single-use email-verification and password-reset records;
   - administrator password re-authentication, production email-verification
     enforcement, single-use step-up tokens, and audit events;
   - lifecycle reconciliation CLI and baseline automated accessibility checks.
3. **Phase 2 — opportunity data platform** — in progress.
   - immutable source-excerpt snapshots;
   - admin source-check records with content-hash change detection;
   - changed sources automatically return to `needs_review` and lose public
     visibility until reverified;
   - scheduled source-monitor runner with HTTPS-only fetching and private-network
     blocking;
   - reviewer actions for publish, hold, conflict, recheck, resolve conflict,
     expire, and archive;
   - CSV import parsing into the same review-safe row contract as JSON imports;
   - admin review queue and data-quality issue dashboard APIs;
   - static admin review/data-quality panels.
4. **Phase 3 — premium frontend foundation** — in progress.
   - Milestone 1: React, TypeScript, Vite build path, design tokens, client
     routing, and cookie-session-aware authentication shell;
   - Milestone 2: verified catalogue and opportunity-detail journey;
   - Milestone 3: profile, matches, and application tracker;
   - Milestone 4: administrator review and data-quality workspace;
   - Milestone 5: accessibility, performance, browser regression, and release
     verification before the legacy UI is retired.
5. **Phase 4 — matching and readiness intelligence** — pending.
6. **Phase 5 — application command centre** — pending.
7. **Phase 6 — citation-first AI assistant** — pending.
8. **Phase 7 — AI document lab** — pending.
9. **Phase 8 — scholarship-only community** — pending.
10. **Phase 9 — production hardening and beta launch** — pending.

## Phase 1 acceptance gates

- An expired, future, unknown-deadline, rolling, or stale record cannot be
  returned by `open_now=true` as open.
- Structured hard-rule failures result in `ineligible`/`likely_ineligible` and
  never a strong fit label.
- Missing information stays unknown; free text is display evidence, not a
  high-impact eligibility decision when a structured rule exists.
- The static client does not inject server strings as trusted HTML or persist
  a production refresh token in `localStorage`.
- Production refuses known development JWT secrets, state-changing cookie
  requests have CSRF protection, and authentication endpoints are rate-limited.
- Tests, Playwright browser journeys, Ruff, Alembic upgrade rehearsal, and the
  local Docker/PostgreSQL readiness check pass.

## Phase 2 acceptance gates

- Changed source content hashes cannot remain silently public as officially
  verified.
- Source-check events create an auditable verification record and safe audit-log
  entry.
- Evidence excerpts are captured as separate snapshots rather than overwriting
  mutable source status.
- Administrators can query review work and data-quality issues with stable
  severity/code fields.
- The browser admin workspace surfaces review and data-quality work without
  trusting server strings as HTML.

## Compatibility decisions

- Existing `opportunities` fields remain as the legacy/current cycle projection
  so existing API clients and imported data keep working. New `opportunity_cycles`
  preserve historical and recurring cycles.
- The public catalogue remains able to show verified historical records when
  explicitly requested. The new `open_now` filter is the authoritative
  "currently open" view and defaults to the safer view in the browser client.
- Existing response fields are retained where feasible while new explicit
  eligibility and window-state fields are added.
