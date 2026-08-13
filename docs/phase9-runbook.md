# Phase 9 operator runbook

This runbook is deliberately executable without exposing student content,
passwords, tokens, document data, or provider payloads. Complete the release
checklist before the first beta invitation and retain the completed record in
the approved operations repository.

## Deploy and migrate

1. Build the reviewed image in CI, scan it, and record the immutable digest and
   `APP_RELEASE_VERSION`.
2. Populate a protected environment using the selected platform secret manager.
   Never use `.env.example`, local Compose secrets, or development database
   credentials in staging/production.
3. Render the deployment before applying it:

   ```powershell
   docker compose -f compose.yaml -f compose.beta.example.yaml config -q
   ```

4. Run the one-off `migrate` service. Confirm it completes successfully before
   allowing API/worker traffic. Do not scale the migration service.
5. Deploy the API image digest and worker services. Confirm `/health/live`,
   `/health/ready`, `/health/operations`, and the platform's Redis/database
   checks are healthy.
6. If a migration fails, stop rollout, preserve only safe migration/log IDs,
   and use the migration's documented forward-fix or rollback decision. Do not
   manually edit production schema or delete migration records.

Student accounts created from an invitation reserve one invitation only. Email
verification activates the beta seat; before it, private-content creation is
blocked. Verify this with a staff pilot account before inviting the first
external cohort; recovery, export, and deletion remain available before
verification.

## Rollback and kill switches

- **Assistant:** set `APP_ASSISTANT_ENABLED=false`, deploy configuration, and
  confirm `POST /api/v1/assistant/answers` returns the safe unavailable state.
- **Document Lab:** set `APP_DOCUMENT_LAB_ENABLED=false`, stop document workers,
  revoke any affected provider credential, and preserve only job identifiers
  and safe audit IDs for investigation.
- **Community:** set `APP_COMMUNITY_ENABLED=false`; preserve moderation records,
  but do not inspect bodies unless the incident process authorizes it.
- **Catalogue/application maintenance:** set
  `APP_CATALOGUE_MAINTENANCE_MODE=true` to stop product writes while preserving
  public read paths. Pause invitation issuance with
  `APP_BETA_REGISTRATION_OPEN=false`.
- **Compromised secret:** rotate it in the secret manager, deploy, invalidate
  affected sessions/provider access where applicable, and record the incident.
  Never paste a secret into an incident ticket or log.

## Backup and restore drill

Target: RPO <= 24 hours; RTO <= 4 hours. The selected managed PostgreSQL
provider must supply encrypted backups and, where offered, point-in-time
restore. Before beta and at the approved cadence:

1. Restore a representative backup into a new, isolated project/network.
2. Use distinct credentials and object-storage prefix. Never point restored
   workers at production providers or scheduled jobs.
3. Run `alembic upgrade head`, then call the readiness endpoint and read only
   public catalogue records to validate the restore.
4. Record backup timestamp, restore start/end, deployment revision, migration
   revision, validation result, RPO/RTO observed, operator, and follow-up work.
5. Destroy the isolated restore environment using the hosting platform's
   recoverable/approved process once evidence is retained.

Use the reproducible local verification command only against an isolated
database URL. It deliberately refuses to run a restore; the managed hosting
platform must perform restoration so credentials and backup media never flow
through a developer shell:

```powershell
./scripts/verify-restored-environment.ps1 -DatabaseUrl 'postgresql+psycopg://...'
```

## Administrator passkey recovery

Follow the two-operator recovery process in the
[Phase 9 threat model](phase9-threat-model.md). Do not reset a passkey using a
password, email link, support request, or a single operator's approval. The
break-glass operator must revoke old sessions, require verified email and a new
passkey, and attach safe audit identifiers to the incident record.

## Scheduled job operations

- Enable `monitoring`, `reminders`, and `retention` for enabled beta features.
  Enable `documents` only after the Document Lab production gate is approved.
- Source monitoring, reminder dispatch, retention, and Document Lab jobs report
  started/completed/failed state to `/health/operations`. This stores only job
  name, timestamp, counters, and a safe exception class—not a source URL,
  email, document name/text, or provider message.
- Alert when a required job is stale beyond its approved cadence, has sustained
  failures, or when the shared rate-limit store or transactional-email health
  is unhealthy. Route alerts to the named incident contact with safe metadata
  only.

## Staging load evidence

Run the bounded read test only against staging, from an approved runner, before
each cohort increase. It contains no student content or credentials:

```powershell
python ./scripts/phase9_load_test.py --base-url https://staging.example.org --requests 200 --concurrency 20
```

Capture the JSON result with CPU/memory/database/Redis worker metrics from the
hosting platform. Record p50/p95, errors, concurrency, enabled features, and
the release digest. A separate disposable-account test may cover refresh and a
bounded write mix; do not put production credentials in the command, shell
history, or evidence artifact.

## Incident response

1. Acknowledge security/availability alerts within the published support window
   (target: 30 minutes). The named incident contact owns triage.
2. Stop the affected capability first; preserve deployment version, request or
   trace ID, safe audit IDs, and timestamps. Do not copy private content into
   tickets.
3. For a suspected unsupported assistant claim, disable the assistant if needed,
   remove the source from factual retrieval, add a regression case, and only
   re-enable after evidence review.
4. For source reliability, remove affected records from verified visibility and
   investigate within two business days.
5. For community reports, acknowledge within one business day while community
   is enabled; use the escalation process for imminent harm.
6. Run a blameless review with timeline, decision owner, communication route,
   impact, corrective actions, and closure approval. High-severity gaps block
   the next cohort increase.

## Required named owner record

Before `APP_BETA_ENABLED=true`, record the product owner, support owner,
moderation owner, data-quality owner, incident contact, support window,
moderator rota, approved cohort cap, privacy/terms version, and the selected
hosting/email/Redis/monitoring/storage providers. Production configuration
enforces the contact fields; vendor selection and legal approval require the
product owner's external authorization.
