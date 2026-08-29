# Architecture and Data-Flow Audit

Audit date: 24 August 2026  
Repository: `Scholarship AI Assistant`  
Audited branch: `codex/phase1b2-crawlee-secure-bridge`  
Audited commit: `f6b3e45dc97c75c7886118d6b972a090ff56bd28`  
Working-tree note: `uv.lock` was already modified before this report; this audit did not modify repository files.

## 1. Scope and evidence standard

This report maps the current application module by module, traces its main data flows, identifies frontend/backend and persistence boundaries, and records architecture bottlenecks verified in source. It does not treat planning documents as implementation evidence.

Evidence classes used throughout:

- **Verified current**: directly supported by source code and/or executed tests.
- **Experimentally reproduced**: demonstrated by a targeted local experiment during the audit.
- **Target**: selected by the attached architecture blueprint, but not necessarily implemented.
- **Not evidenced**: no supported runtime path was found in the audited branch.

Primary source anchors include `app/main.py`, `app/api/router.py`, `app/core/`, `app/db/`, every package under `app/modules/`, `app/cli/`, `frontend/src/`, Alembic migrations, tests, and the 26-page `scholarship-intelligence-platform-blueprint.pdf`.

Verification completed during the underlying audit:

- Ruff passed.
- The non-browser backend suite completed with **656 passed, 20 skipped, 10 deselected**.
- PostgreSQL-, Redis-, Crawlee-, and browser-dependent checks that require unavailable services or packages were skipped or environment-blocked; they are not reported as passing.
- Frontend test/typecheck execution was environment-blocked because installed frontend dependencies were absent; this is not reported as a code failure or a pass.

## 2. Executive architecture verdict

The repository is a **modular monolith**: one FastAPI process exposes domain APIs over a shared SQLAlchemy/PostgreSQL model, while CLI entry points perform worker-style jobs. A React/Vite single-page application consumes the REST API. Redis is required for production request-abuse controls. Private object storage is abstracted for Document Lab. Azure OpenAI is implemented for catalogue claim extraction, but disabled by default; the student assistant defaults to a deterministic evidence-template provider.

The strongest architectural property is its explicit trust boundary: official sources, immutable source artifacts, deterministic evidence checks, review gates, and publication controls are kept separate from model output. The largest mismatch is between that trust boundary and the current execution architecture: long catalogue ingestion can still run synchronously in an admin request, extraction is serial across sources and objectives, the secure Crawlee adapter delegates network I/O to the legacy fetcher, and the rich extraction result cannot yet be approved into a universal canonical graph.

The attached blueprint correctly describes the desired target as:

`Input -> Acquire -> Evidence blocks -> Scoped claims -> Deterministic resolution -> Human review -> Canonical graph -> Product consumers`

The audited branch currently reaches review-only cited staging for expanded v3 extraction, but it does not yet implement the complete target chain.

## 3. Runtime and repository topology

| Layer | Verified current implementation | Primary source anchors |
| --- | --- | --- |
| Application bootstrap | FastAPI app factory, middleware, error handling, health endpoints and aggregated API router | `app/main.py`, `app/api/router.py` |
| Configuration and feature gates | Pydantic settings, production-safe validation, independently disabled high-risk capabilities | `app/core/config.py`, `app/core/feature_gates.py` |
| Security middleware | JWT authentication, proxy handling, rate limits, HTTP security, observability | `app/core/security.py`, `middleware.py`, `proxy_headers.py`, `rate_limit.py`, `http_security.py` |
| Persistence | SQLAlchemy ORM over PostgreSQL, Alembic migrations, request sessions and system sessions | `app/db/session.py`, `app/db/models.py`, `alembic/versions/` |
| Authentication | Registration, login, rotating refresh families, account verification/reset, WebAuthn admin step-up | `app/modules/auth/` |
| Beta access | Invitation creation, reservation, expiry and activation | `app/modules/beta/` |
| Public catalogue | Legacy opportunity records, official sources, evidence policy, source lifecycle and source monitoring | `app/modules/opportunities/` |
| Catalogue ingestion | Direct URL candidates, safe fetch, bounded crawl, discovery ledgers, structured extraction, claim resolution and review-only staging | `app/modules/catalogue_ingestion/` |
| Student profile | Student preferences and matching inputs with version field | `app/modules/profiles/` |
| Matching | Deterministic criteria alignment and persisted evaluation records | `app/modules/matching/` |
| Applications | Application workspaces, tasks, reminders, document metadata, events, exports and lifecycle transitions | `app/modules/applications/` |
| Assistant | Evidence retrieval, conversations, answers, feedback, privacy/retention and provider boundary | `app/modules/assistant/` |
| Document Lab | Private upload, quarantine, scanning, sandboxed extraction, object storage, analysis jobs and retention | `app/modules/document_lab/` |
| Community | Consent, public pseudonymous identity, posts, replies, reports, moderation and blocking | `app/modules/community/` |
| Operations | Operational job health and release/maintenance support | `app/modules/operations/`, `app/core/health.py` |
| Worker entry points | Source monitor, catalogue seed ingestion/evaluation, reminder/document dispatch, retention and release preflight | `app/cli/` |
| Web client | React/Vite SPA with feature pages mapped to backend domains | `frontend/src/` |

