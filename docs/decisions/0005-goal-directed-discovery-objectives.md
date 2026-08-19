# ADR 0005: Drive catalogue discovery from deterministic information objectives

- Status: Accepted for PR5 design
- Date: 2026-08-19
- Applies to: PR5 discovery planning, later autonomous acquisition orchestration, completeness-gap targeting, and acquisition budget allocation
- Related: ADR 0002, ADR 0003, ADR 0004, `docs/pr5-web-discovery-spec.md`, `docs/scholarship-information-contract.md`

## Context

The platform is not successful when it merely finds many URLs. It is successful when a canonical scholarship record becomes complete, current, correctly scoped, and backed by official evidence.

The information contract defines four criticality tiers:

- Tier 0 — identity-critical;
- Tier 1 — decision-critical;
- Tier 2 — workflow-critical;
- Tier 3 — enrichment.

It also defines deterministic completeness states:

```text
INCOMPLETE
PUBLISHABLE_WITH_GAPS
COMPLETE_CORE
COMPLETE_GRAPH
```

and explicitly states that the acquisition planner should eventually prioritize missing dimensions such as identity/provider evidence, current cycle/deadline, funding, eligibility, routes, institutions/programmes, documents/steps, and unresolved scope conflicts.

PR5's web discovery contract currently begins from a public catalogue identity objective. That is necessary but not sufficient for the final acquisition system. Without a deterministic objective engine, future autonomous discovery would tend to optimize for page count, search-result count, or crawler depth rather than catalogue quality.

The discovery planner therefore needs a stable answer to:

> What information gap are we trying to close, why is it important, and when should we stop spending acquisition budget on it?

## Decision

### 1. Discovery is objective-driven, never page-count-driven

Every discovery run must have one explicit `DiscoveryObjective` describing the information need.

A discovery objective is **not** a search query. It is the domain reason for searching.

Examples:

```text
RESOLVE_CANONICAL_SOURCE
RESOLVE_PROVIDER_IDENTITY
CURRENT_CYCLE_STATUS
CURRENT_APPLICATION_DEADLINE
CURRENT_APPLICATION_OPENING
FUNDING_COVERAGE
ELIGIBILITY_CORE
APPLICATION_ROUTE
REQUIRED_DOCUMENTS
APPLICATION_STEPS
PARTICIPATING_INSTITUTIONS
ELIGIBLE_PROGRAMMES
INSTITUTION_LOCAL_REQUIREMENTS
INSTITUTION_LOCAL_DEADLINE
RELATED_INDEPENDENT_AWARDS
CONFLICT_RESOLUTION_SOURCE
FRESHNESS_REFRESH
```

The query planner converts an objective into a small, bounded set of deterministic web-search queries.

Search output never changes the objective by itself.

### 2. Objective derivation is deterministic and downstream of graph/evidence state

The objective engine reads only reviewed catalogue/graph metadata plus current evidence/freshness/conflict state.

It must not use:

- applicant profile data;
- uploaded documents;
- private application data;
- generated assistant prose;
- search-result snippets as catalogue truth;
- model confidence scores as objective priority.

Initial PR5 supports explicit objective creation from known public catalogue identity/backlog context.

Later autonomous orchestration may derive objectives automatically from deterministic completeness evaluation, but the same objective schema and priority rules remain.

### 3. An objective contains exact target scope

A single information objective is scoped to the narrowest graph level that actually needs evidence.

Recommended schema:

```python
@dataclass(frozen=True)
class DiscoveryObjective:
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
    planner_version: str
```

Rules:

- scholarship/candidate identity context is explicit;
- cycle-specific gaps must carry cycle scope when known;
- institution-local facts must carry institution scope;
- programme-local facts must carry programme scope;
- a local objective must never be converted into a global scholarship fact objective;
- `field_paths` are allowlisted catalogue paths, not arbitrary JSON paths supplied by callers.

### 4. Objective priority is a deterministic tuple, not an opaque score

Do not use one blended AI/ML priority number.

Use a lexicographically ordered priority tuple so an operator can explain exactly why one objective ran before another.

Recommended priority tuple:

```text
(
  blocking_class,
  criticality_tier,
  conflict_or_stale_rank,
  current_cycle_rank,
  user_demand_rank,
  structural_dependency_rank,
  retry_penalty,
  deterministic_tiebreak
)
```

Lower tuple sorts first.

