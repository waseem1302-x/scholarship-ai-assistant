# Phase 5 — Application Command Centre

## Scope

The command centre normalizes the legacy saved-opportunity tracker into private
application workspaces. It contains no AI advice, document-content analysis,
social features, or email delivery.

## Contract

`POST /api/v1/applications` creates one owner-scoped application for an active,
officially verified opportunity. The lifecycle is strictly:

`saved → preparing → ready_to_submit → submitted → decision_received → accepted|declined|withdrawn`.

Applications expose owner-scoped task, reminder, document-metadata, event,
dashboard, and export endpoints under `/api/v1/applications`. Lists are paginated
with `limit` and `offset`. `GET /applications/export` exports only the current
student's normalized application records and activity events. `DELETE
/applications/data` removes the current student's normalized workspaces and
legacy saved tracker records.

Document coordination stores only student-entered metadata: requirement state,
filename, declared content type and size, version label, review/expiry dates,
and student-marked completion evidence. It deliberately has no upload,
download, document-content, or document-analysis capability in Phase 5.

The command-centre dashboard separates blocked tasks from blocked applications
(an application is blocked when it has at least one blocked task). It also
surfaces urgent actions, approaching deadlines, source changes, submitted work,
and upcoming reminders.

## Data integrity and privacy

- Migration `20260812_0010` copies saved tracker deadlines, notes, submission
  state, outcomes, and all JSON checklist entries into normalized records.
- Generated tasks retain `is_generated=true`; users' tasks remain distinct.
- Task completion is student-provided evidence, never an assertion of official
  acceptance.
- Application events are append-only. Event metadata contains identifiers and
  field names, not notes, reminder text, or document metadata.
- Application updates use an expected version when the client supplies one. A
  stale save receives a conflict response and must be refreshed before retrying.
- Deletion removes the owner's normalized applications and legacy tracker
  entries. Export contains only that owner's normalized workspaces and event
  history. Reminder worker health is operational data and is excluded.
- `GET /applications/operational-report` is admin-only and returns only
  aggregate reminder delivery, overdue/open task, task-status funnel, and
  failure counters. It excludes every application, user, note, reminder text,
  document-metadata, and event-content field.
- Every application, task, reminder, document, event, and export query is
  filtered by the authenticated owner. Other students receive a 404.
- Reminder creation uses an idempotency key. The worker only transitions
  `scheduled` or `snoozed` rows to `delivered`, making retry delivery safe.

## Operations

Start the in-app reminder worker with:

```bash
docker compose --profile reminders up -d reminder-worker
```

The worker runs `python -m app.cli.dispatch_reminders` at the configured poll
interval. There is deliberately no email notification provider in Phase 5.
