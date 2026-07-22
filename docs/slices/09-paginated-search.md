# Slice 09 — Paginated Search Responses

## Goal

Prepare opportunity search for frontend screens and larger datasets by returning
pagination metadata with public and admin opportunity list responses.

## Updated endpoints

```text
GET /api/v1/opportunities
GET /api/v1/admin/opportunities
```

Both endpoints now support:

- `limit`
- `offset`

`limit` is constrained to `1..100`. `offset` must be `0` or greater.

## Response contract

Opportunity list endpoints now return an envelope:

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Example Scholarship"
    }
  ],
  "pagination": {
    "total": 42,
    "limit": 20,
    "offset": 0,
    "count": 20,
    "has_next": true,
    "has_previous": false
  }
}
```

## Decision

Use `limit` and `offset` pagination first.

## Reason

Offset pagination is simple, easy to test, and enough for the current MVP. It is
also straightforward for a server-rendered frontend or a lightweight SPA.

## Alternative considered

Cursor-based pagination.

## Tradeoff

Cursor pagination is better for very large datasets and frequently changing
records, but it adds more complexity to the API contract. Offset pagination is
the right first step for this portfolio MVP.

## What changed internally

- Repository list methods now accept `limit` and `offset`.
- Repository count methods calculate total filtered results.
- Services wrap list responses in `items + pagination`.
- Public and admin routes expose `limit` and `offset` query parameters.

## What this teaches

- API response contract design
- Frontend-ready backend pagination
- SQL-backed total counts
- Separating internal repository lists from external API envelopes
- Backward-incompatible API changes and test migration

## Portfolio evidence

This slice shows that the backend is moving from prototype endpoints to
frontend-ready product APIs. Search results now include enough metadata to build
real pages, pagination controls, empty states, and result counts.

## Tests added/updated

- Public opportunity search returns `items` and `pagination`.
- Pagination reports total, count, limit, offset, `has_next`, and
  `has_previous`.
- Existing public and admin search tests were migrated to the envelope contract.

## Known limitations

- Saved-opportunity tracker lists are not paginated yet.
- No cursor pagination yet.
- No sort parameter yet.
- No page-number alias yet.

## Recommended next slice

Stage 10 should begin the minimal frontend. The backend now has enough stable
contracts for:

1. login/register screens
2. opportunity search page
3. opportunity detail page
4. profile form
5. match results page
6. saved tracker page
7. admin review/import page
