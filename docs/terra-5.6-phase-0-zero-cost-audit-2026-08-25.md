# Terra 5.6 Phase 0 zero-cost catalogue audit

Date: 2026-08-25 (Asia/Singapore)

## Decision

Phase 0 is complete as an audit, but the catalogue is **not ready to enter a live pilot or bulk
expansion**. The three required families have official-source acquisition evidence, but none has a
complete, route/cycle-scoped, field-level evidence record. The existing active catalogue also has no
backend-owned publication-readiness policy: all 50 active rows satisfy the current public query even
though all 50 are marked `publication_completeness=incomplete`.

No application code, feature flag, opportunity, or database record was changed during this audit.
No network acquisition or Azure/OpenAI request was made by this audit.

## Safety boundary observed

- No deployment, merge, push, publication action, production flag, or ingestion run was performed.
- The dirty worktree was inspected before any write and preserved.
- The only new artifact from this pass is this report.
- Focused tests used fake/local providers. They made no paid provider calls.
- The database contains two **historical** Azure extraction attempts from 2026-08-15 for Chevening,
  both ending in deterministic validation failure. Their combined recorded usage is 4,236 input
  tokens, 1,581 output tokens, and USD 0.004222 estimated cost. They pre-date and are unrelated to
  this audit. Every CSC, DAAD, and Erasmus run inspected recorded zero model calls and zero cost.

## Repository and runtime baseline

### Git

- Branch: `codex/phase1b2-crawlee-secure-bridge`
- Commit: `4635c998ff8dd8877ea67f511461c81d38951fcb`
- Worktree at audit start: 24 modified tracked files and 6 untracked files.
- Modified tracked files:
  `.env.example`, `Dockerfile`, `app/modules/catalogue_ingestion/service.py`,
  `app/modules/opportunities/repository.py`, `app/modules/opportunities/routes.py`,
  `app/modules/opportunities/schemas.py`, `app/modules/opportunities/service.py`,
  `app/modules/opportunities/source_monitor.py`, `compose.yaml`,
  `data/seed/verified_opportunities.json`, `frontend/src/App.tsx`,
  `frontend/src/features/admin/AdminPage.tsx`, `frontend/src/features/admin/admin.test.ts`,
  `frontend/src/features/admin/admin.ts`, `frontend/src/features/admin/types.ts`,
  `frontend/src/features/catalogue/OpportunityDetailPage.tsx`,
  `frontend/src/features/catalogue/catalogue.ts`, `frontend/src/features/catalogue/types.ts`,
  `frontend/src/styles.css`, `tests/test_browser_e2e.py`, `tests/test_catalogue_ingestion.py`,
  `tests/test_frontend.py`, `tests/test_opportunities.py`, and `tests/test_source_monitor.py`.
- Untracked files at audit start:
  `data/seed/private_priority_scholarship_candidates.v1.json`,
  `docs/private-catalogue-seed-audit-2026-08-24.md`,
  `docs/terra-5.6-catalogue-completion-plan.md`,
  `frontend/src/features/admin/AdminAcquiredReviewPage.tsx`,
  `frontend/src/features/admin/AdminReviewPage.tsx`, and
  `frontend/src/features/catalogue/ScholarshipDetailView.tsx`.

The current worktree, not only `HEAD`, was treated as authoritative. Several important review and
multi-source changes exist only in that dirty worktree.

### Compose and migrations

- Running services at inspection: `db` healthy, `api` healthy, and `migrate` exited successfully.
- Default Compose service graph: `db`, `migrate`, `api`.
- Optional profiles define `source-monitor`, `reminder-worker`, `retention-worker`,
  `document-worker`, `document-converter`, and `clamav`.
- There is no dedicated `catalogue-worker` service or profile and no Compose command invoking
  `app.cli.process_catalogue_ingestion_runs`.
- Database Alembic revision: `20260824_0053`.
- Repository Alembic head, verified inside the API container: `20260824_0053 (head)`.
- A direct host `uv run alembic heads` check was blocked by Windows Application Control (OS error
  4551); the container check is the successful replacement evidence.

