# AI-assisted catalogue ingestion

## Scope and truth boundary

This worker acquires public scholarship information into an auditable staging area. It extends the
modular monolith; it is not a second catalogue and does not publish records. The authoritative order
is:

`official provider source -> reviewed catalogue -> deterministic rules -> AI explanation`

PDFs, CSV files, JSON files, and search results only identify things to investigate. A fetched,
deterministically classified official provider, government, or resolved university page is required
before extraction. Search snippets and seed documents never become `Source` evidence.

The state path is `discovered -> official_source_candidate -> source_fetched -> extracted ->
ready_for_review -> submitted_for_review`. Failures terminate in explicit `needs_review`,
`validation_failed`, `conflict_detected`, or `duplicate_candidate` states. Only the existing admin
review action can later move the resulting draft opportunity to active publication.

## Components

- `catalogue_ingestion_runs` stores a checkpoint, configured budgets, aggregate counts, and usage.
- `catalogue_candidates` stores seed identity and a proposal or failure state.
- `catalogue_candidate_sources` stores classification rationale, final URL, bounded excerpt, content
  hash, and fetch result. It does not store a downloaded website corpus.
- `catalogue_extraction_attempts` stores schema/provider/version identity, usage, and structured
  output. A unique source-version key and cross-candidate lookup prevent repeated model work.
- `SeedSourceLoader` accepts a local path or an HTTPS Azure Blob URI. Query strings, including SAS
  tokens, are never persisted. Blob URIs without a query use `DefaultAzureCredential` and the
  storage data-plane scope; managed identity is preferred. Text PDFs use `pypdf` first.
- `SafeSourceFetcher` requires HTTPS, blocks private/reserved DNS and connected peers, validates every
  redirect, restricts content type/size/time, removes active HTML content, and records the final URL.
- `BoundedOfficialSiteCrawler` can expand only from an already-classified official HTTPS root. It
  ranks scholarship-relevant same-host links deterministically, rejects authentication/session and
  unverified cross-domain targets, deduplicates URL/redirect/content identities, and enforces hard
  page, depth, aggregate-byte, and sequential per-host request limits. Every network request remains
  behind `SafeSourceFetcher` or an injected boundary that can enforce the remaining byte allowance.
- `AzureOpenAIExtractionProvider` uses `DefaultAzureCredential`, a configurable deployment, strict
  JSON Schema structured output, byte/token/time/retry ceilings, and configured price estimates.
- deterministic validation checks exact evidence excerpts, source URL, required identity fields,
  conflicts, dates, funding invariants, canonical URL duplicates, and `OpportunityCreate`.

Idempotency includes seed programme/provider/university/country plus cycle and intake, so an exact
retry is skipped while a new cycle remains reviewable. Canonical URL is checked first against the
catalogue; ambiguous or existing-program matches are surfaced, never merged automatically.

Unknown official facts remain null and are listed in `unknown_fields`. Every important non-null fact
must cite an excerpt present in the fetched normalized source. Inferred model knowledge is invalid.

## Supported and deliberately deferred adapters

Seed-supplied URLs are implemented as discovery leads. When
`APP_CATALOGUE_BOUNDED_CRAWLING_ENABLED=true`, an already-classified official root is expanded in
small resumable rounds. Links are admitted only when they can support a missing scholarship
objective such as funding, eligibility, documents, application steps, dates, programmes, official
FAQ/rules, or the participating-institution list. News, generic navigation, legal pages, and
individual participating-university profile sites are not part of the scholarship crawl. Sitemap
discovery is a fallback after visible relevant links are exhausted and uses the same admission gate.

Each fetched official HTML page or PDF remains a separate evidence artifact. Extraction routes only
objective-relevant blocks to a model job and feeds objective closure back into the next acquisition
round. The run stops when the scholarship contract is covered and no relevant frontier remains;
explicit run-wide fetch, model-call, cost, and wall-time ceilings remain emergency failures rather
than normal completeness targets.

Autonomous Foundry web search is not wired in this version;
`APP_CATALOGUE_WEB_DISCOVERY_ENABLED` remains false and an absent official URL goes to manual review.
The `WebDiscoveryProvider` interface allows a later reviewed adapter without changing verification.

Normal text PDF parsing uses `pypdf` first. Docling is attempted only when native PDF text is sparse
or absent; its OCR option therefore applies to likely scanned/image PDFs rather than every PDF.
`AzureDocumentIntelligenceParser` remains a fail-closed optional interface, not a paid default.

## Local operation

Keep `.catalogue-seeds/` local and ignored, or use a private Blob container in staging. Source files
must not contain applicant information or credentials.

```bash
uv run python -m app.cli.ingest_catalogue_seeds \
  --source .catalogue-seeds/scholarships.json \
  --dry-run --mode candidate_only --max-candidates 100
```

`candidate_only` fetches and classifies official leads but does not call AI. `extraction` and
`validation` run the complete proposal gates. `review_queue` creates only a draft through the
existing opportunity service. Resume a checkpoint with:

```bash
uv run python -m app.cli.ingest_catalogue_seeds \
  --resume <run-uuid> --batch-size 25
```

Normal tests use `FakeExtractionProvider` and fake HTTP. No test requires Azure or public internet.

## Azure staging

`scheduled-jobs.bicep` adds a manual Container Apps Job named
`<prefix>-catalogue-ingestion`. Deployment does not start it; its safe default command is `--help`.
The existing user-assigned runtime identity receives the scoped Cognitive Services OpenAI User role
on a named existing Azure OpenAI account. No model API key is stored. The selected deployment must
support strict structured outputs and is supplied through `catalogueAiModel`; changing models is a
Bicep parameter update, not an application release.
When `catalogueSeedStorageAccountName` is supplied, the same identity receives Storage Blob Data
Reader only on that existing account. No public container or storage account is created.

The bounded crawler has an explicit Azure deployment parameter,
`catalogueBoundedCrawlingEnabled`, which defaults to `true` and maps to
`APP_CATALOGUE_BOUNDED_CRAWLING_ENABLED`. Enabling it does not enable web discovery, browser fetching,
Document Intelligence, AI ingestion, or publication. Use it only for reviewed acquisition runs that
already have a verified official root URL.

Before a real run:

1. Verify the seed Blob is private and readable by the operator/job path being used.
2. Populate and manually verify 30-50 private gold JSONL records across the required regions,
   scholarship types, degrees, funding types, deadlines, and difficult eligibility rules.
3. Set actual reviewed input/output pricing and a run ceiling. Zero pricing is allowed only while AI
   is off; it does not mean a real deployment is free.
4. Run the manual `Catalogue AI evaluation` workflow against staging and retain its artifact.
   Its protected `azure-staging` OIDC identity needs scoped OpenAI User and Blob Data Reader roles;
   the workflow uses Azure CLI federation and has no client secret.
5. Require at least 95% correctness for every required-field category, 100% correct official source
   use, zero unsupported confident facts, and human review of all errors.
6. Deploy the manual job with `catalogueAiIngestionEnabled=true`, then start it with an explicit seed
   URI, bounded candidate count, and non-publishing mode. Inspect run/candidate admin APIs before any
   `review_queue` execution.

The model service is a variable charge per token. The Container Apps Job is manual and scales to one
replica, so it has no ingestion compute use while idle. Exact monthly and per-item cost must come from
the chosen region/deployment and the evaluation report; the application enforces model-call and
estimated-spend ceilings but an Azure budget remains an alert, not a hard cap.

Catalogue AI is independent of the Student Assistant. Enabling one does not enable the other.

## Evaluation contract

Private JSONL uses one `GoldItem` per line:

```json
{"id":"sample-1","official_url":"https://official.example/scholarship","source_text":"Manually captured official source text ...","expected":{"identity":{"name":"Example Scholarship"},"application":{"application_deadline":null}}}
```

Run `python -m app.cli.evaluate_catalogue_extraction --gold <private.jsonl>`. The report separates
each expected field and reports official-source correctness, unsupported confident values,
abstention accuracy, schema rate, mean cost, and mean/p95 latency. Do not commit the gold source text
unless its redistribution rights are documented.

## Monitoring and throughput

Published official sources are separate from ingestion. Monitoring claims a bounded due batch with
`FOR UPDATE SKIP LOCKED`, leases claims, schedules `monitor_next_check_at`, rate-limits by host, and
uses exponential failure backoff. Unchanged normalized hashes update freshness without AI. Changed
hashes return the existing record to review and create an evidence/change record.

For a catalogue of `N` sources, interval `D` days, job frequency `F` runs/day, configure a batch of at
least `ceil(N / (D * F))` plus retry headroom. The deployment default of 100/day supports well above
500 sources on a seven-day schedule at one replica. Queue-lag telemetry reveals a missed SLA.

## Administration, rollback, and incident response

Read APIs require the current admin role; retry and submit actions additionally require recent step-up
authentication and emit audit records. Submitted opportunities are draft/needs-review records.

To stop paid work immediately, set `APP_CATALOGUE_AI_INGESTION_ENABLED=false` or deploy
`catalogueAiIngestionEnabled=false`; do not start the manual job. Existing staging/audit rows remain
available. A rolling downgrade removes only staging tables and monitor scheduling columns, so first
stop ingestion and monitoring, confirm no old application revision uses them, export audit records if
required, then apply the Alembic downgrade. The upgrade is additive and does not rewrite catalogue
truth.

Known limitations: no autonomous web-search adapter, no login/CAPTCHA acquisition, and no paid
Document Intelligence implementation. Exact duplicate detection is canonical-URL based before the
existing review workflow's broader duplicate suggestions. Facts absent from official evidence stay
unknown, and production quality still requires private-gold evaluation plus controlled live runs
across several structurally different scholarships.
