# Slice 08 — Expanded Structured Search Filters

## Goal

Improve opportunity discovery before adding semantic search or RAG. The platform
now supports richer database-backed filters for both public students and
administrators.

This keeps the search layer reliable, explainable, and testable.

## Public search endpoint

```text
GET /api/v1/opportunities
```

Public search still returns only opportunities that are:

- active
- attached to an official source
- officially verified

## Public filters added

- `country`
- `degree_level`
- `funding_type`
- `field`
- `nationality`
- `intake_year`
- `deadline_after`
- `deadline_before`
- `funding_coverage`
- `application_fee`
- `english_requirement`
- `verified_after`

Example:

```text
GET /api/v1/opportunities?field=Artificial&nationality=Pakistani&intake_year=2027
```

## Admin search endpoint

```text
GET /api/v1/admin/opportunities
```

## Admin filters added

- `country`
- `degree_level`
- `status`
- `verification_status`
- `needs_review`
- `provider_query`
- `search_query`
- `deadline_after`
- `deadline_before`

The `needs_review=true` filter helps curators find draft, unverified,
needs-review, or conflicting-information records quickly.

## Decision

Use SQL-backed structured filters instead of semantic search for this stage.

## Reason

Structured fields should be reliable before we ask an AI system to retrieve or
summarize them. This also creates a strong baseline for later RAG evaluation.

## Alternative considered

Add vector search immediately over opportunity descriptions and source excerpts.

## Tradeoff

Structured search is less flexible for natural-language queries, but it is much
more predictable. Students can trust filters like country, deadline, nationality,
and intake year.

## What this teaches

- Query composition with SQLAlchemy
- Public vs admin search boundaries
- Database-backed filtering
- Review queue design for curators
- Building non-AI baselines before AI features

## Portfolio evidence

This slice demonstrates backend product maturity. The project now has real
verified records and useful structured discovery, instead of relying on a
generic chatbot or semantic search as the first search mechanism.

## Tests added

- Public search filters by field, nationality, intake year, deadline window,
  funding coverage, application-fee text, English requirement, and verification
  freshness.
- Admin search filters by status, review queue, provider query, source
  verification status, and free-text opportunity search.

## Known limitations

- Text filters are simple case-insensitive contains matches.
- Field and nationality are still stored as free-text fields, not normalized
  eligibility-rule rows.
- There is no pagination yet.
- There is no sorting option beyond the default deadline/name ordering.
- There is no semantic query parsing yet.

## Recommended next slice

Stage 9 should add pagination and response metadata for search results. After
that, the platform will be better prepared for frontend screens and larger seed
datasets.
