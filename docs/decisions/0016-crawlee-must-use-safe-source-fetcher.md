# ADR 0016: Multi-URL acquisition and Crawlee must use SafeSourceFetcher policy

- Status: Accepted (Phase 1b.2a)
- Date: 2026-08-23
- Depends on: ADR 0014, ADR 0015
- Blueprint: Scholarship Intelligence Platform §5

## Context

Phase 1b.1 added an optional Crawlee-labelled factory that still delegates
single-URL `acquire()` to `SafeSourceFetcher`. Full Crawlee orchestration is
valuable for queues and concurrency, but Crawlee's default HTTP clients do not
implement this platform's trust boundary.

`SafeSourceFetcher` enforces (among other rules):

- HTTPS only; no credentials in URL
- DNS resolution checks blocking private/reserved targets
- Redirect validation with the same rules
- Peer address verification after connect
- robots.txt allow/deny (fail closed on unreachable robots when required)
- Accepted content types only
- Byte and timeout budgets
- Authentication destination rejection
- Minimum extractable evidence

## Decision

1. **Every acquisition network request** used by catalogue ingestion must pass
   through `SafeSourceFetcher` (or a future adapter that applies the same
   checks with equivalent regression tests).
2. **Phase 1b.2a:** introduce `SafeMultiUrlAcquisitionSession` for bounded
   multi-URL acquisition using only `EvidenceAcquirer` / `SafeSourceFetcher`.
   Budgets: max URLs, stop-on-error option, no parallel unbounded fan-out.
3. **Phase 1b.2b (later):** if Crawlee queues are adopted, a custom Crawlee
   `HttpClient` (or equivalent) must call into the same safe fetch path. Until
   that client exists and SSRF suites pass, production must not use Crawlee's
   stock HTTP client.
4. Default product path remains single-URL legacy safe acquisition.

## Non-goals

- Enabling Crawlee's Impit/Httpx/Curl clients against the public internet
- Playwright acquisition
- Unbounded crawl of an entire site
- Auto-publish or bulk 500-record load

## Consequences

- Multi-URL support can ship without waiting on Crawlee HTTP integration.
- Security review stays focused on one network implementation.
- Crawlee remains optional packaging until 1b.2b proves parity.
