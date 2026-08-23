# ADR 0014: Replaceable EvidenceAcquirer boundary

- Status: Accepted
- Date: 2026-08-23
- Baseline: `codex/scholarship-detail-extraction-v3` @ `d490dfdf2bc16ea6298086c9ba06c144c03600ae`
- Blueprint: Scholarship Intelligence Platform Engineering Blueprint §5

## Context

The platform already acquires official sources through `SafeSourceFetcher` and
`BoundedOfficialSiteCrawler`. The engineering blueprint selects Crawlee for
Python as the future crawl orchestration layer, with static HTTP first and
controlled Playwright fallback. Product code must not import a crawl vendor
directly. The production contract is an internal acquisition interface so the
engine remains replaceable without changing trust rules.

## Decision

1. Introduce `EvidenceAcquirer` as the internal acquisition protocol in
   `app/modules/catalogue_ingestion/evidence_acquirer.py`.
2. Preserve `SafeSourceFetcher` as the mandatory network-security boundary for
   every HTTP(S) request. No alternate network path is authorized by this ADR.
3. Ship `LegacySafeEvidenceAcquirer` as the default implementation: it wraps
   the existing safe fetcher and returns immutable acquisition records suitable
   for later artifact persistence.
4. Do **not** add Crawlee, Playwright-as-acquisition, Docling, OCR, or bulk
   catalogue throughput in this change. Those land in later phases behind the
   same interface after fixture and security gates pass.
5. Product and extraction code may depend on `EvidenceAcquirer` and the shared
   result types. They must not import Crawlee (or any future vendor) directly.

## Non-goals

- Automatic publication or changes to review-only v3 gates.
- Replacing `BoundedOfficialSiteCrawler` in this slice.
- Azure worker topology, Service Bus, or network-level egress deny lists.
- Semantic evidence-block normalization (Docling / block IDs).

## Consequences

- Acquisition becomes testable behind a protocol without live network I/O.
- A future Crawlee static adapter can implement the same protocol while still
  routing every request through `SafeSourceFetcher` (or an equivalent policy
  adapter that enforces the same HTTPS, DNS/IP, robots, redirect, MIME, and
  byte rules).
- Existing crawler and ingestion paths remain operational until explicitly
  migrated in a later PR.

## Alternatives considered

- Import Crawlee directly in service code: rejected; couples the product to one
  vendor and complicates security testing.
- Rewrite the crawler before introducing an interface: rejected; increases risk
  without a stable seam.
- Delay the interface until Crawlee lands: rejected; the blueprint requires the
  contract first so adapters remain swappable.
