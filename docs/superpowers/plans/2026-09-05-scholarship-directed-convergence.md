# Scholarship-Directed Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make catalogue ingestion converge on complete scholarship-specific evidence without
exhausting an official domain or multiplying paid extraction work.

**Architecture:** Reuse the current safe fetchers, crawler, evidence blocks, resolver, cache, graph,
and review flow. Add an objective-aware admitted frontier and persisted acquisition rounds, then
feed objective closure back into acquisition. Repair extraction splitting, enumeration coverage,
provider circuit classification, and unsupported materialization defaults.

**Tech Stack:** Python 3.12, SQLAlchemy, Pydantic, Alembic, pytest, Azure OpenAI, pypdf, Docling,
Playwright.

**Spec:** `docs/superpowers/specs/2026-09-05-scholarship-directed-convergence-design.md`

## Global Constraints

- The operator-supplied URL is always fetched.
- No arbitrary total page/token ceiling may silently discard relevant scholarship evidence.
- Emergency resource ceilings remain explicit failures.
- Every accepted structured claim requires official evidence.
- Do not follow participating-university websites unless explicitly supplied as supporting sources.
- Preserve conditional Playwright and conditional OCR behavior.
- Add no dependency.

---

### Task 1: Scholarship-relevant link admission

**Files:** Modify `crawler.py`; test `test_bounded_crawler_core.py`.

**Produces:** objective-aware link assessment and a minimum admission threshold.

- [ ] Add tests proving FAQ/rules/funding/application/programme/institution-list links are admitted,
  while news, generic navigation, and individual university links are rejected.
- [ ] Run the focused tests and confirm the new assertions fail for the existing enqueue-all logic.
- [ ] Implement the smallest deterministic assessment and use it before enqueueing discovered links.
- [ ] Run focused crawler tests to green.

### Task 2: Resumable acquisition rounds

**Files:** Modify `crawler.py`, `acquisition_runtime.py`, `acquisition_models.py`,
`hardened_service.py`; test `test_bounded_crawler_core.py`, `test_bounded_crawler_ingestion.py`.

**Produces:** a bounded per-round result containing admitted deferred frontier items; emergency
limits remain run-wide.

- [ ] Add tests proving one round returns deferred relevant URLs and a subsequent round excludes
  already-fetched URLs.
- [ ] Verify RED.
- [ ] Implement round boundaries, frontier serialization, and resume inputs without changing URL
  safety or authority checks.
- [ ] Persist each round before extraction and verify focused tests.

### Task 3: Objective-specific frontier closure

**Files:** Modify `crawler.py`, `acquisition_runtime.py`, `scoped_completeness.py`,
`claim_resolution.py`; test `test_complete_acquisition_contract.py`,
`test_catalogue_ingestion.py`.

**Produces:** `closed_objectives` and `pending_objectives` from the relevant frontier.

- [ ] Add tests proving one objective may close while another still has an admitted URL.
- [ ] Verify RED.
- [ ] Pass objective closure into scoped completeness instead of a single whole-domain boolean.
- [ ] Verify focused tests.

### Task 4: Acquire-extract-measure loop

**Files:** Modify `hardened_service.py`, `production_service.py`, `repository.py`; test
`test_bounded_crawler_ingestion.py`, `test_catalogue_ingestion.py`.

**Produces:** candidate transitions that alternate acquisition and extraction until convergence.

- [ ] Add an integration test where the root resolves some objectives, the second round fetches
  only a missing-objective page, and the candidate terminates without visiting an irrelevant URL.
- [ ] Verify RED.
- [ ] Implement requeueing from unresolved coverage and resume the persisted relevant frontier.
- [ ] Verify focused tests.

### Task 5: Relevant sitemap fallback

**Files:** Modify `crawler.py`, `hardened_service.py`; test `test_bounded_crawler_core.py`.

**Produces:** sitemap discovery only when visible relevant links cannot close unresolved objectives;
sitemap entries use the same admission gate.

- [ ] Add tests for fallback activation and rejection of unrelated sitemap entries.
- [ ] Verify RED, implement, and rerun focused tests.

### Task 6: Participating-institution enumeration

**Files:** Modify `claim_schemas.py`, `claim_provider.py`, `scoped_completeness.py`,
`rich_graph_materializer.py`, relevant models/migration only if persistence requires it; test
`test_catalogue_ingestion.py`, `test_scholarship_graph_schema.py`.

**Produces:** scholarship-level participating institutions with count-aware completeness.

- [ ] Add tests for an official “20 universities” list and for an incomplete count.
- [ ] Verify RED.
- [ ] Reuse institution claims and existing topology count provenance; attach participation without
  requiring visits to institution websites.
- [ ] Verify focused tests.

### Task 7: FAQ and selection guidance preservation

**Files:** Modify claim contracts/prompts and rich graph persistence with the minimum schema change;
test claim-schema and graph tests.

**Produces:** evidence-backed FAQ, purpose, selection-criteria, and candidate-profile guidance.

- [ ] Add tests that preserve these facts and their source excerpts without turning them into
  unsupported advice.
- [ ] Verify RED.
- [ ] Implement the minimal typed representation and materialization path.
- [ ] Verify focused tests and migration upgrade/downgrade if a migration is needed.

### Task 8: Non-duplicating extraction recovery

**Files:** Modify `evidence_routing.py`, `extraction_planner.py`, `claim_bundle_schemas.py`; test
`test_catalogue_extraction_planner.py` and bundle validation tests.

**Produces:** slice-aware objective routing and deterministic evidence binding.

- [ ] Add tests proving two text slices do not both inherit unrelated objectives and repeated
  excerpts cannot silently bind to the wrong occurrence.
- [ ] Verify RED.
- [ ] Implement slice-level scoring/routing and bounded output sizing for large enumerations.
- [ ] Verify focused tests.

### Task 9: Provider health and runtime correctness

**Files:** Modify `scheduling.py`, `provider_execution.py`, `provider_config.py`, `.env.example`;
test `test_catalogue_scheduling.py` and provider execution tests.

**Produces:** endpoint-scoped health lanes; content/schema failures do not open provider circuits;
the production feature path is enabled by one authoritative configuration.

- [ ] Add tests for endpoint isolation, truncation handling, and enabled conditional capabilities.
- [ ] Verify RED.
- [ ] Implement the minimal circuit/config corrections and verify focused tests.

### Task 10: Evidence-only materialization and release verification

**Files:** Modify `rich_graph_materializer.py`, publication tests, README/runtime docs.

**Produces:** no unsupported degree, requiredness, or timezone facts; complete repository evidence.

- [ ] Add tests proving missing values remain unknown or block materialization rather than defaulting.
- [ ] Verify RED, implement the minimal corrections, and rerun focused tests.
- [ ] Run the complete backend suite, Ruff, frontend tests, frontend production build, Bicep build,
  migration checks, and `git diff --check`.
- [ ] Review the final diff, commit the passing implementation on
  `codex/catalogue-completeness`, and report any remaining limitation without a paid live call.
