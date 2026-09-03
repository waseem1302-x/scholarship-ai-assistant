# MVP Truth-First Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Launch the first public version with a trustworthy scholarship journey powered by reviewed extraction data: discover, inspect, check fit, save, and execute an application plan without exposing unfinished AI, Document Lab, or Community promises.

**Architecture:** Keep catalogue extraction as the evidence-producing layer and add a separate deterministic public projection over reviewed graph entities. Preserve the existing public opportunity contract while adding scoped graph facts, evidence references, summaries, and explicit unknowns. The homepage will consume existing public catalogue endpoints for scholarship rows and retain only static workflow cards for capabilities that are genuinely available in V1.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Alembic, React 19, TypeScript, Vitest, pytest.

**Spec:** `docs/scholarship-information-contract.md`; `docs/superpowers/specs/2026-09-03-homepage-conversion-sections-design.md`

## Global Constraints

- The launch definition is catalogue + scholarship detail + profile + deterministic matching + Applications.
- Assistant, Document Lab, and Community remain disabled and receive no homepage conversion links.
- Extraction remains atomic and evidence-first; it must not generate marketing summaries or application advice.
- Every published decision-critical value must come from an officially verified source and preserve its graph scope.
- Unknown, confirmed absent, not applicable, stale, and conflicting are distinct states.
- Existing public API fields remain backward-compatible while graph-backed fields are added.
- No inferred scholarship facts, funding values, required documents, deadlines, or selection probabilities may appear.
- No new infrastructure dependency is required for V1; pgvector, Azure AI Search, browser acquisition, and private-document processing remain deferred.

---

### Task 0: Restore and record a clean runtime baseline

**Files:**
- Inspect: `app/main.py`
- Inspect: `app/core/config.py`
- Inspect: `app/db/session.py`
- Inspect: `app/modules/opportunities/routes.py`
- Inspect: `app/modules/beta/routes.py`
- Modify only if the diagnosis proves a code defect: the smallest responsible file above
- Test: the nearest existing route or configuration test for the diagnosed failure

**Reason:** The current browser session returned HTTP 500 for the public catalogue request. No
feature work should be layered over an unhealthy local API, and an environment/migration problem
must not be mistaken for a product-code defect.

- [ ] **Step 1: Reproduce against the backend directly**

Run migrations, start the documented FastAPI entrypoint, and request the health endpoint plus
`GET /api/v1/opportunities?limit=10`. Capture the server traceback and response body.

- [ ] **Step 2: Classify the failure before changing code**

Check database connectivity, migration head, required environment settings, and route registration.
If the error is environment-only, repair the local configuration and document the command; do not
change application behavior. If it is a code defect, first add a focused regression test that
reproduces the traceback.

- [ ] **Step 3: Establish the baseline**

The task is complete only when health and the public catalogue return non-500 responses, the focused
test passes, and the exact local startup/migration commands are recorded for later browser checks.

---

### Task 1: Add the public scholarship projection contract

**Files:**
- Modify: `app/modules/opportunities/schemas.py`
- Create: `app/modules/opportunities/public_projection.py`
- Test: `tests/test_opportunity_public_projection.py`

**Interfaces:**
- Consumes: reviewed `Opportunity`, `OpportunityCycle`, `ApplicationTrack`, `ScholarshipProgramme`, `ScholarshipEligibilityRule`, `ScopedDeadline`, `FundingComponent`, `RequiredDocument`, `ApplicationStep`, `OpportunityEvent`, `OpportunityResource`, and `FieldEvidence` rows.
- Produces: `build_public_projection(session: Session, opportunity: Opportunity) -> PublicScholarshipProjectionResponse`.
- Produces additive `projection` on `OpportunityDetailResponse`; legacy fields remain unchanged during V1.

- [x] **Step 1: Write failing projection tests**

Create fixtures containing one global fact, one route-scoped fact, one programme-scoped fact, one unknown dimension, and one unverified source. Assert that the projection exposes reviewed facts with scope and evidence while excluding unverified evidence.

```python
def test_public_projection_preserves_scope_and_excludes_unverified_claims(
    db_session: Session,
) -> None:
    opportunity = create_reviewed_graph_fixture(db_session)

    projection = build_public_projection(db_session, opportunity)

    assert projection.tracks[0].scope.track_id is not None
    assert projection.eligibility[0].evidence
    assert all(item.verification_status == "officially_verified" for item in projection.evidence)
    assert "documents" in projection.known_unknowns
```

- [x] **Step 2: Run the new tests and verify RED**

