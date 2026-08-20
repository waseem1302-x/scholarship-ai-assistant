# PR5 — Auditable Web Discovery Implementation Contract

- Status: Architecture-only implementation contract; no PR5 runtime code authorized by this document
- Date: 2026-08-19
- Last reconciled: 2026-08-20 against ADRs 0003-0006 and the Azure feature baseline
- Integration baseline: Azure feature head `552ff0137fca7ff806a13f24e6a10ce79097682a`
- Architecture branch: `scholarship-graph/pr5-discovery-architecture`
- Related decisions: ADRs 0002-0006 in `docs/decisions/`
- Product contract: `docs/scholarship-information-contract.md`

## 1. PR5 objective

PR5 removes routine manual official-URL hunting for already-known public scholarship/provider/institution identities while preserving the platform's source-first truth boundary.

PR5 must answer this question safely:

> Given public catalogue identity hints, which URLs are worth investigating as possible official sources?

PR5 does **not** answer:

> What are the scholarship facts?

and it does **not** prove:

> This URL represents a new independent scholarship.

Those decisions remain downstream of official-source acquisition, evidence, deterministic validation, and PR3 relationship/independence rules.

## 2. Scope

### In scope

- durable discovery runs and query ledger;
- deterministic/versioned query planning;
- Azure OpenAI Responses Web Search provider behind an interface;
- URL extraction from successful web-search responses;
- strict URL normalization/screening;
- global URL-lead deduplication;
- per-query observation provenance;
- contextual source assessment using existing official-source rules;
- explicit binding to an already-known target candidate before network acquisition;
- authoritative safe-fetch confirmation through the existing ingestion boundary before promotion;
- idempotent promotion into the existing `CatalogueCandidate` / candidate-source pipeline;
- low-cardinality discovery metrics;
- protected live capability/evaluation workflow;
- a separate manual Azure Container Apps discovery job;
- fail-closed production configuration;
- admin-safe read visibility for runs/leads/assessments if needed for staging evaluation;
- tests, docs, migration downgrade/forward-fix notes.

### Explicitly out of scope

- autonomous global scholarship-name invention/discovery;
- recursive agentic search;
- deep research;
- browser or Playwright acquisition;
- OCR / Document Intelligence;
- multi-source extraction aggregation;
- automatic relationship approval;
- automatic publication;
- recurring autonomous schedules;
- public search-result pages backed directly by Web Search;
- applicant-specific discovery queries;
- direct mutation of the canonical graph from search output.

## 3. Architectural placement

```text
Public catalogue identity / reviewed backlog
                   ↓
         DiscoveryQueryPlanner
                   ↓
      WebDiscoveryProvider interface
                   ↓
     Azure Responses Web Search
                   ↓
        untrusted URL results
                   ↓
        Discovery Ledger
                   ↓
   URL policy + contextual assessment
                   ↓
 explicit known-candidate authorization
                   ↓
 CandidateSource(DISCOVERED) binding
                   ↓
 existing ingestion / SafeSourceFetcher
                   ↓
 final owner + target-content verification
                   ↓
 CandidateSource(FETCHED) + DiscoveryPromotion
                   ↓
          PR4 bounded crawler
                   ↓
 evidence / extraction / PR3 classification / review
```

The discovery service never creates a candidate from a URL and never writes `Opportunity`, `SourceSnapshot`, `FieldEvidence`, or publication state directly. `SafeSourceFetcher` remains owned by the existing ingestion service; discovery does not introduce a second fetch path.

## 4. Discovery frontier supported by PR5

PR5 supports **identity resolution** only.

Examples:

- `Chevening Scholarship` → find current official provider/government URL candidates;
- `MEXT Scholarship` + provider/country hints → find official Ministry/Embassy/provider source candidates;
- known institution + known scheme → find likely official institution route page candidates;
- reviewed provider domain → optionally domain-constrain a query.

PR5 does not create a new scholarship when it encounters a page for an unknown named award. Such a URL can be preserved as an unpromoted lead for later owner/global-frontier work, but it cannot inflate the canonical scholarship count.

## 5. Proposed persistent model

PR5 should add the next incremental Alembic migration after the current `20260817_0040` head. Do not squash existing migrations.

### 5.1 `catalogue_discovery_runs`

One bounded execution.

Required fields:

```text
id UUID PK
target_candidate_id UUID FK -> catalogue_candidates ON DELETE SET NULL nullable
target_identity_snapshot json NOT NULL
objective_kind varchar(64)
objective_scope json NOT NULL
objective_field_paths json NOT NULL
objective_reason_codes json NOT NULL
objective_criticality_tier int NOT NULL
objective_priority_snapshot json NOT NULL
planner_version varchar(100)
provider varchar(100)
model varchar(255)
status varchar(32)
dry_run bool
max_queries int
max_provider_calls int
max_leads int
max_response_bytes int
max_estimated_cost numeric(12,6)
provider_calls_reserved int default 0
provider_calls_completed int default 0
estimated_cost_reserved numeric(12,6) default 0
estimated_cost_settled numeric(12,6) default 0
raw_leads_seen int default 0
unique_leads int default 0
promotions int default 0
failure_code varchar(100) nullable
aggregate_summary json
created_at timestamptz
started_at timestamptz nullable
completed_at timestamptz nullable
```

`objective_kind` uses the deterministic taxonomy from ADR 0005, beginning with:

```text
RESOLVE_CANONICAL_SOURCE
RESOLVE_PROVIDER_IDENTITY
CURRENT_CYCLE_STATUS
CURRENT_APPLICATION_DEADLINE
FUNDING_COVERAGE
ELIGIBILITY_CORE
APPLICATION_ROUTE
PARTICIPATING_INSTITUTIONS
ELIGIBLE_PROGRAMMES
CONFLICT_RESOLUTION_SOURCE
FRESHNESS_REFRESH
```

Only a non-null `target_candidate_id` can authorize PR5 source binding. The immutable target and objective snapshots preserve why the run existed; they are bounded typed payloads, never arbitrary ORM dumps. Future objective kinds may be added without changing current promotion rules.

### 5.2 `catalogue_discovery_queries`

One deterministic query planned for a run.

```text
id UUID PK
run_id UUID FK -> catalogue_discovery_runs ON DELETE CASCADE
ordinal int
query_text varchar(1000)
query_hash varchar(64)
query_kind varchar(64)
allowed_domains json
public_context json
status varchar(32)
attempt_count int default 0
next_attempt_at timestamptz nullable
claimed_by varchar(100) nullable
claimed_until timestamptz nullable
provider_call_count int default 0
response_bytes int default 0
latency_ms int default 0
estimated_cost numeric(12,6) default 0
failure_code varchar(100) nullable
created_at timestamptz
completed_at timestamptz nullable
```

Constraints:

- unique `(run_id, ordinal)`;
- unique `(run_id, query_hash)`;
- `query_text` contains public catalogue metadata only;
- `public_context` must be a deliberately small schema, not an arbitrary application object dump.

The query row is mutable worker/current-state data. Its provider and cost values are aggregates only; `catalogue_discovery_attempts` is authoritative for individual outbound calls.

### 5.3 `catalogue_discovery_attempts`

One durable row per outbound provider request attempt.

```text
id UUID PK
query_id UUID FK -> catalogue_discovery_queries ON DELETE RESTRICT
attempt_number int
status varchar(32)
request_fingerprint varchar(64)
provider varchar(100)
model varchar(255)
provider_response_id varchar(255) nullable
http_status int nullable
web_search_executed bool nullable
tool_call_count int default 0
result_url_count int default 0
response_bytes int default 0
input_tokens int nullable
output_tokens int nullable
estimated_model_cost numeric(12,6) default 0
estimated_tool_cost numeric(12,6) default 0
estimated_total_cost numeric(12,6) default 0
latency_ms int nullable
error_code varchar(100) nullable
started_at timestamptz
completed_at timestamptz nullable
```

Constraints and lifecycle:

- unique `(query_id, attempt_number)` and positive attempt numbers;
- non-negative tool/result/byte/cost counters;
- insert as `IN_PROGRESS` before network I/O;
- transition once to a terminal result, or to `ABANDONED` during expired-lease recovery;
- never retain raw provider bodies, grounded prose, credentials, or applicant context.

Before inserting `IN_PROGRESS`, atomically reserve the provider request, worst-case tool-call allowance, and worst-case estimated request cost on the parent run. Settle the reservation transactionally with the terminal attempt and query/run aggregates. A crash may conservatively consume capacity, but concurrent workers must never overspend the run ceiling.