### Effective catalogue flags in the running API

All expensive or autonomous paths are off:

| Setting | Effective value |
|---|---:|
| AI ingestion / provider / model | `false` / `unavailable` / `unconfigured` |
| Web discovery | `false` |
| Bounded crawling | `false` |
| Crawlee static scheduling | `false` |
| Browser fetching | `false` |
| Document conversion / OCR | `false` / `false` |
| Source routing | `false` |
| Scheduled ingestion | `false` |
| Graph reads / writes | `false` / `false` |

The effective run ceilings are 500 candidates, 3 pages per candidate, 500 model calls, 80,000
input characters, 6,000 output tokens, and USD 50 estimated cost. Both configured token prices are
zero, which is safe only because AI ingestion is disabled. There is no `.env` file in the repository
root.

## Database truth at inspection

| Record | Count / state |
|---|---:|
| Ingestion runs | 14, all `completed` |
| Candidates | 62 |
| Candidate statuses | 60 `needs_review`; 2 `validation_failed` |
| Candidate sources | 62 |
| Candidate source statuses | 32 `fetched`; 22 `manual_review`; 8 `discovered` |
| Immutable source artifacts | 30 |
| Evidence blocks | 207 |
| Extraction attempts | 2 historical Chevening failures |
| Source-routing decisions | 0 |
| Review proposals / decisions | 0 / 0 |
| Opportunities | 50, all `active` |
| Opportunity source statuses | 72, all `officially_verified` |
| Pending duplicate suggestions | 26 |

All 50 active opportunities are marked incomplete. Among them, 42 have neither a deadline nor a
rolling state, 49 have unknown tuition coverage, 49 have unknown stipend coverage, 34 have no
minimum academic requirement, and 34 have no language/test requirement. The current public-query
predicate returns all 50 because it only requires an active opportunity and a source labelled
officially verified, while rejecting a small set of source statuses.

## Candidate lifecycle trace

1. `app/cli/ingest_catalogue_seeds.py:23-83` accepts one local/private-Blob seed, one direct URL
   bundle, or one resume ID, then calls `CatalogueIngestionService` outside an HTTP request.
2. `CatalogueIngestionService.create_run_from_source` (`service.py:198-238`) loads and parses seeds,
   freezes budgets into a durable run, and creates idempotent candidates.
3. `create_run_from_url` (`service.py:240-351`) validates HTTPS URLs, enforces the page ceiling,
   creates one candidate, and stores primary/supporting source leads. The admin route creates the run
   but does not process it synchronously.
4. `process_run` / `process_next_runs` / `process_claimed_run` (`service.py:353-510`) use durable run
   and candidate leases. `app/cli/process_catalogue_ingestion_runs.py` is the queue worker entry
   point, but Compose does not currently run it.
5. Seed candidates use `SeedUrlDiscoveryProvider`, deterministic official-source classification,
   `SafeSourceFetcher`, optional bounded crawling, immutable source artifacts, and evidence blocks
   (`service.py:530-647`). In `candidate_only`, they deliberately stop in `needs_review` with
   `candidate_only_complete` (`service.py:649-654`).
6. The seed-source extraction path still sends only the selected root artifact to the legacy
   whole-record extractor (`service.py:658-760`). Crawled child sources are persisted but do not
   contribute claims on this path.
7. Direct URL bundles use the newer per-artifact, per-objective claim path
   (`service.py:1171-1430`). It validates exact spans, records one attempt per content
   hash/objective/schema/prompt/provider/model, resolves same-scope claims deterministically, and
   blocks conflicts or incomplete objectives.
8. Source routing can reduce work by source role and stop cycle mixing, but it is disabled and the
   database has no routing decisions. Without routing, every objective is attempted for every
   artifact.
9. A complete legacy `OpportunityCreate` proposal can be staged as a draft. A complete claim-graph
   proposal is materialized only when it matches the MEXT-specific compatibility condition;
   otherwise submission records a proposal/decision but creates no opportunity
   (`service.py:1036-1117`, `graph_materializer.py:54-104`).
