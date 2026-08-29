# Terra 5.6 Phase 5 — Admin Review Experience

Date: 2026-08-25  
Branch: `codex/phase1b2-crawlee-secure-bridge`

## Outcome

Phase 5 is complete. The private admin workflow now presents a backend-owned readiness
verdict, exact evidence for every resolved field, acquisition and extraction lineage,
duplicate/conflict signals, and audit history without requiring database inspection.
No record is published automatically.

## Backend review projection

The candidate review projection is now the single read-only source for:

- objective coverage and an explicit complete/blocked readiness verdict;
- supported mandatory-objective counts, blocker codes, warnings, and source freshness;
- proposed values with route, cycle, institution, programme, country, and family scope;
- source title, official URL, last checked time, immutable excerpt offsets, and block IDs;
- objective/schema/prompt/provider/model extraction lineage;
- acquisition-bundle coverage and gaps;
- complete artifact and deterministic source-routing metadata;
- all extraction attempts and error states;
- conflict, rejected-claim, and duplicate-opportunity identifiers; and
- review-decision and tamper-evident audit history.

The projection remains plain-text only and does not execute a review transition. Source
freshness uses the existing 90-day catalogue policy. Missing extraction, incomplete
mandatory objectives, conflicts, rejected claims, unresolved duplicates, stale or
unknown source freshness, failed acquisition, and non-reviewable candidate states are
fail-closed blockers.

Admin opportunity-list responses also include a current publication-readiness result.
This lets catalogue filters and detail pages use the same backend policy that enforces
the publication mutation.

## Review experience

The materialized opportunity review continues to reuse `ScholarshipDetailView`, including
family route switching and the public scholarship information hierarchy. Its sticky
decision dock now enables Publish only when `publication_readiness.ready` is true. The
backend still re-evaluates readiness during the mutation, and any stale-page rejection is
shown directly to the reviewer. Password step-up and reviewer-note rules are unchanged.

The acquired-candidate page no longer relies on the legacy `identity.*` checklist or a
hard-coded “not ready” message. It now renders all resolved claim entities dynamically.
Every fact card shows its value, official source title and URL, exact excerpt, full scope,
checked time, evidence block/offsets, authority tier, and extraction lineage.

Secondary disclosures expose artifacts and routing, extraction attempts, acquisition
bundle gaps, conflicts, duplicates, warnings, and human/audit history. The readiness
banner and summary make the supported count, blockers, and source freshness visible at
the top of the page.

## Filters

The admin catalogue provides the requested filters:

- complete;
- missing funding;
- missing deadline;
- missing eligibility;
- conflicts;
- duplicates;
- stale sources; and
- failed acquisition.

Opportunity filtering uses backend publication-readiness reasons and duplicate
suggestions. Acquisition filtering uses persisted objective coverage, statuses, source
timestamps, failure codes, conflicts, and duplicate IDs. Acquired candidates now load
across statuses rather than only `needs_review`, so failed records remain discoverable.

## Regression coverage

- Candidate projection tests assert typed values, exact evidence, complete scope,
  source freshness, extraction lineage, artifacts, attempts, acquisition gaps, and audit
  history.
- A candidate-only regression proves that acquired evidence remains inspectable while
  extraction and publication readiness stay blocked.
- Admin opportunity API coverage asserts current readiness is included for both complete
  and blocked records.
- Frontend tests cover readiness/acquisition filter classification plus typed claim-value
  and scope formatting.

## Verification

- Full backend `pytest -m "not e2e"` — 786 selected: 763 passed, 23 skipped, 10
  deselected; no failures.
- Focused candidate review projection — 2 passed.
- Full Ruff check — passed.
- `git diff --check` — passed (Git emitted only LF/CRLF conversion notices).
- Frontend Vitest — 9 files, 37 tests passed.
- Frontend TypeScript/Vite production build — passed with one pre-existing mixed
  static/dynamic import warning.
- Admin browser test was requested but skipped because the Playwright browser runtime is
  not installed in this environment.

## Cost and safety

- Azure/OpenAI/model calls: 0.
- Estimated and observed model cost: USD 0.
- Live network acquisition: none.
- Deployment, merge, push, production flags, and non-test publication: none.
- The pre-existing dirty worktree was preserved.

## Exit gate

Passed. An owner can see in one page what was found, what remains incomplete, which
official evidence supports each value, how it is scoped, how fresh it is, and which exact
backend rule prevents publication. Phase 6 has not started.