### 5.4 `catalogue_discovery_leads`

Global normalized URL identity. A row means "this public URL has been observed", not "this is a scholarship".

```text
id UUID PK
normalized_url varchar(2048)
url_fingerprint varchar(64)
host varchar(255)
first_seen_at timestamptz
last_seen_at timestamptz
active bool default true
created_at timestamptz
```

Constraints:

- unique `url_fingerprint`;
- unique `normalized_url` where database semantics make this safe;
- HTTPS-only normalized URL;
- no username/password components.

Do not store search-result prose as evidence on this row.

### 5.5 `catalogue_discovery_observations`

A query/result relationship.

```text
id UUID PK
query_id UUID FK -> catalogue_discovery_queries ON DELETE RESTRICT
lead_id UUID FK -> catalogue_discovery_leads ON DELETE RESTRICT
provider_rank int nullable
provider_source_type varchar(64) nullable
minimal_title varchar(500) nullable
discovery_reason varchar(255)
observed_at timestamptz
```

Constraints:

- unique `(query_id, lead_id)`;
- title is discovery metadata only and has a bounded length;
- snippets/body prose are not retained by default.

### 5.6 `catalogue_discovery_assessments`

Append-only contextual officiality/ownership assessment.

```text
id UUID PK
lead_id UUID FK -> catalogue_discovery_leads ON DELETE RESTRICT
run_id UUID FK -> catalogue_discovery_runs ON DELETE RESTRICT
assessment_context_hash varchar(64)
context_type varchar(64)
context_scholarship_id UUID nullable
context_provider_id UUID nullable
context_institution_id UUID nullable
context_cycle_id UUID nullable
owner_type varchar(32)
owner_id UUID nullable
canonical_domain varchar(255) nullable
officiality_status varchar(32)
trust_tier int nullable
reason_code varchar(100)
reason_detail varchar(500)
classifier_version varchar(100)
supersedes_assessment_id UUID FK -> catalogue_discovery_assessments ON DELETE RESTRICT nullable
created_at timestamptz
```

`officiality_status`:

```text
official
supporting_official
third_party
unresolved
rejected_url_policy
```

This table is append-only. Do not mutate an old assessment from unresolved to official; create a new assessment and link the superseded record.

### 5.7 `catalogue_discovery_promotions`

Explicit bridge into the existing ingestion domain.

```text
id UUID PK
run_id UUID FK -> catalogue_discovery_runs ON DELETE RESTRICT
lead_id UUID FK -> catalogue_discovery_leads ON DELETE RESTRICT
assessment_id UUID FK -> catalogue_discovery_assessments ON DELETE RESTRICT
candidate_id UUID FK -> catalogue_candidates ON DELETE RESTRICT
candidate_source_id UUID FK -> catalogue_candidate_sources ON DELETE SET NULL nullable
promotion_kind varchar(64)
reason_code varchar(100)
created_at timestamptz
```

Constraints:

- unique `(candidate_id, lead_id)`;
- assessment must belong to the same lead;
- promotion occurs only after an acceptable deterministic assessment and successful `SafeSourceFetcher` result;
- promotion cannot set opportunity/publication state.

### 5.8 Existing `catalogue_candidate_sources` refinement

Add the provenance link defined by ADR 0003:

```text
discovery_lead_id UUID FK -> catalogue_discovery_leads ON DELETE SET NULL nullable
```

with unique `(candidate_id, discovery_lead_id)` for non-null lead IDs. Discovery binds a selected lead to the known target as a `DISCOVERED` candidate source before the ingestion service fetches it. Seed/manual/crawler-created sources retain `discovery_lead_id = NULL`.

### 5.9 Deletion and immutability policy

- attempts preserve each call and allow only `IN_PROGRESS` to terminal mutation;
- observations, assessments, and promotions are immutable business provenance;
- assessments supersede rather than rewrite prior decisions;
- downstream provenance uses `RESTRICT`; only the run-to-query relationship may cascade while no attempt or other protected provenance exists;
- retention must be an explicit reviewed policy, never an accidental cascade.

## 6. State machines

### 6.1 Discovery run

```text
PENDING
  -> RUNNING
      -> COMPLETED
      -> PARTIAL
      -> BUDGET_EXHAUSTED
      -> CAPABILITY_UNAVAILABLE
      -> FAILED
```

