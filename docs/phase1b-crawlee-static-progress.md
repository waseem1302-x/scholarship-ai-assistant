# Phase 1b progress — Crawlee static adapter

- Date: 2026-08-23
- Branch: `codex/phase1b1-crawlee-clean`
- Baseline: `codex/scholarship-detail-extraction-v3` (includes merged Phase 1a #34)

## 1b.1 completed (this slice)

| Item | Status |
| --- | --- |
| ADR 0015 | Done |
| Optional `[crawlee]` extra | Done |
| `select_evidence_acquirer(prefer_crawlee_static=...)` | Done |
| Fail-closed when Crawlee missing | Done |
| Single-URL acquire still via SafeSourceFetcher | Done |
| Default path unchanged | Done |
| Full Crawlee HttpClient / queue orchestration | **Deferred to 1b.2** |

## 1b.2 exit criteria (next)

- [ ] Custom security adapter or HttpClient that applies the same policy as
      `SafeSourceFetcher` for every request Crawlee schedules.
- [ ] SSRF / robots / byte-limit regression suite green with the adapter enabled.
- [ ] Optional multi-page parity tests vs `BoundedOfficialSiteCrawler` fixtures.
- [ ] Still no default switch in production without explicit configuration.
