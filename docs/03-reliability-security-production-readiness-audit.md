# Reliability, Security and Production-Readiness Audit

Audit date: 24 August 2026  
Repository commit: `f6b3e45dc97c75c7886118d6b972a090ff56bd28`

## 1. Release verdict

The codebase contains unusually strong fail-closed controls for a pre-launch scholarship platform, especially around tenant isolation, authentication, source acquisition and publication. It is nevertheless **not ready for an unrestricted public 500-record launch** on the evidence available in this repository.

A narrow closed-beta or internal review deployment is feasible after the P0 reliability defects and environment gates below are resolved. The extraction path should remain review-only until the universal scoped graph and transactional approval path are complete.

This verdict separates three questions:

- **Code readiness:** substantial, but with reproduced concurrency/lifecycle defects.
- **Environment readiness:** not evidenced; no successful staging, rollback, PITR restore, load/soak or worker-fleet record was available.
- **Catalogue readiness:** not evidenced for 500 reviewed current-cycle records or the five-family gold gate.

## 2. Verification performed

### Static and automated checks

- Ruff passed.
- Non-browser backend pytest run: **656 passed, 20 skipped, 10 deselected**.
- PostgreSQL/Redis/Crawlee integration checks requiring unavailable external services/packages did not run and are not counted as passes.
- Frontend dependency installation was absent, so frontend tests, TypeScript checks and the production build could not be independently executed in this environment.
- Repository state was checked before report generation; the only pre-existing tracked change was `uv.lock`.

### Targeted experiments

Small isolated experiments were used to test concurrency and failure boundaries. They reproduced:

1. expired beta invitation can leave a verified user active;
2. profile optimistic locking permits a lost update;
3. object deletion failure can leave private document deletion permanently pending;
4. document jobs can remain `running` without a lease reaper;
5. a timed-out provider thread can continue executing;
6. referenced assistant evidence packets survive retention indefinitely;
7. two assistant quota checks can both pass a limit of one and commit two answers;
8. community suspension accepts an internal user ID but rejects the public member ID exposed by the API;
9. source-check persistence can commit while lease completion fails.

These are reported as reproduced behavior, not theoretical concerns.

## 3. Confirmed strong controls

### 3.1 Tenant and database isolation

- Alembic migration `20260814_0036_tenant_row_level_security.py` enables **FORCE ROW LEVEL SECURITY** on tenant tables.
- `app/db/session.py` checks the production runtime role and rejects `rolsuper` or `rolbypassrls`.
- Tenant context is set through SQLAlchemy session/transaction hooks.
- Separate system-session behavior is explicit rather than an accidental bypass.

### 3.2 Authentication and session containment

- Password hashes and refresh tokens are not stored in plaintext.
- Access tokens include `token_version`.
- Refresh tokens rotate atomically; reuse containment revokes the token family and increments token version.
- Password reset and security events invalidate sessions.
- Production cookie, CORS, proxy and secret settings are validated at startup.
- WebAuthn/passkey step-up protects privileged administrator operations.

### 3.3 Request-abuse controls

- Production configuration requires Redis.
- Redis uses an atomic sliding-window operation.
- Rate-limit-store failure returns HTTP 503 before protected auth/write/high-cost work.
- In-memory limiting is explicitly development-only.

### 3.4 Acquisition security

- HTTPS-only acquisition.
- DNS/IP and peer-address validation.
- Redirect-hop validation.
- Loopback/private/link-local/metadata destination rejection.
- robots, MIME and byte limits.
- Bounded crawl depth/pages/links/bytes.
- Officiality and source-review boundaries.
- Scraped/model content cannot directly publish.

### 3.5 Evidence and publication controls

- Immutable source hashes and exact-excerpt validation.
- Typed structured extraction rather than free-form fact acceptance.
- Conflict/completeness states block readiness.
- Expanded v3 extraction is explicitly review-only.
- High-risk production features default disabled.
- Source monitoring creates diffs rather than silently rewriting published facts.

## 4. Reliability defects

### R-01 - Beta expiry state divergence

**Severity:** High for invite-only beta access  
**Status:** Experimentally reproduced

`BetaService.activate_after_email_verification()` deactivates a user when the reserved invitation is expired. In contrast, `_expire_due()` only marks matching invitations expired and commits. It does not deactivate the reserved user.

Impact: a verified account can remain active after its beta authorization expires, depending on which code path observes expiry.

Recommended fix: centralize invitation expiry transition in one locked helper that updates invitation and reserved user in the same transaction. Add tests for bulk expiry, verification race and repeat execution.

### R-02 - Profile lost update despite expected version

**Severity:** High for correctness  
**Status:** Experimentally reproduced

`profiles/service.py:37-63` loads a profile, compares `expected_version` in Python, mutates fields, increments the version and commits. There is no row lock or atomic conditional update.

Impact: concurrent requests can both read version N, both pass, and last commit wins while both appear successful.

Recommended fix: `UPDATE student_profiles SET ..., version=version+1 WHERE id=:id AND version=:expected RETURNING ...`, raising 409 when zero rows update. Cover PostgreSQL concurrency explicitly.

