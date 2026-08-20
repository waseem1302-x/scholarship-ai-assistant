# PR5 architecture integration audit

- Date: 2026-08-20
- Audited PR: draft PR 17, `scholarship-graph/pr5-discovery-architecture`
- Integration baseline: `feature/azure-ai-catalogue-pipeline` at `552ff0137fca7ff806a13f24e6a10ce79097682a`
- Scope: architecture, repository integration seams, CI shape, and read-only Azure capability posture
- Runtime/provider calls: none
- Azure mutations or billable probes: none

## Result

PR5 remains architecture-only. Its central design is suitable for the next acquisition layer after the corrections recorded below, but it does not prove Azure Web Search availability and does not authorize runtime implementation on the architecture branch.

The durable boundary is:

```text
deterministic objective
  -> bounded Web Search request
  -> immutable lead/observation/attempt provenance
  -> contextual deterministic assessment
  -> explicit binding to a known CatalogueCandidate
  -> existing CatalogueIngestionService / SafeSourceFetcher
  -> final owner and target-content verification
  -> fetched CandidateSource + promotion event
```

Search results remain leads, never scholarship facts or independent scholarship identities.

## Repository findings

### Confirmed integration seams

- `CatalogueIngestionService` already owns candidate-source processing and accepts a `WebDiscoveryProvider` dependency.
- `SafeSourceFetcher` is the established network security boundary and must remain the sole authoritative source fetcher.
- `OfficialSourceClassifier` provides the deterministic base for contextual owner/officiality assessment.
- PR4 contributes bounded crawling only after an accepted official root and remains independently disabled by default.
- The current Alembic head remains `20260817_0040`; PR5 runtime work must add the next incremental revision.
- Existing URL helpers overlap. Runtime Slice 5 must select/refactor one acquisition canonicalization policy and regression corpus instead of introducing another canonicalizer.

### Corrected architecture drift

The main specification predated accepted ADRs 0003-0006. It was corrected to make these decisions authoritative:

- run objectives use explicit `objective_kind`, scope, field-path, reason, criticality, and priority snapshots;
- only `target_candidate_id` authorizes source binding; a name or `objective_ref` cannot do so;
- `catalogue_discovery_attempts` preserves every provider request and normalized cost/tool metadata;
- provider, tool-call, and estimated-cost capacity is reserved atomically before network I/O;
- discovery creates/reuses a `DISCOVERED` candidate source before acquisition, while existing ingestion owns safe fetch and final verification;
- candidate sources carry nullable `discovery_lead_id` provenance;
- observations, assessments, promotions, and attempts use retention-safe foreign keys and mutation rules;
- failed fetches retain provenance but create no promotion; redirect convergence must not duplicate effective sources or erase lead history.

## Azure observation

Read-only CLI inspection found:

```text
subscription: Azure for Students
resource group: rg-scholarship-ai-dev
Azure OpenAI account: scholarship-ai-863780
region: japaneast
deployment: catalogue-gpt5-mini
model: gpt-5-mini 2025-08-07
deployment SKU: GlobalStandard, capacity 10
deployment state: Succeeded
subscription feature: Microsoft.CognitiveServices/OpenAI.BlockedTools.web_search = NotRegistered
```

Microsoft's current [Web Search with the Responses API guidance](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/web-search) describes stable `web_search`, while the [Azure OpenAI Responses REST reference](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/responses) still states that Web Search is unavailable through Azure OpenAI. This documentation conflict makes a protected exact-resource capability probe mandatory.

`NotRegistered` is not treated as proof that the deployment can or cannot execute stable Web Search. It is only evidence that live support has not been established for this subscription/resource. Discovery therefore remains disabled and no preview fallback is authorized.

## CI assessment

The PR's CI right-sizing is acceptable for the student-credit constraint:

- pull requests run once through the `pull_request` event rather than duplicating branch-push validation;
- concurrency cancels obsolete runs for the same PR/ref;
- browser E2E waits for the core test job;
- pull requests prove Chromium journeys, while main/manual validation retains Chromium, Firefox, and WebKit compatibility coverage;
- timeouts bound all jobs.

This changes validation scheduling, not product trust boundaries. The corrected PR head still requires complete repository and GitHub validation before merge.

## Proof classification

| Claim | State |
|---|---|
| PR5 architecture is internally coherent | Pending final document/static validation |
| Existing ingestion/fetch/classifier seams can host PR5 | Repository-audited |
| Runtime discovery implementation exists | Not started |
| Azure infrastructure for the discovery job exists | Not started |
| Stable Web Search works on the exact Azure resource/model | Unproven |
| Discovery cost per useful official lead is acceptable | Unproven |
| Autonomous scheduling or publication is authorized | No |

## Authorized next move

After this architecture PR is rebased onto the current feature branch and all checks pass, create a fresh runtime branch from the resulting feature head. Implement only Slices 1-4 first: schema/constraints, deterministic objectives and planning, repository/attempt/budget state transitions, and a fake provider. Do not add Azure calls, Bicep resources, or billable capability probes until those local boundaries are proven.
