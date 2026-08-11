# Phase 3: premium frontend foundation

## Goal

Replace the single imperative browser script incrementally with a typed,
component-based frontend that can support the later matching, assistant,
document, and community phases without changing the FastAPI product API.

## Milestone 1 delivered

- a React, TypeScript, and Vite project under `frontend/`
- an isolated production preview at `/app`; the existing `/` product remains
  available until its replacement has passed every milestone
- a production build that FastAPI serves at `/app`, including client-side route
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
- The existing static MVP is not deleted during the migration. `/` remains the
  fallback product until the replacement passes the final Phase 3 gates.

## Local development

In one terminal, start the FastAPI API as usual. In another terminal:

```bash
pnpm --dir frontend install
pnpm --dir frontend dev
```

Open `http://localhost:5173/app/` for the Vite development experience. The
development server proxies API calls to FastAPI on port 8000.

To verify FastAPI's production serving path locally:

```bash
pnpm --dir frontend build
python -m uvicorn app.main:app --reload
```

Open `http://localhost:8000/app`.

## Remaining Phase 3 milestones

1. Rebuild verified search, filtering, pagination, and official-evidence
   opportunity detail pages.
2. Rebuild the profile, explainable matching, and saved-application tracker.
3. Rebuild the admin review queue, data-quality dashboard, imports, and
   reviewer actions.
4. Complete responsive, accessibility, performance, empty/error state, and
   browser-regression work. Retire the legacy static UI only after full
   verification and explicit approval.

## Verification

```bash
pnpm --dir frontend test
pnpm --dir frontend build
pytest tests/test_frontend.py tests/test_phase1_security.py
pytest -m e2e
ruff check .
ruff format --check .
```
