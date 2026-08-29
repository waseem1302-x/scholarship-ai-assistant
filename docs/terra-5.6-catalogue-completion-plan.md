# Terra 5.6 plan: finish the private, evidence-backed scholarship catalogue

## 1. Mission

Finish the existing catalogue-ingestion foundation as one usable local workflow:

`private seed -> official-source acquisition -> PDF/HTML normalization -> AI extraction -> evidence resolution -> completeness gate -> admin review`

The first proof must cover CSC, DAAD, and Erasmus Mundus. After that proof is approved, expand in controlled batches until at least 500 distinct, reviewable scholarship routes exist.

This plan does **not** authorize deployment, merging, pushing, public publication, or enabling production flags.

## 2. Non-negotiable rules

1. Work locally and preserve the existing dirty worktree. Inspect `git status` before edits; never reset or overwrite unrelated changes.
2. Do not deploy, merge, push, publish a scholarship, or enable any production capability.
3. All newly materialized opportunities remain `draft` / `needs_review`.
4. A PDF supplied by the owner, a blog, a directory, a search snippet, or model memory may create a discovery lead only. It is never fact evidence.
5. Every public-facing fact must cite an exact excerpt from an acquired official source and retain the official URL, content hash, retrieval time, parser version, and applicable programme/cycle/route scope.
6. Do not invent a value to remove `unknown`. Unsupported facts remain private blockers.
7. Login pages, CAPTCHA pages, unsupported MIME types, inaccessible pages, and low-information JavaScript shells fail closed and enter review.
8. Fully funded means, at minimum, evidence-backed full tuition **and** an evidence-backed living stipend. Do not infer full funding from marketing language.
9. GPT/API use is disabled during code work and automated tests. A live model call requires an explicit pilot command, a hard run ceiling, and owner approval.
10. Use the existing architecture where it is sound. Do not replace the repository with a second crawler, second catalogue, or second review system.

## 3. Important model distinction

- `gpt-5.6-terra` is the Codex/CLI implementation agent used to inspect, edit, and test the repository.
- The owner's Azure Foundry/OpenAI deployment (currently believed to be GPT-5.4 Mini) is the application's paid extraction model.
- Terra must use fake providers and captured fixtures for normal development. It must not silently call the Azure extraction model.
- Official OpenAI guidance describes Terra as the pragmatic all-rounder for everyday work requiring strong reasoning and tool use. Use medium reasoning for narrow changes and high reasoning for the cross-module integration passes: <https://developers.openai.com/codex/models/>.

## 4. Existing foundation to retain

Before writing code, Terra must inventory and reuse these components:

- `CatalogueIngestionService` and the durable run/candidate/attempt ledgers;
- `SeedSourceLoader` and the private priority seed file;
- `SafeSourceFetcher` and URL/redirect/DNS/content safety policy;
- `BoundedOfficialSiteCrawler` and the Crawlee evidence-acquirer adapter;
- document conversion, Docling transport, PDF parsing, and OCR boundaries;
- Azure extraction and claim providers with structured output;
- evidence blocks, field-level claims, claim resolution, and source routing;
- validation/proposal materialization into the existing Opportunity model;
- duplicate suggestions and scholarship graph/family primitives;
- admin review APIs, audit history, and the shared scholarship detail view;
- source monitoring and freshness state.

The problem is integration and completion, not absence of a foundation.

## 5. Definition of a complete review record

A route is `review_ready_complete` only when all mandatory fields below are either:

- `supported`: value plus exact official-source evidence; or
- an explicit, evidence-backed semantic state such as `not_applicable`, `rolling`, `varies_by_country`, or `not_yet_announced`.

Plain missing/null/unknown is never publishable.

Mandatory fields:

1. Scholarship identity and canonical programme family.
2. Provider/awarding body and study country/region.
3. Degree level and route/programme scope.
4. Current application cycle or an officially supported `not_yet_announced` state.
5. Application deadline, rolling status, or country/route-specific deadline rule.
6. Official application URL and application method.
7. Tuition coverage status and supporting wording.
8. Living-stipend coverage; include amount, currency, and frequency when officially stated.
9. Funding classification computed from components, not copied from promotional text.
10. Nationality/geographic eligibility relevant to Asian and African applicants.
11. Minimum academic requirement, or an official statement showing programme-specific variation.
12. Language/test requirements, including accepted exceptions when stated.
13. Required documents, or an official route explaining where programme-specific documents are defined.
14. At least one fresh official source, with all cited source artifacts fetchable and hashable.
15. No unresolved source conflict and no unresolved duplicate identity.

