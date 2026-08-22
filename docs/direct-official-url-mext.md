# Direct official URL to cited MEXT graph

## Milestone

Given one administrator-supplied primary official HTTPS URL and an optional bounded list of
supporting official HTTPS URLs, the system safely acquires the declared evidence bundle, extracts
source-scoped claims, resolves those claims deterministically, and stages exactly one MEXT
scholarship graph for human review. It does not publish the record.

The canonical MEXT identity contains two top-level application tracks:

- Embassy Recommendation
- University Recommendation

Category, institution, deadline, funding, document, and application-step facts remain scoped beneath
the applicable cycle and route. Facts are never copied from one route to another. Programme scope
keys are retained on extracted claims, while canonical academic-programme materialization is
explicitly deferred.

## Entry points

The administrator workspace contains an **Official URL acquisition** tool. Its default dry run
fetches, extracts, resolves, and reports gates without creating a canonical record. Turning off the
dry run stages a draft in the existing review queue. The request requires administrator step-up.
Supporting URLs are entered separately from the primary URL and remain visibly tagged with their
operator-declared role.
An optional expected university name binds a university-domain supporting source to an existing
canonical university record. Education-domain syntax alone never establishes official ownership.

The worker CLI supports the same bounded pipeline:

```powershell
python -m app.cli.ingest_catalogue_seeds `
  --url https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/ `
  --supporting-url https://www.mext.go.jp/example/embassy-guidelines.pdf `
  --supporting-url https://www.mext.go.jp/example/university-guidelines.pdf `
  --name "MEXT Scholarship" `
  --university "Example University" `
  --mode review_queue
```

Use `--dry-run --mode extraction` to validate without materializing a graph. The CLI remains the
preferred entry point for environments where long-running HTTP requests are undesirable.

## Evidence boundary

Every successful fetch creates an append-only `catalogue_source_artifacts` row containing the final
URL, content type, normalized text, content hash, extraction method, byte count, character count,
fetch metadata, and source role. Candidate sources distinguish `primary`, `supporting`, `crawled`,
and legacy/discovery provenance. Update and delete events fail closed.

The primary URL plus supporting URLs form one explicit source bundle. Every URL is normalized by the
existing public HTTPS policy before a run is created. Duplicate normalized URLs are rejected. The
bundle cannot exceed the run's page budget. For bundles with supporting URLs, only the declared URLs
are fetched; implicit crawling is disabled so a rerun uses the same evidence set. Existing bounded
crawling remains available for a single primary URL.

Raw source acquisition has its own bounded per-page byte limit (5 MB by default). This is separate
from the normalized model-input character limit, because a valid compressed PDF can be larger than
its extracted text. The fetch byte limit, page count, normalized text limit, model-call limit, and
estimated-cost limit all remain independently enforced.

Azure throttling is retried using the service's `Retry-After` response, capped by
`APP_CATALOGUE_AI_MAX_RETRY_DELAY_SECONDS`. Exhausted retries fail closed as `ai_rate_limited`.
Operators must size model input/output limits for the deployment's token-per-minute quota; the
worker does not change Azure capacity or silently expand the configured evidence boundary.

Claim extraction is performed independently for every official artifact under
`catalogue-claims.v2`. A claim contains:

- entity type and stable entity key;
- field path and exactly one typed value;
- cycle, track, institution, and programme scope;
- exact excerpt, start offset, end offset, and evidence basis.

The provider normalizes only explicit entity-qualified field paths such as
`funding.component_type` or `track_name`. The resolver verifies
`text[start:end] == excerpt`. If the model supplied incorrect offsets, the provider may rebind them
only when the verbatim excerpt occurs exactly once in the source; ambiguous or missing excerpts
remain rejected. For the same entity, field, and scope,
the best trust tier wins. Differing values at the same best tier are conflicts; claim counts never
break a tie. Intake years and the two recommendation-route names also pass semantic context checks.
More than one intake identity or cycle scope in a bundle is a blocking conflict. This prevents a
new embassy guideline and an older university guideline from being silently combined.
Source-local cycle aliases that carry the same verified intake year are canonicalized to one
deterministic `intake_<year>` key before scope conflict checks; differing years still block.

## MEXT gates

Materialization is blocked unless the proposal is conflict-free and contains evidence-backed:

- scholarship name, provider, destination country, and explicit degree-level scope;
- intake cycle;
- Embassy Recommendation and University Recommendation tracks;
- at least one funding component, required document, and application step.

Unknown facts remain unknown. Provider output conflicts and deterministic conflicts are retained on
the candidate for review.

## Canonical materialization

A successful non-dry review-queue run creates one `draft` opportunity with an additive
`degree_levels` projection. The existing scalar degree field remains a rolling-release compatibility
projection and is not authoritative for a multi-level scholarship.
The graph uses the established cycle, track, institution, scoped deadline, funding component,
required document, and application-step tables. Date-only deadlines retain `local_date` and `date`
precision; funding can retain frequency independently of amount.

Each pre-canonical artifact is promoted to an immutable `SourceSnapshot`. Every resolved claim is
linked to its canonical entity through `FieldEvidence` with a passed deterministic validator status.
Graph creation, candidate linkage, and candidate status commit in one transaction. Public visibility
still requires the existing explicit review and publication action.

Administrators can inspect the graph through:

```text
GET /api/v1/admin/opportunities/{opportunity_id}/graph
```

The response groups routes, institutions, institution-route participation, deadlines, funding,
documents, and steps and returns field citations with source URL, source title, content hash, exact
excerpt, and validator status.

## Operational invariants

- Only HTTPS public URLs accepted by the existing URL policy enter acquisition.
- Restricted Japanese government `.go.jp` domains are recognized as government sources.
- `SafeSourceFetcher` remains the network-security boundary.
- Every operator-declared source must classify as official before and after redirects.
- Redirects that make two declared URLs resolve to the same canonical source block the bundle.
- When the primary source identifies MEXT, every supporting source must contain a MEXT or
  Monbukagakusho identity marker before it can create an artifact or consume a model call.
- Same-host downgrade redirects are rewritten to HTTPS without issuing a plaintext request;
  cross-host and explicit-port downgrades remain blocked.
- `BoundedOfficialSiteCrawler` enforces page, depth, byte, and host-rate budgets.
- For a MEXT root, crawled child pages without a MEXT/Monbukagakusho identity marker are recorded
  for review but excluded from artifacts and model extraction.
- Model call, token, output, and estimated-cost budgets remain enforced per run.
- Unchanged source content reuses a compatible extraction attempt by URL, content hash, schema,
  prompt hash, provider, and model.
- Duplicate canonical source URLs block a second scholarship record.
- No acquisition path can create an active record or bypass human review.

## Current-cycle interpretation

The evergreen Study in Japan overview explicitly defers to the latest route guidelines. Embassy and
university recommendation documents may be published on different schedules, and embassy deadlines
can be country-specific. The ingestion workflow therefore does not infer a missing current guideline,
copy a date between routes, or relabel an older guideline as current. A mixed-cycle bundle remains a
review failure until cycle-compatible official evidence is supplied.

## Deferred

Canonical academic-programme materialization, name-only scholarship discovery, Azure Web Search
promotion, OCR for image-only PDFs, translation, and automatic publication are outside this
milestone. The existing Azure discovery PR stack remains frozen and is not required for direct
official URL acquisition.