A run is `PARTIAL` when at least one query produced valid processed results but another non-fatal query failed after bounded retries.

### 6.2 Discovery query

```text
PLANNED
  -> CLAIMED
  -> CALLING_PROVIDER
  -> RESPONSE_RECEIVED
  -> LEADS_RECORDED
  -> COMPLETED

Terminal alternatives:
  PROVIDER_RATE_LIMITED
  PROVIDER_FAILED
  TOOL_NOT_EXECUTED
  RESPONSE_INVALID
  BUDGET_EXHAUSTED
  CAPABILITY_UNAVAILABLE
  CANCELLED
```

Retryable terminal states may move back to `PLANNED` only through explicit bounded retry scheduling and attempt limits.

### 6.3 Provider attempt

```text
IN_PROGRESS
  -> SUCCEEDED
  -> RATE_LIMITED
  -> TIMEOUT
  -> PROVIDER_FAILED
  -> RESPONSE_INVALID
  -> TOOL_NOT_EXECUTED
  -> CAPABILITY_UNAVAILABLE
  -> BUDGET_REJECTED
  -> ABANDONED
```

Every provider request has exactly one attempt row allocated before network I/O. A retry always receives a new `attempt_number`.

### 6.4 Lead assessment

Lead identity itself does not need a mutable state machine. Context-specific assessment records capture outcomes append-only:

```text
URL_POLICY_REJECTED
THIRD_PARTY
UNRESOLVED
SUPPORTING_OFFICIAL
OFFICIAL
```

### 6.5 Promotion

Promotion is an event, not a mutable lifecycle. A duplicate promotion attempt returns/reuses the existing promotion row.

## 7. Query planner contract

`DiscoveryQueryPlanner` must be deterministic and versioned.

Input schema example:

```python
class DiscoveryObjective(BaseModel):
    objective_kind: DiscoveryObjectiveKind
    scholarship_id: UUID | None
    candidate_id: UUID | None
    cycle_id: UUID | None
    track_id: UUID | None
    institution_id: UUID | None
    programme_id: UUID | None
    field_paths: tuple[str, ...]
    reason_codes: tuple[str, ...]
    criticality_tier: int
    scholarship_name: str | None
    scholarship_aliases: tuple[str, ...]
    provider_name: str | None
    institution_name: str | None
    country: str | None
    programme_name: str | None
    reviewed_domains: tuple[str, ...]
```

No student/application/document fields are accepted by this schema.

Initial planner version: `catalogue-discovery-query.v1`.

Planner characteristics:

- exact scholarship identity query first;
- provider/country refinement second;
- institution/route refinement only when the objective contains that context;
- optional `allowed_domains` only when the domain is already reviewed/resolved;
- hard maximum query count from settings;
- normalized query hash prevents duplicate calls within a run;
- no query generated from model output;
- no recursive search planning from discovered snippets/prose.

## 8. Provider interface

Proposed interface:

```python
class DiscoveryProvider(Protocol):
    def search(
        self,
        request: DiscoveryProviderRequest,
        *,
        budget: DiscoveryBudget,
    ) -> DiscoveryProviderResult: ...
```

`DiscoveryProviderResult` returns only what the discovery domain needs:

```text
provider_response_id
web_search_executed bool
urls[]
provider_call_count
tool_call_count
response_bytes
latency_ms
usage/cost fields available from provider
```

Do not expose grounded answer prose to downstream extraction code.

## 9. Azure Responses provider contract

Provider name: `azure_responses_web_search`.

### Required configuration

