# Terra Detailed Implementation Plan

Prepared: 24 August 2026  
Repository baseline: `codex/phase1b2-crawlee-secure-bridge` at `f6b3e45dc97c75c7886118d6b972a090ff56bd28`  
Primary objective: finish a production-shaped, review-only extraction layer next week and reach a safe live release as quickly as the evidence permits.

## 1. Mission and non-negotiable outcome

Terra should deliver the smallest complete vertical slice that turns an official scholarship URL into an idempotent, reviewable, cited, scoped scholarship proposal without automatic publication.

The definition of “extraction layer finished” is:

`official input -> durable job -> safe acquisition -> canonical evidence blocks -> source/cycle classification -> objective-routed extraction -> deterministic resolution -> bundle completeness -> review proposal`

It is **not** enough for the crawler to download pages or for the model to emit JSON. The result must remain reproducible, exact-evidence grounded, scope-aware and safely resumable.

The public launch path is:

`review proposal -> human approval -> universal graph transaction -> explicit publication -> monitored public projection`

That second path must not be simulated through the current MEXT-specific materializer.

## 2. Ground rules for Terra

Terra must follow these rules on every implementation task:

1. Read the referenced production code and tests before changing behavior.
2. Treat scraped HTML, documents and model output as untrusted data.
3. Preserve `SafeSourceFetcher` as the only authorized network policy boundary.
4. Keep new components behind internal interfaces: `EvidenceAcquirer`, `DocumentConverter`, `SourceRoleClassifier`, `ClaimExtractor`, `ClaimResolver`, `CompletenessEvaluator`, `GraphMaterializer` and `PublicationService`.
5. Do not enable automatic publication.
6. Never repair missing/conflicting facts from model memory.
7. Prefer additive migrations and backwards-compatible response changes.
8. Make every worker operation idempotent and lease/fencing aware.
9. Add deterministic tests before or with implementation; do not rely on live prompt demos.
10. Record exact commands/results and update the implementation log after each slice.
11. Keep commits narrow enough to revert one slice without reverting unrelated work.
12. Stop a release when a required gate is not evidenced; report the blocker rather than weakening the gate.

## 3. Honest delivery forecast

### Achievable next week

A **review-only extraction release candidate** for MEXT and Open Doors with:

- queued/idempotent work;
- secure Crawlee static acquisition parity;
- canonical HTML/PDF evidence blocks;
- Docling adapter for protected complex documents;
- deterministic browser/OCR decision contracts, with fallback enabled only if isolation is ready;
- source-role/cycle classification and objective routing;
- exact block citations and bundle-level completeness;
- operator-visible run/proposal status;
- protected fixture and bounded live dry-run evidence.

### Not safe to promise in one week

- 500 fully reviewed public records;
- universal public graph approval if the schema/migration has not passed review;
- five-family portability proof;
- production Azure deployment, rollback, restore and soak evidence;
- a remote student assistant or Document Lab AI provider.

The fastest responsible launch is therefore staged:

1. end of next week: internal/staging extraction RC;
2. next: limited closed-beta acquisition/review after P0 reliability fixes and MEXT/Open Doors/CSC gates;
3. public catalogue: universal graph + five-family proof + 500 reviewed records + environment evidence.

## 4. Critical-path backlog

### P0-A - Freeze contracts and baseline

Deliverables:

- Architecture decision records for evidence blocks, source roles/cycles, job leases and publication separation.
- Captured MEXT and Open Doors HTML/PDF fixtures with hashes.
- Baseline metrics: calls, tokens, accepted/rejected claims, runtime and cost.
- A regression manifest for the current SafeSourceFetcher security invariants.

Code/docs likely involved:

- `docs/decisions/`
- `tests/fixtures/catalogue_acquisition/`
- `tests/test_evidence_acquirer.py`
- `tests/test_catalogue_ingestion.py`
- `tests/test_complete_acquisition_contract.py`

Exit gate:

- Existing non-browser suite and Ruff pass.
- Fixture hashes and expected claim outcomes are review-approved.
- No production behavior changes yet.

### P0-B - Durable queued ingestion

Problem addressed: direct URL processing defaults to synchronous work and current jobs can be stranded.

Deliverables:

- Change new ingestion requests to enqueue by default; retain an explicit test/admin-only synchronous option if required.
- Add/normalize job fields: state, stage, attempts, `claimed_at`, `claimed_until`, lease token, last error, retry class and dead-letter timestamp.
- Claim with `FOR UPDATE SKIP LOCKED`.
- Fence completion using the lease token so an expired worker cannot overwrite a new owner.
- Add retry/backoff and operator-visible dead-letter state.
- Add `GET run/status` projection for the admin client.