Run: `.venv/Scripts/python -m pytest tests/test_opportunity_public_projection.py -v`

Expected: FAIL because the public projection types and builder do not exist.

- [x] **Step 3: Add strictly typed public graph response models**

Add models for:

```python
class PublicFactScopeResponse(BaseModel):
    cycle_id: uuid.UUID | None = None
    track_id: uuid.UUID | None = None
    institution_id: uuid.UUID | None = None
    programme_id: uuid.UUID | None = None


class PublicEvidenceReferenceResponse(BaseModel):
    id: uuid.UUID
    source_title: str
    source_url: HttpUrl
    excerpt: str
    last_verified_at: datetime | None
    verification_status: VerificationStatus


class PublicScholarshipProjectionResponse(BaseModel):
    tracks: list[PublicTrackResponse] = Field(default_factory=list)
    programmes: list[PublicProgrammeResponse] = Field(default_factory=list)
    eligibility: list[PublicEligibilityResponse] = Field(default_factory=list)
    deadlines: list[PublicDeadlineResponse] = Field(default_factory=list)
    funding: list[PublicFundingResponse] = Field(default_factory=list)
    documents: list[PublicDocumentResponse] = Field(default_factory=list)
    steps: list[PublicApplicationStepResponse] = Field(default_factory=list)
    events: list[PublicEventResponse] = Field(default_factory=list)
    resources: list[PublicResourceResponse] = Field(default_factory=list)
    evidence: list[PublicEvidenceReferenceResponse] = Field(default_factory=list)
    known_unknowns: list[str] = Field(default_factory=list)
```

- [x] **Step 4: Implement the projection builder**

Select the effective current cycle, load graph children, retain their explicit scope IDs, and admit evidence only when the linked source is officially verified and not disqualified by `EvidencePolicy`. Populate `known_unknowns` from missing core dimensions; do not invent placeholder values.

- [x] **Step 5: Run projection and existing opportunity tests**