Keep separate from catalogue extraction settings:

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
APP_CATALOGUE_DISCOVERY_MAX_ESTIMATED_COST_PER_RUN=<reviewed value>
APP_CATALOGUE_DISCOVERY_MAX_ESTIMATED_COST_PER_PROVIDER_REQUEST=<reviewed value>
APP_CATALOGUE_DISCOVERY_MAX_TOOL_CALLS_PER_PROVIDER_REQUEST=1
```

If discovery is enabled in production/staging, startup/job validation must reject:

- provider `unavailable`;
- missing HTTPS endpoint;
- model `unconfigured`;
- non-positive required spend/call ceilings;
- a per-request reservation greater than the corresponding run ceiling;
- malformed token scope;
- configurations that silently enable preview fallback.

### Tool selection

The implementation targets stable `web_search` only when the actual Azure resource proves that capability. The provider does not automatically downgrade to `web_search_preview`.

Microsoft documentation currently contains conflicting statements between the Web Search how-to and the newer REST reference. Therefore the actual target subscription/model must pass the capability probe before `APP_CATALOGUE_WEB_DISCOVERY_ENABLED=true` is accepted for a live acquisition run.

### Authentication

Use `DefaultAzureCredential` / user-assigned managed identity in Azure. No committed API keys. No client secret when managed identity works.

### Response acceptance

A successful HTTP response is not enough.

The parser must verify:

- the response contains a `web_search_call` output item;
- provider/tool status is successful where surfaced;
- returned URLs come from tool source/citation structures defined by the supported API response;
- URLs pass length/scheme parsing before persistence;
- response body is below the configured hard byte limit.

If `web_search_call` is absent, store `TOOL_NOT_EXECUTED`; do not parse URLs from generated message prose.

## 10. URL policy and normalization

Reuse/refactor the same acquisition URL normalization semantics already used by the bounded crawler rather than creating incompatible canonicalization.

Reject before lead creation when possible:

- non-HTTPS scheme;
- username/password in URL;
- empty/invalid hostname;
- localhost/private/internal literals;
- obvious login/sign-in/account/session/logout paths where search results provide them;
- unsupported oversized URLs.

Remove recognized tracking parameters and fragments when normalizing.

Do **not** fetch the URL in the search-provider code. Fetching remains the `SafeSourceFetcher` responsibility.

## 11. Assessment contract

The existing `OfficialSourceClassifier` remains the deterministic base, but PR5 wraps its result in contextual assessment provenance.

Assessment inputs can include:

- provider canonical website;
- resolved institution website/domain;
- reviewed official domains;
- known scholarship/provider/institution identity context.

Important rule:

> Official source authority is not universal across all facts.

An institution URL may be `supporting_official` for local facts even when it is not authoritative for umbrella-provider global terms.

PR5 does not redesign the downstream `Source` table in this PR. It records richer context in the discovery assessment so later evidence/source work can preserve scope correctly.

## 12. Candidate binding and authoritative safe-fetch promotion gate

An acceptable discovery assessment alone is insufficient for binding or promotion. Binding is authorized only for the run's explicit, known `target_candidate_id`; a human-readable label cannot substitute for that foreign key.

Promotion sequence:

```text
lead
 -> acceptable contextual assessment
 -> deterministic root selection for the known target candidate
 -> create/reuse CandidateSource(DISCOVERED, discovery_lead_id)
 -> existing CatalogueIngestionService
 -> SafeSourceFetcher.fetch(candidate_source.url)
 -> fetch policy success and final URL canonicalization
 -> final ownership/officiality and target-content verification
 -> CandidateSource(FETCHED)
 -> DiscoveryPromotion record
