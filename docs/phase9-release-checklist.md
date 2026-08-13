# Phase 9 beta release checklist

Mark each item with evidence location, date, and accountable owner. A missing
or failed mandatory item is a no-go, not a waiver by implication.

## Mandatory repository evidence

- [ ] Backend, frontend, browser, lint/format, PostgreSQL/Alembic, and the
  HIGH/CRITICAL dependency/container vulnerability scan pass (or each finding
  has an approved, dated risk acceptance).
- [ ] Production configuration rejection tests pass: development JWT, wildcard
  CORS, local Document Lab storage, memory limiter, incomplete SMTP, missing
  named beta contacts, and missing WebAuthn RP/origins all fail startup.
- [ ] Redis limiter works across independent API instances and fails closed on
  store outage for auth, write, and high-cost routes.
- [ ] Invitation, verification, password-reset, session-revocation, MFA
  step-up/recovery, owner-scope, telemetry-redaction, and feature-gate tests pass.
- [ ] Enabled assistant/document/community release gates and kill switches pass.
- [ ] Migration/restore and load/accessibility results are attached.

## Mandatory external evidence

- [ ] Isolated staging and production accounts, databases, storage prefixes,
  provider projects, least-privilege roles, TLS edge, and secret manager reviewed.
- [ ] Managed database backup/PITR and restore drill meet RPO/RTO or have an
  explicit, dated risk acceptance.
- [ ] Approved transactional email, shared Redis, monitoring/on-call routing,
  and—if enabled—Document Lab storage/scanner/AI provider contracts are active.
- [ ] Privacy notice, terms, feature notices, data inventory, retention policy,
  and processor/legal review approved for the intended beta population.
- [ ] Product, support, moderation, data-quality, and incident owners accept
  the staff-pilot and cohort cap.

## Rollout evidence

- [ ] Staff pilot exercises sign-up/invitation, verification/reset, MFA,
  export/delete, source review, reminders, enabled features, alerting, rollback,
  and incident communications.
- [ ] Cohort A has a dated start, consented cap, daily safe-metric review, and
  no unresolved release-blocking incident.
- [ ] Cohort B increase has a separate owner approval based on Cohort A capacity
  and support/moderation results.
- [ ] Beta exit report records cohort count, enabled features, availability/error
  observations, source quality, accessibility, support themes, incidents,
  limitations, and recommendation. It does not make outcome claims.
