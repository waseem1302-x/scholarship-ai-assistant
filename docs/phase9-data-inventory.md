# Phase 9 data inventory and retention map

This inventory is the deployment baseline. The product owner must append the
approved processor, hosting region, legal basis, and final retention/backup
window before beta enablement.

| Data class | Purpose and owning module | Primary storage | Default retention / deletion | Export path |
| --- | --- | --- | --- | --- |
| Account email, password hash, verified state, sessions | Identity and account security (`auth`) | PostgreSQL; password never reversible | Account closure deletes account/session records; security audit actor becomes null | `/auth/account/export` |
| Profile fields and match snapshots | Matching and readiness (`profiles`, `matching`) | PostgreSQL | Profile/account deletion; match snapshots have their own expiry | `/auth/account/export` |
| Applications, tasks, notes, reminders, document metadata | Personal command centre (`applications`) | PostgreSQL | User delete or `/applications/data` | `/applications/export`, `/auth/account/export` |
| Assistant questions, answers, citations, feedback | Consent-gated evidence support (`assistant`) | PostgreSQL | Configured history/feedback/audit retention; user delete | `/assistant/export`, `/auth/account/export` |
| Document names, bytes, extracted text, editorial feedback | Private Document Lab (`document_lab`) | Encrypted object storage plus encrypted PostgreSQL fields | Configured Document Lab retention; explicit delete also removes objects | `/document-lab/export`, `/auth/account/export` |
| Community pseudonym, posts, reports, blocks, bookmarks | Moderated optional discussion (`community`) | PostgreSQL | Community delete/account closure; moderation/audit records retain safe metadata | `/community/export`, `/auth/account/export` |
| Invitations and beta notice acceptance | Beta access/consent (`beta`) | PostgreSQL | Invitation expiry/revocation; legal acceptance deleted with account | Account export identifies accepted notice versions once approved |
| Safe admin/security audit events | Security and content moderation | PostgreSQL | Approved audit retention; no private bodies/tokens; actor set null on account deletion | Not included in personal product exports |
| Operational logs, metrics, traces | Reliability and incident response | Approved monitoring provider | No request/response bodies or private content; final retention set by owner | Not a user-content export |
| Backups | Recovery only | Encrypted managed database/object-store backups | Normal backup expiry; deletion is not instant in retained backup copies | Not directly downloadable |

## Account closure sequence

1. Student confirms current password at `DELETE /api/v1/auth/account`.
2. Document Lab objects/records are explicitly deleted first, even when the
   feature is disabled.
3. The account deletion cascades profile, applications, matching, assistant,
   Community, passkey, invitation, and acceptance records. Existing safe audit
   events lose their actor reference rather than retaining the deleted account.
4. The service records one safe closure event. Backups and approved immutable
   security records expire on their normal documented schedule.