## 4. Backend module map

### 4.1 `app/core`

This is the cross-cutting control plane.

- `config.py` declares runtime capabilities and rejects unsafe production combinations. Production requires explicit CORS, secure cookies, external metrics, Redis rate limiting and production-grade Document Lab configuration when enabled.
- `rate_limit.py` implements an in-memory development limiter and an atomic Redis sliding-window limiter. Redis errors fail closed with HTTP 503 before protected work proceeds.
- `security.py`, authentication dependencies and middleware validate signed access tokens and token versions.
- `health.py` exposes liveness, database readiness and separate worker/release health surfaces. The generic `/health/ready` route performs only `SELECT 1`; it does not prove Redis, object storage, scanners, extraction providers or worker freshness.
- `observability.py` provides logging/metrics plumbing, but telemetry coverage is not equivalent to deployed dashboards or alerts.

### 4.2 `app/db`

`session.py` constructs the SQLAlchemy engine with `pool_pre_ping=True`. Request sessions and privileged system sessions share the engine but differ by session metadata used to set PostgreSQL tenant context. Production startup checks that the application database role is neither superuser nor `BYPASSRLS`.

Alembic migration `20260814_0036_tenant_row_level_security.py` enables and forces row-level security on tenant tables. This is a material defense, not merely an application convention.

Confirmed limitation: no explicit engine pool size, overflow, recycle or pool-timeout tuning is configured in `app/db/session.py`; deployed behavior therefore depends on SQLAlchemy defaults unless environment-level controls intervene.

### 4.3 `app/modules/auth` and `beta`

Authentication implements password screening, short-lived access tokens, hashed refresh tokens, refresh-token family rotation and reuse containment. A refresh reuse race revokes the family and increments `User.token_version`, invalidating access sessions.

Beta invitations are integrated with registration and email verification. A targeted experiment reproduced a boundary defect: bulk expiry in `BetaService._expire_due()` changes invitation state but does not deactivate a user whose reserved invitation expires, while `activate_after_email_verification()` does deactivate in its direct expiry branch. This can leave a verified user active after an invitation expires.

### 4.4 `app/modules/opportunities`

This is the current public catalogue and evidence domain. It owns:

- legacy `Opportunity` records and their sources/cycles/eligibility;
- the newer scholarship graph entity set;
- source evidence policy and publication-facing projections;
- event-relative source monitoring, source checks and lifecycle reconciliation.

The legacy `Opportunity` representation and normalized graph representation coexist. That is intentional migration state, but it creates dual-read/dual-write complexity and prevents the richer v3 extraction output from becoming the universal public record today.

### 4.5 `app/modules/catalogue_ingestion`

This package contains the highest architectural density:

- `evidence_acquirer.py` defines the acquisition boundary and immutable fetched result.
- `crawlee_static_acquirer.py` is the optional Crawlee adapter.
- `safe_multi_url_session.py`, `crawler.py`, `url_policy.py` and the injected `SafeSourceFetcher` path enforce safe acquisition.
- `discovery_*` modules implement durable search/discovery ledgers, officiality checks, binding and promotion.
- `claim_provider.py`, `claim_schemas.py` and `provider.py` implement constrained catalogue AI extraction.
- `claim_resolution.py`, `validation.py`, `classification.py` and `evidence.py` apply deterministic checks.
- `repository.py`, `models.py`, `service.py` and `routes.py` coordinate candidates and review-only staging.
- `graph_materializer.py` writes a constrained MEXT-oriented graph only when compatibility permits.

Current branch status is specifically the secure bridge phase. The Crawlee adapter does not authorize Crawlee stock HTTP clients; it delegates requests through the existing safe fetch boundary. Multi-page Crawlee parity, production queue orchestration, Playwright fallback and Docling are not complete runtime capabilities.

### 4.6 `profiles` and `matching`

Profiles store normalized student inputs and expose a version number. Matching compares profile facts against reviewed eligibility and persists explainable evaluation records.

Experimentally reproduced defect: two concurrent profile writers can read the same version, both pass the in-memory expected-version check, and commit sequentially, allowing a lost update. `profiles/service.py` increments a loaded object after checking `profile.version`, but no atomic `UPDATE ... WHERE version = expected` or row lock enforces the comparison at commit time.

Scale bottleneck: matching can load the full public catalogue and accumulate evaluation changes before a final commit. This is manageable at current beta scale but not the desired 5,000+ record operating pattern.

### 4.7 `applications`

Applications are the canonical student planning state. The module has comparatively strong transition validation and idempotency controls for tasks/reminders. It supersedes but still coexists with saved-opportunity/tracker compatibility surfaces.

Confirmed limitations:

- Export loops over every application and issues a separate event query per application (`command_service.py:612-622`), creating N+1 behavior.
- Reminder dispatch atomically changes due database rows to `delivered`, but `app/cli/dispatch_reminders.py` contains no email, push or other delivery adapter. In current behavior, “delivered” means claimed/state-transitioned in the database.

### 4.8 `assistant`

The student assistant retrieves active opportunities and official sources, constructs a bounded evidence-based response, stores an evidence packet, and passes the already structured response through a provider boundary. The default provider returns the deterministic server-composed response unchanged. Other configured remote providers deliberately fail unavailable.

Confirmed architecture issues:

- Retrieval expands up to six tokens into `%token%` `ILIKE` predicates over multiple columns, with no matching trigram or full-text index evidenced.
- The SQL query limits candidates before freshness and evidence-policy filtering, so valid records beyond the limit can be excluded.
- Quotas are count-then-insert rather than atomically reserved; a targeted concurrent experiment showed two requests can both pass a limit of one and commit two answers.
- Evidence packets referenced by retained answers are excluded from deletion and can survive indefinitely.
- Retention is a synchronous global sweep.

### 4.9 `document_lab`

Document Lab separates private student uploads from the public catalogue. The flow is upload -> immutable version -> scan -> restricted extraction -> optional consented analysis -> retention/deletion. Storage is encrypted locally in development or abstracted to S3-compatible storage; scanner/provider readiness is separately reported.

Verified current boundary: `get_provider()` always returns `UnavailableDocumentProvider`; no reviewed remote document-analysis adapter is installed.

Experimentally reproduced reliability issues:

- Deletion commits `PENDING_DELETE`, then deletes objects. If object deletion fails, the database remains pending and there is no evidenced retry worker for that state, leaving an orphan risk.
- Analysis/provider jobs can remain `running` after process interruption because no general expired-lease reaper was found.
- The thread-based provider timeout returns to the caller while a non-cooperative provider thread can continue executing.

### 4.10 `community`

Community uses a public UUID distinct from the internal user ID in member-facing responses. Posts and replies are scoped by consent/suspension and support reporting, blocking and moderation.

Experimentally reproduced API contract defect: moderation resolves `payload.user_id` directly with `session.get(CommunityPreference, payload.user_id)`, which expects the internal user ID. The public API exposes `CommunityPreference.public_id`. Supplying the public member ID fails while the internal ID succeeds.

The moderation/export paths also contain scaling-sensitive per-row loading patterns.

## 5. Main end-to-end data flows

### 5.1 Public catalogue read

