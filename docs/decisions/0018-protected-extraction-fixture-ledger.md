# ADR 0018: Protected extraction fixtures require immutable source payloads

- Status: Accepted
- Date: 2026-08-24
- Applies to: catalogue extraction evaluations

## Decision

Protected MEXT and Open Doors evaluations are executable only when each source
fixture has immutable captured payload bytes, SHA-256 hashes, retrieval metadata,
and a reviewed expected outcome. A URL, current live response, normalized text
hash, or a synthetic example alone is not a protected fixture.

`tests/fixtures/catalogue_extraction/source_snapshot_ledger.v1.json` records
observed safe-acquisition snapshots so their identities cannot be silently
changed while the raw-fixture capture process is completed. Entries whose
`raw_fixture_path` is null are intentionally non-executable and keep the
corresponding protected gate blocked.

## Consequences

- Captured source bytes must be introduced through reviewed repository changes
  or approved private fixture storage, never replaced by live network access in
  unit tests.
- MEXT/Open Doors pass claims are forbidden until every required entry has an
  immutable fixture and a reviewed expected proposal/invariant set.
- A source hash change creates a new fixture version; it does not rewrite old
  evidence or historical expected outcomes.
