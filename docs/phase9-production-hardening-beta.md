# Phase 9 — Production hardening and invite-only beta

## Product decision and scope

Phase 9 turns the existing product capabilities into a safely operated,
invite-only beta. It is a launch-readiness phase, not a feature-expansion
phase. The goal is to make the catalogue, matching, application command
centre, citation-first assistant, Document Lab, and community safe to operate
with real student accounts and support requests when each feature is enabled.

The beta is deliberately closed. Access is granted by invitation, can be
paused without a product redeploy, and is capped at a number that the named
support and moderation owners can handle. A public launch requires a separate
product decision after the beta exit review.

The existing FastAPI modular monolith and PostgreSQL schema remain the
deployment unit. Phase 9 may add managed supporting services (secret manager,
shared rate-limit store, object storage, malware scanner, monitoring, and
transactional email), but does not split product domains into microservices.

## Definition of done

The phase is complete only when all of the following are true:

- A staging environment and the beta production environment are isolated, are
  reproducible from reviewed deployment configuration, and use distinct
  credentials, databases, storage locations, and provider projects.
- The production configuration fails closed for unsafe settings and has no
  development secrets, debug tokens, local Document Lab storage, or permissive
  CORS configuration.
- Production email verification, administrator MFA, shared rate limits,
  backups/restore, observability, and incident handling have been exercised.
- Every enabled high-risk feature has passed its feature-specific release gate.
- The invite-only beta has an accountable product owner, support owner,
  moderator owner, data-quality owner, and incident contact.
- The release checklist, exercise evidence, known limitations, and beta
  decision are recorded. No launch claim is made merely because code has
  merged.

## Release model and feature gates

All beta capabilities must be server-side configurable and default to the
safer state. Turning a capability on requires its gate; turning it off must be
possible promptly without a database migration.

| Capability | Default beta state | Enablement gate | Immediate kill switch |
| --- | --- | --- | --- |
| Verified catalogue, matching, and command centre | On for invited, verified students | Freshness/review queue has no unresolved release-blocking issue; reminder worker is monitored when reminders are offered | Put catalogue into maintenance/read-only mode; pause worker |
| Citation-first assistant | On only with the deterministic evidence-template provider | Citation evaluation passes and the current source corpus is fresh; any remote provider also passes privacy, security, cost, and output review | Disable assistant answers or revert to evidence-template mode |
| Document Lab | Off until all Document Lab production controls pass | Reviewed encrypted object storage, managed key, malware scanner, isolated no-network extraction, shared rate limit, retention exercise, and provider approval where analysis is offered | Set `APP_DOCUMENT_LAB_ENABLED=false` and stop workers |
| Community | Off until moderation coverage is staffed | Named moderator rota, report-response target, shared write limiter, content policy/notice review, and moderator exercise complete | Disable community writes or the community module |
| Invitation intake | Closed | Product owner approves beta cohort size and support capacity | Stop issuing/redeeming invitations |

The assistant never uses community content as evidence or training input.
Document Lab content, application notes, profile data, and account email
addresses remain outside the community and assistant retrieval boundaries.

## Workstream 1 — secure production foundation

### Environments, access, and deployment

- Provision separate staging and production accounts/projects. Production data
  must never be copied into development or test environments.
- Run the API, workers, database, scanner, and supporting services with
  least-privilege workload identities. The API database role cannot create
  databases or administer the server; workers receive only the permissions
  required for their queues and storage prefixes.
- Store JWT secrets, encryption keys, email credentials, provider keys, and
  database credentials in a managed secret store. Rotate each non-development
  secret before beta and prove that a rotation can occur without exposing it in
  logs or source control.
- Terminate TLS at a reviewed edge/proxy, redirect HTTP to HTTPS, and configure
  trusted proxy handling only for that edge. Keep HSTS, the existing CSP,
  secure cookies, CSRF checks, and an explicit CORS allowlist enabled.
- Build an immutable, versioned application image in CI; deploy the reviewed
  image digest rather than rebuilding on the production host. Generate a
  dependency/container vulnerability report and resolve or explicitly accept
  each release-blocking finding.
- Run Alembic as a single, logged deployment step before application workers
  receive traffic. Every migration needs an upgrade rehearsal on a restored
  staging backup and a documented rollback or forward-fix decision.

### Availability and recovery

- Use managed PostgreSQL with encrypted backups, point-in-time recovery where
  offered, and access restricted to workload and break-glass operator roles.
- Set initial beta recovery objectives of **RPO <= 24 hours** and **RTO <= 4
  hours**. If the selected host cannot meet them, reduce the beta scope or
  obtain an explicit product-risk acceptance before inviting users.
