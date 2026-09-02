# Dead-Code Cleanup Design

## Objective

Remove only tracked source code that is demonstrably unreachable or unnecessary, preserve all supported runtime and compatibility behavior, and leave `main` with automated checks that prevent equivalent TypeScript dead code from returning.

## Evidence Standard

A deletion is allowed only when at least two independent checks agree that the code is unused. Applicable checks are:

- repository-wide symbol or module search;
- TypeScript compiler unused-symbol analysis;
- Knip file/export analysis;
- Ruff or Vulture analysis;
- Python static import-graph analysis;
- runtime entry-point, workflow, Docker, and documentation searches;
- focused tests and the complete project test suites.

Low coverage alone is not evidence of dead code. Framework callbacks, ORM fields, Pydantic validators, FastAPI route functions, migration history, command-line modules, dynamically imported modules, and feature-gated paths are presumed live unless their wiring is disproved.

## Verified Cleanup Scope

### Remove unused files

- Delete `frontend/src/components/icons.tsx`, which is empty and has no imports.
- Delete `app/modules/catalogue_ingestion/topology_service.py`. It has no static or textual importer, no route, CLI, workflow, test, or documentation reference, and its only class is not instantiated anywhere.

### Remove unused declarations

- Remove the unused `signInWithGoogle` and `signInWithFacebook` destructuring in `AuthForm`; retain the authentication context methods and backend OAuth flow because those are supported interfaces.
- Remove the unused `waitFor` test import.
- Remove the unused catalogue `availabilityLabel` helper.
- Remove the unused legacy saved-opportunity frontend wrappers and the types used only by those wrappers.
- Remove the unused `deleteApplicationTask` frontend wrapper while retaining the backend endpoint.
- Remove the unused `full_name` argument from the internal OAuth registration method and its callers. Provider profile parsing remains unchanged to preserve its current return contract.

### Narrow unnecessary exports

Remove `export` only, without deleting live implementations, for declarations used solely inside their defining module. This includes internal components, helper functions, response types, and derived catalogue types reported by Knip and confirmed by repository-wide search.

### Prevent recurrence

Enable `noUnusedLocals` and `noUnusedParameters` in `frontend/tsconfig.json`. The existing production build will then enforce these checks without adding dependencies or a new CI step.

## Protected Scope

Do not remove:

- Alembic migrations or database models;
- FastAPI route handlers or middleware callbacks;
- CLI modules referenced by Docker Compose, Azure infrastructure, GitHub workflows, or operator documentation;
- deprecated saved-opportunity APIs before their documented February 2027 sunset;
- feature-gated acquisition, extraction, scheduling, or provider code;
- generated frontend build output, local databases, caches, fixtures, or user data;
- code identified only by low test coverage or low-confidence analyzer output.

## Execution Strategy

Apply removals in small groups: trivial TypeScript declarations, unused frontend API surface, internal export narrowing, and the isolated Python module/parameter cleanup. After each group, run the narrowest relevant static check or test. Run the complete frontend tests, production build, Ruff checks, formatting check, and backend test suite after all changes.

Commit the cleanup only after the complete verification set is green. Push the resulting commit directly to `main`, matching the repository state established before this audit.

## Success Criteria

- Every removed item satisfies the evidence standard.
- Knip reports no unused files, exports, or exported types.
- TypeScript passes with unused locals and parameters enabled.
- Ruff and Ruff formatting checks pass.
- All frontend tests pass.
- The production frontend build succeeds.
- All backend tests pass.
- The worktree is clean and local `main` matches `origin/main` after push.
