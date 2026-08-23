# Phase 1a progress — EvidenceAcquirer boundary

- Date: 2026-08-23
- Branch: `codex/phase1-evidence-acquirer`
- Baseline: `codex/scholarship-detail-extraction-v3` @ `d490dfdf2bc16ea6298086c9ba06c144c03600ae`
- Blueprint: Engineering Blueprint §5 Acquisition Architecture

## Completed in this slice

| Item | Status |
| --- | --- |
| ADR 0014 replaceable acquisition boundary | Done |
| `EvidenceAcquirer` protocol + request/result types | Done |
| `LegacySafeEvidenceAcquirer` over `SafeSourceFetcher` | Done |
| Explicit rejection of browser/document/OCR flags | Done |
| Unit tests (`tests/test_evidence_acquirer.py`) | Done |
| Crawlee dependency | **Not started** (Phase 1b) |
| ContentSufficiencyChecker / Playwright acquisition | **Not started** (Phase 2) |
| Docling / evidence blocks | **Not started** (Phase 3) |
| Bulk 500 catalogue load | **Blocked** until five-family gates |

## Exit criteria for Phase 1a

- [x] Product code can depend on `EvidenceAcquirer` without importing a crawl vendor.
- [x] Default path still uses `SafeSourceFetcher` only.
- [x] No automatic publication path introduced.
- [ ] Local/CI: `pytest tests/test_evidence_acquirer.py` green (operator must run).
- [ ] No regression on existing crawler suites (operator must run full suite).

## Next slice (Phase 1b — not this commit)

1. Optional Crawlee static HTTP adapter implementing `EvidenceAcquirer`.
2. Keep every network call behind the same safe policy boundary.
3. Fixture parity with current MEXT static acquisition artifacts.
4. SSRF / robots / byte-limit regression tests remain mandatory.

## Explicit non-work

No AI magic: no model-chosen URLs, no CAPTCHA bypass, no auto-publish, no
family-specific crawler, no bulk AI batch.
