# Azure invite-only beta foundation

This directory is the deployment contract for the first Azure environment. It
is deliberately separate from local Docker Compose: Docker remains the local
development environment and is never used to host beta data.

## Target architecture

- One resource group for `staging` and a separate one for `beta`; never share
  databases, Key Vaults, storage, or credentials between them.
- Azure Container Apps runs the API with external HTTPS ingress and the free
  platform domain. It starts at one replica and can increase only to the
  approved beta limit.
- Azure Database for PostgreSQL Flexible Server runs in a private delegated
  subnet with backups and point-in-time restore enabled. The API role and the
  migration role are separate database accounts.
- Azure Managed Redis is the shared rate-limit store. The foundation configures
  TLS 1.2+, an encrypted-only Redis database on port 10000, private endpoint,
  private DNS, and disabled public network access.
- Azure Container Registry stores immutable application images. Its admin user
  stays disabled; managed identities receive pull permission.
- Azure Key Vault stores every runtime secret. GitHub Actions uses OIDC, not a
  long-lived Azure password.
- Log Analytics and Azure Monitor receive only redacted operational telemetry.

Document Lab and Community stay disabled in the first Azure cohort. They are
not partly enabled and need separately approved storage/scanning and moderation
rollouts.

## Required release values

Values marked **secret** are created in Key Vault, never committed to Git or
placed in GitHub repository secrets.

| Setting | Source | Notes |
| --- | --- | --- |
| `APP_DATABASE_URL` | Key Vault (**secret**) | Limited API database role. |
| `APP_MIGRATION_DATABASE_URL` | Key Vault (**secret**) | Separate migration-only role; only the migration job receives it. |
| `APP_JWT_SECRET` | Key Vault (**secret**) | Newly generated, 32+ random characters. |
| `APP_RATE_LIMIT_REDIS_URL` | Key Vault (**secret**) | TLS `rediss://` URL only. |
| SMTP username/password | Key Vault (**secret**) | Approved transactional sender, verification tested. |
| `APP_CORS_ORIGINS` | deployment config | Exact HTTPS beta origin only. |
| `APP_TRUSTED_PROXY_MODE` | deployment config | `azure-container-apps`; do not set trusted proxy IPs. |
| WebAuthn RP/origin | deployment config | Exact beta domain and HTTPS origin. |
| Feature gates | deployment config | Community and Document Lab are `false`; Assistant is off. |

`application.bicep` forces `APP_ASSISTANT_ENABLED=false`,
`APP_DOCUMENT_LAB_ENABLED=false`, and `APP_COMMUNITY_ENABLED=false`. Assistant
limits stay deployed while it is off: 30 requests/day, 300/month, and 12/minute
per user. Turning a feature on requires a separately reviewed template change,
staging proof, and product-owner approval.

## Deployment artifacts and access boundaries

| Artifact | Responsibility | Identity and secret boundary |
| --- | --- | --- |
| `foundation.bicep` | Network, PostgreSQL, Redis, Key Vault, ACR, logs, identities | No app secrets are accepted or emitted. |
| `secret-access.bicep` | Per-secret Key Vault RBAC after bootstrap | Runtime gets API/Redis/JWT/SMTP; migration gets only migration URL. |
| `migration-job.bicep` | One-off Alembic job | Separate identity/database role; 30-minute timeout; no retry. |
| `application.bicep` | API revisions, ACR pull, Key Vault references, probes | Runtime identity only; previous revision remains a rollback path. |
| `scheduled-jobs.bicep` | UTC source monitor, reminder dispatch, retention | Created only after API readiness. |
| `cost-guardrails.bicep` | Subscription monthly cost budget | Tags scope staging and beta together. |

Do not place runtime secret values in Bicep parameter files, GitHub secrets,
workflow logs, or chat. With the Key Vault public endpoint disabled, an
authorized operator must bootstrap secrets through a private-network session
after the foundation exists. GitHub-hosted runners cannot read or write the
vault; that is intentional.

The bootstrap operator creates these versionless secret names only after the
limited PostgreSQL roles and Redis connection are tested:

- `app-database-url`
- `app-migration-database-url`
- `app-jwt-secret`
- `app-rate-limit-redis-url` — use the normal
  `<cache>.<region>.redis.azure.net:10000` hostname, never the private-link
  hostname.
- `app-smtp-username`
- `app-smtp-password`

Run `secret-access.bicep` only after those secrets exist. It grants access at
individual-secret scope rather than blanket vault read access.