```

Failures:

- SSRF/DNS/private peer -> no promotion;
- robots blocked -> unresolved/manual-review path, no promotion as fetched evidence;
- login/CAPTCHA -> no promotion;
- unsafe cross-domain redirect -> no promotion;
- unsupported MIME -> no promotion;
- provider search says official but deterministic classifier disagrees -> deterministic result wins.

The discovery worker does not fetch the lead before binding. A blocked or failed fetch retains the source binding and discovery provenance but creates no promotion event. Redirect convergence must reconcile multiple leads to one effective canonical candidate source without deleting either lead's observation history.

PR4 bounded crawling may run only after this official fetched root exists and its independent crawler feature flag is enabled.

## 13. Idempotency and concurrency

### Query idempotency

`query_hash = SHA256(planner_version + normalized objective + normalized query + allowed_domains)`.

Same run + same hash cannot produce two query rows.

### Lead idempotency

`url_fingerprint = SHA256(normalized_url)`.

A globally repeated URL reuses the same lead and adds an observation.

### Assessment idempotency

`assessment_context_hash` includes:

```text
lead fingerprint
classifier version
context type
resolved owner IDs/domains
scholarship/provider/institution context IDs
```

The service may reuse an identical current assessment rather than append an identical duplicate. A materially changed classifier/context creates a new assessment.

### Promotion idempotency

Unique `(candidate_id, lead_id)`.

### Worker claims

Follow the existing ingestion repository pattern:

```text
SELECT ...
FOR UPDATE SKIP LOCKED
```

with bounded `claimed_until`, `attempt_count`, and `next_attempt_at`.

No Redis dependency is added solely for discovery work.

## 14. Retry policy

Retry only transient categories:

- network timeout;
- provider 429;
- provider 5xx;
- selected transient Entra/token acquisition failure.

Do not repeatedly retry:

- invalid request/schema;
- unauthorized/forbidden caused by persistent configuration;
- `TOOL_NOT_EXECUTED` after the bounded provider strategy has been attempted;
- subscription capability unavailable;
- deterministic URL-policy rejection;
- third-party assessment.

Backoff includes bounded exponential delay with jitter. Exact values are implementation details but must be deterministic under tests via an injected clock/random source.

A single failing query must not cause successful prior lead observations to be rolled back.

## 15. Budget model

Discovery budget is separate from extraction budget.

Enforce before each provider call:

- query count;
- provider call count;
- unique lead count;
- URLs per query;
- response-byte ceiling;
- estimated spend ceiling.

The enforcement operation is an atomic reservation, not a read-then-increment check. It reserves one provider request, the configured worst-case tool calls, and the configured worst-case request cost before network I/O. Provider requests and actual web-search tool calls are separate counters and budgets.

When the next call would exceed a hard ceiling:

```text
run -> BUDGET_EXHAUSTED
remaining queries -> CANCELLED/BUDGET_EXHAUSTED
no additional provider call
```

Do not use Azure budget alerts as the application hard stop; they are operational alerts only.

## 16. Privacy and data-access contract

PR5 discovery is public catalogue acquisition, not student personalization.

Allowed outbound values:

- public scholarship names/aliases;
- public provider/institution names;
- country/region;
- public programme names;
- reviewed public domains.

Never send:

- student/user names or emails;
- nationality sourced from a student's profile;
- grades/GPA/tests/work experience from profiles;
- saved/application state;
- CV/transcript/document contents;
- essays/personal statements;
- private conversations;
- any applicant/application PII.

Before recurring automation is enabled, use a database principal/connection contract with catalogue-only read/write access required for discovery. It should be unable to select from applicant/profile/application/private-document tables.

Logs and metrics must never include full provider response bodies or applicant data.

## 17. Metrics

Extend the existing low-cardinality metrics module. No URL/domain/query strings as metric labels.

Counters:

```text
discovery_runs_total
discovery_queries_planned
discovery_provider_calls
discovery_provider_failures
discovery_tool_not_executed
discovery_raw_leads
discovery_unique_leads
discovery_duplicate_observations
discovery_url_policy_rejections
discovery_third_party_leads
discovery_unresolved_leads
discovery_official_leads
discovery_supporting_official_leads
discovery_safe_fetch_failures
discovery_promotions
discovery_budget_exhaustions
```

Histograms:

```text
discovery_provider_latency_seconds
discovery_queue_lag_seconds
discovery_estimated_cost_usd
discovery_leads_per_query
discovery_cost_per_promotion_usd
```

Detailed URLs/reason context live in audit tables, not telemetry dimensions.

## 18. Admin/staging visibility

If PR5 adds admin read endpoints, they are read-only and admin-protected:

```text
GET /admin/catalogue-discovery/runs
GET /admin/catalogue-discovery/runs/{id}
GET /admin/catalogue-discovery/leads
GET /admin/catalogue-discovery/leads/{id}
```

Required visibility:

- run status and budgets;
- query status/failure code;
- lead normalized URL;
- observation provenance;
- latest/contextual assessments;
- promotion target if any.

Do not expose raw Web Search response payloads as an admin convenience feature.

No admin write/approve endpoint is required in PR5 unless implementation reveals a necessary exception workflow; unresolved ownership can remain persisted for the later review-system phase.

## 19. Azure deployment contract

### Separate discovery job

Add a **manual-only** Container Apps Job:

```text
<resourcePrefix>-catalogue-discovery
```

Do not silently combine discovery scheduling with the existing catalogue-ingestion job.

Reasons:

- distinct privacy boundary;
- independent feature switch;
- independent Azure capability failure;
- independent cost budget;
- future schedule can be enabled without scheduling extraction;
- easier incident rollback.

Initial trigger:

```text
Manual
parallelism: 1
replicaCompletionCount: 1
replicaRetryLimit: 0
```

Default command should be a non-running safe command such as `--help` until an operator supplies an explicit discovery objective or protected evaluation workflow starts it.

### Environment

Pass discovery-only settings independently of extraction settings. The existing runtime managed identity may be reused only if its permissions are still least-privilege for both. Before autonomous scheduling, prefer a dedicated catalogue-discovery identity if doing so materially reduces database or service access.

### Roles

Minimum Azure role for the chosen Azure OpenAI resource must be validated against the actual web-search deployment path. Do not add broad Contributor/Owner roles merely to make the tool work.

### Cross-resource scope

PR5 must not silently assume the Azure OpenAI resource lives in the discovery job's resource group. If staging will call an existing account in another resource group, Bicep must model that scope explicitly or use a dedicated staging resource. Keep that topology decision separate from discovery business logic.

## 20. Capability probe

A protected staging/manual capability probe runs before live discovery is enabled.

It sends a harmless public query and asserts:

1. authentication succeeds;
2. Responses endpoint accepts configured model/tool;
3. actual response contains `web_search_call`;
4. at least one public URL source/citation can be parsed;
5. provider response is within configured limits;
6. no applicant/private data is sent;
7. observed provider/tool behavior matches the parser contract.

Failure leaves discovery disabled. It must not trigger preview fallback automatically.

## 21. Discovery Gold evaluation

Initial Gold set target: approximately 50 public identity-resolution cases.

Include:

- major government flagship schemes;
- university-owned independent awards;
- ambiguous acronyms/translations;
- providers with strong third-party SEO noise;
- institution route pages;
- names that deliberately should remain unresolved;
- known aggregator/directory results;
- equivalent URLs with tracking variants.

Per item expected fields:

```text
objective
expected canonical/official domain set
acceptable supporting-official domain set
explicitly rejected third-party domains
minimum acceptable official lead rank/window
whether promotion should occur
```

Proposed activation gates:

- 100% live test calls prove `web_search_call` when provider reports success;
- >=95% expected official-domain recall within bounded results on reviewed Gold;
- 100% automatically promoted leads pass deterministic officiality and SafeSourceFetcher;
- 100% known third-party directory cases do not auto-promote;
- 0 search snippets/prose become evidence;
- 0 applicant PII sent in requests/logs;
- 0 duplicate global lead rows for equivalent normalized URLs;
- 0 direct publication paths;
- all hard budgets enforced;
- cost/latency recorded and reviewed.

A failed gate means improve planner/parser/officiality logic and rerun the evaluation; do not weaken the gate to fit the result.

## 22. Test matrix

### Unit

- deterministic query planner ordering/versioning;
- public-context schema rejects student/private fields;
- query hash stability;
- URL normalization/tracking removal;
- URL fingerprint dedup;
- credential/login/non-HTTPS rejection;
- Azure response parser requires `web_search_call`;
- parser ignores generated prose URLs;
- provider response byte ceiling;
- retry categorization;
- cost/call budget enforcement;
- durable attempt creation, terminal immutability, and query aggregate reconciliation;
- atomic budget reservation under concurrent workers;
- assessment context hashing;
- contextual officiality examples;
- promotion requires a known-target binding followed by authoritative ingestion safe-fetch acceptance;
- metrics reject unsupported/high-cardinality names.

### PostgreSQL integration

- concurrent workers do not claim the same query;
- expired leases can be reclaimed;
- stale in-progress attempts become `ABANDONED` before retrying with a new attempt number;
- concurrent reservations cannot exceed provider, tool-call, or estimated-cost ceilings;
- same normalized URL from many queries creates one lead;
- observations remain distinct;
- append-only assessment behavior;
- identical assessment reuse / supersession semantics;
- duplicate promotion is idempotent;
- partial run completion preserves successful observations;
- downgrade/upgrade migration rehearsal.

### Security

- no provider call when feature flag disabled;
- no provider call with invalid production configuration;
- no URL fetched outside `SafeSourceFetcher`;
- discovery never fetches a lead before candidate-source binding;
- no search prose written to `FieldEvidence`/canonical facts;
- no automatic publication;
- URL policy blocks credentials/private targets;
- discovery payload serialization cannot accept applicant/profile objects.

### Azure/Bicep

- discovery job exists but is manual by default;
- discovery feature flag defaults false;
- no schedule trigger is introduced by PR5;
- no API key secret required for normal managed-identity path;
- extraction flags are not implicitly enabled by discovery;
- browser/OCR/auto-publish remain false/unconfigured.

## 23. Rollback and incident controls

Immediate stop:

```text
APP_CATALOGUE_WEB_DISCOVERY_ENABLED=false
```

or deploy the equivalent Bicep parameter false and do not start the manual discovery job.

Disabling discovery must not disable:

- existing published catalogue reads;
- source monitoring;
- admin review;
- existing seed-only candidate ingestion;
- PR4 bounded crawling when independently enabled for reviewed official roots.

If provider output/parser behavior changes:

1. disable discovery;
2. retain discovery ledger for audit;
3. do not delete already reviewed canonical catalogue truth;
4. fix parser/provider contract behind the disabled flag;
5. rerun offline fixtures and protected capability/Gold evaluation before reactivation.

Migration rollback removes only PR5 discovery ledger tables/config usage. It must not delete canonical opportunities, evidence snapshots, or PR1–PR4 graph/source state.

## 24. PR5 implementation file plan

Expected narrow file surface (names may adjust after code review):

```text
app/modules/catalogue_ingestion/discovery_models.py   # or bounded additions to models.py
app/modules/catalogue_ingestion/discovery.py
app/modules/catalogue_ingestion/discovery_repository.py
app/modules/catalogue_ingestion/discovery_service.py
app/modules/catalogue_ingestion/discovery_provider.py
app/cli/discover_catalogue_sources.py
app/core/config.py
app/modules/catalogue_ingestion/metrics.py
alembic/versions/<next>_catalogue_discovery_ledger.py
infra/azure/scheduled-jobs.bicep
.env.example
.github/workflows/catalogue-discovery-eval.yml
 tests/test_catalogue_discovery_*.py
 tests/test_pr5_azure_wiring.py
 docs/catalogue-ingestion-pipeline.md
