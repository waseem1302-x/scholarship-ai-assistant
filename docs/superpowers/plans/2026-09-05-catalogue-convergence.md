# Catalogue Convergence Implementation Plan

> Execute in the existing `codex/catalogue-completeness` worktree. Use test-driven development and keep each change inside the existing ingestion architecture.

## Task 1: Prove and close completeness

**Files:** `crawler.py`, `scoped_completeness.py`, `claim_resolution.py`, `production_service.py`, related tests.

1. Add failing tests for frontier exhaustion and evidence-closed open objectives.
2. Add explicit crawl-frontier status and enable sitemap/depth-unbounded completeness crawling while retaining emergency budgets.
3. Pass acquisition/extraction proof into scoped completeness.
4. Verify focused crawler/resolution tests.

## Task 2: Execute adaptive PDF and browser capabilities

**Files:** `acquisition_fetcher.py`, `docling_pdf_converter.py`, new focused browser adapter if required, `crawler.py`, related tests.

1. Add failing tests proving readable PDFs bypass OCR, sparse PDFs escalate, and JS shells consume a renderer result.
2. Implement native-text PDF preflight and reuse Docling converters.
3. Implement the policy-restricted Playwright renderer and wire it into the crawler behind the existing feature flag.
4. Verify focused acquisition tests.

## Task 3: Make extraction converge after transient failures

**Files:** `production_service.py`, extraction job repository/model helpers if needed, related tests.

1. Add failing tests for continuing independent jobs and reopening/splitting retryable failures.
2. Replace early abort with terminal-state collection, bounded retry/split behavior, and final resolution after all jobs finish.
3. Verify focused production-service tests.

## Task 4: Strengthen semantic fidelity and preserve graph fields

**Files:** `claim_resolution.py`, `rich_graph_materializer.py`, related tests.

1. Add failing tests for malformed typed claims and currently dropped fields.
2. Add narrow semantic validators and map all supported fields.
3. Verify focused resolver/materializer tests.

## Task 5: End-to-end verification and commit

1. Run the complete backend test suite.
2. Run any repository lint/type checks applicable to touched files.
3. Review the final diff for scope and regressions.
4. Commit the passing implementation on `codex/catalogue-completeness`.
