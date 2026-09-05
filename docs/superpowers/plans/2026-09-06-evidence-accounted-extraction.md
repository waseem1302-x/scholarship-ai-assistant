# Evidence-Accounted Catalogue Extraction Implementation Plan

**Goal:** Prevent acquired official scholarship evidence from disappearing between parsing and the
review proposal by making semantic evidence units, focused extraction, claim cardinality, fallback
guidance, and completeness accounting explicit.

**Architecture:** Reuse persisted artifacts, evidence blocks/routes, extraction jobs, strict evidence
validation, claim resolution, and scoped completeness. Change their contract in place; do not add a
second ingestion pipeline or scholarship-specific rules.

**Spec:** `docs/superpowers/specs/2026-09-06-evidence-accounted-extraction-design.md`

## Constraints

- Use red-green TDD for each task.
- Preserve exact artifact offsets and evidence validation.
- Keep old persisted JSON readable through defaults.
- Add no dependency and no database migration unless an existing persistence constraint proves it is
  required.
- Run focused tests after every task and the full repository verification before committing.
- Do not run a paid provider call in this plan.

## Task 1: Preserve semantic evidence boundaries

**Files:**
- Modify: `app/modules/catalogue_ingestion/acquisition_fetcher.py`
- Modify: `app/modules/catalogue_ingestion/evidence_blocks.py`
- Modify: `app/modules/catalogue_ingestion/evidence_block_models.py`
- Test: `tests/test_evidence_acquirer.py`
- Test: `tests/test_catalogue_evidence_routing.py`

1. Add failing tests proving headings, paragraphs, list items, table rows, and adjacent rules retain
   boundaries after HTML conversion and produce stable exact-offset units.
2. Verify the tests fail against the fixed-character block implementation.
3. Preserve structural newlines in HTML conversion and split blocks on semantic boundaries, with the
   current maximum size only as a long-unit fallback.
4. Advance the block-builder version and run the focused tests.

## Task 2: Make jobs route-focused

**Files:**
- Modify: `app/modules/catalogue_ingestion/extraction_planner.py`
- Test: `tests/test_catalogue_extraction_planner.py`

1. Add a failing planner test with disjoint identity and funding routes and assert each planned job
   contains only its selected objective.
2. Derive job objectives from selected routes and pack only compatible adjacent units within existing
   request limits.
3. Advance the planner version and run planner/routing tests.

## Task 3: Require an explicit unit disposition

**Files:**
- Modify: `app/modules/catalogue_ingestion/claim_bundle_schemas.py`
- Modify: `app/modules/catalogue_ingestion/claim_bundle_provider.py`
- Modify: `app/modules/catalogue_ingestion/claim_bundle_validation.py`
- Modify: `app/modules/catalogue_ingestion/claim_schemas.py`
- Test: `tests/test_catalogue_claim_bundle_evidence.py`
- Test: `tests/test_catalogue_extraction_planner.py`

1. Add failing tests for missing, unknown, duplicated, false-mapped, and valid dispositions.
2. Add backward-compatible disposition models and require one disposition per unit for new provider
   output.
3. Validate `mapped` against accepted claim evidence and `duplicate` against content identity; derive
   no-route `irrelevant` dispositions deterministically.
4. Persist the ledger in `ClaimResolution`, advance bundle/prompt versions, and run focused tests.

## Task 4: Declare field cardinality

**Files:**
- Modify: `app/modules/catalogue_ingestion/claim_schemas.py`
- Modify: `app/modules/catalogue_ingestion/claim_resolution.py`
- Test: `tests/test_catalogue_ingestion.py`

1. Add failing tests proving two scholarship aliases merge while two distinct singleton canonical
   names still conflict.
2. Add the cardinality enum/registry and make resolution dispatch through it.
3. Preserve existing precedence, scope, ordering, and evidence behavior; run resolution tests.

## Task 5: Preserve unsupported student-relevant facts

**Files:**
- Modify: `app/modules/catalogue_ingestion/claim_schemas.py`
- Modify: `app/modules/catalogue_ingestion/claim_provider.py`
- Modify: `app/modules/catalogue_ingestion/claim_bundle_provider.py`
- Test: `tests/test_catalogue_claim_bundle_evidence.py`

1. Add a failing test showing a work-rights or appeal-rule fact is accepted as evidence-backed
   `guidance` under its closest routed objective.
2. Permit guidance for every objective and instruct the provider to use it only when a fact has no
   typed representation.
3. Keep all normal field and evidence validation; run schema/provider tests.

## Task 6: Compute completeness from the evidence ledger

**Files:**
- Modify: `app/modules/catalogue_ingestion/scoped_completeness.py`
- Modify: `app/modules/catalogue_ingestion/production_service.py`
- Test: `tests/test_catalogue_ingestion.py`
- Test: `tests/test_catalogue_claim_bundle_evidence.py`

1. Add failing tests proving provider `complete` cannot hide an unresolved or undisposed selected
   unit, while all mapped/duplicate/irrelevant units permit normal completeness evaluation.
2. Build the deterministic ledger from persisted blocks/routes, validated output, and resolved claims.
3. Add stable evidence-unit completeness errors and include the ledger in the review payload.
4. Run focused completeness and production-service tests.

## Task 7: Recover unresolved evidence independently

**Files:**
- Modify: `app/modules/catalogue_ingestion/production_service.py`
- Test: `tests/test_catalogue_ingestion.py`

1. Add failing tests proving an unrelated recoverable rejection or field conflict does not suppress a
   gap pass for unresolved units.
2. Target the existing bounded gap pass at unresolved units/objectives while retaining final
   materialization blockers and existing budget/pass limits.
3. Run the focused service tests.

## Task 8: End-to-end fixture and repository verification

**Files:**
- Modify/Add only the relevant catalogue test fixture and test files.

1. Add an Open-Doors-shaped local fixture with subject and university lists, FAQ/rule clauses, a
   funding fact, work rights, and official resource links. Assert every relevant unit is mapped or
   explicitly unresolved and no fact needs a scholarship-specific rule.
2. Run all focused catalogue ingestion tests.
3. Run the full backend suite and Ruff.
4. Run frontend tests, lint, and production build.
5. Review the diff for scope and secrets, commit the implementation on
   `codex/catalogue-completeness`, and report that the next paid run still requires explicit approval.
