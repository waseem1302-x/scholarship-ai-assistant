# Phase 1b progress — Crawlee static adapter

- Date: 2026-08-23
- Branch: `codex/phase1b-crawlee-static-adapter`
- Parent: `codex/phase1-evidence-acquirer` (PR #34)
- Baseline extraction branch: `codex/scholarship-detail-extraction-v3`

## 1b.1 completed (this slice)

| Item | Status |
| --- | --- |
| ADR 0015 | Done |
| Optional packaging note (extra reserved; not required) | Documented |
| `select_evidence_acquirer(prefer_crawlee_static=...)` | Done |
| Fail-closed when Crawlee missing | Done |
| Single-URL acquire still via SafeSourceFetcher | Done |
| Default path unchanged | Done |
| Full Crawlee HttpClient / queue orchestration | **Deferred to 1b.2** |
| Playwright acquisition | Phase 2 |
| Bulk 500 load | Blocked by gold-suite gates |

## Why 1b.1 does not call Crawlee's default HTTP client yet

Crawlee's stock HTTP clients are not the platform security boundary. Wiring them
before a custom adapter that enforces HTTPS, DNS/IP, robots, redirects, MIME,
and byte limits would violate the blueprint. Phase 1b.1 only proves the opt-in
factory and fail-closed packaging behaviour.

## 1b.2 exit criteria (next)

- [ ] Custom security adapter or HttpClient that applies the same policy as
      `SafeSourceFetcher` for every request Crawlee schedules.
- [ ] SSRF / robots / byte-limit regression suite green with the adapter enabled.
- [ ] Optional multi-page parity tests vs `BoundedOfficialSiteCrawler` fixtures.
- [ ] Still no default switch in production without explicit configuration.
