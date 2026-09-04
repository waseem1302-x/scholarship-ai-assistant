# Catalogue Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in evidence-complete catalogue run that exhausts the relevant official-source frontier, recovers deterministic extraction failures through smaller spans, and reports incomplete work truthfully.

**Architecture:** Preserve the existing bounded mode and add a settings-driven completeness branch at run creation and crawl-budget derivation. Reuse the current crawler, extraction planner, quarantine ledger, resumable jobs, and scoped completeness evaluator; extend only their stopping and failure transitions. Provider request token limits remain physical per-call limits, while deterministic splitting prevents them from becoming evidence-loss limits.

**Tech Stack:** Python 3.12, Pydantic Settings, SQLAlchemy, pytest, Ruff, Azure Bicep, React/Vite verification.

**Spec:** `docs/superpowers/specs/2026-09-05-catalogue-completeness-design.md`

## Global Constraints

- Completeness mode is opt-in; existing bounded behavior remains unchanged.
- Emergency ceilings are exactly 500 physical model calls and USD 5 per scholarship.
- No claim bypasses exact persisted evidence-span validation.
- URL safety, official-domain authority, byte limits, and human review remain enforced.
- No new dependency or database migration.
- Run focused tests after each red/green cycle and the full backend suite before every task commit.
- Run frontend tests/build and Ruff before the final implementation commit.

---

### Task 1: Completeness Run and Crawl Budgets

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/modules/catalogue_ingestion/acquisition_runtime.py`
- Modify: `app/modules/catalogue_ingestion/crawler.py`
- Modify: `app/modules/catalogue_ingestion/service.py`
- Modify: `app/modules/catalogue_ingestion/provider_config.py`
- Modify: `infra/azure/scheduled-jobs.bicep`
- Test: `tests/test_bounded_crawler_ingestion.py`
- Test: `tests/test_bounded_crawler_core.py`

**Interfaces:**
- Produces settings `catalogue_completeness_mode_enabled: bool`, `catalogue_completeness_max_fetch_attempts: int`, `catalogue_completeness_max_model_calls: int`, and `catalogue_completeness_max_estimated_cost_per_run: Decimal`.
- Produces `CrawlBudget.max_accepted_artifacts: int | None` and `CrawlBudget.max_wall_seconds: float | None`; `None` means frontier exhaustion rather than that normal stopping condition.
- `crawl_budget_for_run(run, settings) -> CrawlBudget` remains the only runtime budget constructor.

- [ ] **Step 1: Write failing settings and runtime tests**

```python
def test_completeness_mode_uses_frontier_exhaustion_and_approved_paid_failsafes() -> None:
    configured = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
        catalogue_completeness_mode_enabled=True,
    )
    run = CatalogueIngestionRun(
        source_label="direct-url:example.edu",
        source_fingerprint="f" * 64,
        input_kind=IngestionInputKind.DIRECT_URL,
        mode=IngestionMode.REVIEW_QUEUE,
        max_candidates=1,
        max_pages_per_candidate=10,
        max_model_calls=configured.catalogue_completeness_max_model_calls,
        max_input_characters=configured.catalogue_ai_max_input_characters,
        max_output_tokens=configured.catalogue_ai_max_output_tokens,
        max_estimated_cost=configured.catalogue_completeness_max_estimated_cost_per_run,
    )

    budget = crawl_budget_for_run(run, configured)

    assert budget.max_accepted_artifacts is None
    assert budget.max_wall_seconds is None
    assert budget.max_fetch_attempts == 1_000
    assert run.max_model_calls == 500
    assert run.max_estimated_cost == Decimal("5")
```

Add a run-creation assertion that completeness mode persists 500 calls and USD 5, while the existing bounded-mode test continues to persist its current settings.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
& 'C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Scripts\python.exe' -m pytest tests/test_bounded_crawler_ingestion.py tests/test_bounded_crawler_core.py -q
```

Expected: FAIL because completeness settings and optional crawl limits do not exist.