Optional benefits such as flights, insurance, accommodation, visa fees, research allowance, and family allowance may be absent, but the UI must distinguish `not stated` from `not covered`. Neither state may be invented.

## 6. Publication-readiness policy

Implement one backend-owned `PublicationReadiness` result; do not duplicate the rules in React.

It must return:

- `ready: bool`;
- `blocking_reasons[]` with field path, reason code, message, and source where applicable;
- `warnings[]` for non-blocking optional fields;
- `supported_required_count` and `required_count`;
- `evaluated_at` and policy version.

Required behavior:

1. Any mandatory unknown, missing evidence, stale source, conflict, invalid route scope, unresolved duplicate, or unverified official ownership sets `ready=false`.
2. The publish transition must call this backend policy transactionally and reject when `ready=false`.
3. The public catalogue query must return only active records that satisfy current publication readiness.
4. Existing active records that fail the new policy must be hidden from public catalogue results and placed in a remediation queue; do not delete them.
5. The public detail serializer must never emit `Unknown — verify from official source`. Such text remains admin-only.
6. Admin UI may show unknowns, but must label them as blockers and identify the missing source objective.

Add tests proving direct API calls cannot bypass the UI lock.

## 7. Implementation phases

### Phase 0 — zero-cost truth audit

No network and no model calls.

1. Record the current branch, commit, dirty files, running Compose services, migrations, feature flags, and database counts by status.
2. Inventory incomplete implementation seams against `docs/current-product-state.md`, `docs/catalogue-ingestion-pipeline.md`, and this plan.
3. Trace the exact candidate lifecycle from CLI entry point to review-queue opportunity.
4. Confirm which current code paths are production code versus interfaces/placeholders.
5. Inspect the existing CSC, DAAD, and Erasmus records and list every missing mandatory field, source, and pipeline state.
6. Produce a short audit report with: reusable code, broken wiring, missing code, obsolete assumptions, and the smallest safe change set.

Exit gate: no coding begins until the audit explains why the current three records are incomplete.

### Phase 1 — freeze contracts and regression fixtures

No live Azure calls.

1. Add/confirm typed states for supported facts, legitimate semantic states, and unsupported unknowns.
2. Add `PublicationReadiness` and policy versioning.
3. Capture private, legally usable official-source fixtures for one route each from CSC, DAAD EPOS, and Erasmus Mundus. If redistribution is unclear, keep raw fixture text in an ignored private directory and commit only synthetic/minimal derived fixtures.
4. Create expected gold outputs including field-to-source evidence mappings.
5. Add failing tests for:
   - unknown deadline;
   - unknown tuition or stipend;
   - missing application URL;
   - missing nationality/academic/document coverage;
   - unsupported evidence excerpt;
   - conflicting official sources;
   - stale source;
   - duplicate programme versus legitimate route/cycle variant;
   - public endpoint leakage of an incomplete record.

Exit gate: the new tests fail for the intended current gaps and make no paid calls.

### Phase 2 — official-source acquisition bundle

No AI extraction yet.

1. Start from an operator-supplied/seeded official root URL.
2. Fetch it only through `SafeSourceFetcher`.
3. Use bounded same-owner crawling to collect a small source bundle rather than one landing page.
4. Classify each page into a source role:
   - identity/overview;
   - funding/benefits;
   - eligibility;
   - dates/cycle;
   - application process;
   - required documents;
   - country route;
   - programme/course annex.
5. Permit a cross-domain page only after deterministic ownership resolution, for example an official ministry, programme consortium, or resolved university domain.
6. Download official PDFs through the same safe boundary. Normalize ordinary PDFs locally; send scan/image PDFs to the isolated Docling/OCR worker.
7. Store an immutable source snapshot/artifact per URL/content hash. Never combine unrelated page text into one anonymous blob.
8. Deduplicate canonical URLs, redirects, and identical content before extraction.
9. Return explicit acquisition gaps such as `funding_source_missing` or `deadline_source_blocked`.

