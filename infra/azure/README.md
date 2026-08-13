# Azure invite-only beta foundation

This directory is the deployment contract for the first Azure environment. It
is deliberately separate from local Docker Compose: Docker remains the local
development environment and is never used to host beta data.

## Target architecture

- One resource group for `staging` and a separate one for `beta`; never share
  databases, Key Vaults, storage, or credentials between them.
- Azure Container Apps runs the API with external HTTPS ingress. It starts at
  one replica and can increase only to the approved beta limit.
- Azure Database for PostgreSQL Flexible Server runs in a private delegated
  subnet with backups and point-in-time restore enabled. The API role and the
  migration role are separate database accounts.
- Managed Redis is the shared rate-limit store. It must use TLS and a private
  endpoint or VNet-integrated endpoint before public beta traffic.
- Azure Container Registry stores immutable application images. Its admin user
  stays disabled; a managed identity receives only pull permission.
- Azure Key Vault stores every runtime secret. GitHub Actions uses OIDC, not a
  long-lived Azure password.
- Log Analytics and Azure Monitor receive only redacted operational telemetry.

Document Lab and Community stay disabled in the first Azure cohort. They are
not “partly enabled” and need a separately approved storage/scanning and
moderation rollout.

## Required release values

The first deployment uses these production settings. Values marked **secret**
must be created in Key Vault, never committed to Git or put in a GitHub
repository secret.

| Setting | Source | Notes |
| --- | --- | --- |
| `APP_DATABASE_URL` | Key Vault (**secret**) | Limited API database role. |
| `APP_MIGRATION_DATABASE_URL` | Key Vault (**secret**) | Separate migration-only database role; only the migration job receives it. |
| `APP_JWT_SECRET` | Key Vault (**secret**) | Newly generated, 32+ random characters. |
| `APP_RATE_LIMIT_REDIS_URL` | Key Vault (**secret**) | TLS Redis URL only. |
| SMTP settings | Key Vault (**secret**) | Approved transactional sender, verification tested. |
| `APP_CORS_ORIGINS` | deployment config | Exact HTTPS beta origin only. |
| `APP_TRUSTED_PROXY_MODE` | deployment config | `azure-container-apps`; do not set `APP_TRUSTED_PROXY_IPS`. |
| WebAuthn RP/origin | deployment config | Exact beta domain and HTTPS origin. |
| Beta owner contacts | deployment config | Named product, support, moderation, data-quality, and incident owners. |
| Feature gates | deployment config | Community and Document Lab are `false`. Assistant remains off until its evidence gate is recorded. |

## Deployment sequence

1. Create isolated Azure `staging` and `beta` resource groups in the approved
   region, set a budget alert, and grant least-privilege roles.
2. Create the private network, PostgreSQL, Redis, Key Vault, registry, logging,
   and Container Apps environment. Confirm public access is disabled on data
   services.
3. Create the two database roles through a one-off, auditable bootstrap job;
   store their URLs in Key Vault. Do not use the PostgreSQL administrator
   credential in the API.
4. Connect GitHub Actions to Azure with OIDC and restrict the production
   environment to reviewed maintainers.
5. Build and scan an immutable image, deploy the one-off Alembic migration job,
   then deploy the API revision and scheduled source-monitor, reminder, and
   retention jobs.
6. Test email verification, administrator passkey, invite redemption, rate-limit
   failure behavior, health checks, rollback, and a database restore in staging.
7. Complete the staff pilot before inviting Cohort A.

## Before provisioning

The Azure subscription must be active and the student credit visible in the
Azure portal. Select the region only after confirming it supports Container
Apps, PostgreSQL Flexible Server, Managed Redis, and the desired data-residency
requirements. Create a cost budget before any resource deployment.
