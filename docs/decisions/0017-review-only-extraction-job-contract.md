# ADR 0017: Review-only extraction jobs are durable, fenced and idempotent

- Status: Accepted
- Date: 2026-08-24
- Applies to: catalogue ingestion only
- Related: ADR 0014, ADR 0015, ADR 0016

## Decision

`CatalogueIngestionRun` is the durable work item for direct official URL
ingestion. Creating a direct URL run only stores validated work and returns its
status projection; it does not fetch, crawl, invoke a model, materialize a
graph, or publish.

The run contract has these required properties:

1. A caller-supplied idempotency key, or a deterministic key derived from the
   canonical source bundle and immutable request options, identifies one logical
   run. Repeated enqueue returns that existing run.
2. Workers claim runnable rows using `FOR UPDATE SKIP LOCKED`, a bounded lease,
   and a newly generated opaque lease token.
3. State-changing terminal completion is fenced by that lease token. An expired
   worker cannot complete, retry, or dead-letter work claimed by a newer worker.
4. Transient failures receive bounded backoff and retain their checkpoint;
   permanent or retry-exhausted failures enter an operator-visible dead-letter
   state. No error is silently discarded.
5. Publication is outside the job contract. A completed run may at most leave a
   review proposal or an existing review-only candidate state.

## Non-goals

- This decision does not authorize Crawlee stock networking, browser rendering,
  OCR, Docling, model-selected URLs, graph approval, or publication.
- It does not make retryable model/provider output authoritative.

## Rollback

Stop queue consumers from claiming new runs and deploy the prior worker image.
Existing rows retain their lease expiry and are reclaimable after expiry. Do not
delete source artifacts, claims, or review-only candidates as part of rollback.
