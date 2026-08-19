# ADR 0002: Put auditable discovery leads before catalogue candidates

- Status: Accepted for PR5 design; runtime activation remains gated
- Date: 2026-08-19
- Applies to: catalogue acquisition only

## Context

The catalogue ingestion pipeline currently begins with a `SeedCandidate`. That
contract is appropriate for reviewed seeds because a scholarship identity is
already known before source acquisition starts. It is not a safe identity
boundary for autonomous web discovery.

A search result is a URL lead, not a scholarship identity and not evidence. The
same official page can be returned by many queries, several URLs can describe
one scholarship, and one institution funding page can describe several awards.
Promoting search results directly into `CatalogueCandidate` would therefore
inflate duplicates before relationship classification can run.

Officiality is also contextual. A university page can be authoritative for its
own deadline or institution-owned award without being authoritative for an
umbrella provider's global funding terms. A single global `is_official` flag on
a discovered URL would lose that scope.

The product contract requires official-source-backed facts, explicit unknowns,
no unsupported independence decisions, and no AI publication. It also targets
an eventually self-operating acquisition system in which routine discovery is
automated while unresolved ownership, conflicts, and unsupported critical facts
become exceptions.

Microsoft's current Azure documentation is internally inconsistent about the
availability of the stable `web_search` tool in Azure OpenAI Responses. The
product must therefore treat web search as a runtime capability that is proven
in the target subscription/model before activation, not as an assumed service
contract.

## Decision

### 1. Discovery is a separate pre-catalogue domain

PR5 introduces an auditable discovery ledger before `CatalogueCandidate`:

```text
DiscoveryRun
  -> DiscoveryQuery
       -> DiscoveryObservation
            -> DiscoveryLead (global normalized URL identity)
                 -> DiscoveryAssessment (contextual officiality/ownership)
                      -> DiscoveryPromotion
                           -> existing CatalogueCandidate / CandidateSource pipeline
```

A `DiscoveryLead` represents a URL identity only. It must never imply that a
new scholarship exists.

### 2. Search output is never catalogue truth

Web search may return URLs and minimal discovery metadata. Generated prose,
search snippets, ranks, and model assertions are discovery metadata only and
must never populate scholarship facts or `FieldEvidence`.

The only path from a search lead to factual evidence remains:

```text
untrusted URL lead
  -> deterministic URL/scope screening
  -> contextual OfficialSourceClassifier assessment
  -> SafeSourceFetcher
  -> immutable official source snapshot/evidence
  -> deterministic validation
```

### 3. Officiality is assessed in context and is append-only

`DiscoveryAssessment` records the context in which a lead was evaluated:

- scholarship/provider/institution identity hints;
- owner type and resolved owner ID when known;
- canonical domain used for the assessment;
- official/supporting-official/third-party/unresolved result;
- deterministic reason codes;
- classifier version;
- timestamp.

A later assessment supersedes rather than rewrites a previous decision. This
allows an institution page to be official for institution-scoped facts without
implicitly becoming authoritative for global provider facts.

### 4. Promotion is explicit and idempotent

Only a lead with a deterministic acceptable assessment and a safe fetch can be
promoted into the existing candidate/source pipeline. Promotion is recorded in
its own table with a unique `(candidate_id, lead_id)` boundary and the source
assessment that justified it.

PR5 will support the safest frontier first: resolving official sources for an
already-known scholarship/provider/institution identity. The schema must also
support future owner-frontier and global-frontier discovery without requiring a
rewrite, but a globally discovered page may not create an independent
scholarship until later evidence and relationship/independence gates prove it.

### 5. URL deduplication happens before candidate creation

Normalize HTTPS URLs using the existing acquisition URL rules, remove recognized
tracking parameters, reject credential-bearing/authentication/session targets,
and assign a stable URL fingerprint. Equivalent normalized URLs map to one
`DiscoveryLead`; repeated search hits become additional observations.

This is intentionally earlier than the existing `CatalogueCandidate`
idempotency key, which remains in force after promotion.

### 6. Query planning is deterministic, versioned, and bounded

PR5 uses a deterministic `DiscoveryQueryPlanner` rather than an open-ended
agent. The planner receives structured public catalogue metadata and emits a
bounded ordered query set. Every run records its planner version and hard
limits.

No recursive autonomous search, deep-research agent, browser search loop, or
unbounded query expansion is permitted in PR5.

### 7. Discovery has an independent Azure provider contract