Initial limits for the three-record pilot:

- maximum 6 accepted source artifacts per route;
- maximum crawl depth 2;
- same official owner by default;
- sequential requests with per-host delay;
- bounded bytes and runtime inherited from current settings.

Exit gate: CSC, DAAD, and Erasmus each have a reviewable official source bundle even if extraction is still disabled.

### Phase 3 — provenance-safe multi-source extraction

Use fake/captured provider outputs first.

1. Extract per source artifact and per objective. Do not ask one prompt to resolve an entire multi-page scholarship.
2. Objectives are identity, funding, eligibility, application dates/process, documents, and route/cycle scope.
3. Each claim must include:
   - canonical field path;
   - typed value;
   - source artifact ID and final official URL;
   - exact evidence excerpt/block locator;
   - programme family, route, country, and cycle scope;
   - extraction schema/prompt/model version;
   - confidence used for review prioritization only, never as proof.
4. Reject any claimed excerpt not present in normalized source text.
5. Resolve claims deterministically:
   - route/cycle-specific official evidence outranks generic programme text;
   - newer applicable cycle outranks an older cycle without erasing history;
   - conflicts become blockers;
   - facts may be inherited only through explicit graph relationships allowed by existing policy.
6. Cache extraction by normalized content hash + objective + schema + prompt + deployment. A retry must not pay twice for unchanged content.
7. Materialize one proposal only after all mandatory objectives have terminal results.

Exit gate: fixture-based outputs for all three scholarship families exactly match expected evidence and scope.

### Phase 4 — programme families, routes, cycles, and deduplication

1. Treat CSC, DAAD, and Erasmus as families containing multiple programmes/routes; never flatten them into one universal record.
2. Generate a deterministic identity key from provider canonical ID, programme family, route/course, host institution where applicable, destination country, degree level, and cycle.
3. Normalize aliases and translated names without merging distinct awards.
4. Use canonical URL/content identity first, then structured identity, then fuzzy similarity as a review suggestion only.
5. Preserve historical cycles. A new deadline creates/updates the applicable cycle, not the scholarship's timeless identity.
6. Add an admin duplicate-resolution view showing the two records, matching signals, and conflicting fields.

Exit gate: retries create no duplicates; legitimate CSC university routes, DAAD EPOS courses, and Erasmus joint masters remain distinct.

### Phase 5 — admin review experience

1. Reuse the public scholarship detail layout as the main admin review view.
2. Add an always-visible readiness banner: complete or blocked, supported mandatory fields, blockers, warnings, and source freshness.
3. For every field, show value/state, source title, official URL, evidence excerpt, route/cycle scope, and last checked time.
4. Show complete source artifacts, extraction attempts, conflicts, duplicate suggestions, warnings, and audit history in secondary disclosures.
5. Allow route switching inside a scholarship family.
6. Keep decision controls at the bottom/sticky area. Password step-up and notes remain required according to existing policy.
7. Disable Publish using backend readiness, but also handle a backend rejection if the page is stale.
8. Provide filters: complete, missing funding, missing deadline, missing eligibility, conflicts, duplicates, stale sources, and failed acquisition.

Exit gate: the owner can understand what was found, what is missing, and why in seconds without opening database records.

### Phase 6 — local runtime wiring

Keep every expensive feature off by default.

1. Add/finish a dedicated local `catalogue-worker` Compose profile. Do not put long-running acquisition inside a web request.
2. Pass only catalogue-specific settings to that worker.
3. Use `DefaultAzureCredential`; never commit keys. Allow the owner's existing Azure model deployment to be supplied through an ignored local environment file or shell environment.
4. Enable independently:
   - AI ingestion;
   - bounded crawling;
   - Crawlee static orchestration;
   - local document conversion/OCR;
   - source routing.
5. Leave autonomous web discovery, browser fetching, scheduled ingestion, graph rollout, and publication disabled for the first pilot.
6. Add a preflight command that validates credentials, model capability, structured-output support, price configuration, worker health, database migration, disk capacity, and all budgets **without processing a scholarship**.
7. Ensure stop/resume is durable at candidate/objective level.

