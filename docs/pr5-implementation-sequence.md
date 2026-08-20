# PR5 implementation and proof sequence

- Status: implementation ordering contract
- Date: 2026-08-19
- Last reconciled: 2026-08-20 against ADRs 0003-0006 and the Azure feature baseline
- Integration baseline: Azure feature head `23180429ed35e65166628a79f0c7e08d4c895dd0`
  (PR4, Step 1/2 safety fixes, PR5 architecture reconciliation, Slices 1-5, and the merged
  complete-acquisition checkpoint).
- Runtime coding starts from a fresh branch at the then-current Azure feature head after this architecture PR is merged.
- This document does not authorize publication, autonomous scheduling, or billable Azure provisioning.

## Current implementation boundary

The runtime foundation implements Slices 1-6: the discovery ledger migration, pure deterministic
objective/query planning, transactional repository state and budget accounting, the bounded provider
protocol with a fake provider, policy-gated normalized URL lead ingestion, and append-only contextual
officiality assessment against reviewed owner/domain inputs. The next isolated runtime increment is
Slice 7 deterministic known-candidate source binding. The foundation still does not include candidate
binding execution, live discovery fetching, live Azure configuration, an Azure provider adapter,
infrastructure changes, or billable calls.

After Slice 5, the complete acquisition checkpoint in
`complete-scholarship-acquisition-contract.md` freezes the larger name/URL/document outcome and
CSC/MEXT proof gates. It does not expand PR5 scope: multi-source evidence aggregation, OCR/browser
fallbacks and complete graph construction remain later work. PR5 must deliver trusted discovery and
binding boundaries that those later stages can reuse.

## Objective

Implement PR5 web discovery in the smallest production-safe slices, proving each boundary before adding the next external capability.

The ordering deliberately separates:

```text
schema durability
  -> deterministic planning
  -> untrusted provider output
  -> URL ledger
  -> contextual assessment
  -> known-candidate source binding
  -> authoritative ingestion safe fetch
  -> target-content verification
  -> promotion
  -> protected live capability proof
```

No later stage may be treated as proof of an earlier stage.

## Slice 0 — merge/base integrity

### Preconditions

- PR4 is merged/integrated into `feature/azure-ai-catalogue-pipeline` by explicit authorization.
- Step 1/2 extraction safety fixes are present at or after `552ff0137fca7ff806a13f24e6a10ce79097682a`.
- Updated feature branch CI is green.
- PR5 runtime branch is created from that updated feature branch, not from the temporary architecture branch.

### Proof

- branch merge base equals the post-PR4 feature head;
- no architecture-only branch history accidentally bypasses feature-branch integration;
- `APP_CATALOGUE_BOUNDED_CRAWLING_ENABLED=false` remains default.

## Slice 1 — discovery schema and migration only

Implement the next Alembic revision after `20260817_0040`.

Tables:

```text
catalogue_discovery_runs
catalogue_discovery_queries
catalogue_discovery_attempts
catalogue_discovery_leads
catalogue_discovery_observations
catalogue_discovery_assessments
catalogue_discovery_promotions
```

Run fields include ADR 0004/0005 refinements:

```text
target_candidate_id
target_identity_snapshot
objective_kind
objective_scope
objective_field_paths
objective_reason_codes
objective_criticality_tier
objective_priority_snapshot
```

Refine existing `catalogue_candidate_sources` with:

```text
discovery_lead_id UUID nullable FK -> catalogue_discovery_leads ON DELETE SET NULL
UNIQUE(candidate_id, discovery_lead_id)
```

### Required invariants

- no applicant/private columns;
- lead URL identity is global and normalized;
- observations preserve query provenance;
- each outbound provider call has one durable attempt row;
- provider/tool/cost capacity is reserved atomically before network I/O;
- assessments are append-only/superseding;
- promotion is idempotent;
- downstream provenance uses the `RESTRICT`/`SET NULL` deletion policy from ADR 0006;
- promotion cannot directly reference publication transitions;
- downgrade is tested where repository policy requires it.

### Proof gate

- SQLite migration tests pass where supported;
- PostgreSQL migration path passes in CI;
- unique/index/FK constraints are asserted;
- migration adds no secrets/default credentials.

## Slice 2 — pure objective and query planner

Implement pure/domain-only types first:

```text
DiscoveryObjectiveKind
DiscoveryObjective
DiscoveryPrioritySnapshot
DiscoveryQueryPlan
DiscoveryQueryPlanner
```

No network provider in this slice.