Likely code:

- `app/modules/catalogue_ingestion/models.py`
- `repository.py`
- `service.py`
- `routes.py`
- `schemas.py`
- a new/updated worker CLI under `app/cli/`
- Alembic migration if the existing candidate lease fields are insufficient.

Acceptance tests:

- duplicate enqueue with the same idempotency key creates one logical run;
- expired lease is reclaimed;
- stale worker completion is rejected;
- transient failure retries; permanent failure dead-letters;
- restart resumes at the last successful objective;
- API returns quickly while worker executes separately.

### P0-C - Finish secure Crawlee static bridge

Problem addressed: current adapter preserves safety but does not deliver full Crawlee orchestration.

Deliverables:

- Custom Crawlee HTTP adapter/client whose every request invokes `SafeSourceFetcher`.
- Request queue integration with canonical URL dedupe and hard page/depth/byte/time budgets.
- Per-domain throttling shared across workers at the chosen launch scale.
- Artifact parity against the legacy bounded crawler.
- Feature-gated rollout and instant fallback to `LegacySafeEvidenceAcquirer`.

Likely code:

- `evidence_acquirer.py`
- `crawlee_static_acquirer.py`
- `safe_multi_url_session.py`
- `crawler.py`
- `url_policy.py`
- `tests/test_crawlee_static_acquirer.py`
- `tests/test_bounded_crawler_*`

Acceptance tests:

- zero direct Crawlee stock network calls;
- redirect/DNS/peer-address/robots/MIME/byte tests pass unchanged;
- MEXT static fixtures produce equivalent accepted artifacts and links;
- deterministic duplicate URL suppression;
- queue cancellation and hard budget stop.

Rollback:

- disable Crawlee feature gate and route new jobs to the legacy acquirer; stored artifacts remain compatible.

### P0-D - Canonical evidence blocks

Problem addressed: flattened text loses hierarchy and model offsets are brittle.

Deliverables:

- Versioned `EvidenceBlock` contract and persistence.
- Deterministic block IDs derived from artifact hash + parser version + structural locator.
- HTML block parser for headings, paragraphs, list items, table rows, key/value pairs and form instructions.
- Fields: `artifact_id`, `block_id`, `block_type`, `structural_path`, `verbatim_text`, normalized offsets, `scope_hint`, `parser_version`.
- Reprocessing creates a new parser-version result without mutating prior citations.
- Exact excerpt offsets are computed inside blocks after the model selects evidence; model-provided offsets become diagnostic only.

Likely code:

- new `evidence_blocks.py` or equivalent in `catalogue_ingestion`
- `evidence.py`
- `models.py`
- `claim_schemas.py`
- `claim_resolution.py`
- additive Alembic migration

Acceptance tests:

- same artifact/parser produces identical block IDs;
- DOM reorder changes only affected block identities;
- table/list hierarchy survives normalization;
- citation can render exact text and location without the model;
- old artifact versions remain inspectable.

### P0-E - Layout-aware document conversion

Problem addressed: pypdf flattened text cannot preserve decision-critical tables and reading order.

Deliverables:

- `DocumentConverter` protocol.
- pypdf preflight for metadata/text sufficiency.
- Docling adapter for PDF/DOCX/PPTX/permitted images.
- Canonical page/region/table/list blocks.
- OCR gate only for pages below a measured text threshold.
- hard file/page/expanded-size/runtime budgets and isolated conversion worker.
- parser/model version recorded on each block set.

Acceptance tests:

- MEXT overview seven-column table retains cell coordinates and row/column association;
- guideline numbered document lists preserve order and nesting;
- scanned-page fixture invokes OCR only when permitted;
- malformed/oversized files fail closed with a stable error code;
- rerun with unchanged artifact/parser creates no duplicate blocks.

Rollback:

- keep pypdf fallback for simple documents; mark complex documents `manual_review` rather than using flattened data.

### P0-F - Source role, cycle classification and objective routing

Problem addressed: every objective can be attempted on every source, and multiple cycles can mix.

Deliverables:

- `SourceRoleClassifier` output: overview, cycle guideline, route, degree track, institution, programme, funding, documents, deadline, portal, result notice or unknown.
- cycle state: current, upcoming, historical, evergreen or ambiguous.
- deterministic/allowlisted relationship for cross-domain embassy/university/portal expansion.
- objective-routing matrix keyed by source role.
- unresolved-completeness query so only missing objectives run.
- explicit manual-review state for ambiguous cycle/source role.

