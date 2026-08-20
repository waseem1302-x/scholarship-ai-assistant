# ADR 0003: Separate discovery binding from safe-source promotion

- Status: Accepted for PR5 design
- Date: 2026-08-19
- Supersedes any ambiguous PR5 wording that implies a search URL directly creates a candidate or that the discovery worker independently performs a second authoritative fetch
- Related: ADR 0002, `docs/pr5-web-discovery-spec.md`, `docs/scholarship-information-contract.md`

## Context

The live ingestion model exposes two facts that materially affect PR5:

1. `CatalogueCandidate` is not a URL identity. It represents a known scholarship acquisition work item and belongs to exactly one ingestion run.
2. The existing candidate idempotency key includes `possible_official_url` along with seed identity fields. Calling the existing seed-creation path once per discovered URL can therefore create distinct candidates for different official pages that actually describe the same scholarship.

The existing ingestion service also owns the authoritative network transition:

```text
candidate source
  -> OfficialSourceClassifier
  -> SafeSourceFetcher / PR4 bounded crawler
  -> final redirect classification
  -> fetched candidate source
  -> extraction / validation
```

If PR5 independently safe-fetches a URL and then hands the URL to ingestion, the same source is fetched twice. That wastes budget, creates a time-of-check/time-of-use gap, and weakens the clarity of which network boundary is authoritative.

A third issue is lifecycle. Reusing a historical candidate from a completed run does not automatically make it processable in a new ingestion run, while creating another candidate per URL causes identity inflation. Published opportunities also need a different source-enrichment workflow from not-yet-published candidates.

## Decision

### 1. PR5 never creates a `CatalogueCandidate` from a discovered URL

No PR5 path may call `add_seed_candidates()` using a discovered URL as a new seed identity.

A search result can create only:

```text
DiscoveryLead
DiscoveryObservation
DiscoveryAssessment
```

It cannot create a scholarship candidate or opportunity.

The legacy candidate idempotency key is therefore not used as the discovery-lead deduplication boundary. URL leads deduplicate independently by normalized URL fingerprint.

### 2. Only an explicit known target candidate is promotable in PR5

A discovery run may carry an optional `target_candidate_id`.

PR5's first live promotion frontier is:

```text
known CatalogueCandidate
  + public scholarship identity hints
  -> discover likely official root
  -> bind accepted lead to that candidate
```

Provider-only, institution-only, and scholarship/institution-route objectives may still populate the discovery ledger, but they do not create candidates and do not automatically bind supporting pages into root extraction in PR5.

This is deliberate. Institution-route and other supporting pages become materially useful when PR6 can aggregate multiple official sources with field-level scope/provenance.

### 3. Add a discovery provenance link to `CatalogueCandidateSource`

PR5 should add:

```text
discovery_lead_id UUID nullable
  FK -> catalogue_discovery_leads(id) ON DELETE SET NULL
```

and a uniqueness/index boundary equivalent to:

```text
UNIQUE(candidate_id, discovery_lead_id)
```

for non-null lead IDs under normal PostgreSQL/SQLite null semantics.

Manual/seed/crawler-created candidate sources keep `discovery_lead_id = NULL`.

This makes the source row the binding point between untrusted discovery and the existing ingestion pipeline without changing source truth semantics.

### 4. Binding is not promotion

A **binding** means:

> This deterministically assessed discovery lead is worth attempting as a source for this already-known candidate.

Binding may create or reuse a `CatalogueCandidateSource` in `DISCOVERED` state with:

- candidate ID;
- discovery lead ID;
- observed URL / normalized candidate-source URL;
- contextual assessment reason;
- trust tier / candidate-context officiality projection.

Binding does **not** mean the source has been fetched, accepted as evidence, or promoted to the canonical graph.

### 5. Safe fetch remains in the existing ingestion service

After binding, the existing ingestion service remains responsible for:

- `SafeSourceFetcher` / PR4 crawler execution;
- DNS/IP/peer/robots/redirect/MIME/size/network controls;
- final URL canonicalization;
- re-running official-source classification after redirects;
- recording candidate-source fetch status and content metadata.

PR5 must not add a parallel raw HTTP client or a second authoritative fetch before this stage.

This avoids double-fetch cost and keeps the existing security boundary authoritative.

### 6. Promotion is an event after safe-fetch acceptance

`CatalogueDiscoveryPromotion` is created only when the bound candidate source has:

1. been fetched successfully through the existing safe acquisition boundary;
2. survived final-URL officiality/ownership assessment for the candidate context;
3. reached the existing `FETCHED` candidate-source state.

The promotion event references:

```text
run_id
discovery_lead_id
discovery_assessment_id
candidate_id
candidate_source_id
promotion_kind = official_root_source
reason_code
created_at
```

Unique boundary:

```text
UNIQUE(candidate_id, discovery_lead_id)
```

A failed/blocked/redirected-to-unofficial source retains its binding/audit trail but gets no promotion event.

### 7. Root promotion is intentionally narrow in PR5

PR5 auto-binding targets the root source required to resolve an already-known scholarship candidate.

It does not automatically bind every official search result.

Initial deterministic selection order should consider, in order:

