# Slice 02: Source-first opportunity catalog

## Goal

Create the first reliable scholarship data backbone: admins can add opportunities with structured funding fields and official source provenance, while students only see records that have been officially verified.

## Acceptance criteria

- Admin-only endpoints can create and review opportunities.
- Public endpoints hide drafts, expired records, and unverified sources.
- Every public opportunity includes an official source URL and last verification status.
- Funding is stored in structured fields, not as a single vague description.
- Duplicate opportunities are blocked by provider, name, country, and intake year.
- Tests cover authorization, publication guard, filtering, duplicate detection, and validation.

## Known limitations

- This slice supports manual admin entry only.
- Source excerpts are stored, but semantic retrieval is not implemented yet.
- Verification is manual; automated source monitoring belongs to a later phase.