- [ ] **Step 3: Implement the minimal completeness budget branch**

Add these settings with the stated bounds:

```python
catalogue_completeness_mode_enabled: bool = False
catalogue_completeness_max_fetch_attempts: int = Field(default=1_000, ge=1, le=10_000)
catalogue_completeness_max_model_calls: int = Field(default=500, ge=1, le=5_000)
catalogue_completeness_max_estimated_cost_per_run: Decimal = Field(
    default=Decimal("5.00"), ge=0, le=10_000
)
```

In `crawl_budget_for_run`, return a completeness budget with no accepted-artifact or wall-time stop, a 1,000-attempt emergency frontier ceiling, depth 3, 500 links/page, and existing byte/per-host safety. In `create_run_from_source` and `create_run_from_url`, choose the completeness call/cost ceilings only when the mode is enabled. Add the new non-secret settings to the configuration fingerprint and expose the mode plus exact emergency limits in Bicep environment configuration.

- [ ] **Step 4: Run focused and full backend tests**

Run the focused command from Step 2, then:

```powershell
& 'C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Scripts\python.exe' -m pytest
```

Expected: 0 failures.

- [ ] **Step 5: Commit Task 1**

```powershell
git add app/core/config.py app/modules/catalogue_ingestion/acquisition_runtime.py app/modules/catalogue_ingestion/crawler.py app/modules/catalogue_ingestion/service.py app/modules/catalogue_ingestion/provider_config.py infra/azure/scheduled-jobs.bicep tests/test_bounded_crawler_ingestion.py tests/test_bounded_crawler_core.py
git commit -m "feat: add catalogue completeness budgets"
```

### Task 2: Relevant Frontier and Resume Reuse

**Files:**
- Modify: `app/modules/catalogue_ingestion/crawler.py`
- Modify: `app/modules/catalogue_ingestion/hardened_service.py`
- Test: `tests/test_bounded_crawler_core.py`
- Test: `tests/test_bounded_crawler_ingestion.py`

**Interfaces:**
- Produces `_is_non_content_link(url: str) -> bool` for deterministic pre-fetch rejection.
- Preserves `score_crawl_link(...) -> int`, adding only a penalty for unlabeled, non-document links.
- Reuses the existing `ProductionCatalogueIngestionService._process_direct_claims(...)` path when persisted explicit sources and artifacts are current.

- [ ] **Step 1: Write failing link and resume tests**

```python
def test_crawler_skips_static_and_calendar_resources_before_fetch() -> None:
    script = "https://example.edu/build/app.js"
    calendar = "https://example.edu/calendar/event.ics"
    eligibility = "https://example.edu/scholarship/eligibility"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Official scholarship overview.",
                links=(
                    FetchedLink(url=script, text=""),
                    FetchedLink(url=calendar, text=""),
                    FetchedLink(url=eligibility, text="Eligibility requirements"),
                ),
            ),
            eligibility: fetched_page(eligibility, "Official eligibility requirements."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(ROOT)

    assert fetcher.calls == [ROOT, eligibility]
    assert [item.reason for item in result.rejected].count("non_content_resource") == 2
```

Add a hardened-service regression test with a `SOURCE_FETCHED` direct candidate, one fetched primary source, and one persisted artifact. Replace `acquisition_crawler.crawl_many` with a function that raises if called and assert `_process_direct_claims` is called exactly once.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
& 'C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Scripts\python.exe' -m pytest tests/test_bounded_crawler_core.py tests/test_bounded_crawler_ingestion.py -q
```

Expected: link resources are fetched or queued, and hardened resume enters acquisition instead of claims.

- [ ] **Step 3: Implement generic filtering and artifact reuse**

Reject `.css`, `.js`, `.map`, `.ico`, font files, and `.ics` in `enqueue_links` with reason `non_content_resource`. Subtract 40 from links with no text/title unless they are recognized documents. In `HardenedCatalogueIngestionService._process_direct_candidate`, restore the existing base-service guard immediately after explicit-source validation:

```python
if candidate.status is CandidateStatus.SOURCE_FETCHED and all(
    source.status is CandidateSourceStatus.FETCHED and source.artifacts
    for source in explicit_sources
):
    if run.mode is IngestionMode.CANDIDATE_ONLY:
        self._manual_review(run, candidate, "candidate_only_complete", run_lease_token)
    elif not self.settings.catalogue_ai_ingestion_enabled:
        self._manual_review(run, candidate, "ai_ingestion_disabled", run_lease_token)
    else:
        self._process_direct_claims(run, candidate, run_lease_token)
    return