## OIDC and GitHub environments

Create a federated credential for each protected GitHub Environment:
`azure-staging` and `azure-beta`. Scope each to its exact repository and
environment. Store only `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and
`AZURE_SUBSCRIPTION_ID` as GitHub Environment variables. They are identifiers,
not client secrets; do not create an Azure client secret.

The deploy identity needs only ACR push plus deployment rights on its isolated
resource group. It must not receive Key Vault Secrets User, Owner, or
subscription-wide Contributor. Protect `azure-beta` with a separate human
approval from staging.

`azure-application-deploy.yml` requires an explicit typed confirmation and:

1. builds a staging digest, or for beta downloads a successful staging provenance artifact and
   imports that exact digest into the isolated beta registry;
2. runs candidate-binary and migration-policy preflight before the rolling-safe expand migration;
3. deploys a deterministic candidate revision while the prior revision retains 100% traffic;
4. exercises readiness, authentication/Redis, catalogue, Applications, and User-B read/update/delete
   tenant attacks against the candidate-only FQDN;
5. deploys compatible jobs, shifts traffic only after smoke succeeds, and uploads immutable staging
   provenance for a separately approved beta promotion.

Beta never builds from a branch or accepts an operator-supplied image string: it consumes a
repository/run-bound staging artifact and imports that exact digest. Pre-promotion failure leaves
the stable revision at 100% and the candidate at zero. PostgreSQL changes must be additive and
prior-release compatible; destructive contract migrations use a separate later release.

Set these additional non-secret values as protected GitHub Environment variables
for both environments: `APP_SMTP_FROM`, `APP_SMTP_HOST`,
`APP_BETA_PRODUCT_OWNER_CONTACT`, `APP_BETA_SUPPORT_CONTACT`,
`APP_BETA_MODERATION_CONTACT`, `APP_BETA_DATA_QUALITY_CONTACT`, and
`APP_BETA_INCIDENT_CONTACT`. SMTP credentials remain Key Vault secrets. The
beta environment enables invitations only after its approval; staging keeps
invitation beta disabled for smoke tests.

Also provision two dedicated, non-privileged staging smoke students as protected Environment
values `SMOKE_USER_A_EMAIL`, `SMOKE_USER_B_EMAIL` and secrets `SMOKE_USER_A_PASSWORD`,
`SMOKE_USER_B_PASSWORD`. They must contain no real applicant data. The release fails closed when
these values, GitHub Environments, required reviewers, or OIDC bindings are absent.

## Cost guardrail before provisioning

Deploy `cost-guardrails.bicep` at the **Student Ambassadors Visual Studio
Enterprise subscription** scope before any foundation resource. Confirm in the
portal that its budget currency is MYR first: budgets use billing currency and
the template cannot safely convert currencies. Feed the Azure-reported value to
`python scripts/validate_budget_currency.py --expected MYR --observed <AZURE_VALUE> --amount 500`
and pass `confirmedBillingCurrency=MYR` to Bicep only when it succeeds. With a MYR 500 monthly budget,
the template alerts at MYR 100 (warning), MYR 300 (review), MYR 500 (urgent),
and forecasted MYR 500. Budgets are alerts, not spend caps, so urgent must
trigger a human review/pause procedure.

## Deployment sequence

1. Confirm subscription, billing currency, service availability, and projected
   monthly cost. Deploy/verify the subscription budget, then create isolated
   staging and beta resource groups.
2. Deploy the foundation into each group. Confirm public access is disabled on
   PostgreSQL, Redis, and Key Vault.
3. Bootstrap database roles and Key Vault secrets through a private-network
   operator session; deploy `secret-access.bicep`.
4. Connect GitHub Actions through OIDC and restrict both GitHub Environments to
   reviewed maintainers.
5. Build and scan an immutable staging image, run its migration job, deploy the
   API revision and scheduled jobs, then exercise health, Redis, email,
   invitations, passkeys, rollback, and restore in staging.
6. Promote the exact recorded digest to beta only after all staging release
   gates and a separate human approval. Complete staff pilot before Cohort A.

## Before provisioning

The Azure subscription must be active and the student credit visible in the
portal. Select Southeast Asia only after confirming it supports Container Apps,
PostgreSQL Flexible Server, Azure Managed Redis, and the data-residency
requirements. Do not purchase a custom domain: use the free Container Apps
domain until an explicit product decision changes that policy.