Exit gate: Compose starts API, PostgreSQL, and required local workers; preflight is green; zero scholarship/model work occurs automatically.

### Phase 7 — cost-controlled live pilot

This is the first phase allowed to call the paid Azure model, and only after explicit owner approval.

1. Confirm the exact Azure deployment name and measured input/output pricing.
2. Set a hard application ceiling for one candidate, one worker, bounded pages, bounded objectives, bounded retries, input characters, and output tokens.
3. Run `candidate_only` first: acquire/classify sources with zero model calls.
4. Inspect and approve the source bundle.
5. Run extraction for **one DAAD EPOS route** only.
6. Report before continuing:
   - provider calls;
   - input/output tokens;
   - estimated and Azure-observed cost;
   - cache hits;
   - extracted fields;
   - blockers/conflicts;
   - evidence accuracy.
7. Fix using fixtures and deterministic tests. Do not repeatedly spend money while debugging.
8. After DAAD passes, repeat one CSC route and one Erasmus route.

Pilot acceptance:

- 100% official-source URLs;
- zero unsupported confident facts;
- 100% mandatory non-null/semantic-state facts linked to valid excerpts;
- correct route/cycle separation;
- no public visibility;
- owner approves all three review pages.

### Phase 8 — source discovery strategy

Do not enable paid autonomous web search by default.

Priority order:

1. Use official URL already present in the private seed.
2. Follow relevant links within the verified official owner boundary.
3. Let the operator add an official supporting URL.
4. Use a deterministic provider/university domain map.
5. Only then consider Azure Responses web search for missing/moved sources.

If Azure web discovery is later approved:

- capability-probe the exact deployment first;
- keep its budget separate from extraction;
- accept returned URLs as leads only;
- fetch and classify every lead before evidence use;
- never use snippets as evidence;
- permit one tool call per request and small query/lead limits;
- record every query, lead, rejection, promotion, token/tool usage, and cost;
- keep it manual until measured precision and cost are approved.

Azure Blob Storage is not required for the local catalogue build. Use local ignored seed/fixture directories. Blob becomes optional only when a private seed must be supplied to a cloud job.

### Phase 9 — controlled catalogue expansion

After the three-family golden path is approved:

1. Normalize and deduplicate all supplied reference PDFs into a private candidate list. Preserve each PDF's provenance as discovery metadata, not evidence.
2. Rank candidates:
   - Tier A: full tuition + stipend confirmed by official evidence;
   - Tier B: likely fully funded but one mandatory funding component still unverified;
   - Tier C: partial/unclear funding, retained privately but outside the initial publication target.
3. Prioritize government and flagship schemes, then Asian/African audience coverage.
4. Process in batches: 5, 20, 50, then repeated 50-record batches.
5. At every batch gate report acquisition success, complete review records, incomplete records by blocker, duplicates, conflicts, token/cost totals, cost per complete record, and manual correction rate.
6. Stop the next batch if any of these occur:
   - unsupported confident claim;
   - official-source accuracy below 100%;
   - mandatory-field accuracy below 95%;
   - unexplained cost variance above 20%;
   - duplicate rate unexpectedly increases;
   - public visibility of a draft/incomplete record.
7. `500+` means 500 distinct routes that passed automated evidence validation and are available for human review. It does not mean 500 automatically published records.

## 8. Cost-control design

Implement and prove all controls before bulk execution:

1. No model calls during unit, integration, browser, or CI tests.
2. Content-hash/objective cache across retries and candidates.
3. Do not send navigation, cookie, privacy, boilerplate, or unrelated page content to the model.
4. Deterministic extraction for obvious URLs/dates/currencies may reduce model input, but it must still retain official evidence and cannot override conflicts.
5. One model deployment initially; do not purchase Blob, Redis, Document Intelligence, web search, or cloud compute for the local proof.
6. Separate ceilings for discovery and extraction.
7. Reserve budget atomically before provider calls and reconcile actual usage afterward.
8. Retries count against budget; rate-limit retries obey `Retry-After` and capped backoff.
9. Every run exposes planned maximum cost before start and actual/estimated cost after each candidate.
10. Add an operator kill switch that disables new provider calls while preserving resumable state.