Acceptance tests:

- Open Doors old/current cycle content never merges;
- subject areas are not treated as programmes by name alone;
- tests/stages are not treated as required documents;
- funding source never receives document-count objective;
- unchanged successful objective is reused;
- hard per-run model-call and cost budgets stop safely.

### P0-G - Scoped resolver and bundle-level completeness

Problem addressed: page-level richness does not prove complete scholarship coverage.

Deliverables:

- Canonical keys/scopes for scholarship, cycle, degree track, subject, academic programme, application route, institution, requirement set, document, funding, event and step.
- Authority tiers T0 provider, T1 route, T2 institution, T3 official portal, plus untrusted lead.
- Inheritance lineage and scoped overrides.
- Completeness states: `resolved`, `unknown`, `delegated`, `not_applicable`, `partial`, `conflict`, `failed`.
- Mandatory objective matrix per applicable scope.
- Review proposal that prioritizes conflicts, rejected claims and missing mandatory objectives.

Acceptance tests:

- embassy deadline does not populate university route;
- historical date does not satisfy current-cycle deadline;
- delegated local deadline remains delegated until local source is acquired;
- programme-scoped document/funding facts do not collapse into one global key;
- no candidate is `ready_for_review` with a mandatory partial/conflict/failed state;
- exact block evidence exists for every accepted mandatory claim.

### P0-H - Operator projection and observability

Deliverables:

- Admin run view: stage, lease, retries, source/artifact hashes, browser/OCR decisions, objective coverage, token/cost totals and failure reason.
- Proposal view: scoped facts beside exact block evidence; conflicts and missing requirements first.
- Metrics by discovery, acquisition, parsing, extraction, resolution and review stage.
- Alerts for queue age, lease expiry, dead-letter count, provider throttling, citation failure and cost budget.
- Capability-aware readiness for enabled extraction dependencies.

Exit gate:

- an operator can explain why a run stopped and resume/retry it without database intervention;
- no logs include secrets or private student content.

## 5. Seven-day execution schedule

The schedule assumes one focused implementation stream with Terra continuously integrating and a human reviewer available for schema/security decisions. If staffing permits, tests/fixtures and UI can run in parallel, but the dependency order must remain.

### Day 1 - Baseline and durable job contract

- Freeze commit, fixture hashes and current metrics.
- Write/approve ADRs.
- Implement queued-by-default ingestion and idempotency key.
- Add lease token/retry/dead-letter contract.
- Add concurrency tests first.

Day exit gate: duplicate/expired/stale worker cases pass on PostgreSQL; API no longer performs a default long run inline.

### Day 2 - Secure Crawlee parity

- Implement the safe Crawlee HTTP bridge.
- Wire request queue, dedupe, budgets and per-domain pacing.
- Run legacy-vs-Crawlee fixture comparison.
- Run all SSRF/redirect/robots/MIME/byte tests.

Day exit gate: MEXT static artifacts are equivalent and no request bypasses `SafeSourceFetcher`.

### Day 3 - Evidence blocks and document adapter

- Add block schema/migration and deterministic HTML parser.
- Implement `DocumentConverter` and Docling adapter behind a feature gate.
- Add MEXT table/list fixtures and OCR insufficiency gate.

Day exit gate: exact citations render from stable block IDs; complex MEXT tables preserve structure.

### Day 4 - Classifier and objective router

- Add source role and cycle classification.
- Add objective-routing matrix and unresolved-completeness selection.
- Convert orchestration from broad source x all-objective loops to durable routed objective jobs.
- Verify cache reuse and budget stops.

Day exit gate: Open Doors fixture has no cross-cycle merge; model-call count drops relative to baseline without losing required coverage.

### Day 5 - Resolver and completeness

- Harden universal entity keys and scoped inheritance/override.
- Implement bundle-level completeness states.
- Build conflict/missing-first review projection.
- Run MEXT and Open Doors protected suites and fix deterministic defects, not scholarship-specific prompt hacks.

Day exit gate: both families produce truthful ready/review or blocked states with exact reasons; zero invented evidence.

### Day 6 - Reliability and operations

- Fix beta expiry, atomic profile updates, assistant quota reservation and community public-ID moderation.
- Add document deletion jobs and abandoned-job reaper.
- Fence source-monitor completion.
- Add aggregate readiness, queue metrics and dead-letter operations.

Day exit gate: all reproduced P0 defects have regression tests; worker kill/retry exercise passes.

### Day 7 - Release-candidate proof