1. assessment acceptable for the expected owner/context;
2. stronger trust tier;
3. query intent priority (`exact scholarship identity` before refinements);
4. known canonical/reviewed owner-domain relationship;
5. provider search rank where available;
6. stable normalized-URL lexical tie-breaker.

The exact scoring representation can be implementation-specific, but tests must make selection deterministic.

Additional good leads remain in the ledger for PR6/PR8 information-gap acquisition rather than becoming duplicate roots.

### 8. Context matters for what can become a root

A URL that is official for an institution is not automatically a valid root authority for an umbrella scholarship.

The discovery objective/assessment must therefore carry the expected root-authority context (for example provider/government/institution) when known.

Examples:

- umbrella government scholarship -> provider/government authority root;
- independent university-owned scholarship -> institution authority root may be valid;
- university page explaining a national scholarship -> supporting official, retained for later scoped evidence, not automatically selected as the umbrella root in PR5.

### 9. Candidate lifecycle gate

The discovery worker must lock the target candidate before binding and fail closed on incompatible lifecycle state.

Automatically bind/resume only when the candidate is clearly still in source-acquisition work, for example:

- `DISCOVERED`; or
- `NEEDS_REVIEW` specifically because no official source was previously found, with no opportunity already staged/published and no conflicting human-reviewed payload.

For a safe automatic resume of the second case, PR5 may clear only the source-not-found failure and return the candidate to `DISCOVERED` after binding under a row lock.

Do not automatically reset or mutate candidates in states such as:

```text
EXTRACTED
VALIDATION_FAILED
CONFLICT_DETECTED
DUPLICATE_CANDIDATE
READY_FOR_REVIEW
SUBMITTED_FOR_REVIEW
APPROVED
REJECTED
PUBLISHED
```

Those states require their existing workflow or a future explicit source-enrichment path.

If `candidate.opportunity_id` is already set, PR5 root binding must fail closed unless a later reviewed enrichment contract explicitly supports it.

### 10. Published scholarship enrichment is not disguised candidate creation

When a canonical `Opportunity` already exists, finding another official source must not create a fresh scholarship candidate merely to attach the URL.

That later workflow should be explicit, for example:

```text
existing Opportunity
  -> information-gap acquisition task
  -> discovered supporting source
  -> scoped source/evidence proposal
  -> review/re-extraction
```

PR6/PR8 can implement this with provenance-safe multi-source extraction and autonomous completeness-driven acquisition. PR5 preserves the leads but does not invent this lifecycle prematurely.

### 11. Final-redirect deduplication must be handled explicitly

Two different discovered URLs can safely redirect to the same final canonical URL.

The existing candidate-source uniqueness boundary is `(candidate_id, canonical_url)`. PR5 implementation must therefore reconcile a fetched final canonical URL with an already-existing candidate source before committing the redirect update.

Required behavior:

```text
lead A -> /old -> /current
lead B -> /current
```

results in:

```text
one effective candidate source for /current
multiple discovery observations/bindings remain auditable
no IntegrityError
no duplicate extraction
```

The implementation may merge/repoint binding metadata or mark the redundant binding as an alias/duplicate, but it must be deterministic and tested. It must not delete discovery provenance.

### 12. PR5 integration pattern

Recommended integration:

```text
catalogue-discovery job
  -> ledger + assessments
  -> deterministic root selection
  -> bind selected lead to target candidate as DISCOVERED source

catalogue-ingestion job/service
  -> prefer/reuse bound candidate source
  -> SafeSourceFetcher
  -> final officiality
  -> candidate source FETCHED
  -> create DiscoveryPromotion event
  -> optional PR4 bounded crawl
  -> existing extraction/validation/review path
```

This keeps search and network acquisition independently switchable while avoiding duplicate network clients and duplicate scholarship identities.

## Consequences

### Positive

- A URL can never become a scholarship identity by accident.
- Multiple official pages for one scholarship do not create multiple candidates.
- PR4/SafeSourceFetcher remains the single authoritative fetch boundary.
- Discovery can be disabled without changing existing seed ingestion.
- Search calls and source HTTP fetches remain separately measurable.
- Later multi-source acquisition can reuse unpromoted high-quality leads.
- Historical/published opportunities are not silently re-entered as new scholarships.

### Cost

- PR5 must add one nullable discovery provenance FK to candidate sources.
- The ingestion service needs a small integration hook for pre-bound discovery sources and promotion-event recording.
- Final redirect deduplication needs explicit merge/reconciliation logic.
- Supporting official pages wait for the provenance-safe multi-source phase rather than being prematurely extracted.

These costs are accepted because candidate identity integrity is more important than reducing a few lines of integration code.

## Required tests

PR5 implementation must prove at least:

- two discovered URLs for one candidate do not create two candidates;
- discovery code never calls seed-candidate creation from a lead;
- repeated lead binding is idempotent;
- an incompatible/terminal candidate cannot be automatically reset;
- source-not-found candidate can be safely resumed only under the narrow allowed rule;
- bound source is fetched by the existing SafeSourceFetcher boundary;
- failed safe fetch creates no promotion event;
- unofficial final redirect creates no promotion event;
- successful fetched root creates one promotion event;
- two leads converging on one final canonical URL do not create duplicate candidate sources or duplicate extraction;
- an institution-supporting page cannot become an umbrella scholarship root without the proper authority context;
- published opportunity discovery remains ledger-only in PR5.
