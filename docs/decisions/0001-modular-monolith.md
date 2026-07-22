# ADR 0001: Start with a modular monolith

- Status: Accepted
- Date: 2026-07-18

## Context

The product needs relational integrity, structured search, matching, retrieval,
and an assistant, but has no measured scale or production traffic yet.

## Decision

Use FastAPI modules inside one deployable application and PostgreSQL as the
primary store. Keep domain services independent of HTTP and keep persistence
behind small repository interfaces where that improves testing.

## Consequences

- One transaction can safely publish an opportunity and its provenance.
- Local development, testing, and Azure deployment remain understandable.
- Module boundaries create a migration path if a measured bottleneck later
  deserves a separate service.
- Independent scaling and fault isolation are deferred.

## Alternatives considered

- Microservices: rejected for MVP operational cost and distributed consistency.
- Document database: rejected because eligibility, provenance, and tracking are
  highly relational and need constraints.
- Separate vector database: deferred until retrieval evaluation demonstrates a
  need beyond PostgreSQL full-text search and pgvector.