- Run Ruff, backend suite, PostgreSQL/Redis integration, frontend test/typecheck/build and migration checks.
- Run bounded live MEXT/Open Doors dry runs with no publication.
- Compare cost, calls, citations and reviewer corrections with baseline.
- Deploy to staging if environment approvals exist.
- Execute smoke, rollback and job-resume drills.
- Produce a signed go/no-go record.

Day exit gate: review-only extraction RC is accepted. Any failed mandatory gate produces a no-go with a bounded remediation list.

## 6. After-next-week launch sequence

### Phase 2 - Universal graph approval (target: next 3-5 engineering days)

Deliverables:

- additive Alembic schema for offering cycles, degree tracks, subjects, programmes, routes, requirement sets, documents, funding, events, steps, institution participation, evidence links and inheritance lineage;
- review proposal diff;
- atomic approval transaction;
- separate explicit publication transaction;
- universal detail API projection;
- legacy compatibility read during migration.

Exit gate: expanded MEXT/Open Doors proposals materialize without projection loss; failed approval rolls back graph and evidence links together.

### Phase 3 - Three-family operational gate (target: 3-5 days)

- Add CSC captured fixtures and bounded live proof.
- Validate identity dedupe, central/provider/university ownership and institution collections.
- Measure idempotency, cost and reviewer corrections.

Exit gate: MEXT, Open Doors and CSC pass mandatory invariants. This is the minimum gate before beginning a controlled catalogue batch.

### Phase 4 - Five-family portability and closed beta (target: 1 week)

- Add GKS or DAAD EPOS and Erasmus Mundus fixtures.
- Complete universal detail UI with degree/route selectors and evidence drawer.
- Add PostgreSQL FTS for approved evidence; defer pgvector until lexical baseline is measured.
- Run staging soak, restore and rollback proof.

Exit gate: all five families pass, closed beta is operable and no review-only data leaks into public reads.

### Phase 5 - 500-record launch

- Process records in family cohorts with hard budgets.
- Review every record or material change.
- Track correction taxonomy and pause families with rising false-ready rates.
- Label current cycle and freshness state.
- Enable source monitoring and event-relative refresh.
- Publish only after release checklist approval.

Exit gate: 500 reviewed, current-cycle-labelled, source-monitored, exportable records; backup/restore, rollback, alerting and quality dashboards have execution evidence.

## 7. Universal graph migration plan

### Additive schema first

Do not mutate/drop legacy opportunity tables during the first release. Add normalized tables and explicit evidence/proposal version relationships. Backfill only approved compatible records.

### Dual-read, single-write transition

1. New approval writes the universal graph.
2. Public API reads the graph only behind a verified feature gate.
3. Compare graph and legacy projections for compatible records.
4. Switch reads after parity evidence.
5. Disable legacy writes.
6. Remove legacy compatibility only in a later migration with rollback plan.

### Transaction rule

Approval must atomically write:

- graph version;
- entity/fact rows;
- evidence links;
- inheritance lineage;
- review decision/audit record;
- candidate approved state.

Publication is a separate transaction that requires an approved graph version and records a rollback identifier.

## 8. Reliability remediation workstream

These items can proceed alongside extraction work but block live release:

| ID | Required change | Acceptance criterion |
| --- | --- | --- |
| R-01 | Central transaction for beta expiry/user deactivation | Every expired reserved invite denies the user; repeat run is idempotent |
| R-02 | Atomic profile conditional update | Two writers with version N yield one success and one 409 |
| R-03 | Durable document deletion jobs | Storage failure retries; terminal failure is visible; no orphan is silently forgotten |
| R-04 | Job lease reaper | Killed worker job is reclaimed or dead-lettered |
| R-05 | Transport/process cancellation | Timed-out provider cannot keep consuming uncontrolled work |
| R-06 | Atomic assistant quota reservation | Concurrent limit-one test yields one admitted request |
| R-07 | Coherent answer/packet retention | No payload survives beyond declared policy without documented legal/audit reason |
| R-08 | Public community member ID moderation | Suspend/reinstate works with API-exposed member ID only |
| R-09 | Fenced source-monitor transaction | Check, freshness, next schedule and lease clear commit atomically |

## 9. Test commands and release evidence

Terra should use repository-native commands after confirming tool availability. Record the exact command, environment and result.

Minimum code checks:

```text
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
git diff --check
```

Required environment-backed checks:

```text
PostgreSQL migration tests and tenant-RLS tests
Redis rate-limit integration tests
Crawlee adapter parity/integration tests
Frontend unit tests, TypeScript check and production build
Browser E2E for admin ingestion/review and public detail
```

Protected live evaluation rules:

