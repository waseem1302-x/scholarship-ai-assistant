# ADR 0002: Put auditable discovery leads before catalogue candidates

- Status: Proposed
- Date: 2026-08-19

## Context

The catalogue ingestion pipeline currently begins with a `SeedCandidate`. That
contract is appropriate for reviewed seeds because a scholarship identity is
already known before source acquisition starts. It is not a safe identity
boundary for autonomous web