### Required behavior

- deterministic ordered query generation;
- versioned planner;
- public catalogue fields only;
- reviewed-domain constraints only;
- maximum query count;
- objective-aware query hash;
- no recursive planning from search output;
- no model-selected objectives;
- no applicant/profile/document fields.

### Proof gate

Property/regression tests prove:

- same objective snapshot => same queries/hashes;
- field ordering/input dict ordering cannot change hash;
- unsafe/private schema fields are rejected or structurally impossible;
- objective priority is lexicographic/deterministic;
- Tier 0/Tier 1 blockers outrank graph breadth;
- local scope stays local.

## Slice 3 — discovery repository and state transitions

Add repositories/services for:

- create run;
- persist immutable identity/objective snapshots;
- persist query plan;
- claim query with lease/CAS semantics;
- reserve run budget and create an in-progress attempt before provider I/O;
- settle or abandon attempts without erasing prior call history;
- record/reuse lead;
- record observation;
- append/reuse contextual assessment;
- record idempotent promotion event.

Still no live Web Search provider.

### Required behavior

- two workers cannot successfully claim the same query concurrently;
- query retries are bounded;
- terminal attempts cannot be rewritten and retries use a new attempt number;
- concurrent workers cannot overspend provider, tool-call, or cost ceilings;
- state transitions are allowlisted;
- append-only records are not silently rewritten;
- same normalized URL reuses a lead;
- same query/lead observation is idempotent;
- same candidate/lead promotion is idempotent.

### Proof gate

- concurrency test on PostgreSQL;
- transaction rollback test;
- invalid transition tests;
- duplicate insert race tests;
- attempt/query aggregate reconciliation and crash-recovery tests;
- concurrent atomic budget-reservation tests;
- no promotion without acceptable assessment/fetch proof input.

## Slice 4 — provider interface + fake provider

Implement:

```text
DiscoveryProvider
DiscoveryProviderRequest
DiscoveryProviderResult
FakeDiscoveryProvider
```

The fake provider is authoritative for CI behavior, not live capability.

### Required behavior

Provider result exposes only bounded acquisition metadata:

```text
provider_response_id
web_search_executed
urls
provider_call_count
tool_call_count
response_bytes
latency_ms
usage/cost metadata when available
```

Do not pass generated answer prose into downstream extraction.

### Proof gate

- provider cannot return more URLs than configured contract permits;
- oversized result rejected;
- missing tool execution represented explicitly;
- cost/call budgets enforced in service before additional calls;
- provider requests and web-search tool calls are accounted separately;
- provider failures produce deterministic state/outcome.

## Slice 5 — URL normalization and lead ingestion

Reuse/refactor PR3/PR4 URL normalization policy rather than creating a third canonicalizer.

Reject before persistence where possible:

- non-HTTPS;
- credentials;
- invalid/empty host;
- localhost/private/internal literal;
- oversized URL;
- obvious auth/session/logout target;
- malformed port/URL.

Normalization policy:

- Unicode DNS hosts are normalized with NFKC and stored as lowercase IDNA ASCII;
- fragments and recognized tracking parameters are removed;
- meaningful and duplicate query parameters are sorted deterministically and retained;
- default ports are removed while valid non-default ports remain part of URL identity;
- rejected raw URLs are not persisted, while bounded rejection-code counts may be returned;
- non-public IP literals and obvious internal hosts are rejected without DNS access;
- DNS resolution, redirect validation, and peer-IP verification remain the later
  `SafeSourceFetcher` boundary.

### Proof gate

Regression corpus includes:

- tracking parameters;
- fragments;
- Unicode/IDN handling policy;
- default/non-default ports;
- duplicate query parameter ordering;
- credentialed URL;
- malformed port;
- auth path;
- repeated URL from different queries/runs.

## Slice 6 — contextual officiality assessment

Wrap the existing deterministic official-source classifier with discovery assessment provenance.

Inputs:

- target identity snapshot;
- reviewed provider identity/domain;
- reviewed institution identity/domain where scoped;
- URL/host;
- classifier version.

Outputs:

```text
official
supporting_official
third_party
unresolved
rejected_url_policy
```

### Required behavior

- search-engine/provider rank is not officiality evidence;
- search-result title is not ownership evidence;
- institution source can be supporting-official for local facts without becoming umbrella authority;
- unresolved/conflicting ownership does not promote.

### Proof gate

