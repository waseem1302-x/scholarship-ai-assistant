# Phase 3: premium frontend foundation

## Goal

Replace the single imperative browser script with a typed, component-based
frontend that can support the later matching, assistant, document, and
community phases without changing the FastAPI product API.

## Milestone 1 delivered

- a React, TypeScript, and Vite project under `frontend/`
- a production build that FastAPI serves at `/`, including client-side route
  fallback and hashed static assets
- a local Vite development server that proxies `/api` to FastAPI
- a small visual system with reusable button, layout, form, card, typography,
  responsive, focus, and reduced-motion styles
- browser routing for the landing page, secure authentication, workspace home,
  and deliberate placeholders for the next product slices
- a typed API client that keeps access tokens in memory, uses same-origin
  cookies, sends the CSRF header on state-changing requests, and coalesces
  concurrent refresh attempts
- login, registration, refresh-session restoration, and logout using the
  current FastAPI authentication contract
- frontend unit coverage for CSRF cookie parsing and a Playwright journey for
  Phase 3 registration and logout
- Docker and GitHub Actions build/test integration for the frontend bundle

## Security and compatibility rules

- The API remains under `/api/v1`; no backend endpoint contracts change.
- Refresh tokens stay in the existing HTTP-only cookie. The client never writes
  an access or refresh token to `localStorage` or `sessionStorage`.
- State-changing requests retain the existing double-submit CSRF header.
- The static MVP was retained during migration, then retired after the final
  Phase 3 gates passed. `/app/*` redirects to the equivalent canonical React
  route for compatibility.

## Local development

In one terminal, start the FastAPI API as usual. In another terminal:

```bash
pnpm --dir frontend install
pnpm --dir frontend dev
```

Open `http://localhost:5173/` for the Vite development experience. The
development server proxies API calls to FastAPI on port 8000.

To verify FastAPI's production serving path locally:

```bash
pnpm --dir frontend build
python -m uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

## Milestone 2 delivered

- public catalogue at `/catalogue`, supplied only by the existing public
  opportunities API
- safe `open_now=true` search semantics, so unknown, future, closed, and stale
  application windows do not appear as current openings
- structured country, degree, funding, field, and nationality filters that are
  represented in the browser URL and survive refresh/back-forward navigation
- pagination that retains the selected filters
- accessible loading, empty, error, retry, and pagination states
- dedicated opportunity detail pages at `/catalogue/{id}` with funding,
  eligibility, application requirements, warnings, curator notes, and explicit
  decision-support language
- official-source evidence card with the stored excerpt, verification date, and
  safe external source link
- frontend unit tests for the safe query contract and a Playwright route-mocked
  catalogue-to-detail browser journey, while existing backend tests continue to
  verify public visibility and source-gating behavior

## Milestone 3 delivered

- authenticated student pages for profile editing, explainable matches, and
  the saved-application tracker
- a structured profile editor covering study goals, academic record, language
  and GRE test state, work/research/leadership context, financial need, and
  constraints accepted by the existing profile API
- profile completeness and missing-recommended-field guidance without guessing
  omitted information
- client-side score handling that omits language and GRE scores unless the
  student explicitly marks the corresponding test as taken
- explainable match cards that separate confirmed alignment, missing evidence,
  uncertainty, next steps, warnings, and hard eligibility failures; scores are
  explicitly presented as decision support, not outcome predictions
- student-only tracker pages for status, private notes, personal deadlines,
  removal, and an empty state that leads back to verified opportunities
- a student-only `Save to tracker` action on opportunity detail pages; public
  and administrator sessions do not receive this control
- frontend unit tests for profile payload safety and a route-mocked Playwright
  journey through profile save, match inspection, and tracker update

## Milestone 4 delivered

- an administrator-only workspace at `/admin` that loads the existing
  review queue and data-quality dashboard contracts
- evidence-rich review cards with issue severity, source excerpts, safe source
  links, explicit reviewer notes, and all supported review actions
- a password-confirmed administrator step-up flow for state-changing review and
  import operations; the short-lived step-up token is used only for that one
  mutation and is never persisted in browser storage
- JSON-row and CSV-text imports with dry-run support and per-row result feedback
- read-only admin dashboard endpoints use ordinary administrator RBAC, avoiding
  consumption of a one-time step-up token merely to load the workspace; mutating
  endpoints retain step-up protection
- focused tests for import parsing and reviewer-note requirements, alongside the
  existing backend review/data-quality coverage

## Milestone 5 delivered

- strict TypeScript unused-local and unused-parameter checks now complement the
  existing compiler, Ruff, and test gates; the obsolete frontend placeholder
  path was removed
- consistent visible keyboard focus and typography inheritance for buttons,
  inputs, selects, and textareas
- an intermediate responsive layout for the workspace cards before the mobile
  breakpoint, with mobile overflow and keyboard-focus verification
- production bundle serving is tested through FastAPI, and the browser suite
  now includes the administrator review workspace as well as the existing
  catalogue and student journeys
- live local verification covered the release build, loading and empty states,
  registration, profile saving, and browser-console errors

## Phase 3 closeout

React now serves the canonical product at `/`; the former static MVP and its
duplicate assets have been removed. Legacy `/app/*` URLs redirect to the same
React routes.

The React account lifecycle now exposes email-verification request/confirmation
at `/verify-email` and password-reset request/confirmation at
`/auth/password-reset`. Both rely on the existing single-use backend token
contracts and never persist tokens in browser storage. Development debug tokens
are rendered only when the backend explicitly returns them; production delivery
continues to require a transactional email provider.

## Verification

```bash
pnpm --dir frontend test
pnpm --dir frontend build
pytest tests/test_frontend.py tests/test_phase1_security.py
pytest -m e2e
ruff check .
ruff format --check .
```
