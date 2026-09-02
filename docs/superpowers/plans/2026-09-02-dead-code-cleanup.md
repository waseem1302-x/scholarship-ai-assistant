# Dead-Code Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove only independently verified dead code and make the existing frontend build reject new unused locals or parameters.

**Architecture:** Keep every runtime route, migration, scheduled command, feature-gated path, and supported API intact. Use compiler/import-graph failures as the red phase, make narrowly scoped removals, and prove the resulting application with static analysis, complete tests, and a production build.

**Tech Stack:** Python 3.12, FastAPI, Ruff 0.16.2, pytest, React 19, TypeScript 5.9, Vite 7, Vitest 4, pnpm 11.

**Spec:** `docs/superpowers/specs/2026-09-02-dead-code-cleanup-design.md`

## Global Constraints

- Remove an item only when at least two independent checks prove it unused.
- Do not delete Alembic migrations, FastAPI handlers, middleware callbacks, scheduled CLI modules, documented compatibility APIs, generated build output, caches, fixtures, or local data.
- Do not use low coverage as deletion evidence.
- Add no runtime or development dependency.
- Keep each deletion group independently testable and committed.

---

### Task 1: Enforce TypeScript unused-symbol checks

**Files:**
- Modify: `frontend/tsconfig.json`
- Modify: `frontend/src/auth/AuthProvider.tsx:160`
- Modify: `frontend/src/features/home/HomePage.test.tsx:2`
- Delete: `frontend/src/components/icons.tsx`

**Interfaces:**
- Consumes: the existing `AuthContextValue` and Vitest setup configured by `frontend/vite.config.ts`.
- Produces: a TypeScript project that rejects unused locals and parameters during the existing `pnpm build` command.

- [ ] **Step 1: Reproduce the unused-symbol failures**

Run:

```powershell
$env:Path = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:Path
pnpm -C frontend exec tsc --noEmit --noUnusedLocals --noUnusedParameters
```

Expected: exit 1 identifying the unused `signInWithGoogle`, `signInWithFacebook`, and `waitFor` declarations.

- [ ] **Step 2: Remove only the reported unused bindings and empty file**

Change the `AuthForm` destructure to:

```tsx
const { signIn } = useAuth();
```

Change the Home page test import to:

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
```

Delete the zero-byte `frontend/src/components/icons.tsx` file.

- [ ] **Step 3: Make the compiler settings permanent**

Add these options under `compilerOptions` in `frontend/tsconfig.json`:

```json
"noUnusedLocals": true,
"noUnusedParameters": true,
```

- [ ] **Step 4: Verify the compiler and targeted frontend tests**

Run:

```powershell
$env:Path = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:Path
pnpm -C frontend exec tsc --noEmit
pnpm -C frontend exec vitest run src/auth/AuthProvider.test.tsx src/features/home/HomePage.test.tsx
```

Expected: both commands exit 0.

- [ ] **Step 5: Commit the compiler-enforced cleanup**

```powershell
git add -- frontend/tsconfig.json frontend/src/auth/AuthProvider.tsx frontend/src/features/home/HomePage.test.tsx frontend/src/components/icons.tsx
git commit -m "chore(frontend): enforce unused code checks"
```

---

### Task 2: Remove dead frontend helpers and narrow internal exports

**Files:**
- Modify: `frontend/src/App.tsx:420`
- Modify: `frontend/src/components/BrandLogo.tsx:3`
- Modify: `frontend/src/api/client.ts:33,84`
- Modify: `frontend/src/features/admin/admin.ts:107,124,139`
- Modify: `frontend/src/features/catalogue/catalogue.ts:57,94-102,197-202`
- Modify: `frontend/src/features/workspace/types.ts:4-16,115-133,163-166`
- Modify: `frontend/src/features/workspace/workspace.ts:2,82-96,131-133`
- Modify: `frontend/src/hooks/useServerQuery.ts:3`

**Interfaces:**
- Consumes: current imports discovered by Knip and repository-wide `rg` searches.
- Produces: the same application behavior with unused wrappers/types deleted and module-private declarations no longer exported.

- [ ] **Step 1: Capture the current Knip failures**

Run:

```powershell
$env:Path = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:Path
Push-Location frontend
pnpm dlx knip@5
Pop-Location
```

Expected: exit 1 listing unused exports and exported types, including `availabilityLabel`, `applicationStatuses`, the saved-opportunity wrappers, and `deleteApplicationTask`.

- [ ] **Step 2: Delete declarations with no callers**

Remove these complete declarations:

```text
frontend/src/features/catalogue/catalogue.ts:
  availabilityLabel

frontend/src/features/workspace/workspace.ts:
  getSaved
  saveOpportunity
  updateSaved
  deleteSaved
  deleteApplicationTask

frontend/src/features/workspace/types.ts:
  ApplicationStatus
  ChecklistItem
  SavedOpportunity
  applicationStatuses