- provider official root positive cases;
- institution local-page positive cases;
- third-party aggregator negative cases;
- deceptive/subdomain/path cases;
- cross-owner/cross-domain unresolved cases;
- same URL can have different contextual assessments across objectives without mutating historical assessment.

## Slice 7 — deterministic known-candidate source binding

Bind only a deterministically selected, acceptably assessed lead to the run's explicit, existing `target_candidate_id`.

Sequence:

```text
lead exists
  -> contextual assessment acceptable
  -> target_candidate_id authorizes binding
  -> candidate lifecycle permits acquisition
  -> create/reuse CandidateSource(DISCOVERED, discovery_lead_id)
```

Binding means the URL is worth attempting for this known candidate. It is not fetch acceptance, evidence, promotion, classification approval, or canonical scholarship creation.

### Proof gate

- a lead can never create a candidate;
- an objective label/snapshot without `target_candidate_id` cannot authorize binding;
- repeated binding is idempotent;
- terminal/incompatible candidates are not automatically reset;
- the narrow `NEEDS_REVIEW` source-not-found resume rule is enforced;
- deterministic root selection is stable under ties;
- supporting institution pages cannot bind as umbrella roots without the required authority context.

## Slice 8 — authoritative ingestion fetch and promotion

Extend the existing ingestion service with the small hook needed to process a pre-bound discovery source. Discovery does not add a second HTTP client or pre-fetch the lead.

```text
CandidateSource(DISCOVERED)
  -> existing CatalogueIngestionService / SafeSourceFetcher
  -> final URL canonicalization and owner/officiality revalidation
  -> target-content verification
  -> CandidateSource(FETCHED)
  -> catalogue_discovery_promotions
```

Target-content verification fails closed when fetched content does not describe the expected public target identity. No AI extraction is required to prove this root-binding boundary.

### Required behavior

- promotion never creates/publishes an `Opportunity`;
- promotion never approves a classification decision;
- blocked/failed/mismatched fetches retain binding provenance but create no promotion;
- redirect convergence produces one effective canonical candidate source without deleting lead provenance;
- downstream PR4 crawler remains independently gated;
- downstream AI extraction remains independently gated;
- duplicate promotion reuses existing result.

### Proof gate

Integration test:

```text
objective
 -> fake provider
 -> lead
 -> assessment
 -> CandidateSource(DISCOVERED) binding
 -> existing ingestion fake-safe fetch
 -> final owner and target-content verification
 -> CandidateSource(FETCHED)
 -> promotion
```

and negative tests at every boundary, including SSRF/private peer, DNS/rebinding, robots, login/CAPTCHA, unsafe redirects, unsupported MIME, target mismatch, failed fetch, and converging redirects.

## Slice 9 — configuration and kill switches

Add explicit config, all fail closed:

```text
APP_CATALOGUE_WEB_DISCOVERY_ENABLED=false
APP_CATALOGUE_WEB_DISCOVERY_PROVIDER=unavailable
APP_CATALOGUE_WEB_DISCOVERY_ENDPOINT=
APP_CATALOGUE_WEB_DISCOVERY_MODEL=unconfigured
APP_CATALOGUE_WEB_DISCOVERY_TOKEN_SCOPE=https://ai.azure.com/.default
APP_CATALOGUE_WEB_DISCOVERY_TIMEOUT_SECONDS=30
APP_CATALOGUE_WEB_DISCOVERY_MAX_RETRIES=2
APP_CATALOGUE_WEB_DISCOVERY_MAX_RESPONSE_BYTES=500000
APP_CATALOGUE_DISCOVERY_MAX_QUERIES_PER_RUN=5
APP_CATALOGUE_DISCOVERY_MAX_PROVIDER_CALLS_PER_RUN=5
APP_CATALOGUE_DISCOVERY_MAX_LEADS_PER_RUN=25
APP_CATALOGUE_DISCOVERY_MAX_URLS_PER_QUERY=5
APP_CATALOGUE_DISCOVERY_MAX_ESTIMATED_COST_PER_RUN=<explicit reviewed positive value when enabled>
APP_CATALOGUE_DISCOVERY_MAX_ESTIMATED_COST_PER_PROVIDER_REQUEST=<explicit reviewed positive value when enabled>
APP_CATALOGUE_DISCOVERY_MAX_TOOL_CALLS_PER_PROVIDER_REQUEST=1
```

### Required startup/job validation

If discovery enabled, reject:

- unavailable provider;
- missing/non-HTTPS endpoint;
- unconfigured model;
- malformed token scope;
- non-positive required budgets;
- a per-request reservation greater than the corresponding run limit;
- unsupported capability mode;
- implicit preview fallback.

