# Terra 5.6 Phase 1 — Publication Readiness and Regression Fixtures

Date: 2026-08-25  
Branch: `codex/phase1b2-crawlee-secure-bridge`  
Prior-phase evidence: `docs/terra-5.6-phase-0-zero-cost-audit-2026-08-25.md`

## Outcome

Phase 1 is complete. A versioned backend publication policy now fails closed across the
review action, public search, public detail, and public family paths. Existing active
rows without current readiness metadata are hidden and appear in the remediation queue.
No record was published outside ephemeral test databases.

## Contract frozen

- Policy version: `publication-readiness.v1`.
- Typed states: `supported`, `not_applicable`, `rolling`, `varies_by_country`,
  `not_yet_announced`, and `unknown`.
- Result fields: readiness boolean, reason-coded blockers and warnings, supported and
  required counts, evaluation time, policy version, validity expiry, and per-dimension
  results.
- Required dimensions: identity/family, provider/country, degree/route, cycle, deadline,
  application route, tuition, stipend, recomputed funding classification,
  nationality/geography, academics, language/tests, documents, official artifacts, and
  conflict/duplicate resolution.
- Evidence acceptance requires an active ownership-resolved official source, a current
  verification, a source hash matching an immutable snapshot, exact excerpt offsets,
  explicit support, and a passed validator.
- Pending duplicate suggestions and contradictory evidence block publication. Dismissed
  route/cycle variants do not.

## Enforcement

- Publish and conflict-resolution transitions lock the opportunity and evaluate policy
  before activation. Failure returns HTTP 409 with `publication_readiness_blocked`.
- Successful publication persists completeness, policy version, evaluation time, and
  the source-freshness expiry in `next_review_at`.
- Review holds, conflicts, rechecks, expiry, archival, and detected source changes clear
  readiness metadata.
- Public SQL requires active/current readiness metadata, a fresh hash-backed official
  snapshot, and no pending duplicate. Public detail and family reads additionally
  re-evaluate the policy.
- The admin review queue includes the full backend result. A dedicated read-only admin
  readiness endpoint is available.
- The legacy seed loader now stages the 50 incomplete seed records as private drafts; it
  no longer attempts to auto-publish them.

## Fixtures and regressions

`tests/fixtures/catalogue_readiness/three_family_gold.v1.json` contains synthetic,
non-authoritative derived text for one CSC route, one DAAD EPOS course, and one Erasmus
Mundus joint master. Each record maps all 15 required dimensions to an exact excerpt.
No raw official page or document text is redistributed.

Regression coverage proves failures for unknown deadline, tuition, and stipend; missing
application URL, nationality, academic requirement, and documents; mismatched excerpts;
conflicting or stale official sources; pending duplicates; direct API bypass attempts;
admin-only unknown placeholders; and incomplete active record leakage. It also proves
that dismissed legitimate route/cycle variants are permitted and successful publication
persists the current policy metadata.

## Verification

- `uv run ruff check .` — passed.
- `git diff --check` — passed (Git emitted only existing LF/CRLF conversion notices).
- New Phase 1 tests — 15 passed.
- Opportunity + matching focused suite — passed.
- Migration, graph-migration, and catalogue-ingestion focused suite — passed.
- `python -m alembic heads` — `20260825_0054 (head)`.
- Full backend `pytest -m "not e2e"` — 770 selected: 747 passed, 23 skipped, 10
  deselected; no failures. One Windows file-lock race in an unrelated document-worker
  test failed on the first broad run and passed immediately in isolation and on the
  final broad run.
- Frontend Vitest — 9 files, 34 tests passed.
- Frontend TypeScript/Vite production build — passed with one pre-existing mixed
  static/dynamic import warning.
- Full format-check was not applied to pre-existing dirty files because Ruff proposed
  broad CRLF/LF normalization. All new Phase 1 Python files were formatted and checked.

## Cost and safety

- Azure/OpenAI/model calls: 0.
- Estimated and observed model cost: USD 0.
- Live network acquisition: none.
- Deployment, merge, push, production flags, and non-test publication: none.
- The pre-existing dirty worktree was preserved.

## Exit gate

Passed. The contract and synthetic three-family gold mappings are frozen, and the
regressions demonstrate that every intended gap fails closed without paid calls.
Phase 2 has not started.