```

- [ ] **Step 4: Run focused and full backend tests**

Run the focused command from Step 2 and the full backend suite. Expected: 0 failures.

- [ ] **Step 5: Commit Task 2**

```powershell
git add app/modules/catalogue_ingestion/crawler.py app/modules/catalogue_ingestion/hardened_service.py tests/test_bounded_crawler_core.py tests/test_bounded_crawler_ingestion.py
git commit -m "fix: reuse catalogue evidence on resume"
```

### Task 3: Terminal Jobs, Validation Recovery, and Quarantine Evidence

**Files:**
- Modify: `app/modules/catalogue_ingestion/repository.py`
- Modify: `app/modules/catalogue_ingestion/production_service.py`
- Test: `tests/test_catalogue_extraction_planner.py`
- Test: `tests/test_catalogue_ingestion.py`

**Interfaces:**
- Produces `CatalogueIngestionRepository.fail_job(job_id, *, worker_id, run_lease_token, candidate_lease_token, error_code, error_detail, checkpoint) -> None`.
- Validation failures first use existing `split_extraction_job(...)`; unsplittable failures become terminal and do not erase valid independent groups.
- Quarantine detail contains `provider_attempt_id`, `validation_error`, `validation_warnings`, `objective_bundle`, `evidence_spans`, and `output_json`.

- [ ] **Step 1: Write failing repository and validation-diagnostic tests**

Add a repository test that starts an owned resumable job, calls `fail_job`, and asserts:

```python
assert job.state is CatalogueJobState.FAILED
assert job.error_code == "bundle_validation_failed"
assert job.error_detail == "invalid_evidence_span:deadline"
assert job.checkpoint["outcome"] == "validation_failed"
assert job.completed_at is not None
```

Extend the existing single-block planner fixture with invalid evidence output and assert `_expand_bundle` raises an `ExtractionSchemaError` whose message includes `invalid_evidence_span:outside`. Add a service-level fake-provider test asserting a splittable invalid job completes its parent with `outcome == "split"`, while an unsplittable invalid job is `FAILED` and its quarantine event retains `output_json` plus exact warnings.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
& 'C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Scripts\python.exe' -m pytest tests/test_catalogue_extraction_planner.py tests/test_catalogue_ingestion.py -q
```

Expected: `fail_job` is missing, validation messages are generic, and invalid paid output terminates the candidate without split recovery.

- [ ] **Step 3: Add the owned failed-job transition**

Implement `fail_job` beside `complete_job` using `_owned_job`, set `CatalogueJobState.FAILED`, bound `error_code` to 100 characters and `error_detail` to 1,000 characters, copy the checkpoint, set `completed_at`, and commit the session. Replace terminal schema/provider `checkpoint_job` calls with `fail_job`; provider deferral remains resumable.

- [ ] **Step 4: Preserve exact validation diagnostics and recover by splitting**

In `_expand_bundle`, collect every warning matching the existing severe prefixes and include the deduplicated values in the raised error message. In the post-provider validation catch:

```python
children = self._split_job(job, blocks_by_id=blocks_by_id, routes=job_routes, run=run)
detail = {
    "provider_attempt_id": str(execution.provider_attempt_id),
    "validation_error": str(exc)[:1000],
    "validation_warnings": _validation_warnings(str(exc)),
    "objective_bundle": [item.value for item in job.objectives],
    "evidence_spans": evidence_spans,
    "output_json": raw_output.model_dump(mode="json"),
}
```