### Proof gate

- default application startup remains unaffected with discovery disabled;
- enabling malformed discovery config fails closed before provider call.

## Slice 10 — Azure provider adapter

Implement the Azure Responses Web Search adapter only after all previous boundaries are fake-provider proven.

### Authentication

- `DefaultAzureCredential` / managed identity;
- no API key committed;
- no client secret when MI works;
- no token logging.

### Response acceptance

Do not treat HTTP 200 as sufficient.

Require the supported response shape to prove a web search tool call was actually executed. Extract URLs only from the supported tool/citation structures, never from free-form generated prose.

### Proof gate

Unit tests use frozen response fixtures for:

- successful tool execution;
- HTTP success without tool execution;
- invalid/missing URL structures;
- duplicate URLs;
- oversized body;
- provider error;
- timeout;
- rate limit;
- bounded retry exhaustion.

## Slice 11 — Azure infrastructure wiring

Add a **separate** Container Apps discovery job and required managed-identity role wiring.

Keep the normal deployment fail closed.

Do not enable a recurring schedule in PR5.

Do not change:

```text
APP_CATALOGUE_AUTO_PUBLISH_ENABLED=false
```

### Proof gate

- Bicep validation;
- security/IaC scan;
- role scope is minimal and explicit;
- no secrets embedded in templates;
- discovery job does not automatically enable crawler/AI extraction/browser/DI/publication flags.

## Slice 12 — protected live capability probe

Before any broad staging acquisition, run one protected capability check against the intended Azure resource/model.

This is the first Azure-runtime proof and must be kept separate from CI proof.

Verify:

- authentication with managed identity/authorized identity;
- actual Web Search tool availability;
- actual response shape;
- provider/tool execution detection;
- one bounded public scholarship identity query;
- cost/usage telemetry available enough to enforce budget policy.

Do not include applicant PII.

If the stable capability is unavailable, discovery remains disabled; do not silently downgrade to a preview API/tool.

## Slice 13 — staging candidate-only flagship proof

First live acquisition proof should remain candidate/source-only.

Recommended difficult flagship sequence:

```text
Chevening or MEXT identity root
  -> then CSC/Tsinghua structural case
```

For each run record:

- objective;
- exact planned queries;
- provider calls;
- raw/unique leads;
- URL-policy rejects;
- assessment outcomes;
- safe-fetch outcomes;
- target-binding outcomes;
- promotions;
- estimated/actual observable cost;
- elapsed/latency metrics;
- exception reasons.

Do not enable AI extraction merely to prove discovery.

## Slice 14 — PR5 release gate

PR5 is complete only when all of the following are proven:

### Source / implementation

- architecture invariants implemented;
- migration/models/repositories/planner/provider/assessment/promotion code reviewed;
- all feature gates default off.

### CI

- backend unit/integration/concurrency tests pass;
- migration path passes PostgreSQL CI;
- frontend unaffected or required admin-safe visibility tested;
- Ruff/format pass;
- browser E2E remains green;
- security/image/IaC scans pass;
- coverage gate passes.

### Azure infrastructure

- Bicep validates;
- intended job/identity/role plan is deployable;
- deployment still leaves discovery off by default.

### Azure runtime

- protected capability probe passes on the exact target resource/model;
- at least one bounded identity run succeeds end to end through promotion;
- zero publication/graph mutation occurs from discovery output.

### Acquisition quality

- official-source lead precision measured;
- duplicate URL rate measured;
- unresolved/third-party rate measured;
- safe-fetch/binding rejection rate measured;
- cost per promoted official lead measured;
- no applicant/private data appears in provider requests/logged query context.

## Explicit non-goals for PR5

PR5 does not yet deliver:

- recurring autonomous schedules;
- global scholarship invention;
- browser fallback;
- OCR / Document Intelligence;
- provenance-safe multi-source extraction aggregation;
- automatic classification approval;
- automatic publication;
- autonomous 500-scholarship scaling.

Those are later phases built on top of PR5's proven acquisition boundary.

## Rule for proceeding

Do not skip a failed proof gate merely because a later layer appears to work.

Examples:

- a successful Azure search does not prove URL policy;
- a successful fetch does not prove ownership;
- a promoted source does not prove scholarship facts;
- an extracted fact does not prove evidence sufficiency;
- CI does not prove Azure runtime;
- Azure runtime does not prove 500-scholarship scale.

Each claim must be reported at its actual proof level.