### R-03 - Private object deletion can strand pending state

**Severity:** High for privacy/data rights  
**Status:** Experimentally reproduced

`document_lab/service.py:996-1016` commits `PENDING_DELETE`, then deletes each object, then advances/deletes database records. A storage exception exits after the first commit. No durable deletion retry/dead-letter worker was found.

Impact: the user sees a deletion request, database state remains pending, and storage objects can persist indefinitely.

Recommended fix: durable deletion jobs with object-level idempotency, retry/backoff, terminal operator state and reconciliation metrics. Do not delete database metadata until all object keys are confirmed absent.

### R-04 - Document jobs can remain running

**Severity:** High for operations  
**Status:** Experimentally reproduced

Document preparation/analysis has running states, but no general job lease expiration/reaper was found that returns abandoned work to retry or dead-letter state.

Impact: worker crashes or process termination can strand jobs permanently.

Recommended fix: add `claimed_at`, `claimed_until`, attempt count, retry class and dead-letter state. Reclaim expired leases with `SKIP LOCKED`; make stage writes idempotent.

### R-05 - Provider timeout does not stop provider work

**Severity:** Medium/High for cost and resource exhaustion  
**Status:** Experimentally reproduced

`document_lab/service.py:822-841` uses `ThreadPoolExecutor`, returns/raises on `future.result(timeout=...)`, then calls `shutdown(wait=False)`. Python cannot kill a running provider thread.

Impact: request/job reports timeout while network or CPU work continues, consuming quota and capacity.

Recommended fix: require provider adapters with transport-level deadlines/cancellation. For untrusted or CPU-heavy work use a killable process/worker boundary; record late completions but never apply them after job terminal state.

### R-06 - Assistant quota race

**Severity:** High for cost controls  
**Status:** Experimentally reproduced

`assistant/service.py:318-346` counts answers and later inserts the next answer. The check and reservation are not atomic.

Impact: concurrent requests can exceed daily/monthly limits and provider budgets.

Recommended fix: reserve quota atomically in Redis or a PostgreSQL counter row before provider work; refund only for explicitly non-billable failure classes.

### R-07 - Assistant evidence retention can be indefinite

**Severity:** Medium/High for retention promises  
**Status:** Experimentally reproduced

`assistant/service.py:437-447` deletes old evidence packets only when not referenced by an answer. No expiry/deletion of the referencing answer is applied in the same retention sweep.

Impact: evidence payloads can outlive the configured audit retention indefinitely.

Recommended fix: define one retention contract for conversations, answers and packets; either delete/compact expired answers first or detach them to a minimal audit record.

### R-08 - Community moderation identifier mismatch

**Severity:** Medium  
**Status:** Experimentally reproduced

Member responses expose `CommunityPreference.public_id`, but suspension/reinstatement calls `session.get(CommunityPreference, payload.user_id)`, which expects the internal user ID.

Impact: admins cannot reliably moderate the identifier displayed by the API, and internal identifiers may be required unexpectedly.

Recommended fix: rename schema field to `member_id` and resolve through `CommunityPreference.public_id`; never expose or require internal tenant user IDs for moderation.

### R-09 - Source check and lease completion are split commits

**Severity:** Medium  
**Status:** Experimentally reproduced

`source_monitor.py:417-435` records a source check through the service and subsequently calls `complete_source_monitoring()`, which commits separately.

Impact: the check/hash can be durable while the lease remains set. Work can appear failed and later be repeated after lease expiry.

Recommended fix: record check, update source freshness/hash, clear lease and schedule next run in one transaction, guarded by a lease token/fencing value.

## 5. Production and scaling bottlenecks

| Finding | Source evidence | Risk at scale |
| --- | --- | --- |
| Synchronous direct ingestion | `process_now: bool = True`; route executes service inline | Request timeout, duplicate retry, tied-up API workers |
| Serial source/objective extraction | service loops over sources and all objectives | Model latency/cost multiplies; poor throughput |
| Matching loads broad catalogue | matching service/repository behavior | Memory and transaction size grow with catalogue |
| Assistant wildcard search | `%token%` `ILIKE` on several columns | Sequential scans/poor relevance without suitable indexes |
| Assistant limits before trust filtering | `assistant/service.py:480-497` | Good records can be omitted while rejected records consume candidate slots |
| Global synchronous assistant retention | `purge_expired_data()` sweep | Long maintenance locks/runtime |
| Applications export N+1 | `command_service.py:612-622` | One event query per application |
| Community moderation/read expansion | service-level per-object access patterns | High query count for large feeds/report queues |
| Document history fan-out | `DocumentLabPage.tsx:37-45` | One API request per version |
| Generic readiness checks only PostgreSQL | `core/health.py:24-27` | Router may accept work when Redis/workers/storage/providers are unavailable |
| Engine tuning limited to `pool_pre_ping` | `db/session.py:15` | Pool saturation behavior is deployment-default dependent |
| Reminder “delivery” is a DB transition | `cli/dispatch_reminders.py:20-69` | Product can count delivery without an external notification channel |
| Graph flags unused | flags in `core/config.py`; no runtime references found | Operators may believe rollout toggles control behavior when they do not |
| Legacy and graph models coexist | `opportunities/models.py`, `graph_models.py` | Dual truth, projection loss and migration complexity |

