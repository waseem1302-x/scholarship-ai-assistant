# Phase 9 threat model and exercise record

Status: release-gate template. Complete this document for the selected staging
and beta providers; do not replace the provider-specific review with generic
assumptions.

## Assets and boundaries

| Asset | Boundary | Primary protections | Residual-risk owner |
| --- | --- | --- | --- |
| Student identity and sessions | API, PostgreSQL, transactional email | password hashing, short access tokens, refresh rotation, CSRF, enumeration-safe account recovery | Security owner |
| Beta entry | invitation service and registration API | hashed one-time/email-bound codes, expiry, revocation, serialized cohort allocation, verified-email activation, versioned acceptance and audit events | Product owner |
| Administrator authority | passkeys, password re-authentication, step-up session | verified email, WebAuthn user verification, scoped short-lived step-up sessions, audit events | Security owner |
| Private document data | Document Lab, object storage, scanner/parser workers | owner scope, opaque keys, client encryption, SSE-KMS, scan-before-extract, retention/delete | Document Lab owner |
| Assistant/community content | dedicated product modules | no cross-domain retrieval, consent/gates, owner scope, redacted telemetry | Product/data-quality owner |
| Operations data | logs, health, alerting, backups | allowlisted fields, safe error classes, restricted access, documented backup expiry | Incident owner |

## Principal threats and required mitigations

| Threat | Mitigation and verification | Release condition |
| --- | --- | --- |
| Invitation theft or self-registration | Email-bound hashed codes, serialized capacity check, reservation until verified-email activation, revocation and closed-registration tests | Staff pilot records an expired/revoked invitation test |
| Account takeover | Email verification, secure cookie/CSRF, password reset without enumeration, token/session revocation | Email delivery and recovery procedure tested without exposing token values |
| Admin phishing or credential replay | WebAuthn passkey plus fresh password and scoped MFA step-up session | Every production admin has a tested passkey; recovery drill has two approvals |
| Cross-user private-data access | Owner-scoped services/queries and export/delete tests | Authorization regression suite passes |
| Malicious document/parser escape | Scan failure blocks extraction; isolated parser worker with resource limits and restricted egress | Platform evidence proves worker permits only database/object-store/scanner endpoints; red-team sample blocks parsing |
| Object-store disclosure | Opaque scoped keys, client encryption, managed KMS, least-privilege prefix role | Storage policy and KMS audit configuration reviewed |
| Telemetry disclosure | Allowlisted JSON logs, no payload/body logging, safe job error codes | Redaction test and hosted telemetry query reviewed |
| Provider outage or unsafe output | Server-side credentials, bounded timeouts, feature gates and kill switches | Disable/re-enable exercise recorded; remote provider approval attached if enabled |
| Restore/backup exposure | Isolated restore project, distinct credentials/prefix, workers disabled | Restore drill meets approved RPO/RTO and environment is destroyed afterward |

## Administrator passkey recovery

Passkeys are not reset by support through email, chat, or a self-service
password-only flow. When an administrator loses all passkeys:

1. The affected administrator opens a security incident through the published
   incident route and proves identity using the organization-approved process.
2. Two different authorized operators approve the recovery in the incident
   record. The record includes request ID, affected admin ID, approver IDs,
   time, reason, and the old credential IDsâ€”never credential material.
3. A break-glass operator deactivates the old administrator account/session,
   creates or reactivates the replacement account, requires verified email and
   a new passkey registration before any privileged mutation, and records the
   `admin_passkey_recovery` audit event through the approved operator process.
4. The incident owner reviews the audit trail and closes the recovery only
   after the replacement passkey and a MFA-backed step-up test succeed.

The two approvals are an organizational control because the product has no
second-person identity authority. A future automated recovery workflow must
store both signed approvals and create equivalent audit events before replacing
this procedure.

## Exercise evidence

Record date, release digest, environment, facilitator, participants, scenario,
timeline, safe request/trace IDs, decisions, communications, findings, owner,
due date, and closure. High-severity findings block the next invitation cohort.

- [ ] Account compromise and WebAuthn recovery tabletop
- [ ] Assistant/provider outage and kill-switch exercise
- [ ] Document Lab containment exercise (only if enabled)
- [ ] Source reliability and community moderation escalation (where enabled)
- [ ] Backup restore and migration rehearsal