1. React catalogue pages call REST endpoints through `frontend/src/api/client.ts`.
2. Opportunity routes invoke opportunity services/repositories.
3. SQLAlchemy loads active opportunity records, current cycles, provider and approved sources.
4. Evidence policy excludes disqualifying, stale or non-approved source state where the calling service applies it.
5. Pydantic response schemas cross the API boundary.
6. React renders a universal catalogue/detail experience, including graph data when available.

The public read path is still partly anchored to legacy `Opportunity`; the universal scoped graph selected by the blueprint is not yet the sole source of truth.

### 5.2 Direct official URL ingestion

1. Admin UI submits a seed URL/name to catalogue-ingestion routes.
2. `process_now` defaults to `true` in `catalogue_ingestion/schemas.py`, and `routes.py` invokes processing in the HTTP request when set.
3. The candidate and source are stored.
4. Acquisition passes through URL policy and `SafeSourceFetcher`; the bounded crawler may discover a small ranked set of linked official pages.
5. Raw/normalized source artifacts and hashes are persisted.
6. Each source is sent through each applicable/current `ClaimObjective` in serial service loops.
7. The Azure structured-output provider, when explicitly enabled, proposes typed claims.
8. Deterministic evidence, ontology, scope, conflict and completeness checks accept or reject claims.
9. Expanded v3 results remain review-only staging. `service.py` rejects legacy graph submission when `_legacy_graph_compatible()` is false.
10. Only compatible reviewed data can reach the current MEXT-oriented materializer; no automatic publication path exists.

This flow preserves safety but combines request latency, crawl latency, model latency and database work in one synchronous admin request by default.

### 5.3 Source monitoring

1. A CLI worker claims due official sources using `SELECT ... FOR UPDATE SKIP LOCKED` and writes a lease.
2. It fetches with per-host pacing and safe source controls.
3. It compares content hashes and records a source check/diff.
4. It separately clears the lease and schedules the next check.

A targeted failure experiment showed the source-check transaction can commit while the subsequent lease-completion commit fails. The change is recorded, but the lease remains until expiry and the worker reports failure. The operations are not atomic as a unit.

### 5.4 Matching

1. The client submits or retrieves a student profile.
2. Matching loads public opportunities and structured eligibility.
3. Deterministic rules produce aligned, missing and conflicting criteria plus a score.
4. Evaluation records are persisted for explanation/audit.
5. The API returns ranked matches; it does not claim admission probability.

### 5.5 Assistant

1. Authenticated user with assistant consent sends a question and optional selected opportunity IDs.
2. The service checks daily/monthly quota counts.
3. Retrieval queries active opportunities, then filters sources for verification/freshness/conflict.
4. The server composes a citation-first answer and evidence packet.
5. The configured provider either returns the deterministic response or fails closed.
6. Conversation/messages/answer/feedback are stored under retention controls.

There is no implemented hybrid FTS + pgvector retrieval path matching the blueprint target.

### 5.6 Private Document Lab

1. React uploads PDF/DOCX bytes to the private API after displaying the notice.
2. Server validates type/size, encrypts and writes object bytes, then stores owner-scoped metadata.
3. Worker scans and performs isolated restricted extraction.
4. User explicitly requests editorial analysis and consents to provider processing.
5. A job invokes the provider boundary and stores structured feedback.
6. Export/deletion/retention operate only on the owner’s private records.

The product boundary is present, but the default scanner/provider configuration and worker readiness mean the full production path is not evidenced.

## 6. Frontend/backend boundary

The frontend is a client-rendered React SPA. It contains no direct database or model access. All authoritative state comes from JSON REST endpoints.

Key boundaries:

- `frontend/src/api/client.ts` centralizes HTTP calls and authentication refresh behavior.
- `AuthProvider.tsx` maintains client authentication state while refresh credentials remain cookie-based.
- Feature folders map closely to backend domains: `admin`, `assistant`, `catalogue`, `community`, `document-lab`, and `workspace`.
- Capability/readiness responses control display for disabled high-risk features.
- There is no server-side rendering, frontend worker queue, or independent frontend data store.