10. Existing opportunity review actions are separate from candidate submission. The publish and
    resolve-conflict transitions set the selected source to `officially_verified` and the
    opportunity to `active` directly (`opportunities/service.py:1204-1225`). There is no
    transactional completeness evaluation.
11. Public list/detail loading requires only `active` plus an officially verified official source
    and absence of a disqualifying official-source status
    (`opportunities/repository.py:918-1035`). Freshness is required only for `open_now`, not for all
    public results.

## Reusable implementation

The following components are real implementation and should be retained:

- durable run/candidate/source/attempt ledgers, worker leases, retry state, checkpoints, and
  idempotency in `models.py`, `repository.py`, and `service.py`;
- local/private-Blob seed loading and bounded JSON/CSV/text/PDF parsing in `seed_parser.py`;
- the SSRF-, redirect-, DNS-, peer-, robots-, MIME-, decompression-, size-, and low-information-safe
  fetch boundary in `opportunities/source_monitor.py`;
- bounded same-owner crawling and canonical URL/content deduplication in `crawler.py`;
- the Crawlee static scheduler adapter, which deliberately delegates every request to the safe
  fetcher, in `crawlee_static_acquirer.py`;
- immutable `CatalogueSourceArtifact` and `CatalogueEvidenceBlock` storage, including final URL,
  hashes, retrieval metadata, parser version, normalized text, and exact block locators;
- text-PDF parsing plus bounded filesystem transport to an offline Docling worker in
  `document_conversion.py`, `document_conversion_transport.py`, and
  `document_conversion_worker.py`;
- strict Azure structured-output providers, fake providers, bounded retries, usage capture, and
  content/objective cache keys in `provider.py` and `claim_provider.py`;
- per-objective claim types, exact excerpt/offset validation, deterministic resolution, and
  fail-closed conflict handling in `claim_schemas.py` and `claim_resolution.py`;
- versioned deterministic source-role/cycle routing in `source_routing.py`;
- existing opportunity families, cycles, graph primitives, fuzzy duplicate suggestions, review
  APIs, step-up authentication, audit records, and source monitoring;
- the shared public/admin scholarship detail view and the acquired-candidate evidence projection in
  the dirty frontend worktree.

## Production paths, gated paths, and placeholders

| Area | Current truth |
|---|---|
| Static safe fetch | Production implementation and used by ingestion/monitoring. |
| Seed URL discovery | Production deterministic lead adapter; no autonomous discovery. |
| Azure web discovery | Provider implementation exists, but it is not part of the default ingestion path and is disabled. |
| Bounded crawler | Implemented and tested, but disabled in the running API. |
| Crawlee | Implemented only as a one-request static scheduler around `SafeSourceFetcher`; disabled. It is not browser acquisition. |
| PDF normalization | Text PDF works locally. Layout/OCR transport exists but is disabled; no running converter service was observed. |
| Azure extraction | Implemented but disabled/unconfigured; historical calls prove only the legacy provider path and failed validation. |
| Multi-source extraction | Implemented for direct URL bundles in the dirty worktree; seed ingestion still uses one root artifact. |
| Source routing | Implemented behind a flag; disabled, with zero durable decisions in the database. |
| Generic graph materialization | Missing. The only graph materializer is `MextGraphMaterializer`, with hard-coded MEXT family/country/timezone assumptions. |
| Completeness/publication readiness | Design documents and a compatibility column exist; no executable `PublicationReadiness` policy exists. |
| Catalogue worker | CLI exists; dedicated Compose worker/profile and preflight do not. |
| Browser/login/CAPTCHA acquisition | Deliberately unavailable/fail-closed. |

## CSC, DAAD, and Erasmus audit

The acquisition ledger and legacy active catalogue are separate truth domains. Acquired artifacts
have not been resolved into or linked as field evidence for the corresponding active records.

### Acquisition state