```

Avoid rewriting `CatalogueIngestionService` wholesale. Adapt the existing `WebDiscoveryProvider` seam or bridge promotions into the existing service with a small explicit boundary.

## 25. Review stop conditions

Stop PR5 implementation and return to architecture review if any of these become necessary:

- search output must directly create a canonical scholarship;
- facts must be extracted from search snippets to meet coverage goals;
- officiality cannot be resolved without model guessing;
- the provider requires applicant data;
- production requires broad Azure roles or persisted API keys with no approved alternative;
- a raw HTTP client is needed outside `SafeSourceFetcher` to fetch discovered evidence pages;
- query recursion is needed to meet the initial identity-resolution scope;
- PR5 starts changing multi-source evidence semantics or browser/OCR behavior;
- automatic scheduling/publication becomes necessary for tests to pass.

These are signs that scope or trust boundaries are being violated, not reasons to bypass them.

## 26. PR5 definition of done

PR5 is **implemented** when:

- discovery ledger migration/models/repositories exist;
- deterministic query planner exists;
- Azure Responses provider and strict parser exist;
- URL dedup/assessment/promotion gates exist;
- separate fail-closed settings/job exist;
- fake-provider tests and PostgreSQL concurrency tests pass;
- documentation matches code.

PR5 is **CI-proven** when the exact final head passes all required repository checks including migration rehearsal, security, browser regression, and Azure infrastructure validation.

PR5 is **Azure-runtime-proven** only when the target Azure environment passes the protected capability probe and Gold evaluation with measured cost/latency and the configured activation gates.

PR5 is **not** production-autonomous when it merely reaches those states. Scheduled autonomous acquisition remains a later orchestrator gate.

## 27. Strategic handoff to later phases

After PR5 is proven:

```text
PR6 — provenance-safe multi-source evidence bundles
PR7 — verified browser / scanned-PDF fallbacks
PR8 — autonomous acquisition orchestrator and schedules
PR9 — exception-focused review/quality operations and catalogue growth
```

The long-term system can then use search demand, known providers/institutions, freshness gaps, and scholarship completeness gaps to create new discovery objectives automatically while preserving this same lead/evidence/promotion boundary.