Run: `.venv/Scripts/python -m pytest tests/test_opportunity_public_projection.py tests/test_opportunities.py -v`

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add app/modules/opportunities/schemas.py app/modules/opportunities/public_projection.py tests/test_opportunity_public_projection.py
git commit -m "feat: add reviewed public scholarship projection"
```

---

### Task 2: Connect the projection to the public detail API

**Files:**
- Modify: `app/modules/opportunities/service.py`
- Modify: `app/modules/opportunities/routes.py`
- Modify: `tests/test_opportunities.py`

**Interfaces:**
- Consumes: `build_public_projection(session, opportunity)` from Task 1.
- Produces: `GET /api/v1/opportunities/{opportunity_id}` with an additive `projection` object.

- [x] **Step 1: Write failing API tests**

```python
def test_public_detail_returns_reviewed_graph_projection(client, reviewed_graph_opportunity):
    response = client.get(f"/api/v1/opportunities/{reviewed_graph_opportunity.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["projection"]["funding"]
    assert body["projection"]["documents"]
    assert body["projection"]["evidence"]


def test_public_detail_does_not_expose_draft_graph(client, draft_graph_opportunity):
    response = client.get(f"/api/v1/opportunities/{draft_graph_opportunity.id}")
    assert response.status_code == 404
```

- [x] **Step 2: Run tests and verify RED**

Run: `.venv/Scripts/python -m pytest tests/test_opportunities.py -k "public_detail and projection" -v`

Expected: FAIL because the detail service does not attach a graph projection.

- [x] **Step 3: Attach the projection in `to_detail_response`**

Call the projection builder only after the existing active-status and official-source gates pass. Do not expose the administrator graph route or reuse its weaker response contract.

- [x] **Step 4: Verify backward compatibility**

Run: `.venv/Scripts/python -m pytest tests/test_opportunities.py tests/test_matching.py tests/test_applications.py -v`

Expected: PASS with existing flat fields unchanged.

- [x] **Step 5: Commit**

```bash
git add app/modules/opportunities/service.py app/modules/opportunities/routes.py tests/test_opportunities.py
git commit -m "feat: expose reviewed scholarship graph publicly"
```

---

### Task 3: Add deterministic decision summaries

**Files:**
- Modify: `app/modules/opportunities/public_projection.py`
- Modify: `app/modules/opportunities/schemas.py`
- Test: `tests/test_opportunity_public_projection.py`

**Interfaces:**
- Consumes: reviewed public projection from Task 1.
- Produces: `build_decision_summary(opportunity, projection) -> ScholarshipDecisionSummaryResponse`.
- Each summary block contains `text`, `evidence_ids`, and `state` where state is `confirmed`, `unknown`, `not_applicable`, `stale`, or `conflicting`.

- [x] **Step 1: Write failing summary tests**

```python
def test_summary_uses_only_confirmed_values(reviewed_projection):
    opportunity, projection = reviewed_projection
    summary = build_decision_summary(opportunity, projection)

    assert summary.overview.state == "confirmed"
    assert summary.overview.evidence_ids
    assert "guaranteed" not in summary.overview.text.casefold()


def test_missing_funding_is_explicitly_unknown(projection_without_funding):
    opportunity, projection = projection_without_funding
    summary = build_decision_summary(opportunity, projection)
    assert summary.funding.state == "unknown"
    assert summary.funding.text == "Funding coverage is not confirmed in the reviewed sources."
```

- [x] **Step 2: Run tests and verify RED**

Run: `.venv/Scripts/python -m pytest tests/test_opportunity_public_projection.py -k summary -v`

Expected: FAIL because the deterministic summary builder does not exist.

- [x] **Step 3: Implement deterministic templates**

Generate only four compact blocks: overview, funding, eligibility, and application route. Each sentence must be composed from reviewed projection values. Missing data produces an explicit unknown sentence rather than a guess. Do not call Azure or any other model.

- [x] **Step 4: Run projection tests**

Run: `.venv/Scripts/python -m pytest tests/test_opportunity_public_projection.py -v`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add app/modules/opportunities/public_projection.py app/modules/opportunities/schemas.py tests/test_opportunity_public_projection.py
git commit -m "feat: add evidence-bound decision summaries"
```

---

### Task 4: Remove unsupported public claims

**Files:**
- Modify: `frontend/src/features/catalogue/types.ts`
- Modify: `frontend/src/features/catalogue/OpportunityDetailPage.tsx`
- Modify: `frontend/src/features/catalogue/OpportunityDetailPage.test.tsx`
- Modify: `app/modules/opportunities/comparator.py`
- Modify: `app/modules/opportunities/routes.py`
- Modify: `tests/test_launch_mvp_modules.py`
- Modify: `tests/test_opportunities.py`

**Interfaces:**
- Consumes: additive `projection` and deterministic summary from Tasks 1–3.
- Produces: an honest scholarship detail UI with explicit unknown states and a comparator that reports only source-supported amounts.

- [x] **Step 1: Write failing frontend truth tests**

```tsx
it("does not invent documents or funding when evidence is absent", async () => {
  renderOpportunityDetail(opportunityWithoutFundingOrDocuments);

  expect(await screen.findByText(/not confirmed in the reviewed sources/i)).toBeVisible();
  expect(screen.queryByText(/official academic transcripts & valid passport/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/^covered$/i)).not.toBeInTheDocument();
});
```

- [x] **Step 2: Write failing comparator tests**

Assert that a scholarship without explicit monetary components has `total_estimated_annual_value_usd=None`, no invented benefits, and cannot be selected as the highest-value scholarship.

- [x] **Step 3: Run the tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/features/catalogue/OpportunityDetailPage.test.tsx`

Run: `.venv/Scripts/python -m pytest tests/test_launch_mvp_modules.py -k funding -v`

Expected: FAIL on current fallback copy and heuristic values.

- [x] **Step 4: Render the new projection progressively**

Show summary first, then funding, eligibility, routes, deadlines, documents, steps, known unknowns, and citations. Omit empty decorative cards. Render the literal state “Not confirmed in reviewed sources” when evidence is unavailable.

- [x] **Step 5: Remove comparator estimates**

Delete the `$20,000`, `$12,000`, `$35,000`, and `$10,000` fallback estimates. Calculate normalized totals only from an explicit amount, currency, and supported frequency.

- [x] **Step 6: Run backend and frontend tests**

Run: `.venv/Scripts/python -m pytest tests/test_launch_mvp_modules.py tests/test_opportunities.py -v`

Run: `cd frontend && pnpm exec vitest run src/features/catalogue/OpportunityDetailPage.test.tsx`

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add frontend/src/features/catalogue app/modules/opportunities/comparator.py tests/test_launch_mvp_modules.py
git commit -m "fix: keep public scholarship claims evidence-bound"
```

---

### Task 5: Make the five homepage sections truthful and data-backed

**Files:**
- Modify: `frontend/src/features/home/homepageJourneyContent.ts`
- Create: `frontend/src/features/home/homepageJourney.ts`
- Modify: `frontend/src/features/home/HomePage.tsx`
- Modify: `frontend/src/features/home/HomepageJourneySection.tsx`
- Modify: `frontend/src/features/home/HomePage.test.tsx`
- Modify: `frontend/src/features/home/homepageJourneyContent.test.ts`

**Interfaces:**
- Consumes: existing `GET /opportunities` filters and `OpportunitySummary`.
- Produces: `loadHomepageOpportunityRows(signal?: AbortSignal) -> Promise<HomepageOpportunityRows>`.
- Produces five V1 sections: verified opportunities, open/upcoming opportunities, destination/study paths, profile matching, and application planning.

- [x] **Step 1: Write failing homepage data tests**

```ts
it("builds scholarship rows from public catalogue responses", async () => {
  apiClient.request = vi.fn()
    .mockResolvedValueOnce({ items: verifiedItems, pagination })
    .mockResolvedValueOnce({ items: openItems, pagination });

  const rows = await loadHomepageOpportunityRows();

  expect(rows.verified[0].opportunityId).toBe(verifiedItems[0].id);
  expect(rows.open.every((item) => item.applicationWindowState === "open")).toBe(true);
});
```

- [x] **Step 2: Run tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/features/home/HomePage.test.tsx src/features/home/homepageJourneyContent.test.ts`

Expected: FAIL because homepage opportunity loading does not exist.

- [x] **Step 3: Add the V1 homepage loader**

Use existing public calls:

```ts
await Promise.all([
  searchOpportunities({ ...defaultCatalogueFilters, limit: "10" }, 0, signal),
  searchOpportunities(
    { ...defaultCatalogueFilters, availability: "open", limit: "10" },
    0,
    signal,
  ),
  searchOpportunities(
    { ...defaultCatalogueFilters, funding_type: "full", limit: "10" },
    0,
    signal,
  ),
]);
```

Map returned records to direct `/catalogue/{id}` links. Use existing local destination artwork by country; imagery remains decorative and never becomes evidence.

- [x] **Step 4: Replace unavailable capability promises**

Use these five rows:

1. `Verified scholarships worth exploring`
2. `Applications open now`
3. `Explore funded study paths`
4. `Check which opportunities fit you`
5. `Save and build your application plan`

Rows 1–3 use catalogue data. Rows 4–5 use truthful workflow cards for `/profile`, `/matches`, `/catalogue`, `/applications`, and `/dashboard`. Remove homepage links to `/assistant`, `/document-lab`, and `/community` for V1.

- [x] **Step 5: Add loading, empty, and API-failure behavior**

Render skeletons while loading. If a dynamic row is empty, omit that row rather than showing fictional scholarships. If the API fails, retain the workflow rows and show one non-blocking catalogue availability message.

- [x] **Step 6: Run frontend tests and build**

Run: `cd frontend && pnpm test -- --run`

Run: `cd frontend && pnpm build`

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add frontend/src/features/home
git commit -m "feat: power launch homepage from verified catalogue"
```

---

### Task 6: Add a launch catalogue quality gate

**Files:**
- Create: `app/modules/opportunities/launch_audit.py`
- Create: `app/cli/audit_launch_catalogue.py`
- Create: `tests/test_launch_catalogue_audit.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `audit_launch_catalogue(session: Session, *, minimum_records: int) -> LaunchCatalogueAudit`.
- CLI exits non-zero when the catalogue has too few publishable records, stale official evidence, unresolved conflicts, missing Tier-0 evidence, or unsupported public summary claims.

- [x] **Step 1: Write failing audit tests**

```python
def test_launch_audit_blocks_stale_or_incomplete_records(db_session):
    create_launch_fixture(db_session, stale=True, coverage_state="unknown")

    result = audit_launch_catalogue(db_session, minimum_records=1)

    assert result.ready is False
    assert result.blockers_by_code["stale_official_source"] == 1
    assert result.blockers_by_code["incomplete_record"] == 1
```

- [x] **Step 2: Run tests and verify RED**

Run: `.venv/Scripts/python -m pytest tests/test_launch_catalogue_audit.py -v`

Expected: FAIL because the audit service and CLI do not exist.

- [x] **Step 3: Implement the deterministic audit**

Report:

- active reviewed scholarship count;
- complete-core and publishable-with-gaps counts derived from required
  `CatalogueCoverageCell` states, rather than trusting the currently unsynchronised
  `Opportunity.publication_completeness` string;
- stale-source count;
- unresolved-conflict count;
- records missing identity, current cycle, funding, eligibility, route, deadline, or evidence;
- the exact opportunity IDs requiring curator action.

Use `evaluate_scoped_completeness(...)` output and persisted coverage cells as the source of
truth. Treat every required cell in `complete` or `not_applicable` as complete-core. Treat records
with a reviewed identity and route but non-critical unknown cells as publishable-with-gaps; list
the open cells explicitly. Do not mutate or auto-correct catalogue records from the audit command.

Default the CLI threshold to 12 reviewed flagship scholarships. Allow `--minimum-records` to raise the threshold without changing code.

- [x] **Step 4: Document the launch command**

Add:

```powershell
.\.venv\Scripts\python.exe -m app.cli.audit_launch_catalogue --minimum-records 12
```

The command must be run against staging immediately before release approval.

- [x] **Step 5: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_launch_catalogue_audit.py tests/test_catalogue_ingestion.py tests/test_opportunities.py -v`

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add app/modules/opportunities/launch_audit.py app/cli/audit_launch_catalogue.py tests/test_launch_catalogue_audit.py README.md
git commit -m "feat: add catalogue launch readiness gate"
```

---

### Task 7: Verify a flagship launch catalogue in staging

**Files:**
- Create: `data/launch-scholarships.json`
- Create: `docs/mvp-launch-runbook.md`
- Modify: `.github/workflows/azure-application-deploy.yml`
- Modify: `tests/test_browser_e2e.py`

**Interfaces:**
- Consumes: reviewed extraction and publication workflow plus the audit CLI from Task 6.
- Produces: a reproducible staging release receipt for at least 12 flagship scholarships.

- [ ] **Step 1: Create the initial launch manifest**

Include the eight already represented on the homepage—DAAD EPOS, Fulbright Foreign Student Program, Chevening, Vanier, Australia Awards, Erasmus Mundus Joint Masters, MEXT Research, and Commonwealth Master’s—plus Gates Cambridge, Türkiye Scholarships, Stipendium Hungaricum, and Swedish Institute Scholarships for Global Professionals. Store canonical names and reviewed official root URLs only; do not store copied scholarship claims in the manifest.

- [ ] **Step 2: Add a browser acceptance journey**

The journey must verify:

```text
homepage card → catalogue result → scholarship detail → official evidence
                 ↓
              profile → explainable match → save → application plan
```

Assert that Assistant, Document Lab, and Community are not promoted from the V1 homepage.

- [ ] **Step 3: Add the staging runbook**

Document exact operator steps: create ingestion run, inspect extraction plan, process, review conflicts, approve, materialize, mark publication-ready, publish, run catalogue audit, run smoke tests, and record release evidence.

- [ ] **Step 4: Gate deployment on catalogue audit and smoke tests**

Run the audit after migration and before traffic promotion. A failed audit must stop deployment without deleting or auto-correcting records.

- [ ] **Step 5: Run the complete release checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m pytest
Set-Location frontend
pnpm test -- --run
pnpm build
```

Run the configured Chromium catalogue-to-application journey against staging. Then execute the catalogue audit with `--minimum-records 12`.

Expected: all checks pass and the audit reports `ready=true`.

- [ ] **Step 6: Commit**

```bash
git add data/launch-scholarships.json docs/mvp-launch-runbook.md .github/workflows/azure-application-deploy.yml tests/test_browser_e2e.py
git commit -m "chore: gate the truth-first MVP launch"
```

---

## Deferred follow-up plans

These are intentionally separate projects and must not block V1:

1. **Public scholarship RAG and Assistant:** PostgreSQL FTS/pgvector projection, retrieval gateway, evidence packets, Azure model gateway, structured answers, claim validation, abstention, and evaluation corpus.
2. **Scholarship preparation playbooks:** first-class selection criteria, essay prompts, interview stages, evidence dimensions, and versioned cited playbook projections.
3. **Private Document Lab:** reviewed Azure provider adapter, scanner/worker readiness, private retrieval, consent, retention, deletion, and scholarship-specific rubrics.
4. **Community:** enable only after the agreed active-user threshold and moderation/abuse operations exist.
5. **Research-position acquisition:** separate `ResearchPosition` claim schema and public model, with source policies for university pages and explicitly permitted social sources. LinkedIn authentication or scraping is not part of the scholarship crawler.

## Estimated delivery

- Tasks 1–4: 6–9 engineering days.
- Task 5: 2–3 engineering days.
- Task 6: 1–2 engineering days.
- Task 7 and flagship curation: 3–5 engineering days, partly parallel with Tasks 1–6.
- Expected elapsed time for one focused engineer: approximately 10–15 working days, excluding external Azure/GitHub approval delays.