- Perform and record a restore drill: restore a representative backup into an
  isolated environment, run migrations, validate readiness, and confirm the
  restored service can read catalogue data without contacting production.
- Treat source-monitor, reminder, document, and retention jobs as independent
  monitored workloads. Each has a schedule, timeout, retry/idempotency policy,
  dead-job visibility, and an operator owner.

## Workstream 2 — identity, abuse prevention, and administration

- Configure a reviewed transactional-email adapter for verification and reset
  messages. Production responses must remain enumeration-safe and must never
  return verification or reset tokens to a browser, log, or API client.
- Require verified email before a student can join the beta or use features
  that create personal content. Define a support process for bounced email,
  inaccessible mailbox, and account recovery without staff learning a user's
  password.
- Add phishing-resistant administrator MFA using WebAuthn/passkeys, with a
  documented recovery process that requires two authorized operators or an
  equivalent auditable approval. Administrative mutations require a fresh
  password re-authentication **and** MFA step-up; recovery cannot silently
  bypass audit logging.
- Replace the in-process limiter with an atomic shared-store implementation.
  It must preserve limits by authenticated user and client IP for login,
  registration, assistant answers, Document Lab uploads, and community writes,
  return a correct `429` and `Retry-After`, and work across multiple API
  instances. Failure of the shared limiter fails closed for authentication and
  all write/high-cost routes; its health is observable.
- Use a durable invitation record with a bounded redemption policy, expiry,
  revocation, and safe audit event. It must not be possible to self-register
  into a closed beta through an undocumented client route.
- Review administrator roles, remove dormant accounts, test account/session
  revocation, and retain only content-free audit metadata needed for operations
  and security investigation.

## Workstream 3 — privacy, data governance, and high-risk processing

- Publish the beta privacy notice, terms, assistant disclaimer, Document Lab
  data-use notice, and community policy before their associated feature is
  enabled. Version and record consent where the existing product requires it.
- Maintain a data inventory that maps each personal-data class to its purpose,
  owning module, storage location, processor, retention period, export/delete
  route, and incident contact. Include database backups and operational logs in
  the inventory even when deletion from them is deferred to normal backup
  expiry.
- Verify that each existing domain export/delete operation is owner-scoped and
  that account closure has a documented orchestration path across profile,
  applications, assistant, Document Lab, and community records. Do not claim
  instant erasure from immutable security records or retained backups; state
  their retention bounds clearly.
- Configure redaction before enabling production telemetry. Logs, traces,
  error reporting, and alerts must exclude passwords, tokens, emails where not
  necessary, profile fields, application notes, document names/bytes/text,
  assistant prompts/answers, and community bodies.
- Complete a threat-model review for the deployed architecture, the selected
  email/provider/storage processors, invitation flow, MFA recovery, and
  incident pathways. High-severity unresolved findings are release blockers.

### Document Lab production gate

Document Lab must meet the existing architecture document in full. In addition,
the team must prove that storage objects use opaque, user-scoped keys; encryption
uses a managed production key; malware scan failure blocks extraction; parsers
run with no network and resource limits; and retention/delete removes both
metadata and objects. Any remote analysis provider requires a documented data
processing approval, server-only credential, fixed model/version, short timeout,
minimal payload, and a tested provider-disable procedure.

## Workstream 4 — observable, supportable operations

- Emit structured, redacted logs with timestamp, deployment version, request or
  trace ID, route class, status, latency, and safe error code. Provide a way to
  correlate a support case to safe identifiers without searching user content.
- Monitor service liveness/readiness, database connectivity, error rate,
  request latency, rate-limit/store failures, queue depth and age, job failures,
  backup success, certificate expiry, source-monitor freshness, reminder-worker
  freshness, document scan/extraction failure, and moderation backlog.
- Alert the named on-call contact on service unavailability, backup failure,
  database/storage exhaustion, sustained elevated errors, failed scheduled
  jobs, and a moderation queue that exceeds the approved response target.
  Alerts must carry safe metadata only.
- Publish lightweight operator runbooks for deploy/rollback, migration failure,
  secret rotation, provider outage, database restore, account compromise,
  data-export/delete request, unsupported assistant claim, Document Lab
  containment, source-data incident, and community moderation escalation.
- Run a tabletop incident exercise and one recovery exercise. Record the
  timeline, decision owner, communication path, gaps, and follow-up actions;
  closing the phase requires remediating high-severity exercise findings.

## Workstream 5 — quality, accessibility, and release evidence