| Family | Best current acquisition evidence | Pipeline state |
|---|---|---|
| Chinese Government Scholarship (CSC) | The main seed URL failed closed on unreachable robots. A separate official Chinese Embassy check acquired 1 immutable artifact / 2 evidence blocks (hash `7b1d0d684a60…`). | `needs_review`; `candidate_only_complete` only on the alternative evidence-check candidate; zero claims/model calls. |
| DAAD EPOS | Official DAAD database page acquired as 1 artifact / 10 blocks (hash `aaf210facdbc…`). | `needs_review`, `candidate_only_complete`; zero claims/model calls. |
| Erasmus Mundus | Official European Commission overview acquired as 1 artifact / 4 blocks (hash `da2e3d47d6f…`). | `needs_review`, `candidate_only_complete`; zero claims/model calls. |

No pilot candidate has a proposal, review decision, opportunity ID, resolved claim set, source-routing
decision, conflict result, or completeness result.

### Mandatory-field gaps in the legacy active records

All three records have provider/country/name strings and application links, but none has field-level
source excerpts. Their catalogue source rows have null content hashes, `officiality_status=unresolved`,
`source_owner_type=unknown`, and zero `source_excerpts`. Each has zero structured eligibility rules
and zero `opportunity_cycles`.

| Requirement | CSC | DAAD EPOS | Erasmus Mundus |
|---|---|---|---|
| Identity/family | Family string exists; `legacy_unreviewed`; family has multiple active variants but no resolved route graph. | Family ID incorrectly embeds `2027-28`; `legacy_unreviewed`. | Umbrella family only; individual joint-master route/programme is not separated; `legacy_unreviewed`. |
| Degree and route scope | Masters row exists, plus separately seeded degree/university variants; explicit embassy/university route evidence is absent. | One umbrella masters row; course routes and course-specific scope are absent. | One umbrella masters row; consortium/programme route is absent. |
| Current cycle | `cycle_id=2027`, but no current-cycle entity or field evidence. | `cycle_id=2027`, but the record name says 2027/28 and no cycle entity/evidence exists. | `cycle_id=2027`, but no cycle entity/evidence exists. |
| Deadline semantic state | Missing; not marked rolling. | Missing; prose says deadlines vary by course, but no typed/evidenced rule. | Missing; not marked rolling and no programme-specific rule. |
| Application method/URL | Values exist but lack field-level evidence and route scope. | Values exist but lack field-level evidence and course scope. | Values exist but lack field-level evidence and programme scope. |
| Tuition | `unknown`; broad source prose is not field evidence. | `unknown`. | `unknown`. |
| Stipend | `unknown` despite a stored CNY 3,000 amount; no evidence/frequency binding. | `unknown` despite a stored EUR 992 amount; no evidence/frequency binding. | `unknown` despite a stored EUR 1,400 amount; no evidence/frequency binding. |
| Computed funding | `unknown`. | `partial`, but component statuses are unknown, so the classification is not proven. | `unknown`. |
| Nationality/geography | Prose exists; no structured/evidenced eligibility rule. | Prose exists; no structured/evidenced eligibility rule or country-list scope. | Prose exists; no structured/evidenced eligibility rule. |
| Academic requirement | Generic prose exists; no field evidence or route-level variation state. | Generic prose exists; no course-scoped evidence. | Generic prose exists; no programme-scoped evidence. |
| Language/test | Generic prose exists; no evidence or accepted-exception state. | Generic prose exists; no course-scoped evidence. | Generic prose exists; no programme-scoped evidence. |
| Required documents | Lists exist but have no source/excerpt/scope binding. | Generic list exists but not the course-defined route it refers to. | Generic list exists but not the programme-defined route it refers to. |
| Fresh official artifacts | Acquisition artifact exists separately, but catalogue sources are unhashed/unowned and not linked to it. | Same. | Same. |
| Conflict/duplicate | Two pending duplicate suggestions block identity; route boundaries unresolved. | No pending duplicate suggestion, but course-route identity is unresolved. | No pending duplicate suggestion, but programme-route identity is unresolved. |

Therefore none of the three records satisfies any reasonable reading of
`review_ready_complete`, even where display values happen to be non-null.

## Broken wiring and missing code