#### `blocking_class`

```text
0  blocks canonical identity / safe publication
1  blocks current decision-making / COMPLETE_CORE
2  blocks workflow completeness
3  blocks COMPLETE_GRAPH structural coverage
4  enrichment only
```

#### `criticality_tier`

```text
0 Tier 0
1 Tier 1
2 Tier 2
3 Tier 3
```

#### `conflict_or_stale_rank`

Suggested ordering:

```text
0 current decision-critical conflict
1 missing current decision-critical fact
2 stale decision-critical fact
3 missing workflow/graph fact
4 enrichment/freshness maintenance
```

#### `current_cycle_rank`

```text
0 current/open/upcoming cycle
1 next known cycle
2 cycle unknown but current identity requires resolution
3 historical/archive-only context
```

#### `user_demand_rank`

User demand may break ties among equally safe objectives, based on low-cardinality aggregate signals such as zero-result/search demand counts.

It must never promote Tier 2/3 work above unresolved Tier 0/Tier 1 safety blockers.

#### `structural_dependency_rank`

Prefer prerequisite objectives before dependent objectives.

Example:

```text
provider identity
  before
canonical source
  before
current cycle
  before
route-specific facts
  before
institution expansion
  before
programme expansion
```

#### `retry_penalty`

Repeated blocked/failed objectives receive a bounded penalty so one inaccessible source family cannot starve the rest of the catalogue.

#### deterministic tiebreak

Use stable identifiers/hash order. Never database insertion order or model output order.

### 5. Core safety blockers always outrank graph breadth

Default priority examples:

```text
Tier 0 identity/provider conflict
    > current deadline conflict
    > missing current cycle/status
    > missing current funding/eligibility/deadline
    > missing application route/method
    > required documents / application steps
    > institution participation coverage
    > programme coverage
    > related-award expansion
    > aliases/enrichment
```

This is intentionally quality-first.

Do not spend budget expanding 200 institutions while the umbrella scholarship still lacks trustworthy current-cycle deadline or eligibility evidence.

### 6. Completeness state alone is not enough; objective derivation uses fact/evidence reasons

`INCOMPLETE` is a summary state, not a search instruction.

The objective engine must preserve the reason for incompleteness.

Example:

```text
INCOMPLETE
  reason: IDENTITY_PROVIDER_MISSING
      -> RESOLVE_PROVIDER_IDENTITY

INCOMPLETE
  reason: CURRENT_DEADLINE_UNSUPPORTED
      -> CURRENT_APPLICATION_DEADLINE

INCOMPLETE
  reason: GLOBAL_VS_LOCAL_DEADLINE_CONFLICT
      -> CONFLICT_RESOLUTION_SOURCE scoped to institution/track
```

Do not generate a generic `complete scholarship` query.

### 7. Already-current verified facts suppress redundant discovery

If the current reviewed graph has adequate current official evidence for the objective's field/scope, the objective is satisfied and should not create new web-search calls.

Suppression requires deterministic evidence/freshness policy, not merely a non-null value.

Examples:

```text
value exists + current official evidence + correct scope
    -> suppress

value exists + stale evidence
    -> FRESHNESS_REFRESH

value exists + conflicting current official evidence
    -> CONFLICT_RESOLUTION_SOURCE

value unknown + official source explicitly does not state it
    -> may be SATISFIED_AS_UNKNOWN when completeness policy allows
```

Unknown is a valid end state when the authoritative current source genuinely does not establish the fact.

### 8. Objective terminal outcomes are explicit

An objective is not simply `done` or `failed`.

Recommended outcomes:

```text
SATISFIED
SATISFIED_AS_UNKNOWN
NOT_APPLICABLE
BLOCKED_SOURCE
NO_OFFICIAL_SOURCE_FOUND
CONFLICT_REQUIRES_REVIEW
BUDGET_EXHAUSTED
CAPABILITY_UNAVAILABLE
DEFERRED_DEPENDENCY
FAILED
```

Only deterministic downstream evidence validation can return `SATISFIED` or `SATISFIED_AS_UNKNOWN`.

Web search finding a plausible URL is not satisfaction.

### 9. Stop conditions are part of the objective contract

A run must stop searching/expanding an objective when the first applicable condition occurs:

1. required evidence is acquired and validated;
2. authoritative evidence explicitly establishes `unknown`/absence/not-applicable where allowed;
3. required prerequisite is unresolved;
4. a conflict requires human review;
5. all bounded planned queries are exhausted;
6. lead/fetch/provider/cost budget is exhausted;
7. remaining sources are login/CAPTCHA/robots/unsafe/unsupported;
8. objective retry ceiling is reached;
9. feature/capability gate is unavailable.

Do not continue crawling because additional links exist after the objective is already satisfied.

### 10. Query templates are objective-specific and deterministic

`DiscoveryQueryPlanner` maps objective kind + public identity snapshot to allowlisted query templates.

Examples:

#### canonical identity/source

```text
"{scholarship_name}" official
"{scholarship_name}" "{provider_name}"
```

#### current deadline/cycle

```text
"{scholarship_name}" deadline {cycle_hint}
"{scholarship_name}" application {cycle_hint}
```

#### funding

```text
"{scholarship_name}" funding benefits tuition stipend
```

#### eligibility

```text
"{scholarship_name}" eligibility requirements
```

#### route

```text
"{scholarship_name}" application route apply
```

#### known institution route/local requirement

```text
"{scholarship_name}" "{institution_name}" apply
"{scholarship_name}" "{institution_name}" deadline
```

Reviewed domains may constrain a query only when already resolved; discovered domains never recursively become allowed domains inside the same run.

No query template includes student/applicant/private attributes.

### 11. Discovery objectives and query rows are separate durable records

Refine the PR5 persistent design by making objective identity explicit rather than encoding the information need only in `objective_type`/`objective_ref` strings on the run.

Recommended minimal approach for PR5:

Add objective fields to `catalogue_discovery_runs`:

```text
objective_kind varchar(64)
objective_scope json NOT NULL
objective_field_paths json NOT NULL
objective_reason_codes json NOT NULL
objective_criticality_tier int NOT NULL
objective_priority_snapshot json NOT NULL
```

Keep the identity snapshot from ADR 0004:

```text
target_candidate_id UUID nullable
target_identity_snapshot json NOT NULL
```

`objective_scope`, `objective_field_paths`, `objective_reason_codes`, and `objective_priority_snapshot` use deliberately small versioned schemas.

They are audit records, not arbitrary dumps of ORM/application state.

A future autonomous orchestrator may introduce a reusable `catalogue_discovery_objectives` queue table when repeated scheduling/leases across many scholarships is implemented. PR5 does not need to prematurely add that orchestration table if runs are still explicitly created.

### 12. Objective priority snapshot is immutable per run

At run creation, persist why this objective was selected:

```json
{
  "schema_version": "catalogue-discovery-priority.v1",
  "blocking_class": 1,
  "criticality_tier": 1,
  "conflict_or_stale_rank": 1,
  "current_cycle_rank": 0,
  "user_demand_rank": 2,
  "structural_dependency_rank": 0,
  "retry_penalty": 0,
  "reason_codes": ["CURRENT_DEADLINE_MISSING"]
}
```

Do not silently recompute an in-flight run's priority after catalogue state changes.

A new orchestration cycle may create/reprioritize a new run after re-evaluating current graph state.

### 13. Objective-specific promotion still passes through ADR 0003

Even when a URL was discovered for a deadline/funding/eligibility objective, promotion remains:

```text
lead
 -> contextual deterministic assessment
 -> SafeSourceFetcher
 -> target-content binding
 -> candidate-source persistence
 -> downstream evidence/extraction/validation
```

The objective does not make the source official.

The objective does not let a local institution source become authoritative for global provider facts.

### 14. Objective fulfilment is field/scope-aware

A promoted/fetched page can help more than one objective downstream, but fulfilment is assessed separately per field/scope.

Example:

A provider application page may establish:

```text
current cycle/status      -> satisfied
application deadline     -> satisfied
application method       -> satisfied
funding amount            -> still unknown
```

Do not mark all open objectives complete merely because one page was promoted.

### 15. Conflicts create investigation objectives, not silent reconciliation

When two current official sources disagree on a decision-critical fact:

```text
CONFLICT_RESOLUTION_SOURCE
```

may search for a more authoritative/current scoped source, but the system must preserve the conflict until deterministic rules/human review resolve it.

Search ranking or model preference cannot choose a winner.

### 16. Structural discovery has explicit applicability gates

Do not generate institution/programme expansion objectives unless the scholarship structure indicates they apply.