The existing CI checks remain mandatory: backend tests, frontend unit tests,
production frontend build, lint/format checks, PostgreSQL/Alembic rehearsal,
and browser journeys. Phase 9 adds the following evidence:

| Area | Required evidence |
| --- | --- |
| Security | Dependency/container scan, configuration review, authorization/CSRF/session regression suite, shared-limiter multi-instance test, and administrator MFA/step-up tests |
| Data safety | Backup restore result, migration rehearsal result, export/delete boundary tests, telemetry-redaction test, and Document Lab production-gate test where enabled |
| Product correctness | Fresh catalogue review report, matching hard-rule suite, assistant citation/abstention evaluation, reminder/idempotency checks, and community moderation/visibility suite where enabled |
| Accessibility | Keyboard and screen-reader smoke test of sign-in, invitation/verification, catalogue, application tasks, assistant consent, Document Lab consent/upload where enabled, and report/moderation controls where enabled |
| Performance | Staging load test that covers browse/search, authenticated session refresh, a bounded write mix, and each enabled worker. Record p50/p95 latency, error rate, resource use, and tested concurrency; set capacity from observed results rather than an untested estimate. |

No beta release is permitted with a known cross-user exposure, a high-severity
unresolved security finding, failed restore drill, unavailable required email
delivery, missing named owner, or an enabled feature that has not met its gate.

## Beta rollout and decision gates

1. **Internal readiness.** Deploy staging, complete all workstream evidence,
   rehearse rollback and kill switches, reverify published catalogue records,
   and obtain written go/no-go approval from the product, security, and
   operations owners.
2. **Staff pilot.** Invite only staff/test accounts. Exercise registration,
   verification, reset, MFA, export/delete, source review, reminders, incident
   response, and every enabled feature in the production-like environment.
3. **Cohort A.** Invite a small consented cohort (recommended cap: 25 students)
   for at least seven days. Review support volume, source freshness, error
   rates, assistant abstentions/feedback, document failures where enabled, and
   moderation backlog daily. Do not use sensitive profile or document content
   as product analytics.
4. **Cohort B.** Increase only after the Cohort A exit review confirms no
   release-blocking incident and that support/moderation response targets were
   met. The product owner sets the new cap from observed capacity and can pause
   invites at any time.
5. **Beta exit.** Produce a transparent beta report: cohort size, enabled
   features, uptime/error observations, source-quality results, accessibility
   findings, support themes, incidents, limitations, and a recommendation to
   extend, pause, or plan public launch. These observations are not treated as
   statistically representative impact claims.

### Initial beta service targets

These are operating targets to measure, not pre-launch claims or contractual
SLAs:

- acknowledge a security or availability alert within 30 minutes during the
  published support window;
- acknowledge a community report within one business day when community is
  enabled, with an escalation path for imminent harm;
- investigate a source-quality report within two business days and remove the
  record from verified visibility immediately when the evidence is no longer
  reliable; and
- target 99.5% monthly availability for the API excluding announced
  maintenance, measured from independent health checks.

## Deliberate non-goals

- A general public launch, paid plans, broad marketing, growth experiments, or
  claims about scholarship outcomes.
- New recommendation algorithms, social features, assistant capabilities, or
  collection of additional sensitive data.
- A microservice rewrite, multi-region active-active deployment, or a promise
  of continuous moderation outside the published support model.
- Sending student data to a new AI provider or processor without the separate
  approval and release gate described above.

## Decisions that require product-owner authorization

Implementation cannot safely infer these choices:

1. Hosting region/platform and the legal/privacy review appropriate to intended
   beta participants.
2. Transactional-email, shared-store, monitoring, object-storage, scanner, and
   any remote AI-provider vendors, including budget and data-processing terms.
3. Beta cohort eligibility, invitation cap, support hours, moderator rota, and
   incident contacts.
4. Whether Document Lab, community, and any remote assistant provider are
   enabled in the first cohort.
5. Final privacy notice, terms, retention periods, backup-retention window, and
   recovery-objective risk acceptance.

## Delivery order

1. Confirm the authorized decisions and create the environment/data inventory.
2. Build staging, managed secrets, TLS/proxy, deployment pipeline, backups, and
   recovery verification.
3. Add shared limiting, email delivery, invitation control, and administrator
   MFA; test failure and recovery paths.
4. Complete Document Lab infrastructure only if it will be enabled; otherwise
   keep it off and verify its kill switch.
5. Add redacted observability, alerts, runbooks, load/accessibility/security
   evidence, and exercises.
6. Run staff pilot, then the gated invitation cohorts and beta exit review.