## 6. AI and extraction production blockers

- The Crawlee adapter is still a secure bridge; multi-page queue parity is incomplete.
- Playwright is not wired as a controlled catalogue acquisition fallback.
- Docling/layout-aware table extraction is not implemented.
- Objective calls remain broader and more serial than the blueprint target.
- Expanded review-only extraction cannot materialize through the legacy graph boundary.
- `MextGraphMaterializer` includes MEXT/Japan/Tokyo defaults and MEXT-labelled source titles; it is not a universal materializer.
- The compatibility helper `_crawler_child_matches_root()` only enforces an MEXT marker when the root itself contains MEXT/Monbukagakusho, so it is not proof of universal source identity.
- Assistant remote providers deliberately remain unavailable; the default is deterministic.
- Document provider always returns unavailable.
- Full protected gold-suite evidence for MEXT, Open Doors, CSC, GKS/DAAD and Erasmus Mundus is absent.

## 7. Readiness and deployment gaps

### 7.1 Health/readiness

`/health/ready` proves only database connectivity. Separate endpoints expose reminder/operational health, but the deployment needs an aggregate gate aligned with enabled capabilities:

- PostgreSQL migration/current schema;
- Redis;
- object storage;
- scanner;
- document worker freshness;
- catalogue worker freshness and queue age;
- Azure extraction provider credentials/quota when enabled;
- browser worker when browser fallback is enabled.

### 7.2 Container/worker mismatch

The base Compose scanner/API readiness expectations are not a complete production topology. The blueprint correctly requires separate static, browser, document and extraction workers with least privilege.

### 7.3 Missing execution evidence

Infrastructure definitions are not proof of:

- a successful Azure staging deployment;
- database migration on the exact release artifact;
- rollback;
- point-in-time restore;
- backup restore;
- multi-tenant smoke testing;
- load, stress, spike or soak performance;
- budget/alert behavior;
- browser/network isolation.

All remain required release evidence.

## 8. Security threat assessment

### Controlled reasonably well in code

- SSRF and redirect abuse.
- Unsafe production configuration.
- token theft/reuse containment.
- cross-tenant database access through forced RLS.
- automatic publication of model output.
- high-risk feature accidental enablement.
- private Document Lab/public catalogue conceptual separation.

### Requires deployment proof or additional controls

- network-level egress deny remains required even with application URL checks;
- browser worker sandbox, resource caps and secret isolation;
- malware scanner availability and quarantine behavior;
- document conversion archive/decompression limits for the future Docling path;
- stored-XSS regression tests on all source excerpts and review UI;
- secret/log redaction under real telemetry exporters;
- public/private retrieval corpus separation tests;
- managed identity and least-privilege Blob permissions;
- admin step-up around ingestion, approval and publication in the final workflow.

## 9. Release gates

### P0 code gates before any live extraction worker

- Fix R-01, R-02, R-03, R-04, R-06 and R-08.
- Make ingestion queued/idempotent by default.
- Keep all Crawlee network traffic on the safe fetch path and pass parity/SSRF tests.
- Add lease fencing for source monitoring and catalogue jobs.
- Add capability-aware readiness.
- Prove database migration on PostgreSQL and Redis fail-closed behavior.

### P0 catalogue gates before public records

- Canonical block citations and layout-aware complex document fixtures.
- Correct cycle/route/degree/programme/subject/document ontology.
- Bundle-level completeness with zero unresolved conflict in ready records.
- Universal graph proposal/approval transaction.
- No automatic publication.
- MEXT, Open Doors and CSC protected acceptance first; remaining blueprint families before full launch.

### Environment gates

- Exact release commit passes CI and frontend build.
- Staging deploy and smoke tests.
- rollback rehearsal;
- PITR/restore proof;
- queue retry/dead-letter exercise;
- tenant isolation smoke test;
- load/spike/soak evidence;
- budget/alert validation;
- signed operator launch checklist.

## 10. Recommended remediation order

1. **Correctness and privacy:** beta expiry, atomic profile versioning, durable deletion, job leases, quota reservation, public moderation identifier.
2. **Extraction critical path:** queued acquisition, safe Crawlee bridge, evidence blocks, Docling, objective routing, scoped completeness.
3. **Approval boundary:** universal graph migration and transactional review approval.
4. **Readiness:** aggregate dependency health, dead-letter operations, telemetry and runbooks.
5. **Scale:** FTS retrieval, batch exports, document-history aggregation, matching pagination/batching and pool tuning.
6. **Release proof:** protected families, staging, restore, rollback and soak.

## 11. Final production disposition

The repository is suitable for continued controlled development and internal review. It should remain **no-go for a public 500-record launch** until P0 correctness defects, universal graph approval, multi-family extraction gates and real environment evidence are complete.

The fastest safe milestone is a review-only extraction worker in staging next week. That can be followed by a limited closed beta after reliability fixes and two/three-family protected proof. Full catalogue launch should follow the blueprint’s five-family and 500-reviewed-record gates rather than a date-only promise.