Examples:

```text
centrally administered award with no host-list structure
    -> participating institutions may be NOT_APPLICABLE

umbrella scheme with designated universities
    -> participating institutions applicable

track with programme-specific eligibility
    -> programme expansion applicable
```

This prevents pointless crawling and protects the meaning of `COMPLETE_GRAPH`.

### 17. Independent-award discovery is lower priority than core truth and has a separate objective

Searching resolved institutions for separately named awards is useful for catalogue growth, but it must not consume budget before the known scholarship's Tier 0/Tier 1 core is safe.

Use:

```text
RELATED_INDEPENDENT_AWARDS
```

with institution scope.

Any unknown named award discovered here still follows ADR 0004's independence/evidence/review path and cannot be auto-created or auto-published.

### 18. Search demand may create backlog objectives but never live truth

Zero-result searches, frequently searched institutions/providers, and incomplete landing journeys may feed a bounded public-demand backlog.

Demand can influence which safe objective runs next, but:

- it cannot bypass identity/evidence gates;
- it cannot create a scholarship from a user query;
- it cannot trigger unreviewed live web answers on canonical truth pages;
- it cannot contain applicant PII in web-search queries.

## PR5 implementation boundary

PR5 should implement enough of this contract to support **explicit, auditable, goal-directed discovery runs**.

PR5 implementation should include:

1. objective enums/schema;
2. target identity snapshot from ADR 0004;
3. objective scope/field/reason/priority snapshot on the run;
4. deterministic objective-specific query templates;
5. objective-aware query hashing/idempotency;
6. no-search suppression for already-satisfied current identity/source objectives where the required evidence state is available;
7. metrics grouped by objective kind and terminal outcome;
8. tests proving private/applicant data cannot enter objective/query schemas.

PR5 should **not** yet implement:

- a recurring autonomous objective queue;
- global catalogue gap sweeps;
- automatic scheduling;
- automatic graph mutation;
- automatic publication;
- recursive objective generation from Web Search results;
- model-selected objectives.

Those belong to the later autonomous orchestrator after PR5 live discovery quality is proven.

## Required tests

### Objective purity

- applicant profile fields are rejected/absent from objective schema;
- document/application/private values cannot enter query context;
- only allowlisted public graph fields can appear in `field_paths`.

### Priority

- Tier 0 blocker outranks Tier 1/Tier 2/graph expansion;
- current decision-critical conflict outranks missing enrichment;
- current-cycle objective outranks historical-cycle work;
- structural prerequisite outranks dependent institution/programme expansion;
- retry penalty prevents blocked source families from starving other objectives;
- tie-breaking is deterministic.

### Suppression

- current verified official evidence suppresses redundant discovery;
- stale evidence creates refresh objective rather than silent satisfaction;
- conflicting evidence creates conflict objective;
- explicit authoritative unknown can satisfy a field as unknown when policy allows.

### Scope

- institution-local deadline objective cannot satisfy global scholarship deadline;
- programme-local requirement objective cannot mutate global eligibility;
- route-specific objective carries track scope;
- not-applicable graph dimensions do not produce expansion queries.

### Query generation

- same objective snapshot produces the same ordered query set/hash;
- discovered snippets/titles do not generate recursive queries;
- reviewed domains can constrain queries;
- unreviewed discovered domains cannot become allowed domains in the same run;
- maximum query count is enforced.

### Stop conditions

- validated fulfilment stops additional provider calls;
- budget exhaustion is terminal for the run/objective attempt;
- conflict requiring review stops further automatic truth selection;
- blocked/login/CAPTCHA/unsafe sources do not trigger bypass behavior.

## Consequences

### Positive

- Discovery spend is tied directly to catalogue quality.
- The system becomes explainable: every search has a reason code and field/scope target.
- Core scholarship truth is completed before graph breadth/enrichment.
- The later autonomous acquisition loop can reuse the same objective contract instead of inventing a second planner.
- Search/crawl stopping becomes deterministic and budget-aware.
- Human review receives meaningful exceptions rather than a pile of arbitrary pages.

### Cost

- PR5 run schema becomes slightly richer.
- Completeness/reason-code coverage must be made explicit over time.
- Later orchestration still needs a durable queue/lease layer for repeated objective scheduling across the catalogue.

This cost is preferable to an autonomous crawler whose optimization target is merely "find more pages".
