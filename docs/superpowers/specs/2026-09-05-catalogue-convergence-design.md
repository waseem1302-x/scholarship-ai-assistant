# Catalogue Convergence Design

## Goal

Make a completeness-mode ingestion run finish with a defensible answer: either a publishable scholarship record whose required objectives are closed by fetched official evidence, or an explicit review result naming the unresolved evidence/capability failure. The implementation must reuse the existing crawler, extraction planner, evidence cache, claim resolver, and publication guard.

## Diagnosed gaps

1. Open-ended coverage cells can never close because only a few finite identity fields have deterministic requirements.
2. The crawler records browser/OCR escalation requests but does not execute browser rendering, and every PDF enters the heavyweight Docling path before the inexpensive native-text path.
3. A retryable provider failure aborts the remaining extraction jobs and persists a terminal failed job that cannot be resumed.
4. Semantic validation accepts structurally valid but nonsensical values such as prose in a programme-duration field.
5. The rich materializer silently drops already-supported claim fields.

## Design

### Evidence-closed completeness

Completeness remains scoped to required claim objectives. An open-ended objective may close only when all of these are true:

- acquisition exhausted the eligible official-source frontier without a budget or capability blocker;
- all routed extraction jobs finished successfully;
- the provider reported the objective complete for the supplied evidence; and
- every accepted value has a valid evidence span.

An objective with no claim may close as `not_stated` under the same acquisition/extraction proof. Without that proof it remains unresolved. Existing finite identity/count requirements remain authoritative when present.

The crawl result will expose frontier exhaustion explicitly. Completeness-mode crawling will seed sitemaps and remove the artificial depth ceiling while retaining emergency resource controls (fetch attempts, per-resource bytes, total bytes, model-call count, and cost). This is not a claim of internet-wide completeness; it is completeness over the reachable, policy-allowed official evidence frontier.

### Adaptive acquisition

PDFs use native text extraction first. Digitally readable PDFs stop there. Sparse/scanned PDFs escalate to the existing Docling OCR converter. Docling converter construction is reused across documents.

When an HTML response is a JavaScript shell and browser rendering is enabled, the crawler executes a Playwright renderer and re-evaluates the rendered content. Browser navigation is restricted to the prevalidated public target origin and existing fetch limits. A failed or disabled capability remains a named completeness blocker.

### Extraction recovery

Retryable provider failures do not abort unrelated jobs. The failed job is split when possible; otherwise it is reopened for a bounded retry on resume. Previously validated outputs remain cacheable and are reused. Final resolution happens only after every planned job reaches a terminal state, so one timeout cannot discard useful work.

### Semantic and materialization fidelity

Add narrow, field-specific checks for typed values whose shape is objectively testable (duration, years, amounts, currency, URLs). Rejecting uncertain prose is safer than publishing it as structured truth. Preserve all supported eligibility, funding, step, and resource fields when materializing the graph.

## Non-goals

- Replacing Crawlee, Playwright/Chromium, Docling, the database, or the AI provider.
- Crawling unrelated third-party domains without typed authority.
- Claiming mathematical 100% coverage of information not published by the provider.
- Broad schema redesign or new infrastructure.

## Acceptance criteria

- A frontier-exhausted, fully extracted objective can deterministically become complete or verified not-stated.
- Budget exhaustion, disabled/failed rendering, OCR failure, or extraction failure prevents publication and remains observable.
- Native PDFs avoid OCR; scanned PDFs use Docling OCR; JS shells can be rendered when enabled.
- Retryable job failure no longer prevents independent jobs from completing and can recover on resume.
- Known malformed structured claims are rejected.
- Rich claim fields survive materialization.
- Relevant tests and the complete backend suite pass.
