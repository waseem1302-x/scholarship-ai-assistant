# Slice 05 — Saved Opportunities and Application Tracker

## Goal

Let a student turn search and matching results into a personal application
workflow. The student can save an officially verified opportunity, add notes,
track status, manage checklist items, and remove the saved record later.

This slice intentionally avoids reminder delivery and WhatsApp/email
integration. Those features require privacy and external-service decisions that
belong after the core tracker is reliable.

## User value

Before this slice, the platform could recommend opportunities but could not help
students act on them. Now a student can maintain a lightweight application
pipeline:

- Interested
- Researching
- Preparing documents
- Waiting for recommendation
- Ready to apply
- Submitted
- Interview stage
- Accepted
- Rejected
- Withdrawn
- Expired

## Implemented backend behavior

- `POST /api/v1/saved-opportunities`
  - Saves one active, officially verified opportunity for the current student.
  - Rejects duplicate saves for the same student and opportunity.
  - Rejects draft, expired, archived, or unverified opportunities.
- `GET /api/v1/saved-opportunities`
  - Lists only the current student's saved opportunities.
  - Supports filtering by application status.
- `GET /api/v1/saved-opportunities/{id}`
  - Returns one saved tracker item only if it belongs to the current student.
- `PATCH /api/v1/saved-opportunities/{id}`
  - Updates status, personal notes, personal deadline, document checklist,
    recommendation-letter checklist, test checklist, submission date, and
    outcome notes.
- `DELETE /api/v1/saved-opportunities/{id}`
  - Removes the saved tracker item for the current student.

## Data model

New table: `saved_opportunities`

Important fields:

- `user_id`
- `opportunity_id`
- `status`
- `personal_notes`
- `personal_deadline`
- `document_checklist`
- `recommendation_letters`
- `test_requirements`
- `submitted_at`
- `outcome_notes`
- `created_at`
- `updated_at`

Important constraints:

- `user_id + opportunity_id` is unique.
- `status` is constrained to supported application states.
- Foreign keys cascade when a user or opportunity is deleted.

## Decision

For the MVP, saved opportunity and application tracking are stored in one table.

## Reason

The first useful version needs to be simple enough to understand, test, and
demo. A separate table for every checklist item, recommendation letter, reminder,
and outcome would add complexity before the workflow is proven.

## Alternative considered

Create separate normalized tables:

- `applications`
- `application_documents`
- `recommendation_letters`
- `test_requirements`
- `reminders`

## Tradeoff

The JSON checklist fields are less queryable than fully normalized tables, but
they keep the MVP small. When reminders, analytics, or detailed checklist
reporting become important, these JSON fields can be migrated into separate
tables.

## What this teaches

- User-owned data isolation
- Many-to-one tracking relationships
- Duplicate prevention with database constraints
- State-machine style status design
- The difference between MVP schema simplicity and long-term normalization

## Portfolio evidence

This slice shows that the project is not just a search API or chatbot. It now
supports a real student workflow: discovering an opportunity, saving it, and
tracking progress toward application submission.

## Tests added

- Student can save a verified opportunity.
- Student can track document, recommendation, and test checklist items.
- Student can update application status and filter tracker results.
- Student cannot save the same opportunity twice.
- Student cannot save unverified opportunities.
- Saved opportunities are isolated between students.
- Student can unsave an opportunity.

## Known limitations

- No reminder delivery yet.
- No email or WhatsApp notifications yet.
- Checklist items are stored as JSON for MVP simplicity.
- No frontend tracker screen yet.
- No analytics dashboard for application progress yet.

## Recommended next slice

Stage 6 should improve administration and data ingestion:

1. CSV/JSON import for opportunities.
2. Data-quality warnings.
3. Better duplicate detection.
4. Admin review workflow for extracted or imported records.