1. **Publication can bypass completeness.** The React page disables Publish when its locally derived
   high-severity issue count is non-zero, but a direct API call reaches `_apply_review_transition`
   and activates the record without a backend completeness check. The public query likewise ignores
   the incomplete marker and most required evidence.
2. **There is no single versioned `PublicationReadiness` result.** Existing data-quality warnings are
   display-oriented and incomplete; they do not return the plan's reason-coded contract, do not
   validate every mandatory field's evidence/scope, and do not transactionally own publication.
3. **The current active catalogue violates the intended truth boundary.** All 50 active records are
   marked incomplete, yet all 50 pass the current public filter. Source labels are treated as proof
   despite null hashes, unresolved ownership, and absent field-level excerpts.
4. **Seed and direct ingestion diverge.** Only direct bundles use per-artifact/objective claim
   extraction. The private priority seed—the intended bulk input—still selects one official root and
   invokes the legacy single-source extractor.
5. **Multi-source materialization is programme-specific.** Complete non-MEXT claim resolutions are
   parked as candidate proposals and cannot become route/cycle-aware draft opportunity graphs.
6. **Completeness checks do not implement the plan's field contract.** `detail_completeness_errors`
   checks structural claim categories and objective coverage, not the 15 mandatory publication
   fields, semantic states, freshness, verified ownership, or unresolved duplicate status.
7. **Typed semantic absence is incomplete.** Funding has explicit status enums and opportunity
   cycles have `is_rolling`, but there is no uniform supported/not-applicable/varies-by-country/
   not-yet-announced fact state with evidence.
8. **Identity keys are insufficient for the required route model.** Candidate idempotency includes
   seed name/provider/university/country/cycle/intake/URL, while the opportunity canonical check uses
   provider/family/cycle/degree/funding. Neither expresses route/course/host/destination as the plan
   requires. Fuzzy suggestions remain review-only, which is correct.
9. **Worker/runtime wiring is incomplete.** A durable queue CLI exists, but no dedicated local
   catalogue worker or preflight command is wired into Compose. A created HTTP run will remain queued
   unless an operator separately invokes the worker CLI.
10. **The pilot evidence pack is missing.** There is no three-family gold fixture containing legally
    usable official-source excerpts and expected field-to-source mappings. Existing CSC fixtures
    exercise identity/relationship safety, not end-to-end CSC/DAAD/Erasmus completeness.
11. **The admin UI is useful but not authoritative.** It reuses the detail page and shows sources,
    gaps, claims, and family variants, but readiness is derived in React from legacy issue severity;
    it lacks the backend policy result, source freshness summary, objective filters, and a complete
    duplicate-resolution comparison.
12. **No 500-route evidence exists.** There are 62 staging candidates, zero ready-for-review
    candidates, zero review proposals, and only 50 legacy active/incomplete opportunities.

## Obsolete or unsafe assumptions

- `docs/current-product-state.md` accurately describes the architecture, but its broad
  “source-reviewed catalogue” statement must not be interpreted as proof that current records meet
  the new publication standard. Database evidence contradicts that stronger interpretation.
- `docs/catalogue-ingestion-pipeline.md` says multi-source text is not aggregated and extraction uses
  only a root source. That remains true for seed-source ingestion, but is now incomplete as a global
  description because the dirty worktree has a direct-bundle per-artifact/objective claim path.
- A source row labelled `officially_verified` is not enough to support a public record. The three
  pilot rows demonstrate why: the label coexists with null hashes, unresolved ownership, no field
  excerpts, and mandatory unknowns.
- `publication_completeness` is currently a stored compatibility label, not an enforced policy
  result. It cannot be trusted as a gate until the evaluator and transactional integration exist.
- A completed ingestion run means processing terminated, not that its candidates are complete. All
  14 runs are completed while no candidate is review-ready.
- Historical `verified_*` seed filenames and prose excerpts are not current field-level proof.

## Smallest safe implementation sequence

This sequence preserves the existing architecture and puts the public safety boundary first:

1. **Phase 1A — freeze fact/readiness contracts.** Implement a versioned backend
   `PublicationReadiness` evaluator over explicit scoped facts/evidence. Reconcile it with ADR 0008,
   but make the plan's 15 mandatory requirements the minimum gate. Add reason codes, counts,
   warnings, evaluated time, policy version, and typed semantic states.
2. **Phase 1B — close publication bypasses.** Call the evaluator while locking the opportunity in
   the publish transaction; make public list/detail queries require current readiness; queue existing
   active failures for remediation without deleting them. Add direct-API and public-leakage tests
   before changing any pilot data.
3. **Phase 1C — create the private gold pack.** Capture one legally usable official bundle for one
   CSC route, one DAAD EPOS course, and one Erasmus Mundus joint master. Commit only synthetic/minimal
   derived fixtures if redistribution is uncertain. Define exact expected facts, scopes, evidence
   spans, semantic absences, conflicts, and identity keys.
4. **Phase 2 — converge acquisition paths.** Make both seed and direct inputs produce the same
   bounded official source bundle and explicit acquisition-gap result. Keep `SafeSourceFetcher` as
   the sole network boundary and keep browser/OCR off unless separately proved.
5. **Phase 3 — finish generic multi-source extraction/resolution.** Use per-artifact/objective
   claims for seed runs, atomic pre-call budget reservation, deterministic scope precedence, and the
   gold pack. Keep Azure disabled while fake/captured outputs are debugged.
6. **Phase 4 — generalize materialization and identity.** Replace MEXT-only assumptions with the
   existing graph primitives; include family, route/course, host, destination, degree, and cycle in
   deterministic identity. Preserve history and hold fuzzy matches for review.
7. **Phases 5–6 — consume backend readiness and wire local operations.** Make the admin UI render the
   backend result, then add the dedicated Compose worker, preflight, kill switch, and durable
   candidate/objective resume proof.
8. **Phase 7 onward — require owner approval.** Only after all prior gates pass should one bounded
   DAAD live extraction be proposed. CSC/Erasmus follow only after its report is approved; batch
   expansion follows approval of all three.

## Verification performed

Read-only/runtime checks:

- `git status --short --branch`, `git branch --show-current`, `git rev-parse HEAD`
- complete reads of `docs/terra-5.6-catalogue-completion-plan.md`,
  `docs/current-product-state.md`, and `docs/catalogue-ingestion-pipeline.md`
- source and migration inventory, targeted code-path inspection, and dirty diff summary
- `docker compose ps --all`
- `docker compose config --services`
- container `alembic heads`
- read-only PostgreSQL counts and CSC/DAAD/Erasmus evidence/gap queries
- running-container catalogue flag inspection

Focused no-network tests:

```text
uv run python -m pytest -q \
  tests/test_private_priority_seed.py \
  tests/test_catalogue_ingestion.py::test_direct_source_bundle_stages_expanded_claims_from_three_explicit_sources \
  tests/test_catalogue_ingestion.py::test_expanded_direct_url_stays_in_cited_staging_until_graph_support_exists \
  tests/test_catalogue_ingestion.py::test_source_routing_blocks_ambiguous_artifact_without_model_calls \
  tests/test_opportunities.py::test_admin_review_action_publish_and_flag_conflict_control_public_visibility \
  tests/test_opportunities.py::test_public_family_excludes_draft_or_unverified_routes
```

Result: 6 passed. One Starlette/httpx deprecation warning was emitted.

Not run in Phase 0:

- full Ruff, backend, frontend, build, browser, and Compose-up regressions;
- live official-source acquisition;
- document-converter runtime proof;
- PostgreSQL concurrency suites beyond the read-only ledger inspection;
- any Azure/OpenAI extraction, web search, or paid capability probe;
- any publish/remediation mutation.

These are intentionally deferred to their requirement-matched phases and must not be inferred from
the six focused test passes.

## Phase 0 exit gate

The audit explains why the three records are incomplete and identifies the smallest safe change
set. The Phase 0 exit gate therefore passes. Phase 1 has **not** started and requires owner approval.