```

Then remove `SavedOpportunity` from the import list in `frontend/src/features/workspace/workspace.ts`.

- [ ] **Step 3: Narrow declarations that are live only inside their module**

Remove only the `export` keyword from these declarations:

```text
frontend/src/App.tsx: Dashboard
frontend/src/components/BrandLogo.tsx: BrandLogoIcon
frontend/src/api/client.ts: AdminMfaStepUp, BetaInvitationDelivery
frontend/src/features/admin/admin.ts: jsonImportRows, AdminWorkspacePage, adminOpportunitySearch
frontend/src/features/catalogue/catalogue.ts: UrgencyTier, DeadlineUrgency, CardBadges
frontend/src/hooks/useServerQuery.ts: ServerQueryState
```

Do not remove `Topbar`, `SearchPill`, `readCsrfToken`, `ApiClient`, `DashboardSections`, `listFromText`, or `profilePayload`; tests import those declarations directly.

- [ ] **Step 4: Verify Knip, compilation, and frontend behavior**

Run:

```powershell
$env:Path = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:Path
Push-Location frontend
pnpm dlx knip@5
Pop-Location
pnpm -C frontend exec tsc --noEmit
pnpm -C frontend test
```

Expected: all commands exit 0 and Vitest reports 60 passing tests.

- [ ] **Step 5: Commit the frontend API-surface cleanup**

```powershell
git add -- frontend/src/App.tsx frontend/src/components/BrandLogo.tsx frontend/src/api/client.ts frontend/src/features/admin/admin.ts frontend/src/features/catalogue/catalogue.ts frontend/src/features/workspace/types.ts frontend/src/features/workspace/workspace.ts frontend/src/hooks/useServerQuery.ts
git commit -m "refactor(frontend): remove verified dead code"
```

---

### Task 3: Remove the unused Python service and OAuth parameter

**Files:**
- Delete: `app/modules/catalogue_ingestion/topology_service.py`
- Modify: `app/modules/auth/oauth_service.py:118-126`
- Modify: `app/modules/auth/routes.py:125-165`
- Modify: `tests/test_oauth_social_login.py:28-36,107-115`

**Interfaces:**
- Consumes: `OAuthService.authenticate_or_register_social_user(provider, provider_user_id, email)`.
- Produces: unchanged OAuth behavior without an ignored `full_name` parameter; removes an unreachable topology write service while retaining all topology models and active services.

- [ ] **Step 1: Reproduce both Python dead-code findings**

Run:

```powershell
uvx vulture app --min-confidence 80
rg -n "CatalogueTopologyService|topology_service" . --hidden --glob '!.git/**' --glob '!node_modules/**' --glob '!.venv/**' --glob '!.pytest*/**' --glob '!app/modules/catalogue_ingestion/topology_service.py'
```

Expected: Vulture reports only the unused `full_name` parameter at confidence 100, and the repository search returns no consumer for `CatalogueTopologyService` or its module.

- [ ] **Step 2: Remove the ignored OAuth parameter**

Change the method signature to:

```python
def authenticate_or_register_social_user(
    self,
    *,
    provider: str,
    provider_user_id: str,
    email: str,
) -> IssuedTokens:
```

Remove the `full_name=profile_data.get("name")` arguments from both OAuth routes and the `full_name=profile_data["name"]` arguments from the Google and Facebook registration tests. Keep provider profile dictionaries unchanged.

- [ ] **Step 3: Delete the unreachable topology service**

Delete `app/modules/catalogue_ingestion/topology_service.py`. Do not alter `topology_models.py`, `topology_recompute.py`, `scoped_completeness.py`, or their imports.

- [ ] **Step 4: Verify Python static checks and OAuth behavior**

Run:

```powershell
uvx vulture app --min-confidence 80
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\ruff.exe format --check app tests
.\.venv\Scripts\python.exe -m pytest tests/test_oauth_social_login.py
```

Expected: Vulture produces no confidence-80-or-higher findings; Ruff commands exit 0; OAuth tests pass.

- [ ] **Step 5: Commit the Python cleanup**

```powershell
git add -- app/modules/catalogue_ingestion/topology_service.py app/modules/auth/oauth_service.py app/modules/auth/routes.py tests/test_oauth_social_login.py
git commit -m "refactor: remove verified unused backend code"
```

---

### Task 4: Verify and publish the cleaned baseline

**Files:**
- Verify: all tracked source and test files
- Update: `origin/main` through a normal fast-forward push

**Interfaces:**
- Consumes: the three independently committed cleanup groups.
- Produces: a clean, tested local and remote `main` ready for subsequent feature work.

- [ ] **Step 1: Run all static checks**

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
$env:Path = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:Path
pnpm -C frontend exec tsc --noEmit
Push-Location frontend
pnpm dlx knip@5
Pop-Location
```

Expected: every command exits 0 with no unused-code findings.

- [ ] **Step 2: Run complete automated tests**

```powershell
.\.venv\Scripts\python.exe -m pytest
pnpm -C frontend test
```

Expected: pytest reports 707 passed and 31 skipped; Vitest reports 60 passed.

- [ ] **Step 3: Build the production frontend**

```powershell
pnpm -C frontend build
```

Expected: TypeScript and Vite exit 0 and produce `app/web/frontend-dist`.

- [ ] **Step 4: Verify repository state and push**

```powershell
git diff --check
git status --short --branch
git log --oneline origin/main..main
git push origin main
git fetch origin --prune
git status --short --branch
```

Expected: the pre-push worktree is clean and only planned commits are ahead; the push succeeds; the final status shows `main...origin/main` with no divergence or working-tree changes.
