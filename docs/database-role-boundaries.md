# Production database role boundaries

This document defines the database trust boundary required by the private-domain
PostgreSQL row-level-security policies introduced in migration `20260814_0036`.
It is a security control, not optional naming guidance.

## Roles

Production uses three different database credentials.

| Login | Used by | RLS behavior | Required privilege profile |
| --- | --- | --- | --- |
| migration administrator | one-off Alembic job only | administrative/bypass as required for DDL | schema migration only; never exposed to API/workers |
| API runtime login | public FastAPI Container App | constrained by tenant RLS | `NOSUPERUSER`, `NOBYPASSRLS`, normal application DML only |
| `scholarship_worker` | private scheduled Container Apps Jobs | explicitly permitted cross-tenant by policy | `NOSUPERUSER`, `NOBYPASSRLS`, only DML needed by scheduled jobs |

The **database login name `scholarship_worker` is intentional**. Migration
`0036` recognizes that exact PostgreSQL `current_user` for private batch jobs.
Do not reuse that login for the HTTP API, developer access, reporting tools, or
interactive administration.

## Key Vault separation

Use distinct secrets:

```text
app-database-url            -> API runtime database login
app-worker-database-url     -> scholarship_worker login
app-migration-database-url  -> migration/DDL login
```

Azure scheduled-job infrastructure creates a separate `${resourcePrefix}-worker-id`
managed identity. That identity may read `app-worker-database-url` but must not
be granted read access to `app-database-url` or `app-migration-database-url`.
Likewise, the public API runtime identity must not receive the worker or migration
database secret.

The actual passwords/connection strings are created through the approved private
bootstrap procedure and never committed to Git, Bicep parameter files, Actions
logs, tickets, or documentation.

## API tenant context

After an access token is authenticated, the request-scoped SQLAlchemy Session
sets this transaction-local PostgreSQL setting:

```sql
app.current_user_id = <authenticated user UUID>
```

It is applied with `set_config(..., true)`, making it transaction-local. When a
service commits and a new transaction begins within the same request Session,
the SQLAlchemy `after_begin` listener reapplies the authenticated user ID.
Connection-pool reuse therefore cannot carry Student A's tenant context into
Student B's request.

The API continues to use explicit owner predicates such as:

```text
WHERE user_id = authenticated_user.id
```

RLS is a second boundary for programming mistakes. It is not a replacement for
application authorization.

## Private tables protected by RLS

Direct owner policies cover:

- `student_profiles`
- `saved_opportunities`
- `applications`
- `application_notification_preferences`
- `match_evaluations`
- Assistant conversations, evidence packets, answers, feedback, preferences
- Document Lab assets, versions, extractions, consents, analyses, jobs
- application/document links

Parent-derived policies cover:

- application tasks, reminders, events, and document records
- match evaluation results and rule outcomes
- Assistant messages and citations
- Document Lab feedback items

Policies use `FORCE ROW LEVEL SECURITY` so accidental table ownership by a
runtime role does not silently bypass the boundary.

## Intentionally excluded tables

Authentication/session tables are not tenant-RLS protected because the system
must resolve the authenticated identity **before** tenant context exists. Those
tables remain protected by narrowly scoped authentication repository methods.

Public scholarship/catalogue tables are intentionally shared.

Community posts/replies and community identity data are not folded into these
private policies because the feature intentionally supports cross-user public
visibility and moderation. Community remains separately feature-gated; its
future public-profile/private-preference split should be designed before adding
RLS there rather than applying a policy that breaks legitimate reads.

Operational health and audit history are also separate trust domains.

## Bootstrap requirements

Before applying migration `0036` in staging/beta:

1. Create the restricted API database login used by `app-database-url`.
2. Confirm it is `NOSUPERUSER` and `NOBYPASSRLS`.
3. Create the `scholarship_worker` login.
4. Confirm it is also `NOSUPERUSER` and `NOBYPASSRLS`; cross-tenant access comes
   only from the explicit worker clause in the policies.
5. Grant each login only the schema/table/sequence privileges its workload needs.
6. Store the three connection URLs in their distinct Key Vault secrets.
7. Confirm the API managed identity cannot read either privileged worker or
   migration DB secret.
8. Confirm the worker managed identity cannot read API or migration DB secrets.
9. Run the PostgreSQL RLS smoke test before external beta traffic.

Never make the API login a superuser, table-owner bypass role, or `BYPASSRLS`
role to fix an authorization error. Treat such an error as a release blocker.

## CI proof

CI upgrades a real PostgreSQL 16 service and then runs:

```text
python tests/postgres_rls_smoke.py
```

The smoke test creates disposable non-superuser roles and proves all three
properties on `student_profiles`:

1. Student A can see Student A's row.
2. Student A cannot read, update, or insert another student's row even when the
   SQL itself omits the application owner predicate.
3. The dedicated `scholarship_worker` role can perform the intended cross-tenant
   scheduled-workload read.

The normal pytest suite remains SQLite-backed for speed; it does not substitute
for this PostgreSQL-specific release gate.

## Mobile/API consequence

This boundary lives entirely behind the API. Future Android and iOS applications
use the same authenticated API and inherit the same database isolation without
embedding database credentials or reproducing authorization logic in mobile
clients.