Confirmed frontend bottleneck: `DocumentLabPage.tsx:37-45` loads policy/assets/applications, then performs one analysis-history request for every document version with `Promise.all`. Request count grows linearly with versions and can burst the API.

## 7. Database interaction model

### Verified strengths

- SQLAlchemy statements are parameterized.
- PostgreSQL tenant tables use forced RLS.
- Production runtime-role validation rejects superuser and `BYPASSRLS` roles.
- Several worker claims use leases and `SKIP LOCKED`.
- Refresh rotation and several application commands use uniqueness or atomic update patterns.
- Publication-sensitive operations are separated from extraction proposals.

### Verified weaknesses

- Some optimistic concurrency is checked only in Python, not in the write predicate.
- Several workflows split logically atomic state across multiple commits: document deletion and source monitoring are the clearest reproduced cases.
- Count-then-act quotas are raceable.
- N+1 exports and moderation/read paths will amplify database round trips.
- Long matching and ingestion work retain large in-memory object sets and coarse transaction boundaries.
- Engine pool behavior is mostly defaulted.
- Legacy and normalized graph models coexist, increasing migration and consistency burden.

## 8. Architecture bottlenecks and priorities

| Priority | Verified bottleneck | Consequence | Recommended architectural response |
| --- | --- | --- | --- |
| P0 | Expanded extraction cannot materialize to a universal graph | Extraction work cannot become a complete reviewed public record | Add additive scoped graph schema, proposal diff and transactional approval |
| P0 | Secure Crawlee adapter still delegates to legacy fetcher | No real Crawlee queue/concurrency/telemetry benefit yet | Finish custom safe Crawlee HTTP client/bridge and parity tests |
| P0 | Serial source x objective extraction | High latency/cost and weak catalogue throughput | Route objectives by source role and unresolved completeness; add durable per-objective jobs |
| P0 | Synchronous `process_now=true` ingestion | Admin request timeouts and duplicate retry pressure | Default to enqueue; expose run status and idempotent resume |
| P1 | Flat HTML/PDF text as canonical extraction input | Lost headings, tables, list hierarchy and scope | Introduce deterministic evidence blocks and Docling document conversion |
| P1 | Dual legacy/graph model | Projection loss and complex reads | Complete additive migration, then deprecate legacy writes |
| P1 | Weak readiness aggregation | Traffic can reach an API whose critical dependencies are unavailable | Add capability-specific readiness and deployment gates |
| P1 | N+1 exports/community/document history | Latency and load grow with user data | Batch eager loading, aggregate endpoints and background exports |
| P1 | `ILIKE` assistant retrieval | Poor relevance and scaling | PostgreSQL FTS first; pgvector only for approved evidence after measured need |
| P2 | Default SQLAlchemy pool settings | Unpredictable saturation behavior | Tune and measure pool size, timeout, recycle and overflow per deployment |

## 9. Blueprint alignment

The attached blueprint’s architectural decisions are consistent with the source-confirmed constraints:

- Preserve `SafeSourceFetcher` as the policy boundary.
- Put Crawlee behind an internal `EvidenceAcquirer` interface.
- Use static HTTP first and Playwright only after deterministic insufficiency.
- Convert HTML/documents into stable evidence blocks; use Docling for layout-aware files.
- Keep Azure OpenAI limited to schema-bound claim proposals.
- Resolve and publish only through deterministic validators and explicit review.
- Keep PostgreSQL as the initial queue/graph/retrieval foundation and add distributed infrastructure only when metrics justify it.

However, Crawlee orchestration, deterministic Playwright fallback, Docling conversion, universal scoped graph approval, pgvector retrieval and isolated Azure worker deployment are **targets**, not verified capabilities of the audited commit.

## 10. Final disposition

The application is not a prototype shell: it has substantial authentication, catalogue, matching, applications, evidence, privacy and tenant-isolation foundations. Its architecture is suitable for an evidence-first scholarship platform if the team completes the extraction-to-approval critical path.

For the next-week goal, the correct “extraction layer complete” definition is not “the model emits many fields.” It is: safe queued acquisition, canonical block production, objective routing, exact citations, scope/cycle resolution, truthful completeness, idempotent reruns, and a reviewable proposal. Public launch must remain gated until the universal graph and publication transaction are proven.
