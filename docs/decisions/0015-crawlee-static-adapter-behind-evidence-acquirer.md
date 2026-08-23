# ADR 0015: Crawlee static adapter behind EvidenceAcquirer

- Status: Accepted (Phase 1b.1 scaffolding)
- Date: 2026-08-23
- Depends on: ADR 0014
- Blueprint: Scholarship Intelligence Platform §5

## Context

Phase 1a introduced `EvidenceAcquirer` with `LegacySafeEvidenceAcquirer` as the
default. The engineering blueprint selects Crawlee for Python as crawl
orchestration (static HTTP first). Product code must not import Crawlee
directly. Every network request must continue to honour the existing
HTTPS / DNS-IP / robots / redirect / MIME / byte policy boundary.

## Decision

1. Crawlee is an **optional** dependency (`[project.optional-dependencies]
crawlee`), not a required runtime dependency for the application image by
   default.
2. A factory helper may select a Crawlee-labelled adapter only when explicitly
   requested **and** the optional package is installed.
3. **Phase 1b.1 (this change):** the optional adapter still performs single-URL
   `acquire()` through `SafeSourceFetcher`. This preserves the security
   boundary while the interface and packaging path are proven.
4. **Phase 1b.2 (future):** implement a custom Crawlee `HttpClient` (or
   equivalent security adapter) so multi-page orchestration can use Crawlee
   queues while every byte still passes the same policy checks. Only then may
   production workers opt into Crawlee for catalogue acquisition.
5. Browser (Playwright) acquisition remains disabled until Phase 2 gates.
6. Default `default_evidence_acquirer()` remains the legacy safe adapter.

## Non-goals

- Making Crawlee the default in CI or production images.
- Bypass of `SafeSourceFetcher` / URL policy.
- Multi-page Crawlee crawl replacement of `BoundedOfficialSiteCrawler` in this
  slice.
- Docling, OCR, bulk 500 load, or auto-publish.

## Consequences

- Operators can install `crawlee` extras without changing default behaviour.
- Security reviewers can inspect a clear two-step path: packaging/interface
  first, then network client substitution with SSRF regression tests.
- Risk of shipping an unvetted alternate HTTP stack in the same PR as the
  interface is avoided.
