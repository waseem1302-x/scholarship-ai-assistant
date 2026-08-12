# Slice 10: Local frontend MVP

## Goal

Give the backend a usable product surface so the project can be tested like a
real early-stage application instead of only through Swagger or curl.

This historical slice deliberately kept the frontend lightweight. It was served
directly by FastAPI from static files so the project had one local runtime and
one Docker entry point. The static client was retired in the Phase 3 closeout;
see `docs/slices/13-phase3-frontend-foundation.md` for the current frontend.

## What changed

- Added a local frontend at `/`.
- Kept API documentation available at `/docs`.
- Added static assets under `app/web/static` (retired in Phase 3).
- Mounted `/static` through FastAPI (retired in Phase 3).
- Updated tests so the root route is now the product UI.
- Polished opportunity cards and detail pages to highlight funding fields,
  eligibility warnings, official-source evidence, and last verification dates.
- Added responsive layout hardening for embedded browser and narrow laptop
  widths.
- Added frontend regression tests for required page sections, static assets,
  duplicate HTML IDs, encoding artifacts, and duplicate JavaScript function
  definitions.
- Updated README instructions and limitations.

## User-facing features

Students can:

- register
- login
- logout
- search public verified opportunities
- use structured opportunity filters
- page through results with `limit` and `offset`
- open opportunity details
- view funding fields, requirements, official-source excerpt, source URL, and
  last verification date
- create and update their profile
- refresh explainable matches
- save opportunities
- update saved-opportunity application status and personal notes
- remove saved opportunities

Administrators can:

- login with an admin account created through the trusted CLI
- list admin opportunities
- create a draft opportunity with official-source provenance
- mark an opportunity source as officially verified

## Historical decision

Use a dependency-light static frontend instead of introducing React/Vite yet.

## Reason

The portfolio proof currently needs reliability and end-to-end product testing
more than a complex frontend stack. A static frontend:

- keeps Docker and local setup simple
- avoids adding Node tooling before the API contract stabilizes
- makes the product immediately testable in the browser
- keeps the project focused on backend, data provenance, matching, and AI
  engineering foundations

## Alternative considered

React or another SPA framework.

## Tradeoff

The static frontend is easier to understand and maintain right now, but it will
be less scalable for complex UI state later. If the product grows into richer
dashboards, comparison views, assistant chat, and notification settings, a
dedicated frontend framework can be introduced with a stable API already in
place.

## Portfolio evidence

This slice demonstrates:

- practical full-stack integration
- API-driven UI design
- progressive enhancement without overengineering
- authenticated browser flows
- source-first opportunity detail pages
- pagination-aware product UI
- explicit product disclaimer and uncertainty language

## Acceptance criteria

- Visiting `/` returns the frontend.
- Visiting `/docs` still returns FastAPI documentation.
- A student can register or login from the browser.
- A student can search opportunities and open official-source details.
- A student can save and track opportunities.
- A student can create or update their profile.
- A student can refresh explainable matches.
- An administrator can create a draft and mark it verified.
- Tests cover frontend serving.
- Tests cover core frontend structure and asset regressions.
- Existing backend tests still pass.

## Historical limitations

- The static client's local demo-token approach and missing production-grade
  CSRF/session-cookie strategy were resolved before its retirement.
- The UI does not include the future AI assistant chat interface yet.
- Admin creation is intentionally minimal; CSV/JSON import remains better
  tested through the API for now.
- There is no Playwright-style browser end-to-end test yet; current frontend
  tests are static structural regressions plus backend integration tests.
- Visual design is polished enough for a demo but not a final design system.

## Recommended next slice

Slice 11 should add the first grounded assistant baseline:

1. deterministic question intent routing,
2. retrieval from structured opportunity records and source excerpts,
3. citation-bearing responses,
4. abstention when evidence is insufficient,
5. tests for citation and refusal behavior.