Record that detail in the quarantine event. If children exist, complete the parent as `split` and prepend children to `pending_jobs`. Otherwise fail the job, append its safe error to `terminal_failures`, and continue the loop. Pass terminal failures to finalization and append them to `candidate.validation_errors`; do not report a complete candidate while any remain.

- [ ] **Step 5: Run focused and full backend tests**

Run the focused command from Step 2 and the full backend suite. Expected: 0 failures.

- [ ] **Step 6: Commit Task 3**

```powershell
git add app/modules/catalogue_ingestion/repository.py app/modules/catalogue_ingestion/production_service.py tests/test_catalogue_extraction_planner.py tests/test_catalogue_ingestion.py
git commit -m "fix: recover catalogue validation failures"
```

### Task 4: Completeness Truth Gate and Release Verification

**Files:**
- Modify: `app/modules/catalogue_ingestion/production_service.py`
- Modify: `README.md`
- Modify: `.env.example`
- Test: `tests/test_catalogue_extraction_planner.py`
- Test: `tests/test_bounded_crawler_ingestion.py`

**Interfaces:**
- Produces `_completeness_blockers(run, candidate, terminal_failures) -> list[str]`.
- Reuses the latest `CatalogueAcquisitionSnapshot`, existing scoped `resolution.completeness_errors`, and terminal job failures; no parallel completeness model is introduced.

- [ ] **Step 1: Write the failing truth-gate tests**

Add tests proving completeness mode appends `acquisition_budget:<reason>` when the latest snapshot has `budget_exhausted`, appends terminal extraction failures, and never marks such a candidate `READY_FOR_REVIEW`. Add the positive case: frontier not exhausted, no terminal failures, no scoped completeness errors, non-empty proposal, and every resumable job terminal.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
& 'C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Scripts\python.exe' -m pytest tests/test_catalogue_extraction_planner.py tests/test_bounded_crawler_ingestion.py -q
```

Expected: acquisition exhaustion is absent from candidate validation state.

- [ ] **Step 3: Implement the truth gate and operator documentation**

In completeness mode, query the newest acquisition snapshot for the candidate. Return blockers for each budget reason and disabled required escalation, plus terminal extraction failures. Merge these with scoped completeness errors before candidate status selection. Document the opt-in environment variables, exact USD 5/500-call emergency ceilings, and the definition of reachable-authority completeness in `.env.example` and `README.md`.

- [ ] **Step 4: Run all release checks**

Run:

```powershell
& 'C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Scripts\python.exe' -m pytest
& 'C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Scripts\python.exe' -m ruff check .
pnpm --dir frontend test
pnpm --dir frontend build
az bicep build --file infra/azure/scheduled-jobs.bicep --stdout | Out-Null
git diff --check
```

Expected: backend 0 failures, frontend 0 failures, production build success, Ruff clean, Bicep build success, and no whitespace errors.

- [ ] **Step 5: Review diff and commit the completed implementation**

Verify only approved completeness files changed, then:

```powershell
git add app/core/config.py app/modules/catalogue_ingestion/acquisition_runtime.py app/modules/catalogue_ingestion/crawler.py app/modules/catalogue_ingestion/hardened_service.py app/modules/catalogue_ingestion/production_service.py app/modules/catalogue_ingestion/provider_config.py app/modules/catalogue_ingestion/repository.py infra/azure/scheduled-jobs.bicep tests/test_bounded_crawler_core.py tests/test_bounded_crawler_ingestion.py tests/test_catalogue_extraction_planner.py tests/test_catalogue_ingestion.py .env.example README.md
git commit -m "feat: complete evidence-backed catalogue ingestion"
```

Do not push or run another paid Open Doors call in this plan. Report the branch and commits for user review.
