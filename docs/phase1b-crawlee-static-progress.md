# Phase 1b progress — Crawlee static adapter

- Date: 2026-08-23
- Baseline: `codex/scholarship-detail-extraction-v3` (1a #34 + 1b.1 #36 merged)
- Active branch: `codex/phase1b2-crawlee-secure-bridge`

## Completed

| Slice | Status |
| --- | --- |
| 1a EvidenceAcquirer + LegacySafeEvidenceAcquirer | Merged #34 |
| 1b.1 optional Crawlee factory (safe delegate) | Merged #36 |
| 1b.2a multi-URL session via SafeSourceFetcher | **This branch** |
| ADR 0016 security contract | **This branch** |

## Remaining

| Slice | Status |
| --- | --- |
| 1b.2b custom Crawlee HttpClient calling SafeSourceFetcher | Not started |
| Multi-page parity vs BoundedOfficialSiteCrawler fixtures | Not started |
| Opt-in production worker using Crawlee queues | Blocked on 1b.2b |
| Playwright / Docling / bulk 500 | Later phases |

## Policy

Crawlee stock HTTP clients are **not** authorised. All network I/O for acquisition
must remain on the SafeSourceFetcher policy path until 1b.2b proves parity with
SSRF regression tests.