- bounded official sources only;
- no publication;
- explicit page/model/token/cost budgets;
- stored artifact hashes;
- exact provider/model/prompt/schema versions;
- accepted/rejected claim counts;
- reviewer correction record;
- no secrets or private user content in logs.

## 10. Go-live checklist

### Code

- All mandatory suites green on the exact release commit.
- Clean migration from production-like database snapshot.
- No open P0 defects.
- Dependency lockfiles reproducible.
- Feature flags default safe.

### Extraction quality

- Exact evidence for every mandatory published fact.
- No cross-cycle leakage.
- Correct route/degree/programme/subject/document classification.
- No unresolved conflict in ready records.
- Unchanged rerun produces no model call or duplicate write.
- Multi-family protected suite passes.

### Security/privacy

- Network egress deny and redirect/SSRF tests.
- Browser isolation and no-secret proof.
- Document quarantine/scanner/converter limits.
- Forced RLS/tenant smoke.
- Public/private retrieval separation.
- Retention/deletion reconciliation proof.

### Operations

- Aggregate readiness reflects every enabled dependency.
- Queue age, retry and dead-letter dashboards.
- Cost and token alerts.
- Backup restore and PITR evidence.
- Rollback rehearsal.
- Load/spike/soak results.
- On-call runbook and named release approver.

### Product

- Universal detail page shows cycle/degree/route scope and exact citations.
- Review-only records never appear publicly.
- Matching uses reviewed facts only and makes no selection-probability claim.
- Assistant retrieves approved evidence only and abstains on insufficient coverage.
- Applications preserve source version when creating tasks/deadlines.

## 11. Rollback strategy

- **Crawlee:** disable feature gate and use legacy safe acquirer; do not discard compatible artifacts.
- **Docling:** disable converter and route complex documents to manual review; retain pypdf simple-document fallback.
- **New parser:** keep parser version on blocks; restore prior parser for new jobs without mutating old citations.
- **New graph reads:** switch read gate back to legacy projection; universal graph remains additive.
- **Worker release:** stop claiming new jobs, allow bounded in-flight completion, then deploy prior image. Expired leases are reclaimed after rollback.
- **Publication:** use recorded graph/publication version to restore the last approved public projection; never delete evidence history as rollback.

## 12. Risk register

| Risk | Early warning | Containment |
| --- | --- | --- |
| Crawlee/Docling version churn | Fixture parity changes | Pin versions, adapters, contract tests |
| Official-site variability | rising unknown/manual-review rate | family cohorts, source-role registry, exception queue |
| Model drift | schema/evidence rejection increase | prompt/model versioning, protected eval before rollout |
| Ontology overreach | frequent reviewer re-binding | concrete fixtures, explicit unknown/not-applicable, additive schema |
| Cost growth | calls/tokens per approved record rise | objective routing, hash reuse, hard budgets, static first |
| Reviewer bottleneck | queue age and correction time rise | conflicts first, cohort pause, reusable deterministic mappings |
| False freshness | expired/delegated facts remain current | cycle classification, event-relative monitoring, scoped stale state |
| Private/public leakage | private IDs/content in public retrieval test | separate storage/index/permissions and cross-corpus tests |
| Rushed 500-record batch | large blocked staging backlog | enforce three-family gate before batch and five-family gate before launch |

## 13. Terra work-report template

After each slice, Terra should produce:

```text
Slice:
Objective:
Baseline commit:
Files changed:
Migration impact:
Behavior before:
Behavior after:
Trust/security invariants preserved:
Tests added:
Commands run and exact results:
Targeted experiment:
Metrics/cost comparison:
Known limitations:
Rollback:
Next gate:
```

## 14. First instruction to give Terra

Use this as the starting task:

> Work from commit `f6b3e45dc97c75c7886118d6b972a090ff56bd28`. Implement P0-A and P0-B only: freeze the extraction contracts/fixtures, then make direct URL ingestion queued, idempotent, leased, fenced, retryable and dead-letter capable. Preserve every SafeSourceFetcher and no-auto-publication invariant. Add PostgreSQL concurrency tests for duplicate enqueue, expired lease reclamation and stale-worker completion. Do not start Crawlee networking changes until this slice is green. Report exact files, migrations, commands, results, rollback and remaining blockers.

## 15. Final decision rule

Move fast by narrowing the milestone, not by weakening evidence gates. At the end of next week, success means the team can repeatedly turn MEXT and Open Doors official source bundles into truthful, exact-cited review proposals through durable workers. Public launch begins only after those proposals can be approved into the universal graph, the protected family gates pass, and staging/rollback/restore evidence exists.
