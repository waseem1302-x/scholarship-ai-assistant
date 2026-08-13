# Phase 9 requirement audit

Audit date: 2026-08-13
Scope: repository, local Compose deployment, configuration, CI, tests, and
existing operational documentation. This is a code-and-local-environment audit;
it cannot attest to a selected hosting provider, vendor contracts, legal review,
or a real-user beta.

## Baseline evidence

- Final local verification: backend suite passed (2026-08-13); focused beta
  invitation and full Alembic upgrade/rollback rehearsals passed, together
  with Ruff check, Ruff format check, and `git diff --check`. Frontend
  unit/build and 9 baseline browser journeys had passed before the final
  backend-only invitation correction and must be repeated from the immutable
  candidate image before release.
- Final candidate image `scholarship-ai-assistant@sha256:9e48937b39acdfa17177e77a825376656025c416ab1a01301b41f93107a20248`
  built successfully from the Bookworm base. Docker Scout indexed 212 packages
  and reported no fixed HIGH/CRITICAL findings (2026-08-13). The beta Compose
  overlay rendered successfully with non-secret verification values; it was
  not deployed against the existing local environment.
- Repeated final checks: 19 frontend unit tests, production frontend build,
  9 browser journeys, and the existing API's `/health/live` and
  `/health/ready` probes passed. The live local API remains deliberately on
  the pre-Phase-9 image/schema and is not deployment evidence for this
  candidate.
- Final regression after the data-rights/operational-health review: full
  backend suite, Ruff check, Ruff format check, and `git diff --check` passed
  (2026-08-13). Community and Document Lab kill switches preserve their
  owner-scoped export and deletion routes; operations health now exposes a
  safe boolean for transactional-email reachability.
- Production WebAuthn settings now reject non-HTTPS origins, credentials in an
  origin, path-bearing origins, and origins outside the configured relying
  party domain. The configuration regression test passed (2026-08-13).
- The beta overlay now explicitly leaves assistant, Document Lab, and Community
  disabled until their individual release gates are evidenced. Production also
  rejects an enabled assistant backed by any provider other than the reviewed
  deterministic evidence-template implementation; targeted tests and final
  Compose rendering passed (2026-08-13).
- The existing Docker Desktop CLI is available at
  `C:\Users\Admin\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe`.
  The existing `scholarship-ai-assistant-api-1` and
  `scholarship-ai-assistant-db-1` containers are healthy; no second Docker
  project was created.
- CI already runs frontend unit/build checks, backend tests, Ruff, PostgreSQL
  migration upgrade, and Chromium browser tests.
- The worktree already contains uncommitted Phase 7/8 work. Phase 9 changes
  must preserve it and be validated against it.

## Requirement-by-requirement status

| Phase 9 requirement | Existing evidence | Gap / Phase 9 action | Status |
| --- | --- | --- | --- |
| Isolated staging and beta production | Beta overlay removes the development DB and requires a distinct managed database URL, Redis, TLS edge, secrets, and named owners | Provision isolated accounts/projects and record their identities/permissions. | Partial |
| Fail-closed production settings | Production rejects debug, insecure cookies, HTTP/wildcard/empty CORS, missing trusted proxy, development secret, memory limiter, incomplete SMTP, and unsafe Document Lab settings | Deploy reviewed TLS edge and secret manager values. | Partial |
| Immutable release and migration procedure | Docker image builds frontend/runtime; migration is a one-off Compose service; CI upgrades PostgreSQL; runbook requires an immutable image digest | Build the candidate image, scan it, then record its digest/version and a staging migration result. | Partial |
| Backups, restore drill, RPO/RTO | Isolated restore verifier, evidence fields, and RPO<=24h/RTO<=4h runbook are provided | Managed PostgreSQL/PITR selection and an actual restore drill remain external release gates. | Partial |
| Transactional email | SMTP provider boundary, production validation, enumeration-safe responses, and no production debug tokens are implemented | Configure and exercise a reviewed external SMTP provider; record delivery/alert evidence. | Partial |
| Verified beta access and invitations | Durable hashed, email-bound, expiring, revocable single-use invitations reserve a seat at registration and activate it only after email verification; cohort allocation is serialized on PostgreSQL; legal acceptance and safe audit events are recorded | Conduct staff pilot and approved cohort rollout. | Partial |
| Administrator WebAuthn MFA plus fresh password | Administrator passkey registration/assertion, verified-email check, fresh-password + MFA single-use step-up, audit events, recovery procedure, UI and tests are implemented; production origin/RP validation fails closed | Enrol production administrators and exercise two-operator recovery in the selected environment. | Partial |
| Shared, atomic, fail-closed rate limiting | Redis-backed atomic limiter, safe store failure behavior, production validation, safe health endpoint, and Compose beta overlay are implemented | Validate the selected managed Redis across multiple deployed API replicas. | Partial |
| Feature gates and kill switches | Unified server-side gates control assistant, Document Lab, Community, maintenance/read-only mode, and invitation intake; Document Lab and Community export/delete remain available after a kill switch | Exercise enabled-feature gates and kill switches in staging with the named operators. | Partial |
| Document Lab production gate | Encrypted S3-compatible object-storage adapter, opaque keys, scanner adapter, isolated-parser configuration gate, consent, retention/delete boundary, and remote-provider approval gate are implemented | Provision and test the selected storage/scanner/parser isolation; a reviewed vendor is external. | Partial |
| Privacy notice, terms, data inventory | Versioned beta terms/privacy acceptance, notice pack, complete inventory, account export/closure orchestration, and backup/log disclosure are implemented | Obtain product/legal approval and publish the final external processor/region/retention details. | Partial |
| Redacted observability, metrics, alerts | Safe JSON log fields, request IDs, aggregate metrics, rate-limit health, worker health, alerting runbook, and redaction coverage are implemented | Configure hosted telemetry and on-call routing with approved vendor. | Partial |
| Worker reliability | Source, reminder, Document Lab, and retention jobs now record safe common health and have a Compose retention profile | Set each production schedule/cadence and alert policy in selected host. | Partial |
| Threat model and incident/runbooks | Phase 9 threat model, deploy/rollback/recovery/incident runbook, recovery and tabletop evidence templates are provided | Actual exercises require named owners and the selected environment. | Partial |
| Security, accessibility, performance evidence | CI runs dependency/container scanning; regression suites, production configuration, migration, feature-gate tests, load-test harness, and accessibility smoke checklist exist | Run load/manual accessibility checks in approved staging and attach evidence. | Partial |
| Controlled rollout and beta exit | Configurable cohort cap/pause, feature gates, release checklist, notices, rollout and beta-exit templates are implemented | Inviting people and collecting outcomes need product-owner authorization. | Partial |

## Implementation order

1. Establish the configuration and deployment policy that makes beta mode,
   feature gates, email, the shared limiter, and production safety explicit.
2. Deliver durable invitation control, email boundary, shared limiter, and the
   administrator MFA lifecycle, with schema migrations and API tests.
3. Add redacted observability, worker/recovery controls, account-closure/data
   governance, and Document Lab production configuration.
4. Extend React with clear, accessible beta/account/admin surfaces.
5. Run the full automated suite, migration rehearsal, Docker deployment checks,
   and scripted restore/load checks; record the release evidence.
6. Hand off the remaining owner-authorized decisions and live exercises using
   the supplied runbooks/checklists. Those are hard Phase 9 release gates, not
   claims this repository can fabricate.