## 9. Tests and evidence required

Terra must add or update tests in proportion to each change, then run the narrow tests before the full suite.

Required categories:

- seed parsing and duplicate normalization;
- safe fetch, redirects, login/CAPTCHA/low-information rejection;
- bounded crawler and same-owner policy;
- HTML, text PDF, complex PDF, and OCR worker transport;
- source-role routing;
- evidence-block and exact-excerpt binding;
- per-objective claim extraction and deterministic resolution;
- route/cycle scoping and inheritance;
- Azure provider schema, retry, usage, and budget accounting using mocks;
- resumable PostgreSQL worker leasing/fencing;
- publication readiness and API-bypass protection;
- public query/detail exclusion of incomplete records;
- admin detail rendering and action handling;
- end-to-end three-family fixture proof;
- full backend/frontend/browser regression.

Standard verification commands:

```text
uv run ruff check .
uv run ruff format --check .
uv run pytest -ra -m "not e2e" --cov=app --cov-report=term-missing --cov-fail-under=85
pnpm --dir frontend test
pnpm --dir frontend build
uv run pytest -m "e2e and not browser_compat" --browser chromium
docker compose config
docker compose up --build
```

Do not claim a test passed if its dependency was skipped or unavailable. Report skipped integration proofs separately.

## 10. Required deliverables

1. Zero-cost audit report.
2. Versioned completeness/publication-readiness policy.
3. Three-family private gold fixture/evaluation pack.
4. Official multi-source acquisition bundle and document processing proof.
5. Provenance-safe extraction/resolution implementation.
6. Route/cycle-aware deduplication proof.
7. Admin review page with field-level evidence and blockers.
8. Local worker/preflight/kill-switch workflow.
9. One-record, then three-record live cost report.
10. Batch reports through the 500+ review-ready target.
11. Final local acceptance report listing all commands, results, skips, remaining blockers, and exact uncommitted files.

## 11. Definition of done

The implementation is complete only when:

- CSC, DAAD, and Erasmus each produce correctly separated, complete, evidence-backed review records from official multi-source bundles;
- every mandatory value/state has field-level official evidence;
- incomplete records cannot be published by UI or direct API and cannot appear publicly;
- the admin can identify findings and missing evidence within seconds;
- duplicates are prevented or held for review without collapsing legitimate routes/cycles;
- local PDF/HTML acquisition works without Azure Blob or paid Document Intelligence;
- paid extraction is explicit, bounded, cached, resumable, and auditable;
- the owner approves the three-record pilot before batching;
- at least 500 distinct validated routes are in the private human-review queue;
- no deployment, merge, push, production flag, or automatic publication occurred.

## 12. Terra 5.6 execution instructions

Give Terra one phase at a time. Do not ask it to implement the entire plan in one unattended run.

Use this initial prompt:

```text
You are implementing docs/terra-5.6-catalogue-completion-plan.md in the existing
Scholarship AI Assistant repository.

Work on Phase 0 only. Read the plan and the repository's current-state and ingestion
documentation completely. Inspect the dirty worktree and preserve all existing changes.
Perform a read-only, zero-cost audit. Do not call Azure/OpenAI or any paid provider. Do
not edit application code, deploy, merge, push, publish records, or enable production
flags. Trace CSC, DAAD, and Erasmus from seed through acquisition, extraction,
validation, materialization, review, and public visibility. Produce the Phase 0 audit
report required by the plan, including exact files/functions, current runtime flags,
database/run state, missing wiring, and the smallest safe implementation sequence.
Stop after the report and wait for approval.
```

For every later phase, instruct Terra:

```text
Implement Phase N only from docs/terra-5.6-catalogue-completion-plan.md. First verify
that the prior phase exit gate is evidenced. Preserve the dirty worktree. Keep paid
providers disabled unless this phase explicitly permits a live pilot and the owner has
approved it. Add focused tests, run them, then run the relevant regression suite. Do not
deploy, merge, push, publish records, or enable production flags. End with changed files,
test results, skipped proofs, cost/model-call count, remaining blockers, and whether the
phase exit gate passed. Stop and wait for approval.
```