The Responses/Web Search provider is configured independently from extraction:

- separate feature flag;
- separate endpoint/model/token-scope settings;
- separate call, URL, response-byte, timeout, retry, and cost ceilings;
- `DefaultAzureCredential` / managed identity;
- no API key or client secret where managed identity works;
- no silent fallback from stable to preview search tools.

The provider is fail-closed. If a response does not prove that the web-search
tool actually executed, the query is failed rather than treating generated
model text as discovery output.

### 8. Applicant data is outside the discovery trust boundary

Discovery requests may contain only public catalogue metadata such as
scholarship/provider/institution/programme names, countries, aliases, and
reviewed public domains.

They must never contain student profiles, email addresses, CVs, transcripts,
application data, uploaded documents, personal statements, assistant
conversations, or other applicant PII.

Before autonomous scheduling, the discovery job should use a catalogue-scoped
database principal/credential that cannot read applicant/profile/application
or private-document tables. Application-layer validation is defense in depth,
not the only privacy control.

### 9. PostgreSQL remains the durable queue/lease authority

PR5 follows the existing modular-monolith decision. PostgreSQL stores discovery
state, idempotency, claims, and audit records. Redis is not introduced solely
for discovery locking. Workers use bounded leases and `FOR UPDATE SKIP LOCKED`
/compare-and-set patterns consistent with the existing ingestion repository.

### 10. Migrations stay incremental

Do not squash migrations during active catalogue development. PR5 may add the
next migration after the current `20260817_0040` head. Later phases continue
with explicit expand/forward-fix/downgrade strategy so the deployment history
remains reviewable.

### 11. Automation is an activation phase, not a PR5 side effect

PR5 may add a discovery job and deployment configuration, but web discovery
remains disabled by default and is not scheduled automatically. Activation
requires:

1. offline CI with fake provider fixtures;
2. Azure infrastructure validation;
3. a protected target-subscription capability probe;
4. a reviewed discovery Gold evaluation;
5. measured cost/latency/error data;
6. explicit staging activation.

Recurring autonomous scheduling belongs to the later orchestrator phase after
quality gates pass. `APP_CATALOGUE_AUTO_PUBLISH_ENABLED` remains false.

## Required invariants

- Search results are leads, never evidence.
- A discovery lead cannot directly create/publish an `Opportunity`.
- One normalized URL has one global lead identity; queries create observations.
- Officiality is contextual and versioned/append-only.
- Promotion requires deterministic officiality plus safe acquisition.
- Candidate idempotency and PR3 relationship/independence rules remain active.
- Unknown ownership remains unresolved; it is not guessed.
- No applicant PII is sent to web discovery.
- Every provider call and promotion is budgeted/auditable.
- Discovery, extraction, crawler, browser, OCR, and publication kill switches
  remain independent.

## Consequences

### Positive

- Search noise cannot inflate the scholarship count directly.
- Repeated queries naturally deduplicate before expensive fetch/extraction work.
- Discovery provenance is inspectable without treating search prose as truth.
- The same schema supports identity resolution now and broader autonomous
  discovery later.
- Provider/search outages can be disabled without disabling the rest of the
  catalogue.
- Human involvement can become exception-based rather than routine URL entry.

### Costs

- PR5 adds several small relational tables instead of a single provider class.
- Promotion is a deliberate extra state transition.
- The system must maintain two identities: URL-lead identity and scholarship
  candidate identity.
- A live capability/quality gate is required before web discovery can be used in
  staging automation.

These costs are accepted because they prevent duplicate inflation, scope
corruption, and search-generated claims from entering the catalogue.

## Alternatives rejected

### Search result -> `CatalogueCandidate`

Rejected because search titles/URLs do not prove scholarship identity and would
create duplicates before the relationship classifier can protect the graph.

### Store search prose and extract facts from it

Rejected because discovery and evidence would collapse into one trust boundary.

### One mutable `is_official` flag per URL

Rejected because source authority depends on owner and fact scope.

### Agentic recursive discovery in PR5

Rejected because query/cost/error behavior would be difficult to bound and
measure before the base discovery quality is proven.

### New microservice / message broker for discovery

Rejected because the repository already uses a modular monolith and PostgreSQL
leases successfully; no measured scale requires another distributed system.

### Automatic publication after successful discovery

Rejected. Discovery can at most feed the existing evidence, classification,
validation, and review workflow. Publication governance is unchanged.
