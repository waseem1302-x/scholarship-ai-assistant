# Terra 5.6 Phase 4 — Families, Routes, Cycles, and Deduplication

Date: 2026-08-25  
Branch: `codex/phase1b2-crawlee-secure-bridge`  
Prior-phase evidence: `docs/terra-5.6-phase-3-provenance-safe-extraction-2026-08-25.md`

## Outcome

Phase 4 is complete. New catalogue records now receive versioned deterministic family,
timeless-route, and cycle-scoped identity keys. Duplicate review exposes both records,
the signals that matched, and their structured conflicts. All decisions remain human
controlled.

## Identity contract

- Policy version: `catalogue-identity.v1`.
- Family identity uses the provider canonical ID and explicit programme family.
- Timeless route identity additionally uses the route/course, host institution when
  applicable, destination country, and degree level.
- Cycle identity additionally includes the cycle key.
- Unicode, case, whitespace, punctuation, and generic award suffixes are normalized.
  Fuzzy similarity never becomes an identity key and cannot merge records.
- Explicit stable family and route/course IDs allow translated display names and aliases
  to resolve consistently without conflating distinct awards.

The database persists the policy version and all three keys. The cycle-scoped key has a
partial unique index, while nullable legacy rows remain compatible with the additive
migration. Family grouping now prefers the persisted family key and retains the legacy
name-based fallback for pre-migration records.

## Routes and cycles

CSC university routes remain distinct when their host institutions differ. DAAD EPOS
courses and Erasmus joint masters remain distinct when their route/course IDs differ.
Different cycles share the same family and timeless-route keys but receive different
cycle-scoped keys. Existing `opportunity_cycles` history remains append-only; a new
cycle does not rewrite the family or route identity.

JSON import deduplication now uses the complete scoped identity, so two legitimate
routes in the same provider/family/cycle are not discarded as duplicate rows.

## Duplicate ordering and review

Candidate ingestion continues to use canonical source identity before structured
identity. Persisted opportunity creation rejects an exact cycle-scoped structured
identity. Potential matches are then ranked for human review, with canonical URL and
content-hash matches scored ahead of name similarity.

The existing admin duplicate endpoint now returns:

- both record snapshots;
- official source URLs and persisted identity keys;
- ordered matching signals; and
- conflicting provider, family, route/course, host, country, degree, and cycle fields.

The private admin workspace renders those pairs side-by-side and retains password
step-up for both “confirm duplicate” and “keep separate” decisions.

## Migration

- Revision: `20260825_0056`.
- Adds nullable `programme_route_id`, family/route/cycle identity keys, and identity
  policy version to `opportunities`.
- Adds a partial unique index for non-null cycle-scoped identity keys and lookup indexes
  for family, route, and programme-route values.
- Release policy now points to `20260825_0056`.

## Verification

- Identity, opportunity, and migration regressions — 68 passed.
- Full backend `pytest -m "not e2e"` — 785 selected: 762 passed, 23 skipped, 10
  deselected; no failures.
- Full Ruff check — passed.
- `git diff --check` — passed (Git emitted only LF/CRLF conversion notices).
- Alembic head — `20260825_0056`.
- Frontend Vitest — 9 files, 35 tests passed.
- Frontend TypeScript/Vite production build — passed with one pre-existing mixed
  static/dynamic import warning.

## Cost and safety

- Azure/OpenAI/model calls: 0.
- Estimated and observed model cost: USD 0.
- Live network acquisition: none.
- Deployment, merge, push, production flags, and non-test publication: none.
- The pre-existing dirty worktree was preserved.

## Exit gate

Passed. Exact retries are rejected without adding a second canonical record, while
fixture identities for distinct CSC university routes, DAAD EPOS courses, and Erasmus
joint masters remain distinct. Phase 5 has not started.
